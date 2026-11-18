"""All my calls: one private page with every reviewed call and how your listening is trending.

    .venv/bin/python meeting_history.py              rebuild calls.html in the meetings folder (settings.json)
    .venv/bin/python meeting_history.py --patterns   also ask Claude what keeps coming up across calls

Runs after every call review. The page lives only on this Mac (a file in the Meetings folder, never published).
Each call's numbers come from its coach.json (worked out from the audio) and review.json (Claude's review).
The patterns across calls come from Claude through the Claude Code command line on your subscription, only
when the set of reviews has changed; they're kept in patterns.json.
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = json.load(open(os.path.join(HERE, "settings.json")))
MEET = os.path.expanduser(SETTINGS.get("meetings_folder", "~/Earshot Meetings"))
sys.path.insert(0, HERE)
from meeting_review import grade, t, e, clock_s, CLAUDE, selfcheck, pitches, claude_env, CLAUDE_LEAN, lean_dir   # noqa: E402

PATTERN_SCHEMA = {"type": "object", "properties": {
    "headline": {"type": "string", "description": "one plain sentence to the user on how their listening is trending, under 18 words"},
    "keeps_coming_up": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "object", "properties": {
        "title": {"type": "string", "description": "under 8 words"},
        "detail": {"type": "string", "description": "one or two sentences naming the calls it showed up in"}},
        "required": ["title", "detail"]}},
    "getting_better": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "detail": {"type": "string"}}, "required": ["title", "detail"]}},
    "focus_next": {"type": "string", "description": "the one habit to practise on the next call, under 14 words"}},
    "required": ["headline", "keeps_coming_up", "getting_better", "focus_next"]}


def calls():
    out = []
    for name in sorted(os.listdir(MEET)):
        folder = os.path.join(MEET, name)
        rj, cj = os.path.join(folder, "review.json"), os.path.join(folder, "coach.json")
        if not (re.match(r"^\d{4}-\d\d-\d\d \d{4}", name) and os.path.exists(rj)):
            continue
        r = json.load(open(rj))
        c = json.load(open(cj)) if os.path.exists(cj) else {}
        scores = [int(x["score"]) for x in r["listening_scale"]]
        letter, avg = grade(scores)
        when = datetime.strptime(name[:15], "%Y-%m-%d %H%M")
        talk, listen = c.get("talk_secs", 0), c.get("listen_secs", 0)
        ref = r.get("reflections", {})
        me = selfcheck(folder)
        mine = [me.get(k) for k in ("sensing", "processing", "responding") if me.get(k)]
        out.append({"name": name, "when": when, "r": r, "c": c, "letter": letter, "avg": avg,
                    "title": r.get("call_title") or when.strftime("Call, %-d %b"),
                    "share": talk / max(1, talk + listen) if talk else None, "talk": talk, "listen": listen,
                    "fu10": c.get("follow_ups", 0) / max(1, c.get("length_min", 1)) * 10,
                    "longest": c.get("longest_secs", 0) / 60,
                    "rq": ref.get("count", 0) / max(1, ref.get("questions", 1)),
                    "minutes": c.get("length_min", 0), "type": r.get("call_type"),
                    "self": sum(mine) / len(mine) if mine else None, "answers": pitches(folder), "goal": (r.get("goal_check") or {})})
    return out


def patterns(items, force=False):
    """What keeps coming up across calls, from Claude. Cached until a review changes."""
    if len(items) < 2:
        return None
    path = os.path.join(MEET, "patterns.json")
    key = hashlib.sha1("".join(i["name"] + str(os.path.getmtime(os.path.join(MEET, i["name"], "review.json")))
                               for i in items).encode()).hexdigest()
    try:
        cached = json.load(open(path))
        if cached.get("key") == key and not force:
            return cached["patterns"]
    except (OSError, ValueError):
        cached = None
    brief = []
    for i in items:
        r = i["r"]
        brief.append({"call": i["title"], "date": i["when"].strftime("%-d %b"), "grade": i["letter"],
                      "listening_scale": {x["part"]: x["score"] for x in r["listening_scale"]},
                      "talk_share": round(i["share"] or 0, 2), "longest_monologue_min": round(i["longest"], 1),
                      "verdict": r["verdict"], "one_thing": r["one_thing"]["habit"],
                      "wins": [w["title"] for w in r["wins"]], "fixes": [f["title"] + ": " + f["what_happened"] for f in r["fixes"]],
                      "came_across": [c["kind"] + ": " + c["title"] for c in r["came_across"]]})
    prompt = ("These are reviews of the user's recorded calls, oldest first. Find what keeps coming up in how they "
              "listen and present themselves, what is getting better, and the one habit to practise next. Write to them "
              "as \"you\". Name the "
              "calls each point comes from. Plain words, short sentences, no em dashes, no flattery.\n\n"
              + json.dumps(brief, indent=1))
    env = claude_env()
    try:
        run = subprocess.run([CLAUDE, "-p", "--no-session-persistence", "--model", "opus", "--output-format", "json",
                              "--tools", "", *CLAUDE_LEAN, "--json-schema", json.dumps(PATTERN_SCHEMA)],
                             input=prompt, capture_output=True, text=True, timeout=600, env=env, cwd=lean_dir())
        out = json.loads(run.stdout)
        p = out.get("structured_output")
    except (ValueError, subprocess.SubprocessError, OSError):
        p = None
    if not p:
        return cached["patterns"] if cached else None
    with open(path, "w") as f:
        json.dump({"key": key, "patterns": p}, f, indent=1)
    return p


def chart(items, value, lo, hi, fmt, band=None, line=None, label=None, better="up", second=None):
    """A small line chart as inline SVG: one point per call, oldest on the left."""
    W, H, L, R, T, B = 340, 210, 44, 30, 26, 30   # room on the right, so the last date isn't cut off
    pts = [(i, value(c)) for i, c in enumerate(items) if value(c) is not None]
    n = max(1, len(items) - 1)
    x = lambda i: L + 14 + (W - L - R - 28) * (i / n if len(items) > 1 else 0.5)   # inset, so labels clear the axis
    y = lambda v: T + (H - T - B) * (1 - (min(max(v, lo), hi) - lo) / (hi - lo))
    g = []
    if band:
        g.append(f'<rect x="{L}" y="{y(band[1]):.1f}" width="{W - L - R}" height="{y(band[0]) - y(band[1]):.1f}" class="band"/>')
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                 f'<text x="{L - 8}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{e(fmt(v))}</text>')
    if line is not None:
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{y(line):.1f}" y2="{y(line):.1f}" class="target"/>')
    if len(pts) > 1:
        g.append('<polyline class="ln" points="' + " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts) + '"/>')
    for i, v in pts:
        tip = f"{items[i]['when'].strftime('%-d %b')}: {fmt(v)}"
        g.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="6" class="pt"><title>{e(tip)}</title></circle>')
        lab = label(items[i]) if label else fmt(v)
        above = y(v) - 12
        if line is not None and abs(above - 4 - y(line)) < 9:      # the label would sit on the target line
            above = y(v) + 22
        g.append(f'<text x="{x(i):.1f}" y="{above:.1f}" class="pl" text-anchor="middle">{e(lab)}</text>')
    if second:
        sp = [(i, second(c)) for i, c in enumerate(items) if second(c) is not None]
        if len(sp) > 1:
            g.append('<polyline class="ln2" points="' + " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in sp) + '"/>')
        for i, v in sp:
            g.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="5" class="pt2"><title>{e("Your own rating: " + fmt(v))}</title></circle>')
    for i, c in enumerate(items):
        g.append(f'<text x="{x(i):.1f}" y="{H - 10}" class="ax" text-anchor="middle">{e(c["when"].strftime("%-d %b"))}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img">{"".join(g)}</svg>'



# ------------------------------------------------------------------ the science tab
# What each measure is, where it comes from, how this tool measures it, and how strong the evidence is.
MEASURES = [
    {"name": "Overall grade: the Active-Empathic Listening Scale", "kind": "Validated rating scale", "used": "Grade, review",
     "what": "Three parts of listening: sensing (picking up what someone said and meant), processing (remembering "
             "and connecting it) and responding (showing them you understood).",
     "found": "Bodie built and validated the scale across several studies, as a self-report and as a rating by the "
              "other person or an observer. It is one of the most used measures of listening in communication research.",
     "how": "Claude reads the transcript like a trained observer and scores each part 1 to 7, quoting the moment behind "
            "each score. The grade is the average as a letter: 6 A, 5 B, 4 C, 3 D.",
     "bar": "No pass mark in the research; higher is better. The letter bands are this tool's.",
     "links": [("Bodie 2011, Communication Quarterly", "https://doi.org/10.1080/01463373.2011.583495"),
               ("Drollinger, Comer & Warrington 2006, the original sales version", "https://doi.org/10.1002/mar.20105")]},
    {"name": "Follow-up questions", "kind": "Peer-reviewed study", "used": "Scorecard, review",
     "what": "Questions that build on what the other person just said, rather than changing the subject.",
     "found": "Across live chats and speed dates, people who asked more questions, especially follow-ups, were liked "
              "more by the person they were talking to. Outside observers didn't show the same effect, and a later "
              "re-analysis questioned the speed-dating part.",
     "how": "The scorecard counts your questions to the other person and marks a follow-up when it shares key words "
            "with their last 80 or so words. Claude also suggests the follow-ups you could have asked.",
     "bar": "Two per 10 minutes (this tool's bar; the study says more is better).",
     "links": [("Huang, Yeomans, Brooks, Minson & Gino 2017, JPSP", "https://doi.org/10.1037/pspi0000097"),
               ("Open copy at Harvard", "https://dash.harvard.edu/handle/1/35647952"),
               ("Plain-English summary, APS", "https://psychologicalscience.org/news/minds-business/asking-questions-increases-likability.html")]},
    {"name": "Reflections for every question", "kind": "Clinical coding manual", "used": "Review",
     "what": "A reflection gives back what the other person said or meant, in your words, before you add your own.",
     "found": "MITI is the coding system used to train and check counsellors in motivational interviewing. It counts "
              "reflections against questions: talk that reflects people back keeps them talking and feeling heard.",
     "how": "Claude counts reflections and questions the way a MITI coder would and quotes your best one. (Matching "
            "words on this Mac couldn't recognise a reflection said in new words, so that part was dropped.)",
     "bar": "1 reflection per question is beginning proficiency, 2 is competent (thresholds from MITI versions used in trials).",
     "links": [("MITI 4.2 coding manual (CASAA, University of New Mexico)", "https://casaa.unm.edu/assets/docs/miti4_2.pdf"),
               ("Thresholds used in a primary-care trial, BMC", "https://bmcfampract.biomedcentral.com/articles/10.1186/s12875-018-0742-5/tables/4")]},
    {"name": "Talk share", "kind": "Industry data", "used": "Scorecard, header bar, trends",
     "what": "How much of the talking was you, against how much you listened.",
     "found": "Gong analysed hundreds of thousands of recorded sales calls. Its early research put winning calls at "
              "about 43% seller talk; its 2025 refresh found winning calls nearer 57%, and lost calls higher still.",
     "how": "Measured from the sound itself: your microphone and the call audio are separate tracks on one clock, so "
            "this Mac knows exactly who is talking at every moment.",
     "bar": "Between 43% and 57%. Industry data from sales calls, not peer reviewed; a friendly catch-up is different.",
     "links": [("Gong: the talk-to-listen ratio", "https://www.gong.io/blog/talk-to-listen-conversion-ratio")]},
    {"name": "Longest monologue", "kind": "Industry data", "used": "Scorecard, trends",
     "what": "Your longest stretch of talking without the other person taking the floor (their yeahs don't count).",
     "found": "In Gong's call data, long seller monologues go with lost deals; it advises keeping them under two and a half minutes.",
     "how": "From the sound of each track: your talk joined across their short yeahs, ending when they actually speak.",
     "bar": "Under 2.5 minutes. Industry data, not peer reviewed.",
     "links": [("Gong help: call stats and monologues", "https://help.gong.io/docs/understand-your-team-s-call-stats")]},
    {"name": "Pause before you answer", "kind": "Peer-reviewed study", "used": "Scorecard (context, no pass or fail)",
     "what": "The gap between them finishing and you starting.",
     "found": "Across ten languages, people take turns with a gap of about 0.2 seconds on average, with only small "
              "differences between cultures.",
     "how": "From the sound of each track: each time the floor passes from them to you.",
     "bar": "No pass or fail. Around 0.2 seconds is the human norm; starting before they finish shows up as overlap.",
     "links": [("Stivers et al. 2009, PNAS", "https://doi.org/10.1073/pnas.0903616106"),
               ("Summary, Scientific American", "https://www.scientificamerican.com/article/universal-social-rules-underlie-languages/")]},
    {"name": "Talking over vs talking together", "kind": "Linguistics research", "used": "Scorecard (context)",
     "what": "Not every overlap is an interruption. Talking along with someone to show enthusiasm is cooperative; it "
             "only takes the floor when they stop.",
     "found": "Tannen named this cooperative overlap in your study of friends talking over dinner. Whether an overlap "
              "feels rude depends on the relationship and on each person's style.",
     "how": "From the sound: when you start while they're talking, it counts as taking the floor only if they go quiet "
            "in the next two seconds.",
     "bar": "No pass or fail. The scorecard lists the times you took the floor.",
     "links": [("Tannen 1984, Conversational Style (Oxford University Press)", "https://global.oup.com/academic/product/conversational-style-9780195221817"),
               ("Li 2001, cooperative and intrusive interruptions", "https://www.interruptions.net/literature/Li-JLSP01.pdf")]},
]

CONSIDERED = [
    ("ALOS-global, an observer scale for doctors' listening (validated on 524 consultations)",
     "https://sites.google.com/site/empathytraininglitreview/measurements/alos-global",
     "Built for medical consultations, so not used here."),
]

PIPELINE = [
    ("Record", "Your mic and the call audio on one clock (meetcap, Apple's ScreenCaptureKit).", "This Mac"),
    ("Transcribe", "Whisper large-v3-turbo through whisper.cpp, with the Silero filter for silence and your word list.", "This Mac"),
    ("Measure", "Talk time, monologues, overlaps and pauses from the sound; questions and follow-ups from the words.", "This Mac"),
    ("Review", "Claude reads the transcript and the scorecard and rates you on the published measures, quoting moments.", "Claude, your subscription"),
    ("Show", "The review page with clips, and this history page. Both stay in your Meetings folder.", "This Mac"),
]


def science_html():
    steps = "".join(f'''
      <div class="card step"><div class="num">{i + 1}</div><h3>{t(n)}</h3><p>{t(d)}</p>
        <p class="where">{e(w)}</p></div>''' for i, (n, d, w) in enumerate(PIPELINE))
    cards = []
    for k, m in enumerate(MEASURES):
        links = "".join(f'<a href="{html.escape(u)}" target="_blank" rel="noopener">{e(n)} &#8599;</a>' for n, u in m["links"])
        cards.append(f'''
      <div class="card measure{' wide' if k == 0 else ''}"><div class="tags"><span class="tag ev">{e(m["kind"])}</span><span class="tag use">{e(m["used"])}</span></div>
        <h3>{t(m["name"])}</h3>
        <div class="cols"><div class="col">
        <p class="lab"><span>What it is</span>{t(m["what"])}</p>
        <p class="lab"><span>What the research found</span>{t(m["found"])}</p></div><div class="col">
        <p class="lab"><span>How this tool measures it</span>{t(m["how"])}</p>
        <p class="lab bar2"><span>The bar</span>{t(m["bar"])}</p></div></div>
        <div class="links">{links}</div></div>''')
    considered = "".join(f'<li><a href="{html.escape(u)}" target="_blank" rel="noopener">{e(n)} &#8599;</a> {e(why)}</li>'
                         for n, u, why in CONSIDERED)
    return f'''
  <div class="head"><h2>{t("How the machine works")}</h2><p class="sub">{t("Five steps after every call. Only the transcript text ever leaves this Mac.")}</p></div>
  <div class="grid pipe">{steps}</div>
  <div class="head"><h2>{t("The measures, and the research behind them")}</h2><p class="sub">{t("Each card says how strong the evidence is. Industry data is useful, but it isn't peer reviewed.")}</p></div>
  <div class="grid measures">{"".join(cards)}</div>
  <div class="head"><h2>{t("Looked at, not used")}</h2><p class="sub">{t("Checked during the research and left out, with the reason.")}</p></div>
  <ul class="considered">{considered}</ul>'''


def page(items, pats):
    latest = items[-1] if items else None
    first = items[0] if items else None
    if latest and first and latest is not first:
        d = latest["avg"] - first["avg"]
        trend = (f"Up {d:.1f} on the listening scale since your first reviewed call." if d > 0.15 else
                 f"Down {-d:.1f} on the listening scale since your first reviewed call." if d < -0.15 else
                 "Holding steady on the listening scale since your first reviewed call.")
    else:
        trend = "Your first reviewed call. The trend starts with the next one."

    charts = [
        ("Overall listening", "Listening-scale average, out of 7; the letter is the grade. The dashed line is your own rating.",
         chart(items, lambda c: c["avg"], 1, 7, lambda v: f"{v:.1f}", label=lambda c: c["letter"], second=lambda c: c["self"])),
        ("Talk share", "Share of the talking that was you. The shaded band is 43% to 57%.",
         chart(items, lambda c: c["share"] * 100 if c["share"] is not None else None, 0, 100,
               lambda v: f"{v:.0f}%", band=(43, 57))),
        ("Follow-up questions", "Per 10 minutes, building on what they'd just said. The line is 2.",
         chart(items, lambda c: c["fu10"], 0, 4, lambda v: f"{v:.1f}", line=2)),
        ("Longest monologue", "Minutes. The line is 2.5, where people start to drift.",
         chart(items, lambda c: c["longest"], 0, 6, lambda v: f"{v:.1f}", line=2.5)),
    ]
    chart_html = "".join(f'''
      <div class="card chart"><h3>{t(h)}</h3><p class="note2">{t(n)}</p>{svg}</div>''' for h, n, svg in charts)

    pat_html = ""
    if pats:
        keep = "".join(f'<div class="card fix"><div class="tag work">Keeps coming up</div><h3>{t(p["title"])}</h3>'
                       f'<p>{t(p["detail"])}</p></div>' for p in pats["keeps_coming_up"])
        good = "".join(f'<div class="card win"><div class="tag good">Getting better</div><h3>{t(p["title"])}</h3>'
                       f'<p>{t(p["detail"])}</p></div>' for p in pats["getting_better"])
        cols = len(pats["keeps_coming_up"]) + len(pats["getting_better"])
        pat_html = f'''
  <div class="head"><h2>{t("Across your calls")}</h2><p class="sub">{t(pats["headline"])}</p></div>
  <div class="grid flow">{keep}{good}</div>
  <div class="focus"><span>Practise on your next call</span>{t(pats["focus_next"])}</div>'''

    rows = []
    for c in reversed(items):
        r = c["r"]
        ans = c["answers"]
        pitchline = (f"Open-question answers: {sum(1 for x in ans if x['seconds'] <= 60)} of {len(ans)} under a minute."
                     if ans else "")
        line = f"You rated yourself {c['self']:.1f}; the review gave {c['avg']:.1f}." if c["self"] else ""
        selfr = (f'<p class="selfr">{t(line)}</p>' if line else "") + (f'<p class="selfr">{t(pitchline)}</p>' if pitchline else "")
        bar = (f'<div class="mini"><i style="width:{c["share"] * 100:.0f}%"></i></div>'
               f'<p class="tl">{t(f"Talked {clock_s(c["talk"])} · listened {clock_s(c["listen"])}")}</p>') if c["share"] is not None else ""
        rows.append(f'''
    <a class="row" href="{html.escape(c["name"])}/review.html">
      <div class="g">{e(c["letter"])}</div>
      <div class="meta"><p class="date">{t(c["when"].strftime("%a %-d %b, %-I:%M %p") + f" · {c['minutes']:.0f} min" + ((" · " + c["type"]) if c["type"] else ""))}</p>
        <h3>{t(c["title"])}</h3>{bar}</div>
      <div class="v"><p>{t(r["verdict"])}</p>{selfr}<p class="one"><span>The one thing</span>{t(r["one_thing"]["habit"])}</p></div>
      <div class="open">Open review &rarr;</div>
    </a>''')

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>All my calls</title>
<style>
:root {{
  --bg: #F6F5F4; --card: #FFFFFF; --ink: #17151A; --soft: #4A4550; --line: #DEDAD9; --head-bg: #2B1626;
  --head-ink: #FFFFFF; --head-soft: #E9DDE4; --title: #2B1626; --good: #16653F; --goodbg: #E1F2E8; --work: #8A3C08;
  --workbg: #FCEBDC; --accent: #9C2C5C; --band: rgba(22,101,63,.12); --hover: #FBF9F8;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #121113; --card: #1D1B1F; --ink: #F5F3F4; --soft: #CFCACD; --line: #38343A; --title: #F5F3F4;
  --good: #8EE0B4; --goodbg: #173726; --work: #FFC089; --workbg: #3E2511; --accent: #F29BC0;
  --band: rgba(142,224,180,.14); --hover: #252228; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 17px/1.55 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif; }}
header {{ background: var(--head-bg); color: var(--head-ink); padding: 40px 4vw 36px; }}
header .top {{ display: flex; justify-content: space-between; gap: 24px; color: var(--head-soft); font-size: 15px;
  letter-spacing: .06em; text-transform: uppercase; }}
header .top p {{ margin: 0 0 10px; }}
header .top a.dl {{ color: inherit; text-decoration: underline; text-underline-offset: 3px; }}
.hero {{ display: grid; grid-template-columns: auto 1fr; gap: 28px; align-items: center; }}
.big {{ background: #FFFFFF; color: #2B1626; border-radius: 18px; width: 128px; height: 128px; display: flex;
  flex-direction: column; align-items: center; justify-content: center; }}
.big b {{ font: 700 64px/1 "New York", Georgia, serif; }}
.big span {{ font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin-top: 4px; }}
.htext {{ display: flex; flex-direction: column; }}
h1 {{ font: 600 clamp(28px, 3.6vw, 54px)/1.1 "New York", Georgia, serif; margin: 0; }}
.htext p {{ margin: 10px 0 0; color: var(--head-soft); }}
.wrap {{ padding: 8px 4vw 64px; }}
.head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 24px; flex-wrap: wrap;
  margin: 44px 0 18px; border-bottom: 2px solid var(--line); padding-bottom: 10px; }}
h2 {{ font: 600 clamp(22px, 2vw, 30px)/1.2 "New York", Georgia, serif; margin: 0; color: var(--title); }}
.sub {{ margin: 0; color: var(--soft); text-align: right; flex: 1 1 340px; }}
.grid {{ display: grid; gap: 18px; }}
.charts {{ grid-template-columns: repeat(4, 1fr); }}
.grid > * {{ min-width: 0; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-top: 5px solid var(--line); border-radius: 14px;
  padding: 20px 22px; display: flex; flex-direction: column; gap: 10px; }}
.card.win {{ border-top-color: var(--good); }} .card.fix {{ border-top-color: var(--work); }}
.card.chart {{ border-top-color: var(--accent); }}
.card h3 {{ margin: 0; font-size: 19px; line-height: 1.3; }}
.card p {{ margin: 0; }}
.note2 {{ color: var(--soft); font-size: 15px; }}
.tag {{ display: inline-block; width: fit-content; font-size: 13px; font-weight: 700; letter-spacing: .05em;
  text-transform: uppercase; padding: 3px 10px; border-radius: 99px; }}
.tag.good {{ color: var(--good); background: var(--goodbg); }} .tag.work {{ color: var(--work); background: var(--workbg); }}
.focus {{ display: flex; flex-direction: column; margin-top: 18px; background: var(--head-bg); color: var(--head-ink);
  border-radius: 14px; padding: 18px 22px; font: 600 clamp(19px, 1.6vw, 24px)/1.35 "New York", Georgia, serif; }}
.focus span {{ font: 700 12px -apple-system, sans-serif; letter-spacing: .08em; text-transform: uppercase;
  color: var(--head-soft); margin-bottom: 4px; }}
svg {{ width: 100%; height: auto; display: block; margin-top: auto; }}
svg .grid {{ stroke: var(--line); stroke-width: 1; }}
svg .ax {{ fill: var(--soft); font: 12px -apple-system, sans-serif; }}
svg .pl {{ fill: var(--ink); font: 700 13px -apple-system, sans-serif; paint-order: stroke; stroke: var(--card); stroke-width: 4px; stroke-linejoin: round; }}
svg .ln {{ fill: none; stroke: var(--accent); stroke-width: 3; }}
svg .pt {{ fill: var(--accent); stroke: var(--card); stroke-width: 2; }}
svg .band {{ fill: var(--band); }}
svg .ln2 {{ fill: none; stroke: var(--soft); stroke-width: 2; stroke-dasharray: 5 4; }}
svg .pt2 {{ fill: var(--card); stroke: var(--soft); stroke-width: 2; }}
svg .target {{ stroke: var(--good); stroke-width: 2; stroke-dasharray: 6 5; }}
.tabs {{ position: sticky; top: 0; z-index: 20; display: flex; gap: 8px; padding: 12px 4vw; background: var(--head-bg);
  border-top: 1px solid rgba(255,255,255,.15); box-shadow: 0 2px 12px rgba(0,0,0,.18); }}
.tabs a {{ color: var(--head-ink); text-decoration: none; font-weight: 700; padding: 8px 18px; border-radius: 99px;
  border: 1px solid rgba(255,255,255,.35); }}
.tabnote {{ margin-left: auto; align-self: center; color: var(--head-soft); font-size: 14px; }}
.tabs a.on {{ background: #FFFFFF; color: #2B1626; border-color: #FFFFFF; }}
.pipe {{ grid-template-columns: repeat(5, 1fr); }}
.grid.flow {{ display: flex; flex-wrap: wrap; }}
.grid.flow > .card {{ flex: 1 1 300px; }}
.step .num {{ font: 700 30px/1 "New York", Georgia, serif; color: var(--accent); }}
.step .where {{ margin-top: auto !important; font-size: 13px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--soft); }}
.measures {{ grid-template-columns: repeat(3, 1fr); }}
.measure .cols, .measure .col {{ display: flex; flex-direction: column; gap: 10px; }}
.measure.wide {{ grid-column: 1 / -1; }}
.measure.wide .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }}
.measure.wide .tags {{ justify-content: space-between; }}
@media (max-width: 1100px) {{ .measures {{ grid-template-columns: repeat(2, 1fr); }} }}
.card.measure {{ border-top-color: var(--accent); }}
.tags {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.tag.ev {{ color: var(--good); background: var(--goodbg); }}
.tag.use {{ color: var(--soft); background: transparent; border: 1px solid var(--line); }}
.lab {{ display: flex; flex-direction: column; }}
.lab span {{ font-size: 12px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--soft); margin-bottom: 2px; }}
.bar2 {{ background: var(--goodbg); border-radius: 10px; padding: 10px 12px; }}
.links {{ display: flex; flex-direction: column; gap: 6px; margin-top: auto; padding-top: 6px; border-top: 1px solid var(--line); }}
.links a, .considered a {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
.links a:hover, .considered a:hover {{ text-decoration: underline; }}
.considered {{ margin: 0; padding: 0 0 0 20px; }}
.considered li {{ margin-bottom: 6px; }}
@media (max-width: 1000px) {{ .pipe {{ grid-template-columns: 1fr; }} }}
.rows {{ display: flex; flex-direction: column; gap: 12px; }}
.row {{ display: grid; grid-template-columns: 76px minmax(220px, 1fr) 2fr auto; gap: 24px; align-items: center;
  background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px 22px; color: inherit;
  text-decoration: none; }}
.row:hover {{ background: var(--hover); border-color: var(--ink); }}
.row .g {{ font: 700 40px/1 "New York", Georgia, serif; color: var(--title); text-align: center; }}
.row h3 {{ margin: 2px 0 8px; font-size: 19px; }}
.row p {{ margin: 0; }}
.meta {{ display: flex; flex-direction: column; }}
.date {{ font-size: 14px; color: var(--soft); }}
.mini {{ height: 8px; border-radius: 99px; background: #7FB8F0; overflow: hidden; }}
.mini i {{ display: block; height: 100%; background: #E57BA6; }}
.tl {{ font-size: 14px; color: var(--soft); margin-top: 4px !important; }}
.v {{ display: flex; flex-direction: column; gap: 8px; }}
.one {{ display: flex; flex-direction: column; font-weight: 600; }}
.one span {{ font-size: 12px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--soft); }}
.selfr {{ color: var(--soft); font-size: 15px; }}
.open {{ font-weight: 700; color: var(--accent); white-space: nowrap; }}
footer {{ padding: 0 4vw 48px; color: var(--soft); font-size: 14.5px; }}
footer p {{ margin: 0; border-top: 1px solid var(--line); padding-top: 18px; }}
@media (max-width: 1200px) {{ .charts {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 900px) {{ .row {{ grid-template-columns: 64px 1fr; }} .row .v, .row .open {{ grid-column: 1 / -1; }} }}
@media (max-width: 760px) {{
  header, .wrap, footer {{ padding-left: 16px; padding-right: 16px; }}
  .hero {{ grid-template-columns: 1fr; gap: 16px; }} .big {{ width: 96px; height: 96px; }} .big b {{ font-size: 48px; }}
  header .top {{ display: block; }} .head {{ display: block; }} .tabnote {{ display: none; }}
  .tabs {{ padding: 10px 16px; }} .sub {{ text-align: left; margin-top: 4px; }}
  .charts, .grid {{ grid-template-columns: 1fr !important; }}
  .measures {{ grid-template-columns: 1fr; }} .measure.wide .cols {{ grid-template-columns: 1fr; }}
}}
</style></head>
<body>
<header>
  <div class="top"><p>All my calls · private, on this Mac</p><p>{len(items)} reviewed · <a class="dl" href="Learnings.md" download>Download my learnings (.md)</a></p></div>
  <div class="hero">
    <div class="big"><b>{e(latest["letter"] if latest else "–")}</b><span>Latest</span></div>
    <div class="htext"><h1>{t(pats["headline"] if pats else "How you listen, call by call")}</h1>
      <p>{t(trend)}</p></div>
  </div>
</header>
<nav class="tabs"><a href="#calls" data-tab="calls">My calls</a><a href="#science" data-tab="science">The science</a>
  <span class="tabnote">{e("Rebuilds after every call review · last " + datetime.now().strftime("%-d %b, %-I:%M %p"))}</span></nav>
<main class="wrap tab" id="tab-science" hidden>{science_html()}
</main>
<main class="wrap tab" id="tab-calls">
  {pat_html}
  <div class="head"><h2>{t("Trends")}</h2><p class="sub">{t("One point per call, oldest on the left. Hover a point for its date.")}</p></div>
  <div class="grid charts">{chart_html}</div>
  <div class="head"><h2>{t("Every call")}</h2><p class="sub">{t("Newest first. Click a call to open its full review, with the clips.")}</p></div>
  <div class="rows">{"".join(rows)}</div>
</main>
<footer><p>{t("This page lives only on this Mac, in your Meetings folder. It rebuilds itself after every call review. Grades come from the Active-Empathic Listening Scale (Bodie 2011); talk time and monologues from the audio.")}</p></footer>
<script>
(function () {{
  function show() {{
    var want = location.hash === "#science" ? "science" : "calls";
    document.querySelectorAll(".tab").forEach(function (m) {{ m.hidden = m.id !== "tab-" + want; }});
    document.querySelectorAll(".tabs a").forEach(function (a) {{ a.classList.toggle("on", a.dataset.tab === want); }});
  }}
  window.addEventListener("hashchange", function () {{ show(); window.scrollTo(0, 0); }}); show();
}})();
</script>
</body></html>
'''


def main(force_patterns=False, want_patterns=True):
    items = calls()
    pats = patterns(items, force_patterns) if want_patterns else None
    if pats is None and want_patterns is False:
        try:
            pats = json.load(open(os.path.join(MEET, "patterns.json")))["patterns"]
        except (OSError, ValueError, KeyError):
            pats = None
    path = os.path.join(MEET, "calls.html")
    with open(path, "w") as f:
        f.write(page(items, pats))
    # The same reviews as markdown: each call's learnings.md and Learnings.md in the meetings folder.
    try:
        import meeting_learnings
        meeting_learnings.main()
    except Exception as err:                                         # the page matters more; say why and carry on
        print("learnings not rebuilt:", err, file=sys.stderr)
    print(path)


if __name__ == "__main__":
    main("--patterns" in sys.argv, "--no-patterns" not in sys.argv)
