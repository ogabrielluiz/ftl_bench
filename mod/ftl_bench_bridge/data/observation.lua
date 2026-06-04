-- ftl_bench observation serializer. Builds a minimal-but-REAL observation
-- table from VERIFIED Hyperspace getters, with nil-guards for not-in-game.
-- Installs _G.ftl_bench.build_observation().
--
-- NOTE: the std::pair access form (.first/.second vs [0]/[1]) is confirmed
-- against the live game in M1 Task 8.4. If hull.current comes back nil in-game,
-- switch the *.first/*.second accesses below to [0]/[1].
_G.ftl_bench = _G.ftl_bench or {}

local function ship_snapshot(mgr)
  if not mgr then return nil end
  local pwr = mgr:GetAvailablePower()        -- pair {max, available}
  local snap = {
    hull = {
      current = mgr.ship.hullIntegrity.first,
      max = mgr.ship.hullIntegrity.second,
    },
    reactor = { total = pwr.first, available = pwr.second },
    resources = {
      scrap = mgr.currentScrap,
      fuel = mgr.fuel_count,
      missiles = mgr:GetMissileCount(),
      drone_parts = mgr:GetDroneCount(),
    },
    oxygen_pct = mgr:GetOxygenPercentage(),
    systems = {},
    crew = {},
    weapons = {},
  }

  local sys_list = mgr.vSystemList
  if sys_list then
    for i = 0, sys_list:size() - 1 do
      local sys = sys_list[i]
      snap.systems[#snap.systems + 1] = {
        id = sys:GetId(),
        power = sys.powerState.first,
        power_max = sys.powerState.second,
        damage = sys.fDamage,
        max_damage = sys.fMaxDamage,
        powered = sys:Powered(),
      }
    end
  end

  local crew_list = mgr.vCrewList
  if crew_list then
    for i = 0, crew_list:size() - 1 do
      local crew = crew_list[i]
      snap.crew[#snap.crew + 1] = {
        id = i,
        room = crew.iRoomId,
        health_current = crew.health.first,
        health_max = crew.health.second,
        dead = crew.bDead,
        mind_controlled = crew.bMindControlled,
      }
    end
  end

  local weapon_list = mgr:GetWeaponList()
  if weapon_list then
    for i = 0, weapon_list:size() - 1 do
      local w = weapon_list[i]
      snap.weapons[#snap.weapons + 1] = {
        slot = i,
        cooldown = w.cooldown,
        base_cooldown = w.baseCooldown,
        powered = w.powered,
      }
    end
  end

  -- Shields::shields is a single Shield struct (NOT a vector): .charger is the
  -- charge progress within the current layer; .power is a ShieldPower struct with
  -- .first = current charged layers, .second = max layers.
  local shield_sys = mgr.shieldSystem
  if shield_sys then
    local sh = shield_sys.shields
    if sh then
      snap.shields = {
        charger = sh.charger,
        layers = sh.power.first,
        max_layers = sh.power.second,
      }
    end
  end

  return snap
end

function _G.ftl_bench.build_observation(tick)
  local app = Hyperspace.App
  local world = app and app.world
  local gui = app and app.gui

  local obs = {
    schema_version = 1,
    tick = tick,
    seed = Hyperspace.Global.currentSeed,
    game_started = world and world.bStartedGame or false,
    paused = gui and gui.bPaused or false,
  }

  if not obs.game_started then
    obs.player_ship = nil
    obs.enemy_ship = nil
    return obs
  end

  obs.player_ship = ship_snapshot(Hyperspace.ships.player)
  obs.enemy_ship = ship_snapshot(Hyperspace.ships.enemy)

  local star_map = world.starMap
  if star_map then
    obs.map = {
      sector = star_map.worldLevel,
      current_sector = star_map.currentSector,
    }
  end

  obs.choice_box_open = gui and gui.choiceBoxOpen or false

  return obs
end
