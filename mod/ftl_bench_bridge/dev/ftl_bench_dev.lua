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

-- M3 actions (thin wrappers over the new C++ bindings)
local function apply_jump(act)
  Hyperspace.benchmark_jump_to_beacon(act.beacon_index or 0)
end

local function apply_choose_event(act)
  Hyperspace.benchmark_choose_event(act.choice_index or 0)
end

local function apply_fire_weapon(act)
  Hyperspace.benchmark_fire_weapon(act.weapon_slot or 0,
                                   act.target_ship_id or 1,
                                   act.target_room_id or 0)
end

local function dispatch_actions(actions)
  local mgr = Hyperspace.ships.player
  for _, act in ipairs(actions or {}) do
    if act.type == "set_system_power" then
      if mgr then apply_set_system_power(mgr, act) end
    elseif act.type == "move_crew" then
      if mgr then apply_move_crew(mgr, act) end
    elseif act.type == "jump" then
      apply_jump(act)
    elseif act.type == "choose_event" then
      apply_choose_event(act)
    elseif act.type == "fire_weapon" then
      apply_fire_weapon(act)
    end
  end
end

-- M3 observation additions (hot-reloadable; patches the obs built by observation.lua)
local function add_m3_obs(obs)
  local world = Hyperspace.App and Hyperspace.App.world
  if not world then return end

  -- connected beacons reachable from the current location (jump targets)
  local sm = world.starMap
  if sm and sm.currentLoc and obs.map then
    local beacons = {}
    local connected = sm.currentLoc.connectedLocations
    for i = 0, connected:size() - 1 do
      local loc = connected[i]
      if loc then
        beacons[#beacons + 1] = {
          index = i, known = loc.known, visited = loc.visited,
          danger_zone = loc.dangerZone, boss = loc.boss,
          nebula = loc.nebula, has_event = (loc.event ~= nil),
        }
      end
    end
    obs.map.connected_beacons = beacons
  end

  -- current event choices (for choose_event) — read from the LIVE choiceBox,
  -- NOT world.baseLocationEvent (which can be a different/stale event).
  local gui = Hyperspace.App.gui
  if gui and gui.choiceBoxOpen then
    local cb = gui.choiceBox
    local choices = {}
    local text = ""
    if cb then
      local okt, mt = pcall(function() return cb.mainText end)
      if okt and type(mt) == "string" then text = mt end
      local ok, ev_choices = pcall(function() return cb:GetChoices() end)
      if ok and ev_choices then
        for i = 0, ev_choices:size() - 1 do
          local c = ev_choices[i]
          if c then
            local ctext = ""
            local okc, t = pcall(function() return c.text:GetText() end)
            if okc and type(t) == "string" then ctext = t end
            choices[#choices + 1] = { index = i, text = ctext }
          end
        end
      end
    end
    obs.event = { text = text, choices = choices }
  end

  -- enemy room ids (for weapon targeting): system_id -> room_id
  local enemy = Hyperspace.ships.enemy
  if enemy and obs.enemy_ship then
    local rooms = {}
    local sys_list = enemy.vSystemList
    if sys_list then
      for i = 0, sys_list:size() - 1 do
        local sys = sys_list[i]
        rooms[#rooms + 1] = { room_id = sys:GetRoomId(), system_id = sys:GetId() }
      end
    end
    obs.enemy_ship.rooms = rooms
  end

  -- player weapon charge (cooldown is a Pair {current, max}); patch into weapons[]
  local player = Hyperspace.ships.player
  if player and obs.player_ship and obs.player_ship.weapons then
    local wl = player:GetWeaponList()
    if wl then
      for i = 0, wl:size() - 1 do
        local w = wl[i]
        local pw = obs.player_ship.weapons[i + 1]
        if w and pw then
          local ok1, cur = pcall(function() return w.cooldown.first end)
          local ok2, mx = pcall(function() return w.cooldown.second end)
          if ok1 then pw.charge = cur end
          if ok2 then pw.charge_max = mx end
          pw.ready = (ok1 and ok2 and type(cur) == "number" and type(mx) == "number"
                      and mx > 0 and cur >= mx) or false
        end
      end
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
    obs.schema_version  = 3
    obs.last_action_seq = S.last_applied_seq
    local gui = Hyperspace.App and Hyperspace.App.gui
    obs.paused = (gui ~= nil and gui.bPaused) or false
    -- M3 fields are best-effort: never let them lose the base observation.
    local m3ok, m3err = pcall(add_m3_obs, obs)
    if not m3ok then log_err("m3 obs error: " .. tostring(m3err)) end
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
    -- Autonomy: let the harness start/continue a game from the menu (no click).
    local ok, action_str = pcall(Hyperspace.read_json_action)
    if ok and action_str and action_str ~= "" then
      local dok, action = pcall(json.decode, action_str)
      if dok and type(action) == "table" and action.seq ~= nil
         and (S.last_applied_seq == nil or action.seq > S.last_applied_seq) then
        for _, act in ipairs(action.actions or {}) do
          if act.type == "start_game" then
            if act.mode == "new" then
              S.starting_new = true       -- multi-step flow, driven below
              S.menu_throttle = 0
            else
              pcall(Hyperspace.benchmark_continue_game)
              S.starting_new = false
            end
          end
        end
        S.last_applied_seq = action.seq
      end
    end
    -- New game is a 3-click flow (New Game -> CONFIRM -> hangar Start); step it
    -- every ~25 ticks so each screen has time to transition before the next click.
    if S.starting_new then
      S.menu_throttle = (S.menu_throttle or 0) + 1
      if S.menu_throttle % 25 == 0 then
        pcall(Hyperspace.benchmark_advance_menu)
      end
    end
    write_observation()
    return
  end
  S.starting_new = false   -- in a run now; stop driving the menu

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
