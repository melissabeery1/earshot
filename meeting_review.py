"""The call review: a deep read of one recorded call, turned into a page you can take in in two
minutes without rereading the transcript. Every finding is pinned to a moment, with what they said, what you
said, and the words to try instead, and a play button for the moment itself.

    .venv/bin/python meeting_review.py "<meeting folder>"            review it with Claude, then make the page
    .venv/bin/python meeting_review.py "<meeting folder>" --page     only remake the page from review.json

The judgment comes from Claude through the Claude Code command line (`claude -p`), which runs on your Claude
subscription: no API key and no extra bill. If the command line isn't signed in, run `claude auth login` once.
Only the transcript text goes to Claude; the audio stays on this Mac.

Grounded in published work, so the feedback isn't a made-up rubric:
  - Active-Empathic Listening Scale (Bodie 2011): sensing, processing, responding, rated 1 to 7.
  - Follow-up questions (Huang, Yeomans, Brooks, Minson & Gino 2017, JPSP): the questions tied to being liked.
  - Reflections versus questions (MITI, the Motivational Interviewing Treatment Integrity code): 1 reflection
    per question is beginning proficiency, 2 is competent.
  - Monologue length and talk share (Gong's sales-call data), turn gaps (Stivers et al. 2009), cooperative
    overlap (Tannen): these numbers come from coach.md, worked out on this Mac.

Writes review.json, review.html and call.m4a (both sides mixed, for the play buttons; deleted with the rest of
the audio after 30 days).
"""
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.local/bin/claude")
# the review's own long-lived sign-in (made with `claude setup-token`, saved by you, readable only by
# your account). The command line's normal sign-in is shared with the Claude app, and whenever one refreshed it the
# other was signed out, so reviews kept failing. Nothing here prints or logs the token.
TOKEN_FILE = os.path.expanduser("~/.config/call-review/claude-token")


# Only what the review needs: no connected apps (MCP servers), no skills, run from an empty folder so no project
# notes load. With your full setup, a one-line request was ~260,000 tokens and was refused as too long.
CLAUDE_LEAN = ["--strict-mcp-config", "--disable-slash-commands"]
RUN_DIR = os.path.expanduser("~/.config/call-review/run")


def lean_dir():
    os.makedirs(RUN_DIR, exist_ok=True)
    return RUN_DIR


def claude_env():
    """The environment for `claude -p`: no app proxy settings, Homebrew on the PATH, and the review's own sign-in."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
    env["PATH"] = "/opt/homebrew/bin:/usr/bin:/bin:" + env.get("PATH", "")
    try:
        token = open(TOKEN_FILE).read().strip()
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    except OSError:
        pass
    return env
FFMPEG = "/opt/homebrew/bin/ffmpeg"

MOMENT = {"type": "object", "properties": {
    "time": {"type": "string", "description": "m:ss from the transcript"},
    "they_said": {"type": "string", "description": "a short quote of the other person, under 25 words"},
    "you_said": {"type": "string", "description": "a short quote of the user, under 25 words"}},
    "required": ["time", "they_said", "you_said"]}

SCHEMA = {"type": "object", "properties": {
    "call_title": {"type": "string", "description": "a short title for the call naming the other person if known, e.g. 'Catch-up with Sam', under 6 words"},
    "call_type": {"type": "string", "enum": ["Catch-up", "Pitching or presenting", "Being interviewed or advised",
                  "Interviewing or advising someone", "Working session", "Other"],
                  "description": "what kind of call this was, from the user's side"},
    "goal_check": {"type": "object", "properties": {
        "goal": {"type": "string", "description": "the user's stated goal word for word, or if none was given, what they most likely wanted, in under 14 words"},
        "result": {"type": "string", "enum": ["Got it", "Partly", "Didn't get it"]},
        "why": {"type": "string", "description": "one sentence, pointing at the moment that decided it"}},
        "required": ["goal", "result", "why"]},
    "verdict": {"type": "string", "description": "one plain sentence to the user, under 16 words: how they listened on this call"},
    "one_thing": {"type": "object", "properties": {
        "habit": {"type": "string", "description": "the single change that would help most, under 12 words"},
        "why": {"type": "string", "description": "one sentence, pointing at this call"},
        "practice_line": {"type": "string", "description": "words the user can literally say next time"}},
        "required": ["habit", "why", "practice_line"]},
    "listening_scale": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
        "part": {"type": "string", "enum": ["Sensing", "Processing", "Responding"]},
        "score": {"type": "integer", "minimum": 1, "maximum": 7},
        "why": {"type": "string", "description": "one sentence"},
        "moment": MOMENT}, "required": ["part", "score", "why", "moment"]}},
    "wins": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
        "title": {"type": "string", "description": "under 8 words"},
        "moment": MOMENT,
        "why_it_worked": {"type": "string", "description": "one or two sentences, naming the research idea if one applies"}},
        "required": ["title", "moment", "why_it_worked"]}},
    "fixes": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
        "title": {"type": "string", "description": "under 8 words"},
        "moment": MOMENT,
        "what_happened": {"type": "string", "description": "one or two sentences"},
        "try_this": {"type": "string", "description": "the exact words the user could have said instead"}},
        "required": ["title", "moment", "what_happened", "try_this"]}},
    "missed_follow_ups": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "object", "properties": {
        "time": {"type": "string"},
        "they_said": {"type": "string", "description": "under 20 words"},
        "ask": {"type": "string", "description": "the follow-up question, in the user's voice"}},
        "required": ["time", "they_said", "ask"]}},
    "reflections": {"type": "object", "properties": {
        "count": {"type": "integer"}, "questions": {"type": "integer"},
        "best": {"type": "object", "properties": {"time": {"type": "string"}, "quote": {"type": "string"},
                                                   "note": {"type": "string"}}, "required": ["time", "quote", "note"]}},
        "required": ["count", "questions", "best"]},
    "came_across": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["Strength", "Watch"]},
        "title": {"type": "string", "description": "under 8 words"},
        "time": {"type": "string"},
        "quote": {"type": "string", "description": "the user's words, under 20 words"},
        "note": {"type": "string", "description": "one or two sentences"}},
        "required": ["kind", "title", "time", "quote", "note"]}},
    "tighter_version": {"type": "object", "properties": {
        "topic": {"type": "string", "description": "the main thing the user explained about their work, under 8 words"},
        "time": {"type": "string"},
        "took": {"type": "string", "description": "how long the user took, e.g. '4 minutes'"},
        "say_this": {"type": "string", "description": "the same thing in about 60 to 80 words, in the user's own voice, ending by handing it back"}},
        "required": ["topic", "time", "took", "say_this"]},
    "next_call": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string",
                  "description": "a habit for the user's next call, an imperative under 14 words"}}},
    "required": ["call_title", "call_type", "goal_check", "verdict", "one_thing", "listening_scale", "wins", "fixes", "missed_follow_ups", "reflections",
                 "came_across", "tighter_version", "next_call"]}

PROMPT = """You are reviewing a recorded call to coach the user (labelled "Me") on active listening and on how
they present themselves and their ideas. They want feedback they can act on without rereading the transcript.
Write every piece of feedback to them as "you".

Rules:
- Pin every point to a real moment: its m:ss time from the transcript, a short quote of the other person, and a
  short quote of the user. Quote the transcript's words: trim, don't invent. The transcript is machine-made, so
  ignore obvious mishearings and repeated "yeah"s.
- Use these published measures and name them when they apply: the Active-Empathic Listening Scale (Bodie 2011:
  sensing = picking up what they said and meant, processing = remembering and connecting it, responding =
  showing they understood. Rate each 1 to 7), follow-up questions (Huang et al. 2017: questions that build on
  what the other person just said are the ones tied to being liked), reflections versus questions (MITI: a
  reflection gives back what they said or meant. 1 per question is beginning proficiency, 2 is competent).
- Count reflections and questions-to-the-other-person yourself, the way a MITI coder would.
- Be direct, specific and kind. No flattery, no generic advice. Every "try this" is words the user could actually say.
- Write in plain words, short sentences, no jargon, no em dashes.
- The listening scorecard below was worked out from the audio and is accurate on timing. Use its numbers.
- Judge the call by what it was for. {goal_line} Decide what kind of call it was. When the user's role was mainly
  to answer (being interviewed or advised), long answers and a high talk share are expected: don't count them
  against them, and say so. In goal_check, say whether they got what they came for.

LISTENING SCORECARD (coach.md):
{coach}

TRANSCRIPT (transcript.md):
{transcript}
"""


def ask_claude(folder):
    transcript = open(os.path.join(folder, "transcript.md")).read()
    coach_path = os.path.join(folder, "coach.md")
    coach = open(coach_path).read() if os.path.exists(coach_path) else "(none)"
    try:
        goal = (json.load(open(os.path.join(folder, "meeting.json"))).get("goal") or "").strip()
    except (OSError, ValueError):
        goal = ""
    goal_line = (f'Their goal for this call, in their words: "{goal}". Score listening in light of it.' if goal else
                 "They didn't state a goal, so infer what they most likely wanted from the call.")
    try:
        notes = (json.load(open(os.path.join(folder, "meeting.json"))).get("notes") or "").strip()
    except (OSError, ValueError):
        notes = ""
    timed = pitches(folder)
    if timed:                                   # your answers to open questions, timed live (pitch timer)
        goal_line += " Their answers to open questions, timed live: " + "; ".join(
            f'"{x["question"][:80]}" at {x["asked_at"] // 60:.0f}:{x["asked_at"] % 60:02.0f}, they answered for {x["seconds"]} seconds'
            for x in timed) + ". Use these in the tighter version and the fixes when they ran over a minute."
    if notes:                                   # your prep notes from before the call (Upcoming calls in the menu)
        goal_line += (f' Their prep notes from before the call: "{notes}". Check whether they asked the questions and '
                      "covered the points they planned, and mention any they missed in goal_check or the follow-ups.")
    run = subprocess.run([CLAUDE, "-p", "--no-session-persistence", "--model", "opus", "--output-format", "json",
                          "--tools", "", *CLAUDE_LEAN, "--json-schema", json.dumps(SCHEMA)],
                         input=PROMPT.format(coach=coach, transcript=transcript, goal_line=goal_line), capture_output=True, text=True,
                         timeout=900, env=claude_env(), cwd=lean_dir())
    try:
        out = json.loads(run.stdout)
    except ValueError:
        raise SystemExit("Claude didn't answer: " + (run.stderr or run.stdout)[-400:])
    if out.get("is_error") or not out.get("structured_output"):
        msg = str(out.get("result", ""))
        if "auth" in msg.lower() or "login" in msg.lower():
            raise SystemExit("The review's Claude sign-in has expired: run  claude setup-token  and save the new one "
                             "(see the README, 'The review's sign-in').")
        raise SystemExit("Claude couldn't finish the review: " + msg[:400])
    review = out["structured_output"]
    with open(os.path.join(folder, "review.json"), "w") as f:
        json.dump(review, f, indent=1)
    return review


def mix_audio(folder):
    """Both sides in one small file, so each moment can be played back."""
    out = os.path.join(folder, "call.m4a")
    me, them = os.path.join(folder, "me.wav"), os.path.join(folder, "them.wav")
    if os.path.exists(out) or not (os.path.exists(me) and os.path.exists(them)):
        return
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", me, "-i", them, "-filter_complex",
                    "amix=inputs=2:normalize=0", "-ac", "1", "-c:a", "aac", "-b:a", "48k", out],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------ the page

def secs(t):
    m = re.match(r"^\s*(?:(\d+):)?(\d+):(\d+)", str(t))
    if not m:
        return 0
    h, mm, ss = m.groups()
    return int(h or 0) * 3600 + int(mm) * 60 + int(ss)


def e(s):
    return html.escape(str(s or ""))


def t(s):
    """Escaped text, set the way a typesetter would (your layout rules): a sentence's first word never sits alone
    at a line end, and a paragraph never ends on a single word."""
    out = re.sub(r"(?<=\w)-(?=\w)", "\u2011", e(s))       # "follow-up" never splits at its hyphen
    words = out.split()
    if len(words) < 3:
        return " ".join(words)
    ends = re.compile(r"[.!?](?:&quot;|&#x27;|[”’)])*$")
    glue = [False] * len(words)                                # glue[i]: no break between word i and i + 1
    for i in range(1, len(words) - 1):
        if ends.search(words[i - 1]):                          # a sentence starts at word i
            glue[i] = True
    glue[len(words) - 2] = True                                # never end on a single word
    return "".join(w + ("" if i == len(words) - 1 else "&nbsp;" if glue[i] else " ") for i, w in enumerate(words))


CLIPS = {"turns": []}


def load_turns(folder):
    """Every word of the call with a time, from Whisper's own line timings on each side (me.json, them.json):
    lines of a sentence or so, so a quote's moment is found to within a second or two."""
    timeline = []
    for name, who in (("me.json", "Me"), ("them.json", "Them")):
        try:
            lines = json.load(open(os.path.join(folder, name))).get("transcription", [])
        except (OSError, ValueError):
            continue
        for x in lines:
            ws = x.get("text", "").split()
            a, b = x["offsets"]["from"] / 1000, x["offsets"]["to"] / 1000
            b = min(b, a + 0.45 * max(1, len(ws)) + 0.5)          # a line's end can run on into silence
            for i, w in enumerate(ws):
                timeline.append((who, a + (b - a) * i / max(1, len(ws)), re.sub(r"[^a-z0-9']", "", w.lower())))
    timeline.sort(key=lambda x: x[1])
    CLIPS["turns"] = timeline


def find(quote, near, who=None):
    """When a quote was said: (start, end) in seconds, closest to the given time, or None."""
    q = [w for w in (re.sub(r"[^a-z0-9']", "", x.lower()) for x in str(quote or "").split()) if w]
    tl = [x for x in CLIPS["turns"] if who is None or x[0] == who]
    if len(q) < 2 or not tl:
        return None
    best = None
    for i in range(len(tl)):
        if abs(tl[i][1] - near) > 150:
            continue
        window = [x[2] for x in tl[i:i + len(q) + 3]]
        hits = sum(1 for w in q[:6] if w in window[:8])
        if hits >= min(4, len(q)) and tl[i][2] in q[:2]:
            score = (hits, -abs(tl[i][1] - near))
            if best is None or score > best[0]:
                best = (score, i)
    if best is None:
        return None
    i = best[1]
    j = min(len(tl) - 1, i + len(q) - 1)
    return tl[i][1], tl[j][1] + 0.9


def clip(time, they=None, you=None):
    """The stretch to play: from what they said through what you said, with a little lead-in, under 45 seconds.
    If the two moments are far apart, just your words with the lead-up. Without a match: 20 seconds from the time."""
    at = secs(time)
    them_span = find(they, at, "Them") if they else None
    you_span = find(you, at, "Me") if you else None
    if you_span and them_span and 0 <= you_span[0] - them_span[0] <= 40:
        a, b = them_span[0] - 1, you_span[1] + 1
    elif you_span and them_span and 0 <= them_span[0] - you_span[0] <= 40:   # your question, then their answer
        a, b = you_span[0] - 1, them_span[1] + 1
    elif you_span:
        a, b = you_span[0] - 4, you_span[1] + 1
    elif them_span:
        a, b = them_span[0] - 1, them_span[1] + 4
    else:
        a, b = at - 2, at + 20
    a = max(0, a)
    b = min(max(b, a + 6), a + 45)
    return round(a, 1), round(b, 1)


def play_range(a, b, label):
    """A play button for an exact stretch (seconds into the call)."""
    a, b = max(0, round(a, 1)), round(b, 1)
    n = round(b - a)
    length = f"{n} sec" if n < 60 else f"{n // 60}:{n % 60:02d}"
    return (f'<button class="play" data-a="{a}" data-b="{b}" data-label="{e(label)}" title="Play ({length})">'
            f'<span class="ic">&#9654;</span> {e(label)} <span class="len">· {length}</span></button>')


def pitches(folder):
    """Your answers to open questions, from the live pitch timer (pitches.json), or []."""
    try:
        return json.load(open(os.path.join(folder, "pitches.json"))).get("answers", [])
    except (OSError, ValueError, AttributeError):
        return []


def play(time, they=None, you=None):
    a, b = clip(time, they, you)
    n = round(b - a)
    length = f"{n} sec" if n < 60 else f"{n // 60}:{n % 60:02d}"
    return (f'<button class="play" data-a="{a}" data-b="{b}" data-label="{e(time)}" '
            f'title="Play this moment ({length})"><span class="ic">&#9654;</span> {e(time)} '
            f'<span class="len">· {length}</span></button>')


def moment(m, show_them=True):
    them = f'<p class="said them"><span>They said</span>{t(m.get("they_said"))}</p>' if show_them and m.get("they_said") else ""
    return f'{them}<p class="said you"><span>You said</span>{t(m.get("you_said"))}</p>'


def grade(scores):
    """The overall grade: the average of the three Active-Empathic Listening Scale scores, as a letter.
    6 and up is an A, 5 a B, 4 a C, 3 a D; the top third of a band adds a plus, the bottom third a minus."""
    avg = sum(scores) / len(scores)
    for floor, letter in ((6, "A"), (5, "B"), (4, "C"), (3, "D")):
        if avg >= floor:
            part = min(avg, 7) - floor
            mod = "+" if part >= 0.67 and letter != "A" or (letter == "A" and avg >= 6.67) else "−" if part < 0.34 else ""
            return letter + mod, avg
    return "F", avg


def clock_s(n):
    n = int(round(n))
    return f"{n // 60}:{n % 60:02d}"


ANSWERING = ("Being interviewed or advised",)      # calls where your job was mainly to answer


def selfcheck(folder):
    """Your own ratings from the panel at the end of the call (selfcheck.json), or {}."""
    try:
        return json.load(open(os.path.join(folder, "selfcheck.json")))
    except (OSError, ValueError):
        return {}


def benchmarks(folder, call_type=None):
    """The pass/fail lines from coach.md, as small cards. On a call where your job was to answer, talk share and
    monologue length don't apply (the research behind them is about leading a conversation): None, not False."""
    try:
        text = open(os.path.join(folder, "coach.md")).read()
    except OSError:
        return []
    out = []
    for ok, name, why in re.findall(r"^- (Met|Not yet): \*\*(.+?)\.\*\* (.+)$", text, re.M):
        first = re.split(r"(?<=\.)\s", why, maxsplit=1)[0]
        if call_type in ANSWERING and ("Talk share" in name or "monologue" in name):
            out.append((None, name, first + " Your role on this call was mostly to answer, so this doesn't apply."))
        else:
            out.append((ok == "Met", name, first))
    return out


def page(folder, r):
    meta = {}
    try:
        meta = json.load(open(os.path.join(folder, "meeting.json")))
    except (OSError, ValueError):
        pass
    started = datetime.fromtimestamp(meta.get("started", os.path.getmtime(folder)))
    when = started.strftime("%A %-d %B, %-I:%M %p")
    load_turns(folder)
    has_audio = os.path.exists(os.path.join(folder, "call.m4a"))
    try:
        length = re.search(r"a (\d+)-minute call", open(os.path.join(folder, "coach.md")).read()).group(1) + "-minute call"
    except (OSError, AttributeError):
        length = ""

    me = selfcheck(folder)
    def mine(part):
        v = me.get(part.lower())
        return f'<span class="mine">You said {int(v)}</span>' if v else ""
    scale = "".join(f'''
      <div class="card scale">
        <div class="scale-top"><h3>{t(s["part"])}</h3><div class="score">{mine(s["part"])}{int(s["score"])}<small>/7</small></div></div>
        <div class="bar"><i style="width:{int(s["score"]) / 7 * 100:.0f}%"></i></div>
        <p>{t(s["why"])}</p>
        {moment(s["moment"])}
        <div class="foot">{play(s["moment"]["time"], s["moment"].get("they_said"), s["moment"].get("you_said"))}</div>
      </div>''' for s in r["listening_scale"])

    wins = "".join(f'''
      <div class="card win">
        <div class="tag good">Worked</div><h3>{t(w["title"])}</h3>
        {moment(w["moment"])}
        <p class="why">{t(w["why_it_worked"])}</p>
        <div class="foot">{play(w["moment"]["time"], w["moment"].get("they_said"), w["moment"].get("you_said"))}</div>
      </div>''' for w in r["wins"])

    fixes = "".join(f'''
      <div class="card fix">
        <div class="tag work">Try next time</div><h3>{t(f["title"])}</h3>
        {moment(f["moment"])}
        <p class="why">{t(f["what_happened"])}</p>
        <p class="try"><span>Try this</span>&ldquo;{t(f["try_this"])}&rdquo;</p>
        <div class="foot">{play(f["moment"]["time"], f["moment"].get("they_said"), f["moment"].get("you_said"))}</div>
      </div>''' for f in r["fixes"])

    follow = "".join(f'''
      <div class="card ask">
        <p class="said them"><span>They said</span>{t(q["they_said"])}</p>
        <p class="try"><span>You could have asked</span>&ldquo;{t(q["ask"])}&rdquo;</p>
        <div class="foot">{play(q["time"], q["they_said"], None)}</div>
      </div>''' for q in r["missed_follow_ups"])

    came = "".join(f'''
      <div class="card {'win' if c["kind"] == "Strength" else 'fix'}">
        <div class="tag {'good' if c["kind"] == "Strength" else 'work'}">{t(c["kind"])}</div><h3>{t(c["title"])}</h3>
        <p class="said you"><span>You said</span>{t(c["quote"])}</p>
        <p class="why">{t(c["note"])}</p>
        <div class="foot">{play(c["time"], None, c["quote"])}</div>
      </div>''' for c in r["came_across"])

    ref = r["reflections"]
    ratio = ref["count"] / max(1, ref["questions"])
    ctype = r.get("call_type")
    marks = {True: ("met", "good", "Met"), False: ("notyet", "work", "Not yet"), None: ("na", "na", "Doesn't apply")}
    bench = "".join(f'''
      <div class="card bench {marks[ok][0]}"><div class="tag {marks[ok][1]}">{marks[ok][2]}</div>
        <h3>{t(name)}</h3><p>{t(why)}</p></div>''' for ok, name, why in benchmarks(folder, ctype))
    bench += f'''
      <div class="card bench {'met' if ratio >= 1 else 'notyet'}"><div class="tag {'good' if ratio >= 1 else 'work'}">{'Met' if ratio >= 1 else 'Not yet'}</div>
        <h3>{t("Reflections for every question")}</h3><p>{t(f"{ref['count']} reflections to {ref['questions']} questions ({ratio:.1f}). MITI counts 1 per question as the starting level.")}</p></div>'''

    letter, avg = grade([int(x["score"]) for x in r["listening_scale"]])
    try:
        nums = json.load(open(os.path.join(folder, "coach.json")))
    except (OSError, ValueError):
        nums = {}
    talk, listen = nums.get("talk_secs", 0), nums.get("listen_secs", 0)
    tshare = talk / max(1, talk + listen)
    met_total = sum(1 for ok, _, _ in benchmarks(folder, ctype) if ok is not None) + 1
    met_count = sum(1 for ok, _, _ in benchmarks(folder, ctype) if ok) + (1 if ratio >= 1 else 0)
    gc = r.get("goal_check")
    stated = (meta.get("goal") or "").strip()
    goalrow = ""
    if gc or ctype:
        res = (gc or {}).get("result", "")
        cls = {"Got it": "good", "Partly": "part", "Didn't get it": "work"}.get(res, "part")
        goalrow = f'''
  <div class="goalrow">
    <div class="gcell"><span>{"Your goal" if stated else "What you likely wanted"}</span>{t(stated or (gc or {}).get("goal", ""))}</div>
    <div class="gcell res {cls}"><span>Did you get it?</span>{t(res + ". " + (gc or {}).get("why", "")) if res else ""}</div>
    <div class="gcell"><span>Kind of call</span>{t(ctype or "")}</div>
  </div>'''
    selfline = ""
    if me.get("sensing") or me.get("processing") or me.get("responding"):
        vals = [me.get(k) for k in ("sensing", "processing", "responding") if me.get(k)]
        savg = sum(vals) / len(vals)
        gap = savg - avg
        read = ("You saw yourself about the way the review did." if abs(gap) < 0.5 else
                f"You rated yourself {gap:.1f} higher than the review: worth a look at where the gap is." if gap > 0 else
                f"You rated yourself {-gap:.1f} lower than the review: you listened better than you thought.")
        note = (me.get("note") or "").strip()
        selfline = f'''
  <div class="selfrow"><div class="gcell"><span>Your own rating</span>{t(f"{savg:.1f} of 7. " + read)}</div>
    {f'<div class="gcell"><span>What you said you\'d do differently</span>&ldquo;{t(note)}&rdquo;</div>' if note else ""}</div>'''
    talkbar = (f'''
  <div class="talk">
    <div class="talk-labels"><span><b>You talked {clock_s(talk)}</b> · {tshare:.0%}</span>
      <span><b>You listened {clock_s(listen)}</b> · {1 - tshare:.0%}</span></div>
    <div class="talk-bar"><i style="width:{tshare * 100:.1f}%"></i></div>
  </div>''' if talk else "")
    answers = pitches(folder)
    pitch_html = ""
    if answers:
        under = sum(1 for x in answers if x["seconds"] <= 60)
        cards = "".join(f'''
      <div class="card {'win' if x["seconds"] <= 60 else 'fix'}">
        <div class="tag {'good' if x["seconds"] <= 60 else 'work'}">{"Under a minute" if x["seconds"] <= 60 else clock_s(x["seconds"] - 60) + " over"}</div>
        <h3>{t(f"You took {clock_s(x['seconds'])}")}</h3>
        <p class="said them"><span>They asked</span>{t(x["question"])}</p>
        <div class="foot">{play_range(x["asked_at"] - 4, min(x["answer_from"] + x["seconds"], x["asked_at"] + 90), clock_s(x["asked_at"]))}</div>
      </div>''' for x in answers)
        cols = min(len(answers), 4)
        pitch_html = f'''
  <div class="head" id="pitches"><h2>{t("Your answers to open questions")}</h2><p class="sub">{t(f"{under} of {len(answers)} under a minute, timed live by the pitch timer. The clip plays the question and up to 90 seconds of your answer.")}</p></div>
  <div class="grid" style="grid-template-columns: repeat({cols}, 1fr)">{cards}</div>'''
    habits = "".join(f'<li><b>{i + 1}</b>{t(h)}</li>' for i, h in enumerate(r["next_call"]))
    tv = r["tighter_version"]
    one = r["one_thing"]

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Call review</title>
<style>html {{ scroll-behavior: smooth; }}</style>
<style>
:root {{
  --bg: #F6F5F4; --card: #FFFFFF; --ink: #17151A; --soft: #4A4550; --line: #DEDAD9;
  --head-bg: #2B1626; --head-ink: #FFFFFF; --head-soft: #E9DDE4; --title: #2B1626;
  --good: #16653F; --goodbg: #E1F2E8; --work: #8A3C08; --workbg: #FCEBDC; --ask: #1B4F8F; --askbg: #E3EDF9;
  --try: #FFF7E8; --tryline: #E0A85A; --you: #9C2C5C; --btn: #F0EEED; --btnink: #17151A; --bar: #9C2C5C;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #121113; --card: #1D1B1F; --ink: #F5F3F4; --soft: #CFCACD; --line: #38343A;
  --head-bg: #2B1626; --head-ink: #FFFFFF; --head-soft: #E9DDE4; --title: #F5F3F4;
  --good: #8EE0B4; --goodbg: #173726; --work: #FFC089; --workbg: #3E2511; --ask: #A9CBFF; --askbg: #182C47;
  --try: #2C2416; --tryline: #E0A85A; --you: #F29BC0; --btn: #2B282E; --btnink: #F5F3F4; --bar: #F29BC0; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 17px/1.55 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif; }}
.wrap {{ padding: 40px 4vw 64px; }}
header {{ background: var(--head-bg); color: var(--head-ink); padding: 40px 4vw 36px; }}
header .when {{ font-size: 15px; letter-spacing: .06em; text-transform: uppercase; color: var(--head-soft); margin: 0 0 10px; }}
header h1 {{ font: 600 clamp(26px, 3.4vw, 52px)/1.12 "New York", Georgia, serif; margin: 0; }}
nav.sticky {{ position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 20px;
  justify-content: space-between; padding: 10px 4vw; background: var(--card); border-bottom: 1px solid var(--line);
  box-shadow: 0 2px 10px rgba(0,0,0,.06); }}
nav.sticky .links {{ display: flex; gap: 4px; overflow-x: auto; scrollbar-width: none; }}
nav.sticky .links::-webkit-scrollbar {{ display: none; }}
nav.sticky a {{ color: var(--ink); text-decoration: none; font-weight: 600; font-size: 14.5px; padding: 6px 12px;
  border-radius: 99px; white-space: nowrap; }}
nav.sticky .links a:hover {{ background: var(--btn); }}
nav.sticky .links a.on {{ background: var(--head-bg); color: #FFFFFF; }}
nav.sticky .all {{ color: var(--you); flex: none; }}
.head {{ scroll-margin-top: 72px; }}
.verdict {{ display: grid; grid-template-columns: auto 1fr; gap: 28px; align-items: center; }}
.grade {{ background: #FFFFFF; color: #2B1626; border-radius: 18px; width: 128px; height: 128px; display: flex;
  flex-direction: column; align-items: center; justify-content: center; }}
.grade .letter {{ font: 700 64px/1 "New York", Georgia, serif; }}
.grade .gl {{ font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin-top: 4px; }}
.vtext {{ display: flex; flex-direction: column; }}
.gwhy {{ margin: 10px 0 0; color: var(--head-soft); font-size: 15.5px; }}
.talk {{ margin-top: 26px; }}
.talk-labels {{ display: flex; justify-content: space-between; gap: 16px; font-size: 15.5px; color: var(--head-soft); margin-bottom: 8px; }}
.talk-labels b {{ color: var(--head-ink); }}
.talk-bar {{ height: 14px; border-radius: 99px; background: #7FB8F0; overflow: hidden; }}
.talk-bar i {{ display: block; height: 100%; background: #F29BC0; }}
.goalrow, .selfrow {{ display: grid; grid-template-columns: 2fr 2fr 1fr; gap: 14px; margin-top: 22px; }}
.selfrow {{ grid-template-columns: 1fr 1fr; }}
.gcell {{ display: flex; flex-direction: column; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.22);
  border-radius: 12px; padding: 12px 16px; }}
.gcell span {{ font-size: 12px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--head-soft); margin-bottom: 3px; }}
.gcell.res.good {{ border-color: #8EE0B4; }} .gcell.res.work {{ border-color: #FFC089; }} .gcell.res.part {{ border-color: #F2D38B; }}
.mine {{ font: 600 13px -apple-system, sans-serif; color: var(--soft); margin-right: 10px; border: 1px solid var(--line);
  border-radius: 99px; padding: 2px 9px; vertical-align: middle; }}
.tag.na {{ color: var(--soft); background: transparent; border: 1px solid var(--line); }}
.card.bench.na {{ border-top-color: var(--line); }}
.one {{ display: grid; grid-template-columns: auto 1fr 1fr; gap: 28px; align-items: center; margin-top: 28px;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.25); border-radius: 18px; padding: 22px 26px; }}
.one .label {{ font-size: 14px; text-transform: uppercase; letter-spacing: .08em; color: var(--head-soft); }}
.one .habit {{ font: 600 clamp(20px, 2vw, 30px)/1.2 "New York", Georgia, serif; }}
.one p {{ margin: 0; }}
.one .line {{ font-weight: 600; margin-top: 6px; }}
.head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 24px; flex-wrap: wrap;
  margin: 48px 0 18px; border-bottom: 2px solid var(--line); padding-bottom: 10px; }}
h2 {{ font: 600 clamp(22px, 2vw, 30px)/1.2 "New York", Georgia, serif; margin: 0; color: var(--title); }}
.sub {{ margin: 0; color: var(--soft); text-align: right; flex: 1 1 340px; }}
header .top {{ display: flex; justify-content: space-between; gap: 24px; }}
header .top a.dl {{ color: inherit; text-decoration: underline; text-underline-offset: 3px; }}
.grid {{ display: grid; gap: 18px; }}
.grid.three {{ grid-template-columns: repeat(3, 1fr); }}
.grid.four {{ grid-template-columns: repeat(4, 1fr); }}
@media (max-width: 1100px) {{ .grid.four {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 900px) {{ .grid.three {{ grid-template-columns: 1fr; }} }}
@media (max-width: 640px) {{ .grid.four {{ grid-template-columns: 1fr; }} }}
.grid > * {{ min-width: 0; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-top: 5px solid var(--line); border-radius: 14px;
  padding: 20px 22px; display: flex; flex-direction: column; gap: 12px; }}
.card.win {{ border-top-color: var(--good); }}
.card.fix {{ border-top-color: var(--work); }}
.card.ask {{ border-top-color: var(--ask); }}
.card.scale {{ border-top-color: var(--bar); }}
.card h3 {{ margin: 0; font-size: 19px; line-height: 1.3; }}
.card p {{ margin: 0; }}
.tag {{ align-self: flex-start; display: inline-block; width: fit-content; font-size: 13px; font-weight: 700;
  letter-spacing: .05em; text-transform: uppercase; padding: 3px 10px; border-radius: 99px; }}
.tag.good {{ color: var(--good); background: var(--goodbg); }}
.tag.work {{ color: var(--work); background: var(--workbg); }}
.said, .try {{ display: flex; flex-direction: column; }}
.said {{ font-size: 16px; color: var(--ink); padding-left: 12px; border-left: 3px solid var(--line); }}
.said.you {{ border-left-color: var(--you); }}
.said span, .try span {{ display: block; font-size: 12px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; color: var(--soft); margin-bottom: 2px; }}
.why {{ color: var(--ink); }}
.try {{ background: var(--try); border-left: 4px solid var(--tryline); border-radius: 10px; padding: 12px 14px;
  font-weight: 600; color: var(--ink); }}
.card.ask .try {{ background: var(--askbg); border-left-color: var(--ask); }}
.foot {{ margin-top: auto; padding-top: 4px; }}
.play {{ font: 600 14px -apple-system, sans-serif; color: var(--btnink); background: var(--btn);
  border: 1px solid var(--line); border-radius: 99px; padding: 6px 13px; cursor: pointer; }}
.play .len {{ font-weight: 500; color: var(--soft); }}
.play:hover, .play.on {{ border-color: var(--ink); }}
.noaudio .play {{ cursor: default; opacity: .6; }}
.scale-top {{ display: flex; justify-content: space-between; align-items: baseline; }}
.score {{ font: 600 34px/1 "New York", Georgia, serif; color: var(--title); }}
.score small {{ font-size: 16px; color: var(--soft); }}
.bar {{ height: 8px; background: var(--line); border-radius: 99px; overflow: hidden; }}
.bar i {{ display: block; height: 100%; background: var(--bar); border-radius: 99px; }}
.pitch {{ display: grid; grid-template-columns: 1fr 2fr; gap: 28px; border-top-color: var(--work); }}
.pitch .say {{ font: 500 clamp(19px, 1.6vw, 24px)/1.5 "New York", Georgia, serif; }}
ol.habits {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
ol.habits li {{ display: flex; flex-direction: column; background: var(--head-bg); color: var(--head-ink); border-radius: 14px;
  padding: 22px; font-size: 19px; line-height: 1.4; }}
ol.habits b {{ display: block; font: 600 30px/1 "New York", Georgia, serif; margin-bottom: 10px; color: var(--head-soft); }}
.note {{ padding-top: 0; color: var(--soft); font-size: 14.5px; }}
.note p {{ margin: 0; border-top: 1px solid var(--line); padding-top: 18px; }}
.scirow {{ display: flex; justify-content: space-between; gap: 24px; flex-wrap: wrap; margin-top: 12px; }}
.note .sci {{ color: var(--you); font-weight: 700; text-decoration: none; }}
/* the player bar: what's playing, how long is left, and the speed */
#player {{ position: fixed; left: 0; right: 0; bottom: 0; display: none; align-items: center; gap: 18px;
  padding: 12px 4vw; background: var(--head-bg); color: var(--head-ink); box-shadow: 0 -6px 24px rgba(0,0,0,.25); }}
#player.show {{ display: flex; }}
#player .what {{ font-weight: 700; white-space: nowrap; }}
#player .track {{ flex: 1; height: 6px; background: rgba(255,255,255,.25); border-radius: 99px; overflow: hidden; }}
#player .track i {{ display: block; height: 100%; width: 0; background: #FFFFFF; }}
#player .left {{ font-variant-numeric: tabular-nums; white-space: nowrap; color: var(--head-soft); }}
#player .speeds {{ display: flex; gap: 6px; }}
#player button {{ font: 600 14px -apple-system, sans-serif; color: var(--head-ink); background: transparent;
  border: 1px solid rgba(255,255,255,.4); border-radius: 99px; padding: 5px 11px; cursor: pointer; }}
#player button.sel {{ background: #FFFFFF; color: var(--head-bg); border-color: #FFFFFF; }}
body.playing {{ padding-bottom: 72px; }}
@media (max-width: 760px) {{
  .wrap, header {{ padding-left: 16px; padding-right: 16px; }}
  .one, .pitch {{ grid-template-columns: 1fr; gap: 12px; }}
  .verdict {{ grid-template-columns: 1fr; gap: 16px; }} .grade {{ width: 96px; height: 96px; }} .grade .letter {{ font-size: 48px; }}
  .talk-labels {{ flex-direction: column; gap: 2px; }}
  .goalrow, .selfrow {{ grid-template-columns: 1fr; }}
  nav.sticky {{ padding: 8px 12px; gap: 10px; }} nav.sticky .all {{ display: none; }}
  .head {{ display: block; margin-top: 36px; }} .sub {{ text-align: left; margin-top: 4px; }}
  header .top {{ display: block; }} .wrap {{ padding-top: 8px; }}
  ol.habits {{ grid-template-columns: 1fr; }}
  .grid {{ grid-template-columns: 1fr; }}
  #player {{ flex-wrap: wrap; gap: 10px; padding: 10px 16px; }} #player .track {{ flex-basis: 100%; order: 3; }}
}}
</style></head>
<body class="{'' if has_audio else 'noaudio'}">
<header id="top">
  <div class="top"><p class="when">{t("Call review · " + when)}</p><p class="when">{e(length)} · <a class="dl" href="learnings.md" download>Download learnings (.md)</a></p></div>
  <div class="verdict">
    <div class="grade"><div class="letter">{e(letter)}</div><div class="gl">Overall</div></div>
    <div class="vtext"><h1>{t(r["verdict"])}</h1>
      <p class="gwhy">{t(f"{avg:.1f} of 7 on the Active-Empathic Listening Scale (Bodie 2011), the average of the three scores below. {met_count} of {met_total} research benchmarks met.")}</p></div>
  </div>{goalrow}{selfline}{talkbar}
  <div class="one">
    <div class="label">The one thing</div>
    <div class="habit">{t(one["habit"])}</div>
    <div><p>{t(one["why"])}</p><p class="line">Say: &ldquo;{t(one["practice_line"])}&rdquo;</p></div>
  </div>
</header>
<nav class="sticky" aria-label="Sections">
  <div class="links"><a href="#top">Grade</a><a href="#listening">Listening</a><a href="#worked">Worked</a><a href="#grow">Grow</a>
    <a href="#followups">Follow-ups</a><a href="#across">Came across</a>{'<a href="#pitches">Answers</a>' if pitches(folder) else ""}<a href="#tighter">Tighter</a>
    <a href="#benchmarks">Benchmarks</a><a href="#next">Next call</a></div>
  <a class="all" href="../calls.html">All my calls &rarr;</a>
</nav>
<main class="wrap">
  <div class="head" id="listening"><h2>{t("Your listening, on the Active-Empathic Listening Scale")}</h2><p class="sub">{t("Three parts, each out of 7 (Bodie 2011). The moment behind each score is underneath it.")}</p></div>
  <div class="grid three">{scale}</div>

  <div class="head" id="worked"><h2>{t("What worked")}</h2><p class="sub">{t("Keep doing these.")}</p></div>
  <div class="grid three">{wins}</div>

  <div class="head" id="grow"><h2>{t("Where to grow")}</h2><p class="sub">{t("What happened, and the words to use next time.")}</p></div>
  <div class="grid three">{fixes}</div>

  <div class="head" id="followups"><h2>{t("Follow-ups you could have asked")}</h2><p class="sub">{t("Questions that build on what they just said are the ones tied to being liked (Huang et al. 2017).")}</p></div>
  <div class="grid four">{follow}</div>

  <div class="head" id="across"><h2>{t("How you came across")}</h2><p class="sub">{t("What made your ideas land, and what blurred them.")}</p></div>
  <div class="grid four">
      <div class="card win"><div class="tag good">Your best reflection</div><h3>&ldquo;{t(ref["best"]["quote"])}&rdquo;</h3>
        <p class="why">{t(ref["best"]["note"])}</p><div class="foot">{play(ref["best"]["time"], None, ref["best"]["quote"])}</div></div>{came}</div>

{pitch_html}
  <div class="head" id="tighter"><h2>{t("A tighter way to say it")}</h2><p class="sub">{t("The same story in about a minute, ending by handing it back.")}</p></div>
  <div class="card pitch">
    <div><div class="tag work">{t(tv["topic"])}</div><p style="margin-top:10px">{t("You took " + tv["took"] + " at the time.")}</p><div class="foot">{play(tv["time"])}</div></div>
    <p class="say">&ldquo;{t(tv["say_this"])}&rdquo;</p>
  </div>

  <div class="head" id="benchmarks"><h2>{t("The research benchmarks")}</h2><p class="sub">{t("Counted on this Mac from the audio (talk time, monologues) and by Claude (reflections).")}</p></div>
  <div class="grid four">{bench}</div>

  <div class="head" id="next"><h2>{t("For your next call")}</h2><p class="sub">{t("Three habits. Read them before you dial.")}</p></div>
  <ol class="habits">{habits}</ol>

</main>
<footer class="wrap note"><p>{t("Made on this Mac from the call's transcript and audio. The review itself is by Claude through your Claude subscription; only the transcript text was sent. Full transcript: transcript.md in this folder.")}</p>
  <div class="scirow"><a class="sci" href="../calls.html#science">How this is graded, with the studies &rarr;</a><a class="sci" href="../calls.html">All my calls &rarr;</a></div></footer>
<audio id="a" preload="metadata" src="call.m4a"></audio>
<div id="player" role="region" aria-label="Clip player">
  <span class="what">&#9654; <span id="pw">0:00</span></span>
  <div class="track"><i id="pt"></i></div>
  <span class="left" id="pl"></span>
  <div class="speeds" id="ps"><button data-s="1">1&times;</button><button data-s="1.25">1.25&times;</button><button data-s="1.5">1.5&times;</button><button data-s="2">2&times;</button></div>
  <button id="px" title="Stop">Stop</button>
</div>
<script>
(function () {{
  var a = document.getElementById("a"), bar = document.getElementById("player"), cur = null, end = 0, start = 0;
  var speed = 1;
  try {{ speed = parseFloat(localStorage.getItem("reviewSpeed")) || 1; }} catch (x) {{}}
  function fmt(s) {{ s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + ("0" + s % 60).slice(-2); }}
  function marks() {{
    document.querySelectorAll("#ps button").forEach(function (b) {{ b.classList.toggle("sel", +b.dataset.s === speed); }});
  }}
  function stop() {{
    a.pause(); bar.classList.remove("show"); document.body.classList.remove("playing");
    if (cur) {{ cur.classList.remove("on"); cur.querySelector(".ic").innerHTML = "&#9654;"; }} cur = null;
  }}
  document.querySelectorAll(".play").forEach(function (b) {{
    b.addEventListener("click", function () {{
      if (document.body.classList.contains("noaudio")) return;
      if (cur === b) {{ if (a.paused) {{ a.play(); b.querySelector(".ic").innerHTML = "&#10074;&#10074;"; }}
                        else {{ a.pause(); b.querySelector(".ic").innerHTML = "&#9654;"; }} return; }}
      if (cur) {{ cur.classList.remove("on"); cur.querySelector(".ic").innerHTML = "&#9654;"; }}
      cur = b; start = +b.dataset.a; end = +b.dataset.b;
      b.classList.add("on"); b.querySelector(".ic").innerHTML = "&#10074;&#10074;";
      document.getElementById("pw").textContent = b.dataset.label;
      bar.classList.add("show"); document.body.classList.add("playing");
      a.currentTime = start; a.playbackRate = speed; a.play().catch(function () {{}});
    }});
  }});
  a.addEventListener("timeupdate", function () {{
    if (!cur) return;
    var done = (a.currentTime - start) / (end - start);
    document.getElementById("pt").style.width = Math.min(100, Math.max(0, done * 100)) + "%";
    document.getElementById("pl").textContent = fmt((end - a.currentTime) / speed) + " left";
    if (a.currentTime >= end) stop();
  }});
  document.querySelectorAll("#ps button").forEach(function (b) {{
    b.addEventListener("click", function () {{
      speed = +b.dataset.s; a.playbackRate = speed; marks();
      try {{ localStorage.setItem("reviewSpeed", speed); }} catch (x) {{}}
    }});
  }});
  document.getElementById("px").addEventListener("click", stop);
  document.addEventListener("keydown", function (ev) {{ if (ev.key === "Escape") stop(); }});
  a.addEventListener("error", function () {{ document.body.classList.add("noaudio"); }});
  marks();
  // The sticky bar marks the section in view.
  var links = {{}}; document.querySelectorAll("nav.sticky .links a").forEach(function (l) {{ links[l.getAttribute("href").slice(1)] = l; }});
  var spots = ["top"].concat(Object.keys(links).filter(function (k) {{ return k !== "top"; }}));
  function mark() {{
    var cur = "top";
    spots.forEach(function (id) {{ var el = document.getElementById(id); if (el && el.getBoundingClientRect().top < 120) cur = id; }});
    Object.keys(links).forEach(function (k) {{ links[k].classList.toggle("on", k === cur); }});
    if (links[cur]) links[cur].scrollIntoView({{ block: "nearest", inline: "nearest" }});
  }}
  window.addEventListener("scroll", mark, {{ passive: true }}); mark();
}})();
</script>
</body></html>
'''


def write_page(folder, review):
    path = os.path.join(folder, "review.html")
    with open(path, "w") as f:
        f.write(page(folder, review))
    return path


def main(folder, page_only=False, tell=False):
    problem = os.path.join(folder, "review-problem.txt")
    try:
        review = json.load(open(os.path.join(folder, "review.json"))) if page_only else ask_claude(folder)
    except SystemExit as err:
        with open(problem, "w") as f:
            f.write(str(err) + "\n")
        raise
    mix_audio(folder)
    path = write_page(folder, review)
    if os.path.exists(problem):
        os.remove(problem)
    # The history page (calls.html) rebuilds with every review; the patterns across calls only when new.
    subprocess.run([sys.executable, os.path.join(HERE, "meeting_history.py")] + ([] if not page_only else ["--no-patterns"]),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # A fresh review leaves a marker; Hammerspoon (meetings.lua) sees it and sends the notification.
    if tell and not page_only:
        open(os.path.join(folder, "review-new"), "w").close()
    print(path)


if __name__ == "__main__":
    main(sys.argv[1], "--page" in sys.argv, "--notify" in sys.argv)
