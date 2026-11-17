# Earshot

*Working title. Dictation, a meeting recorder and a listening coach for your Mac. Free, and it runs on your own machine.*

Hold the Fn key, talk, let go, and your words are typed wherever the cursor is. Record a call, and you get a transcript, a scorecard and a coaching review of how well you listened, with every moment that matters one click from playing back. During the call, a timer nudges you when someone asks "so what are you working on?" and you're about to talk for four minutes. Over time, one private page shows whether you're getting better.

It started as a replacement for two paid apps, a dictation app and an AI meeting notetaker. It turned into something neither of them does: it tells you how you came across.

The whole thing was built in one long working session between a non-engineer and Claude, over about three weeks of daily use. The "How it was built" section is the honest version, including what broke.

## Contents

- [What it does](#what-it-does)
- [The research behind the grade](#the-research-behind-the-grade)
- [Privacy: what stays on your Mac](#privacy-what-stays-on-your-mac)
- [Before you record anyone](#before-you-record-anyone)
- [Install](#install)
- [Using it day to day](#using-it-day-to-day)
- [How it works](#how-it-works)
- [Make it yours: your own menu bar icon](#make-it-yours-your-own-menu-bar-icon)
- [Testing without a live call](#testing-without-a-live-call)
- [Troubleshooting](#troubleshooting)
- [How it was built](#how-it-was-built)
- [Going fully local](#going-fully-local)
- [Known limits](#known-limits)
- [Credits and licence](#credits-and-licence)

## What it does

### Dictation (hold Fn and talk)

- Hold **Fn**, speak, let go. The text is pasted at your cursor and your clipboard is put back.
- **Double-tap Fn** for hands-free mode. Tap once more to finish, or press Escape to throw it away. It stops by itself after five minutes.
- Ums and uhs come out. Say "comma", "period", "question mark", "exclamation point", "new line" or "new paragraph" and you get the mark. "A period of time" is left alone.
- **Snippets:** say "my website" on its own and a saved link is typed instead.
- **Your word list:** names Whisper gets wrong, spelled right from then on. Highlight a wrong word, then choose "Add the highlighted word" from the menu.
- **History:** every dictation is saved on your Mac. Control-Option-H searches it and pastes one again.
- About 1.5 seconds from letting go to text, on an Apple Silicon Mac. It always listens through the Mac's built-in microphone, even with Bluetooth headphones on.

### Prep before the call

- Your next two weeks of calendar events show in the menu. Click one to write what you want from the call, plus prep notes: questions to ask, things to mention.
- When a call is booked, a notification invites you to prep it. An hour before a prepped call, you're reminded of your goal.

### Meeting recorder

- When a call app starts using the microphone, a small panel asks "Record this meeting?". Your goal is already in it if you prepped the call, and you can type one if you didn't.
- It records **two tracks on one clock**: your microphone, and what the Mac plays (the other people). The transcript says who said what because the two sides never mix.
- It stops when you click, or after four minutes of silence on the call.
- Transcription runs on your Mac with Whisper. If you're on speakers, the other side's voices are taken out of your track.

### The pitch timer (live, during calls)

- When the other person asks an open question ("What are you working on?", "Tell me about...", "How did that go?"), a countdown appears at the top of the screen, near your camera.
- It starts when you start answering: one minute, amber with 15 seconds left, red at zero, then it counts how far over you went.
- It stops when they take the floor or you pause, then flashes your time. Click it to hide it.
- Yes/no and scheduling questions ("Can you hear me?", "Are you going to that?") are ignored.

### After the call

1. **A self-rating panel**, 20 seconds, before you see anything else. You rate your own listening on the same three parts the review uses, plus one thing you'd do differently. These ratings are never sent anywhere.
2. **A transcript**, Me and Them, with timestamps.
3. **A scorecard**, measured on your Mac from the audio: how long you talked and listened, your longest monologue, your follow-up questions, your pause before answering, and when you talked over someone.
4. **A call review page**, written by Claude from the transcript:
   - an overall grade, whether you got what you came for, and what kind of call it was
   - your own rating next to the review's, so you can see the gap
   - your listening on a published research scale, with the moment behind each score
   - three things that worked and three to change, each with the exact words to try next time
   - four follow-up questions you could have asked, built on what the other person said
   - your timed answers to open questions, from the pitch timer
   - a tighter version of the main thing you explained
   - a play button on every moment, showing how long the clip is, with 1x to 2x speed
   - a sticky bar to jump between sections
5. **A notification** when the review is ready, showing the grade and a one-line verdict.

### All my calls

One private page with every reviewed call: the latest grade, trend charts, and a summary of what keeps coming up across calls and what's getting better. A dashed line shows your self-ratings against the review's. A second tab, **The science**, explains every measure and links to the studies behind it.

## The research behind the grade

The first version graded calls against a rubric we made up. That was replaced with measures that have published evidence behind them. The science tab says how strong each one is.

| Measure | Source | Evidence | How it's measured here |
|---|---|---|---|
| Overall grade: sensing, processing, responding | Bodie (2011), the Active-Empathic Listening Scale | Validated rating scale | Claude rates each part 1 to 7 from the transcript, quoting the moment. The average becomes a letter: 6 is an A, 5 a B, 4 a C |
| Follow-up questions | Huang, Yeomans, Brooks, Minson & Gino (2017), *JPSP* | Peer reviewed | Questions that share key words with what the other person just said. Two per 10 minutes is this tool's bar |
| Reflections per question | MITI, the Motivational Interviewing Treatment Integrity code | Clinical coding manual | Claude counts them the way a MITI coder would. One per question is the starting level |
| Talk share, 43% to 57% | Gong's analysis of recorded sales calls | Industry data, not peer reviewed | From the audio of each side |
| Longest monologue under 2.5 minutes | Gong | Industry data, not peer reviewed | From the audio |
| Pause before answering, about 0.2 seconds | Stivers et al. (2009), *PNAS* | Peer reviewed | From the audio (context only, no pass or fail) |
| Talking over vs talking together | Tannen, cooperative overlap | Linguistics research | An overlap only counts against you if the other person stops |
| Answering open questions in about a minute | Elevator-pitch practice, and Gong's monologue data | Practice target | The pitch timer, live |

Context matters. If the call was mainly you being interviewed or advised, talk share and monologue length are marked "doesn't apply". The research behind them is about leading a conversation.

Links:
[Bodie 2011](https://doi.org/10.1080/01463373.2011.583495) ·
[Huang et al. 2017](https://doi.org/10.1037/pspi0000097) ·
[MITI 4.2 manual](https://casaa.unm.edu/assets/docs/miti4_2.pdf) ·
[Gong talk-to-listen ratio](https://www.gong.io/blog/talk-to-listen-conversion-ratio) ·
[Gong call stats and monologues](https://help.gong.io/docs/understand-your-team-s-call-stats) ·
[Stivers et al. 2009](https://doi.org/10.1073/pnas.0903616106) ·
[Li 2001, on cooperative and intrusive interruptions](https://www.interruptions.net/literature/Li-JLSP01.pdf)

## Privacy: what stays on your Mac

- **Your voice never leaves your Mac.** Recording, transcription and the pitch timer are all local. No audio is sent anywhere.
- **Dictation clips are deleted** as soon as their words are typed.
- **The pitch timer's live copy of the call** is deleted when the call ends.
- **Meeting audio is deleted after 30 days.** Transcripts and reviews stay, as plain files in one folder.
- **Your calendar is read only on your Mac**, by a small helper app. It reads titles, times, guest names and video links for the next two weeks, and it never writes to your calendar.
- **One step uses the cloud: the call review.** The transcript text, never the audio, goes to Claude through the Claude Code command line, on your own Claude subscription. There's no API key and no extra bill. A review uses roughly 20,000 to 40,000 tokens of your plan.
- **Your self-ratings are never sent,** so the review grades you independently.
- **The review's sign-in** is kept in a file only your account can read (`~/.config/call-review/claude-token`).
- **Want it fully offline?** The review step can run on a local open model instead. See "Going fully local" below.

## Before you record anyone

This tool records other people. Recording laws differ by country and by state, and some require everyone on the call to agree. Tell people you're recording, and check the rules where you and they are. The meeting panel never records without you clicking Record.

## Install

### Requirements

- A Mac with Apple Silicon, on macOS 14 or later. It was built on an M4 MacBook Air with 32 GB of memory.
- [Hammerspoon](https://www.hammerspoon.org), free. In its preferences, tick "Launch Hammerspoon at login".
- [Homebrew](https://brew.sh), then `brew install whisper-cpp ffmpeg`.
- Xcode Command Line Tools, for `swiftc`: `xcode-select --install`.
- Python 3.
- For the review step: [Claude Code](https://claude.com/claude-code) and a Claude subscription.

### Steps

1. **Get the code and build the three small helpers:**

   ```bash
   git clone <this repo> ~/earshot
   cd ~/earshot
   python3 -m venv .venv && .venv/bin/pip install numpy
   swiftc -O dictrec/dictrec.swift -o dictrec/dictrec
   swiftc -O meetcap/meetcap.swift -o meetcap/meetcap
   mkdir -p "calcheck/Meeting Prep.app/Contents/MacOS"
   cp calcheck/Info.plist "calcheck/Meeting Prep.app/Contents/Info.plist"
   swiftc -O calcheck/calcheck.swift -o "calcheck/Meeting Prep.app/Contents/MacOS/calcheck"
   codesign --force -s - "calcheck/Meeting Prep.app"
   ```

2. **Get the models.** `models/README.md` has the three commands: two downloads (the Whisper model, 574 MB, and the Silero voice detector, 1 MB) and one line that makes the warm-up clip with your Mac's own voice.

3. **Check `settings.json`.** It says where your meetings are kept (`~/Earshot Meetings` unless you change it), the answer target for the pitch timer (60 seconds), and whether the pitch timer and call reviews are on. The code finds its own folder, so you can clone it anywhere.

4. **Your word list and snippets** are made from `words.example.txt` and `snippets.example.txt` the first time it runs. Edit them from the menu afterwards. They stay out of git.

5. **Load it in Hammerspoon.** Add these lines to `~/.hammerspoon/init.lua`, then choose Reload Config:

   ```lua
   require("hs.ipc")
   dictation = dofile(os.getenv("HOME") .. "/earshot/dictation.lua")
   meetings  = dofile(os.getenv("HOME") .. "/earshot/meetings.lua")
   ```

6. **Give the review its own sign-in.** Skip this if you don't want reviews: set `"call_reviews": false` in `settings.json`, and you still get transcripts and scorecards.

   ```bash
   ./save-review-token.sh
   ```

   It runs `claude setup-token`, which opens your browser. Approve it, copy the token it prints, and paste it once at the hidden prompt. It lasts about a year. Don't use the everyday `claude auth login` sign-in for this: it's shared with the Claude desktop app, and one signs the other out.

7. **Allow the permissions macOS asks for**, each once:

   | Permission | For | Where |
   |---|---|---|
   | Accessibility | The Fn key and pasting | Privacy & Security › Accessibility › Hammerspoon |
   | Microphone | Dictation and your side of calls | Asked on first use |
   | Screen & System Audio Recording | The other side of calls | Privacy & Security › Screen & System Audio Recording › Hammerspoon |
   | Calendars | Prep before calls | Asked by Meeting Prep on first run |

8. **If your meetings live in Google Calendar,** add the account under System Settings › Internet Accounts and switch on Calendars only.

## Using it day to day

Everything lives in the menu bar icon.

| Menu item | What it does |
|---|---|
| Search what I've dictated (Control-Option-H) | Find any past dictation and paste it again |
| Add the highlighted word to my word list | Teach it a name it keeps getting wrong |
| Edit my word list / Edit my snippets | Open the files |
| Record a meeting now | Start recording without waiting for a call app |
| Set this call's goal | While recording, add or change the goal |
| Pitch timer during calls: on/off | Switch the live timer |
| Upcoming calls: prep | Your next two weeks. ✓ marks calls you've prepped |
| Recent meetings › a call | Open transcript, Listening scorecard, Call review, Rate my listening, Add or change this call's goal, Write notes with Claude, Coach me with Claude |
| All my calls: grades and trends | The history page |
| Restart dictation | Reload everything |

### What each call's folder contains

Every call gets a folder like `2026-01-15 1000 Call/` in your meetings folder (`~/Earshot Meetings` by default).

| File | What it is |
|---|---|
| `meeting.json` | When it started, the call app, your goal and prep notes, the calendar event and guests |
| `me.wav`, `them.wav`, `me_clean.wav`, `call.m4a` | The audio (deleted after 30 days) |
| `transcript.md` | Me and Them, with timestamps |
| `turns.json`, `me.json`, `them.json` | The transcript with exact timings, used for the scorecard and the clips |
| `coach.md`, `coach.json` | The scorecard |
| `selfcheck.json` | Your own ratings |
| `pitches.json` | Each open question and how long your answer took |
| `review.json`, `review.html` | Claude's review, and the page made from it |

In the meetings folder itself: `calls.html` (All my calls), `patterns.json` (what keeps coming up), `prep.json` (your goals and notes before calls) and `upcoming-calendar.json` (the next two weeks).

## How it works

```
 Hold Fn ──► dictrec (Swift, built-in mic) ──► whisper-server (model kept loaded) ──► tidy ──► paste

 Calendar ──► Meeting Prep.app ──► upcoming calls ──► prep panel (goal, notes) ──► prep.json

 Call starts ──► record panel (goal filled in) ──► meetcap (Swift, ScreenCaptureKit)
                                                      │  me.wav + them.wav on one clock
                                                      │  live loudness of both sides ──► pitch.lua ──► countdown
                                                      │  live copy of their side ──► whisper-server ──► open question?
                                                      ▼
                  self-rating panel ◄── call ends     meeting_finish.py: echo removal, whisper-cli, transcript.md
                                                      ▼
                                                      meeting_coach.py: timing from the audio, coach.md
                                                      ▼
                                                      meeting_review.py: claude -p with a JSON schema, review.html
                                                      ▼
                                                      meeting_history.py: calls.html, patterns across calls
```

### The pieces

| File | What it does |
|---|---|
| `dictation.lua` | The Fn key, the speech server, the tidy step, snippets, history and the menu bar icon |
| `meetings.lua` | The record, prep and self-rating panels, the calendar refresh, review notifications, the meetings menu |
| `pitch.lua` | The live pitch timer: spots open questions on the other side and runs the one-minute countdown |
| `dictrec/dictrec.swift` | The dictation recorder. It always uses the built-in mic, starts in about 0.1 seconds and keeps recording 0.3 seconds after you let go |
| `meetcap/meetcap.swift` | Records both sides of a call on one clock with ScreenCaptureKit. Reports both sides' loudness five times a second and keeps a live copy of their side for the pitch timer |
| `calcheck/calcheck.swift` | **Meeting Prep.app**, a tiny app with no Dock icon that reads your calendar |
| `meeting_finish.py` | Echo removal, transcription, and merging the two sides into `transcript.md` |
| `meeting_coach.py` | The scorecard: talk time, monologues, overlaps and pauses from the sound, questions from the words |
| `meeting_review.py` | Asks Claude for the review as structured JSON, then builds the review page with timed clips |
| `meeting_history.py` | Builds the All my calls page and asks Claude what keeps coming up across calls |
| `save-review-token.sh` | Gives the review its own long-lived Claude sign-in |
| `pitch_replay.py` | Replays part of a recorded call in real time, to test the pitch timer |
| `settings.json` | Where meetings are kept, the answer target, and whether the pitch timer and reviews are on |
| `icons/` | The menu bar icons: idle, listening, and recording a call |
| `make_icons.py` | Makes your own icons, in your colours or from your photo |
| `words.example.txt`, `snippets.example.txt` | Starting points for your word list and snippets |
| `models/` | The speech models and the warm-up clip (see `models/README.md`) |

### Things you can tune

| Where | What |
|---|---|
| `settings.json`: `answer_seconds` | The pitch timer's target (60) |
| `settings.json`: `pitch_timer`, `call_reviews` | Turn the live timer or the Claude review off |
| `settings.json`: `meetings_folder` | Where calls, reviews and the history page are kept |
| `pitch.lua`: `THEM_ON`, `ME_ON` | How loud counts as talking on each side. Measured on a real call: 0.02 and 0.015 |
| `pitch.lua`: `OPEN`, `CLOSED` | The phrases that make a question open, and the ones that rule it out |
| `meetings.lua`: `QUIET_STOP` | Seconds of silence before a recording stops by itself (240) |
| `meeting_coach.py` | The benchmark bars (talk share, monologue, follow-ups) |
| `meeting_review.py`: `SCHEMA`, `PROMPT` | What the review contains and how Claude is asked for it |

## Make it yours: your own menu bar icon

The menu bar icon keeps its colours. Most menu bar icons are "template" images, which macOS turns black and white to match the bar. This one isn't: the code calls `setIcon(img, false)`, and `false` tells macOS to show the picture as it is. So your icon can be any colour, or your own face.

There are three icons, in `icons/`:

| File | When it shows |
|---|---|
| `idle.png` | Most of the time. It's also the picture on review notifications |
| `listening.png` | While you dictate. The idle icon with a coloured ring |
| `recording.png` | While a call is recording. A dark ring and a red dot |

**Make all three in one line** with `make_icons.py` (it needs Pillow: `.venv/bin/pip install pillow`):

```bash
# a disc in your colours
.venv/bin/python make_icons.py --color "#1B4F8F" --mark "#FFFFFF" --ring "#7FB8F0"

# your photo, cropped to a circle
.venv/bin/python make_icons.py --photo ~/Pictures/me.jpg

# your photo in shades of one colour, which reads better at this size
.venv/bin/python make_icons.py --photo ~/Pictures/me.jpg --tint "#F4C6D6" --ring "#E57BA6"
```

Then choose **Restart dictation** in the menu.

| Option | What it sets |
|---|---|
| `--color`, `--mark` | The disc and its sound waves, when there's no photo |
| `--photo` | A photo to use instead, cropped from just above the middle so a face sits well |
| `--tint` | Turns the photo into shades of one colour |
| `--ring` | The ring while you dictate |
| `--rec-ring`, `--dot` | The ring and dot while a call records |

**Drawing your own by hand** works too. Make three PNGs, 104 pixels square, with a transparent background, and keep the important part inside the middle 76 pixels so the ring and dot have room. The menu bar shows them at 26 points, which is why 104 pixels stays sharp on a Retina screen. Keep shapes bold: fine detail disappears at that size. Your icons are yours, so if you'd rather not share your face, add `icons/` to `.gitignore` in your copy.

## Testing without a live call

- **The pitch timer:** in the Hammerspoon console, replay a stretch of a recorded call in real time. For example, 110 seconds from 7:10:

  ```lua
  meetings.pitchReplay(os.getenv("HOME") .. "/Earshot Meetings/2026-01-15 1000 Call", 430, 110, "/tmp/pitchtest")
  ```

  The countdown appears as it would live, and `/tmp/pitchtest/pitches.json` shows what it logged.

- **A transcript, scorecard and review for an existing recording:**

  ```bash
  .venv/bin/python meeting_finish.py "<meeting folder>"
  ```

- **Just the review page, without asking Claude again:**

  ```bash
  .venv/bin/python meeting_review.py "<meeting folder>" --page
  ```

## Troubleshooting

| What you see | What to do |
|---|---|
| Nothing happens when you hold Fn | Check Accessibility for Hammerspoon, then Restart dictation |
| "Dictation is starting up" | The speech model takes a few seconds to load after login |
| Dictation types nonsense | Check which mic it's using: it's built to use the Mac's own. Bluetooth headset mics are muffled and confuse Whisper |
| The other side of a call is silent | Allow Screen & System Audio Recording for Hammerspoon. FaceTime can't be captured |
| "Call review couldn't run" | The review's sign-in has expired or is missing: run `./save-review-token.sh` again |
| A review is refused as "too long" | Make sure reviews run lean (`--strict-mcp-config --disable-slash-commands`, as in the code). A Claude Code setup with many plugins and connected apps can otherwise add hundreds of thousands of tokens |
| Upcoming calls is empty | Allow Calendars for Meeting Prep, and add your Google account under Internet Accounts |
| The pitch timer never appears | Check it's on in the menu, and that the call is being recorded. Try the replay test above |
| The pitch timer fires on the wrong questions | Edit `OPEN` and `CLOSED` in `pitch.lua` |

## How it was built

This is the useful part if you want to build something like it. Every fix below came from a real failure on a real day.

### 1. Start simple, then measure

Version one was 300 lines of Lua: ffmpeg recorded while Fn was held, and a Whisper server turned the clip into text. It worked, badly. Usage dropped off within a week. Reading its own history file showed why:

- **First words cut off:** "Side of this new script" instead of "Inside of this new script". Timing showed ffmpeg took half a second to start listening, and people start talking the moment they press the key.
- **Last words cut off:** "Put this note into". Recording stopped the instant the key came up.
- **Invented sentences:** "And I'll see you next time." Whisper fills silence with phrases it has seen thousands of times.
- **Slow after a break:** the first dictation after a few minutes took 3.5 seconds. Apple's graphics memory let go of the model after 180 seconds idle.
- **Two servers running at once:** an old copy ignored the normal stop signal and survived two weeks of restarts.

**Fixes:** a small Swift recorder that starts in about 0.1 seconds and keeps listening 0.3 seconds after release. Whisper's built-in voice detection on the server. A keep-alive setting (`GGML_METAL_RESIDENCY_KEEP_ALIVE_S`) plus a tiny warm-up clip every 2.5 minutes. A force-stop of stray servers on every start.

**Lesson:** keep a log of what the tool produced. The bugs were all sitting in plain sight in `history.txt`.

### 2. Bluetooth headphones broke everything

One morning dictation turned a normal sentence into "Nova's night was gone". The cause: wireless headphones had become the Mac's microphone. Their headset mic is narrow, muffled audio, and turning it on changes the audio format mid-stream, which crashed the recorder.

The first fix, pointing Apple's audio engine at the built-in mic, crashed too. The engine insists on the system's default input. Rebuilding the recorder on `AVCaptureSession`, which takes a named device, fixed it for good.

**Lesson:** test with the hardware people actually wear.

### 3. A side-by-side test against the paid notetaker

The same 30-minute call went through both tools, and the transcripts were compared line by line.

- **This tool won on who said what,** because the two sides are separate recordings.
- **The paid tool won on readability and names:** "Substack" came out as "sub stack" and "sub snack".

Three Whisper settings closed most of the gap:

- **`--carry-initial-prompt`** sends your word list to every 30-second window, not just the first.
- **`-ml 120 -sow`** gives sentence-length lines, so one side's long turn can't swallow the other side's interruption.
- **The word list goes in as a punctuated sentence,** not a bare list of names. Whisper copies the style of its prompt. A bare list gave six minutes with zero punctuation. The same names in a sentence gave 65 marks.

Two ideas were tested and dropped. Removing Whisper's memory of earlier text fixed one skipped passage, but cost minutes of punctuation. Shrinking the audio window for short clips was three times faster, but it made up words.

**Lesson:** compare against the thing you're replacing, on the same input.

### 4. The scorecard: trust the sound, not the transcript

The first scorecard said the user interrupted 35 times in 30 minutes. Wrong: Whisper's line endings run on into the silence after someone stops, so every handover looked like an overlap.

Measuring from the audio fixed it. Each side has its own track on one clock, so loudness frame by frame shows exactly who is talking. The real number was 12, and the other person did it 12 times too. That's two people talking with energy.

**Lesson:** when two signals disagree, measure the one closer to reality.

### 5. Replacing a made-up rubric with research

The first grade came from a rubric we invented. The user's next question was "are there standardized, vetted tests for this?" There's no single test that grades a call automatically. The validated listening scales are filled in by a trained observer or the other person. So the tool combines:

- **things a computer can count from audio,** each matched to a published benchmark
- **a validated scale** (Bodie's Active-Empathic Listening Scale) **rated by Claude acting as the observer**, with a quoted moment behind every score

Reflections per question were dropped from the automatic count when word matching kept missing them. "Branching out your ecosystem" is a perfect reflection that shares no words with what the other person said. Claude counts those instead.

**Lesson:** say which parts are evidence and which are your own judgment. The science tab does exactly that.

### 6. Make the review usable in two minutes

The first scorecard was a wall of numbers. The user said she'd have to reread the whole transcript to act on it. The review page answers that:

- Every finding is pinned to a moment: what they said, what you said, and the words to try instead.
- A play button for each moment, timed from Whisper's own line timings, so you hear the exchange instead of reading it. Clips were checked by transcribing them again.
- The grade and talk-versus-listen bar at the top. A sticky bar to jump between sections.

Readability got its own pass. Pink text on white and a murky dark mode were both hard to read, so colour now only marks what kind of card you're looking at.

### 7. Context changes the grade

A call where you're being advised shouldn't be graded like a pitch. With an optional goal, or a call type the review works out itself, a call that scored D− became C−. The talk-share bars were marked "doesn't apply", and the review says whether you got what you came for.

Prep before the call came next, so the goal is written when the meeting is booked rather than in the scramble just before it. A self-rating at the end of each call came with it: rating yourself before you read the review makes the gap visible.

### 8. A live coach, not just a report

The hardest request: notice, during the call, when someone asks a question that invites a long answer, and put a one-minute timer on screen.

The recorder already separated the two sides, so it needed two additions: loudness for each side five times a second, and a live copy of the other side's audio. When they finish speaking, their last few seconds go to the speech server that dictation keeps warm, and the words are checked against patterns for open questions.

Whisper takes about a second, and people start answering faster than that. So the timer counts from when you actually started talking, not from when the question was recognised. It was tested by replaying a real call in real time: it caught "So what's new with you?" and timed the answer.

### 9. Small engineering notes

- **Calendar access needed its own tiny app.** Hammerspoon can't request calendar access, and a plain command line can't either. A minimal app bundle (`LSUIElement`, with a calendar usage description) can, and Hammerspoon runs it in the background.
- **Your own calendar events look different from invites.** Events you create often have no guests, and Google keeps Meet links where the Mac's calendar doesn't show them. So every timed event counts as a possible call, except daily repeats, flights and long blocks.
- **The review needs its own sign-in, and a lean setup.** The command line's normal sign-in is shared with the Claude desktop app, so one would sign the other out. A long-lived token from `claude setup-token` fixed that. And with every plugin and connected app loaded, a one-line request was 260,000 tokens and refused, so reviews run with `--strict-mcp-config --disable-slash-commands` from an empty folder (about 10,000).
- **Review notifications come through a marker file.** The review runs as a detached process, so it can't call back into Hammerspoon. Instead it drops a `review-new` file, and a folder watcher turns that into a clickable notification.
- **Panels that take typing are small web views.** Hammerspoon's drawing canvas can't take keyboard input, so the record, prep and self-rating panels are tiny web pages that post their answers back. They never take focus from your call app until you click into them.
- **Typesetting rules are enforced in code.** The pages pass a layout checker at four widths: no single word alone on a last line, and no sentence starting at the end of a line. The page generator joins words with non-breaking spaces where needed.

## Going fully local

The review is the only step that uses the cloud. To keep it on your Mac, swap the `claude -p` call in `meeting_review.py` and `meeting_history.py` for a local model through [llama.cpp](https://github.com/ggml-org/llama.cpp). It's `llama-server --json-schema` with the same schema the review already uses. Google's Gemma 4 26B (about 14 GB) fits a 32 GB Mac. This hasn't been built yet. Expect reviews that are slower and less sharp than Claude's.

## Known limits

- **Speed depends on what else your Mac is doing.** Transcribing a 30-minute call takes 2 to 15 minutes.
- **FaceTime keeps its call audio from screen capture,** so the other side of a FaceTime call isn't recorded.
- **Whisper still mishears.** Names it hasn't seen, and words like "Claude" heard as "cloud", need your word list.
- **The pitch timer hears questions by pattern,** in English. It will miss some open questions and occasionally fire on one that isn't.
- **The grade is a guide.** It's based on research from sales calls, counselling and lab studies. A friendly catch-up is a different kind of conversation.

## Credits and licence

[whisper.cpp](https://github.com/ggml-org/whisper.cpp) and OpenAI's Whisper model ·
[Silero VAD](https://github.com/snakers4/silero-vad) ·
[Hammerspoon](https://www.hammerspoon.org) ·
[ffmpeg](https://ffmpeg.org) ·
Claude, for the reviews and much of the code ·
the researchers above, whose work the grade stands on.

Licence: MIT (see `LICENSE`).
