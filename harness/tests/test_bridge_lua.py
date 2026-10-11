"""Execute the shipped Lua 5.3 state machine against a small engine double.

These test the real queue and frame gates, including an engine frame that reaches
full charge and fires before ON_TICK can observe the full cooldown value.
"""
import json
from pathlib import Path

from lupa.lua53 import LuaRuntime
import pytest
from ftl_bench.cli import _bench_root


ROOT = _bench_root()


def bridge(kind="BEAM", targets=2, charge=0, charge_max=5, victory=None):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute((ROOT / "mod/ftl_bench_bridge/data/json.lua").read_text())
    lua.execute("""
        function vec(items)
          local v = { n = #items }
          for i, value in ipairs(items) do v[i-1] = value end
          function v:size() return self.n end
          function v:pop_back() self.n=self.n-1; self[self.n]=nil end
          function v:push_back(value) self[self.n]=value; self.n=self.n+1 end
          return v
        end
        script = {on_internal_event=function() end, on_render_event=function() end}
        Defines = {InternalEvents={GET_RUN_SEED=1,PROJECTILE_FIRE=2,DAMAGE_AREA_HIT=3,
                   SHIELD_COLLISION=4}, RenderEvents={MOUSE_CONTROL=1}}
        action_json, last_obs, fired = '', nil, 0
        pf = {powered=true, targets=vec({}), cooldown={first=0,second=5},
              blueprint={typeName='BEAM'}, lastProjectileId=0}
        function pf:NumTargetsRequired() return 2 end
        pl = {bJumping=false, ship={hullIntegrity={first=30,second=30}},
              myBlueprint={blueprintName='PLAYER_SHIP_HARD'}}
        function pl:GetWeaponList() return vec({pf}) end
        enemy = {bDestroyed=false,bJumping=false,_targetable={hostile=true}}
        function enemy:GetRoomCenter(room) return {x=room*35,y=0} end
        gui = {bPaused=true,gameover=false}
        world = {bStartedGame=true,currentDifficulty=1}
        Hyperspace = {App={gui=gui,world=world},ships={player=pl,enemy=enemy},
                      Settings={difficulty=1},
                      Score={currentScore={score=0}},
          read_json_action=function() return action_json end,
          write_json_observation=function(obs) last_obs=obs; return true end,
          benchmark_set_weapon_autofire=function(enabled) global_autofire=enabled end}
        function native_fire(slot, ship, a, b)
          native_fire_calls=(native_fire_calls or 0)+1
          pf.fireWhenReady=true;pf.autoFiring=true;global_autofire=true
          return true
        end
        Hyperspace.benchmark_fire_weapon=native_fire
        Hyperspace.benchmark_fire_beam=native_fire
        _G.ftl_bench={build_observation=function(tick)
          return {tick=tick,game_started=true,player_ship={weapons={{slot=0}},systems={},reactor={}}}
        end}
        function engine_tick()
          if not gui.bPaused then
            pf.cooldown.first=math.min(pf.cooldown.second,pf.cooldown.first+1)
            if pf.cooldown.first >= pf.cooldown.second and pf.fireWhenReady then
              fired=fired+1; released_targets=pf.targets
              pf.cooldown.first=0; pf.lastProjectileId=pf.lastProjectileId+1
            end
          end
          _G.ftl_bench_tick()
        end
    """)
    lua.globals().pf.blueprint.typeName = kind
    lua.globals().pf.cooldown.first = charge
    lua.globals().pf.cooldown.second = charge_max
    lua.globals().pf.NumTargetsRequired = lua.eval(f"function() return {targets} end")
    if victory is not None:
        lua.globals().Hyperspace.Score.currentScore.victory = victory
    lua.execute((ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua").read_text())
    return lua


def step(lua, seq, actions, frames):
    lua.globals().action_json = json.dumps({"seq": seq, "actions": actions, "advance_frames": frames})
    lua.globals().engine_tick()
    for _ in range(frames):
        lua.globals().engine_tick()
    return json.loads(lua.globals().last_obs)


def show_enemy(lua):
    lua.execute("""
      function enemy:GetWeaponList() return vec({}) end
      local original = _G.ftl_bench.build_observation
      _G.ftl_bench.build_observation = function(tick)
        local obs = original(tick)
        if Hyperspace.ships.enemy then obs.enemy_ship = {hull={current=4,max=8}} end
        return obs
      end
    """)


@pytest.mark.parametrize("hostile", [True, False, None, 1, "true"])
def test_enemy_hostility_is_exact_native_boolean_and_neutral_pointer_remains_visible(hostile):
    lua = bridge()
    show_enemy(lua)
    lua.globals().enemy._targetable.hostile = hostile
    obs = step(lua, 1, [], 0)
    enemy = obs["enemy_ship"]
    assert enemy["hull"] == {"current": 4, "max": 8}
    assert enemy["targetable"] is (hostile is True)
    if type(hostile) is bool:
        assert enemy["hostile"] is hostile
    else:
        assert "hostile" not in enemy
    assert obs["capabilities"]["enemy_hostility"] is True


@pytest.mark.parametrize("kind", ["fire_weapon", "fire_beam"])
@pytest.mark.parametrize("hostile,reason", [(False, "enemy_not_hostile"), (None, "enemy_hostility_unknown"), (1, "enemy_hostility_unknown")])
def test_enemy_fire_refusal_never_calls_native_or_releases_weapon(kind, hostile, reason):
    lua = bridge()
    lua.globals().enemy._targetable.hostile = hostile
    action = {"type": kind, "weapon_slot": 0, "target_ship_id": 1}
    action.update({"target_room_id": 3} if kind == "fire_weapon" else {"room_a": 2, "room_b": 5})
    obs = step(lua, 1, [action], 20)
    assert (lua.globals().native_fire_calls or 0) == 0
    assert lua.globals().fired == 0
    assert lua.globals().ftl_bench_state.manual_fire["0"] is None
    feedback = obs["action_feedback"][0]
    expected = {"action_index": 1, **action, "status": "rejected", "reason": reason,
                "enemy_targetable": False, "queued": False}
    if type(hostile) is bool:
        expected["enemy_hostile"] = hostile
    assert feedback == expected


@pytest.mark.parametrize("kind", ["fire_weapon", "fire_beam"])
@pytest.mark.parametrize("hostile", [False, None])
def test_surrender_cancels_already_queued_enemy_shot_before_any_native_release(kind, hostile):
    lua = bridge(charge=20, charge_max=20)
    action = {"type": kind, "weapon_slot": 0, "target_ship_id": 1}
    action.update({"target_room_id": 3} if kind == "fire_weapon" else {"room_a": 2, "room_b": 5})
    obs = step(lua, 1, [action], 0)
    assert obs["action_feedback"][0]["status"] == "applied"
    assert lua.globals().ftl_bench_state.manual_fire["0"] is not None
    lua.globals().enemy._targetable.hostile = hostile
    step(lua, 2, [], 30)
    assert lua.globals().fired == 0
    assert lua.globals().pf.fireWhenReady is False
    assert lua.globals().pf.autoFiring is False
    assert lua.globals().global_autofire is False
    assert lua.globals().ftl_bench_state.manual_fire["0"] is None


@pytest.mark.parametrize("result", [False, None, 1, "true"])
@pytest.mark.parametrize("kind", ["fire_weapon", "fire_beam"])
def test_enemy_fire_feedback_requires_exact_native_acceptance(kind, result):
    lua = bridge()
    binding = "benchmark_fire_weapon" if kind == "fire_weapon" else "benchmark_fire_beam"
    lua.globals().native_fire_result = result
    lua.globals().Hyperspace[binding] = lua.eval("function(...) return native_fire_result end")
    action = {"type": kind, "weapon_slot": 0, "target_ship_id": 1}
    action.update({"target_room_id": 3} if kind == "fire_weapon" else {"room_a": 2, "room_b": 5})
    obs = step(lua, 1, [action], 20)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == "native_fire_refused"
    assert lua.globals().fired == 0
    assert lua.globals().ftl_bench_state.manual_fire["0"] is None


@pytest.mark.parametrize("field,value,reason", [
    ("bDestroyed", True, "enemy_destroyed"),
    ("bDestroyed", None, "enemy_state_unknown"),
    ("bJumping", True, "enemy_jumping"),
    ("bJumping", None, "enemy_state_unknown"),
])
def test_hostile_enemy_still_requires_known_native_death_and_warp_state(field, value, reason):
    lua = bridge()
    show_enemy(lua)
    lua.globals().enemy[field] = value
    obs = step(lua, 1, [{"type": "fire_weapon", "weapon_slot": 0, "target_room_id": 3}], 20)
    assert obs["enemy_ship"]["hostile"] is True
    assert obs["enemy_ship"]["targetable"] is False
    assert obs["action_feedback"][0]["reason"] == reason
    assert (lua.globals().native_fire_calls or 0) == 0
    assert lua.globals().fired == 0


@pytest.mark.parametrize("kind", ["fire_weapon", "fire_beam"])
@pytest.mark.parametrize("mode,reason", [("missing", "native_fire_unavailable"), ("error", "native_fire_failed")])
def test_fire_native_transport_failures_are_explicit_and_do_not_queue(kind, mode, reason):
    lua = bridge()
    binding = "benchmark_fire_weapon" if kind == "fire_weapon" else "benchmark_fire_beam"
    lua.globals().Hyperspace[binding] = None if mode == "missing" else lua.eval("function(...) error('native failure') end")
    action = {"type": kind, "weapon_slot": 0, "target_ship_id": 1}
    action.update({"target_room_id": 3} if kind == "fire_weapon" else {"room_a": 2, "room_b": 5})
    obs = step(lua, 1, [action], 20)
    assert obs["action_feedback"][0] == {"action_index": 1, **action, "status": "rejected", "reason": reason,
                                         "enemy_hostile": True, "enemy_targetable": True, "queued": False}
    assert lua.globals().fired == 0
    assert lua.globals().ftl_bench_state.manual_fire["0"] is None


def test_player_bomb_target_does_not_require_an_enemy_but_self_target_laser_is_refused():
    lua = bridge(kind="BOMB", targets=1)
    lua.globals().Hyperspace.ships.enemy = None
    lua.execute("function pl:GetRoomCenter(room) return {x=room*35,y=0} end")
    obs = step(lua, 1, [{"type": "fire_weapon", "weapon_slot": 0, "target_ship_id": 0, "target_room_id": 4}], 20)
    assert obs["action_feedback"][0] == {"action_index": 1, "type": "fire_weapon", "weapon_slot": 0,
                                         "target_ship_id": 0, "target_room_id": 4, "status": "applied", "queued": True}
    assert lua.globals().fired == 1
    lua.globals().pf.blueprint.typeName = "LASER"
    obs = step(lua, 2, [{"type": "fire_weapon", "weapon_slot": 0, "target_ship_id": 0, "target_room_id": 4}], 20)
    assert obs["action_feedback"][0]["reason"] == "self_target_unsupported"
    assert lua.globals().fired == 1


def test_missing_native_hostility_object_is_unknown_in_observation_and_refused_before_fire():
    lua = bridge()
    show_enemy(lua)
    lua.globals().enemy._targetable = None
    obs = step(lua, 1, [{"type": "fire_weapon", "weapon_slot": 0, "target_room_id": 3}], 20)
    assert obs["enemy_ship"]["targetable"] is False
    assert "hostile" not in obs["enemy_ship"]
    assert obs["action_feedback"][0]["reason"] == "enemy_hostility_unknown"
    assert lua.globals().fired == 0


@pytest.mark.parametrize("destroyed", [True, False, None])
def test_enemy_destroyed_observation_uses_native_flag_only(destroyed):
    lua = bridge()
    lua.globals().enemy.bDestroyed = destroyed
    lua.globals().enemy.bJumping = True
    lua.execute("""
      function enemy:GetWeaponList() return vec({}) end
      local original = _G.ftl_bench.build_observation
      _G.ftl_bench.build_observation = function(tick)
        local obs = original(tick)
        obs.enemy_ship = {hull={current=0,max=10}}
        return obs
      end
    """)
    enemy = step(lua, 1, [], 0)["enemy_ship"]
    assert enemy["targetable"] is False
    if destroyed is None:
        assert "destroyed" not in enemy
    else:
        assert enemy["destroyed"] is destroyed


def crew_bridge(*, real_serializer=False):
    lua = bridge()
    lua.execute("""
      function make_crew(owner, current, controllable, intruder, hp)
        local c={iShipId=owner,currentShipId=current,controllable=controllable,
          intruder=intruder,iRoomId=owner+1,health={first=hp or 100,second=100},
          bDead=false,bMindControlled=false,species='human',moves=0}
        function c:GetControllable() return self.controllable end
        function c:IsDead() return self.bDead end
        function c:OutOfGame() return false end
        function c:GetSkillLevel() return 0 end
        function c:Repairing() return false end
        function c:MoveToRoom(room, slot, force)
          self.moves=self.moves+1
          if self.refuse then return false end
          self.iRoomId=room; return true
        end
        return c
      end
      own=make_crew(0,0,true,false)
      hostile=make_crew(1,0,false,true)
      boarder=make_crew(0,1,true,true)
      pl.iShipId=0; pl.vCrewList=vec({own,hostile,boarder})
      _G.ftl_bench.build_observation=function(tick)
        local crew={}
        for i=0,pl.vCrewList:size()-1 do
          local c=pl.vCrewList[i]
          crew[#crew+1]={id=i,room=c.iRoomId,health_current=c.health.first,
            health_max=c.health.second,dead=c.bDead,mind_controlled=c.bMindControlled}
        end
        return {tick=tick,game_started=true,
          player_ship={crew=crew,weapons={{slot=0}},systems={},reactor={}}}
      end
    """)
    if real_serializer:
        lua.execute("""
          Hyperspace.Global={currentSeed=1}
          Hyperspace.ships.enemy=nil
          pl.vSystemList=vec({})
          function pl:GetAvailablePower() return {first=8,second=0} end
          function pl:GetMissileCount() return 0 end
          function pl:GetDroneCount() return 0 end
          function pl:GetOxygenPercentage() return 100 end
        """)
        lua.execute((ROOT / "mod/ftl_bench_bridge/data/observation.lua").read_text())
    return lua


@pytest.mark.parametrize("real_serializer", [False, True])
def test_crew_ownership_filters_hostiles_without_renumbering_or_losing_own_boarders(real_serializer):
    lua = crew_bridge(real_serializer=real_serializer)
    obs = step(lua, 1, [], 0)
    crew = obs["player_ship"]["crew"]
    assert [item["id"] for item in crew] == [0, 2]
    assert [item["owner_ship_id"] for item in crew] == [0, 0]
    assert [item["current_ship_id"] for item in crew] == [0, 1]
    assert all(item["player_owned"] and item["controllable"] for item in crew)
    assert crew[1]["intruder"] is True and crew[1]["on_enemy_ship"] is True
    assert obs["player_ship"]["intruders"][0]["room_id"] == 2
    assert obs["capabilities"]["crew_control_guard"] is True


def test_hostile_crew_command_is_rejected_and_later_owned_command_still_applies():
    lua = crew_bridge()
    obs = step(lua, 1, [{"type": "move_crew", "crew_id": 1, "room_id": 4},
                        {"type": "move_crew", "crew_id": 2, "room_id": 5}], 0)
    assert lua.globals().hostile.moves == 0
    assert lua.globals().hostile.iRoomId == 2
    assert lua.globals().boarder.moves == 1
    assert lua.globals().boarder.iRoomId == 5
    assert obs["action_feedback"] == [
        {"action_index": 1, "type": "move_crew", "crew_id": 1, "room_id": 4,
         "status": "rejected", "reason": "crew_not_player_owned"},
        {"action_index": 2, "type": "move_crew", "crew_id": 2, "room_id": 5,
         "status": "applied"},
    ]
    assert step(lua, 2, [], 0)["action_feedback"] == []


@pytest.mark.parametrize("case, reason", [
    ("mind_controlled", "crew_not_controllable"),
    ("getter_missing", "crew_not_controllable"),
    ("zero_health", "crew_not_alive"),
    ("engine_refused", "crew_move_refused"),
])
def test_owned_crew_requires_native_controllability_and_reports_refused_moves(case, reason):
    lua = crew_bridge()
    if case == "mind_controlled":
        lua.execute("own.bMindControlled=true; own.controllable=false")
    elif case == "getter_missing":
        lua.execute("own.GetControllable=nil")
    elif case == "zero_health":
        lua.execute("own.health.first=0")
    else:
        lua.execute("own.refuse=true")
    obs = step(lua, 1, [{"type": "move_crew", "crew_id": 0, "room_id": 4}], 0)
    assert lua.globals().own.iRoomId == 1
    assert lua.globals().own.moves == (1 if case == "engine_refused" else 0)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == reason
    if case in {"mind_controlled", "getter_missing"}:
        assert obs["player_ship"]["crew"][0]["controllable"] is False


def test_mind_controlling_an_enemy_does_not_transfer_crew_ownership():
    lua = crew_bridge()
    lua.execute("hostile.bMindControlled=true; hostile.controllable=true")
    obs = step(lua, 1, [{"type": "move_crew", "crew_id": 1, "room_id": 4}], 0)
    assert lua.globals().hostile.moves == 0
    assert [item["id"] for item in obs["player_ship"]["crew"]] == [0, 2]
    assert obs["action_feedback"][0]["reason"] == "crew_not_player_owned"


def test_charging_beam_keeps_distinct_endpoints_until_one_release():
    lua = bridge()
    step(lua, 1, [{"type": "fire_beam", "weapon_slot": 0, "room_a": 2, "room_b": 5}], 2)
    assert lua.globals().fired == 0
    assert lua.globals().pf.fireWhenReady is True
    assert lua.globals().pf.targets[0].x == 70
    assert lua.globals().pf.targets[1].x == 175
    step(lua, 2, [], 20)
    assert lua.globals().fired == 1
    assert lua.globals().pf.fireWhenReady is False
    assert lua.globals().global_autofire is False


def test_observation_includes_airlock_topology_with_unique_display_indices():
    lua = bridge()
    lua.execute("""
      pl.ship.vDoorList=vec({{iDoorId=3,iRoom1=1,iRoom2=2,bOpen=false}})
      pl.ship.vOuterAirlocks=vec({{iDoorId=8,iRoom1=2,iRoom2=-1,bOpen=true}})
    """)
    doors = step(lua, 1, [], 0)["player_ship"]["doors"]
    assert doors == [
        {"index": 0, "id": 3, "room_a": 1, "room_b": 2, "open": False, "airlock": False},
        {"index": 1, "id": 8, "room_a": 2, "room_b": -1, "open": True, "airlock": True},
    ]


def test_charge_reset_completes_request_without_observing_fully_ready_frame():
    lua = bridge(kind="LASER", targets=3, charge_max=5)
    step(lua, 1, [{"type": "fire_weapon", "weapon_slot": 0, "target_room_id": 4}], 20)
    assert lua.globals().fired == 1
    assert lua.globals().pf.targets.n == 3
    assert lua.globals().pf.fireWhenReady is False
    assert lua.globals().ftl_bench_state.manual_fire["0"] is None


def test_zero_frame_action_does_not_advance_and_empty_wait_releases_queue():
    lua = bridge()
    step(lua, 1, [{"type": "fire_beam", "weapon_slot": 0, "room_a": 1, "room_b": 3}], 0)
    assert lua.globals().pf.cooldown.first == 0
    assert lua.globals().gui.bPaused is True
    step(lua, 2, [], 6)
    assert lua.globals().fired == 1


def test_two_shot_laser_is_not_classified_or_dispatched_as_beam():
    lua = bridge(kind="LASER", targets=2)
    obs = step(lua, 1, [{"type": "fire_beam", "weapon_slot": 0, "room_a": 1, "room_b": 3}], 8)
    assert lua.globals().fired == 0
    assert obs["player_ship"]["weapons"][0]["is_beam"] is False


def test_native_victory_is_explicit_and_absence_stays_unknown():
    lua = bridge(victory=True)
    obs = step(lua, 1, [], 0)
    assert obs["victory"] is True
    assert obs["capabilities"]["victory"] is True
    assert obs["difficulty"] == 1
    assert obs["player_ship"]["blueprint"] == "PLAYER_SHIP_HARD"
    obs = step(bridge(), 1, [], 0)
    assert "victory" not in obs
    assert obs["capabilities"]["victory"] is False


def test_setup_identity_getters_override_unreliable_raw_fields():
    lua = bridge()
    lua.execute("""
      world.currentDifficulty=1735223612
      pl.myBlueprint.name=nil
      Hyperspace.benchmark_difficulty=function() return 0 end
      Hyperspace.benchmark_player_blueprint=function() return 'PLAYER_SHIP_HARD' end
    """)
    obs = step(lua, 1, [], 0)
    assert obs["difficulty"] == 0
    assert obs["player_ship"]["blueprint"] == 'PLAYER_SHIP_HARD'


def test_new_game_sets_and_verifies_easy_before_advancing_menu():
    lua = bridge()
    lua.execute("""
      world.bStartedGame=false
      difficulty, menu_clicks=1,0
      Hyperspace.benchmark_set_difficulty=function(value)
        assert(not world.bStartedGame)
        difficulty=value; return true
      end
      Hyperspace.benchmark_difficulty=function() return difficulty end
      Hyperspace.benchmark_advance_menu=function()
        assert(difficulty==0); menu_clicks=menu_clicks+1
      end
    """)
    step(lua, 1, [{"type": "start_game", "mode": "new", "seed": 1}], 25)
    assert lua.globals().difficulty == 0
    assert lua.globals().menu_clicks == 1
    lua.globals().Hyperspace.benchmark_set_difficulty = lua.eval("function() return false end")
    step(lua, 2, [], 25)
    assert lua.globals().menu_clicks == 1


def test_current_run_score_replaces_stale_top_score_and_absent_getter_stays_unknown():
    lua = bridge()
    lua.execute("""
      Hyperspace.Score.currentScore.score=9999
      Hyperspace.benchmark_run_score=function() return 0 end
      Hyperspace.benchmark_score_components=function()
        return '{"scrap_collected":0,"ships_destroyed":0,"beacons_explored":0,"difficulty":0}'
      end
    """)
    obs = step(lua, 1, [], 0)
    assert obs["ftl_score"] == 0
    assert obs["ftl_score_source"] == "native_live_v1"
    assert obs["ftl_score_components"]["scrap_collected"] == 0
    lua.globals().Hyperspace.benchmark_run_score = None
    assert "ftl_score" not in step(lua, 2, [], 0)


def test_hacking_uses_zero_for_idle_and_negative_one_for_active_lock():
    lua = bridge()
    lua.execute("""
      pl.hackingSystem={iLockCount=0,powerState={first=1},drone={arrived=false},
        effectTimer={first=0,second=0}, Powered=function() return true end,
        GetMaxPower=function() return 1 end}
    """)
    obs = step(lua, 1, [], 0)
    assert obs["player_ship"]["hacking"]["ready"] is True
    assert obs["player_ship"]["hacking"]["system_locked"] is False
    lua.globals().pl.hackingSystem.iLockCount = -1
    obs = step(lua, 2, [], 0)
    assert obs["player_ship"]["hacking"]["ready"] is False
    assert obs["player_ship"]["hacking"]["system_locked"] is True


def test_native_victory_getter_takes_precedence_over_stale_score_field():
    lua = bridge(victory=False)
    lua.globals().Hyperspace.benchmark_victory = lua.eval("function() return true end")
    assert step(lua, 1, [], 0)["victory"] is True


def test_hacking_charge_drain_does_not_count_as_a_manual_weapon_release():
    lua = bridge(kind="LASER", targets=3, charge=3, charge_max=5)
    step(lua, 1, [{"type": "fire_weapon", "weapon_slot": 0, "target_room_id": 4}], 0)
    lua.globals().pf.iHackLevel = 2
    lua.globals().pf.cooldown.first = 0
    step(lua, 2, [], 1)
    assert lua.globals().fired == 0
    assert lua.globals().ftl_bench_state.manual_fire["0"] is not None
    lua.globals().pf.iHackLevel = 0
    step(lua, 3, [], 12)
    assert lua.globals().fired == 1


def event_bridge(*, mode=2, open_time=1):
    lua = bridge()
    lua.execute("""
      event_calls=0
      cb={mainText='Choose an event branch',selectedChoice=-1,potentialChoice=-1,
          openTime=1,choices=vec({{type=0,text='Continue'},
                                {type=1,text='Unaffordable trade'},
                                {type=2,text='Special option'}})}
      function cb:GetChoices() return self.choices end
      gui.choiceBoxOpen=true; gui.choiceBox=cb; Hyperspace.Settings.dialogKeys=2
      function Hyperspace.benchmark_choose_event(index)
        event_calls=event_calls+1
        if event_error then error('engine call failed') end
        local c=cb.choices[index]
        if Hyperspace.Settings.dialogKeys==0 then return false end
        if Hyperspace.Settings.dialogKeys==2 and cb.openTime<0.3 then return false end
        if c and c.type~=1 and not event_refuse then cb.selectedChoice=index end
        -- Native KeyDown can return true for a handled key without a selection.
        return true
      end
      original_engine_tick=engine_tick
      function engine_tick()
        if gui.choiceBoxOpen and type(cb.openTime)=='number' then cb.openTime=cb.openTime+1/60 end
        original_engine_tick()
      end
    """)
    lua.globals().Hyperspace.Settings.dialogKeys = mode
    lua.globals().cb.openTime = open_time
    return lua


@pytest.mark.parametrize("kind", ["fire_weapon", "fire_beam"])
@pytest.mark.parametrize("hostile_after_choice", [True, False])
def test_event_then_fire_records_checked_dispatch_target_not_previous_observation(kind, hostile_after_choice):
    lua = event_bridge(mode=1)
    show_enemy(lua)
    lua.globals().enemy._targetable.hostile = not hostile_after_choice
    before = step(lua, 1, [], 0)
    assert before["enemy_ship"]["hostile"] is not hostile_after_choice
    lua.globals().hostile_after_choice = hostile_after_choice
    lua.execute("""
      local select_choice = Hyperspace.benchmark_choose_event
      function Hyperspace.benchmark_choose_event(index)
        local result = select_choice(index)
        if cb.selectedChoice == index then
          enemy._targetable.hostile = hostile_after_choice
          gui.choiceBoxOpen = false
        end
        return result
      end
    """)
    action = {"type": kind, "weapon_slot": 0, "target_ship_id": 1}
    action.update({"target_room_id": 3} if kind == "fire_weapon" else {"room_a": 2, "room_b": 5})
    obs = step(lua, 2, [{"type": "choose_event", "choice_index": 0}, action], 0)
    feedback = obs["action_feedback"][1]
    assert feedback["enemy_hostile"] is hostile_after_choice
    assert feedback["enemy_targetable"] is hostile_after_choice
    assert feedback["queued"] is hostile_after_choice
    assert feedback["status"] == ("applied" if hostile_after_choice else "rejected")
    assert lua.globals().fired == 0  # queued is acceptance, not a projectile/hit claim


def test_event_choices_expose_native_availability_without_renumbering():
    lua = event_bridge(mode=0, open_time=0)
    lua.execute("cb.choices[2].rewards={scrap=100,missiles=-5,upgradeAmount=1}")
    obs = step(lua, 1, [], 0)
    assert obs["event"]["dialog_keys"] == 0
    assert obs["event"]["open_time"] == pytest.approx(1 / 60)
    assert [(c["index"], c["native_type"], c["disabled"], c["enabled"], c["available"])
            for c in obs["event"]["choices"]] == [
        (0, 0, False, True, True), (1, 1, True, False, False),
        (2, 2, False, True, True),
    ]
    # Rewards may contain branch outcomes. This repair exposes no unknown costs.
    assert "rewards" not in obs["event"]["choices"][2]
    assert "cost" not in obs["event"]["choices"][2]


def test_disabled_event_choice_is_rejected_without_native_call_and_can_select_another():
    lua = event_bridge()
    obs = step(lua, 1, [{"type": "choose_event", "choice_index": 1},
                        {"type": "choose_event", "choice_index": 2}], 0)
    assert lua.globals().event_calls == 1
    assert lua.globals().cb.selectedChoice == 2
    assert obs["action_feedback"] == [
        {"action_index": 1, "type": "choose_event", "choice_index": 1,
         "status": "rejected", "reason": "choice_disabled", "selected_choice": -1},
        {"action_index": 2, "type": "choose_event", "choice_index": 2,
         "status": "applied", "selected_choice": 2},
    ]
    assert obs["event"]["selected_choice"] == 2
    assert lua.globals().gui.choiceBoxOpen is True
    assert step(lua, 2, [], 0)["action_feedback"] == []


def test_native_event_gui_delay_can_age_while_paused_without_automatic_selection_retry():
    lua = event_bridge(open_time=0)
    obs = step(lua, 1, [{"type": "choose_event", "choice_index": 0}], 0)
    assert lua.globals().event_calls == 1
    assert obs["action_feedback"][0]["reason"] == "event_input_delay"
    assert obs["event"]["open_time"] < 0.3
    # Native GUI time can age while ship simulation is paused. This must not
    # retry the rejected action, but the new keyboard readiness needs a snapshot.
    for _ in range(30):
        lua.globals().engine_tick()
    assert lua.globals().cb.openTime >= 0.3
    assert lua.globals().event_calls == 1
    assert lua.globals().cb.selectedChoice == -1
    assert json.loads(lua.globals().last_obs)["event"]["open_time"] >= 0.3
    obs = step(lua, 2, [{"type": "choose_event", "choice_index": 0}], 0)
    assert lua.globals().event_calls == 2
    assert obs["action_feedback"][0]["status"] == "applied"
    assert obs["action_feedback"][0]["selected_choice"] == 0
    assert lua.globals().Hyperspace.Settings.dialogKeys == 2


@pytest.mark.parametrize("mode,open_time,reason", [
    (0, 1, "event_hotkeys_disabled"),
    (2, 0.1, "event_input_delay"),
    (1, 0, "event_selection_refused"),
    (None, None, "event_selection_refused"),
])
def test_event_native_boolean_is_not_selection_proof(mode, open_time, reason):
    lua = event_bridge(mode=mode, open_time=open_time)
    lua.globals().event_refuse = True
    obs = step(lua, 1, [{"type": "choose_event", "choice_index": 0}], 0)
    assert lua.globals().event_calls == 1
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == reason
    assert obs["action_feedback"][0]["selected_choice"] == -1


def test_event_unknown_native_type_stays_unknown_and_selection_still_requires_proof():
    lua = event_bridge()
    lua.execute("cb.choices[0].type=nil")
    obs = step(lua, 1, [], 0)
    choice = obs["event"]["choices"][0]
    assert all(key not in choice for key in ("native_type", "enabled", "available", "disabled"))
    obs = step(lua, 2, [{"type": "choose_event", "choice_index": 0}], 0)
    assert obs["action_feedback"][0]["status"] == "applied"
    assert obs["action_feedback"][0]["selected_choice"] == 0


@pytest.mark.parametrize("index", [-1, 3, 9, 1.5, "0"])
def test_event_invalid_indices_never_reach_native_dispatch(index):
    lua = event_bridge()
    obs = step(lua, 1, [{"type": "choose_event", "choice_index": index}], 0)
    assert lua.globals().event_calls == 0
    assert obs["action_feedback"][0]["reason"] == "invalid_choice_index"


@pytest.mark.parametrize("case,reason", [
    ("closed", "event_closed"),
    ("choices_unavailable", "event_choices_unavailable"),
    ("native_error", "event_selection_failed"),
])
def test_event_dispatch_reports_unavailable_or_failed_native_state(case, reason):
    lua = event_bridge()
    if case == "closed":
        lua.globals().gui.choiceBoxOpen = False
    elif case == "choices_unavailable":
        lua.execute("cb.GetChoices=function() error('unavailable choices') end")
    else:
        lua.globals().event_error = True
    obs = step(lua, 1, [{"type": "choose_event", "choice_index": 0}], 0)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == reason
    assert lua.globals().event_calls == (1 if case == "native_error" else 0)


@pytest.mark.parametrize("requested", [0, 2])
def test_event_pending_selection_cannot_prove_a_new_call_or_be_overwritten(requested):
    lua = event_bridge()
    lua.globals().cb.selectedChoice = 0
    obs = step(lua, 1, [{"type": "choose_event", "choice_index": requested}], 0)
    assert lua.globals().event_calls == 0
    assert lua.globals().cb.selectedChoice == 0
    assert obs["event"]["selected_choice"] == 0
    assert obs["action_feedback"] == [
        {"action_index": 1, "type": "choose_event", "choice_index": requested,
         "status": "rejected", "reason": "event_selection_pending", "selected_choice": 0}
    ]


def economy_bridge():
    lua = bridge()
    lua.execute("""
      legacy_upgrade_calls=0; system_upgrade_calls=0; reactor_upgrade_calls=0
      wait_calls=0; distress_calls=0; recovery_frames=0
      pl.currentScrap=100; pl.fuel_count=0
      legacy_system={maxLevel=8,GetMaxPower=function() return 2 end}
      function legacy_system:UpgradeSystem()
        legacy_upgrade_calls=legacy_upgrade_calls+1; error('Lua system upgrade forbidden')
      end
      function pl:GetSystem() return legacy_system end
      function pl:ModifyScrapCount()
        legacy_upgrade_calls=legacy_upgrade_calls+1; error('Lua scrap deduction forbidden')
      end
      economy={native_protocol=5,upgrade_available=true,
        systems={{system_id=0,current_max_power=2,max_level=8,
                  next_upgrade_cost=21,can_upgrade=true}},
        reactor={current_max_power=8,max_level=25,next_upgrade_cost=22,can_upgrade=true},
        fuel_recovery={out_of_fuel=true,distress_on=false,can_wait=true,waiting=false}}
      function Hyperspace.benchmark_economy_state()
        if economy_error then error('native state failed') end
        if economy_json_override then return economy_json_override end
        return _G.json.encode(economy)
      end
      function Hyperspace.benchmark_upgrade_system(id)
        system_upgrade_calls=system_upgrade_calls+1; requested_system_id=id
        if upgrade_error then error('native upgrade failed') end
        local sys=economy.systems[1]
        if id~=sys.system_id or upgrade_refuse or not economy.upgrade_available
           or not sys.can_upgrade or pl.currentScrap<sys.next_upgrade_cost then return false end
        pl.currentScrap=pl.currentScrap-sys.next_upgrade_cost
        sys.current_max_power=sys.current_max_power+1; return true
      end
      function Hyperspace.benchmark_upgrade_reactor()
        reactor_upgrade_calls=reactor_upgrade_calls+1
        if upgrade_error then error('native upgrade failed') end
        local rc=economy.reactor
        if upgrade_refuse or not economy.upgrade_available or not rc.can_upgrade
           or pl.currentScrap<rc.next_upgrade_cost then return false end
        pl.currentScrap=pl.currentScrap-rc.next_upgrade_cost
        rc.current_max_power=rc.current_max_power+1; return true
      end
      function Hyperspace.benchmark_wait_for_fuel()
        wait_calls=wait_calls+1
        if fuel_error then error('native recovery failed') end
        local f=economy.fuel_recovery
        if fuel_refuse or not f.can_wait or f.waiting then return false end
        f.waiting=true; f.can_wait=false; return true
      end
      function Hyperspace.benchmark_set_distress(enabled)
        distress_calls=distress_calls+1; requested_distress=enabled
        if fuel_error then error('native recovery failed') end
        if fuel_refuse then return false end
        economy.fuel_recovery.distress_on=enabled; return true
      end
      economy_original_tick=engine_tick
      function engine_tick()
        local f=economy.fuel_recovery
        if f.waiting then
          recovery_frames=recovery_frames+1
          if recovery_frames>=3 then
            pl.fuel_count=1; f.waiting=false; f.out_of_fuel=false
          end
        end
        economy_original_tick()
      end
    """)
    return lua


def test_native_system_and_reactor_prices_are_charged_once_without_lua_fallback():
    lua = economy_bridge()
    obs = step(lua, 1, [{"type": "upgrade_system", "system_id": 0},
                        {"type": "upgrade_reactor"}], 0)
    assert lua.globals().pl.currentScrap == 57  # Native prices 21 + 22, not a generic table.
    assert lua.globals().legacy_upgrade_calls == 0
    assert lua.globals().system_upgrade_calls == lua.globals().reactor_upgrade_calls == 1
    assert lua.globals().requested_system_id == 0
    assert obs["economy"]["systems"][0]["current_max_power"] == 3
    assert obs["economy"]["systems"][0]["next_upgrade_cost"] == 21
    assert obs["economy"]["reactor"]["current_max_power"] == 9
    assert obs["action_feedback"] == [
        {"action_index": 1, "type": "upgrade_system", "system_id": 0, "status": "applied"},
        {"action_index": 2, "type": "upgrade_reactor", "status": "applied"},
    ]
    assert obs["capabilities"]["upgrade_rules"] is True
    assert obs["capabilities"]["fuel_recovery"] is True
    assert obs["bridge_version"] == 5


@pytest.mark.parametrize("case", ["modal", "unaffordable", "at_cap", "engine_refused"])
def test_native_upgrade_refusal_preserves_scrap_and_observed_price(case):
    lua = economy_bridge()
    if case == "modal":
        lua.globals().economy.upgrade_available = False
    elif case == "unaffordable":
        lua.globals().pl.currentScrap = 20
    elif case == "at_cap":
        lua.globals().economy.systems[1].can_upgrade = False
        lua.globals().economy.reactor.can_upgrade = False
    else:
        lua.globals().upgrade_refuse = True
    initial_scrap = lua.globals().pl.currentScrap
    obs = step(lua, 1, [{"type": "upgrade_system", "system_id": 0},
                        {"type": "upgrade_reactor"}], 0)
    assert lua.globals().pl.currentScrap == initial_scrap
    assert lua.globals().legacy_upgrade_calls == 0
    assert obs["economy"]["systems"][0]["current_max_power"] == 2
    assert obs["economy"]["systems"][0]["next_upgrade_cost"] == 21
    assert obs["economy"]["reactor"]["current_max_power"] == 8
    assert all(f["status"] == "rejected" and f["reason"] == "native_upgrade_refused"
               for f in obs["action_feedback"])


def test_fuel_wait_is_queued_once_and_native_ui_resolution_updates_paused_observation():
    lua = economy_bridge()
    obs = step(lua, 1, [{"type": "set_distress", "enabled": True},
                        {"type": "set_distress", "enabled": False},
                        {"type": "wait_for_fuel"}, {"type": "wait_for_fuel"}], 0)
    assert lua.globals().pl.fuel_count == 0
    assert lua.globals().wait_calls == 2
    assert obs["economy"]["fuel_recovery"] == {
        "out_of_fuel": True, "distress_on": False, "can_wait": False, "waiting": True,
    }
    assert obs["action_feedback"] == [
        {"action_index": 1, "type": "set_distress", "enabled": True, "status": "applied"},
        {"action_index": 2, "type": "set_distress", "enabled": False, "status": "applied"},
        {"action_index": 3, "type": "wait_for_fuel", "status": "applied"},
        {"action_index": 4, "type": "wait_for_fuel", "status": "rejected",
         "reason": "native_fuel_recovery_refused"},
    ]
    for _ in range(20):
        lua.globals().engine_tick()
    assert lua.globals().pl.fuel_count == 1
    assert lua.globals().wait_calls == 2
    obs = json.loads(lua.globals().last_obs)
    assert lua.globals().gui.bPaused is True
    assert obs["last_action_seq"] == 1
    assert obs["economy"]["fuel_recovery"]["out_of_fuel"] is False
    assert obs["economy"]["fuel_recovery"]["waiting"] is False
    assert lua.globals().requested_distress is False
    assert obs["economy"]["fuel_recovery"]["distress_on"] is False
    assert obs["action_feedback"][1]["enabled"] is False


@pytest.mark.parametrize("action,binding,prefix", [
    ({"type": "upgrade_system", "system_id": 0}, "benchmark_upgrade_system", "native_upgrade"),
    ({"type": "upgrade_reactor"}, "benchmark_upgrade_reactor", "native_upgrade"),
    ({"type": "wait_for_fuel"}, "benchmark_wait_for_fuel", "native_fuel_recovery"),
    ({"type": "set_distress", "enabled": False}, "benchmark_set_distress", "native_fuel_recovery"),
])
@pytest.mark.parametrize("failure", ["missing", "exception", "non_boolean"])
def test_economy_actions_report_missing_failed_or_non_boolean_native_results(action, binding, prefix, failure):
    lua = economy_bridge()
    if failure == "missing":
        lua.globals().Hyperspace[binding] = None
        suffix = "unavailable"
    elif failure == "exception":
        lua.globals().Hyperspace[binding] = lua.eval("function() error('native call failed') end")
        suffix = "failed"
    else:
        lua.globals().Hyperspace[binding] = lua.eval("function() return 'true' end")
        suffix = "refused"
    obs = step(lua, 1, [action], 0)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == f"{prefix}_{suffix}"
    assert lua.globals().pl.currentScrap == 100
    assert lua.globals().pl.fuel_count == 0
    assert lua.globals().legacy_upgrade_calls == 0


@pytest.mark.parametrize("action,reason", [
    ({"type": "upgrade_system", "system_id": -1}, "invalid_system_id"),
    ({"type": "upgrade_system", "system_id": 1.5}, "invalid_system_id"),
    ({"type": "upgrade_system", "system_id": "0"}, "invalid_system_id"),
    ({"type": "upgrade_system", "system_id": 2147483648}, "invalid_system_id"),
    ({"type": "set_distress", "enabled": 0}, "invalid_distress_enabled"),
    ({"type": "set_distress"}, "invalid_distress_enabled"),
])
def test_invalid_economy_action_values_never_reach_native_bindings(action, reason):
    lua = economy_bridge()
    obs = step(lua, 1, [action], 0)
    assert obs["action_feedback"][0]["reason"] == reason
    assert lua.globals().system_upgrade_calls == lua.globals().distress_calls == 0


def test_native_nullable_economy_fields_remain_unknown_and_zero_cost_stays_zero():
    lua = economy_bridge()
    lua.globals().economy_json_override = json.dumps({
        "native_protocol": 5, "upgrade_available": False,
        "systems": [{"system_id": 0, "current_max_power": 8, "max_level": 8,
                     "next_upgrade_cost": None, "can_upgrade": False},
                    {"system_id": 3, "current_max_power": 1, "max_level": 8,
                     "next_upgrade_cost": 0, "can_upgrade": False}],
        "reactor": None,
        "fuel_recovery": {"out_of_fuel": False, "distress_on": False,
                          "can_wait": False, "waiting": False},
    })
    obs = step(lua, 1, [], 0)
    assert "next_upgrade_cost" not in obs["economy"]["systems"][0]
    assert obs["economy"]["systems"][0]["can_upgrade"] is False
    assert obs["economy"]["systems"][1]["next_upgrade_cost"] == 0
    assert "reactor" not in obs["economy"]
    assert obs["capabilities"]["upgrade_rules"] is True
    assert obs["capabilities"]["fuel_recovery"] is True


@pytest.mark.parametrize("case", ["no_getter", "getter_error", "invalid_json", "old_protocol", "missing_bindings"])
def test_economy_capabilities_require_protocol_state_and_available_bindings(case):
    lua = economy_bridge()
    lua.execute("""Hyperspace.benchmark_capabilities=function()
      return '{"native_protocol":5,"fuel_recovery":true,"upgrade_rules":true}' end""")
    if case == "no_getter":
        lua.globals().Hyperspace.benchmark_economy_state = None
    elif case == "getter_error":
        lua.globals().economy_error = True
    elif case == "invalid_json":
        lua.globals().economy_json_override = "not-json"
    elif case == "old_protocol":
        lua.globals().economy.native_protocol = 4
    else:
        lua.globals().Hyperspace.benchmark_upgrade_system = None
        lua.globals().Hyperspace.benchmark_set_distress = None
    obs = step(lua, 1, [], 0)
    assert obs["capabilities"]["upgrade_rules"] is False
    assert obs["capabilities"]["fuel_recovery"] is False
    if case in {"no_getter", "getter_error", "invalid_json"}:
        assert "economy" not in obs


def test_event_choice_capability_reflects_available_guarded_native_dispatch():
    lua = event_bridge()
    assert step(lua, 1, [], 0)["capabilities"]["event_choice_state"] is True
    lua.globals().Hyperspace.benchmark_choose_event = None
    assert step(lua, 2, [], 0)["capabilities"]["event_choice_state"] is False


def count_observations(lua):
    lua.execute("""
      observed_builds=0
      counted_build=_G.ftl_bench.build_observation
      _G.ftl_bench.build_observation=function(tick)
        observed_builds=observed_builds+1
        return counted_build(tick)
      end
    """)


def test_transient_observation_read_failure_retries_without_replaying_native_wait():
    lua = economy_bridge()
    step(lua, 1, [], 0)
    lua.execute("""
      original_build=_G.ftl_bench.build_observation
      build_failures=1
      _G.ftl_bench.build_observation=function(tick)
        if build_failures>0 then build_failures=build_failures-1; error('transient ship read') end
        return original_build(tick)
      end
    """)
    stale = step(lua, 2, [{"type": "wait_for_fuel"}], 0)
    assert stale["last_action_seq"] == 1
    assert lua.globals().ftl_bench_state.obs_fresh is False
    assert lua.globals().wait_calls == 1
    lua.globals().engine_tick()
    obs = json.loads(lua.globals().last_obs)
    assert obs["last_action_seq"] == 2
    assert obs["action_feedback"][0]["status"] == "applied"
    assert lua.globals().ftl_bench_state.obs_fresh is True
    assert lua.globals().wait_calls == 1


@pytest.mark.parametrize("failure", ["exception", "refusal", "missing_boolean"])
@pytest.mark.parametrize("frames", [0, 1])
def test_failed_observation_writer_retries_after_zero_frame_or_completed_advance(failure, frames):
    lua = bridge()
    step(lua, 1, [], 0)
    lua.execute("""
      writer_failures=1
      writer_failure='exception'
      Hyperspace.write_json_observation=function(obs)
        if writer_failures>0 then
          writer_failures=writer_failures-1
          if writer_failure=='exception' then error('transient writer error') end
          if writer_failure=='missing_boolean' then return nil end
          return false
        end
        last_obs=obs; return true
      end
    """)
    lua.globals().writer_failure = failure
    stale = step(lua, 2, [], frames)
    assert stale["last_action_seq"] == 1
    assert lua.globals().ftl_bench_state.obs_fresh is False
    charge = lua.globals().pf.cooldown.first
    lua.globals().engine_tick()
    assert json.loads(lua.globals().last_obs)["last_action_seq"] == 2
    assert lua.globals().ftl_bench_state.obs_fresh is True
    assert lua.globals().pf.cooldown.first == charge


def test_stable_idle_does_not_rebuild_ship_collections_but_gui_events_do():
    lua = event_bridge()
    count_observations(lua)
    step(lua, 1, [], 0)
    for _ in range(60):
        lua.globals().engine_tick()
    assert lua.globals().observed_builds == 1  # A ready GUI timer changing is not a rebuild reason.
    lua.execute("cb.mainText='A different event'; cb.selectedChoice=-1")
    lua.globals().engine_tick()
    assert json.loads(lua.globals().last_obs)["event"]["text"] == "A different event"
    assert lua.globals().observed_builds == 2
    lua.globals().gui.choiceBoxOpen = False
    lua.globals().engine_tick()
    assert "event" not in json.loads(lua.globals().last_obs)
    assert lua.globals().observed_builds == 3


def test_pending_native_wait_polls_without_a_lua_waiting_binding_then_stops_when_complete():
    lua = economy_bridge()
    lua.execute("world.starMap={bOpen=false,bChoosingNewSector=false}")
    count_observations(lua)
    step(lua, 1, [{"type": "wait_for_fuel"}], 0)
    assert lua.globals().world.starMap.waiting is None  # The native waiting field is unbound.
    assert lua.globals().ftl_bench_state.observed_native_waiting is True
    for _ in range(12):
        lua.globals().engine_tick()
    obs = json.loads(lua.globals().last_obs)
    assert obs["last_action_seq"] == 1
    assert obs["economy"]["fuel_recovery"]["waiting"] is False
    assert obs["economy"]["fuel_recovery"]["out_of_fuel"] is False
    assert lua.globals().ftl_bench_state.observed_native_waiting is False
    assert lua.globals().observed_builds == 2
    assert lua.globals().wait_calls == 1
    for _ in range(60):
        lua.globals().engine_tick()
    assert lua.globals().observed_builds == 2


def test_transient_map_snapshot_error_withholds_partial_acknowledgement_then_retries():
    lua = bridge()
    step(lua, 1, [], 0)
    lua.execute("""
      map_failures=1
      connected=vec({})
      function connected:size()
        if map_failures>0 then map_failures=map_failures-1; error('transient map read') end
        return 0
      end
      world.starMap={worldLevel=0,currentLoc={connectedLocations=connected}}
      before_map_build=_G.ftl_bench.build_observation
      _G.ftl_bench.build_observation=function(tick)
        local obs=before_map_build(tick); obs.map={}; return obs
      end
    """)
    stale = step(lua, 2, [], 0)
    assert stale["last_action_seq"] == 1
    assert lua.globals().ftl_bench_state.obs_fresh is False
    lua.globals().engine_tick()
    obs = json.loads(lua.globals().last_obs)
    assert obs["last_action_seq"] == 2
    assert obs["map"]["connected_beacons"] == []
    assert lua.globals().ftl_bench_state.obs_fresh is True

def sector_bridge():
    lua = bridge()
    lua.execute("""
      pl.fuel_count=2; pl.jump_timer={first=85,second=85}
      Hyperspace.ships.enemy=nil
      world.starMap={worldLevel=1,currentLoc={beacon=true,connectedLocations=vec({})},
                    sectors=vec({}),bChoosingNewSector=false}
      leave_calls=0; native_leave_result=true
      function Hyperspace.benchmark_leave_sector()
        leave_calls=leave_calls+1
        if native_leave_error then error('native leave failed') end
        return native_leave_result
      end
      function Hyperspace.benchmark_economy_state()
        local ready=pl.jump_timer.first>=pl.jump_timer.second
        return _G.json.encode({native_protocol=5,sector_navigation_version=1,
          beacon_navigation_version=1,navigation={can_jump=ready,enemy_defeat_pending=false,
            drive_current=pl.jump_timer.first,drive_max=pl.jump_timer.second,
            reason=not ready and 'drive_charging' or nil}})
      end
      before_leave_observation=_G.ftl_bench.build_observation
      _G.ftl_bench.build_observation=function(tick)
        local obs=before_leave_observation(tick); obs.map={sector=world.starMap.worldLevel}
        return obs
      end
    """)
    return lua


def beacon_bridge():
    lua = sector_bridge()
    lua.execute("""
      world.starMap.currentLoc.connectedLocations=vec({{}, {}})
      jump_calls=0; native_jump_result=true; native_pending=false
      native_can_jump=true; native_jump_reason=nil; beacon_marker=1
      function Hyperspace.benchmark_economy_state()
        return _G.json.encode({native_protocol=5,beacon_navigation_version=beacon_marker,
          navigation={can_jump=native_can_jump,enemy_defeat_pending=native_pending,
            drive_current=pl.jump_timer.first,drive_max=pl.jump_timer.second,
            reason=native_jump_reason}})
      end
      function Hyperspace.benchmark_jump_to_beacon(index)
        jump_calls=jump_calls+1; requested_beacon=index
        if native_jump_error then error('native jump failed') end
        return native_jump_result
      end
    """)
    return lua


@pytest.mark.parametrize("case", ["live_enemy", "destroyed_enemy", "no_enemy"])
def test_beacon_jump_uses_native_readiness_instead_of_enemy_or_charge_inference(case):
    lua = beacon_bridge()
    if case == "live_enemy":
        lua.execute("Hyperspace.ships.enemy={bDestroyed=false,_targetable={hostile=true}}")
    elif case == "destroyed_enemy":
        lua.execute("Hyperspace.ships.enemy={bDestroyed=true}")
    lua.globals().native_can_jump = False
    lua.globals().native_jump_reason = "drive_charging"
    lua.globals().pl.jump_timer.first = 41.5675
    refused = step(lua, 1, [{"type": "jump", "beacon_index": 1}], 0)
    assert lua.globals().jump_calls == 0
    assert refused["jump_charged"] is False
    assert refused["action_feedback"] == [{"action_index": 1, "type": "jump", "beacon_index": 1,
        "status": "rejected", "reason": "drive_charging"}]


def test_charged_pending_defeat_jump_is_legal_and_reports_exact_native_acceptance():
    lua = beacon_bridge()
    lua.globals().native_pending = True
    applied = step(lua, 1, [{"type": "jump", "beacon_index": 1}], 0)
    assert applied["capabilities"]["beacon_navigation"] is True
    assert applied["economy"]["navigation"]["enemy_defeat_pending"] is True
    assert applied["jump_charged"] is True
    assert applied["action_feedback"] == [{"action_index": 1, "type": "jump", "beacon_index": 1,
        "status": "applied"}]
    assert lua.globals().jump_calls == 1
    assert lua.globals().requested_beacon == 1


@pytest.mark.parametrize("result", [False, None, 1, "true"])
def test_beacon_jump_never_credits_non_boolean_native_result(result):
    lua = beacon_bridge()
    lua.globals().native_jump_result = result
    obs = step(lua, 1, [{"type": "jump", "beacon_index": 0}], 0)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == "native_jump_refused"
    assert lua.globals().jump_calls == 1


@pytest.mark.parametrize("index", [-1, 0.5, 2, None])
def test_invalid_beacon_never_calls_native(index):
    lua = beacon_bridge()
    obs = step(lua, 1, [{"type": "jump", "beacon_index": index}], 0)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == "invalid_beacon"
    assert lua.globals().jump_calls == 0


@pytest.mark.parametrize("mode,reason", [
    ("missing", "native_jump_unavailable"), ("error", "native_jump_failed"),
    ("marker", "native_jump_unavailable")])
def test_beacon_jump_binding_and_contract_failures_are_visible(mode, reason):
    lua = beacon_bridge()
    if mode == "missing":
        lua.globals().Hyperspace.benchmark_jump_to_beacon = None
    elif mode == "error":
        lua.globals().native_jump_error = True
    else:
        lua.globals().beacon_marker = None
    obs = step(lua, 1, [{"type": "jump", "beacon_index": 0}], 0)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == reason
    if mode != "error":
        assert obs["capabilities"]["beacon_navigation"] is False


def test_sector_leave_records_native_acceptance_and_refusal():
    lua = sector_bridge()
    obs = step(lua, 1, [{"type": "leave_sector"}], 0)
    assert lua.globals().leave_calls == 1
    assert obs["action_feedback"] == [
        {"action_index": 1, "type": "leave_sector", "status": "applied"}]
    lua.globals().native_leave_result = False
    refused = step(lua, 2, [{"type": "leave_sector"}], 0)
    assert lua.globals().leave_calls == 2
    assert refused["action_feedback"] == [
        {"action_index": 1, "type": "leave_sector", "status": "rejected",
         "reason": "native_leave_refused"}]


@pytest.mark.parametrize("case,reason", [
    ("fuel", "no_fuel"), ("event", "event_open"), ("exit", "not_at_exit"),
    ("enemy", "enemy_present"), ("charge", "drive_charging"),
    ("warp", "mid_warp"), ("transition", "transition_pending"),
])
def test_sector_leave_observable_blockers_do_not_call_native(case, reason):
    lua = sector_bridge()
    if case == "fuel":
        lua.globals().pl.fuel_count = 0
    elif case == "event":
        lua.globals().gui.choiceBoxOpen = True
    elif case == "exit":
        lua.globals().world.starMap.currentLoc.beacon = False
    elif case in ("enemy", "charge"):
        lua.execute("Hyperspace.ships.enemy={bDestroyed=false,_targetable={hostile=true}}")
        if case == "charge":
            lua.globals().pl.jump_timer.first = 20
    elif case == "warp":
        lua.globals().pl.bJumping = True
    else:
        lua.globals().world.starMap.bChoosingNewSector = True
    obs = step(lua, 1, [{"type": "leave_sector"}], 0)
    assert lua.globals().leave_calls == 0
    assert obs["action_feedback"][0] == {
        "action_index": 1, "type": "leave_sector", "status": "rejected", "reason": reason}


@pytest.mark.parametrize("mode,reason", [
    ("missing", "native_leave_unavailable"), ("error", "native_leave_failed")])
def test_sector_leave_native_transport_failures_are_visible(mode, reason):
    lua = sector_bridge()
    if mode == "missing":
        lua.globals().Hyperspace.benchmark_leave_sector = None
    else:
        lua.globals().native_leave_error = True
    obs = step(lua, 1, [{"type": "leave_sector"}], 0)
    assert obs["action_feedback"][0]["status"] == "rejected"
    assert obs["action_feedback"][0]["reason"] == reason


@pytest.mark.parametrize("hostile", [False, None])
def test_sector_leave_retained_neutral_or_unknown_pointer_defers_to_native_readiness(hostile):
    lua = sector_bridge()
    lua.execute("Hyperspace.ships.enemy={bDestroyed=false,_targetable={}}")
    lua.globals().Hyperspace.ships.enemy._targetable.hostile = hostile
    obs = step(lua, 1, [{"type": "leave_sector"}], 0)
    assert lua.globals().leave_calls == 1
    assert obs["action_feedback"] == [{"action_index": 1, "type": "leave_sector", "status": "applied"}]
    lua.globals().native_leave_result = False
    refused = step(lua, 2, [{"type": "leave_sector"}], 0)
    assert lua.globals().leave_calls == 2
    assert refused["action_feedback"][0]["reason"] == "native_leave_refused"


@pytest.mark.parametrize("marker,binding,expected", [
    (None, True, False), (0, True, False), (1, True, True), (1, False, False)])
def test_sector_navigation_capability_requires_repaired_native_marker_and_binding(marker, binding, expected):
    lua = economy_bridge()
    lua.globals().economy.sector_navigation_version = marker
    lua.globals().Hyperspace.benchmark_leave_sector = lua.eval("function() return true end") if binding else None
    obs = step(lua, 1, [], 0)
    assert obs["capabilities"]["sector_navigation"] is expected
