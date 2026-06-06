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

-- Spend scrap to raise a system's MAX power by one (the Upgrade screen, available anytime).
-- UpgradeSystem only raises the cap; we deduct scrap via ModifyScrapCount so it isn't free.
-- Cost approximates FTL's escalating per-level upgrade price (indexed by the new level).
local UPGRADE_COST = {30, 30, 40, 45, 55, 60, 70, 80, 90, 100, 110, 120, 130, 150}
local function apply_upgrade_system(mgr, act)
  local sys = mgr:GetSystem(act.system_id)
  if not sys then return end
  local cur = sys:GetMaxPower()
  local maxlv = sys.maxLevel or 8
  if cur >= maxlv then return end                          -- already maxed
  local cost = UPGRADE_COST[math.min(cur + 1, #UPGRADE_COST)] or 100
  if (mgr.currentScrap or 0) < cost then return end        -- can't afford
  pcall(function() mgr:ModifyScrapCount(-cost, false) end)
  pcall(function() sys:UpgradeSystem(1) end)
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
  local slot = act.weapon_slot or 0
  local ship_id = act.target_ship_id or 1
  local room = act.target_room_id or 0
  -- The C++ binding arms the weapon, sets a persistent target, and turns on global
  -- autofire -- but it only supplies ONE target point. Multi-shot weapons need
  -- NumTargetsRequired() points (Burst Laser II: 3 shots -> 3 points); with too few
  -- they stay powered + fully charged + fire_when_ready yet NEVER release a shot
  -- (the "burst laser ready but won't fire" bug). Top up the aim points here so every
  -- shot of a burst weapon targets the chosen room.
  Hyperspace.benchmark_fire_weapon(slot, ship_id, room)
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    local target = (ship_id == 0) and pl or (Hyperspace.ships and Hyperspace.ships.enemy)
    if not (pl and target) then return end
    local pf = pl:GetWeaponList()[slot]
    if not pf then return end
    local need = pf:NumTargetsRequired()
    if not need or need <= pf.targets:size() then return end
    local center = target:GetRoomCenter(room)
    while pf.targets:size() < need do
      pf.targets:push_back(center)
    end
  end)
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
  pcall(Hyperspace.benchmark_fire_beam, slot, ship_id, room_a, room_b)
  pcall(function()
    local pl = Hyperspace.ships and Hyperspace.ships.player
    local target = (ship_id == 0) and pl or (Hyperspace.ships and Hyperspace.ships.enemy)
    if not (pl and target) then return end
    local pf = pl:GetWeaponList()[slot]
    if not pf or not pf.powered then return end
    if pf:NumTargetsRequired() ~= 2 then return end  -- not a beam: leave it alone
    local ca = target:GetRoomCenter(room_a)
    local cb = target:GetRoomCenter(room_b)
    while pf.targets:size() > 0 do pf.targets:pop_back() end
    pf.targets:push_back(ca)
    pf.targets:push_back(cb)
  end)
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
  for _, act in ipairs(actions or {}) do
    pcall(record_action, act)   -- log to the on-screen overlay (never let logging break dispatch)
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
    elseif act.type == "store_buy" then
      pcall(Hyperspace.benchmark_store_buy, act.index or 0)   -- buy store item #index
    elseif act.type == "store_sell" then
      pcall(Hyperspace.benchmark_store_sell, act.index or 0)  -- sell player item #index
    elseif act.type == "upgrade_system" then
      -- spend scrap to raise a system's max power (the Upgrade screen, available anytime).
      -- IncreasePower can't exceed power_max, so an upgrade is how you get e.g. a 2nd shield
      -- layer. UpgradeSystem raises the cap; deduct the scrap so it isn't free.
      if mgr then apply_upgrade_system(mgr, act) end
    elseif act.type == "cloak" then
      if mgr then apply_cloak(mgr, act) end           -- engage cloaking (id 10)
    elseif act.type == "set_doors" then
      apply_set_doors(act)                            -- open/close doors to vent O2 (id 8)
    elseif act.type == "mind_control" then
      apply_mind_control(act)                         -- mind-control enemy crew (id 14)
    elseif act.type == "battery" then
      if mgr then apply_battery(mgr, act) end          -- backup battery: temp reactor power (id 12)
    elseif act.type == "fire_beam" then
      apply_fire_beam(act)                            -- two-point beam sweep
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

  -- jump_charged: is it safe to initiate a jump now? (recharged in combat / always OK out)
  pcall(function() obs.jump_charged = jump_ready(Hyperspace.ships and Hyperspace.ships.player) end)
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
  -- jump_timer is ShipManager's std::pair<float,float> {first=current, second=max}; the same
  -- field jump_ready() gates on (first >= second). NOTE: out of combat the timer sits idle
  -- (e.g. 0/85) so pct reads ~0.0 even though you can jump freely -- pct is an IN-COMBAT
  -- progress bar; gate actual jump decisions on jump_charged, not pct.
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
    for i = 0, cl:size() - 1 do
      local c = cl[i]
      if c then pcall(function()
        if c.iShipId == 1 and not c:IsDead() and not c:OutOfGame() then
          local r = c.iRoomId
          local e = counts[r] or { room_id = r, crew = 0, controllable = 0 }
          e.crew = e.crew + 1
          if not c:IsDrone() and not c:IsTelepathic() and not c.bMindControlled then
            e.controllable = e.controllable + 1
          end
          counts[r] = e
        end
      end) end
    end
    local rooms = {}
    for _, e in pairs(counts) do rooms[#rooms + 1] = e end
    obs.enemy_ship.rooms_with_crew = rooms
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
    pcall(function() h.system_locked = (hs.iLockCount ~= -1) end) -- our hacking ion-locked
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
        -- autofiring: the RELIABLE "this weapon is armed and will fire at its target when
        -- charged" flag (set true by the benchmark fire path's SetAutoFire). currentShipTarget
        -- is left nil by that path, so has_target flickers false even after a successful fire —
        -- which made an agent re-issue `fire` every turn (fire-spam). Prefer autoFiring.
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
          ow.is_beam     = (pf:NumTargetsRequired() == 2) or (tname == "BEAM")
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
            e.is_beam     = (w:NumTargetsRequired() == 2) or (tname == "BEAM")
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

    -- (b) enrich own crew with current task + species + key skills (man the right station; see
    -- who is already busy repairing/fighting). Skill ids: 0 pilot,1 engine,2 shield,3 weapon,
    -- 4 repair,5 combat (best-effort: kept only when GetSkillLevel returns a number).
    if obs.player_ship.crew then
      local cl = pl.vCrewList
      if cl then
        for i = 0, cl:size() - 1 do
          local c = cl[i]; local oc = obs.player_ship.crew[i + 1]
          if c and oc then
            pcall(function() oc.species = c.species end)
            pcall(function() oc.intruder = c.intruder end)            -- true if THIS crew is boarding the enemy
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

    -- (d) FIRES per room (send crew to extinguish). GetFireCount(roomId)>0 = burning.
    local fires = {}
    local ship = pl.ship
    if ship and ship.vRoomList then
      local rl = ship.vRoomList
      for i = 0, rl:size() - 1 do
        local rm = rl[i]
        if rm then pcall(function()
          local rid = rm.iRoomId
          local fc = pl:GetFireCount(rid)
          if fc and fc > 0 then fires[#fires + 1] = { room_id = rid, fires = fc } end
        end) end
      end
    end
    obs.player_ship.fires = fires
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
    -- game_over: the run has ended (all crew dead / ship lost). NOT a crash and NOT hull<=0
    -- for crew-death, so this is the only reliable terminal signal — the harness uses it to
    -- end/reset the episode instead of spinning no-op actions at the GAME OVER screen.
    obs.game_over = (gui ~= nil and gui.gameover) or false
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
    s.enemy = (en ~= nil) and (not en.bDestroyed)
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
    if (en ~= nil) and (not en.bDestroyed) and (not base.enemy) then reason = "combat_started"; return end
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
    S.adv_elapsed = (S.adv_elapsed or 0) + 1
    -- HYBRID pause: after a short settle, end the advance EARLY on a critical event so the agent
    -- gets a turn to react (combat start / hull damage / boarder / fire / event). Not mid-warp.
    if S.frame_budget > 0 and S.adv_elapsed >= 18 then
      local r = check_critical(S.danger0, S.adv_elapsed)
      if r then S.frame_budget = 0; S.interrupt_reason = r end
    end
    if S.frame_budget == 0 then
      set_frozen(true)
      write_observation()        -- advance complete (or early-interrupt): rebuild
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
