-- ftl_bench dev script (M2 turn-based closed loop). HOT-RELOADABLE: deployed to
-- the FTL user folder and re-run live by the bootstrap (data/bridge.lua) when a
-- reload marker appears. Defines _G.ftl_bench_tick; persistent loop state lives in
-- _G.ftl_bench_state so it survives reloads.
--
-- Pause model: gui.bPaused only (FTL's real pause / spacebar). FPS.SpeedFactor is
-- %immutable in the Lua binding (live-confirmed "This variable is immutable") so we
-- must NOT write it.

local json = _G.json
local S = _G.ftl_bench_state or {}
_G.ftl_bench_state = S
S.frame_counter    = S.frame_counter or 0
S.frame_budget     = S.frame_budget or 0
S.last_applied_seq = S.last_applied_seq      -- nil until first action
S.err_cooldown     = S.err_cooldown or 0

local function log_err(msg)
  if S.err_cooldown > 0 then return end
  S.err_cooldown = 120
  print("[ftl_bench] " .. msg)
end

------------------------------------------------------------------
-- Action dispatchers (verified bindings only)
------------------------------------------------------------------

local function apply_set_system_power(mgr, act)
  local sys = mgr:GetSystem(act.system_id)
  if not sys then return end
  local target = act.level or 0
  local current = sys.powerState.first
  local guard = 0
  while current < target and guard < 16 do
    sys:IncreasePower(1, false)
    current = sys.powerState.first
    guard = guard + 1
  end
  guard = 0
  while current > target and guard < 16 do
    sys:DecreasePower(false)
    current = sys.powerState.first
    guard = guard + 1
  end
end

local function apply_move_crew(mgr, act)
  local list = mgr.vCrewList
  if not list then return end
  local id = act.crew_id
  if id == nil or id < 0 or id >= list:size() then return end
  local crew = list[id]
  if not crew then return end
  local slot = act.slot_id
  if slot == nil then slot = -1 end
  crew:MoveToRoom(act.room_id, slot, false)
end

local function dispatch_actions(actions)
  local mgr = Hyperspace.ships.player
  if not mgr then return end
  for _, act in ipairs(actions or {}) do
    if act.type == "set_system_power" then
      apply_set_system_power(mgr, act)
    elseif act.type == "move_crew" then
      apply_move_crew(mgr, act)
    end
  end
end

------------------------------------------------------------------
-- Pause (bPaused only)
------------------------------------------------------------------

local function set_frozen(frozen)
  local gui = Hyperspace.App and Hyperspace.App.gui
  if gui then gui.bPaused = frozen end
end

------------------------------------------------------------------
-- Observation (schema_version 2: + last_action_seq, live paused)
------------------------------------------------------------------

local function write_observation()
  local ok, err = pcall(function()
    local obs = _G.ftl_bench.build_observation(S.frame_counter)
    obs.schema_version  = 2
    obs.last_action_seq = S.last_applied_seq
    local gui = Hyperspace.App and Hyperspace.App.gui
    obs.paused = (gui ~= nil and gui.bPaused) or false
    Hyperspace.write_json_observation(json.encode(obs))
  end)
  if not ok then log_err("observation error: " .. tostring(err)) end
end

------------------------------------------------------------------
-- Per-tick state machine
------------------------------------------------------------------

_G.ftl_bench_tick = function()
  S.frame_counter = S.frame_counter + 1
  if S.err_cooldown > 0 then S.err_cooldown = S.err_cooldown - 1 end

  local gui = Hyperspace.App and Hyperspace.App.gui
  if not gui then return end

  -- Only gate during an actual run; at the menu/hangar, stream without freezing.
  local world = Hyperspace.App.world
  local in_game = (world ~= nil) and world.bStartedGame or false
  if not in_game then
    S.frame_budget = 0
    write_observation()
    return
  end

  if S.frame_budget > 0 then
    S.frame_budget = S.frame_budget - 1
    if S.frame_budget == 0 then
      set_frozen(true)
      write_observation()
    end
    return
  end

  set_frozen(true)

  local ok, action_str = pcall(Hyperspace.read_json_action)
  if ok and action_str and action_str ~= "" then
    local dok, action = pcall(json.decode, action_str)
    if dok and type(action) == "table" and action.seq ~= nil
       and (S.last_applied_seq == nil or action.seq > S.last_applied_seq) then
      local aok, aerr = pcall(dispatch_actions, action.actions)
      if not aok then log_err("dispatch error: " .. tostring(aerr)) end
      S.last_applied_seq = action.seq
      S.frame_budget = action.advance_frames or 30
      if S.frame_budget > 0 then
        set_frozen(false)
        return
      end
    end
  end

  write_observation()
end

print("[ftl_bench] dev script loaded (M2 turn-based loop)")
