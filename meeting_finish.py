"""Turns a recorded meeting into a Me / Them transcript.

    .venv/bin/python meeting_finish.py "<meeting folder>"

The folder holds me.wav (your microphone) and them.wav (what the Mac played). Each is transcribed on this
Mac by whisper.cpp; the two are merged by time into transcript.md, and a shortcut goes into
~/Desktop/Latest.

On speakers, your mic also hears the others, so their words came out twice: once as Me, once as Them.
Two passes take that echo out:
  1. By sound. them.wav is exactly what the speakers played, so wherever your mic holds nothing louder than
     that sound leaking back in, it's turned down before transcription. Needs the two tracks on one clock,
     which meetcap gives from.
  2. By words. Any run of three or more words in a Me line that also turns up in a Them line close by is cut.
Recordings from before 30 Oct (mic from ffmpeg, which dropped audio) skip step 1, and step 2 matches the
whole of both transcripts in order instead of by time.
"""
import json
import os
import re
import subprocess
import sys
import wave
from datetime import datetime
from difflib import SequenceMatcher

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "ggml-large-v3-turbo-q5_0.bin")
VAD = os.path.join(HERE, "models", "ggml-silero-v5.1.2.bin")   # finds the speech, so timestamps survive long silences
WHISPER = "/opt/homebrew/bin/whisper-cli"
RATE = 16000


def words():
    """Your names, as a punctuated sentence. Whisper copies the style of its prompt, and with --carry-initial-prompt
    it sees the prompt every 30 seconds: a bare list of names gave whole minutes with no punctuation at all
    (0 full stops in 6 minutes of your talking), the same names in a sentence gave 65."""
    try:
        names = open(os.path.join(HERE, "words.txt")).read().strip().rstrip(",.")
    except OSError:
        return ""
    return f"Hello, and welcome. Today's conversation mentions {names}." if names else ""


# ------------------------------------------------------------------ audio

def load(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def save(path, a):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())


def lag(me, them):
    """How many samples your mic hears the speakers after they played (searching up to half a second)."""
    n = min(len(me), len(them), RATE * 600)
    a, b = me[:n], them[:n]
    size = 1 << (2 * n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    k = RATE // 2
    return int(np.r_[np.arange(k), np.arange(-k, 0)][np.argmax(np.r_[c[:k], c[-k:]])])


N, HOP, TAIL = 512, 256, 6        # 32 ms frames, half overlapping; the room rings for ~6 frames (100 ms)
WIN = np.hanning(N).astype(np.float32)


def spectra(a, first, last):
    """Frames first..last-1 of `a`, as spectra (complex64)."""
    idx = np.arange(N)[None, :] + HOP * np.arange(first, last)[:, None]
    return np.fft.rfft(a[idx] * WIN, axis=1).astype(np.complex64)


def remove_echo(folder):
    """Writes me_clean.wav: your mic with the call's sound taken out, frequency by frequency. A minute at a time,
    so a long call doesn't fill the memory."""
    me, them = load(os.path.join(folder, "me.wav")), load(os.path.join(folder, "them.wav"))
    d = lag(me, them)
    shifted = np.zeros_like(me)
    src = them[max(0, -d):]
    shifted[max(0, d):max(0, d) + len(src)] = src[:len(me) - max(0, d)]
    frames = 1 + max(0, len(me) - N) // HOP

    # How loudly the speakers reach the mic, per frequency: the typical ratio while the call side is talking,
    # taken from every fourth frame.
    sample = np.arange(0, frames, 4)
    idx = np.arange(N)[None, :] + HOP * sample[:, None]
    Ms = np.abs(np.fft.rfft(me[idx] * WIN, axis=1)).astype(np.float32)
    Ts = np.abs(np.fft.rfft(shifted[idx] * WIN, axis=1)).astype(np.float32)
    level = Ts.sum(1)
    loud = level > max(np.percentile(level, 70), 1e-3)
    if loud.sum() < 50:                                        # the call side was silent: nothing to remove
        return os.path.join(folder, "me.wav"), d
    leak = np.median(Ms[loud] / (Ts[loud] + 1e-6), axis=0)
    del Ms, Ts, idx

    out = np.zeros(len(me) + N, np.float32)
    weight = np.zeros(len(me) + N, np.float32)
    step = 4096
    for f0 in range(0, frames, step):
        f1 = min(frames, f0 + step)
        p0 = max(0, f0 - TAIL)
        M = spectra(me, f0, f1)
        Tm = np.abs(spectra(shifted, p0, f1))
        # The room keeps ringing for a moment after a sound stops, so each frame takes the loudest of the last 100 ms.
        Tr = Tm.copy()
        for k in range(1, TAIL + 1):
            Tr[k:] = np.maximum(Tr[k:], Tm[:-k] * (0.8 ** k))
        Tr = Tr[f0 - p0:]
        gain = np.clip(1 - 2.0 * leak * Tr / (np.abs(M) + 1e-6), 0, 1)   # take out twice the expected echo
        clean = np.fft.irfft(M * gain, N, axis=1).astype(np.float32) * WIN
        for i, fr in enumerate(clean):
            s = (f0 + i) * HOP
            out[s:s + N] += fr
            weight[s:s + N] += WIN ** 2
    path = os.path.join(folder, "me_clean.wav")
    save(path, (out / np.maximum(weight, 1e-3))[:len(me)])
    return path, d


# ------------------------------------------------------------------ speech to text

SENTENCE = re.compile(r"[^.?!]+[.?!]*")


def transcribe(folder, wav, who):
    if not os.path.exists(wav) or os.path.getsize(wav) < 16000:      # under half a second of sound
        return []
    out = os.path.join(folder, who.lower())
    # After an A/B against a paid notetaker on a 30-minute call:
    #   --carry-initial-prompt  your word list reaches every 30-second piece, not just the first
    #                           ("sub stack", "cloud code" later in the call).
    #   -ml 120 -sow            lines of a sentence or so, split between words, so a long stretch from one side
    #                           can't swallow the other's interruption and the conversation stays in order.
    #   Tried and dropped: -mc 0 (no memory of earlier text) stopped a skipped passage but cost whole minutes
    #   of punctuation; -mc 64 lost punctuation too. MEETING_WHISPER_FLAGS overrides these for testing.
    subprocess.run([WHISPER, "-m", MODEL, "-f", wav, "-l", "en", "-np", "-oj", "-of", out, "--prompt", words(),
                    "--carry-initial-prompt", *os.environ.get("MEETING_WHISPER_FLAGS", "-ml 120 -sow").split(),
                    "--vad", "-vm", VAD, "-vsd", "500"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return parse(out + ".json", who)


def parse(path, who):
    with open(path) as f:
        data = json.load(f)
    segs = []
    for s in data.get("transcription", []):
        text = s.get("text", "").strip()
        if not text or text[0] in "[(":                              # [BLANK_AUDIO], (music)
            continue
        start, end = s["offsets"]["from"], s["offsets"]["to"]
        # Deep into a long recording whisper can start writing a word or two per line; those join back up
        # into sentences, or the cleanup below mistakes them for stray scraps.
        if segs and start - segs[-1]["end"] < 1000 and (len(text.split()) < 4 or len(segs[-1]["text"].split()) < 4):
            segs[-1]["text"] += " " + text
            segs[-1]["end"] = end
        else:
            segs.append({"who": who, "start": start, "end": end, "text": text})
    # Whisper sometimes gets stuck and writes one sentence over and over ("And so that's what we're going to
    # do." six times on 30 Oct). A sentence of four or more words said three times within two minutes is that.
    seen = {}
    for n, s in enumerate(segs):
        for m in SENTENCE.finditer(s["text"]):
            key = " ".join(norm(w) for w in m.group().split())
            if len(key.split()) >= 4:
                seen.setdefault(key, []).append(s["start"])
    stuck = {k for k, ts in seen.items() if any(ts[i + 2] - ts[i] < 120000 for i in range(len(ts) - 2))}
    def is_stuck(sentence):                          # the loop sentence, or a broken-off end of it
        key = " ".join(norm(w) for w in sentence.split())
        return key in stuck or (len(key.split()) >= 3 and any(k.endswith(" " + key) for k in stuck))
    if stuck:
        for s in segs:
            s["text"] = " ".join(m.group().strip() for m in SENTENCE.finditer(s["text"])
                                 if not is_stuck(m.group())).strip()
        segs = [s for s in segs if s["text"]]
    return segs


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def mark(a, b, fits=lambda blk: True):
    """True for each word of `a` that sits in a run of 3+ words also found, in order, in `b`. `fits` can turn
    down a short run that turns up at the wrong moment."""
    echo = [False] * len(a)
    blocks = [blk for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
              if blk.size >= 6 or (blk.size >= 3 and fits(blk))]
    for blk in blocks:
        for i in range(blk.a, blk.a + blk.size):
            echo[i] = True
    # Your mic hears the speakers a little differently ("read the screen" for "redesign them"), so a short scrap
    # next to an echoed run is echo too if it's just a few words, or if it sounds like the words the call
    # side said at that point.
    edges = [(0, 0, False)] + [(blk.a + blk.size, blk.b + blk.size, True) for blk in blocks]
    starts = [(blk.a, blk.b, True) for blk in blocks] + [(len(a), len(b), False)]
    for (a0, b0, left), (a1, b1, right) in zip(edges, starts):
        n = a1 - a0
        if n <= 0 or n > 6 or not (left or right):
            continue
        said = " ".join(b[max(0, b0 - 2):max(b1, b0) + 2])
        if (left and right and n <= 3) or SequenceMatcher(None, " ".join(a[a0:a1]), said).ratio() >= 0.5:
            for i in range(a0, a1):
                echo[i] = True
    return echo


def rebuild(s, toks, echo):
    """What's left of a Me line after its echo is cut: one or more lines, timed by where they sat."""
    out, span, run = [], s["end"] - s["start"], []
    for i, t in enumerate(toks + [None]):
        if t is not None and not echo[i]:
            run.append(i)
        elif run:
            text = " ".join(toks[k] for k in run)
            if len(run) >= 3 or norm(text) not in ("", "the", "and", "so", "i", "a", "to", "it", "of"):
                out.append({"who": "Me", "text": text,
                            "start": s["start"] + span * run[0] // len(toks),
                            "end": s["start"] + span * (run[-1] + 1) // len(toks)})
            run = []
    return out


def strip_echo(me, them, window):
    """Cuts from each Me line any run of 3+ words that a Them line within `window` ms also has."""
    out, cut = [], 0
    for s in me:
        toks = s["text"].split()
        near = [w for t in them if t["start"] < s["end"] + window and s["start"] < t["end"] + window
                for w in t["text"].split()]
        echo = mark([norm(w) for w in toks], [norm(w) for w in near]) if near else [False] * len(toks)
        cut += sum(echo)
        out += rebuild(s, toks, echo)
    return out, cut


def strip_echo_by_order(me, them):
    """For old recordings whose mic lost audio, so Me times can't be trusted: the whole Me transcript is
    matched against the whole Them transcript in order, which needs no times at all. The matches then
    double as anchors that put the Me lines that are left on the Them clock."""
    a, where = [], []
    for n, s in enumerate(me):
        toks = s["text"].split()
        for k in range(len(toks)):
            a.append(norm(toks[k])); where.append((n, k, s["start"] + (s["end"] - s["start"]) * k // len(toks)))
    b, when = [], []
    for s in them:
        toks = s["text"].split()
        for k in range(len(toks)):
            b.append(norm(toks[k])); when.append(s["start"] + (s["end"] - s["start"]) * k // len(toks))
    # Runs of six or more words are surely echo; they set the clock. A shorter run ("the kind of") only
    # counts if it turns up within 15 seconds of where that clock puts it.
    xs, ys = [], []
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if blk.size >= 6:
            xs.append(where[blk.a][2]); ys.append(when[blk.b])
    def to_them(x):
        return int(np.interp(x, xs, ys, left=x + ys[0] - xs[0], right=x + ys[-1] - xs[-1])) if xs else x
    echo = mark(a, b, lambda blk: abs(to_them(where[blk.a][2]) - when[blk.b]) < 15000)
    out, i = [], 0
    for s in me:
        toks = s["text"].split()
        flags = echo[i:i + len(toks)]; i += len(toks)
        for piece in rebuild(s, toks, flags):
            piece["start"], piece["end"] = to_them(piece["start"]), to_them(piece["end"])
            out.append(piece)
    return out, sum(echo)


# ------------------------------------------------------------------ writing it up

def clock(ms):
    s = ms // 1000
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def main(folder):
    me_wav, them_wav = os.path.join(folder, "me.wav"), os.path.join(folder, "them.wav")
    them = transcribe(folder, them_wav, "Them")
    one_clock = (os.path.exists(me_wav) and os.path.exists(them_wav)
                 and abs(os.path.getsize(me_wav) - os.path.getsize(them_wav)) < RATE * 2 * 3)   # within 3 seconds
    if one_clock and them:
        me_wav, _ = remove_echo(folder)
    me = transcribe(folder, me_wav, "Me")
    heard = sum(len(s["text"].split()) for s in me)
    me, cut = strip_echo(me, them, 3000) if one_clock else strip_echo_by_order(me, them)
    # A lone "yeah" or "mm-hmm" in the middle of someone else's sentence stays out of the way.
    me = [s for s in me if len(s["text"].split()) > 2
          or not any(t["start"] < s["start"] and s["end"] < t["end"] for t in them)]
    segs = sorted(me + them, key=lambda s: s["start"])

    # Consecutive lines from the same person, close together, read as one paragraph.
    turns = []
    for s in segs:
        if turns and turns[-1]["who"] == s["who"] and s["start"] - turns[-1]["end"] < 2500:
            turns[-1]["text"] += " " + s["text"]
            turns[-1]["end"] = max(turns[-1]["end"], s["end"])
        else:
            turns.append(dict(s))

    meta = {}
    try:
        meta = json.load(open(os.path.join(folder, "meeting.json")))
    except (OSError, ValueError):
        pass
    started = datetime.fromtimestamp(meta.get("started", os.path.getmtime(folder)))
    length = clock(max((s["end"] for s in segs), default=0))
    title = f"Meeting, {started.strftime('%a %-d %b %Y, %-I:%M %p')}"
    lines = [f"# {title}", "",
             f"*{meta.get('app', 'Call')} · {length} long · recorded and transcribed on this Mac*", ""]
    if not turns:
        lines.append("Nothing was said, or the recording was silent.")
    for t in turns:
        lines += [f"**{t['who']}** ({clock(t['start'])}): {t['text']}", ""]
    path = os.path.join(folder, "transcript.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    with open(os.path.join(folder, "turns.json"), "w") as f:    # exact times, for the listening scorecard
        json.dump(turns, f)
    with open(os.path.join(folder, "echo.json"), "w") as f:     # for checking the echo removal later
        json.dump({"one_clock": one_clock, "me_words_heard": heard, "me_words_cut_as_echo": cut,
                   "me_words_kept": sum(len(s["text"].split()) for s in me),
                   "them_words": sum(len(s["text"].split()) for s in them)}, f)

    # The listening scorecard (coach.md), worked out on this Mac from the times..
    subprocess.run([sys.executable, os.path.join(HERE, "meeting_coach.py"), folder],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # The call review (review.html): Claude reads the transcript and scorecard and writes feedback pinned to
    # moments. It takes a few minutes, so it runs on its own and a notification says when it's ready.
    settings = json.load(open(os.path.join(HERE, "settings.json")))
    if settings.get("call_reviews", True) and not os.environ.get("EARSHOT_TEST"):
        subprocess.Popen([sys.executable, os.path.join(HERE, "meeting_review.py"), folder, "--notify"],
                         stdout=open(os.path.join(folder, "review.log"), "w"), stderr=subprocess.STDOUT,
                         start_new_session=True)
    print(path)


if __name__ == "__main__":
    main(sys.argv[1])
