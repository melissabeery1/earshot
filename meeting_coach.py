"""The listening scorecard for a recorded call. Free and on this Mac: no AI.

    .venv/bin/python meeting_coach.py "<meeting folder>"

Built on published measures, not a made-up grade (your ask). Each benchmark names its source:
  - Follow-up questions: Huang, Yeomans, Brooks, Minson & Gino (2017), "It Doesn't Hurt to Ask: Question-Asking
    Increases Liking", Journal of Personality and Social Psychology 113(3). Follow-up questions, the kind that
    build on what the other person just said, were the ones tied to being liked.
  - Reflections to questions (MITI, the Motivational Interviewing Treatment Integrity code: 1 per question is
    beginning proficiency, 2 competent) were tried here and dropped: matching words can't recognise a reflection
    said in new words. Coach me with Claude counts them instead.
  - Longest monologue and talk share: Gong's analysis of recorded sales calls (industry data, not peer reviewed):
    keep monologues to 2.5 minutes; winning calls sat between about 43% and 57% seller talk.
  - Response gap: Stivers et al. (2009), PNAS, ten languages: about 0.2 seconds between turns is the human norm.
  - Overlaps: Tannen's "cooperative overlap". Talking along with someone isn't always interrupting; it only
    takes the floor when they stop.
The deeper listening ratings (the Active-Empathic Listening Scale's sensing, processing and responding) need a
person or Claude to judge, so they live in face menu > Recent meetings > Coach me with Claude.

Reads turns.json (from meeting_finish.py) for words and the two audio tracks for timing. Writes coach.md and a
line in coach-history.csv in the meetings folder. Whisper drops most "um"s, so filler counts run low.
"""
import json
import os
import re
import sys
import wave
from datetime import datetime

import numpy as np

FRAME = 0.03                                                       # seconds per loudness reading

BACKCHANNEL = {"yeah", "yep", "yes", "mm-hmm", "mhm", "hmm", "right", "okay", "ok", "totally", "sure", "nice",
               "wow", "oh", "cool", "great", "exactly", "same", "uh-huh", "good", "awesome", "true", "no", "of",
               "course", "interesting", "absolutely", "definitely", "agreed", "so", "and", "i", "know"}
FILLERS = ["um", "uh", "you know", "sort of", "kind of", "i mean", "basically", "literally", "honestly",
           "for lack of a better word", "for lack of a better way of saying it", "like, ", "right?"]
HEDGES = ["i don't know", "i think", "maybe", "i guess", "probably", "i'm not sure", "a little bit",
          "i'm so new", "i'm still"]
OPEN_Q = re.compile(r"^\s*(what|how|why|which|where|when|who|tell me|walk me|talk me)\b", re.I)


STOP = set("""about above after again against also am an and any are aren't as at be because been before being
below between both but by can can't could couldn't did didn't do does doesn't doing don't down during each even
every few for from further get gets getting go going gonna got had has have having he her here hers herself him
himself his how i i'm i've i'd i'll if in into is isn't it it's its itself just kind know like lot made make many
maybe me mean more most much my myself no nor not now of off on once one only or other our ours out over own
pretty probably really right said same say she should so some something sort still such sure than that that's the
their them then there these they they're thing things think this those through to too totally um uh under until
up very want was wasn't way we well were what when where which while who why will with would yeah yes yet you
you're your yours actually okay oh great cool little bit""".split())


def stems(t):
    """The words that carry meaning, cut to five letters so "companies" matches "company"."""
    return {w[:5] for w in words(t) if len(w) >= 4 and w not in STOP}


def words(t):
    return re.findall(r"[a-z0-9'-]+", t.lower())


def is_backchannel(t):
    w = words(t)
    return len(w) <= 4 and all(x in BACKCHANNEL for x in w)


def clock(ms):
    s = max(0, int(ms)) // 1000
    return f"{s // 60}:{s % 60:02d}"


def opening(text, n=9):
    w = text.split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def speech(path):
    """When this track has someone talking: a list of (start, end) in ms, from loudness, not from Whisper.
    Whisper's line endings run on into the silence after a person stops, which made every handover look
    like an interruption (35 of them in a 30-minute test call). The sound itself doesn't."""
    with wave.open(path) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    n = int(rate * FRAME)
    frames = a[:len(a) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9)
    floor = np.percentile(db, 20)                                  # the room with nobody talking
    on = db > min(max(floor + 15, -50), -28)
    runs, start = [], None
    for i, v in enumerate(np.r_[on, False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append([start, i]); start = None
    joined = []
    for r in runs:                                                 # gaps under 0.4 s are breaths, not stops
        if joined and r[0] - joined[-1][1] < 0.4 / FRAME:
            joined[-1][1] = r[1]
        else:
            joined.append(r)
    ms = int(FRAME * 1000)
    return [(a0 * ms, a1 * ms) for a0, a1 in joined if (a1 - a0) * FRAME >= 0.2]


def busy(spans, t0, t1):
    """How many ms of [t0, t1] these spans cover."""
    return sum(max(0, min(b, t1) - max(a, t0)) for a, b in spans)


def say_at(turns, who, t):
    """Your (or their) words at a moment, for quoting: the line that starts closest to it."""
    best = min((x for x in turns if (x["who"] == "Me") == (who == "Me")),
               key=lambda x: abs(x["start"] - t), default=None)
    return best["text"] if best else ""



def analyse(turns, folder):
    me = [t for t in turns if t["who"] == "Me"]
    them = [t for t in turns if t["who"] != "Me"]
    real = [t for t in turns if not is_backchannel(t["text"])]
    me_real = [t for t in real if t["who"] == "Me"]
    them_real = [t for t in real if t["who"] != "Me"]
    me_words = sum(len(words(t["text"])) for t in me_real)
    them_words = sum(len(words(t["text"])) for t in them_real)
    length_min = max((t["end"] for t in turns), default=0) / 60000 or 1

    # Questions you asked.
    qs = []
    for t in me:
        for sent in re.findall(r"[^.?!]*\?", t["text"]):
            sent = sent.strip()
            # "…you know?" and "…right?" are habits, not questions; "When was that? When was that?" is one.
            if len(words(sent)) < 3 or re.search(r"\b(you know|right|okay|yeah)\?$", sent, re.I) \
                    or re.match(r"^\s*you know what", sent, re.I):
                continue
            if qs and words(qs[-1]["text"])[-3:] == words(sent)[-3:] and t["start"] - qs[-1]["at"] < 20000:
                continue
            # Questions to yourself ("Am I saying it backwards?") aren't asked of them; Huang and MITI count
            # questions to the other person.
            if re.search(r"\b(i|my|me)\b", sent, re.I) and not re.search(r"\byou(r)?\b", sent, re.I):
                continue
            core = re.sub(r"^\s*((oh|so|and|but|okay|well|um|uh|yeah|like),?\s+)+", "", sent, flags=re.I)
            if len(words(sent)) >= 3:
                qs.append({"at": t["start"], "text": sent, "open": bool(OPEN_Q.match(core)),
                           "about_them": bool(re.search(r"\byou(r|'re|'ve)?\b", sent, re.I))})

    # ---- timing, from the sound of each track (they're on one clock)
    mine_path = os.path.join(folder, "me_clean.wav")
    if not os.path.exists(mine_path):
        mine_path = os.path.join(folder, "me.wav")
    mine, theirs = speech(mine_path), speech(os.path.join(folder, "them.wav"))

    # A short burst of yours while they're mid-flow is a "yeah" or "mm-hmm": listening, not taking the floor.
    def nod(span, other):
        a, b = span
        return 250 <= b - a < 1200 and busy(other, a - 1500, a) > 700 and busy(other, b, b + 1500) > 700
    my_nods = [s for s in mine if nod(s, theirs)]
    my_turns = [s for s in mine if not nod(s, theirs)]
    their_turns = [s for s in theirs if not nod(s, mine)]

    def cut_ins(starts, other, other_turns):
        """Starting while the other person is still going: they had been talking for at least a second, and
        they keep talking for most of the next second."""
        hits = []
        for a, b in starts:
            if b - a < 1500 or (hits and a - hits[-1] < 8000):        # one tussle counts once
                continue
            if busy(other, a - 1000, a) > 700 and busy(other, a, a + 1000) > 600:
                hits.append(a)
        return hits
    my_cut_ins_at = cut_ins(my_turns, theirs, their_turns)
    their_cut_ins_at = cut_ins(their_turns, mine, my_turns)
    my_cut_ins = [{"at": t, "text": say_at(turns, "Me", t + 500), "over": opening(say_at(turns, "Them", t - 500), 6)}
                  for t in my_cut_ins_at]
    their_cut_ins = [{"at": t} for t in their_cut_ins_at]

    # How long you wait after they stop: each time the floor passes from them to you.
    gaps = []
    for a, b in my_turns:
        before = [e for s0, e in their_turns if e <= a + 200 and e > a - 3000]
        if before and busy(mine, max(before) - 3000, max(before)) < 300:
            gaps.append(a - max(before))
    gaps.sort()
    median_gap = gaps[len(gaps) // 2] if gaps else 0

    # Stretches: your talk joined across their "yeah"s; it ends when they actually take the floor.
    stretches = []
    for a, b in my_turns:
        if stretches and busy(their_turns, stretches[-1]["end"], a) < 1200:
            stretches[-1]["end"] = b
        else:
            stretches.append({"start": a, "end": b})
    for st in stretches:
        st["text"] = say_at(turns, "Me", st["start"] + 1000)
    stretches.sort(key=lambda x: x["end"] - x["start"], reverse=True)

    nods = len(my_nods)
    them_min = sum(b - a for a, b in their_turns) / 60000 or 1
    me_secs_audio = sum(b - a for a, b in my_turns) / 1000 or 1
    them_secs_audio = sum(b - a for a, b in their_turns) / 1000 or 1

    text = " " + " ".join(t["text"] for t in me_real).lower() + " "
    fillers = {f.strip(" ,?"): len(re.findall(r"(?<![a-z])" + re.escape(f), text)) for f in FILLERS}
    fillers = {k: v for k, v in fillers.items() if v}
    hedges = {h: len(re.findall(r"(?<![a-z])" + re.escape(h), text)) for h in HEDGES}
    hedges = {k: v for k, v in hedges.items() if v}
    restarts = len(re.findall(r"\b(\w+), \1\b", text))          # "I, I" / "it's, it's"
    # Words a minute over your stretches, pauses included, the way people usually measure speaking pace.
    pace = round(me_words / (sum(x["end"] - x["start"] for x in stretches) / 60000 or 1))

    share = me_secs_audio / (me_secs_audio + them_secs_audio)        # share of the talking time
    longest = (stretches[0]["end"] - stretches[0]["start"]) / 1000 if stretches else 0

    # Follow-up questions (Huang et al. 2017): your question builds on what they'd been saying, the last 80 or so
    # of their words before it (their answers run long, and their last line is often just "go ahead").
    def their_recent(t, need=80):
        out = []
        for x in reversed([x for x in them_real if x["start"] < t]):
            out = x["text"].split() + out
            if len(out) >= need:
                break
        return " ".join(out[-need:])
    for q in qs:
        reported = re.match(r"^\s*(and )?(i'm|i was|she's|he's|they're) like\b", q["text"], re.I)
        q["follow_up"] = not reported and bool(stems(q["text"]) & stems(their_recent(q["at"] + 1)))
    follow_ups = [q for q in qs if q["follow_up"]]

    # Reflections (MITI): the opening of your turn right after they speak gives back their own content
    # ("You could always extrapolate from your Substack to seed your LinkedIn"). Matched from the words, so a
    # reflection in all-new words ("branching out your ecosystem") is missed; Coach me with Claude catches those.
    reflections = []
    for t in me_real:
        before = [x for x in them_real if x["start"] < t["start"] and t["start"] - x["end"] < 4000]
        if not before:
            continue
        first = re.split(r"(?<=[.?!])\s+", t["text"].strip())
        opening_ = " ".join(first[:2])
        if "?" in opening_ or not 3 <= len(words(opening_)) <= 30:
            continue
        shared = stems(opening_) & stems(their_recent(t["start"], 60))
        if len(shared) >= 2 or (len(shared) >= 1 and len(words(opening_)) <= 12):
            reflections.append({"at": t["start"], "text": opening_})
    rq = len(reflections) / max(1, len(qs))

    # Overlaps (Tannen): did you take the floor (they stopped), or were they talking together (both went on)?
    took_floor = [c for c in my_cut_ins if busy(theirs, c["at"] + 1000, c["at"] + 3000) < 500]
    together = [c for c in my_cut_ins if c not in took_floor]
    they_took_floor = [c for c in their_cut_ins if busy(mine, c["at"] + 1000, c["at"] + 3000) < 500]

    fu_rate = len(follow_ups) / length_min * 10
    bench = [
        ("Follow-up questions", fu_rate >= 2,
         f"{len(follow_ups)} of your {len(qs)} questions built on what they'd just said, {fu_rate:.1f} per 10 minutes. "
         "Follow-ups were the questions tied to being liked (Huang et al. 2017). The bar of 2 per 10 minutes is mine; "
         "the study says more is better."),
        ("Longest monologue under 2.5 minutes", longest <= 150,
         f"Your longest was {longest / 60:.1f} minutes. Gong's sales-call data puts the limit at 2.5 minutes, "
         "after which the other person drifts."),
        ("Talk share between 43% and 57%", 0.43 <= share <= 0.57,
         f"You did {share:.0%} of the talking. Gong's winning sales calls sat in this range (industry data, "
         "not peer reviewed)."),
    ]
    met = sum(1 for _, ok, _ in bench if ok)

    talk_secs, listen_secs = me_secs_audio, them_secs_audio
    return dict(bench=bench, met=met, share=share, talk_secs=talk_secs, listen_secs=listen_secs, me_words=me_words, them_words=them_words,
                stretches=stretches, qs=qs, follow_ups=follow_ups, reflections=reflections, rq=rq,
                my_cut_ins=my_cut_ins, their_cut_ins=their_cut_ins, took_floor=took_floor, together=together,
                they_took_floor=they_took_floor, median_gap=median_gap, gaps=gaps, nods=nods, them_min=them_min,
                fillers=fillers, hedges=hedges, restarts=restarts, pace=pace, length_min=length_min, longest=longest)


def tips(a):
    out = []
    if a["longest"] > 150:
        s = a["stretches"][0]
        out.append(f"Your longest run was {a['longest'] / 60:.1f} minutes, from {clock(s['start'])} "
                   f"(\"{opening(s['text'])}\"). Around the one-minute mark, hand it back: \"want the short version "
                   "or how it works?\"")
    if len(a["follow_ups"]) < len(a["qs"]) / 2 or a["length_min"] / 10 * 2 > len(a["follow_ups"]):
        out.append("Ask about what they just said, not a new topic: \"what would the fractional offer have to "
                   "include for a Series B to say yes?\" builds on them; \"are you going to that event?\" moves on.")
    if len(a["took_floor"]) >= 3:
        out.append(f"You took the floor mid-sentence {len(a['took_floor'])} times (they stopped when you started). "
                   "Let them land the sentence; Stivers' 0.2-second gap is all you need.")
    if a["share"] > 0.57:
        out.append(f"You did {a['share']:.0%} of the talking. Close to half is the target.")
    if not out:
        out.append("A well-balanced call on every measure here.")
    return out


def write(folder, a):
    meta = {}
    try:
        meta = json.load(open(os.path.join(folder, "meeting.json")))
    except (OSError, ValueError):
        pass
    started = datetime.fromtimestamp(meta.get("started", os.path.getmtime(folder)))
    L = [f"# Listening scorecard, {started.strftime('%a %-d %b %Y, %-I:%M %p')}", "",
         f"**{a['met']} of {len(a['bench'])} research benchmarks met** · a {a['length_min']:.0f}-minute call", "",
         "## The benchmarks", ""]
    L += [f"- {'Met' if ok else 'Not yet'}: **{name}.** {why}" for name, ok, why in a["bench"]]
    L += ["", "## What to work on", ""] + [f"- {t}" for t in tips(a)]
    gap = a["median_gap"] / 1000
    L += ["", "## Context (no pass or fail)", "",
          f"- **Your pause before answering:** {gap:.1f} seconds typically. The human norm across ten languages is "
          "about 0.2 (Stivers et al. 2009), so " + ("you're right in the normal range." if 0 <= gap <= 0.6 else
          "you often start before they've finished." if gap < 0 else "you take a little longer than most."),
          f"- **Talking over each other:** you started while they were talking {len(a['my_cut_ins'])} times. "
          f"{len(a['took_floor'])} took the floor (they stopped); {len(a['together'])} were talking together, which "
          "Tannen calls cooperative overlap, a sign of enthusiasm in a friendly chat. They took the floor from you "
          f"{len(a['they_took_floor'])} times.",
          f"- **Listening sounds:** {a['nods']} yeahs and mm-hmms while they talked, {a['nods'] / a['them_min']:.1f} a minute.",
          f"- **Pace:** {a['pace']} words a minute, pauses included.",
          f"- **Restarted words** (\"I, I\"): {a['restarts']}."]
    if a["hedges"]:
        L.append("- **Softeners:** " + ", ".join(f"\"{k}\" {v}" for k, v in sorted(a["hedges"].items(), key=lambda kv: -kv[1])) + ".")
    if a["fillers"]:
        L.append("- **Fillers:** " + ", ".join(f"\"{k}\" {v}" for k, v in sorted(a["fillers"].items(), key=lambda kv: -kv[1]))
                 + ". (Whisper leaves out most ums, so these run low.)")
    L += ["", "## Your questions", ""]
    if a["qs"]:
        L += [f"- {clock(q['at'])} {q['text']}" + (" *(follow-up)*" if q["follow_up"] else "") for q in a["qs"]]
    else:
        L.append("- None picked up.")
    L += ["", "## Your three longest stretches", ""]
    L += [f"- {clock(s['start'])}, {(s['end'] - s['start']) / 60000:.1f} minutes: \"{opening(s['text'], 14)}\""
          for s in a["stretches"][:3]]
    if a["took_floor"]:
        L += ["", "## Where you took the floor", ""]
        L += [f"- {clock(c['at'])} over \"{c['over']}\": \"{opening(c['text'])}\"" for c in a["took_floor"]]
    L += ["", "*Worked out on this Mac: timing from the sound of each side, words from the transcript. Question, "
          "follow-up and reflection counts are matched from the words, so treat them as close, not exact. For the "
          "judgment calls (reflections versus questions as MITI counts them, how your ideas landed, what you could "
          "have asked), use Coach me with Claude in the face menu. Reflections were tried here and dropped: matching "
          "words can't tell \"branching out your ecosystem\" is one.*", ""]
    with open(os.path.join(folder, "coach.md"), "w") as f:
        f.write("\n".join(L))
    # The numbers on their own, for the call review page.
    with open(os.path.join(folder, "coach.json"), "w") as f:
        json.dump({"talk_secs": round(a["talk_secs"]), "listen_secs": round(a["listen_secs"]), "share": round(a["share"], 3),
                   "length_min": round(a["length_min"], 1), "longest_secs": round(a["longest"]),
                   "benchmarks_met": a["met"], "benchmarks": len(a["bench"]), "nods": a["nods"],
                   "follow_ups": len(a["follow_ups"]), "questions": len(a["qs"]),
                   "took_floor": len(a["took_floor"]), "pace": a["pace"]}, f, indent=1)

    hist = os.path.join(os.path.dirname(folder), "coach-history.csv")
    head = "meeting,benchmarks_met,talk_share,questions,follow_ups,reflections,longest_secs,took_floor,pace\n"
    rows = []
    if os.path.exists(hist) and open(hist).readline() == head:
        rows = [r for r in open(hist).read().splitlines()[1:] if not r.startswith(os.path.basename(folder) + ",")]
    rows.append(f"{os.path.basename(folder)},{a['met']},{a['share']:.2f},{len(a['qs'])},{len(a['follow_ups'])},"
                f"{len(a['reflections'])},{a['longest']:.0f},{len(a['took_floor'])},{a['pace']}")
    with open(hist, "w") as f:
        f.write(head + "\n".join(sorted(rows)) + "\n")


def main(folder):
    path = os.path.join(folder, "turns.json")
    if not os.path.exists(path):
        print("No turns.json in that folder (re-run meeting_finish.py on it first).")
        return
    turns = json.load(open(path))
    if not any(t["who"] == "Me" for t in turns):
        return
    a = analyse(turns, folder)
    write(folder, a)
    print(os.path.join(folder, "coach.md"), f"{a['met']} of {len(a['bench'])}")


if __name__ == "__main__":
    main(sys.argv[1])
