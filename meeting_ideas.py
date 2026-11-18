"""Ideas for an upcoming call: what to touch on, questions to ask, and your own habit to watch.

    .venv/bin/python meeting_ideas.py call.json      call.json: {"title", "about", "goal", "notes", "people"}

Used by the prep panel (meetings.lua, "Get ideas"). Prints one JSON object. Claude reads what you typed about the
call, your learnings across calls (Learnings.md in the meetings folder), and the learnings from any past call
with the same people, so the ideas fit both the call and what you're working on. Runs on your Claude
subscription through the command line, like the reviews. Only text goes to Claude.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from meeting_review import CLAUDE, CLAUDE_LEAN, claude_env, lean_dir   # noqa: E402
from meeting_history import MEET   # noqa: E402

SCHEMA = {"type": "object", "properties": {
    "opener": {"type": "string", "description": "a natural first thing to say once hellos are done, under 25 words"},
    "touch_on": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "object", "properties": {
        "point": {"type": "string", "description": "a topic or point to raise, under 12 words"},
        "why": {"type": "string", "description": "one short sentence on why it matters for this call"}},
        "required": ["point", "why"]}},
    "questions": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "string"},
                  "description": "open questions to ask them, each under 20 words"},
    "watch_for": {"type": "string", "description": "their own habit most likely to show up on this call, and what to do instead, under 30 words"},
    "from_before": {"type": "string", "description": "if a past call with these people is given, one sentence on what to pick up from it; else empty"}},
    "required": ["opener", "touch_on", "questions", "watch_for", "from_before"]}


def words(s):
    return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower())}


def past_calls(call):
    """Learnings from earlier reviewed calls with the same people (by name or email on the invite, or title)."""
    want = {p.lower() for p in call.get("people") or []}
    name_words = words(" ".join(call.get("people") or [])) | (words(call.get("title")) - {"call", "meeting", "with", "the", "and", "catch"})
    found = []
    for name in sorted(os.listdir(MEET), reverse=True):
        folder = os.path.join(MEET, name)
        lm = os.path.join(folder, "learnings.md")
        if not os.path.exists(lm):
            continue
        try:
            meta = json.load(open(os.path.join(folder, "meeting.json")))
        except (OSError, ValueError):
            meta = {}
        theirs = {p.lower() for p in meta.get("people") or []}
        title = open(lm).readline()
        if (want and want & theirs) or (name_words and name_words & (words(title) | words(" ".join(theirs)))):
            found.append(open(lm).read()[:5000])
        if len(found) == 2:
            break
    return found


def main():
    call = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else json.load(sys.stdin)
    try:
        learnings = open(os.path.join(MEET, "Learnings.md")).read()
        learnings = learnings.split("## Playbook: lines to try")[0][:9000]
    except OSError:
        learnings = "(no reviewed calls yet)"
    before = past_calls(call)
    prompt = (
        "The user has a call coming up and wants a few ideas before it. Give them things to touch on, open questions "
        "to ask, a natural opener, and the one habit of theirs to watch on this call, taken from their learnings. "
        "Fit everything to what this call is about and what they want from it. Concrete and specific to this call, "
        "not generic advice. Plain words, short sentences, no em dashes, no flattery. Speak to them as 'you'.\n\n"
        "THE CALL\n" + json.dumps(call, indent=1, ensure_ascii=False) + "\n\n"
        "THEIR LEARNINGS ACROSS PAST CALLS\n" + learnings + "\n\n"
        + ("PAST CALLS WITH THESE PEOPLE\n" + "\n\n---\n\n".join(before) if before else "No past reviewed call with these people.")
    )
    try:
        run = subprocess.run([CLAUDE, "-p", "--no-session-persistence", "--model", "sonnet", "--output-format", "json",
                              "--tools", "", *CLAUDE_LEAN, "--json-schema", json.dumps(SCHEMA)],
                             input=prompt, capture_output=True, text=True, timeout=240, env=claude_env(), cwd=lean_dir())
        out = json.loads(run.stdout).get("structured_output")
    except (ValueError, subprocess.SubprocessError, OSError) as err:
        out, run = None, None
        print(json.dumps({"error": f"Couldn't reach Claude ({type(err).__name__})."}))
        return
    if not out:
        msg = (run.stdout or run.stderr or "")[-300:] if run else ""
        print(json.dumps({"error": "Claude didn't send ideas back. " + msg.strip()}))
        return
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
