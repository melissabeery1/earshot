"""Learnings: the call reviews as plain markdown, to download, reread, or hand to Claude.

    .venv/bin/python meeting_learnings.py        rewrite every call's learnings.md and Learnings.md

Each reviewed call gets learnings.md in its folder: the one habit, what worked, what to change with the words
to try, the follow-ups that were missed, and the numbers. Learnings.md in the meetings folder pulls them together: the focus
right now, what keeps coming up, what's getting better, the trend call by call, and a playbook of lines.

Nothing new is asked of Claude here. It's all rebuilt from review.json, coach.json and patterns.json, so it's
instant and runs after every review (meeting_history.py calls it).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from meeting_history import calls, MEET   # noqa: E402

OVERALL = os.path.join(MEET, "Learnings.md")


def mins(secs):
    secs = int(secs or 0)
    return f"{secs // 60}:{secs % 60:02d}"


def q(s):
    return (s or "").replace("\n", " ").strip()


def call_md(c):
    r, k = c["r"], c["c"]
    when = c["when"].strftime("%a %-d %b %Y, %-I:%M %p")
    out = [f"# {c['title']}", "", f"{when} · {r.get('call_type', 'Call')} · grade {c['letter']}", ""]
    g = c["goal"]
    if g.get("goal"):
        out += [f"**Goal:** {q(g['goal'])}  ", f"**Result:** {g.get('result', '')}. {q(g.get('why'))}", ""]
    out += [f"> {q(r.get('verdict'))}", ""]

    one = r.get("one_thing") or {}
    if one:
        out += ["## The one thing to work on", "", f"**{q(one.get('habit'))}**", "", q(one.get("why")), ""]
        if one.get("practice_line"):
            out += [f"Practise saying: *\"{q(one['practice_line'])}\"*", ""]

    if r.get("next_call"):
        out += ["## On your next call", ""] + [f"- {q(x)}" for x in r["next_call"]] + [""]

    if r.get("wins"):
        out += ["## What worked", ""]
        for w in r["wins"]:
            m = w.get("moment") or {}
            out += [f"### {q(w.get('title'))} ({m.get('time', '')})", ""]
            if m.get("they_said"):
                out += [f"- They said: \"{q(m['they_said'])}\""]
            if m.get("you_said"):
                out += [f"- You said: \"{q(m['you_said'])}\""]
            out += ["", q(w.get("why_it_worked")), ""]

    if r.get("fixes"):
        out += ["## What to change", ""]
        for x in r["fixes"]:
            m = x.get("moment") or {}
            out += [f"### {q(x.get('title'))} ({m.get('time', '')})", ""]
            if m.get("they_said"):
                out += [f"- They said: \"{q(m['they_said'])}\""]
            if m.get("you_said"):
                out += [f"- You said: \"{q(m['you_said'])}\""]
            out += ["", q(x.get("what_happened")), "", f"**Try instead:** \"{q(x.get('try_this'))}\"", ""]

    if r.get("missed_follow_ups"):
        out += ["## Follow-up questions you could have asked", ""]
        for x in r["missed_follow_ups"]:
            out += [f"- **{x.get('time', '')}** They said \"{q(x.get('they_said'))}\". You could ask: \"{q(x.get('ask'))}\""]
        out += [""]

    tv = r.get("tighter_version") or {}
    if tv.get("say_this"):
        out += [f"## A tighter way to say it: {q(tv.get('topic'))}", "",
                f"At {tv.get('time', '')} this took {tv.get('took', '')}. Next time:", "", f"> {q(tv['say_this'])}", ""]

    if r.get("came_across"):
        out += ["## How you came across", ""]
        for x in r["came_across"]:
            out += [f"- **{x.get('kind', '')}: {q(x.get('title'))}** ({x.get('time', '')}). \"{q(x.get('quote'))}\" {q(x.get('note'))}"]
        out += [""]

    out += ["## Listening scores (1 to 7)", ""]
    for s in r.get("listening_scale", []):
        out += [f"- **{s['part']}: {s['score']}.** {q(s.get('why'))}"]
    ref = r.get("reflections") or {}
    out += [""]
    if k:
        out += ["## The numbers", "",
                f"- Length: {round(k.get('length_min', 0))} minutes",
                f"- You talked {round((c['share'] or 0) * 100)}% of the time",
                f"- Longest stretch without a break: {mins(k.get('longest_secs'))}",
                f"- Questions: {k.get('questions', 0)}, follow-ups: {k.get('follow_ups', 0)}, "
                f"reflections: {ref.get('count', 0)}",
                f"- Pace: {k.get('pace', 0)} words a minute", ""]
    out += ["---", "Made from this call's review. The full page with play buttons is review.html in the same folder.", ""]
    return "\n".join(out)


def overall_md(items, pats):
    items = sorted(items, key=lambda c: c["when"])
    out = ["# Getting better: what my calls are teaching me", "",
           f"{len(items)} reviewed calls, {items[0]['when']:%-d %b} to {items[-1]['when']:%-d %b %Y}. "
           "Rebuilt after every call review.", ""]
    if pats:
        out += ["## Focus right now", "", f"**{q(pats.get('focus_next'))}**", "", q(pats.get("headline")), ""]
        if pats.get("keeps_coming_up"):
            out += ["## What keeps coming up", ""]
            for x in pats["keeps_coming_up"]:
                out += [f"### {q(x['title'])}", "", q(x["detail"]), ""]
        if pats.get("getting_better"):
            out += ["## What's getting better", ""]
            for x in pats["getting_better"]:
                out += [f"### {q(x['title'])}", "", q(x["detail"]), ""]

    latest = items[-1]
    if latest["r"].get("next_call"):
        out += [f"## For your next call (from {latest['title']})", ""] + [f"- {q(x)}" for x in latest["r"]["next_call"]] + [""]

    out += ["## Call by call", "",
            "| Date | Call | Grade | Sensing | Processing | Responding | Talk share | Reflections / questions |",
            "|---|---|---|---|---|---|---|---|"]
    for c in reversed(items):
        sc = {s["part"]: s["score"] for s in c["r"].get("listening_scale", [])}
        ref = c["r"].get("reflections") or {}
        share = f"{round(c['share'] * 100)}%" if c["share"] else ""
        out += [f"| {c['when']:%-d %b} | {q(c['title'])} | {c['letter']} | {sc.get('Sensing', '')} | "
                f"{sc.get('Processing', '')} | {sc.get('Responding', '')} | {share} | {ref.get('count', 0)} / {ref.get('questions', 0)} |"]
    out += [""]

    out += ["## The one thing, call by call", "", "Each review picks one habit. The ones that repeat are the ones to drill.", ""]
    for c in reversed(items):
        one = c["r"].get("one_thing") or {}
        if one.get("habit"):
            line = f"- **{c['when']:%-d %b}, {q(c['title'])}:** {q(one['habit'])}"
            if not line.rstrip().endswith((".", "?", "!")):
                line += "."
            if one.get("practice_line"):
                line += f" Practise: \"{q(one['practice_line'])}\""
            out += [line]
    out += [""]

    out += ["## Playbook: lines that worked", "", "Things you said that landed, worth saying again.", ""]
    for c in reversed(items):
        for w in c["r"].get("wins", []):
            said = q((w.get("moment") or {}).get("you_said"))
            if said:
                out += [f"- \"{said}\" ({q(w.get('title'))}, {c['when']:%-d %b})"]
    out += ["", "## Playbook: lines to try", "", "Better versions of moments that didn't land.", ""]
    for c in reversed(items):
        for x in c["r"].get("fixes", []):
            if x.get("try_this"):
                out += [f"- **{q(x.get('title'))}** ({c['when']:%-d %b}): \"{q(x['try_this'])}\""]
    out += ["", "## Each call's learnings", ""]
    for c in reversed(items):
        out += [f"- [{c['when']:%-d %b}, {q(c['title'])}](<{c['name']}/learnings.md>)"]
    out += ["", "---", "Made from the call reviews on this Mac. Each call's full page is review.html in its folder; "
            "all calls with charts is calls.html.", ""]
    return "\n".join(out)


def main():
    items = calls()
    if not items:
        return
    for c in items:
        with open(os.path.join(MEET, c["name"], "learnings.md"), "w") as f:
            f.write(call_md(c))
    try:
        pats = json.load(open(os.path.join(MEET, "patterns.json")))["patterns"]
    except (OSError, ValueError, KeyError):
        pats = None
    with open(OVERALL, "w") as f:
        f.write(overall_md(items, pats))
    print(OVERALL)


if __name__ == "__main__":
    main()
