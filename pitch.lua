-- The pitch timer. During a recorded call, it listens for the other person asking an open question
-- ("what are you working on?", "tell me about...", "how does it work?") and puts a one-minute countdown at the
-- top of the screen, near the camera, from the moment you start answering. Amber with 15 seconds left, red at
-- zero, then it counts the time over. It stops when they take the floor or you pause, flashes your time, and
-- logs the answer in the call's pitches.json for the review.
--
-- Everything is on this Mac: meetcap reports both sides' loudness five times a second ("lv <them> <me>") and keeps
-- them-live.raw (the call side as it arrives); when they finish speaking, their last few seconds go to the
-- whisper-server dictation already keeps running. Loaded by meetings.lua.

local P = {}
local PORT = 8178                         -- the dictation speech server (dictation.lua)
local THEM_ON, ME_ON = 0.02, 0.015        -- loudness that counts as talking (measured on a real call)
local HERE = (debug.getinfo(1, "S").source:match("^@(.+)/[^/]+$"))
local SETTINGS = hs.json.read(HERE .. "/settings.json") or {}
local LIMIT = SETTINGS.answer_seconds or 60    -- seconds: the goal for an answer (settings.json)
local LIVE_RATE = 32000                   -- bytes a second in them-live.raw (16 kHz, 16-bit, mono)

local st                                  -- state for the call being recorded
local pill, pillTimer

------------------------------------------------------------------ is it an open question?
-- Questions that invite you to talk at length. Yes/no and logistics ("can you hear me?") don't count.
local OPEN = {
  "what are you working on", "what have you been working on", "what's new", "what is new", "what are you up to",
  "what have you been up to", "tell me about", "tell me more", "walk me through", "talk me through", "how does it work",
  "how does that work", "how do you", "how did you", "what do you do", "what are you doing", "what made you",
  "why did you", "what's your", "what is your", "how would you", "what would you", "how's it going with",
  "how is it going with", "what's the", "what does it", "can you explain", "could you explain", "explain",
  "what got you", "how are you thinking about", "what are you thinking", "where are you at with", "describe",
  "how did that go", "how did it go", "how was it", "how's that going", "how is that going", "what happened with",
  "what was it like", "what do you think about", "what do you think of", "what are your thoughts",
}
local CLOSED = {
  "can you hear me", "can you see", "are you there", "is that okay", "does that time work", "does that day work",
  "sound good", "right?",
  "you know?", "make sense?", "what time", "which day", "how are you doing", "how are you?",
}

function P.isOpen(text)
  local t = " " .. (text or ""):lower():gsub("[’']", "'"):gsub("%s+", " ") .. " "
  for _, c in ipairs(CLOSED) do
    if t:find(c, 1, true) and not t:find("tell me", 1, true) then return false end
  end
  for _, o in ipairs(OPEN) do
    if t:find(o, 1, true) then return true, o end
  end
  return false
end

------------------------------------------------------------------ the countdown on screen
local function fmt(s)
  s = math.floor(math.abs(s) + 0.5)
  return string.format("%d:%02d", s // 60, s % 60)
end

local function hidePill() if pillTimer then pillTimer:stop(); pillTimer = nil end; if pill then pill:delete(); pill = nil end end

local function drawPill(big, small, color)
  local f = hs.screen.mainScreen():frame()
  local w, h = 300, 74
  if not pill then
    pill = hs.canvas.new({ x = f.x + (f.w - w) / 2, y = f.y + 8, w = w, h = h })
    pill:level(hs.canvas.windowLevels.overlay)
    pill:clickActivating(false)
    pill:canvasMouseEvents(true, false, false, false)
    pill:mouseCallback(function() if st then st.dismissed = true end; hidePill() end)   -- click to hide
    pill:show()
  end
  pill:replaceElements(
    { type = "rectangle", action = "fill", fillColor = { hex = color, alpha = 1 },
      roundedRectRadii = { xRadius = 18, yRadius = 18 } },
    { type = "text", frame = { x = 0, y = 6, w = w, h = 40 },
      text = hs.styledtext.new(big, { font = { name = ".AppleSystemUIFontBold", size = 30 }, color = { white = 1 },
        paragraphStyle = { alignment = "center" } }) },
    { type = "text", frame = { x = 10, y = 46, w = w - 20, h = 22 },
      text = hs.styledtext.new(small, { font = { name = ".AppleSystemUIFont", size = 13 }, color = { white = 1, alpha = 0.9 },
        paragraphStyle = { alignment = "center", lineBreak = "truncateTail" } }) })
end

local function tick()
  if not st or not st.answering then return end
  local now = hs.timer.secondsSinceEpoch()
  local left = LIMIT - (now - st.myStart)
  if st.dismissed then return end
  if left > 15 then drawPill(fmt(left), "Aim for one minute", "#2B1626")
  elseif left > 0 then drawPill(fmt(left), "Start landing it", "#A65B0D")
  else drawPill("+" .. fmt(-left), "Over a minute: hand it back", "#B3261E") end
end

------------------------------------------------------------------ logging an answer
local function save()
  if not st then return end
  hs.json.write({ answers = st.answers }, st.folder .. "/pitches.json", true, true)
end

local function finish(endAt, why)
  if not st or not st.answering then return end
  st.answering = false
  local secs = endAt - st.myStart
  if secs >= 8 then                                                  -- a quick reply isn't a pitch
    table.insert(st.answers, { question = st.question, asked_at = st.qEnd - st.recStart,
      answer_from = st.myStart - st.recStart, seconds = math.floor(secs + 0.5), ended = why })
    save()
    local over = secs - LIMIT
    drawPill(fmt(secs), over > 0 and (fmt(over) .. " over a minute") or "Under a minute. Nice.", over > 0 and "#B3261E" or "#16653F")
    pillTimer = hs.timer.doAfter(4, hidePill)
  else
    hidePill()
  end
end

------------------------------------------------------------------ hearing their question
local function wavHeader(n)
  local function le(v, k) local s = "" for _ = 1, k do s = s .. string.char(v % 256); v = v // 256 end return s end
  return "RIFF" .. le(36 + n, 4) .. "WAVEfmt " .. le(16, 4) .. le(1, 2) .. le(1, 2) .. le(16000, 4) .. le(32000, 4)
    .. le(2, 2) .. le(16, 2) .. "data" .. le(n, 4)
end

local function askedWhat(secondsBack, onText)
  local f = io.open(st.folder .. "/them-live.raw", "rb")
  if not f then return end
  local size = f:seek("end")
  local n = math.min(size, math.floor(secondsBack * LIVE_RATE / 2) * 2)
  f:seek("set", size - n)
  local pcm = f:read(n); f:close()
  if not pcm or #pcm < LIVE_RATE then return end
  local b = "----pitch" .. tostring(math.random(1e9))
  local body = "--" .. b .. '\r\nContent-Disposition: form-data; name="response_format"\r\n\r\ntext\r\n'
    .. "--" .. b .. '\r\nContent-Disposition: form-data; name="file"; filename="q.wav"\r\nContent-Type: audio/wav\r\n\r\n'
    .. wavHeader(#pcm) .. pcm .. "\r\n--" .. b .. "--\r\n"
  hs.http.asyncPost("http://127.0.0.1:" .. PORT .. "/inference", body,
    { ["Content-Type"] = "multipart/form-data; boundary=" .. b },
    function(status, text) if status == 200 and st then onText(text or "") end end)
end

------------------------------------------------------------------ the live loop
function P.start(folder)
  hidePill()
  st = { folder = folder, recStart = hs.timer.secondsSinceEpoch(), answers = {},
         themOn = false, themStart = 0, themLast = 0, meOn = false, meStart = 0, meLast = 0, answering = false }
  st.ticker = hs.timer.doEvery(0.25, tick)
end

function P.stop()
  if not st then return end
  if st.answering then finish(st.meLast, "call ended") end
  if st.ticker then st.ticker:stop() end
  save()
  st = nil
  hs.timer.doAfter(5, hidePill)
end

function P.enabled()
  local v = hs.settings.get("pitchTimer")
  if v == nil then return SETTINGS.pitch_timer ~= false end      -- until switched in the menu, settings.json decides
  return v
end
function P.toggle() hs.settings.set("pitchTimer", not P.enabled()) end

-- Called five times a second with both sides' loudness.
function P.level(them, me)
  if not st or not P.enabled() then return end
  local now = hs.timer.secondsSinceEpoch()

  -- Your side: when you started talking, and when you last made a sound.
  if me > ME_ON then
    if not st.meOn and now - st.meLast > 0.6 then st.meStart = now end
    st.meOn, st.meLast = true, now
  elseif now - st.meLast > 0.6 then st.meOn = false end

  -- Their side: a turn starts after a pause and ends after 0.7 seconds of silence.
  if them > THEM_ON then
    if not st.themOn then
      if now - st.themLast > 0.7 then st.themStart = now end
      st.themOn = true
    end
    st.themLast = now
    -- They take the floor back (1.8 seconds of talking): your answer is over.
    if st.answering and now - st.themStart > 1.8 and st.themStart > st.myStart + 2 then finish(st.themStart, "they spoke") end
  elseif st.themOn and now - st.themLast > 0.7 then
    st.themOn = false
    local turn = st.themLast - st.themStart
    if turn >= 1.0 and not st.answering then
      local qEnd = st.themLast
      askedWhat(math.min(turn + 0.5, 12) + (now - st.themLast), function(text)
        local open = P.isOpen(text)
        if not open or not st or st.answering then return end
        st.question, st.qEnd, st.dismissed = text:gsub("^%s+", ""):gsub("%s+$", ""), qEnd, false
        -- You may already be answering by the time Whisper replies: start from when you began.
        local began = (st.meStart >= qEnd - 0.3) and st.meStart or nil
        if began then st.myStart, st.answering, st.pendingSince = began, true, nil; tick()
        else st.pendingSince = qEnd; drawPill("1:00", "Open question: aim for one minute", "#2B1626") end
      end)
    end
  end

  -- Waiting for you to start after an open question (up to 8 seconds).
  if st.pendingSince and not st.answering then
    if st.meOn and st.meStart >= st.pendingSince - 0.3 then
      st.myStart, st.answering, st.pendingSince = st.meStart, true, nil
    elseif now - st.pendingSince > 8 then st.pendingSince = nil; hidePill() end
  end

  -- You've stopped: four seconds without a sound ends the answer.
  if st.answering and now - st.meLast > 4 then finish(st.meLast, "paused") end
  if st.answering and now - st.myStart > 360 then finish(now, "six minutes") end
end

return P
