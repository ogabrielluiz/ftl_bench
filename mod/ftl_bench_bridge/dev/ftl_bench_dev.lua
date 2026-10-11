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
S.manual_fire      = S.manual_fire or {}      -- slot -> one-shot fire request

-- Minimum frames an advancing step runs before the hybrid pause may cut it short on a critical
-- event (taking a hit, a fire, a boarder). The old floor was 18 (~0.3s), so in combat the
-- took_damage check re-paused almost immediately every step — the agent fired once, ate one hit,
-- and was re-prompted, so a fight never flowed and weapons never resolved a kill. Raising the
-- floor lets each combat step play a real beat (set power/target, then let the volley land) before
-- handing control back. Setup actions whose own advance budget is already below this (power=20,
-- crew=30) are unaffected — they just run their short budget and re-pause as before. Tune here.
local MIN_STEP_FRAMES = 150

local function log_err(msg)
  if S.err_cooldown > 0 then return end
  S.err_cooldown = 120
  print("[ftl_bench] " .. msg)
end

local function put_scalar_if_present(t, key, fn)
  if not t or t[key] ~= nil then return false end
  local ok, v = pcall(fn)
  local tv = type(v)
  if ok and (tv == "number" or tv == "boolean" or tv == "string") then
    t[key] = v
    return true
  end
  return false
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

-- Shot-outcome feed: hook the engine's projectile events so the agent SEES whether ITS shots
-- LAND, get SHIELD-BLOCKED, or MISS (dodged). Without this it only sees enemy-hull deltas and
-- can't tell a whiff from a block -- the exact gap that made an agent dump 8 missiles into a
-- high-evasion drone. We tally OUR shots (projectile.ownerId == 0) vs the enemy (iShipId 1):
-- fired (PROJECTILE_FIRE) - hit (DAMAGE_AREA_HIT) - shield-blocked (SHIELD_COLLISION) = missed.
-- Registered ONCE (hot-reload guard). Callbacks do only scalar reads + a table append (safe)
-- and RETURN NOTHING -- DAMAGE_AREA_HIT/SHIELD_COLLISION are chain events where a truthy return
-- PREEMPTS damage, so returning nil keeps the chain (verified live: damage still applies).
if not _G.ftl_bench_shot_hooks then
  _G.ftl_bench_shot_hooks = true
  local function shots()
    S.shots = S.shots or { fired = 0, hit = 0, shields = 0, dmg = 0, log = {} }
    return S.shots
  end
  local function push(result, dmg)
    local sh = shots()
    sh.log[#sh.log + 1] = (dmg and { result = result, dmg = dmg }) or { result = result }
    while #sh.log > 8 do table.remove(sh.log, 1) end
  end
  script.on_internal_event(Defines.InternalEvents.PROJECTILE_FIRE, function(projectile, weapon)
    pcall(function()
      if projectile and projectile.ownerId == 0 then shots().fired = shots().fired + 1 end
    end)
  end)
  script.on_internal_event(Defines.InternalEvents.DAMAGE_AREA_HIT,
    function(ship, projectile, location, damage, friendlyFire)
      pcall(function()
        if projectile and projectile.ownerId == 0 and ship and ship.iShipId == 1 then
          local d = (damage and damage.iDamage) or 0
          local sh = shots(); sh.hit = sh.hit + 1; sh.dmg = sh.dmg + d; push("hit", d)
        end
      end)
    end)
  script.on_internal_event(Defines.InternalEvents.SHIELD_COLLISION,
    function(ship, projectile, damage, response)
      pcall(function()
        if projectile and projectile.ownerId == 0 and ship and ship.iShipId == 1 then
          shots().shields = shots().shields + 1; push("shields")
        end
      end)
    end)
end

-- On-screen action log: draw the agent's recent decisions as an overlay ON the FTL screen so a
-- human can WATCH what the agent is doing turn by turn (populated by record_action in
-- dispatch_actions; rolling list in S.action_log). Registered ONCE (hot-reload guard). The whole
-- draw is pcall-wrapped so a rendering error can NEVER crash the game loop.
if not _G.ftl_bench_render_hook then
  _G.ftl_bench_render_hook = true
  local function draw_overlay()
    if S.observation_mode == "visual-v1" then return end
    pcall(function()
      S.render_count = (S.render_count or 0) + 1   -- proves the render hook is firing
      local lines = S.action_log
      if not lines or #lines == 0 then return end
      local G = Graphics
      local x, y, lh, w = 14, 120, 16, 252
      local n = #lines
      G.CSurface.GL_DrawRect(x - 6, y - 6, x - 6 + w, y + n * lh + 6, G.GL_Color(0, 0, 0, 0.55))
      G.CSurface.GL_SetColor(G.GL_Color(0.40, 0.90, 1.0, 1.0))
      G.freetype.easy_print(10, x, y, "AGENT ACTIONS")
      G.CSurface.GL_SetColor(G.GL_Color(0.86, 0.92, 0.98, 1.0))
      for i = 1, n do
        G.freetype.easy_print(10, x, y + i * lh, lines[i])
      end
      G.CSurface.GL_SetColor(G.GL_Color(1, 1, 1, 1))   -- restore default draw color
    end)
  end
  -- pcall the registration so a render-API mismatch can't abort the whole dev-script load
  -- (which would silently revert every other obs field). Capture the error for diagnosis.
  local ok, err = pcall(function()
    script.on_render_event(Defines.RenderEvents.MOUSE_CONTROL, draw_overlay, function() end)
  end)
  if not ok then _G.ftl_bench_render_err = tostring(err) end
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

local function apply_native_bool(fn, reason_prefix, ...)
  if type(fn) ~= "function" then return false, reason_prefix .. "_unavailable" end
  local ok, accepted = pcall(fn, ...)
  if not ok then return false, reason_prefix .. "_failed" end
  if accepted ~= true then return false, reason_prefix .. "_refused" end
  return true
end

-- Native upgrade rules own the price, cap, UI legality and scrap deduction.
-- Never approximate prices or charge scrap independently of a successful upgrade.
local function apply_upgrade_system(act)
  local id = act.system_id
  if type(id) ~= "number" or id ~= math.floor(id) or id < 0 or id > 2147483647 then
    return false, "invalid_system_id"
  end
  return apply_native_bool(Hyperspace.benchmark_upgrade_system, "native_upgrade", id)
end

local function apply_set_distress(act)
  if type(act.enabled) ~= "boolean" then return false, "invalid_distress_enabled" end
  return apply_native_bool(Hyperspace.benchmark_set_distress, "native_fuel_recovery", act.enabled)
end

local function native_economy_state()
  if type(Hyperspace.benchmark_economy_state) ~= "function" then return nil end
  local ok, raw = pcall(Hyperspace.benchmark_economy_state)
  if not ok or type(raw) ~= "string" or raw == "" then return nil end
  local decoded, state = pcall(json.decode, raw)
  if decoded and type(state) == "table" and type(state.native_protocol) == "number" then
    -- The existing codec omits native null costs/reactor. Missing means unknown
    -- or unavailable; it must never imply a zero price or a free upgrade.
    return state
  end
  return nil
end

local function apply_move_crew(mgr, act)
  local list = mgr.vCrewList
  if not list then return false, "crew_unavailable" end
  local id = act.crew_id
  if type(id) ~= "number" or id ~= math.floor(id) or id < 0 or id >= list:size() then
    return false, "invalid_crew_id"
  end
  local crew = list[id]
  if not crew then return false, "crew_unavailable" end
  -- vCrewList includes hostile boarders physically aboard the player ship. Direct
  -- MoveToRoom bypasses the UI's controllability check, so enforce it before the
  -- native call. Ownership stays 0 for our crew while they board the enemy.
  if crew.iShipId ~= 0 then return false, "crew_not_player_owned" end
  local cok, controllable = pcall(function() return crew:GetControllable() end)
  if not cok or controllable ~= true then return false, "crew_not_controllable" end
  local alive_ok, alive = pcall(function()
    return not crew:IsDead() and not crew:OutOfGame() and crew.health.first > 0
  end)
  if not alive_ok or not alive then return false, "crew_not_alive" end
  local slot = act.slot_id
  if slot == nil then slot = -1 end
  local mok, moved = pcall(function() return crew:MoveToRoom(act.room_id, slot, false) end)
  if not mok then return false, "crew_move_failed" end
  if moved ~= true then return false, "crew_move_refused" end
  return true
end

-- M3 actions (thin wrappers over the new C++ bindings)
-- Navigation readiness comes from the ordinary native FTL button and timer,
-- including outside combat. A destroyed enemy can still have a pending death
-- event/reward; expose that fact without inventing a loot collection requirement.
local function native_navigation_state(economy)
  economy = economy or native_economy_state()
  local nav = economy and economy.navigation
  if not (economy and economy.native_protocol >= 5 and economy.beacon_navigation_version == 1
      and type(nav) == "table" and type(nav.can_jump) == "boolean"
      and type(nav.enemy_defeat_pending) == "boolean"
      and type(nav.drive_current) == "number" and type(nav.drive_max) == "number") then return nil end
  return nav
end

local function apply_jump(act)
  local index = act.beacon_index
  if type(index) ~= "number" or index < 0 or index ~= math.floor(index) then
    return false, "invalid_beacon"
  end
  local nav = native_navigation_state()
  if not nav then return false, "native_jump_unavailable" end
  if not nav.can_jump then return false, nav.reason or "native_jump_refused" end
  local app = Hyperspace.App
  local sm = app and app.world and app.world.starMap
  local ok, count = pcall(function() return sm.currentLoc.connectedLocations:size() end)
  if ok and index >= count then return false, "invalid_beacon" end
  return apply_native_bool(Hyperspace.benchmark_jump_to_beacon, "native_jump", index)
end

local function apply_leave_sector(mgr)
  local app = Hyperspace.App
  local sm = app and app.world and app.world.starMap
  local gui = app and app.gui
  if not mgr then return false, "player_unavailable" end
  if mgr.bJumping then return false, "mid_warp" end
  if sm and sm.bChoosingNewSector then return false, "transition_pending" end
  if gui and (gui.choiceBoxOpen or (gui.choiceBox and gui.choiceBox.bOpen)) then
    return false, "event_open"
  end
  if type(mgr.fuel_count) == "number" and mgr.fuel_count < 1 then return false, "no_fuel" end
  if not sm or not sm.currentLoc or not sm.currentLoc.beacon then return false, "not_at_exit" end
  local enemy = Hyperspace.ships and Hyperspace.ships.enemy
  local nav = native_navigation_state()
  if not nav then return false, "native_leave_unavailable" end
  if not nav.can_jump then return false, nav.reason or "native_leave_refused" end
  local hostile
  pcall(function() hostile = enemy and enemy._targetable.hostile end)
  if hostile == true and enemy.bDestroyed ~= true then return false, "enemy_present" end
  return apply_native_bool(Hyperspace.benchmark_leave_sector, "native_leave")
end
local function native_choice_type(choice)
  local ok, value = pcall(function() return choice.type end)
  if ok and type(value) == "number" and value == math.floor(value) then return value end
  return nil
end

local function selected_event_choice(cb)
  local ok, value = pcall(function() return cb.selectedChoice end)
  if ok and type(value) == "number" then return value end
  return nil
end

local function apply_choose_event(act)
  local gui = Hyperspace.App and Hyperspace.App.gui
  if not (gui and gui.choiceBoxOpen and gui.choiceBox) then return false, "event_closed" end
  local cb = gui.choiceBox
  local queued = selected_event_choice(cb)
  if queued ~= nil and queued >= 0 then
    return false, "event_selection_pending", queued
  end
  local index = act.choice_index
  if index == nil then index = 0 end
  -- The native bridge sends number keys 1..9. Never renumber the choices or
  -- dispatch an index that this input path cannot select.
  if type(index) ~= "number" or index ~= math.floor(index) or index < 0 or index > 8 then
    return false, "invalid_choice_index", selected_event_choice(cb)
  end
  local ok, choice = pcall(function()
    local choices = cb:GetChoices()
    if not choices or index >= choices:size() then return nil end
    return choices[index]
  end)
  if not ok then return false, "event_choices_unavailable", selected_event_choice(cb) end
  if not choice then return false, "invalid_choice_index", selected_event_choice(cb) end
  -- ChoiceBox::KeyDown rejects exactly type 1. Other types include ordinary
  -- and blue choices; the resolved native type already accounts for requirements.
  if native_choice_type(choice) == 1 then
    return false, "choice_disabled", selected_event_choice(cb)
  end
  local called = pcall(Hyperspace.benchmark_choose_event, index)
  local selected = selected_event_choice(cb)
  if not called then return false, "event_selection_failed", selected end
  -- KeyDown's boolean can report a handled key without selecting a choice.
  -- Only the queued native selectedChoice proves that this request was accepted.
  if selected == index then return true, nil, selected end
  local mode, open_time
  pcall(function() mode = Hyperspace.Settings.dialogKeys end)
  pcall(function() open_time = cb.openTime end)
  if mode == 0 then return false, "event_hotkeys_disabled", selected end
  if mode == 2 and type(open_time) == "number" and open_time < 0.3 then
    return false, "event_input_delay", selected
  end
  return false, "event_selection_refused", selected
end

local function weapon_charge(pf)
  local cur, mx = nil, nil
  pcall(function() cur = pf.cooldown.first end)
  pcall(function() mx = pf.cooldown.second end)
  return cur, mx
end

local function target_ship(ship_id)
  if ship_id == 0 then return Hyperspace.ships and Hyperspace.ships.player end
  return Hyperspace.ships and Hyperspace.ships.enemy
end

-- The native enemy pointer survives accepted surrender. Hostility is the same
-- scalar used by CombatControl::IsInCombat; absence is unknown, never hostile.
local function native_enemy_state(enemy)
  local state = {}
  if not enemy then return state end
  local function boolean(key, getter)
    local ok, value = pcall(getter)
    if ok and type(value) == "boolean" then state[key] = value end
  end
  boolean("hostile", function() return enemy._targetable.hostile end)
  boolean("destroyed", function() return enemy.bDestroyed end)
  boolean("jumping", function() return enemy.bJumping end)
  return state
end

local function enemy_target_refusal(enemy, state)
  if not enemy then return "enemy_absent" end
  state = state or native_enemy_state(enemy)
  if state.hostile == false then return "enemy_not_hostile" end
  if state.hostile ~= true then return "enemy_hostility_unknown" end
  if state.destroyed == true then return "enemy_destroyed" end
  if state.destroyed ~= false then return "enemy_state_unknown" end
  if state.jumping == true then return "enemy_jumping" end
  if state.jumping ~= false then return "enemy_state_unknown" end
  return nil
end

local function set_global_weapon_autofire(enabled)
  -- WeaponControl.autoFiring is immutable in SWIG. A native setter is optional;
  -- never silently rely on assigning that field. Per-slot flags are mutable.
  if type(Hyperspace.benchmark_set_weapon_autofire) == "function" then
    return pcall(Hyperspace.benchmark_set_weapon_autofire, enabled)
  end
  return false
end

local function fill_weapon_targets(pf, target, room, room_b)
  local need = 1
  pcall(function() need = pf:NumTargetsRequired() end)
  if not need or need < 1 then need = 1 end
  local ok, center = pcall(function() return target:GetRoomCenter(room) end)
  if not ok or not center then return end
  pcall(function()
    while pf.targets:size() > 0 do pf.targets:pop_back() end
    if room_b ~= nil then
      pf.targets:push_back(center)
      pf.targets:push_back(target:GetRoomCenter(room_b))
    else
      while pf.targets:size() < need do pf.targets:push_back(center) end
    end
  end)
end

local function clear_weapon_fire_state(pf)
  if not pf then return end
  pcall(function() pf.fireWhenReady = false end)
  pcall(function() pf.autoFiring = false end)
end

local function clear_manual_fire_slot(slot)
  if not S.manual_fire then return end
  S.manual_fire[tostring(slot)] = nil
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    local wl = pl and pl:GetWeaponList()
    clear_weapon_fire_state(wl and wl[slot])
  end)
end

local function clear_idle_weapon_fire_states()
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not pl or pl.bJumping then return end
    local wl = pl:GetWeaponList()
    if not wl then return end
    for i = 0, wl:size() - 1 do
      if not (S.manual_fire and S.manual_fire[tostring(i)] ~= nil) then
        clear_weapon_fire_state(wl[i])
      end
    end
  end)
end

local function cancel_unavailable_manual_fire()
  for key, req in pairs(S.manual_fire or {}) do
    if type(req) ~= "table" or ((req.ship_id or 1) ~= 0 and
       enemy_target_refusal(target_ship(req.ship_id or 1))) then
      clear_manual_fire_slot(tonumber(key))
    end
  end
end

local function arm_manual_fire_slot(slot, req)
  local pl = Hyperspace.ships and Hyperspace.ships.player
  local target = target_ship(req.ship_id or 1)
  if not (pl and target) or pl.bJumping then clear_manual_fire_slot(slot); return nil end
  if (req.ship_id or 1) ~= 0 and enemy_target_refusal(target) then
    clear_manual_fire_slot(slot); return nil
  end
  local wl = pl:GetWeaponList()
  local pf = wl and wl[slot]
  if not pf then clear_manual_fire_slot(slot); return nil end
  local powered = false
  pcall(function() powered = pf.powered end)
  if not powered then clear_manual_fire_slot(slot); return nil end

  set_global_weapon_autofire(false)
  fill_weapon_targets(pf, target, req.room or 0, req.room_b)
  pcall(function() pf.autoFiring = false end)
  pcall(function() pf.fireWhenReady = true end)
  return pf
end

local function update_manual_fire()
  if not S.manual_fire then return end
  set_global_weapon_autofire(false)
  clear_idle_weapon_fire_states()
  for key, req in pairs(S.manual_fire) do
    local slot = tonumber(key)
    if not slot or type(req) ~= "table" then
      S.manual_fire[key] = nil
    else
      -- Sample before rearming: the engine may reach full charge AND release in
      -- one frame, so a previous observation of exactly full charge is not needed.
      local pl = Hyperspace.ships and Hyperspace.ships.player
      local wl = pl and not pl.bJumping and pl:GetWeaponList()
      local pf = wl and wl[slot]
      local cur, mx = weapon_charge(pf)
      local projectile_id
      pcall(function() projectile_id = pf.lastProjectileId end)
      local hacked = false
      pcall(function() hacked = (pf.iHackLevel or 0) > 0 end)
      local released = (req.projectile_id ~= nil and projectile_id ~= nil
        and req.projectile_id ~= projectile_id)
        or (not hacked and type(cur) == "number" and type(req.last_charge) == "number"
          and cur + 0.05 < req.last_charge)
      if released then
        clear_manual_fire_slot(slot)
        pf = nil
      else
        pf = arm_manual_fire_slot(slot, req)
      end
      if pf then
        local cur, mx = weapon_charge(pf)
        if type(cur) == "number" and type(mx) == "number" and mx > 0 then
          if cur >= mx - 0.05 then req.seen_ready = true end
          if req.seen_ready and cur < mx * 0.75 then
            clear_manual_fire_slot(slot)
          else
            req.last_charge = cur
            req.max_charge = mx
          end
        end
      end
    end
  end
end

local function fire_request_context(slot, ship_id, room_a, room_b)
  local facts = {}
  local function refuse(reason) return nil, reason, facts end
  if type(slot) ~= "number" or slot < 0 or slot ~= math.floor(slot) then
    return refuse("invalid_weapon_slot")
  end
  if ship_id ~= 0 and ship_id ~= 1 then return refuse("invalid_target_ship") end
  for _, room in ipairs({room_a, room_b}) do
    if type(room) ~= "number" or room < 0 or room ~= math.floor(room) then
      return refuse("invalid_target_room")
    end
  end
  local pl = Hyperspace.ships and Hyperspace.ships.player
  if not pl then return refuse("player_ship_unavailable") end
  if pl.bJumping then return refuse("player_jumping") end
  if ship_id == 1 then
    local enemy = target_ship(ship_id)
    local state = native_enemy_state(enemy)
    local reason = enemy_target_refusal(enemy, state)
    facts.enemy_hostile = state.hostile
    facts.enemy_targetable = reason == nil
    if reason then return refuse(reason) end
  end
  local ok, weapon = pcall(function() return pl:GetWeaponList()[slot] end)
  if not ok or not weapon then return refuse("weapon_unavailable") end
  if weapon.powered ~= true then return refuse("weapon_unpowered") end
  if ship_id == 0 then
    local bomb_ok, bomb = pcall(function() return weapon.blueprint.typeName == "BOMB" end)
    if not bomb_ok or not bomb then return refuse("self_target_unsupported") end
  end
  return weapon, nil, facts
end

local function apply_fire_weapon(act)
  local slot = act.weapon_slot or 0
  local ship_id = act.target_ship_id or 1
  local room = act.target_room_id or 0

  -- Manual fire control: release this weapon once when charged, then idle. The C++ helper sets
  -- target state but also enables autofire; immediately turn autofire back off and keep only this
  -- slot's fireWhenReady asserted while it is pending. When the weapon charge resets, the shot or
  -- burst volley has released and the pending request is cleared.
  local weapon, reason, facts = fire_request_context(slot, ship_id, room)
  if not weapon then clear_manual_fire_slot(slot); return false, reason, facts end
  local accepted, reason = apply_native_bool(Hyperspace.benchmark_fire_weapon,
    "native_fire", slot, ship_id, room)
  if not accepted then clear_manual_fire_slot(slot); return false, reason, facts end
  S.manual_fire[tostring(slot)] = {
    ship_id = ship_id,
    room = room,
    last_charge = nil,
    max_charge = nil,
    seen_ready = false,
  }
  local pf = arm_manual_fire_slot(slot, S.manual_fire[tostring(slot)])
  -- The old native helper enables autofire on all slots. Neutralize every idle
  -- slot before the next simulation frame, including previously targeted guns.
  clear_idle_weapon_fire_states()
  if pf then
    local cur, mx = weapon_charge(pf)
    if type(cur) == "number" and type(mx) == "number" and mx > 0 then
      S.manual_fire[tostring(slot)].last_charge = cur
      S.manual_fire[tostring(slot)].max_charge = mx
      S.manual_fire[tostring(slot)].seen_ready = cur >= mx - 0.05
    end
    pcall(function() S.manual_fire[tostring(slot)].projectile_id = pf.lastProjectileId end)
  end
  return pf ~= nil, pf == nil and "weapon_unavailable" or nil, facts
end

-- Fire a BEAM weapon. Unlike apply_fire_weapon (one room center repeated, correct for a burst
-- laser), a beam needs TWO DISTINCT points: a swipe from room_a's center to room_b's center,
-- damaging every room/tile the segment crosses. The high-level WeaponControl::Fire path
-- (persistent target + global autofire) isn't Lua-bound, so we go through the C++ free fn; a
-- Lua top-up rewrites pf.targets to exactly [ca, cb] as belt-and-suspenders.
local function apply_fire_beam(act)
  local slot    = act.weapon_slot or 0
  local ship_id = act.target_ship_id or 1
  local room_a  = act.room_a or 0
  local room_b  = act.room_b
  if room_b == nil then room_b = room_a end          -- degenerate single-point beam (safe; no chaining)
  local weapon, reason, facts = fire_request_context(slot, ship_id, room_a, room_b)
  if not weapon then clear_manual_fire_slot(slot); return false, reason, facts end
  local is_beam = false
  pcall(function() is_beam = weapon.blueprint.typeName == "BEAM" end)
  if not is_beam then clear_manual_fire_slot(slot); return false, "weapon_not_beam", facts end
  local accepted, reason = apply_native_bool(Hyperspace.benchmark_fire_beam,
    "native_fire", slot, ship_id, room_a, room_b)
  if not accepted then clear_manual_fire_slot(slot); return false, reason, facts end
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    local target = (ship_id == 0) and pl or (Hyperspace.ships and Hyperspace.ships.enemy)
    if not (pl and target) then return end
    local pf = pl:GetWeaponList()[slot]
    if not pf or not pf.powered then return end
    if not pf.blueprint or pf.blueprint.typeName ~= "BEAM" then return end
    local ca = target:GetRoomCenter(room_a)
    local cb = target:GetRoomCenter(room_b)
    while pf.targets:size() > 0 do pf.targets:pop_back() end
    pf.targets:push_back(ca)
    pf.targets:push_back(cb)
    S.manual_fire[tostring(slot)] = { ship_id = ship_id, room = room_a, room_b = room_b }
    local cur, mx = weapon_charge(pf)
    local req = S.manual_fire[tostring(slot)]
    req.last_charge, req.max_charge = cur, mx
    pcall(function() req.projectile_id = pf.lastProjectileId end)
    req.seen_ready = type(cur) == "number" and type(mx) == "number" and cur >= mx - 0.05
    arm_manual_fire_slot(slot, req)
  end)
  clear_idle_weapon_fire_states()
  local pending = S.manual_fire[tostring(slot)] ~= nil
  return pending, not pending and "weapon_unavailable" or nil, facts
end

-- ===================== special-system actions (researched via workflow) ===============

-- Cloaking (system id 10): flip bTurnedOn + (re)start the system's own timer, the way the
-- cloak box does. CloakingSystem::OnLoop then drives ship.bCloaked, the dodge bonus, and
-- untargetability, and auto-disables when the timer is Done(). Player's own ship, no target.
local function apply_cloak(mgr, act)
  local cloak = mgr.cloakSystem
  if not cloak then pcall(function() cloak = mgr:GetSystem(10) end) end
  if not cloak then return end                         -- ship has no cloaking system (buy it first)
  local already = false
  pcall(function() already = cloak.bTurnedOn end)
  if already then return end                           -- already cloaked: idempotent no-op
  local powered = false; pcall(function() powered = (cloak:GetEffectivePower() or 0) > 0 end)
  if not powered then return end
  local functioning = true; pcall(function() functioning = cloak:Functioning() end)
  if not functioning then return end
  local locked = false; pcall(function() locked = cloak:GetLocked() end)
  if locked then return end                            -- post-cloak cooldown
  pcall(function() cloak.bTurnedOn = true end)
  pcall(function()
    local dur = cloak.timer.maxTime
    if not dur or dur <= 0 then dur = 5 end
    cloak.timer:Start(dur)
  end)
end

-- Doors (system id 8): set door.bOpen directly (FTL has no Door::Close; Open() is just
-- bOpen=1, and OxygenSystem::OnLoop reads bOpen each frame to vent/equalize air). Lets the
-- agent vent oxygen (fight fires / suffocate boarders). ship_id 0=player(default), 1=enemy.
local function apply_set_doors(act)
  local ship_id = act.ship_id or 0
  local mgr = (ship_id == 0) and (Hyperspace.ships and Hyperspace.ships.player)
                              or  (Hyperspace.ships and Hyperspace.ships.enemy)
  if not mgr then return end
  pcall(function()
    if mgr.bJumping or mgr.bDestroyed then return end
    local ship = mgr.ship
    if not ship then return end
    local want_open = (act.open == true)
    local id_set = nil
    if act.door_ids and type(act.door_ids) == "table" and #act.door_ids > 0 then
      id_set = {}
      for _, d in ipairs(act.door_ids) do id_set[d] = true end
    end
    local room_sel = act.room_id
    local function toggle_list(list)
      if not list then return end
      for i = 0, list:size() - 1 do
        local door = list[i]
        if door then
          local locked, forced, hacked = false, false, false
          pcall(function() locked = door.lockedDown.running end)
          pcall(function() forced = door.forcedOpen.running end)
          pcall(function() hacked = (door.iHacked or 0) > 0 end)
          if not (locked or hacked) and not (forced and not want_open) then
            local pick
            if id_set then pick = id_set[door.iDoorId] == true
            elseif room_sel ~= nil then pick = (door.iRoom1 == room_sel) or (door.iRoom2 == room_sel)
            else pick = true end
            if pick then door.bOpen = want_open end
          end
        end
      end
    end
    toggle_list(ship.vDoorList)
    if act.include_airlocks then toggle_list(ship.vOuterAirlocks) end
  end)
end

-- Mind control (system id 14): queue an enemy crew member onto mindSystem.queuedCrew; the
-- MindSystem::OnLoop hook fires InitiateMindControl() next frame (the supported path, since
-- InitiateMindControl isn't Lua-bound). target_room_id = an enemy room that has crew.
local function apply_mind_control(act)
  local pl = Hyperspace.ships and Hyperspace.ships.player
  local en = Hyperspace.ships and Hyperspace.ships.enemy
  if not (pl and en) or pl.bJumping then return end
  local ms = pl.mindSystem
  if not ms then pcall(function() ms = pl:GetSystem(14) end) end
  if not ms then return end
  local ready = false
  pcall(function()
    ready = (ms:GetEffectivePower() > 0) and ms:Functioning() and (ms.iLockCount == 0)
            and (ms.controlTimer.first >= ms.controlTimer.second) and (not ms.bBlocked)
  end)
  if not ready then return end
  local room = act.target_room_id
  if room == nil then return end
  local cl = en.vCrewList
  if not cl then return end
  local want_id = act.target_crew_id
  for i = 0, cl:size() - 1 do
    local c = cl[i]
    if c then
      local ok, valid = pcall(function()
        return c.iRoomId == room and c.iShipId == 1 and not c:IsDead() and not c:OutOfGame()
           and not c:IsDrone() and not c:IsTelepathic() and not c.bMindControlled
      end)
      if ok and valid and (want_id == nil or i == want_id) then
        pcall(function() ms.queuedCrew:push_back(c) end)
        if want_id ~= nil then break end
      end
    end
  end
end

-- Backup Battery (system id 12): +N (level-scaled) temporary reactor power for a timed window.
-- Mirrors apply_cloak: flip bTurnedOn AND (re)start the system's own timer the way the battery
-- box does. BatterySystem::OnLoop then writes PowerManager.batteryPower each frame until the
-- timer is Done(), then auto-disables + goes on cooldown. A bare bTurnedOn=true is NOT enough
-- (OnLoop doesn't self-start the timer, so it flips straight back off). Fail closed if the
-- timer isn't initialized (maxTime<=0) rather than inventing a duration. Player ship, no target.
local function apply_battery(mgr, act)
  local bat = mgr.batterySystem
  if not bat then pcall(function() bat = mgr:GetSystem(12) end) end
  if not bat then return end                           -- no battery system (buy it first)
  local already = false
  pcall(function() already = bat.bTurnedOn end)
  if already then return end                            -- already discharging: idempotent no-op
  local powered = false; pcall(function() powered = (bat:GetEffectivePower() or 0) > 0 end)
  if not powered then return end                        -- depowered: grants nothing
  local functioning = true; pcall(function() functioning = bat:Functioning() end)
  if not functioning then return end                    -- destroyed
  local locked = false; pcall(function() locked = bat:GetLocked() end)
  if locked then return end                             -- post-discharge cooldown / hacked
  pcall(function() bat.bTurnedOn = true end)
  pcall(function()
    local dur = bat.timer.maxTime
    if not dur or dur <= 0 then bat.bTurnedOn = false; return end  -- not initialized: fail closed
    bat.timer:Start(dur)
  end)
end

-- Hacking (system id 15): deploy the player's hacking drone at an enemy SYSTEM and arm the
-- disruption. The heavy lifting (resolve the enemy system's room, aim the drone at the enemy
-- targetable, push it into space.drones, set queued/current system + bHacking) is done in C++
-- because SpaceManager::drones is unwritable from Lua. HackingDrone is a SpaceDrone (NOT a
-- CrewMember) -> outside the Rosetta crew-teardown SIGBUS class; the C++ side dedups the push
-- by pointer-scan. This wrapper only validates prerequisites and forwards the call.
local function apply_hack_system(act)
  local pl = Hyperspace.ships and Hyperspace.ships.player
  local en = Hyperspace.ships and Hyperspace.ships.enemy
  if not (pl and en) or pl.bJumping then return end     -- combat-only, never mid-warp
  local hs = pl.hackingSystem
  if not hs then pcall(function() hs = pl:GetSystem(15) end) end   -- 15 = SYS_HACKING
  if not hs then return end                             -- must BUY Hacking at a store first
  local powered = false
  pcall(function() powered = hs:Powered() end)
  if not powered then return end                        -- needs >= 1 power bar
  local target_sys = act.target_system_id or 0          -- enemy system id (default shields=0)
  local have = false
  pcall(function() have = en:HasSystem(target_sys) end)
  if not have then return end                           -- enemy lacks that system
  pcall(function() Hyperspace.benchmark_hack_system(target_sys) end)
end

-- Drone Control (system id 4): power a drone slot to deploy it. Deploying drives the engine's
-- real IncreasePower -> ForceIncreasePower -> PowerDrone -> SetDeployed chain (all bound), so
-- no C++ fn is needed. ROSETTA GUARD: SpaceDrone types (0 defense,1 combat,7 shield,hacking)
-- are NOT CrewMembers -> safe; CrewDrone types (2 repair,3 battle,4 boarder,5 ship-repair) are
-- the teardown-SIGBUS class and are refused unless act.allow_crew_drone (their teardown is
-- leak-covered by FTL_BENCH_STABILIZE_DRONES, but that path is unexercised, so default-refuse).
local CREW_DRONE_TYPES = { [2] = true, [3] = true, [4] = true, [5] = true }
local function consumes_part(t) return t ~= 0 end       -- only DEFENSE(0) deploys free

local function drone_deployable(ds, mgr, idx, allow_crew)
  local d = ds.drones[idx]
  if not d then return false end
  if d.bDead then return false end
  local t = d.type
  if CREW_DRONE_TYPES[t] and not allow_crew then return false end    -- ROSETTA GUARD
  if consumes_part(t) and (mgr:GetDroneCount() or 0) <= 0 then return false end  -- out of parts
  return true
end

local function apply_deploy_drone(mgr, act)
  if not mgr or mgr.bJumping then return end            -- never deploy mid-warp (teardown class)
  if not mgr:HasSystem(4) then return end               -- must be installed/bought
  local ds = mgr.droneSystem
  if not ds then return end
  local ok_fn = true; pcall(function() ok_fn = ds:Functioning() end)
  if not ok_fn then return end                          -- destroyed / hacked off
  local allow_crew = (act.allow_crew_drone == true)

  local n = 0; pcall(function() n = ds.drones:size() end)
  if n == 0 then return end

  -- Pick slot: explicit act.slot, else the FIRST unpowered deployable slot.
  local slot = act.slot
  if slot == nil then
    for i = 0, n - 1 do
      local d = ds.drones[i]
      if d and not d.powered and drone_deployable(ds, mgr, i, allow_crew) then slot = i; break end
    end
  end
  if slot == nil or slot < 0 or slot >= n then return end
  if not drone_deployable(ds, mgr, slot, allow_crew) then return end

  -- SLOT-ORDER GUARD: the engine powers slots in index order. Refuse to power past an earlier
  -- UNPOWERED slot the guard would refuse (else we'd deploy that crew drone first).
  for i = 0, slot - 1 do
    local d = ds.drones[i]
    if d and not d.powered and not drone_deployable(ds, mgr, i, allow_crew) then
      return
    end
  end

  -- Power to cover slots 0..slot (sum powerRequired). One shot first, bar-by-bar fallback.
  local cur = 0;  pcall(function() cur = ds.powerState.first end)
  local maxp = cur; pcall(function() maxp = ds:GetMaxPower() or cur end)
  local want = act.power_level
  if want == nil then
    local need = 0
    for i = 0, slot do
      local d = ds.drones[i]
      need = need + ((d and d.powerRequired) or 1)
    end
    want = need
  end
  if want > maxp then want = maxp end
  if cur < want then
    pcall(function() ds:IncreasePower(want - cur, false) end)
    local guard = 0
    while (ds.powerState.first or 0) < want and guard < 16 do
      if not ds:IncreasePower(1, false) then break end
      guard = guard + 1
    end
  end
end

-- Recall / power down the drone system (mirror of deploy). Safe for SpaceDrones.
local function apply_recall_drones(mgr, act)
  if not mgr or mgr.bJumping then return end
  if not mgr:HasSystem(4) then return end
  local ds = mgr.droneSystem
  if not ds then return end
  local guard = 0
  while (ds.powerState.first or 0) > 0 and guard < 16 do
    if not ds:DecreasePower(false) then break end
    guard = guard + 1
  end
end

-- Teleporter (system id 9): send (command=1) / recall (command=2) ORGANIC boarders to/from a
-- chosen ENEMY room. The room-targeted primitive (CompleteShip::InitiateTeleport) isn't bound
-- to Lua, so we call the C++ free fn, which also enforces the Rosetta guard (refuses to ship a
-- crew-drone -- only organic crew, freed via uncorrupted ~CrewAnimation, are safe). Lua just
-- gates on readiness. The recall room MATTERS (the HS reimpl recalls only that room), so it is
-- plumbed through; -1 lets the C++ resolve it to a room actually holding our boarders.
local function apply_teleport_crew(act)
  local p = Hyperspace.ships and Hyperspace.ships.player
  if not p or p.bJumping then return end
  local cmd = act.command or 1                          -- 1 = send, 2 = recall
  local tele = p:GetSystem(9)                           -- id 9 = SYS_TELEPORTER
  if not tele then return end
  local ts = p.teleportSystem
  local okc, charged = pcall(function() return ts and ts:Charged() end)
  if not (okc and charged) then return end
  local en = Hyperspace.ships and Hyperspace.ships.enemy
  if not en or en.bDestroyed or en.bJumping then return end
  local room = act.target_room_id
  if room == nil then room = -1 end                     -- send: -1 random; recall: -1 = C++ resolves
  pcall(Hyperspace.benchmark_teleport_crew, cmd, room)
end

-- Format one agent action into a short readable line for the on-screen log (field names match
-- the harness action builders in session.py).
local SYS_SHORT = { [0]="shields", [1]="engines", [2]="oxygen", [3]="weapons", [4]="drones",
  [5]="medbay", [6]="pilot", [7]="sensors", [8]="doors", [9]="teleport", [10]="cloak",
  [12]="battery", [14]="mind", [15]="hack" }
local function fmt_action(a)
  local t = a.type
  if t == "set_system_power" then
    return string.format("power %s -> %s", SYS_SHORT[a.system_id] or tostring(a.system_id), tostring(a.level))
  elseif t == "fire_weapon" then
    return string.format("fire w%s -> room %s", tostring(a.weapon_slot), tostring(a.target_room_id))
  elseif t == "fire_beam" then
    return string.format("beam w%s r%s->r%s", tostring(a.weapon_slot), tostring(a.room_a), tostring(a.room_b))
  elseif t == "jump" then return "jump -> beacon " .. tostring(a.beacon_index)
  elseif t == "leave_sector" then return "leave sector"
  elseif t == "choose_event" then return "event: choice " .. tostring(a.choice_index)
  elseif t == "move_crew" then
    return string.format("crew %s -> room %s", tostring(a.crew_id), tostring(a.room_id))
  elseif t == "store_buy" then return "buy item " .. tostring(a.index)
  elseif t == "store_sell" then return "sell item " .. tostring(a.index)
  elseif t == "upgrade_system" then return "upgrade " .. (SYS_SHORT[a.system_id] or tostring(a.system_id))
  elseif t == "upgrade_reactor" then return "upgrade reactor"
  elseif t == "wait_for_fuel" then return "wait for fuel"
  elseif t == "set_distress" then return a.enabled and "distress on" or "distress off"
  elseif t == "hack_system" then return "hack sys " .. tostring(a.target_system_id)
  elseif t == "mind_control" then return "mind-control room " .. tostring(a.target_room_id)
  elseif t == "teleport_crew" then return (a.command == 2) and "recall boarders" or ("board room " .. tostring(a.target_room_id))
  elseif t == "set_doors" then return (a.open and "open doors" or "close doors")
  elseif t == "deploy_drone" then return "deploy drone"
  elseif t == "recall_drones" then return "recall drones"
  elseif t == "cloak" then return "engage cloak"
  elseif t == "battery" then return "fire battery"
  else return tostring(t) end
end

-- Append an action to the rolling on-screen log (most recent last; the render hook draws it).
local function record_action(a)
  if not a or not a.type then return end
  S.action_log = S.action_log or {}
  S.action_count = (S.action_count or 0) + 1
  S.action_log[#S.action_log + 1] = string.format("%d. %s", S.action_count, fmt_action(a))
  while #S.action_log > 11 do table.remove(S.action_log, 1) end
end

local function dispatch_actions(actions)
  local mgr = Hyperspace.ships.player
  S.action_feedback = {}
  for action_index, act in ipairs(actions or {}) do
    pcall(record_action, act)   -- log to the on-screen overlay (never let logging break dispatch)
    if act.type == "set_system_power" then
      if mgr then apply_set_system_power(mgr, act) end
    elseif act.type == "move_crew" then
      local moved, reason = false, "player_ship_unavailable"
      if mgr then moved, reason = apply_move_crew(mgr, act) end
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "move_crew", crew_id = act.crew_id,
        room_id = act.room_id, status = moved and "applied" or "rejected", reason = reason,
      }
    elseif act.type == "jump" then
      local accepted, reason = apply_jump(act)
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "jump", beacon_index = act.beacon_index,
        status = accepted and "applied" or "rejected", reason = reason,
      }
    elseif act.type == "choose_event" then
      local selected, reason, selected_choice = apply_choose_event(act)
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "choose_event", choice_index = act.choice_index or 0,
        status = selected and "applied" or "rejected", reason = reason,
        selected_choice = selected_choice,
      }
    elseif act.type == "fire_weapon" then
      local accepted, reason, facts = apply_fire_weapon(act)
      facts = facts or {}
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "fire_weapon", weapon_slot = act.weapon_slot or 0,
        target_ship_id = act.target_ship_id or 1, target_room_id = act.target_room_id or 0,
        status = accepted and "applied" or "rejected", reason = reason,
        enemy_hostile = facts.enemy_hostile, enemy_targetable = facts.enemy_targetable,
        queued = accepted == true,
      }
    elseif act.type == "leave_sector" then
      local accepted, reason = apply_leave_sector(mgr)
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "leave_sector",
        status = accepted and "applied" or "rejected", reason = reason,
      }
    elseif act.type == "store_buy" then
      pcall(Hyperspace.benchmark_store_buy, act.index or 0)   -- buy store item #index
    elseif act.type == "store_sell" then
      pcall(Hyperspace.benchmark_store_sell, act.index or 0)  -- sell player item #index
    elseif act.type == "upgrade_system" then
      local accepted, reason = apply_upgrade_system(act)
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "upgrade_system", system_id = act.system_id,
        status = accepted and "applied" or "rejected", reason = reason,
      }
    elseif act.type == "upgrade_reactor" then
      local accepted, reason = apply_native_bool(Hyperspace.benchmark_upgrade_reactor, "native_upgrade")
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "upgrade_reactor",
        status = accepted and "applied" or "rejected", reason = reason,
      }
    elseif act.type == "wait_for_fuel" then
      local accepted, reason = apply_native_bool(Hyperspace.benchmark_wait_for_fuel, "native_fuel_recovery")
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "wait_for_fuel",
        status = accepted and "applied" or "rejected", reason = reason,
      }
    elseif act.type == "set_distress" then
      local accepted, reason = apply_set_distress(act)
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "set_distress", enabled = act.enabled,
        status = accepted and "applied" or "rejected", reason = reason,
      }
    elseif act.type == "cloak" then
      if mgr then apply_cloak(mgr, act) end           -- engage cloaking (id 10)
    elseif act.type == "set_doors" then
      apply_set_doors(act)                            -- open/close doors to vent O2 (id 8)
    elseif act.type == "mind_control" then
      apply_mind_control(act)                         -- mind-control enemy crew (id 14)
    elseif act.type == "battery" then
      if mgr then apply_battery(mgr, act) end          -- backup battery: temp reactor power (id 12)
    elseif act.type == "fire_beam" then
      local accepted, reason, facts = apply_fire_beam(act)
      facts = facts or {}
      S.action_feedback[#S.action_feedback + 1] = {
        action_index = action_index, type = "fire_beam", weapon_slot = act.weapon_slot or 0,
        target_ship_id = act.target_ship_id or 1, room_a = act.room_a or 0,
        room_b = act.room_b ~= nil and act.room_b or (act.room_a or 0),
        status = accepted and "applied" or "rejected", reason = reason,
        enemy_hostile = facts.enemy_hostile, enemy_targetable = facts.enemy_targetable,
        queued = accepted == true,
      }
    elseif act.type == "hack_system" then
      apply_hack_system(act)                          -- deploy+arm hacking drone (id 15)
    elseif act.type == "deploy_drone" then
      if mgr then apply_deploy_drone(mgr, act) end     -- power a drone slot to deploy (id 4)
    elseif act.type == "recall_drones" then
      if mgr then apply_recall_drones(mgr, act) end    -- power the drone system down
    elseif act.type == "teleport_crew" then
      apply_teleport_crew(act)                         -- send(1)/recall(2) organic boarders (id 9)
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

  -- diagnostics for the on-screen action-log overlay: render_count proves the render hook is
  -- firing; action_log_len shows how many lines it has to draw.
  pcall(function() obs.render_count = S.render_count end)
  pcall(function() obs.action_log_len = S.action_log and #S.action_log or 0 end)
  pcall(function() obs.render_err = _G.ftl_bench_render_err end)
  -- interrupted_by: if the hybrid pause ended the LAST advance early, why (combat_started /
  -- took_damage / boarder_aboard / fire / event) -- a flag telling the agent to look NOW.
  pcall(function() obs.interrupted_by = S.interrupt_reason end)

  -- jump_charge_pct: the FTL-drive recharge as a scalar in [0,1], plus the raw {current,max}
  -- seconds, so the agent can reason hold-vs-flee instead of only the jump_charged bool.
  -- jump_timer is ShipManager's std::pair<float,float> {first=current, second=max}.
  -- The exact native timer is separate from navigation legality. jump_charged
  -- reflects native navigation.can_jump; never infer readiness from enemy absence.

  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not pl or pl.bJumping then return end
    local cur, mx
    pcall(function() cur = pl.jump_timer.first  end)
    pcall(function() mx  = pl.jump_timer.second end)
    if cur and mx and mx > 0 then
      local pct = cur / mx
      if pct < 0 then pct = 0 elseif pct > 1 then pct = 1 end
      obs.jump_charge_pct = pct
      obs.jump_charge = { current = cur, max = mx }
    end
  end)

  -- store inventory when standing on a store beacon: {buy=[{i,name,price,count}...], sell=[...]}.
  -- "" off a store. Lets the agent spend scrap (buy weapons/drones/systems/augments/repair/fuel).
  pcall(function()
    local sj = Hyperspace.benchmark_store_read()
    if sj and sj ~= "" then obs.store = json.decode(sj) end
  end)

  -- cloaking system state (id 10): so the agent knows whether/when it can engage cloak.
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (pl and obs.player_ship) or pl.bJumping then return end
    local cloak = pl.cloakSystem
    if not cloak then return end                       -- nil => no cloaking system
    local c = { installed = true }
    pcall(function() c.active = cloak.bTurnedOn end)
    pcall(function() c.power = cloak:GetEffectivePower() end)
    pcall(function() c.functioning = cloak:Functioning() end)
    pcall(function() c.locked = cloak:GetLocked() end)
    pcall(function()
      c.time_left = cloak.timer.running and ((cloak.timer.currGoal or 0) - (cloak.timer.currTime or 0)) or 0
    end)
    c.ready = (c.power and c.power > 0) and (c.functioning ~= false) and (c.locked ~= true) and (c.active ~= true)
    obs.player_ship.cloak = c
  end)

  -- EVASION (dodge %) for both ships. GetDodgeFactor() returns an int percent the engine
  -- builds from powered/manned engines + piloting skill + cloak bonus -- the same number FTL
  -- shows as "Evasion: NN%". Lets the agent see WHY shots miss (don't dump 4 missiles into a
  -- high-evasion auto-ship; lower its engines via hack/ion first). Scalar int getter on a
  -- stable ShipManager -> no collection iteration, crash-safe. (GetNetDodgeFactor is UNBOUND.)
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (pl and obs.player_ship) or pl.bJumping then return end
    pcall(function() obs.player_ship.evasion = pl:GetDodgeFactor() end)
  end)
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if not (en and obs.enemy_ship) or en.bDestroyed or en.bJumping then return end
    pcall(function() obs.enemy_ship.evasion = en:GetDodgeFactor() end)
  end)

  -- COMBAT AVAILABILITY: a human knows "I can't shoot anymore" because the targeting cursor
  -- disappears (nothing to aim at). The programmatic `fire` API has no such cue, so surface it
  -- explicitly:
  --   targetable = you can actually aim a weapon at the enemy right now. FALSE once the enemy is
  --     warping out (bJumping) or destroyed -- firing then hits nothing.
  --   fleeing    = the enemy has FORFEIT and is charging its FTL drive to escape (or already
  --     warping out). The fight is effectively over; finishing the kill is a race vs its jump.
  --   jump_charge_pct = how close the enemy is to escaping (0..1).
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if not (en and obs.enemy_ship) then return end
    local native = native_enemy_state(en)
    obs.enemy_ship.hostile = native.hostile
    obs.enemy_ship.destroyed = native.destroyed
    obs.enemy_ship.targetable = enemy_target_refusal(en, native) == nil
    local jumping = native.jumping == true
    local cur, mx = 0, 0
    pcall(function() cur = en.jump_timer.first end)
    pcall(function() mx  = en.jump_timer.second end)
    if mx and mx > 0 then obs.enemy_ship.jump_charge_pct = math.min(1.0, (cur or 0) / mx) end
    obs.enemy_ship.fleeing = (jumping or (mx and mx > 0 and cur and cur > 0)) and true or false
  end)

  -- Flagship/boss metadata. Some boss internals are not bound in stock Hyperspace, so every
  -- field below is best-effort. We still expose the guaranteed player-visible fact available
  -- through the map: whether the current beacon is the boss beacon.
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    local sm = world and world.starMap
    local flag = {}
    local added = 0
    local is_boss = false
    if put_scalar_if_present(flag, "present", function() return sm.currentLoc.boss end) then
      added = added + 1
      is_boss = flag.present == true
    end
    if put_scalar_if_present(flag, "phase", function() return world.bossLevel end) then added = added + 1 end
    if put_scalar_if_present(flag, "phase", function() return world.bossPhase end) then added = added + 1 end
    if put_scalar_if_present(flag, "stage", function() return world.bossStage end) then added = added + 1 end
    if put_scalar_if_present(flag, "power_surge_timer", function() return world.bossPowerTimer.first end) then added = added + 1 end
    if put_scalar_if_present(flag, "power_surge_timer_max", function() return world.bossPowerTimer.second end) then added = added + 1 end
    if put_scalar_if_present(flag, "power_surge_type", function() return world.bossPowerType end) then added = added + 1 end
    if en and obs.enemy_ship then
      if is_boss then obs.enemy_ship.flagship = true end
      local ss = {}
      put_scalar_if_present(ss, "value", function() return en.superShield end)
      put_scalar_if_present(ss, "value", function() return en.superShieldPower end)
      put_scalar_if_present(ss, "value", function() return en.zoltanShield end)
      put_scalar_if_present(ss, "value", function() return en.shieldSystem.superShield end)
      put_scalar_if_present(ss, "max", function() return en.superShieldMax end)
      put_scalar_if_present(ss, "active", function() return en.bHasZoltanShield end)
      if next(ss) ~= nil then
        flag.super_shield = ss
        obs.enemy_ship.super_shield = ss
        added = added + 1
      end
      put_scalar_if_present(obs.enemy_ship, "power_surge_timer", function() return en.bossPowerTimer.first end)
      put_scalar_if_present(obs.enemy_ship, "power_surge_timer_max", function() return en.bossPowerTimer.second end)
      put_scalar_if_present(obs.enemy_ship, "power_surge_type", function() return en.bossPowerType end)
    end
    local has_flagship_details = flag.present == true or flag.phase ~= nil or flag.stage ~= nil
      or flag.super_shield ~= nil or flag.power_surge_timer ~= nil or flag.power_surge_type ~= nil
    if added > 0 and has_flagship_details then
      obs.flagship = flag
    end
  end)

  -- The native TopScore snapshot can retain the previous run until Save updates it.
  -- Only expose the pure current-run StatTracker getter as authoritative score.
  obs.ftl_score = nil
  obs.ftl_score_source = nil
  pcall(function()
    local score = Hyperspace.benchmark_run_score()
    if type(score) == "number" and score >= 0 then
      obs.ftl_score = score
      obs.ftl_score_source = "native_live_v1"
      local components = Hyperspace.benchmark_score_components()
      if type(components) == "string" and components ~= "" then
        local ok, decoded = pcall(json.decode, components)
        if ok and type(decoded) == "table" then obs.ftl_score_components = decoded end
      end
    end
  end)

  -- shot-outcome feed: surface OUR shots' effectiveness THIS combat so the agent can tell its
  -- weapons are MISSING (vs landing / shield-blocked) and adapt (target engines / flee). The
  -- tallies are filled by the projectile event hooks above; reset when combat ends.
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if en and obs.enemy_ship and obs.player_ship and S.shots then
      local s = S.shots
      local missed = s.fired - s.hit - s.shields
      if missed < 0 then missed = 0 end
      obs.player_ship.shots = {
        fired = s.fired, hit = s.hit, shields_blocked = s.shields,
        missed = missed, damage_dealt = s.dmg, recent = s.log,
      }
    elseif not en then
      S.shots = nil   -- combat over -> reset the per-combat tally
    end
  end)

  -- mind-control system state (id 14) + enemy rooms holding crew (target picker for it).
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (pl and obs.player_ship) or pl.bJumping then return end
    local has = false; pcall(function() has = pl:HasSystem(14) end)
    if not has then return end
    local ms = pl.mindSystem
    if not ms then pcall(function() ms = pl:GetSystem(14) end) end
    if not ms then return end
    local mc = { installed = true }
    pcall(function()
      mc.power = ms:GetEffectivePower(); mc.functioning = ms:Functioning()
      mc.timer = ms.controlTimer.first; mc.timer_max = ms.controlTimer.second
      mc.ready = (ms:GetEffectivePower() > 0) and ms:Functioning() and (ms.iLockCount == 0)
                 and (ms.controlTimer.first >= ms.controlTimer.second) and (not ms.bBlocked)
    end)
    obs.player_ship.mind_control = mc
  end)
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (en and obs.enemy_ship) or (pl and pl.bJumping) then return end
    local cl = en.vCrewList
    if not cl then return end
    local counts = {}
    local crew = {}
    for i = 0, cl:size() - 1 do
      local c = cl[i]
      if c then pcall(function()
        if c.iShipId == 1 and not c:IsDead() and not c:OutOfGame() then
          local r = c.iRoomId
          local e = counts[r] or { room_id = r, crew = 0, controllable = 0, members = {} }
          local m = { id = i, room_id = r }
          put_scalar_if_present(m, "health", function() return c.health.first end)
          put_scalar_if_present(m, "health_max", function() return c.health.second end)
          put_scalar_if_present(m, "species", function() return c.species end)
          put_scalar_if_present(m, "drone", function() return c:IsDrone() end)
          put_scalar_if_present(m, "mind_controlled", function() return c.bMindControlled end)
          put_scalar_if_present(m, "fighting", function() return c.bFighting end)
          put_scalar_if_present(m, "repairing", function() return c:Repairing() end)
          put_scalar_if_present(m, "telepathic", function() return c:IsTelepathic() end)
          e.crew = e.crew + 1
          if not c:IsDrone() and not c:IsTelepathic() and not c.bMindControlled then
            e.controllable = e.controllable + 1
          end
          e.members[#e.members + 1] = m
          counts[r] = e
          crew[#crew + 1] = m
        end
      end) end
    end
    local rooms = {}
    for _, e in pairs(counts) do rooms[#rooms + 1] = e end
    obs.enemy_ship.rooms_with_crew = rooms
    obs.enemy_ship.crew = crew
  end)

  -- backup battery state (id 12): temp reactor power on a timer. ready => can fire it now.
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (pl and obs.player_ship) or pl.bJumping then return end
    local bat = pl.batterySystem
    if not bat then pcall(function() bat = pl:GetSystem(12) end) end
    if not bat then return end                          -- nil => no battery system installed
    local b = { installed = true }
    pcall(function() b.active = bat.bTurnedOn end)
    pcall(function() b.power = bat:GetEffectivePower() end)   -- extra reactor power while active
    pcall(function() b.functioning = bat:Functioning() end)
    pcall(function() b.locked = bat:GetLocked() end)
    pcall(function()
      b.time_left = bat.timer.running and ((bat.timer.currGoal or 0) - (bat.timer.currTime or 0)) or 0
    end)
    b.ready = (b.power and b.power > 0) and (b.functioning ~= false) and (b.locked ~= true) and (b.active ~= true)
    obs.player_ship.battery = b
  end)

  -- hacking system state (id 15): readiness to deploy + live hack/pulse state + which enemy
  -- system is being disrupted. COMBAT-ONLY, never mid-warp. All fields are bound in hyperspace.i.
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (pl and obs.player_ship) or pl.bJumping then return end
    local hs = pl.hackingSystem
    if not hs then pcall(function() hs = pl:GetSystem(15) end) end
    if not hs then obs.player_ship.hacking = { installed = false }; return end  -- buy it first
    local h = { installed = true }
    pcall(function() h.powered       = hs:Powered() end)
    pcall(function() h.power         = hs.powerState.first end)
    pcall(function() h.max_power     = hs:GetMaxPower() end)
    pcall(function() h.hacking       = hs.bHacking end)          -- drone is out / hack active
    pcall(function() h.armed         = hs.bArmed end)            -- UI target-select flag
    pcall(function() h.can_hack      = hs.bCanHack end)
    pcall(function() h.blocked       = hs.bBlocked end)          -- super-shield/defense blocking
    pcall(function() h.drone_arrived = hs.drone.arrived end)     -- drone reached enemy hull
    pcall(function() h.pulse_timer   = hs.effectTimer.first end)
    pcall(function() h.pulse_max     = hs.effectTimer.second end)
    pcall(function() h.system_locked = (hs.iLockCount ~= 0) end) -- 0 idle; -1 active lock; >0 cooldown/ion
    pcall(function() if hs.currentSystem then h.target_room = hs.currentSystem.roomId end end)
    h.ready = (h.powered == true) and (h.system_locked ~= true)
    obs.player_ship.hacking = h
  end)
  -- mark which enemy systems are under a hack pulse (iHackEffect > 0), so the agent SEES it land.
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if not (en and obs.enemy_ship and obs.enemy_ship.rooms) then return end
    for _, r in ipairs(obs.enemy_ship.rooms) do
      local s = en:GetSystem(r.system_id)
      if s then pcall(function() r.hacked = (s.iHackEffect > 0) end) end
    end
  end)

  -- Drone Control system (id 4): readiness + per-slot loadout. is_space flags which slots are
  -- SAFE space-drones vs crew-drone (Rosetta) slots; drone_parts is the combat/boarder ammo.
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (pl and obs.player_ship) or pl.bJumping then return end
    if not pl:HasSystem(4) then obs.player_ship.drones = { installed = false }; return end
    local ds = pl.droneSystem
    if not ds then return end
    local D = { installed = true, slots = {} }
    pcall(function() D.power       = ds.powerState.first end)
    pcall(function() D.max_power   = ds:GetMaxPower() end)
    pcall(function() D.functioning = ds:Functioning() end)
    pcall(function() D.hacked      = (ds.iHackEffect or 0) > 0 end)
    pcall(function() D.drone_parts = pl:GetDroneCount() end)   -- ammo for combat/boarder drones
    pcall(function() D.has_target  = (ds.targetShip ~= nil) end)
    local n = 0; pcall(function() n = ds.drones:size() end)
    local CREW = { [2] = true, [3] = true, [4] = true, [5] = true }   -- crew-drone (Rosetta) types
    for i = 0, n - 1 do
      local d = ds.drones[i]
      if d then
        local name = ""; pcall(function() name = d:GetName() end)
        local t = d.type
        D.slots[#D.slots + 1] = {
          slot = i, name = name, type = t,
          is_space  = (not CREW[t]),     -- true => SAFE to deploy (SpaceDrone); false => crew-drone
          powered   = d.powered, deployed = d.deployed, dead = d.bDead,
          ready     = (d.powered and d.deployed and not d.bDead),
          req_power = d.powerRequired,
        }
      end
    end
    obs.player_ship.drones = D
  end)

  -- Enemy Drone Control (id 4): which drones the ENEMY has DEPLOYED (flying around) + their TYPE.
  -- A deployed SpaceDrone (combat/defense/beam) attacks/defends INDEPENDENTLY of the enemy's
  -- WEAPONS, so an enemy with depowered guns + a live drone is still a threat. Mirrors the player
  -- droneSystem emission; READ-ONLY, same pcall guards, combat-only (not mid-warp).
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if not (en and obs.enemy_ship) or en.bJumping then return end
    if not en:HasSystem(4) then return end
    local ds = en.droneSystem
    if not ds then return end
    local CREW = { [2] = true, [3] = true, [4] = true, [5] = true }
    local list = {}
    local n = 0; pcall(function() n = ds.drones:size() end)
    for i = 0, n - 1 do
      local d = ds.drones[i]
      if d then
        local name = ""; pcall(function() name = d:GetName() end)
        local t = d.type
        list[#list + 1] = {
          slot = i, name = name, type = t,
          is_space = (not CREW[t]),
          powered = d.powered, deployed = d.deployed, dead = d.bDead,
          firing  = (d.powered and d.deployed and not d.bDead),
        }
      end
    end
    obs.enemy_ship.drones = list
  end)

  -- teleporter system state (id 9) + ORGANIC boarder picture. iShipId is the OWNER ship (player
  -- crew is always 0, even while boarding); currentShipId is where the crew physically is.
  -- "Aboard enemy" = owned by us (iShipId==0) AND on the enemy (currentShipId==1). Drones are
  -- excluded from every count: only organic crew are safe to teleport under Rosetta.
  pcall(function()
    local p  = Hyperspace.ships and Hyperspace.ships.player
    if not (p and obs.player_ship) or p.bJumping then return end
    local has = false; pcall(function() has = p:HasSystem(9) end)
    if not has then return end
    local t = { installed = true }
    local sys = p:GetSystem(9)
    if sys then
      pcall(function() t.power       = sys:GetEffectivePower() end)   -- 0 = unpowered, can't teleport
      pcall(function() t.functioning = sys:Functioning() end)
      pcall(function() t.hacked      = sys.iHackEffect > 0 end)
    end
    local ts = p.teleportSystem
    if ts then
      pcall(function() t.charged     = ts:Charged() end)
      pcall(function() t.charge_pct  = ts:GetChargedPercent() end)
      pcall(function() t.can_send    = ts:CanSend() end)
      pcall(function() t.can_receive = ts:CanReceive() end)
      pcall(function() t.num_slots   = ts.iNumSlots end)
    end
    pcall(function() t.tele_room_id = p:GetSystemRoom(9) end)         -- room boarders must stand in to be sent
    local ready_to_send, aboard, home = 0, 0, 0
    local aboard_by_room = {}
    local cl = p.vCrewList
    if cl then
      for i = 0, cl:size() - 1 do
        local c = cl[i]
        if c then pcall(function()
          if not c.bDead and not c:IsDrone() and not c:OutOfGame() and c.iShipId == 0 then
            if c.currentShipId == 1 then
              aboard = aboard + 1                                      -- physically on the enemy ship
              local r = c.iRoomId
              aboard_by_room[r] = (aboard_by_room[r] or 0) + 1
            elseif c.currentShipId == 0 then
              home = home + 1
              if t.tele_room_id and c.iRoomId == t.tele_room_id then
                ready_to_send = ready_to_send + 1                      -- in the teleporter room = sendable
              end
            end
          end
        end) end
      end
    end
    t.organic_in_tele_room = ready_to_send   -- >0 AND charged => a send will actually fire
    t.organic_aboard_enemy = aboard          -- >0 AND charged => a recall is meaningful
    t.organic_home         = home
    local abl = {}
    for r, nn in pairs(aboard_by_room) do abl[#abl + 1] = { room_id = r, organic = nn } end
    t.organic_aboard_by_room = abl            -- pass one of these room_ids as recall target_room_id
    obs.player_ship.teleporter = t
  end)

  -- Per-weapon firing state, COMBAT-ONLY and not mid-warp (reading ProjectileFactory
  -- pointers during a jump teardown is the freeze class). required_power lets an agent
  -- tell the 2-power Burst Laser from the 1-power Artemis; fire_when_ready/has_target
  -- say whether a charged weapon will actually fire.
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    local ps = obs.player_ship
    -- NOTE: do NOT gate this on an enemy being present. weapon_type/is_beam/num_shots/
    -- required_power are properties of the PLAYER's own weapons and must be readable while
    -- idle too (a real agent couldn't see its loadout between fights). The only enemy-
    -- dependent fields below degrade gracefully (has_target=false, n_targets=0).
    if not (pl and ps and ps.weapons) or pl.bJumping then return end
    local wl = pl:GetWeaponList()
    for i = 0, wl:size() - 1 do
      local pf = wl[i]; local ow = ps.weapons[i + 1]
      if pf and ow then
        pcall(function() ow.required_power = pf.requiredPower end)
        pcall(function() ow.fire_when_ready = pf.fireWhenReady end)
        pcall(function() ow.has_target = (pf.currentShipTarget ~= nil) end)
        ow.manual_fire_pending = (S.manual_fire and S.manual_fire[tostring(i)] ~= nil) or false
        -- autofiring is raw engine state only. The benchmark fire path is manual one-shot:
        -- prefer manual_fire_pending/fire_when_ready when reasoning about queued releases.
        pcall(function() ow.autofiring = pf.autoFiring end)
        -- shots/targets: a multi-shot weapon needs NumTargetsRequired() aim points to
        -- actually fire (see apply_fire_weapon). Expose both so an agent can tell a
        -- charged-but-unfireable weapon (n_targets < targets_required) from a ready one.
        pcall(function() ow.num_shots = pf.numShots end)
        pcall(function() ow.targets_required = pf:NumTargetsRequired() end)
        pcall(function() ow.n_targets = pf.targets:size() end)
        -- BEAM discriminator: a beam reports NumTargetsRequired()==2 (or typeName "BEAM").
        -- Lets the agent pick the right slot for fire_beam and read its sweep length.
        pcall(function()
          local tname = pf.blueprint and pf.blueprint.typeName or ""
          ow.weapon_type = tname                       -- "BEAM"|"LASER"|"MISSILES"|"BOMB"|"BURST"
          ow.is_beam     = (tname == "BEAM")
          ow.beam_length = pf.blueprint and pf.blueprint.length or 0
        end)
        -- DAMAGE PROFILE: per-shot hull damage + how many shield layers the shot ignores.
        -- WeaponBlueprint::damage is a value-typed Damage struct (bound), reached via the
        -- already-read pf.blueprint pointer; iDamage/iShieldPiercing/fireChance/iIonDamage are
        -- plain int fields (all default 0). Lets the agent tell a shield-piercer from a bolt.
        pcall(function()
          local d = pf.blueprint and pf.blueprint.damage
          if d then
            ow.damage          = d.iDamage          -- hull damage per shot (int)
            ow.shield_piercing = d.iShieldPiercing  -- shield layers ignored (int, 0 = none)
            ow.fire_chance     = d.fireChance        -- 0..10 chance to start a fire
            ow.ion_damage      = d.iIonDamage        -- ion damage per shot
          end
        end)
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
        local b = {
          index = i, known = loc.known, visited = loc.visited,
          danger_zone = loc.dangerZone, boss = loc.boss,
          nebula = loc.nebula, has_event = (loc.event ~= nil),
          -- exit_beacon: jumping here advances to the next sector (the goal beacon).
          -- fleet: the rebel pursuit fleet has reached this beacon (deadly — avoid).
          exit_beacon = loc.beacon, new_sector = loc.newSector,
          quest = loc.questLoc, fleet = loc.fleetChanging,
          pos_x = px, pos_y = py,  -- map position (to navigate toward the exit)
        }
        put_scalar_if_present(b, "store", function() return loc.store end)
        put_scalar_if_present(b, "distress", function() return loc.distressBeacon end)
        beacons[#beacons + 1] = b
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
    pcall(function()
      if not sm.bChoosingNewSector then return end
      local sectors = sm.sectors
      if not sectors then return end
      local opts = {}
      for i = 0, sectors:size() - 1 do
        local sec = sectors[i]
        if sec then
          local opt = { index = i }
          local n = 0
          if put_scalar_if_present(opt, "name", function() return sec.name end) then n = n + 1 end
          if put_scalar_if_present(opt, "type", function() return sec.type end) then n = n + 1 end
          if put_scalar_if_present(opt, "level", function() return sec.level end) then n = n + 1 end
          if put_scalar_if_present(opt, "visited", function() return sec.visited end) then n = n + 1 end
          if put_scalar_if_present(opt, "reachable", function() return sec.reachable end) then n = n + 1 end
          if put_scalar_if_present(opt, "nebula", function() return sec.nebula end) then n = n + 1 end
          if put_scalar_if_present(opt, "civilian", function() return sec.civilian end) then n = n + 1 end
          if put_scalar_if_present(opt, "hostile", function() return sec.hostile end) then n = n + 1 end
          if put_scalar_if_present(opt, "unique", function() return sec.unique end) then n = n + 1 end
          if n > 0 then opts[#opts + 1] = opt end
        end
      end
      if #opts > 0 then obs.map.sector_choices = opts end
    end)

    -- map.hazard: environmental hazard active at THIS beacon. Scalar flags off SpaceManager
    -- (world.space) -- all bound in the compiled SWIG wrapper, all bools, no collection
    -- iteration. Already jump-guarded by the enclosing map `if`. Priority: storm/pulsar/sun
    -- (reactor/health threats) win over a co-present nebula; FTL renders one dominant hazard.
    -- PDS (an anti-ship turret) is orthogonal -> exposed separately.
    pcall(function()
      local space = world and world.space
      if not space then return end
      local hz = "none"
      if space.bStorm then hz = "ion_storm"            -- plasma/ion storm: caps usable reactor
      elseif space.pulsarLevel then hz = "pulsar"      -- periodic ion + power + shield drops
      elseif space.sunLevel then hz = "sun"            -- periodic hull fire damage
      elseif space.asteroidGenerator and space.asteroidGenerator.bRunning then hz = "asteroids"
      elseif space.bNebula then hz = "nebula"          -- sensors offline; can hide a storm
      end
      obs.map.hazard = hz
      pcall(function() obs.map.pds = space.bPDS end)               -- anti-ship turret, independent of hz
      pcall(function() obs.map.hazard_target = space.envTarget end)  -- 0 = player ship, 1 = enemy
    end)

    -- reactor power-truth: base obs reactor.available comes from GetAvailablePower(), which
    -- reports RAW reactor bars and IGNORES the storm/ion/hack cap -- so reactor_free LIES in a
    -- storm. PowerManager::GetMaxPower() is the engine's honest cap (RenderReactorBar uses it):
    --   min(currentPower.second - iTempPowerLoss - iHacked, iTempPowerCap).
    pcall(function()
      local pl = Hyperspace.ships and Hyperspace.ships.player
      if not (pl and obs.player_ship and obs.player_ship.reactor) then return end
      if pl.bJumping then return end
      local pm = Hyperspace.PowerManager.GetPowerManager(0)   -- static; 0 = player ship id
      if not pm then return end
      local rc = obs.player_ship.reactor
      local raw_total = rc.total
      pcall(function() raw_total = pm.currentPower.second end)
      local usable = raw_total
      pcall(function() usable = pm:GetMaxPower() end)          -- instance method, colon call
      local divide = 1
      pcall(function() divide = pm.iTempDividePower end)
      rc.usable_total   = usable                               -- TRUE max bars assignable now
      rc.power_penalty  = math.max(0, raw_total - usable)      -- bars stolen by storm/ion/hack
      rc.divide_power   = divide                               -- reactor divisor (usually 1)
      local allocated = (rc.total or 0) - (rc.available or 0)
      rc.usable_available = math.max(0, usable - allocated)    -- corrected free bars
    end)
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
      local selected, potential
      pcall(function() selected = cb.selectedChoice end)
      pcall(function() potential = cb.potentialChoice end)
      local ok, ev_choices = pcall(function() return cb:GetChoices() end)
      if ok and ev_choices then
        for i = 0, ev_choices:size() - 1 do
          local c = ev_choices[i]
          if c then
            -- ChoiceText::text is a plain std::string (already resolved), not a TextString.
            local choice = { index = i }
            local ctext = ""
            local okc, t = pcall(function() return c.text end)
            if okc and type(t) == "string" then ctext = t end
            choice.text = ctext
            if selected == i then choice.selected = true end
            if potential == i then choice.potential = true end
            put_scalar_if_present(choice, "blue", function() return c.blue end)
            put_scalar_if_present(choice, "blue", function() return c.bBlue end)
            put_scalar_if_present(choice, "color", function() return c.color end)
            local native_type = native_choice_type(c)
            if native_type ~= nil then
              choice.native_type = native_type
              choice.disabled = native_type == 1
              choice.enabled = native_type ~= 1
              choice.available = native_type ~= 1
            end
            put_scalar_if_present(choice, "locked", function() return c.locked end)
            put_scalar_if_present(choice, "requirements_met", function() return c.requirementMet end)
            put_scalar_if_present(choice, "cost", function() return c.cost end)
            if choice.disabled == nil and (choice.enabled == false or choice.available == false) then
              choice.disabled = true
            end
            choices[#choices + 1] = choice
          end
        end
      end
    end
    obs.event = { text = text, choices = choices }
    put_scalar_if_present(obs.event, "selected_choice", function() return cb.selectedChoice end)
    put_scalar_if_present(obs.event, "potential_choice", function() return cb.potentialChoice end)
    put_scalar_if_present(obs.event, "open_time", function() return cb.openTime end)
    put_scalar_if_present(obs.event, "dialog_keys", function() return Hyperspace.Settings.dialogKeys end)
  end

  -- enemy room ids (for weapon targeting): system_id -> room_id
  -- GUARD: skip during a jump or after destruction. This block iterates the enemy's
  -- GetWeaponList() + derefs ProjectileFactory/blueprint pointers; doing so mid-warp or during
  -- teardown reads freed pointers and freezes the loop (the 2026-06-04 freeze class).
  local enemy = Hyperspace.ships.enemy
  local _pl = Hyperspace.ships and Hyperspace.ships.player
  if enemy and obs.enemy_ship and not enemy.bDestroyed and not (_pl and _pl.bJumping) then
    local rooms = {}
    local sys_list = enemy.vSystemList
    if sys_list then
      for i = 0, sys_list:size() - 1 do
        local sys = sys_list[i]
        rooms[#rooms + 1] = { room_id = sys:GetRoomId(), system_id = sys:GetId() }
      end
    end
    obs.enemy_ship.rooms = rooms
    -- enemy weapons: charge timing (when they fire) + TYPE/DAMAGE PROFILE (how bad the hit is).
    -- Mirrors the player weapon loop. ProjectileFactory::blueprint -> WeaponBlueprint::damage
    -- (value-typed Damage struct, all fields bound). Each read individually pcall-wrapped so a
    -- nil blueprint on one weapon degrades that weapon's fields to absent, not the whole tick.
    local ewl = enemy:GetWeaponList()
    if ewl then
      local ew = {}
      for i = 0, ewl:size() - 1 do
        local w = ewl[i]
        if w then
          local okc, cur = pcall(function() return w.cooldown.first end)
          local okm, mx = pcall(function() return w.cooldown.second end)
          local e = { slot = i, powered = w.powered,
                      charge = okc and cur or nil, charge_max = okm and mx or nil }
          pcall(function()
            local tname = w.blueprint and w.blueprint.typeName or ""
            e.weapon_type = tname                          -- "BEAM"|"LASER"|"MISSILES"|"BOMB"|"BURST"
            e.is_beam     = (tname == "BEAM")
          end)
          pcall(function() e.num_shots = w.numShots end)
          pcall(function()
            local d = w.blueprint and w.blueprint.damage
            if d then
              e.damage          = d.iDamage          -- hull damage per shot (int)
              e.shield_piercing = d.iShieldPiercing  -- shield layers ignored (int, 0 = none)
              e.fire_chance     = d.fireChance        -- 0..10 chance to start a fire
              e.ion_damage      = d.iIonDamage        -- ion damage per shot
            end
          end)
          ew[#ew + 1] = e
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
        pcall(function() ps.ion = math.max(0, sys.iLockCount) end)
        local onr, nr = pcall(function() return sys:NeedsRepairing() end)
        if onr then ps.needs_repair = nr end
        local oh, he = pcall(function() return sys.iHackEffect end)
        if oh and type(he) == "number" then ps.hacked = he > 0 end
      end
    end
  end)

  -- Crew management (fix stuff / fight invaders / fight fires). move_crew(crew_id, room_id) is
  -- the universal tasking action: send a crew member into a damaged system's room to REPAIR it,
  -- into a fire room to EXTINGUISH, into an intruder's room to FIGHT, into a station room to MAN
  -- it. This block gives the agent what it needs to decide: player system->room mapping, each
  -- crew's task/species/skills, the list of INTRUDERS aboard our ship, and FIRES per room. All
  -- fields are %rename-bound (pure Lua hot-reload, no rebuild).
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not (pl and obs.player_ship) then return end

    -- (a) player system -> room_id, so a repairer can be moved to the right room (the base obs
    -- omits it; the enemy obs already exposes room ids via GetRoomId). damage>0 => needs repair.
    if obs.player_ship.systems then
      local sl = pl.vSystemList
      if sl then
        for i = 0, sl:size() - 1 do
          local sys = sl[i]; local ps = obs.player_ship.systems[i + 1]
          if sys and ps then pcall(function() ps.room_id = sys:GetRoomId() end) end
        end
      end
    end

    -- (b) filter the old base serializer's mixed physical crew list, then enrich
    -- by ORIGINAL native id. Filtering must never change command identity.
    -- Our boarders stay player-owned even when their intruder flag is true.
    -- Enrich own crew with current task + species + key skills (man the right station; see
    -- who is already busy repairing/fighting). Skill ids: 0 pilot,1 engine,2 shield,3 weapon,
    -- 4 repair,5 combat (best-effort: kept only when GetSkillLevel returns a number).
    if obs.player_ship.crew then
      local cl = pl.vCrewList
      if cl then
        local own = {}
        for _, oc in ipairs(obs.player_ship.crew) do
          local id = oc.id
          local c = type(id) == "number" and id >= 0 and id < cl:size() and cl[id] or nil
          if c and c.iShipId == 0 then
            own[#own + 1] = oc
            oc.owner_ship_id = c.iShipId
            oc.current_ship_id = c.currentShipId
            oc.player_owned = true
            local cok, controllable = pcall(function() return c:GetControllable() end)
            oc.controllable = cok and controllable == true
            pcall(function() oc.species = c.species end)
            pcall(function() oc.intruder = c.intruder end)
            pcall(function() oc.fighting = c.bFighting end)
            pcall(function() oc.repairing = c:Repairing() end)
            pcall(function() oc.on_enemy_ship = (c.currentShipId == 1) end)
            pcall(function()
              local sk = {}
              for k = 0, 5 do
                local v = c:GetSkillLevel(k)
                if type(v) == "number" then sk[k] = v end
              end
              if next(sk) then oc.skills = sk end
            end)
          end
        end
        obs.player_ship.crew = own
      end
    end

    -- (c) INTRUDERS aboard OUR ship (find invaders). An invader has currentShipId==0 (physically
    -- on the player ship) and is NOT owned by us (iShipId~=0). Scan both crew lists (FTL keeps an
    -- intruder in its OWNER ship's list). Send your crew to room_id to fight them.
    local intr = {}
    local function scan(list)
      if not list then return end
      for i = 0, list:size() - 1 do
        local c = list[i]
        if c then pcall(function()
          if (not c.bDead) and c.currentShipId == 0 and c.iShipId ~= 0 then
            intr[#intr + 1] = { room_id = c.iRoomId,
                                health = c.health and c.health.first,
                                species = c.species, fighting = c.bFighting }
          end
        end) end
      end
    end
    scan(pl.vCrewList)
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if en then scan(en.vCrewList) end
    obs.player_ship.intruders = intr

    -- (d) ROOM STATUS + FIRES. Room oxygen/doors/breaches are visible in the game UI and
    -- essential for venting/fire/suffocation decisions. Keep `fires` as the old compact crisis
    -- list while also surfacing all room rows for agents that need the full topology.
    local rooms = {}
    local fires = {}
    local ship = pl.ship
    if ship and ship.vRoomList then
      local rl = ship.vRoomList
      for i = 0, rl:size() - 1 do
        local rm = rl[i]
        if rm then pcall(function()
          local rid = rm.iRoomId
          local room = { room_id = rid }
          pcall(function()
            if rm.rect then
              room.rect = { x = rm.rect.x, y = rm.rect.y, w = rm.rect.w, h = rm.rect.h }
            end
          end)
          local o2 = pl.oxygenSystem
          if o2 then
            put_scalar_if_present(room, "oxygen", function() return o2.oxygenLevels[rid] end)
            put_scalar_if_present(room, "oxygen", function() return o2.oxygenLevels[i] end)
          end
          local fc = pl:GetFireCount(rid)
          if fc ~= nil then room.fires = fc end
          put_scalar_if_present(room, "breaches", function() return rm.iBreaches end)
          put_scalar_if_present(room, "breached", function() return rm.bBreached end)
          put_scalar_if_present(room, "breach", function() return rm.breach end)
          put_scalar_if_present(room, "blacked_out", function() return rm.bBlackedOut end)
          rooms[#rooms + 1] = room
          if fc and fc > 0 then fires[#fires + 1] = { room_id = rid, fires = fc } end
        end) end
      end
    end
    obs.player_ship.rooms = rooms
    obs.player_ship.fires = fires

    -- Door graph includes outer airlocks: opening them is an exposed actuator and agents
    -- need to see which rooms vent to space. The display index is unique across both lists.
    local doors = {}
    local function append_doors(dl, airlock)
      if not dl then return end
      for i = 0, dl:size() - 1 do
        local door = dl[i]
        if door then pcall(function()
          local d = { index = #doors, airlock = airlock }
          put_scalar_if_present(d, "id", function() return door.iDoorId end)
          put_scalar_if_present(d, "room_a", function() return door.iRoom1 end)
          put_scalar_if_present(d, "room_b", function() return door.iRoom2 end)
          put_scalar_if_present(d, "open", function() return door.bOpen end)
          put_scalar_if_present(d, "locked", function() return door.lockedDown.running end)
          put_scalar_if_present(d, "forced_open", function() return door.forcedOpen.running end)
          put_scalar_if_present(d, "hacked", function() return door.iHacked end)
          doors[#doors + 1] = d
        end) end
      end
    end
    if ship then
      append_doors(ship.vDoorList, false)
      pcall(function() append_doors(ship.vOuterAirlocks, true) end)
    end
    obs.player_ship.doors = doors
  end)
end

------------------------------------------------------------------
-- Pause (bPaused only)
------------------------------------------------------------------

local DeterministicSetup
local function set_frozen(frozen)
  local gui = Hyperspace.App and Hyperspace.App.gui
  if type(Hyperspace.benchmark_visual_set_clock) == "function" then
    pcall(Hyperspace.benchmark_visual_set_clock, S.observation_mode == "visual-v1" or (DeterministicSetup and DeterministicSetup.owns()), not frozen)
  end
  if gui then gui.bPaused = frozen end
end

------------------------------------------------------------------
-- Observation (schema_version 2: + last_action_seq, live paused)
------------------------------------------------------------------

-- Pausing ship simulation does not stop native GUI timers or a requested map
-- Wait turn. Watch only stable scalars here; do not traverse ship collections on
-- every idle tick just to discover a changed popup or completed recovery turn.
local function idle_ui_signature(gui, world)
  local function scalar(fn)
    local ok, value = pcall(fn)
    if ok and (type(value) == "number" or type(value) == "boolean" or type(value) == "string") then
      return value
    end
    return "unknown"
  end
  local choice_open = scalar(function() return gui.choiceBoxOpen end)
  local mode = scalar(function() return Hyperspace.Settings.dialogKeys end)
  local key = json.encode({
    choice_open,
    scalar(function() return gui.gameover end),
    scalar(function() return gui.alreadyWon end),
    scalar(function() return world.starMap.bOpen end),
    scalar(function() return world.starMap.bChoosingNewSector end),
    mode,
    choice_open == true and scalar(function() return gui.choiceBox.mainText end) or "",
    choice_open == true and scalar(function() return gui.choiceBox.selectedChoice end) or -1,
    choice_open == true and scalar(function()
      return mode ~= 2 or gui.choiceBox.openTime >= 0.3
    end) or false,
  })
  return key
end

local function visual_capabilities()
  if type(Hyperspace.benchmark_visual_capabilities) ~= "function" then return nil end
  local ok, encoded = pcall(Hyperspace.benchmark_visual_capabilities)
  if not ok or type(encoded) ~= "string" then return nil end
  local decoded, caps = pcall(json.decode, encoded)
  if decoded and type(caps) == "table" and caps.visual_io_version == 1
    and caps.capture == true and caps.input == true then return caps end
  return nil
end

local function visual_world_updates(caps)
  if not caps or caps.visual_clock_version ~= 2 or type(caps.world_updates) ~= "string"
    or not caps.world_updates:match("^%d+$") or caps.fixed_step_numerator ~= 1
    or caps.fixed_step_denominator ~= 60 or caps.simulated_updates ~= caps.world_updates then return nil end
  local updates=tonumber(caps.world_updates)
  if not updates or updates > 9007199254740991 then return nil end
  return updates
end

local function write_observation()
  if S.observation_mode == "visual-v1" and not S.visual_in_render then
    S.visual_pending = true
    return false -- only the completed native render may acknowledge this step
  end
  local ok, complete, waiting = pcall(function()
    local obs = _G.ftl_bench.build_observation(S.frame_counter)
    obs.schema_version  = 3
    obs.last_action_seq = S.last_applied_seq
    obs.reset_done_seq  = S.reset_done_seq   -- seq of the reset whose NEW seeded game has loaded
    local gui = Hyperspace.App and Hyperspace.App.gui
    obs.paused = (gui ~= nil and gui.bPaused) or false
    -- game_over: the run has ended (all crew dead / ship lost). NOT a crash and NOT hull<=0
    -- for crew-death, so this is the only reliable terminal signal — the harness uses it to
    -- end/reset the episode instead of spinning no-op actions at the GAME OVER screen.
    obs.game_over = (gui ~= nil and gui.gameover) or false
    obs.bridge_version = 5
    obs.capabilities = {
      manual_fire = true,
      crew_control_guard = true,
      crew_ownership = true,
      enemy_hostility = true,
      global_autofire_control = type(Hyperspace.benchmark_set_weapon_autofire) == "function",
      victory = false,
    }
    if DeterministicSetup then obs.deterministic_setup=DeterministicSetup.observe() end
    obs.action_feedback = S.action_feedback or {}
    local visual_caps = visual_capabilities()
    obs.capabilities.external_input_guard = visual_caps ~= nil and visual_caps.external_input_guard == true
      and type(visual_caps.external_input_generation) == "string"
      and type(visual_caps.external_input_detected) == "boolean"
    if visual_caps and visual_world_updates(visual_caps) ~= nil
      and type(Hyperspace.benchmark_visual_set_clock) == "function" then
      obs.capabilities.visual_clock_version = visual_caps.visual_clock_version
      obs.capabilities.world_updates = visual_caps.world_updates
      obs.capabilities.fixed_step_numerator = visual_caps.fixed_step_numerator
      obs.capabilities.fixed_step_denominator = visual_caps.fixed_step_denominator
      obs.capabilities.simulated_updates = visual_caps.simulated_updates
    end
    obs.capabilities.visual_io = visual_caps ~= nil
    if visual_caps then obs.capabilities.visual_io_version = 1 end
    obs.observation_mode = S.observation_mode or "structured-v7"
    if S.observation_mode == "visual-v1" then obs.visual_request_error = S.visual_request_error end
    put_scalar_if_present(obs, "difficulty", function() return Hyperspace.benchmark_difficulty() end)
    -- The live Windows WorldManager.currentDifficulty field can contain garbage;
    -- use the actual game settings binding if a native getter is unavailable.
    put_scalar_if_present(obs, "difficulty", function() return Hyperspace.Settings.difficulty end)
    if obs.player_ship then
      put_scalar_if_present(obs.player_ship, "blueprint", function() return Hyperspace.benchmark_player_blueprint() end)
      put_scalar_if_present(obs.player_ship, "blueprint", function() return Hyperspace.ships.player.myBlueprint.blueprintName end)
    end
    -- Only expose a win when a native, explicitly bound boolean is available.
    -- Neither sector number nor an arbitrary boss-stage value proves victory.
    local victory = {}
    put_scalar_if_present(victory, "value", function() return Hyperspace.benchmark_victory() end)
    put_scalar_if_present(victory, "value", function() return Hyperspace.Score.currentScore.victory end)
    put_scalar_if_present(victory, "value", function() return gui.alreadyWon end)
    if type(victory.value) == "boolean" then
      obs.victory = victory.value
      obs.capabilities.victory = true
    end
    if type(Hyperspace.benchmark_capabilities) == "function" then
      local cok, cjson = pcall(Hyperspace.benchmark_capabilities)
      if cok and type(cjson) == "string" and cjson ~= "" then
        local dok, caps = pcall(json.decode, cjson)
        if dok and type(caps) == "table" then
          for k, v in pairs(caps) do obs.capabilities[k] = v end
        end
      end
    end
    obs.economy = native_economy_state()
    local economy = obs.economy
    local protocol5 = economy ~= nil and economy.native_protocol >= 5
    obs.capabilities.sector_navigation = protocol5 and economy.sector_navigation_version == 1
      and type(Hyperspace.benchmark_leave_sector) == "function"
    local navigation = native_navigation_state(economy)
    obs.capabilities.beacon_navigation = navigation ~= nil
      and type(Hyperspace.benchmark_jump_to_beacon) == "function"
    obs.jump_charged = obs.capabilities.beacon_navigation and navigation.can_jump or false
    obs.capabilities.upgrade_rules = protocol5
      and type(economy.upgrade_available) == "boolean" and type(economy.systems) == "table"
      and type(Hyperspace.benchmark_upgrade_system) == "function"
      and type(Hyperspace.benchmark_upgrade_reactor) == "function"
    local fuel = economy and economy.fuel_recovery
    obs.capabilities.fuel_recovery = protocol5 and type(fuel) == "table"
      and type(fuel.out_of_fuel) == "boolean" and type(fuel.distress_on) == "boolean"
      and type(fuel.can_wait) == "boolean" and type(fuel.waiting) == "boolean"
      and type(Hyperspace.benchmark_wait_for_fuel) == "function"
      and type(Hyperspace.benchmark_set_distress) == "function"
    obs.capabilities.event_choice_state = type(Hyperspace.benchmark_choose_event) == "function"
    -- Individual optional probes are best-effort inside add_m3_obs. A whole
    -- snapshot failure must not publish a partial action acknowledgement.
    local m3ok, m3err = pcall(add_m3_obs, obs)
    if not m3ok then
      log_err("m3 obs error: " .. tostring(m3err))
      return false
    end
    if S.observation_mode == "visual-v1" then
      local encoded = Hyperspace.benchmark_write_visual_observation(json.encode(obs),
        S.last_applied_seq or -1, S.frame_counter, S.visual_requested_frames or 0,
        S.adv_elapsed or 0, json.encode(S.visual_feedback or {}))
      if type(encoded) ~= "string" or encoded == "" then error("native visual writer refused snapshot") end
      local metadata = json.decode(encoded)
      if type(metadata) ~= "table" or type(metadata.capture_id) ~= "string"
        or metadata.visual_io_version ~= 1 or metadata.paused ~= true
        or visual_world_updates(metadata) == nil
        or metadata.world_updates ~= visual_caps.world_updates then
        error("invalid native capture acknowledgement")
      end
      S.visual_capture = metadata
      S.visual_pending = false
    else
      local written = Hyperspace.write_json_observation(json.encode(obs))
      if written ~= true then error("native observation writer refused snapshot") end
    end
    return m3ok, type(fuel) == "table" and fuel.waiting == true
  end)
  if not ok then log_err("observation error: " .. tostring(complete)) end
  if not ok or complete ~= true then return false end
  local gui = Hyperspace.App and Hyperspace.App.gui
  local world = Hyperspace.App and Hyperspace.App.world
  S.observed_ui_signature = idle_ui_signature(gui, world)
  S.observed_frame = S.frame_counter
  -- StarMap.waiting is not exposed in SWIG. The native economy getter is the
  -- authoritative signal; keep polling at a bounded rate until it completes.
  S.observed_native_waiting = waiting == true
  return true
end

------------------------------------------------------------------
-- Per-tick state machine
------------------------------------------------------------------

-- ===== Hybrid pause: critical-event early interrupt =====
-- The bridge advances a fixed frame budget per action, BUT re-pauses EARLY if a clearly-critical
-- event fires mid-advance, so the agent never sleeps through a crisis it would want to react to:
-- combat starting, taking hull damage, a boarder coming aboard, a new fire, or an event popup.
-- All JUDGMENT stays with the agent (we don't try to define every "meaningful" moment -- only the
-- unambiguous ones); the rest is the agent's call. NEVER fires during a warp (bJumping) -- the
-- SIGBUS window -- and a jump's arrival surfaces the new combat at re-pause anyway.
local function count_intruders_fires(pl)
  local intr, fires = 0, 0
  local function scan(list)
    if not list then return end
    for i = 0, list:size() - 1 do
      local c = list[i]
      if c then pcall(function()
        if (not c.bDead) and c.currentShipId == 0 and c.iShipId ~= 0 then intr = intr + 1 end
      end) end
    end
  end
  pcall(function() scan(pl and pl.vCrewList) end)
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    if en then scan(en.vCrewList) end
  end)
  pcall(function()
    local rl = pl and pl.ship and pl.ship.vRoomList
    if rl then
      for i = 0, rl:size() - 1 do
        local rm = rl[i]
        if rm then pcall(function()
          local fc = pl:GetFireCount(rm.iRoomId)
          if fc and fc > 0 then fires = fires + 1 end
        end) end
      end
    end
  end)
  return intr, fires
end

local function danger_snapshot()
  local s = { enemy = false, hull = nil, intruders = 0, fires = 0, event = false }
  pcall(function()
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    local native = native_enemy_state(en)
    s.enemy = native.hostile == true and native.destroyed == false
    local gui = Hyperspace.App and Hyperspace.App.gui
    s.event = (gui ~= nil) and gui.choiceBoxOpen or false
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if pl and pl.ship then pcall(function() s.hull = pl.ship.hullIntegrity.first end) end
    s.intruders, s.fires = count_intruders_fires(pl)
  end)
  return s
end

-- Returns an interrupt-reason string if a critical event fired vs the baseline, else nil.
local function check_critical(base, elapsed)
  if not base then return nil end
  local reason = nil
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    if not pl or pl.bJumping then return end          -- never interrupt mid-warp
    local gui = Hyperspace.App and Hyperspace.App.gui
    if gui and gui.choiceBoxOpen and not base.event then reason = "event"; return end
    local en = Hyperspace.ships and Hyperspace.ships.enemy
    local native = native_enemy_state(en)
    if native.hostile == true and native.destroyed == false and not base.enemy then
      reason = "combat_started"; return
    end
    if base.hull then
      local h = nil
      pcall(function() h = pl.ship.hullIntegrity.first end)
      if h and h < base.hull then reason = "took_damage"; return end
    end
    if elapsed % 12 == 0 then                          -- throttle the crew/room iterations
      local intr, fires = count_intruders_fires(pl)
      if intr > base.intruders then reason = "boarder_aboard"; return end
      if fires > base.fires then reason = "fire"; return end
    end
  end)
  return reason
end


-- Visual-v1 input transport. These functions deliver normal game-window events;
-- they never infer that the UI accepted a gameplay operation.
local function integer(value) return type(value) == "number" and value == math.floor(value) end
local function visual_feedback(index, act, status, reason)
  local item = {index=index-1,type=type(act) == "table" and act.type or "unknown",status=status}
  if reason then item.reason=reason end
  S.visual_feedback[#S.visual_feedback+1] = item
end
local function visual_deliver(index, act, caps)
  if type(act) ~= "table" then visual_feedback(index,act,"rejected","invalid_action"); return end
  local modifiers = 0
  if act.modifiers ~= nil and type(act.modifiers) ~= "table" then
    visual_feedback(index,act,"rejected","invalid_modifiers"); return
  end
  local seen = {}
  for _, modifier in ipairs(act.modifiers or {}) do
    if (modifier ~= "shift" and modifier ~= "ctrl") or seen[modifier] then
      visual_feedback(index,act,"rejected","unsupported_modifier"); return
    end
    seen[modifier]=true
    modifiers=modifiers+(modifier == "shift" and 1 or 2)
  end
  local function point(x,y)
    return integer(x) and integer(y) and x >= 0 and y >= 0
      and type(caps.width) == "number" and type(caps.height) == "number"
      and x < caps.width and y < caps.height
  end
  local fn, args
  if act.type == "key" then
    if type(act.key) ~= "string" then visual_feedback(index,act,"rejected","invalid_key"); return end
    fn,args=Hyperspace.benchmark_key_press,{act.key,modifiers}
  elseif act.type == "click" or act.type == "move" or act.type == "drag" then
    if not point(act.x,act.y) or (act.type == "drag" and not point(act.to_x,act.to_y)) then
      visual_feedback(index,act,"rejected","invalid_coordinates"); return
    end
    local button = act.button or "left"
    if button ~= "left" and button ~= "right" then visual_feedback(index,act,"rejected","unsupported_button"); return end
    if act.type == "move" then
      if modifiers ~= 0 then visual_feedback(index,act,"rejected","move_modifiers_unsupported"); return end
      fn,args=Hyperspace.benchmark_mouse_move,{act.x,act.y}
    elseif act.type == "click" then
      fn,args=Hyperspace.benchmark_mouse_click,{act.x,act.y,button == "left" and 0 or 1,modifiers}
    else
      fn,args=Hyperspace.benchmark_mouse_drag,{act.x,act.y,act.to_x,act.to_y,button == "left" and 0 or 1,modifiers}
    end
  else visual_feedback(index,act,"rejected","unsupported_input"); return end
  if type(fn) ~= "function" then visual_feedback(index,act,"rejected","native_input_unavailable"); return end
  local ok, delivered = pcall(fn,table.unpack(args))
  visual_feedback(index,act,ok and delivered == true and "delivered" or "rejected",
    (not ok and "native_input_error") or (delivered ~= true and "native_input_refused") or nil)
end
local function visual_blocked()
  if type(Hyperspace.benchmark_visual_simulation_blocked) ~= "function" then return true end
  local ok, blocked = pcall(Hyperspace.benchmark_visual_simulation_blocked)
  return not ok or blocked ~= false
end

_G.ftl_bench_visual_render = function()
  if S.observation_mode ~= "visual-v1" or not S.visual_pending or S.frame_budget > 0 then return end
  set_frozen(true)
  S.visual_in_render = true
  S.obs_fresh = write_observation()
  S.visual_in_render = false
end

local function read_action_packet()
  local ok, encoded = pcall(Hyperspace.read_json_action)
  if not ok or type(encoded) ~= "string" or encoded == "" then return nil end
  local decoded, packet = pcall(json.decode, encoded)
  if decoded and type(packet) == "table" and integer(packet.seq) then return packet end
  return nil
end

-- Isolated future-cohort helper. Ordinary gameplay RNG is never reseeded here.
-- Native construction/seed receipt v3 and native clock2 are mandatory.
local function NewDeterministicSetup(S, H, json, freeze, capabilities, counter)
 local D={}
 local function integer(v) return type(v)=="number" and v==math.floor(v) end
 local function state() return S.benchmark_setup end
 local function count_string(n) return string.format("%.0f",n) end
 function D.owns() local r=state();return r~=nil and r.active==true end
 local function fail(message)
  local r=state()
  if r then r.error=message;r.phase="failed";r.active=true end
  S.frame_budget=0
  pcall(H.benchmark_visual_set_clock,true,false)
  if H.App and H.App.gui then H.App.gui.bPaused=true end
  return false
 end
 local function clock()
  local caps=capabilities();local n=counter(caps)
  if n==nil then fail("clock2 counter unavailable");return nil end
  return n
 end
 local function idle_counter_valid()
  local r=state()
  if r and r.active and r.phase=="ready" and not r.pending then
   local now=clock();if now==nil then return false end
   if count_string(now)~=r.clock.current_world_updates then return fail("unbudgeted idle setup update") end
  end
  return true
 end
 local function permit(advance)
  local ok,accepted=pcall(H.benchmark_visual_set_clock,true,advance)
  if not ok or accepted~=true then return fail("clock ownership refused") end
  freeze(not advance)
  return true
 end
 local function stage()
  local ok,value=pcall(H.benchmark_fresh_menu_stage)
  if not ok or type(value)~="string" then fail("native menu stage unavailable");return nil end
  return value
 end
 local function capture_native_receipt()
  local r=state()
  local ok,payload=pcall(H.benchmark_fresh_seed_receipt)
  local decoded,native=pcall(json.decode,ok and payload or "")
  r.native_seed_receipt={call_succeeded=ok,raw_response=tostring(payload),
   parse_succeeded=decoded and type(native)=="table"}
  if decoded and type(native)=="table" then r.native_seed=native;return native end
  r.native_seed_receipt.parse_error=tostring(native)
  return nil
 end
 -- Evidence only: every binding read is protected, and no value influences
 -- admission, native timing, or the number of forward calls.
 local function menu_snapshot()
  local out={contract="menu-binding-diagnostic-v1",errors={}}
  local function read(label,fn)
   local ok,value=pcall(fn)
   if not ok or value==nil then
    out.errors[#out.errors+1]={field=label,error=ok and "binding returned nil" or tostring(value)}
    return nil
   end
   return value
  end
  local function scalar(label,fn)
   local value=read(label,fn)
   if value~=nil then
    if type(value)=="number" or type(value)=="boolean" or type(value)=="string" then out[label]=value
    else out[label]=tostring(value) end
   end
  end
  local app=read("app",function() return H.Global.GetInstance():GetCApp() end)
  local menu=read("menu",function() return app.menu end)
  local button=read("start_button",function() return menu.startButton end)
  scalar("start_button_identity",function() return tostring(button) end)
  for _,field in ipairs({"bActive","bHover"}) do
   scalar("start_button_"..field,function() return button[field] end)
  end
  for _,part in ipairs({"hitbox","position"}) do
   local object=read("start_button_"..part,function() return button[part] end)
   local fields=part=="hitbox" and {"x","y","w","h"} or {"x","y"}
   for _,field in ipairs(fields) do
    scalar("start_button_"..part.."_"..field,function() return object[field] end)
   end
  end
  for _,field in ipairs({"bOpen","bScoreScreen","bCreditScreen","bSelectSave","finalChoice","bNewGame"}) do
   scalar("menu_"..field,function() return menu[field] end)
  end
  for _,field in ipairs({"confirmNewGame","shipBuilder","optionScreen","changelog"}) do
   scalar("menu_"..field.."_open",function() return menu[field].bOpen end)
  end
  scalar("language_chooser_open",function() return app.langChooser.bOpen end)
  local buttons=read("menu_buttons",function() return menu.buttons end)
  scalar("menu_buttons_count",function() return buttons:size() end)
  out.menu_button_identities={}
  local n=out.menu_buttons_count
  if type(n)=="number" and n>=0 and n==math.floor(n) then
   out.menu_buttons_truncated=n>128
   for index=0,math.min(n,128)-1 do
    local item=read("menu_button_"..index,function() return buttons[index] end)
    local row={index=index}
    if item~=nil then
     row.identity=tostring(item)
     local equal=read("menu_button_"..index.."_is_start",function() return item==button end)
     if equal~=nil then row.is_start=equal end
    end
    out.menu_button_identities[#out.menu_button_identities+1]=row
   end
  end
  return out
 end
 local function capture_menu_snapshot()
  local ok,value=pcall(menu_snapshot)
  if ok then return value end
  return {contract="menu-binding-diagnostic-v1",errors={{field="snapshot",error=tostring(value)}}}
 end
 local function native_seed(applied)
  local r=state();local native=capture_native_receipt()
  if type(native)~="table"
   or native.contract~="fresh-start-seed-v3" or native.contract_version~=3
   or native.seed~=r.seed or native.failed~=false
   or not integer(native.epoch) or native.epoch<1 then
   fail("native fresh seed receipt invalid");return nil
  end
  if r.native_epoch and native.epoch~=r.native_epoch then fail("native seed epoch changed");return nil end
  if native.utility_name_calls~=1 or native.utility_lookup_calls~=1 or native.utility_lookup_completed~=1
   or native.utility_lookup_valid~=true
   or native.utility_name_provenance~="StatBoostManager::CreateDummyCrew.GetCrewBlueprint(human)"
   or type(native.utility_name)~="string" or native.utility_name==""
   or not integer(native.utility_thread_id) or native.utility_thread_id<1
   or native.names_before_arm~=1 or native.unclassified_names_before_arm~=0
   or native.intervening_names_after_arm~=0 or native.ship_inits_before_arm~=0
   or native.reservations_before_arm~=1 then
   fail("classified utility construction evidence invalid");return nil
  end
  for _,kind in ipairs({"crew","lost","player","enemy","clone"}) do
   if native["factory_"..kind.."_before_arm"]~=0 or applied and native["factory_"..kind.."_before_reset"]~=0 then
    fail("preexisting crew factory construction");return nil
   end
  end
  if r.utility_name and (native.utility_name~=r.utility_name or native.utility_thread_id~=r.utility_thread) then
   fail("classified utility identity changed");return nil
  end
  r.utility_name=native.utility_name;r.utility_thread=native.utility_thread_id
  if applied then
   if native.applied~=true or native.pending~=false
    or native.native_seed_applications~=1 or native.c_runtime_seed_applications~=1
    or native.boundary~="ShipBuilder::Open.before_super"
    or native.constructor_timing_controlled~=true or native.fixed_creation_timing~=true
    or native.construction_clock_owned~=true
    or native.construction_fixed_step_numerator~=1 or native.construction_fixed_step_denominator~=60
    or native.construction_speed_factor_bits~=1049135241
    or native.construction_scope_active~=false
    or not integer(native.construction_clicks) or native.construction_clicks<1
    or native.completed_construction_clicks~=native.construction_clicks
    or not integer(native.seed_thread_id) or native.seed_thread_id<1
    or native.utility_thread_id~=native.seed_thread_id
    or native.names_before_seed~=1 or native.unclassified_names_before_seed~=0
    or native.ship_inits_before_seed~=0
    or native.reservations_before_reset~=1 or native.reservations_after_reset~=0
    or native.reservation_reset_applications~=1 or native.reservation_reset_verified~=true
    or native.reservation_reset_thread_id~=native.seed_thread_id
    or type(native.reservation_names_before_reset)~="table"
    or #native.reservation_names_before_reset~=1 or native.reservation_names_before_reset[1]~=native.utility_name
    or not integer(native.names_during_open) or native.names_during_open<1 then
    fail("construction seed evidence incomplete");return nil
   end
   if r.native_thread and native.seed_thread_id~=r.native_thread then fail("native seed thread changed");return nil end
   r.native_thread=native.seed_thread_id
  elseif native.pending~=true or native.applied~=false
   or native.native_seed_applications~=0 or native.c_runtime_seed_applications~=0
   or native.reservation_reset_applications~=0 or native.reservation_reset_verified~=false
   or native.names_before_seed~=0 or native.unclassified_names_before_seed~=0
   or native.ship_inits_before_seed~=0 then
   fail("fresh seed no longer pending");return nil
  end
  r.native_epoch=native.epoch;r.native_seed=native
  return native
 end
 local function arm()
  local r=state();local current=stage()
  r.admission_stage=current
  if current~="main_menu" and current~="overwrite_confirmation" then return fail("unsafe fresh construction boundary") end
  local ok,accepted=pcall(H.benchmark_arm_fresh_seed,r.seed)
  r.arm_call={succeeded=ok,accepted=accepted==true,response=tostring(accepted)}
  if not ok or accepted~=true then
   capture_native_receipt()
   return fail("fresh native seed arm refused")
  end
  r.phase="menu"
  return native_seed(false)~=nil
 end
 function D.admit(packet)
  if packet.benchmark_setup==nil then return true end
  if state() then return fail("setup opt-in cannot be rearmed") end
  local request=packet.benchmark_setup
  local action=type(packet.actions)=="table" and #packet.actions==1 and packet.actions[1] or nil
  S.benchmark_setup={contract="deterministic-setup-v1",version=1,active=true,
   phase="admitting",intervals={},menu_stages={},determinism_claimed=false,
   start_action_seq=packet.seq,seed=type(request)=="table" and request.seed or nil}
  if type(request)~="table" or request.version~=1 or request.fresh~=true
   or not integer(request.seed) or request.seed<0 or request.seed>4294967295
   or packet.advance_frames~=0 or not action or action.seed~=request.seed
   or not (action.type=="reset_episode" or (action.type=="start_game" and action.mode=="new")) then
   return fail("explicit single fresh setup request required")
  end
  local ok,version=pcall(H.benchmark_fresh_seed_contract_version)
  if not ok or version~=3 then return fail("fresh native seed contract3 unavailable") end
  if not permit(false) then return false end
  S.observation_mode="structured-v7";S.visual_pending=false;S.visual_capture=nil
  local n=clock();if n==nil then return false end
  local r=state();r.clock={version=2,numerator=1,denominator=60,initial_world_updates=count_string(n),current_world_updates=count_string(n)}
  local current=stage()
  if action.type=="reset_episode" and current=="in_game" then
   r.phase="resetting";r.reset_steps=0;return true
  end
  _G.ftl_bench_desired_seed=r.seed
  if not arm() then return false end
  S.starting_new=true;S.menu_throttle=0
  return true
 end
 function D.guard(packet)
  local r=state();if not r or not r.active or not packet then return true end
  if r.error then return false end
  if not idle_counter_valid() then return false end
  if not integer(packet.advance_frames) or packet.advance_frames<0 or packet.advance_frames>600
   or type(packet.actions)~="table" then return fail("invalid explicit setup packet budget or actions") end
  if packet.benchmark_setup and packet.seq~=r.start_action_seq then return fail("duplicate setup request") end
  if packet.seq==r.start_action_seq then return true end
  for _,action in ipairs(packet.actions or {}) do
   if action.type=="set_seed" or action.type=="reset_episode" or action.type=="start_game" then
    return fail("fresh lifecycle action during setup")
   end
  end
  return true
 end
 function D.menu()
  local r=state();if not r or not r.active then return false end
  if r.error then return false end
  if r.phase=="resetting" then
   if r.pending then
    local now=clock();if now==nil then return false end
    local row=r.pending;local delta=now-tonumber(row.start_world_updates)
    if delta<0 or delta>row.requested_updates then return fail("reset interval counter mismatch") end
    row.end_world_updates=count_string(now);row.actual_updates=delta;row.status="menu_boundary";r.pending=nil
   end
   if not permit(false) or not arm() then return false end
  end
  -- No uncontrolled hangar OnLoop between opening and Start. Asynchronous
  -- paths fail closed instead of waiting under an unaccounted UI clock.
  for _=1,3 do
   local current=stage()
   if current~="main_menu" and current~="overwrite_confirmation" and current~="hangar" then
    return fail("unsupported stage in fresh menu chain")
   end
   local native=native_seed(current=="hangar");if not native then return false end
   local before=clock();if before==nil then return false end
   r.menu_diagnostics=r.menu_diagnostics or {}
   local diagnostic={index=#r.menu_diagnostics+1,stage=current,before=capture_menu_snapshot()}
   r.menu_diagnostics[#r.menu_diagnostics+1]=diagnostic
   local ok,accepted=pcall(H.benchmark_advance_fresh_menu)
   diagnostic.after=capture_menu_snapshot()
   diagnostic.forward_call_succeeded=ok;diagnostic.forward_call_accepted=accepted==true
   -- Freeze in the SAME callback, before any next CApp/world/render iteration.
   if not permit(false) then return false end
   if not ok or accepted~=true then
    r.forward_call={succeeded=ok,accepted=accepted==true,response=tostring(accepted),stage=current}
    capture_native_receipt()
    return fail("native scoped forward click refused")
   end
   local after=clock();if after==nil then return false end
   if after~=before then return fail("unbudgeted world update during construction") end
   local next_stage=stage()
   r.menu_stages[#r.menu_stages+1]={before=current,after=next_stage,world_updates_before=count_string(before),world_updates_after=count_string(after)}
   if current=="hangar" then
    if next_stage~="start_pending" or H.App.world.bStartedGame then return fail("Start must enter the controlled native completion boundary") end
    local pending=native_seed(true);if not pending then return false end
    if pending.start_pending~=true or pending.start_completed~=false then return fail("native Start completion was not armed") end
    r.creation_pending={start_action_seq=r.start_action_seq,world_updates_before_start=count_string(before)}
    r.phase="starting";r.clock.current_world_updates=count_string(after);return true
   end
   if next_stage==current then return fail("fresh menu chain made no synchronous progress") end
  end
  return fail("fresh menu chain exceeded three forward clicks")
 end
 function D.start_pending() local r=state();return r and r.active and r.phase=="starting" end
 function D.complete_start()
  local r=state();if not D.start_pending() or r.error then return fail("no pending Start completion") end
  local current=stage();local native=native_seed(true);local now=clock()
  if not native or now==nil then return false end
  local before=r.creation_pending.world_updates_before_start
  if current~="in_game" or not H.App.world.bStartedGame
   or native.start_pending~=false or native.start_completed~=true
   or native.start_completion_callbacks~=1 or native.start_extra_hangar_dwell~=0
   or native.start_hangar_onloop_requests~=1 or native.start_hangar_onloop_executed~=0
   or native.start_game_calls~=1 or native.start_game_returns~=1
   or native.start_cfps_fixed_applications~=1 or native.start_speed_factor_bits~=1049135241
   or native.start_thread_id~=native.seed_thread_id
   or native.start_world_updates_before~=before or native.start_world_updates_after~=before
   or native.start_timing_controlled~=true or native.start_world_frozen~=true
   or count_string(now)~=before then
   return fail("controlled next-loop Start completion invalid or late")
  end
  if not permit(false) then return false end
  r.creation={start_action_seq=r.start_action_seq,world_updates_before_start=before,
   world_updates_after_start=count_string(now),frozen_immediately=true,zero_unbudgeted_world_updates=true,
   completion_callbacks=1,extra_hangar_dwell=0}
  r.phase="ready";r.clock.current_world_updates=count_string(now);return true
 end
 function D.begin_interval(seq,requested,kind,defer)
  local r=state();if not r or not r.active then return true end
  if r.error or r.pending then return fail("setup interval overlaps or follows failure") end
  if not integer(requested) or requested<0 or requested>600 then return fail("setup budget must be an integer in 0..600") end
  if not idle_counter_valid() then return false end
  local now=clock();if now==nil then return false end
  local row={index=#r.intervals+1,kind=kind or "structured",action_seq=seq,requested_updates=requested,
   start_world_updates=count_string(now),end_world_updates=count_string(now),actual_updates=0,status=requested==0 and "complete" or "pending"}
  r.intervals[#r.intervals+1]=row;r.pending=requested>0 and row or nil
  r.clock.current_world_updates=count_string(now)
  return permit(requested>0 and not defer)
 end
 function D.dispatch_complete()
  local r=state();local row=r and r.intervals[#r.intervals]
  if not row or r.error then return fail("setup dispatch without interval") end
  local now=clock();if now==nil then return false end
  if now~=tonumber(row.start_world_updates) then return fail("unbudgeted update during semantic dispatch") end
  return permit(row.requested_updates>0)
 end
 function D.advance_interval()
  local r=state();local row=r and r.pending
  if not row or r.error then return fail("no pending setup interval") end
  local now=clock();if now==nil then return false end
  local delta=now-tonumber(row.start_world_updates)
  row.end_world_updates=count_string(now);row.actual_updates=delta;r.clock.current_world_updates=count_string(now)
  if delta<0 or delta>row.requested_updates then row.status="failed";return fail("setup clock regression or overrun") end
  S.adv_elapsed=delta;S.frame_budget=row.requested_updates-delta
  if S.frame_budget==0 then row.status="complete";r.pending=nil;return permit(false) end
  return true
 end
 function D.reset_tick()
  local r=state();if not r or r.error or r.phase~="resetting" then return false end
  if r.pending then
   if not D.advance_interval() then return false end
   if r.pending then return true end
   r.reset_steps=r.reset_steps+1
  end
  if r.reset_steps>=600 then return fail("reset transition exceeded fixed budget") end
  if r.reset_steps%10==0 then
   local gui=H.App.gui
   if gui.choiceBoxOpen then
    return fail("reset with event modal requires explicit prior event resolution")
   end
   local a=pcall(H.benchmark_return_to_menu);local b=pcall(H.benchmark_confirm_menu)
   if not a or not b then return fail("native reset menu command failed") end
  end
  return D.begin_interval(r.start_action_seq,1,"reset")
 end
 function D.handoff(seq)
  local r=state();if not r or not r.active then return true end
  if r.error or r.phase~="ready" or r.pending then return fail("visual handoff before fixed setup completion") end
  local now=clock();local native=native_seed(true)
  if now==nil or not native then return false end
  if native.start_completion_scope_active~=false then return fail("visual handoff during Start completion scope") end
  -- Called only AFTER visual mode assignment; the visual owner now retains it.
  r.handoff={action_seq=seq,world_updates=count_string(now)};r.phase="visual";r.active=false
  return true
 end
 function D.failed() local r=state();return r and r.error~=nil end
 D.reject=fail
 function D.observe()
  local r=state();if not r then return nil end
  idle_counter_valid()
  local caps=capabilities();local now=counter(caps)
  if now and r.clock then r.clock.current_world_updates=count_string(now) end
  return r
 end
 return D
end

DeterministicSetup=NewDeterministicSetup(S,Hyperspace,json,set_frozen,visual_capabilities,visual_world_updates)

local function visual_tick(packet)
  local current_caps = S.observation_mode == "visual-v1" and visual_capabilities() or nil
  local changed_input = S.visual_capture and current_caps
    and current_caps.external_input_generation ~= S.visual_capture.external_input_generation
  if changed_input then S.obs_fresh=false end -- publish contamination even while waiting for the model
  if S.observation_mode == "visual-v1" and S.frame_budget > 0 then
    local updates=visual_world_updates(current_caps)
    if updates == nil or S.visual_start_world_updates == nil or updates < S.visual_start_world_updates then
      S.visual_request_error="visual_clock_unavailable"; S.frame_budget=0
    else
      S.adv_elapsed=updates-S.visual_start_world_updates
      S.frame_budget=math.max(0,S.visual_requested_frames-S.adv_elapsed)
    end
    -- Only visible blocking UI stops this mode; no hidden damage/crew/kill gates.
    if not current_caps or current_caps.external_input_guard ~= true then
      S.visual_request_error="external_input_guard_unavailable"; S.frame_budget=0
    elseif changed_input or current_caps.external_input_detected == true then
      S.visual_request_error="external_input_since_capture"; S.frame_budget=0
    elseif S.adv_elapsed > S.visual_requested_frames then
      S.visual_request_error="visual_clock_overrun"; S.frame_budget=0
    elseif visual_blocked() then S.frame_budget=0 end
    if S.frame_budget == 0 then set_frozen(true); S.obs_fresh=write_observation() end
    return true
  end
  local fresh=packet ~= nil
    and (S.last_applied_seq == nil or packet.seq > S.last_applied_seq)
  if fresh and packet.observation_mode == "structured-v7" then
    S.observation_mode="structured-v7"; S.visual_pending=false; S.visual_capture=nil
    if type(Hyperspace.benchmark_visual_set_clock) == "function" then
      pcall(Hyperspace.benchmark_visual_set_clock,DeterministicSetup.owns(),false)
    end
    return false -- backstage reset/menu handling remains in the historical path
  end
  if not (fresh and packet.observation_mode == "visual-v1") and S.observation_mode ~= "visual-v1" then return false end
  set_frozen(true)
  if fresh then
    S.observation_mode="visual-v1"
    S.manual_fire={} -- visual input owns normal native weapon queues from now on
    S.last_applied_seq=packet.seq
    S.action_feedback={}
    S.visual_feedback={}
    S.visual_request_error=nil
    S.visual_requested_frames=packet.advance_frames or 0
    S.adv_elapsed=0
    local actions=type(packet.actions) == "table" and packet.actions or {}
    local caps=visual_capabilities()
    local reason=nil
    if type(packet.actions) ~= "table" then reason="invalid_actions"
    elseif not integer(S.visual_requested_frames) or S.visual_requested_frames < 0 or S.visual_requested_frames > 600 then reason="invalid_frame_budget"
    elseif #actions > 4 then reason="too_many_inputs"
    elseif not caps then reason="visual_io_unavailable"
    elseif visual_world_updates(caps) == nil or type(Hyperspace.benchmark_visual_set_clock) ~= "function" then reason="visual_clock_unavailable"
    elseif caps.external_input_guard ~= true or type(caps.external_input_generation) ~= "string"
      or type(caps.external_input_detected) ~= "boolean" then reason="external_input_guard_unavailable"
    elseif caps.external_input_detected == true or (S.visual_capture
      and caps.external_input_generation ~= S.visual_capture.external_input_generation) then reason="external_input_since_capture"
    elseif packet.expected_capture_id ~= nil and (not S.visual_capture or packet.expected_capture_id ~= S.visual_capture.capture_id) then reason="stale_capture"
    elseif (#actions > 0 or S.visual_requested_frames > 0) and (not S.visual_capture or packet.expected_capture_id == nil) then reason="capture_required"
    elseif (#actions > 0 or S.visual_requested_frames > 0) and packet.expected_external_input_generation == nil then reason="external_input_generation_required"
    elseif packet.expected_external_input_generation ~= nil and
      (not S.visual_capture or packet.expected_external_input_generation ~= S.visual_capture.external_input_generation
        or packet.expected_external_input_generation ~= caps.external_input_generation) then reason="external_input_generation_mismatch"
    elseif S.visual_capture and (caps.width ~= S.visual_capture.width or caps.height ~= S.visual_capture.height) then reason="capture_dimensions_changed" end
    if reason then
      S.visual_request_error=reason
      for index,act in ipairs(actions) do visual_feedback(index,act,"rejected",reason) end
      if reason == "invalid_frame_budget" then S.visual_requested_frames=0 end
      S.frame_budget=0 -- stale/invalid packets never invoke handlers or advance time
    else
      if DeterministicSetup.owns() and not DeterministicSetup.handoff(packet.seq) then
        S.visual_request_error="deterministic_setup_handoff_failed";S.frame_budget=0
        S.obs_fresh=write_observation();return true
      end
      for index,act in ipairs(actions) do visual_deliver(index,act,caps) end
      S.visual_start_world_updates=visual_world_updates(caps)
      S.frame_budget=S.visual_requested_frames
      if visual_blocked() then S.frame_budget=0 end
    end
    if S.frame_budget > 0 then set_frozen(false); S.obs_fresh=false; return true end
    set_frozen(true) -- a delivered Space key cannot run through model latency
    S.obs_fresh=write_observation()
  elseif not S.obs_fresh then S.obs_fresh=write_observation() end
  return true
end

_G.ftl_bench_tick = function()
  S.frame_counter = S.frame_counter + 1
  if S.err_cooldown > 0 then S.err_cooldown = S.err_cooldown - 1 end

  local gui = Hyperspace.App and Hyperspace.App.gui
  if not gui then return end
  -- Atomic publication can replace the file during this tick. Route one decoded
  -- snapshot throughout, so a new visual packet cannot be consumed by a later
  -- historical handler after visual admission inspected the previous packet.
  local action = read_action_packet()
  local fresh_setup=action and action.benchmark_setup and (S.last_applied_seq==nil or action.seq>S.last_applied_seq)
  if fresh_setup and not DeterministicSetup.admit(action) then
    S.last_applied_seq=action.seq;S.obs_fresh=write_observation();return
  end
  if not DeterministicSetup.guard(action) or DeterministicSetup.failed() then
    if action then S.last_applied_seq=action.seq end
    S.obs_fresh=write_observation();return
  end
  if DeterministicSetup.start_pending() then
    DeterministicSetup.complete_start();S.starting_new=false
    S.obs_fresh=write_observation();return
  end
  if visual_tick(action) then return end

  -- Only gate during an actual run; at the menu/hangar, stream without freezing.
  local world = Hyperspace.App.world
  local in_game = (world ~= nil) and world.bStartedGame or false
  if not in_game then
    S.frame_budget = 0
    S.manual_fire = {}
    -- A reset_episode that has reached the menu: kick off a fresh seeded game.
    if S.resetting then
      _G.ftl_bench_desired_seed = S.reset_seed
      S.starting_new = true
      S.menu_throttle = 0
      S.resetting = false
    end
    -- Autonomy: let the harness start/continue a game from the menu (no click).
    if action then
      if action.seq ~= nil
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
        S.action_feedback = {}
      end
    end
    -- New game is a 3-click flow (New Game -> CONFIRM -> hangar Start); step it
    -- every ~25 ticks so each screen has time to transition before the next click.
    if S.starting_new and DeterministicSetup.owns() then
      local set_ok,accepted=pcall(Hyperspace.benchmark_set_difficulty,0)
      local get_ok,difficulty=pcall(Hyperspace.benchmark_difficulty)
      if not set_ok or accepted~=true or not get_ok or difficulty~=0 then
        DeterministicSetup.reject("canonical difficulty unavailable")
      elseif DeterministicSetup.menu() then S.starting_new=false end
    elseif S.starting_new then
      S.menu_throttle = (S.menu_throttle or 0) + 1
      if S.menu_throttle % 25 == 0 then
        -- Canonical benchmark starts on easy. Set it only in the menu and verify
        -- the native setting before any click can create the seeded world.
        local set_ok, accepted = pcall(Hyperspace.benchmark_set_difficulty, 0)
        local get_ok, difficulty = pcall(Hyperspace.benchmark_difficulty)
        if set_ok and accepted == true and get_ok and difficulty == 0 then
          pcall(Hyperspace.benchmark_advance_menu)
        else
          log_err("cannot verify canonical easy difficulty before new game")
        end
      end
    end
    S.obs_fresh = false
    write_observation()
    return
  end
  if S.starting_new and S.reset_pending_seq then
    -- the NEW seeded game from a reset_episode has just loaded: stamp a marker the harness can wait
    -- on, robust to a laggy/bind-mounted obs that misses the brief game_started false->true window.
    S.reset_done_seq = S.reset_pending_seq
    S.reset_pending_seq = nil
  end
  S.starting_new = false   -- in a run now; stop driving the menu

  -- reset_episode: abandon this run back to the main menu (the menu-guard above
  -- then launches a fresh seeded game). Runs UNFROZEN so the transition plays out.
  if S.resetting then
    S.manual_fire = {}
    if DeterministicSetup.owns() then
      DeterministicSetup.reset_tick();S.obs_fresh=write_observation();return
    end
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

  -- Cancel stale surrender targets while still paused, before an empty wait can
  -- unfreeze a fully charged queued weapon for its first native simulation frame.
  cancel_unavailable_manual_fire()
  if S.frame_budget > 0 then
    if DeterministicSetup.owns() then
      update_manual_fire()
      DeterministicSetup.advance_interval()
      if S.frame_budget==0 then S.obs_fresh=write_observation() end
      return
    end
    update_manual_fire()
    S.frame_budget = S.frame_budget - 1
    S.adv_elapsed = (S.adv_elapsed or 0) + 1
    -- HYBRID pause: after a MINIMUM beat (MIN_STEP_FRAMES), end the advance EARLY on a critical
    -- event so the agent gets a turn to react (combat start / hull damage / boarder / fire /
    -- event). The minimum stops a fight being chopped into ~18-frame slivers by chip damage. Not
    -- mid-warp (check_critical excludes bJumping).
    if S.frame_budget > 0 and S.adv_elapsed >= MIN_STEP_FRAMES then
      local r = check_critical(S.danger0, S.adv_elapsed)
      if r then S.frame_budget = 0; S.interrupt_reason = r end
    end
    if S.frame_budget == 0 then
      set_frozen(true)
      S.obs_fresh = write_observation()  -- failed snapshots remain dirty for retry
    end
    return
  end

  set_frozen(true)

  local applied = false
  if action then
    if action.seq ~= nil
       and (S.last_applied_seq == nil or action.seq > S.last_applied_seq) then
      local is_reset = false
      for _, act in ipairs(action.actions or {}) do
        if act.type == "reset_episode" then
          is_reset = true
          S.resetting = true
          S.reset_throttle = 0
          S.reset_seed = act.seed
          S.reset_pending_seq = action.seq   -- mark THIS reset so we can confirm its new game loaded
        end
      end
      S.last_applied_seq = action.seq
      S.action_feedback = {}
      if not is_reset then
        if DeterministicSetup.owns() and not DeterministicSetup.begin_interval(action.seq,action.advance_frames,"structured",true) then
          S.obs_fresh=write_observation();return
        end
        local aok, aerr = pcall(dispatch_actions, action.actions)
        if not aok then
          if DeterministicSetup.owns() then
            DeterministicSetup.reject("setup dispatch error: "..tostring(aerr));S.obs_fresh=write_observation();return
          end
          log_err("dispatch error: " .. tostring(aerr))
        end
        applied = true
        S.frame_budget = action.advance_frames or 30
        if DeterministicSetup.owns() and not DeterministicSetup.dispatch_complete() then
          S.obs_fresh=write_observation();return
        end
        if S.frame_budget > 0 then
          -- hybrid pause: snapshot the danger baseline so check_critical can detect a crisis
          -- developing during this advance and re-pause early. Clear the prior interrupt flag.
          S.danger0 = danger_snapshot()
          S.adv_elapsed = 0
          S.interrupt_reason = nil
          set_frozen(false)
          S.obs_fresh = false      -- about to advance; rebuild fresh on re-freeze
          return
        end
      end
    end
  end

  local ui_signature = idle_ui_signature(gui, world)
  local ui_changed = ui_signature ~= S.observed_ui_signature
  local waiting_refresh = S.observed_native_waiting and S.frame_counter - (S.observed_frame or 0) >= 12
  -- Stable paused ships keep their cached snapshot. Native GUI transitions and
  -- explicit Wait turns can still progress; refresh on transition and at a
  -- bounded interval while waiting. A failed read/write never makes the cache fresh.
  if applied or not S.obs_fresh or ui_changed or waiting_refresh then
    S.obs_fresh = write_observation()
  end
end

print("[ftl_bench] dev script loaded (M2 turn-based loop)")
