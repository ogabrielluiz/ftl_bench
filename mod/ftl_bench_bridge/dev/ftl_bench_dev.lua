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

-- M4 reproducible seeds: override the run seed at NewGame when one is requested.
-- Registered ONCE (the dev script is re-run on hot-reload; the guard prevents
-- accumulating duplicate callbacks). The handler reads the global each call.
if not _G.ftl_bench_seed_hook then
  _G.ftl_bench_seed_hook = true
  script.on_internal_event(Defines.InternalEvents.GET_RUN_SEED, function(customSeed, seed)
    if _G.ftl_bench_desired_seed ~= nil then
      return true, _G.ftl_bench_desired_seed
    end
    return customSeed, seed
  end)
end

------------------------------------------------------------------
-- Action dispatchers (verified bindings only)
------------------------------------------------------------------

local function apply_set_system_power(mgr, act)
  local sys = mgr:GetSystem(act.system_id)
  if not sys then return end
  local target = act.level or 0
  local current = sys.powerState.first
  -- Increase ALL needed bars in ONE call. IncreasePower(1) one-at-a-time fails on the
  -- weapons system: a single bar can't half-arm a multi-power weapon, so after the
  -- 1-power Artemis takes a bar the 2-power Burst Laser is never armed. IncreasePower
  -- (target-current) respects weapon-arming boundaries and powers both. If reactor-
  -- limited it stops short on its own; retry smaller as a fallback.
  if current < target then
    local ok = pcall(function() return sys:IncreasePower(target - current, false) end)
    local guard = 0
    while sys.powerState.first < target and guard < 16 do  -- fallback: 1 bar at a time
      if not sys:IncreasePower(1, false) then break end
      guard = guard + 1
    end
  end
  local guard = 0
  while sys.powerState.first > target and guard < 16 do
    sys:DecreasePower(false)
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
-- True only when it is SAFE to initiate a jump: there's a player ship, it's not
-- already warping, and the FTL drive has finished recharging.
-- ROOT CAUSE of the seed-11 beacon-3 freeze (found via `sample` of the hung process:
-- the game-loop thread was spinning in FTL's CommandGui::OnLoop): forcing
-- starMap.readyToTravel while the FTL drive was still charging -- e.g. jumping again
-- immediately after a flee -- puts the engine in an inconsistent warp state and it
-- spins forever. jump_timer.first < jump_timer.second means "still charging".
local function jump_ready(p)
  if not p or p.bJumping then return false end       -- never start a jump mid-warp
  -- The FTL-drive recharge (jump_timer) only gates jumps IN combat; out of combat the
  -- timer sits idle (e.g. 0/85) yet you can jump freely. Gating on it out of combat
  -- deadlocks (the jump is what charges it).
  local enemy = Hyperspace.ships and Hyperspace.ships.enemy
  if not enemy then return true end
  local ready = true
  pcall(function() ready = p.jump_timer.first >= p.jump_timer.second end)
  return ready
end

local function apply_jump(act)
  local p = Hyperspace.ships and Hyperspace.ships.player
  if not jump_ready(p) then return end       -- wait out the FTL-drive recharge
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
    elseif act.type == "leave_sector" then
      -- same FTL-drive guard as apply_jump: only leave when the drive is charged and
      -- we're not already warping (forcing it mid-warp/charging spins CommandGui::OnLoop)
      if jump_ready(mgr) then
        pcall(Hyperspace.benchmark_leave_sector)  -- exit beacon -> next sector
      end
    elseif act.type == "open_menu" then
      pcall(Hyperspace.benchmark_open_menu)
    elseif act.type == "menu_command" then
      pcall(Hyperspace.benchmark_set_menu_command, act.cmd or 0)
    elseif act.type == "confirm_menu" then
      pcall(Hyperspace.benchmark_confirm_menu)
    elseif act.type == "return_to_menu" then
      pcall(Hyperspace.benchmark_return_to_menu)
    end
  end
end

-- M3 observation additions (hot-reloadable; patches the obs built by observation.lua)
local function add_m3_obs(obs)
  local world = Hyperspace.App and Hyperspace.App.world
  if not world then return end

  -- jump_charged: is it safe to initiate a jump now? (recharged in combat / always OK out)
  pcall(function() obs.jump_charged = jump_ready(Hyperspace.ships and Hyperspace.ships.player) end)

  -- Per-weapon firing state, COMBAT-ONLY and not mid-warp (reading ProjectileFactory
  -- pointers during a jump teardown is the freeze class). required_power lets an agent
  -- tell the 2-power Burst Laser from the 1-power Artemis; fire_when_ready/has_target
  -- say whether a charged weapon will actually fire.
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    local ps = obs.player_ship
    if not (pl and en and ps and ps.weapons) or pl.bJumping then return end
    local wl = pl:GetWeaponList()
    for i = 0, wl:size() - 1 do
      local pf = wl[i]; local ow = ps.weapons[i + 1]
      if pf and ow then
        pcall(function() ow.required_power = pf.requiredPower end)
        pcall(function() ow.fire_when_ready = pf.fireWhenReady end)
        pcall(function() ow.has_target = (pf.currentShipTarget ~= nil) end)
      end
    end
  end)

  -- connected beacons reachable from the current location (jump targets).
  -- GUARD: skip the whole starMap read during a warp -- iterating currentLoc.
  -- connectedLocations while WorldManager rebuilds locations on arrival reads freed
  -- pointers and freezes WorldManager::OnLoop (the residual eval freeze, 2026-06-04).
  -- The agent never acts mid-warp, so missing this for the warp frames is harmless.
  local sm = world.starMap
  local _plj = Hyperspace.ships and Hyperspace.ships.player
  if sm and sm.currentLoc and obs.map and not (_plj and _plj.bJumping) then
    local beacons = {}
    local connected = sm.currentLoc.connectedLocations
    for i = 0, connected:size() - 1 do
      local loc = connected[i]
      if loc then
        local px, py
        pcall(function() px, py = loc.loc.x, loc.loc.y end)
        beacons[#beacons + 1] = {
          index = i, known = loc.known, visited = loc.visited,
          danger_zone = loc.dangerZone, boss = loc.boss,
          nebula = loc.nebula, has_event = (loc.event ~= nil),
          -- exit_beacon: jumping here advances to the next sector (the goal beacon).
          -- fleet: the rebel pursuit fleet has reached this beacon (deadly — avoid).
          exit_beacon = loc.beacon, new_sector = loc.newSector,
          quest = loc.questLoc, fleet = loc.fleetChanging,
          pos_x = px, pos_y = py,  -- map position (to navigate toward the exit)
        }
      end
    end
    obs.map.connected_beacons = beacons

    -- sector-wide context for navigation: the exit beacon's position (the goal),
    -- our current position, and whether FTL is showing the choose-next-sector map.
    pcall(function() obs.map.current_pos = { x = sm.currentLoc.loc.x, y = sm.currentLoc.loc.y } end)
    -- at_exit: standing on the sector exit beacon -> leave_sector can advance the sector
    pcall(function() obs.map.at_exit = sm.currentLoc.beacon end)
    -- exit_pos: scan sector locations for the exit beacon, but ONLY in a stable state.
    -- Iterating sm.locations during a jump/warp/sector-transition reads Location pointers
    -- that the engine is tearing down -> hangs the game loop (the freeze, found 2026-06-04).
    -- Guard on not-jumping + not choosing-a-new-sector; the exit is static within a sector.
    local pl_j = Hyperspace.ships and Hyperspace.ships.player
    if (not (pl_j and pl_j.bJumping)) and (not sm.bChoosingNewSector) then
    pcall(function()
      local locs = sm.locations
      for j = 0, locs:size() - 1 do
        local L = locs[j]
        if L and L.beacon then
          obs.map.exit_pos = { x = L.loc.x, y = L.loc.y }
          break
        end
      end
    end)
    end  -- close the not-jumping / not-choosing-sector guard around the exit_pos scan
    pcall(function() obs.map.choosing_new_sector = sm.bChoosingNewSector end)
    pcall(function() obs.map.out_of_fuel = sm.outOfFuel end)
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
            -- ChoiceText::text is a plain std::string (already resolved), not a TextString.
            local ctext = ""
            local okc, t = pcall(function() return c.text end)
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
    -- enemy weapons (so the agent knows when the enemy is about to fire)
    local ewl = enemy:GetWeaponList()
    if ewl then
      local ew = {}
      for i = 0, ewl:size() - 1 do
        local w = ewl[i]
        if w then
          local okc, cur = pcall(function() return w.cooldown.first end)
          local okm, mx = pcall(function() return w.cooldown.second end)
          ew[#ew + 1] = { slot = i, powered = w.powered,
                          charge = okc and cur or nil, charge_max = okm and mx or nil }
        end
      end
      obs.enemy_ship.weapons = ew
    end
  end

  -- incoming projectiles aimed at the player (danger info the agent uses to decide
  -- whether to brace/flee). COMBAT-ONLY and not mid-warp: iterating space.projectiles
  -- during a jump/teardown reads freed pointers and freezes the loop (2026-06-04). The
  -- guards keep it to a stable state where the projectile list isn't being torn down.
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if not (pl and en) or pl.bJumping then return end   -- only in active combat, not warping
    local space = world.space
    if not space then return end
    local projs = space.projectiles
    if not projs then return end
    local incoming = 0
    for i = 0, projs:size() - 1 do
      local p = projs[i]
      if p and p.targetId == 0 then incoming = incoming + 1 end
    end
    obs.incoming_projectiles = incoming
  end)

  -- in-game menu inspection (for return-to-menu work)
  local ok_mc, mc = pcall(Hyperspace.benchmark_menu_button_count)
  if ok_mc and type(mc) == "number" then
    obs.menu_button_count = mc
    local texts = {}
    for i = 0, mc - 1 do
      local okt, t = pcall(Hyperspace.benchmark_menu_button_text, i)
      texts[#texts + 1] = (okt and type(t) == "string") and t or "?"
    end
    obs.menu_buttons = texts
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

  -- enrich player systems with ion / repair / hack status (drives repair & power)
  pcall(function()
    if not (player and obs.player_ship and obs.player_ship.systems) then return end
    local sl = player.vSystemList
    if not sl then return end
    for i = 0, sl:size() - 1 do
      local sys = sl[i]
      local ps = obs.player_ship.systems[i + 1]
      if sys and ps then
        local oi, ion = pcall(function() return sys:Ioned() end)
        if oi then ps.ioned = ion end
        local onr, nr = pcall(function() return sys:NeedsRepairing() end)
        if onr then ps.needs_repair = nr end
        local oh, he = pcall(function() return sys.iHackEffect end)
        if oh and type(he) == "number" then ps.hacked = he > 0 end
      end
    end
  end)
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
    -- A reset_episode that has reached the menu: kick off a fresh seeded game.
    if S.resetting then
      _G.ftl_bench_desired_seed = S.reset_seed
      S.starting_new = true
      S.menu_throttle = 0
      S.resetting = false
    end
    -- Autonomy: let the harness start/continue a game from the menu (no click).
    local ok, action_str = pcall(Hyperspace.read_json_action)
    if ok and action_str and action_str ~= "" then
      local dok, action = pcall(json.decode, action_str)
      if dok and type(action) == "table" and action.seq ~= nil
         and (S.last_applied_seq == nil or action.seq > S.last_applied_seq) then
        for _, act in ipairs(action.actions or {}) do
          if act.type == "set_seed" then
            _G.ftl_bench_desired_seed = act.seed   -- nil clears it (random)
          elseif act.type == "start_game" then
            if act.seed ~= nil then _G.ftl_bench_desired_seed = act.seed end
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
    S.obs_fresh = false
    write_observation()
    return
  end
  S.starting_new = false   -- in a run now; stop driving the menu

  -- reset_episode: abandon this run back to the main menu (the menu-guard above
  -- then launches a fresh seeded game). Runs UNFROZEN so the transition plays out.
  if S.resetting then
    set_frozen(false)
    S.reset_throttle = (S.reset_throttle or 0) + 1
    if S.reset_throttle % 10 == 0 then
      if gui.choiceBoxOpen then
        -- Clear any (chained) event so the menu can open. Disabled choices (e.g.
        -- unaffordable "Hire for N scrap") are no-ops, so try the LAST choice first
        -- (almost always an available "leave/continue"), then cycle downward.
        local n = 4
        pcall(function() n = gui.choiceBox:GetChoices():size() end)
        if n < 1 then n = 1 end
        local c = (n - 1) - ((S.reset_choice or 0) % n)
        pcall(Hyperspace.benchmark_choose_event, c)
        S.reset_choice = (S.reset_choice or 0) + 1
      else
        pcall(Hyperspace.benchmark_return_to_menu)   -- open menu + select Main Menu
        pcall(Hyperspace.benchmark_confirm_menu)      -- confirm the "lose progress" warning
      end
    end
    S.obs_fresh = false
    write_observation()
    return
  end

  if S.frame_budget > 0 then
    S.frame_budget = S.frame_budget - 1
    if S.frame_budget == 0 then
      set_frozen(true)
      write_observation()        -- advance complete: state changed, rebuild
      S.obs_fresh = true
    end
    return
  end

  set_frozen(true)

  local applied = false
  local ok, action_str = pcall(Hyperspace.read_json_action)
  if ok and action_str and action_str ~= "" then
    local dok, action = pcall(json.decode, action_str)
    if dok and type(action) == "table" and action.seq ~= nil
       and (S.last_applied_seq == nil or action.seq > S.last_applied_seq) then
      local is_reset = false
      for _, act in ipairs(action.actions or {}) do
        if act.type == "reset_episode" then
          is_reset = true
          S.resetting = true
          S.reset_throttle = 0
          S.reset_seed = act.seed
        end
      end
      S.last_applied_seq = action.seq
      if not is_reset then
        local aok, aerr = pcall(dispatch_actions, action.actions)
        if not aok then log_err("dispatch error: " .. tostring(aerr)) end
        applied = true
        S.frame_budget = action.advance_frames or 30
        if S.frame_budget > 0 then
          set_frozen(false)
          S.obs_fresh = false      -- about to advance; rebuild fresh on re-freeze
          return
        end
      end
    end
  end

  -- Rebuild the observation ONLY on a state change (an action was applied) or the first
  -- frozen tick of this idle period -- not every idle frame. While the agent "thinks" the
  -- frozen state doesn't change; rebuilding (iterating volatile game collections) ~60x/sec
  -- was pure waste AND set up the next advance to spin (the residual freeze).
  if applied or not S.obs_fresh then
    write_observation()
    S.obs_fresh = true
  end
end

print("[ftl_bench] dev script loaded (M2 turn-based loop)")
