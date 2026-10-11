"""Actual shipped Lua must initialize a fixture before the first render snapshot."""
import ast
import json
from pathlib import Path
import sys

import pytest

from ftl_bench.cli import _bench_root

sys.path.insert(0, str(_bench_root() / "harness/tests"))
from test_visual_bridge_lua import visual_bridge, request, render

DRIVER = _bench_root() / "scripts/validate_visual_challenges.py"
FIXTURE = next(ast.literal_eval(node.value) for node in ast.parse(DRIVER.read_text()).body
               if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FIXTURE_LUA" for t in node.targets))


def fixture(kind="combat"):
    lua = visual_bridge()
    lua.execute('''
      pl.jump_timer={first=12,second=85}
      crew={iShipId=0,health={first=100,second=100}}
      function crew:DirectModifyHealth(delta) self.health.first=self.health.first+delta end
      pl.vCrewList={[0]=crew}
      fire_calls=0;damage_calls=0;seed_calls=0;action_reads=0
      system={healthState={first=2,second=2}}
      function system:GetRoomId() return 2 end
      function system:AddDamage(amount) damage_calls=damage_calls+1;self.healthState.first=1 end
      function pl:GetSystem(id) return system end
      function pl:StartFire(room) fire_calls=fire_calls+1 end
      enemyWeapon={cooldown={first=3,second=8}}
      function enemy:GetWeaponList() return vec({enemyWeapon}) end
      -- Fresh construction already seeded both generators; fixture6 must not reseed.
      _G.ftl_bench_state.benchmark_setup={phase="visual",active=false,
        native_seed={contract="fresh-start-seed-v3",contract_version=3,seed=1,
          applied=true,pending=false,failed=false,native_seed_applications=1,c_runtime_seed_applications=1}}
      Hyperspace.setRandomSeed=function(seed) seed_calls=seed_calls+1;last_rng_seed=seed end
      local original_reader=Hyperspace.read_json_action
      Hyperspace.read_json_action=function() action_reads=action_reads+1;return original_reader() end
    ''')
    lua.execute(FIXTURE.replace("__ID__", json.dumps("admission-test")).replace("__CHALLENGE__", json.dumps(kind)))
    return lua


@pytest.mark.parametrize("kind", ["combat", "fire-crew-recovery", "repair-charge-escape"])
def test_fixture_applied_before_render_and_first_capture_without_second_read(kind):
    lua = fixture(kind)
    request(lua, 7)
    # This seam is BEFORE render(lua): pixels have not yet been drawn or captured.
    assert lua.globals().captures == 0
    assert lua.globals().action_reads == 1
    assert lua.globals().pl.jump_timer.first == 0
    assert lua.globals().seed_calls == 0
    if kind == "combat":
        assert lua.globals().enemyWeapon.cooldown.first == 0
    elif kind == "fire-crew-recovery":
        assert lua.globals().crew.health.first == 50 and lua.globals().fire_calls == 1
    else:
        assert lua.globals().system.healthState.first == 1 and lua.globals().damage_calls == 1
    first = render(lua)
    assert first["visual_challenge_fixture"]["applied"] is True
    assert first["visual_challenge_fixture"]["applied_before_first_capture"] is True
    assert first["visual_challenge_fixture"]["admission_action_seq"] == first["last_action_seq"] == 7
    assert first["visual"]["world_updates"] == "0"
    assert first["visual_challenge_fixture"]["initial_rng_seed"] == 1
    assert first["visual_challenge_fixture"]["rng_seed_applied_here"] is False
    assert first["visual_challenge_fixture"]["seed_contract"] == "fresh-start-seed-v3"
    lua.globals().engine_tick()
    assert render(lua)["visual"] == first["visual"]
    assert lua.globals().captures == 1
    assert lua.globals().seed_calls == 0


@pytest.mark.parametrize("packet", [
    {"seq": 7, "actions": [], "advance_frames": 1, "observation_mode": "visual-v1"},
    {"seq": 7, "actions": "bad", "advance_frames": 0, "observation_mode": "visual-v1"},
    {"seq": 7, "actions": [], "advance_frames": 0, "observation_mode": "visual-v1", "expected_capture_id": "wrong"},
    {"seq": 7, "actions": [], "advance_frames": 0, "observation_mode": "structured-v7"},
])
def test_unadmitted_or_advancing_packet_does_not_apply_fixture(packet):
    lua = fixture()
    lua.globals().action_json = json.dumps(packet)
    lua.globals().engine_tick()
    assert lua.globals().action_reads == 1
    assert lua.globals().seed_calls == 0
    assert lua.globals().pl.jump_timer.first == 12
    assert lua.globals().enemyWeapon.cooldown.first == 3
    assert len(lua.globals().input_calls) == 0


def test_external_input_rejection_does_not_initialize_fixture():
    lua = fixture()
    lua.globals().external_detected = True
    request(lua, 7)
    assert lua.globals().seed_calls == 0
    assert lua.globals().pl.jump_timer.first == 12


def test_setup_error_is_published_without_retries_or_claiming_success():
    lua = fixture("combat")
    lua.execute("enemy.GetWeaponList=nil")
    request(lua, 7)
    first = render(lua)
    evidence = first["visual_challenge_fixture"]
    assert evidence["applied"] is False and evidence["setup_error"]
    assert evidence.get("applied_before_first_capture") is not True
    lua.globals().engine_tick()
    assert render(lua)["visual"] == first["visual"]
    assert lua.globals().captures == 1
    assert lua.globals().seed_calls == 0


@pytest.mark.parametrize("mutation", [
    "_G.ftl_bench_state.benchmark_setup=nil",
    "_G.ftl_bench_state.benchmark_setup.phase='ready'",
    "_G.ftl_bench_state.benchmark_setup.native_seed.contract='fresh-start-seed-v2'",
    "_G.ftl_bench_state.benchmark_setup.native_seed.contract_version=2",
    "_G.ftl_bench_state.benchmark_setup.native_seed.pending=true",
    "_G.ftl_bench_state.benchmark_setup.native_seed.failed=true",
    "_G.ftl_bench_state.benchmark_setup.native_seed.native_seed_applications=2",
    "_G.ftl_bench_state.benchmark_setup.native_seed.c_runtime_seed_applications=0",
])
def test_fixture6_refuses_missing_or_invalid_fresh_native_admission_before_mutation(mutation):
    lua = fixture("fire-crew-recovery")
    lua.execute(mutation)
    request(lua, 7)
    assert lua.globals().captures == 0
    assert lua.globals().action_reads == 1
    assert lua.globals().seed_calls == 0
    assert lua.globals().pl.jump_timer.first == 12
    assert lua.globals().crew.health.first == 100
    assert lua.globals().fire_calls == 0
    first = render(lua)
    evidence = first["visual_challenge_fixture"]
    assert evidence["applied"] is False and evidence["setup_error"]
    lua.globals().engine_tick()
    assert render(lua)["visual"] == first["visual"]
    assert lua.globals().captures == 1
    assert lua.globals().fire_calls == 0
