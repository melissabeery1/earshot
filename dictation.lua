-- Hold Fn, talk, let go: the words are typed where the cursor is.
--. Everything runs on your Mac: ffmpeg records, whisper.cpp's whisper-server turns speech
-- into text with the model kept loaded, and this file tidies the text and pastes it. No AI service, $0.
-- Loaded by ~/.hammerspoon/init.lua. Reload after editing: Hammerspoon menu > Reload Config.

local HERE   = (debug.getinfo(1, "S").source:match("^@(.+)/[^/]+$"))   -- the folder this file is in
local MODEL  = HERE .. "/models/ggml-large-v3-turbo-q5_0.bin"
local VAD    = HERE .. "/models/ggml-silero-v5.1.2.bin"
local WARM   = HERE .. "/models/warm.wav"       -- "Testing one two three", made with the Mac's say command
local SERVER = "/opt/homebrew/bin/whisper-server"
local RECORDER = HERE .. "/dictrec/dictrec"    -- replaces ffmpeg, which lost your first half-second
local PORT   = 8178
local MIN_HOLD = 0.35        -- a shorter Fn press is a tap, not dictation
local TMP    = os.getenv("TMPDIR")          -- each clip is dictation-<n>.wav here, deleted once its words are back

local M = {}

-- First run: your word list and snippets start as copies of the examples.
for _, name in ipairs({ "words", "snippets" }) do
  if not hs.fs.attributes(HERE .. "/" .. name .. ".txt") then
    hs.execute("cp '" .. HERE .. "/" .. name .. ".example.txt' '" .. HERE .. "/" .. name .. ".txt'")
  end
end

-- Your names and words, so Whisper spells them right (edit words.txt, then reload).
local function words()
  local f = io.open(HERE .. "/words.txt", "r")
  if not f then return "" end
  local s = f:read("*a"); f:close()
  return (s:gsub("%s+$", ""))
end

------------------------------------------------------------------ the speech server
-- Exactly one server. A Hammerspoon reload used to leave the old one running beside the new, and a request
-- landing on the old one (its model swapped out of memory) took many seconds. So every load
-- first stops any server on this port, and a server only restarts itself if it is still the current one.
-- two servers were running again (one from 30 Oct, one from 10 Nov). Now every start clears the
-- port first, whatever the reason for starting.
-- Silence filter (--vad): silence used to come back as made-up sentences ("And I'll see you next time.").
-- Keep-alive: the graphics chip let go of the model after 3 idle minutes, so the first dictation after a break
-- took 3.5 seconds instead of 1. The model is now held, and a tiny test clip keeps it warm every 2.5 minutes.
local server
-- A plain stop isn't enough: the 30 Oct server ignored it and lived for two weeks. So ask, wait, then force.
local function killStrays()
  local pat = "'whisper-serve[r].*--port " .. PORT .. "'"   -- the [r] keeps it from matching its own shell
  hs.execute("pkill -f " .. pat .. "; sleep 0.5; pkill -9 -f " .. pat)
  hs.timer.usleep(200000)
end
local function startServer()
  if server and server:isRunning() then return end
  killStrays()
  local mine
  mine = hs.task.new(SERVER, function() if server == mine then hs.timer.doAfter(3, startServer) end end,
    { "-m", MODEL, "--host", "127.0.0.1", "--port", tostring(PORT), "-l", "en",
      "--vad", "-vm", VAD, "-vp", "200" })
  mine:setEnvironment({ GGML_METAL_RESIDENCY_KEEP_ALIVE_S = "86400", HOME = os.getenv("HOME"), PATH = "/opt/homebrew/bin:/usr/bin:/bin" })
  server = mine
  server:start()
end
killStrays()                                                      -- leftovers from an earlier load

------------------------------------------------------------------ the little pill on screen
local pill
local function show(text)
  if pill then pill:delete() end
  local f = hs.screen.mainScreen():frame()
  local w, h = 190, 40
  pill = hs.canvas.new({ x = f.x + (f.w - w) / 2, y = f.y + f.h - h - 28, w = w, h = h })
  pill:appendElements(
    { type = "rectangle", action = "fill", fillColor = { hex = "#3A1830", alpha = 0.92 }, roundedRectRadii = { xRadius = 20, yRadius = 20 } },
    { type = "text", text = hs.styledtext.new(text, { font = { name = ".AppleSystemUIFont", size = 15 },
      color = { hex = "#FBE1E7" }, paragraphStyle = { alignment = "center" } }), frame = { x = 0, y = 10, w = w, h = h } })
  pill:level(hs.canvas.windowLevels.overlay)
  pill:show()
end
local function hide() if pill then pill:delete(); pill = nil end end

------------------------------------------------------------------ tidying the words
local function tidy(t)
  t = t:gsub("%[BLANK_AUDIO%]", ""):gsub("%(.-%)", "")              -- Whisper's notes about silence or noises
  t = t:gsub("%s*\n%s*", " ")                                       -- Whisper's own line breaks; only a spoken "new line" makes one
  -- Ums and uhs, with the comma that usually follows them.
  for _, f in ipairs({ "[Uu]m+", "[Uu]h+", "[Uu]hm+", "[Ee]rm+", "[Hh]mm+" }) do
    t = t:gsub("%f[%a]" .. f .. "%f[%A],?%s*", "")
  end
  -- Saying punctuation. Whisper writes its own marks around the word,
  -- so those go with it. "Period" only counts at the very end or with a mark after it, so "a period of time" stays.
  local function mark(word, m)
    t = t:gsub("[,%.]?%s*%f[%a]" .. word .. "%f[%A][,%.]?", m == "\n" and m or m == "\n\n" and m or m .. " ")
  end
  mark("[Nn]ew paragraph", "\n\n"); mark("[Nn]ew line", "\n")
  mark("[Qq]uestion mark", "?"); mark("[Ee]xclamation [pm][oa][ir][nk]t?", "!"); mark("[Cc]omma", ",")
  t = t:gsub("[,%.]?%s*%f[%a][Pp]eriod[,%.]%s*", ". "):gsub("[,%.]?%s*%f[%a][Pp]eriod%.?%s*$", ".")
  t = t:gsub("[,%.]?%s*%f[%a][Ff]ull stop%f[%A][,%.]?", ". ")
  t = t:gsub("[ \t]+([,%.%?!])", "%1"):gsub("[ \t][ \t]+", " "):gsub("^%s+", ""):gsub("%s+$", "")
  t = t:gsub("\n[ \t]+", "\n"):gsub("[ \t]+\n", "\n")
  t = t:gsub(",%s*([%.%?!])", "%1")                                  -- "today, ." left behind
  t = t:gsub("([%.%?!])[%.,]+", "%1")
  t = t:gsub("^%l", string.upper)                                    -- capital after a removed "um"
  t = t:gsub("([%.%?!]%s+)(%l)", function(a, c) return a .. c:upper() end)
  t = t:gsub("(\n%s*)(%l)", function(a, c) return a .. c:upper() end)
  return t
end

local function paste(text)
  local before = hs.pasteboard.getContents()
  hs.pasteboard.setContents(text)
  hs.eventtap.keyStroke({ "cmd" }, "v", 0)
  hs.timer.doAfter(0.8, function() if before then hs.pasteboard.setContents(before) end end)   -- your clipboard comes back
  local log = io.open(HERE .. "/history.txt", "a")                   -- on this Mac only, in case a paste lands nowhere
  if log then log:write(os.date("%Y-%m-%d %H:%M  ") .. text .. "\n"); log:close() end
end

------------------------------------------------------------------ snippets: say a short phrase, get saved text
-- snippets.txt, one per line: "my website = https://example.com". The whole dictation has to be the
-- phrase (case and end punctuation don't matter), so a phrase inside a sentence is left alone.
local function snippet(text)
  local said = text:lower():gsub("[%p%s]+$", ""):gsub("^%s+", "")
  local f = io.open(HERE .. "/snippets.txt", "r")
  if not f then return nil end
  for line in f:lines() do
    local phrase, out = line:match("^%s*(.-)%s*=%s*(.-)%s*$")
    if phrase and phrase ~= "" and not phrase:match("^#") and phrase:lower() == said then
      f:close()
      return (out:gsub("\\n", "\n"))
    end
  end
  f:close()
end

------------------------------------------------------------------ stats: words and speed
local lastHeld = 0
local function logStats(words, secs)
  local f = io.open(HERE .. "/stats.csv", "a")
  if f then f:write(string.format("%s,%.1f,%d\n", os.date("%Y-%m-%d"), secs, words)); f:close() end
end
function M.weekStats()
  local since, words, secs = os.date("%Y-%m-%d", os.time() - 6 * 86400), 0, 0
  local f = io.open(HERE .. "/stats.csv", "r")
  if f then
    for line in f:lines() do
      local d, s, w = line:match("^([%d%-]+),([%d%.]+),(%d+)$")
      if d and d >= since then words = words + tonumber(w); secs = secs + tonumber(s) end
    end
    f:close()
  end
  local wpm = secs > 0 and math.floor(words / secs * 60 + 0.5) or 0
  return words, wpm
end

------------------------------------------------------------------ sending the recording to the server
local transcribe
function transcribe(WAV)
  local f = io.open(WAV, "rb")
  if not f then working = false; hide(); return end
  local audio = f:read("*a"); f:close()
  local b = "----dictation" .. tostring(math.random(1e9))
  local function field(n, v) return "--" .. b .. "\r\nContent-Disposition: form-data; name=\"" .. n .. "\"\r\n\r\n" .. v .. "\r\n" end
  local body = field("response_format", "text") .. field("prompt", words())
    .. "--" .. b .. "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
    .. audio .. "\r\n--" .. b .. "--\r\n"
  show("Writing…")
  hs.http.asyncPost("http://127.0.0.1:" .. PORT .. "/inference", body,
    { ["Content-Type"] = "multipart/form-data; boundary=" .. b },
    function(status, text)
      working = false
      hide()
      os.remove(WAV)                                                 -- the words are back, so the voice clip goes
      if status ~= 200 then
        startServer()
        hs.alert.show("Dictation is starting up. Try again in a few seconds.")
        return
      end
      text = tidy(text or "")
      if text == "" then return end
      local saved = snippet(text)
      if saved then paste(saved); return end
      local _, n = text:gsub("%S+", "")
      logStats(n, lastHeld)
      if M.polish then M.polish(text, function(out) paste(out .. " ") end)
      else paste(text .. " ") end
    end)
end

------------------------------------------------------------------ holding Fn, or double-tapping it for hands-free
-- Hold Fn: records until you let go. Double-tap Fn: keeps recording with you hands free until you tap Fn
-- once more (Escape throws it away). Hands-free stops by itself after five minutes.
local rec, started, cancelled, showTimer                              -- rec is true while the mic is recording
local latched, stopOnRelease, lastTap, latchTimer = false, false, 0, nil
local DOUBLE_TAP = 0.5
local clipNo = 0
local working = false                                                -- a clip is on its way to the server

-- The recorder stays running and waits for "start", "stop" or "cancel". After "stop" it keeps listening
-- 0.3 seconds more, so the last word isn't clipped, then says "done" and the clip goes to the server.
local recorder
local function startRecorder()
  if recorder and recorder:isRunning() then return end
  local mine
  mine = hs.task.new(RECORDER, function() if recorder == mine then recorder = nil end end,
    function(_, out)
      for line in (out or ""):gmatch("[^\n]+") do
        local clip = line:match("^done (.+)$")
        if clip then working = true; transcribe(clip)
        elseif line:match("^error") then hide(); hs.alert.show("Dictation couldn't use the microphone") end
      end
      return true
    end, {})
  recorder = mine
  recorder:start()
end
local function tell(cmd)
  startRecorder()
  recorder:setInput(cmd .. "\n")
end

local function begin()
  cancelled = false
  started = hs.timer.secondsSinceEpoch()
  rec = true
  clipNo = clipNo + 1
  tell("start " .. TMP .. "dictation-" .. clipNo .. ".wav")
  showTimer = hs.timer.doAfter(MIN_HOLD, function() show("● Listening"); if M.listening then M.listening(true) end end)   -- a quick tap never flashes the pill
end

local function finish(cancel)
  if not rec then return end
  if showTimer then showTimer:stop() end
  if latchTimer then latchTimer:stop(); latchTimer = nil end
  if M.listening then M.listening(false) end
  local held = hs.timer.secondsSinceEpoch() - started
  cancelled = cancel or (not latched and held < MIN_HOLD)
  latched, stopOnRelease = false, false
  lastHeld = held
  if cancelled then hide(); tell("cancel") else tell("stop") end
  rec = nil
end

local function latch()                                               -- second tap: keep listening, hands free
  if showTimer then showTimer:stop() end
  latched = true
  show("● Listening · tap Fn to stop")
  if M.listening then M.listening(true) end
  latchTimer = hs.timer.doAfter(300, function() finish(false) end)
end

M.tap = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged, hs.eventtap.event.types.keyDown }, function(e)
  if e:getType() == hs.eventtap.event.types.keyDown then
    if rec and latched and e:getKeyCode() == hs.keycodes.map.escape then finish(true)   -- Escape throws it away
    elseif rec and not latched then finish(true) end                 -- Fn plus another key is a shortcut, not dictation
    return false
  end
  local fn = e:getFlags().fn
  local others = e:getFlags().cmd or e:getFlags().alt or e:getFlags().ctrl or e:getFlags().shift
  local now = hs.timer.secondsSinceEpoch()
  if fn and not others then
    if latched then stopOnRelease = true                             -- the tap that ends hands-free
    elseif not rec then begin() end
  elseif not fn and rec then
    if latched then
      if stopOnRelease then finish(false) end
    elseif now - started < MIN_HOLD then                             -- a tap, not a hold
      if now - lastTap < DOUBLE_TAP then lastTap = 0; latch()
      else lastTap = now; finish(true) end
    else finish(false) end
  elseif others and rec and not latched then finish(true) end
  return false
end)

------------------------------------------------------------------ looking back: Control-Option-H
-- Every dictation, newest first, in a search box. Type to filter, Enter pastes it again where the cursor is.
local function history()
  local items, f = {}, io.open(HERE .. "/history.txt", "r")
  if f then
    for line in f:lines() do
      local when, text = line:match("^(%d+%-%d+%-%d+ %d+:%d+)  (.*)$")
      if text then table.insert(items, 1, { text = text, subText = when }) end
    end
    f:close()
  end
  if #items == 0 then hs.alert.show("Nothing dictated yet"); return end
  local chooser = hs.chooser.new(function(choice) if choice then paste(choice.text) end end)
  chooser:choices(items):searchSubText(true):placeholderText("Search everything you've dictated"):rows(12):show()
end
M.history = hs.hotkey.bind({ "ctrl", "alt" }, "h", history)

------------------------------------------------------------------ your face in the menu bar
-- Hammerspoon's hammer is hidden and this takes its place. Not a template image, so it keeps its pinks;
-- it gains a rose ring while you're talking. icons/idle.png is the menu bar icon; swap in your own.
local function icon(file)
  local img = hs.image.imageFromPath(HERE .. "/" .. file)
  return img and img:setSize({ w = 26, h = 26 }) or nil
end
M.faceIdle, M.faceListening = icon("icons/idle.png"), icon("icons/listening.png")

-- Highlight a word that came out wrong, choose this, and Whisper is told the right spelling from then on.
local function addWord()
  local before = hs.pasteboard.getContents()
  hs.pasteboard.clearContents()
  hs.eventtap.keyStroke({ "cmd" }, "c", 0)
  hs.timer.doAfter(0.3, function()
    local w = (hs.pasteboard.getContents() or ""):gsub("^%s+", ""):gsub("%s+$", "")
    if before then hs.pasteboard.setContents(before) end
    if w == "" or #w > 40 or w:find("\n") then hs.alert.show("Highlight a word or name first"); return end
    local f = io.open(HERE .. "/words.txt", "a")
    if f then f:write(", " .. w); f:close() end
    hs.alert.show("Added to your word list: " .. w)
  end)
end
M.addWord = addWord

-- What's new: the newest date's lines from whats-new.md; any line opens the whole running list.
local function whatsNew()
  local function openList() hs.execute("open -e '" .. HERE .. "/whats-new.md'") end
  local items, date = {}, nil
  local f = io.open(HERE .. "/whats-new.md")
  if f then
    for line in f:lines() do
      local heading = line:match("^## (%d.*)")
      if heading then
        if date then break end
        date = heading
        table.insert(items, { title = "Added " .. date, disabled = true })
      elseif date and line:match("^%- ") then
        table.insert(items, { title = line:sub(3), fn = openList })
      end
    end
    f:close()
  end
  table.insert(items, { title = "-" })
  table.insert(items, { title = "Everything installed so far", fn = openList })
  return items
end
M.whatsNew = whatsNew

hs.menuIcon(false)
M.menu = hs.menubar.new()
if M.menu then
  M.menu:setIcon(M.faceIdle, false)
  M.menu:setTooltip("Dictation: hold Fn and talk")
  M.menu:setMenu(function()
    local words, wpm = M.weekStats()
    local items = {
    { title = "Hold Fn and talk · double-tap Fn for hands-free", disabled = true },
    { title = string.format("This week: %s words%s", words, wpm > 0 and (" · about " .. wpm .. " a minute") or ""), disabled = true },
    { title = "-" },
    { title = "Search what I've dictated  (Control-Option-H)", fn = history },
    { title = "Add the highlighted word to my word list", fn = addWord },
    { title = "Edit my word list", fn = function() hs.execute("open -e '" .. HERE .. "/words.txt'") end },
    { title = "Edit my snippets", fn = function() hs.execute("open -e '" .. HERE .. "/snippets.txt'") end },
    { title = "-" },
    table.unpack(meetings and meetings.menuItems() or {}),
  }
  -- Meetings (meetings.lua) adds its own lines; the restart and settings lines stay last.
  local tail = {
    { title = "-" },
    { title = "What's new", menu = whatsNew() },
    { title = "Restart dictation", fn = hs.reload },
    { title = "Hammerspoon settings", fn = hs.openPreferences },
  }
  for _, item in ipairs(tail) do table.insert(items, item) end
  return items
  end)
end
M.listening = function(on) if M.menu then M.menu:setIcon(on and M.faceListening or M.faceIdle, false) end end
M.busy = function() return rec ~= nil end                            -- the meeting recorder skips its prompt while you dictate

-- Keep the model warm: every 2.5 minutes a 1.5-second test clip, skipped while you're dictating.
M.warm = hs.timer.doEvery(150, function()
  if rec or working then return end
  hs.task.new("/usr/bin/curl", nil, { "-s", "-m", "20", "-o", "/dev/null", "-F", "file=@" .. WARM,
    "-F", "response_format=text", "http://127.0.0.1:" .. PORT .. "/inference" }):start()
end)

startServer()
startRecorder()
M.tap:start()
hs.alert.show("Dictation ready: hold Fn and talk")
return M
