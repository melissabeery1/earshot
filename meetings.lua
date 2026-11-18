-- Meeting recorder. Loaded after dictation.lua.
--
-- When a call app starts using the microphone, a small panel asks "Record this meeting?". Recording keeps
-- two tracks on one clock, both from meetcap: your microphone (me.wav) and what the Mac plays (them.wav), so the
-- transcript can say Me and Them. It stops when you click stop, or after four quiet minutes on the call.
-- meeting_finish.py then transcribes on this Mac and writes transcript.md. Notes come from Claude when you
-- ask (Recent meetings > Write notes with Claude copies a ready message). Audio is kept 30 days.

local HERE    = (debug.getinfo(1, "S").source:match("^@(.+)/[^/]+$"))   -- the folder this file is in
local SETTINGS = hs.json.read(HERE .. "/settings.json") or {}
local MEET    = (SETTINGS.meetings_folder or "~/Earshot Meetings"):gsub("^~", os.getenv("HOME"))
local MEETCAP = HERE .. "/meetcap/meetcap"
local PYTHON  = HERE .. "/.venv/bin/python"       -- has numpy, for taking the speaker echo out of your mic
local QUIET_STOP = 240          -- seconds of silence from the other side before it stops by itself
local ASK_AFTER  = 6            -- seconds a call app holds the mic before you're asked

local M = {}
local pitch = dofile(HERE .. "/pitch.lua")                          -- the live pitch timer
M.pitch = pitch
local _ = hs.json, hs.webview, hs.dialog, hs.notify, hs.pathwatcher   -- load these at startup, not mid-panel
local active                    -- the meeting being recorded: { folder, mic, sys, started, lastSound, open }
local prompted, micSince, panel = false, nil, nil

-- Which call app is open, for the transcript header. Browsers count too (Google Meet).
local APPS = { { "zoom.us", "Zoom" }, { "Microsoft Teams", "Teams" }, { "MSTeams", "Teams" }, { "Webex", "Webex" },
  { "FaceTime", "FaceTime" }, { "Slack", "Slack" }, { "Discord", "Discord" } }
local function callApp()
  for _, a in ipairs(APPS) do if hs.application.get(a[1]) then return a[2] end end
  return "Call"
end

------------------------------------------------------------------ the panels (web panels, so you can type)
-- the ask panel takes an optional goal for the call, and a self-rating panel opens when a call
-- ends. Both are small web panels at the top right. They never take focus from the call app: you click into
-- one to type. Whatever you type stays on this Mac (meeting.json, selfcheck.json).
local function closePanel()
  local p = panel
  panel = nil
  if p then pcall(function() p:delete() end) end                  -- already gone (closed with the red button) is fine
end

local CSS = [[
  * { box-sizing: border-box; } body { margin: 0; padding: 16px 18px; background: #FFFFFF; color: #17151A;
  font: 14px/1.4 -apple-system, sans-serif; } 
  h1 { font-size: 15px; margin: 0 0 10px; } .hint { color: #4A4550; font-size: 12.5px; margin: 0 0 8px; }
  input, textarea { width: 100%; font: 14px -apple-system, sans-serif; padding: 8px 10px; border: 1px solid #C9C4C7;
  border-radius: 8px; } textarea { height: 52px; resize: none; }
  .row { display: flex; gap: 8px; margin-top: 12px; } button { font: 600 14px -apple-system, sans-serif; border-radius: 99px;
  padding: 7px 16px; cursor: pointer; border: 1px solid #2B1626; } .go { background: #2B1626; color: #FFFFFF; }
  .no { background: transparent; color: inherit; border-color: #8E878C; }
  .q { margin: 10px 0 2px; font-weight: 700; } .q span { font-weight: 400; color: inherit; opacity: .75; }
  .scale { display: flex; gap: 4px; } .n { flex: 1; padding: 6px 0; border-radius: 8px; border: 1px solid #C9C4C7;
  background: #F6F5F4; color: #17151A; font-weight: 700; } .n.on { background: #2B1626 !important; color: #FFFFFF !important; border-color: #2B1626 !important; }
  @media (prefers-color-scheme: dark) { body { background: #1D1B1F; color: #F5F3F4; }
  input, textarea { background: #121113 !important; color: #F5F3F4 !important; border-color: #4A4550 !important; }
  .n { background: #2B282E !important; color: #F5F3F4 !important; border-color: #4A4550 !important; } .hint { color: #CFCACD !important; }
  body .go { background: #FFFFFF !important; color: #2B1626 !important; border-color: #FFFFFF !important; }
  body .n.on { background: #FFFFFF !important; color: #2B1626 !important; border-color: #FFFFFF !important; } }
]]

local function webPanel(w, h, html, onMessage, title)
  closePanel()
  local f = hs.screen.mainScreen():frame()
  local uc = hs.webview.usercontent.new("panel")
  uc:setCallback(function(msg) onMessage(msg.body) end)
  panel = hs.webview.new({ x = f.x + f.w - w - 18, y = f.y + 10, w = w, h = h }, { developerExtrasEnabled = false }, uc)
  panel:windowStyle({ "titled", "closable" }):windowTitle(title):allowTextEntry(true)
  local mine = panel
  panel:windowCallback(function(action) if action == "closing" and panel == mine then panel = nil end end)
  panel:level(hs.drawing.windowLevels.floating):html("<!doctype html><meta charset='utf-8'><style>" .. CSS .. "</style>" .. html)
  panel:show()
  return panel
end

local function send(js) return "window.webkit.messageHandlers.panel.postMessage(" .. js .. ")" end

-- Record this meeting? With an optional line: what does you want from the call?
local function ask(onRecord, asked)
  local ev = M.eventNow and M.eventNow()
  local pre = ev and hs.fs.attributes(MEET .. "/prep.json") and (hs.json.read(MEET .. "/prep.json") or {})[ev.id] or {}
  local preGoal = (pre.goal or ""):gsub("&", "&amp;"):gsub('"', "&quot;"):gsub("<", "&lt;")
  M.pendingEvent = ev
  webPanel(360, 196, [[
    <h1>]] .. (asked and "A call started. Record this meeting?" or "Record a meeting") .. [[</h1>
    <p class="hint">]] .. (preGoal ~= "" and "From your prep. Change it if you need to; the review judges the call against it."
      or "Optional: what do you want from this call? The review will judge it against this.") .. [[</p>
    <input id="g" placeholder="e.g. get Sam's take on our pricing" maxlength="160" value="]] .. preGoal .. [["
      onkeydown="if(event.key==='Enter'){]] .. send("{go:true,goal:g.value}") .. [[}">
    <div class="row"><button class="go" onclick="]] .. send("{go:true,goal:g.value}") .. [[">Record</button>
      <button class="no" onclick="]] .. send("{go:false}") .. [[">]] .. (asked and "Not now" or "Cancel") .. [[</button></div>]],
    function(b)
      closePanel()
      if b.go then onRecord((b.goal or ""):gsub("^%s+", ""):gsub("%s+$", "")) end
    end, "Record this meeting?")
  if asked then hs.timer.doAfter(90, function() if not active then closePanel() end end) end
end

-- How did you listen? The same three parts the review scores, before you see the review.
local function selfCheck(folder)
  local function scale(id)
    local out = {}
    for i = 1, 7 do out[#out + 1] = '<button class="n" data-p="' .. id .. '" data-v="' .. i .. '" onclick="pick(this)">' .. i .. "</button>" end
    return '<div class="scale">' .. table.concat(out) .. "</div>"
  end
  webPanel(400, 430, [[
    <h1>How did you listen?</h1>
    <p class="hint">20 seconds, before you see the review. 1 is not at all, 7 is fully. Your ratings sit next to the review's, so you can see the gap.</p>
    <p class="q">Sensing <span>· I caught what they said and meant</span></p>]] .. scale("sensing") .. [[
    <p class="q">Processing <span>· I remembered and connected it</span></p>]] .. scale("processing") .. [[
    <p class="q">Responding <span>· I showed them I understood</span></p>]] .. scale("responding") .. [[
    <p class="q">One thing I'd do differently <span>· optional</span></p><textarea id="t" maxlength="240"></textarea>
    <div class="row"><button class="go" onclick="save()">Save</button><button class="no" onclick="]] .. send("{skip:true}") .. [[">Skip</button></div>
    <script>
      var r = {};
      function pick(b) { r[b.dataset.p] = +b.dataset.v;
        document.querySelectorAll('[data-p="' + b.dataset.p + '"]').forEach(function (x) { x.classList.toggle('on', x === b); }); }
      function save() { r.note = document.getElementById('t').value; r.saved = true; ]] .. send("r") .. [[; }
    </script>]],
    function(b)
      closePanel()
      if b.skip or not (b.sensing or b.processing or b.responding) then return end
      local f = io.open(folder .. "/selfcheck.json", "w")
      if f then
        f:write(hs.json.encode({ sensing = b.sensing, processing = b.processing, responding = b.responding,
          note = b.note or "", at = os.time() }, true)); f:close()
      end
      -- If the review is already there, remake its page so your ratings show beside the review's.
      if hs.fs.attributes(folder .. "/review.json") then
        hs.task.new(PYTHON, nil, { HERE .. "/meeting_review.py", folder, "--page" }):start()
      end
      hs.alert.show("Saved. Your ratings will sit next to the review's.", 3)
    end, "How did you listen?")
  hs.timer.doAfter(900, function() if panel then closePanel() end end)
end


------------------------------------------------------------------ prep: goals for calls before they happen
-- you want to set a call's goal when it's booked, not in the scramble before it starts.
-- Meeting Prep.app (calcheck/, the only thing here with calendar access) lists your next 14 days of events into
-- Meetings/upcoming-calendar.json every 10 minutes. Prep you write goes in Meetings/prep.json, keyed by the
-- calendar event. When a call starts, the Record panel is filled in from it, and the review reads it.
local PREP_APP = HERE .. "/calcheck/Meeting Prep.app"
local CAL_FILE = MEET .. "/upcoming-calendar.json"
local PREP_FILE = MEET .. "/prep.json"
M.events, M.seen = {}, nil

local function readPrep() return hs.fs.attributes(PREP_FILE) and hs.json.read(PREP_FILE) or {} end
local function writePrep(t) hs.json.write(t, PREP_FILE, true, true) end

local function evTime(ev, which)                                    -- an event's start or end, as epoch seconds
  return ev[(which or "start") .. "_ts"]
end

local function when(ev)
  local t = evTime(ev)
  return t and (os.date("%a %d %b, %I:%M %p", t):gsub(" 0", " ")) or ev.start
end

-- The prep panel: what you want from the call, and anything to remember (questions, things to mention).
function M.prepFor(ev)
  local all = readPrep()
  local p = all[ev.id] or {}
  local function esc(x) return (x or ""):gsub("&", "&amp;"):gsub("<", "&lt;"):gsub('"', "&quot;") end
  local who = (#(ev.people or {}) > 0) and (" with " .. table.concat(ev.people, ", ")) or ""
  webPanel(420, 368, [[
    <h1>]] .. esc(ev.title) .. [[</h1>
    <p class="hint">]] .. esc(when(ev) .. who) .. [[</p>
    <p class="q">What do you want from this call?</p>
    <input id="g" maxlength="160" value="]] .. esc(p.goal) .. [[" placeholder="e.g. find out what Sam needs tested">
    <p class="q">Prep notes <span>· questions to ask, things to mention</span></p>
    <textarea id="n" style="height:96px" maxlength="800">]] .. esc(p.notes) .. [[</textarea>
    <div class="row"><button class="go" onclick="]] .. send("{save:true,goal:g.value,notes:n.value}") .. [[">Save</button>
      <button class="no" onclick="]] .. send("{save:false}") .. [[">Close</button></div>]],
    function(b)
      closePanel()
      if not b.save then return end
      local fresh = readPrep()
      fresh[ev.id] = { goal = b.goal or "", notes = b.notes or "", title = ev.title, start = ev.start, saved = os.time() }
      writePrep(fresh)
      hs.alert.show("Prep saved for " .. ev.title, 2)
    end, "Prep for this call")
end

-- Calls coming up, for the menu and for matching a call when recording starts.
local function upcoming()
  local out, now, seen = {}, os.time(), {}
  for _, ev in ipairs(M.events) do
    local t = evTime(ev)
    local key = (ev.title or "") .. "|" .. tostring(t)              -- the same call on two calendars shows once
    if ev.is_call and t and t > now - 3600 and not seen[key] then seen[key] = true; out[#out + 1] = ev end
  end
  table.sort(out, function(a, b) return evTime(a) < evTime(b) end)
  return out
end

-- The calendar event happening now (started up to 15 minutes ago or starting in the next 10), if any.
function M.eventNow()
  local now = os.time()
  for _, ev in ipairs(M.events) do
    local a, b = evTime(ev), evTime(ev, "end")
    if a and b and now >= a - 600 and now <= b then return ev end
  end
end

local function nudge(ev)
  local n = hs.notify.new(function() M.prepFor(ev) end, {
    title = "New call booked", subTitle = ev.title, informativeText = when(ev) .. ". Click to add your goal and prep notes.",
    withdrawAfter = 0 })
  local img = hs.image.imageFromPath(HERE .. "/icons/idle.png")
  if img then n:contentImage(img) end
  n:send(); table.insert(M.notes, n)
end

-- Refresh from the calendar. New calls (not seen before) get a nudge; the first run only takes note of them.
function M.refreshCalendar()
  if not hs.fs.attributes(PREP_APP) then return end
  hs.task.new("/usr/bin/open", function()
    local data = hs.json.read(CAL_FILE)
    if type(data) ~= "table" or data.error then return end
    M.events = data
    local state = hs.json.read(MEET .. "/upcoming-seen.json") or {}
    local first = next(state) == nil
    local fresh = {}
    for _, ev in ipairs(upcoming()) do
      if not state[ev.id] then
        state[ev.id] = ev.start
        if not first and not readPrep()[ev.id] then fresh[#fresh + 1] = ev end
      end
    end
    -- One booking gets its own nudge; a crowd (say, a calendar just connected) gets one summary instead.
    if #fresh > 0 and #fresh <= 3 then
      for _, ev in ipairs(fresh) do nudge(ev) end
    elseif #fresh > 3 then
      local n = hs.notify.new(nil, { title = #fresh .. " upcoming calls found",
        informativeText = "Face menu > Upcoming calls: prep, to add a goal to any of them.", withdrawAfter = 0 })
      n:send(); table.insert(M.notes, n)
    end
    hs.json.write(state, MEET .. "/upcoming-seen.json", true, true)
    -- An hour before a call with prep, a reminder of what you want from it.
    local now = os.time()
    for _, ev in ipairs(upcoming()) do
      local t, p = evTime(ev), readPrep()[ev.id]
      M.reminded = M.reminded or {}
      if t and p and (p.goal or "") ~= "" and t - now > 0 and t - now <= 3600 and not M.reminded[ev.id] then
        M.reminded[ev.id] = true
        local n = hs.notify.new(function() M.prepFor(ev) end, { title = "Coming up: " .. ev.title,
          subTitle = when(ev), informativeText = "Your goal: " .. p.goal, withdrawAfter = 0 })
        n:send(); table.insert(M.notes, n)
      end
    end
  end, { "-W", "-g", PREP_APP, "--args", CAL_FILE, "14" }):start()
end
M.calTimer = hs.timer.doEvery(600, M.refreshCalendar)
hs.timer.doAfter(20, M.refreshCalendar)

local function upcomingMenu()
  local items, prep = {}, readPrep()
  for i, ev in ipairs(upcoming()) do
    if i > 12 then break end
    local p = prep[ev.id]
    local mark = (p and (p.goal or "") ~= "") and "✓ " or "    "
    local tag = ev.invited and "  (video)" or ""                    -- a link or guests on the invite
    items[#items + 1] = { title = mark .. when(ev) .. " · " .. ev.title .. tag, fn = function() M.prepFor(ev) end }
  end
  if #items == 0 then
    items = { { title = hs.fs.attributes(CAL_FILE) and "No calls in the next two weeks" or "Calendar not read yet", disabled = true } }
  end
  table.insert(items, { title = "-" })
  table.insert(items, { title = "✓ means you've set a goal. Click any call to prep it.", disabled = true })
  return items
end

------------------------------------------------------------------ recording
local function setIcon(on)
  local D = dictation
  if D and D.menu then D.menu:setIcon(on and M.recIcon or D.faceIdle, false) end
end

local finish

function M.start(goal)
  if active then return end
  closePanel()
  goal = type(goal) == "string" and goal or ""
  local app = callApp()
  local folder = MEET .. "/" .. os.date("%Y-%m-%d %H%M ") .. app
  hs.fs.mkdir(MEET); hs.fs.mkdir(folder)
  local meta = io.open(folder .. "/meeting.json", "w")
  local ev = M.pendingEvent or (M.eventNow and M.eventNow())
  M.pendingEvent = nil
  local pre = ev and hs.fs.attributes(MEET .. "/prep.json") and (hs.json.read(MEET .. "/prep.json") or {})[ev.id] or {}
  if meta then meta:write(hs.json.encode({ started = os.time(), app = app, goal = goal, notes = pre.notes or "",
    event = ev and ev.title or "", people = ev and ev.people or {} })); meta:close() end
  active = { folder = folder, started = os.time(), lastSound = os.time() }
  local function exited() finish() end
  -- meetcap records both tracks on one clock.
  active.sys = hs.task.new(MEETCAP, function(_, code, _, err)
      if code ~= 0 and code ~= 15 and active and not active.stopping then
        hs.alert.show("To hear the other side, allow Hammerspoon under Screen & System Audio Recording, then record again.", 8)
        hs.execute("open 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'")
      end
      exited()
    end,
    function(_, out)                     -- "level 0.0123" once a second; "lv <them> <me>" five times a second
      for line in (out or ""):gmatch("[^\n]+") do
        local lvl = tonumber(line:match("^level ([%d%.]+)"))
        if lvl and lvl > 0.003 and active then active.lastSound = os.time() end
        local th, me = line:match("^lv ([%d%.]+) ([%d%.]+)")
        if th then pitch.level(tonumber(th), tonumber(me)) end
      end
      return true
    end, { folder .. "/them.wav", folder .. "/me.wav" })
  active.sys:start()
  pitch.start(folder)
  setIcon(true)
  hs.alert.show("Recording this meeting. Click your face in the menu bar to stop.", 4)
end

-- While recording: add or change the goal (the review reads it from meeting.json).
-- The goal box is a web panel, not hs.dialog.textPrompt. A textPrompt is modal: until it's answered, all of
-- Hammerspoon stops (dictation included) and the app can't be quit. Lost behind other windows, it looks like a hang.
local function goalPanel(hint, current, onSave)
  local v = (current or ""):gsub("&", "&amp;"):gsub('"', "&quot;"):gsub("<", "&lt;")
  webPanel(360, 176, [[
    <h1>This call's goal</h1><p class="hint">]] .. hint .. [[</p>
    <input id="g" maxlength="160" value="]] .. v .. [[" onkeydown="if(event.key==='Enter'){]] .. send("{go:true,goal:g.value}") .. [[}">
    <div class="row"><button class="go" onclick="]] .. send("{go:true,goal:g.value}") .. [[">Save</button>
      <button class="no" onclick="]] .. send("{go:false}") .. [[">Cancel</button></div>]],
    function(b)
      closePanel()
      if b.go then onSave(((b.goal or ""):gsub("^%s+", ""):gsub("%s+$", ""))) end
    end, "This call's goal")
end

function M.setGoal()
  if not active then return end
  local path = active.folder .. "/meeting.json"
  local meta = hs.json.read(path) or {}
  goalPanel("What do you want from this call? The review judges it against this.", meta.goal, function(text)
    meta.goal = text; hs.json.write(meta, path, true, true)
  end)
end

M.selfCheck = function(folder) selfCheck(folder) end

-- A goal for a call that's already happened: saved in meeting.json, then the review is redone against it.
function M.goalFor(folder)
  local path = folder .. "/meeting.json"
  local meta = hs.json.read(path) or {}
  goalPanel("What did you want from this call? The review will be redone against it (about a minute).", meta.goal,
    function(text)
      meta.goal = text
      hs.json.write(meta, path, true, true)
      if hs.fs.attributes(folder .. "/transcript.md") then
        hs.task.new(PYTHON, nil, { HERE .. "/meeting_review.py", folder, "--notify" }):start()
        hs.alert.show("Goal saved. Redoing the review; a notification will say when it's ready.", 4)
      end
    end)
end
M.currentPanel = function() return panel end             -- for testing the panels
M.closePanel = function() closePanel() end

-- Testing the pitch timer without a live call: replay a stretch of a recorded call in real time.
function M.pitchReplay(src, from, seconds, out)
  hs.fs.mkdir(out)
  pitch.start(out)
  M.replay = hs.task.new(PYTHON, function() pitch.stop() end, function(_, o)
    for line in (o or ""):gmatch("[^\n]+") do
      local th, me = line:match("^lv ([%d%.]+) ([%d%.]+)")
      if th then pitch.level(tonumber(th), tonumber(me)) end
    end
    return true
  end, { HERE .. "/pitch_replay.py", src, tostring(from), tostring(seconds), out })
  M.replay:start()
end
M.ask = function(asked) ask(M.start, asked) end

function M.stop()
  if not active or active.stopping then return end
  active.stopping = true
  for _, t in ipairs({ active.sys }) do if t and t:isRunning() then t:interrupt() end end
end

finish = function()
  local folder = active.folder
  pitch.stop()
  os.remove(folder .. "/them-live.raw")                              -- the live copy was only for the pitch timer
  active = nil
  setIcon(false)
  hs.alert.show("Meeting saved. Writing the transcript…", 3)
  selfCheck(folder)
  hs.task.new(PYTHON, function(code, out)
    if code == 0 then
      local path = (out or ""):gsub("%s+$", "")
      hs.notify.new(function() hs.execute("open '" .. path .. "'") end,
        { title = "Meeting transcript ready", informativeText = "Click to open. Notes: face menu > Recent meetings.",
          withdrawAfter = 0 }):send()
    else
      hs.alert.show("The transcript didn't finish. The recording is safe in your Meetings folder.", 6)
    end
  end, { HERE .. "/meeting_finish.py", folder }):start()
end

------------------------------------------------------------------ noticing a call
M.watch = hs.timer.doEvery(2, function()
  local now = os.time()
  if active then
    if not active.stopping and now - active.started > 60 and now - active.lastSound > QUIET_STOP then
      hs.alert.show("The call went quiet, so I stopped recording.", 4)
      M.stop()
    end
    return
  end
  local mic = hs.audiodevice.defaultInputDevice()
  local inUse = mic and mic:inUse()
  local dictating = dictation and dictation.busy and dictation.busy()
  if inUse and not dictating then
    micSince = micSince or now
    if not prompted and now - micSince >= ASK_AFTER then prompted = true; ask(M.start, true) end
  elseif not inUse then
    micSince, prompted = nil, false                                  -- the call ended: ask again next time
  end
end)

------------------------------------------------------------------ the menu
local function recent()
  local list = {}
  local iter, dir = hs.fs.dir(MEET)
  if iter then
    for name in iter, dir do
      if name:match("^%d%d%d%d%-%d%d%-%d%d") and hs.fs.attributes(MEET .. "/" .. name .. "/transcript.md") then
        table.insert(list, name)
      end
    end
  end
  table.sort(list, function(a, b) return a > b end)
  local items = {}
  for i = 1, math.min(#list, 8) do
    local folder = MEET .. "/" .. list[i]
    local y, mo, d, hh, mm, app = list[i]:match("^(%d+)%-(%d+)%-(%d+) (%d%d)(%d%d) (.*)$")
    -- Lua's os.date has no %-d or %-I (that crashed this menu once), so leading zeros come off by hand.
    local when = y and os.time({ year = y, month = mo, day = d, hour = hh, min = mm })
    local label = (when and os.date("%a %d %b, %I:%M %p", when):gsub(" 0", " ") or list[i]) .. " · " .. (app or "")
    table.insert(items, { title = label, menu = {
      { title = "Open transcript", fn = function() hs.execute("open '" .. folder .. "/transcript.md'") end },
      { title = "Write notes with Claude (copies a message to paste)", fn = function()
          hs.pasteboard.setContents('Write meeting notes for "' .. folder .. '/transcript.md": a short summary, the decisions, '
            .. 'and action items with who owns each. Save them as notes.md in the same folder and add them to my Latest folder as "Meeting, '
            .. label:gsub(" · .*", "") .. ' notes".')
          hs.alert.show("Copied. Paste it into a Claude session.")
        end },
      -- the listening scorecard (meeting_coach.py, free, on this Mac) and coaching on top of it.
      hs.fs.attributes(folder .. "/coach.md") and
        { title = "Listening scorecard", fn = function() hs.execute("open '" .. folder .. "/coach.md'") end }
        or { title = "Listening scorecard (not made for this one)", disabled = true },
      -- the call review page (meeting_review.py): feedback pinned to moments, with play buttons.
      hs.fs.attributes(folder .. "/review.html") and
        { title = "Call review", fn = function() hs.execute("open '" .. folder .. "/review.html'") end }
        or { title = "Make the call review (a few minutes)", fn = function()
          hs.task.new(HERE .. "/.venv/bin/python", nil, { HERE .. "/meeting_review.py", folder, "--notify" }):start()
          hs.alert.show("Reviewing the call. A notification will say when it's ready.")
        end },
      -- rate a past call, or give it a goal afterwards (the review is redone with the goal).
      { title = (hs.fs.attributes(folder .. "/selfcheck.json") and "Rate my listening again" or "Rate my listening"),
        fn = function() selfCheck(folder) end },
      { title = "Add or change this call's goal", fn = function() M.goalFor(folder) end },
      { title = "Coach me with Claude (copies a message to paste)", fn = function()
          hs.pasteboard.setContents('Coach me on my call in "' .. folder .. '/transcript.md". I am Me. Read the transcript, '
            .. 'and coach.md beside it (my listening scorecard, from published benchmarks). Then: '
            .. '(1) rate my listening 1 to 7 on each of the three parts of the Active-Empathic Listening Scale '
            .. '(Bodie 2011): sensing (picking up what they said and what they meant), processing (remembering and '
            .. 'connecting it), and responding (showing them I understood), quoting the moments, with their times, '
            .. 'behind each score; (2) how I presented myself and my ideas: where I was clear, where I rambled, hedged '
            .. 'or undersold myself; count my reflections against my questions as the MITI coding manual does (a reflection gives back '
            .. 'what they said or meant; 1 per question is beginning proficiency, 2 is competent) and quote my best and my weakest; '
            .. '(3) the follow-up questions I missed, built on what the other person actually said; '
            .. '(4) a tighter version of the main thing I explained about my work, in my own voice; (5) three things '
            .. 'to do on my next call. Be direct and specific, no flattery. Save it as coaching.md in the same folder '
            .. 'and add it to my Latest folder as "Meeting, ' .. label:gsub(" · .*", "") .. ' coaching".')
          hs.alert.show("Copied. Paste it into a Claude session.")
        end },
    } })
  end
  if #items == 0 then items = { { title = "No meetings yet", disabled = true } } end
  return items
end

function M.menuItems()
  -- Built item by item: a missing item left as a gap (nil) in the list would cut off everything after it.
  local items = {}
  local function add(x) if x then items[#items + 1] = x end end
  add(active and { title = "● Recording a meeting · click to stop", fn = M.stop }
    or { title = "Record a meeting now", fn = function() ask(M.start, false) end })
  if active then add({ title = "Set this call's goal", fn = M.setGoal }) end
  add({ title = "Pitch timer during calls: " .. (pitch.enabled() and "on" or "off"), fn = pitch.toggle })
  add({ title = "Upcoming calls: prep", menu = upcomingMenu() })
  add({ title = "Recent meetings", menu = recent() })
  if hs.fs.attributes(MEET .. "/calls.html") then
    add({ title = "All my calls: grades and trends", fn = function() hs.execute("open '" .. MEET .. "/calls.html'") end })
  end
  add({ title = "Open my Meetings folder", fn = function() hs.execute("open '" .. MEET .. "'") end })
  return items
end

------------------------------------------------------------------ setup
M.recIcon = (function()
  local img = hs.image.imageFromPath(HERE .. "/icons/recording.png")
  return img and img:setSize({ w = 26, h = 26 }) or nil
end)()
-- when a call review finishes, meeting_review.py leaves "review-new" in the meeting's folder. This
-- turns it into a notification: the grade, the call and the verdict. Click it for the review; "All calls" opens
-- the history page. A review that couldn't run (Claude signed out) gets a notification saying what to do.
M.notes, M.seenProblems = {}, {}
function M.reviewReady(folder)
  local r = hs.json.read(folder .. "/review.json") or {}
  local f, page = io.open(folder .. "/review.html"), ""
  if f then page = f:read("*a"); f:close() end
  local letter = page:match('class="letter">([^<]+)<') or ""
  local n = hs.notify.new(function(note)
    if note:activationType() == hs.notify.activationTypes.actionButtonClicked then
      hs.execute("open '" .. MEET .. "/calls.html'")
    else
      hs.execute("open '" .. folder .. "/review.html'")
    end
  end, { title = "Call review ready" .. (letter ~= "" and (" · " .. letter) or ""),
         subTitle = r.call_title or "", informativeText = r.verdict or "Click to open it.",
         hasActionButton = true, actionButtonTitle = "All calls", withdrawAfter = 0 })
  local img = hs.image.imageFromPath(HERE .. "/icons/idle.png")
  if img then n:contentImage(img) end
  n:send()
  table.insert(M.notes, n)                                  -- kept, so a click still reaches it later
end
M.reviewWatch = hs.pathwatcher.new(MEET, function(paths)
  for _, p in ipairs(paths) do
    if p:match("/review%-new$") and hs.fs.attributes(p) then
      os.remove(p)
      M.reviewReady((p:gsub("/review%-new$", "")))
    elseif p:match("/review%-problem%.txt$") and hs.fs.attributes(p) and not M.seenProblems[p] then
      M.seenProblems[p] = true
      local f = io.open(p); local why = f and f:read("*a") or ""; if f then f:close() end
      hs.notify.new(nil, { title = "Call review couldn't run", informativeText = why, withdrawAfter = 0 }):send()
    end
  end
end):start()

hs.fs.mkdir(MEET)
hs.execute("find '" .. MEET .. "' \\( -name '*.wav' -o -name 'call.m4a' \\) -mtime +30 -delete")   -- audio is kept 30 days (your pick)
return M
