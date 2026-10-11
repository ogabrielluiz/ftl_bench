"""Challenge acceptance requires native state evidence, not intended inputs."""
from copy import deepcopy
import importlib.util
import json
import re
from types import SimpleNamespace

import pytest

from ftl_bench.cli import _bench_root

spec = importlib.util.spec_from_file_location("visual_challenges", _bench_root() / "scripts/validate_visual_challenges.py")
challenge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(challenge)


def observed(kind="combat"):
    return {"seed": 1, "difficulty": 0, "game_started": True, "game_over": False,
        "paused": True, "choice_box_open": False, "last_action_seq": 1,
        "player_ship": {"blueprint": "PLAYER_SHIP_HARD", "hull": {"current": 30, "max": 30},
            "resources": {"fuel": 15}, "oxygen_pct": 100,
            "crew": [{"id": i, "player_owned": True, "dead": False, "room": i,
                      "health_current": 100, "health_max": 100} for i in range(3)],
            "systems": [{"id": 1, "room_id": 14, "power": 2, "damage": 0, "needs_repair": False},
                        {"id": 2, "room_id": 2, "power": 1, "damage": 0, "needs_repair": False}],
            "rooms": [{"room_id": 2, "fires": 0, "oxygen": 100}]},
        "enemy_ship": {"hostile": kind == "combat", "destroyed": False, "hull": {"current": 8, "max": 8},
                       "weapons": [{"slot": 0, "charge": 0, "charge_max": 8}]},
        "map": {"sector": 0, "hazard": "none", "current_pos": {"x": 49, "y": 231},
                "connected_beacons": [{"pos_x": 75, "pos_y": 250}]},
        "economy": {"navigation": {"can_jump": False, "drive_current": 0, "drive_max": 85}},
        "visual": {"world_updates": "5", "simulated_updates": "5", **challenge.TIME_CONTRACT},
        "capabilities": {"world_updates": "5", "simulated_updates": "5", **challenge.TIME_CONTRACT},
        "visual_evaluator": {"map_open": False, "player_jumping": False, "store_open": False},
        "ftl_score_components": {"ships_destroyed": 0, "scrap_collected": 0},
        "visual_challenge_system_health": [{"system_id": 1, "health_current": 2, "health_max": 2, "damaged_bars": 0},
                                           {"system_id": 2, "health_current": 1, "health_max": 1, "damaged_bars": 0}],
        "visual_challenge_fixture": {"challenge": kind, "applied": True, "initial_rng_seed": 1,
            "applied_before_first_capture": True, "admission_action_seq": 1,
            "initial_drive_reset_requested": True, "enemy_weapon_charge_reset_requested": True}}


def initial(kind):
    raw = observed(kind)
    if kind != "combat":
        raw["map"]["current_pos"] = {"x": 88, "y": 152}
        raw["visual_challenge_fixture"].update(initial_drive_reset_requested=True)
    if kind == "fire-crew-recovery":
        raw["player_ship"]["crew"][0]["health_current"] = 50
        raw["player_ship"]["rooms"][0]["fires"] = 1
        raw["visual_challenge_fixture"].update(injured_crew_id=0, fire_room=2)
    elif kind == "repair-charge-escape":
        raw["player_ship"]["systems"][0].update(damage=2, needs_repair=True, power=0)
        raw["visual_challenge_system_health"][0].update(health_current=1, damaged_bars=1)
        raw["visual_challenge_fixture"].update(engine_health_before=2, engine_health_max_before=2)
    from test_challenge_setup import good_receipt
    raw["deterministic_setup"] = good_receipt()["deterministic_setup"]
    raw["visual"].update(world_updates="90", simulated_updates="90")
    raw["capabilities"].update(world_updates="90", simulated_updates="90")
    raw["visual_challenge_fixture"].update(rng_seed_applied_here=False)
    return raw


def rows(*observations):
    return [{"i": i, "kind": "reset" if i == 0 else "step", "obs": raw}
            for i, raw in enumerate(observations)]


@pytest.mark.parametrize("kind", list(challenge.TASKS))
def test_precondition_rejects_missing_facts_and_wrong_fixture(kind):
    raw = initial(kind)
    assert challenge.setup_proof(kind, raw)["passed"]
    for change in (lambda r: r["visual_challenge_fixture"].update(applied=False),
                   lambda r: r.update(seed=2),
                   lambda r: r["map"].update(hazard="sun"),
                   lambda r: r.update(choice_box_open=True),
                   lambda r: r["visual"].pop("world_updates"),
                   lambda r: r["economy"]["navigation"].update(drive_current=85)):
        invalid = deepcopy(raw)
        change(invalid)
        assert not challenge.setup_proof(kind, invalid)["passed"]


def test_signature_preserves_gameplay_facts_and_ignores_capture_wall_time():
    raw = initial("fire-crew-recovery")
    after = deepcopy(raw)
    after.update(tick=900, timestamp=1234)
    after["visual"].update(world_updates="900", capture_id=99)
    assert challenge.gameplay_signature(raw) == challenge.gameplay_signature(after)
    after["player_ship"]["crew"][0]["health_current"] = 51
    assert challenge.gameplay_signature(raw) != challenge.gameplay_signature(after)


@pytest.mark.parametrize("source,key,value", [
    ("visual", "visual_clock_version", 1),
    ("capabilities", "fixed_step_denominator", 59),
    ("visual", "fixed_step_numerator", True),
    ("capabilities", "simulated_updates", "6"),
    ("visual", "world_updates", "٥"),
    ("capabilities", "world_updates", 5),
])
def test_time_contract_requires_native_fixed_step_and_both_exact_counters(source, key, value):
    raw = initial("combat")
    assert challenge.time_contract_proof(raw)["passed"]
    raw[source][key] = value
    assert not challenge.time_contract_proof(raw)["passed"]
    assert not challenge.setup_proof("combat", raw)["passed"]


def test_signature_keeps_fixed_step_and_rng_identity():
    raw = initial("combat")
    for change in (lambda r: r["visual"].update(fixed_step_denominator=30),
                   lambda r: r["visual_challenge_fixture"].update(initial_rng_seed=2)):
        after = deepcopy(raw)
        change(after)
        assert challenge.gameplay_signature(raw) != challenge.gameplay_signature(after)


def combat_rows():
    before = initial("combat")
    after = deepcopy(before)
    after["visual"]["world_updates"] = "605"
    after["enemy_ship"].update(destroyed=True, hull={"current": 0, "max": 8})
    after["ftl_score_components"].update(ships_destroyed=1, scrap_collected=12)
    return rows(before, after)


def test_combat_needs_native_defeat_reward_survival_and_simulation():
    trajectory = combat_rows()
    assert challenge.outcome_proof("combat", trajectory)["achieved"]
    for change in (lambda r: r["enemy_ship"].update(destroyed=False),
                   lambda r: r["ftl_score_components"].update(scrap_collected=0),
                   lambda r: r["ftl_score_components"].update(ships_destroyed=0),
                   lambda r: r["visual"].update(world_updates="5"),
                   lambda r: r["player_ship"]["crew"][0].update(dead=True),
                   lambda r: r["map"].update(current_pos={"x": 75, "y": 250})):
        invalid = deepcopy(trajectory)
        change(invalid[-1]["obs"])
        assert not challenge.outcome_proof("combat", invalid)["achieved"]


def fire_rows():
    before = initial("fire-crew-recovery")
    after = deepcopy(before)
    after["visual"]["world_updates"] = "1205"
    after["player_ship"]["rooms"][0]["fires"] = 0
    after["player_ship"]["crew"][0]["health_current"] = 100
    return rows(before, after)


def test_fire_recovery_needs_exhaustive_fire_counts_health_oxygen_and_survival():
    trajectory = fire_rows()
    assert challenge.outcome_proof("fire-crew-recovery", trajectory)["achieved"]
    for change in (lambda r: r["player_ship"]["rooms"][0].pop("fires"),
                   lambda r: r["player_ship"]["crew"][0].update(health_current=99),
                   lambda r: r["player_ship"].update(oxygen_pct=89),
                   lambda r: r["visual_challenge_system_health"][1].update(health_current=0, damaged_bars=1),
                   lambda r: r["player_ship"]["systems"][1].update(power=0)):
        invalid = deepcopy(trajectory)
        change(invalid[-1]["obs"])
        assert not challenge.outcome_proof("fire-crew-recovery", invalid)["achieved"]


def escape_rows():
    before = initial("repair-charge-escape")
    ready = deepcopy(before)
    ready["visual"]["world_updates"] = "905"
    ready["player_ship"]["systems"][0].update(damage=0, power=2, needs_repair=False)
    ready["visual_challenge_system_health"][0].update(health_current=2, damaged_bars=0)
    ready["economy"]["navigation"].update(drive_current=85, can_jump=True)
    ready["visual_evaluator"]["map_open"] = True
    after = deepcopy(ready)
    after["visual"]["world_updates"] = "1005"
    after["map"]["current_pos"] = {"x": 75, "y": 250}
    after["player_ship"]["resources"]["fuel"] = 14
    after["economy"]["navigation"].update(drive_current=0, can_jump=False)
    return rows(before, ready, after)


def test_repair_escape_needs_repaired_powered_ready_map_connected_arrival_and_fuel():
    trajectory = escape_rows()
    assert challenge.outcome_proof("repair-charge-escape", trajectory)["achieved"]
    assert not challenge.outcome_proof("repair-charge-escape", [trajectory[0], trajectory[2]])["achieved"]
    for index, change in ((1, lambda r: r["visual_challenge_system_health"][0].update(health_current=1, damaged_bars=1)),
                         (1, lambda r: r["player_ship"]["systems"][0].update(power=0)),
                         (2, lambda r: r["player_ship"]["resources"].update(fuel=15)),
                         (2, lambda r: r["map"].update(current_pos={"x": 100, "y": 100})),
                         (2, lambda r: r["visual_evaluator"].update(player_jumping=True))):
        invalid = deepcopy(trajectory)
        change(invalid[index]["obs"])
        assert not challenge.outcome_proof("repair-charge-escape", invalid)["achieved"]


def test_repair_progress_zero_does_not_mean_system_bars_are_repaired():
    before = initial("repair-charge-escape")
    before["player_ship"]["systems"][0].update(damage=0, power=1)
    assert challenge.setup_proof("repair-charge-escape", before)["passed"]
    trajectory = escape_rows()
    trajectory[1]["obs"]["visual_challenge_system_health"][0].update(health_current=1, damaged_bars=1)
    assert not challenge.outcome_proof("repair-charge-escape", trajectory)["achieved"]
    before.pop("visual_challenge_system_health")
    assert not challenge.setup_proof("repair-charge-escape", before)["passed"]


def test_input_intent_and_ack_do_not_count_as_gameplay_success():
    raw = initial("combat")
    trajectory = rows(raw, deepcopy(raw))
    trajectory[-1].update(actions=[{"type": "click", "x": 100, "y": 100}], thought="Enemy defeated")
    assert not challenge.outcome_proof("combat", trajectory)["achieved"]
    assert challenge.classify_outcome(challenge.outcome_proof("combat", trajectory), trajectory,
                                     "decision_budget") == "budget_exhausted"
    assert challenge.classify_outcome(challenge.outcome_proof("combat", trajectory), trajectory,
                                     "decision_budget", RuntimeError("capture unavailable")) == "infrastructure_failure"


def test_native_loss_is_a_valid_failed_outcome():
    trajectory = combat_rows()
    trajectory[-1]["obs"]["player_ship"]["crew"][0].update(dead=True, health_current=0)
    proof = challenge.outcome_proof("combat", trajectory)
    assert challenge.classify_outcome(proof, trajectory, "decision_budget") == "failed_native_loss"


def test_protocol_and_backend_errors_remain_distinct_and_missing_crew_is_not_loss():
    trajectory = combat_rows()
    proof = challenge.outcome_proof("combat", trajectory)
    assert challenge.classify_outcome(proof, trajectory, "visual_model_error",
        challenge.VisualProtocolError("bad decision")) == "protocol_failure"
    assert challenge.classify_outcome(proof, trajectory, "visual_backend_error",
        challenge.VisualBackendError("service timeout")) == "infrastructure_failure"
    trajectory[-1]["obs"]["player_ship"].pop("crew")
    proof = challenge.outcome_proof("combat", trajectory)
    assert challenge.classify_outcome(proof, trajectory, "decision_budget") == "budget_exhausted"


def test_actor_audit_needs_real_image_and_cli_tool_free_events():
    trajectory = combat_rows()
    step = trajectory[-1]
    step.update(model={"provider": "codex", "tool_use": False, "image": {"sha256": "same"},
                       "events": [{"type": "turn.completed"}]},
                visual={"before": {"sha256": "same"}})
    assert challenge.actor_audit(trajectory)
    step["model"]["image"]["sha256"] = "other"
    assert not challenge.actor_audit(trajectory)


def test_fixture_only_mutates_setup_once_and_never_fabricates_outcomes():
    data = challenge.fixture_bridge(b"-- pinned production\n", "fire-crew-recovery", "trial")
    assert data.startswith(b"-- pinned production\n")
    assert b"crew:DirectModifyHealth" in data and b"p:StartFire" in data
    assert b"engines:AddDamage(2)" in data
    assert b"not visualChallenge.applied" in data
    for illegal in (b"drive_current=", b"bDestroyed=", b"world_updates=", b"frame_budget=",
                    b"can_jump=", b"readyToTravel=", b"ships_destroyed=", b"scrap_collected="):
        assert not re.search(re.escape(illegal[:-1]) + rb"\s*=(?!=)", data)


def test_lua_fixture_applies_once_and_reports_missing_binding_honestly():
    lua = pytest.importorskip("lupa").LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      crew={iShipId=0,health={first=100,second=100}}
      function crew:DirectModifyHealth(delta) self.health.first=self.health.first+delta end
      player={vCrewList={[0]=crew},fire_calls=0,engine_calls=0,jump_timer={first=85,second=85}}
      function player:GetSystem(id) return {GetRoomId=function() return 2 end,
            healthState={first=2,second=2},
        AddDamage=function() player.engine_calls=player.engine_calls+1 end} end
      function player:StartFire(room) self.fire_calls=self.fire_calls+1 end
      Hyperspace={App={world={bStartedGame=true},gui={choiceBoxOpen=false}},ships={player=player},
        benchmark_write_visual_observation=function(payload) return payload end,
        setRandomSeed=function(seed) last_rng_seed=seed end}
      _G.ftl_bench_state={observation_mode="visual-v1",visual_pending=true,visual_requested_frames=0,
        frame_budget=0,last_applied_seq=1,
        benchmark_setup={phase="visual",native_seed={contract="fresh-start-seed-v3",contract_version=3,
            applied=true,pending=false,failed=false,native_seed_applications=1,c_runtime_seed_applications=1,seed=1}}}
      _G.ftl_bench_tick=function() end
      json={decode=function() return {} end,encode=function(value) last_observation=value;return '{}' end}
    ''')
    lua.execute(challenge.fixture_bridge(b"", "fire-crew-recovery", "once").decode())
    lua.globals().ftl_bench_tick()
    lua.globals().ftl_bench_tick()
    assert lua.globals().player.fire_calls == 1
    assert lua.globals().crew.health.first == 50
    lua.globals().Hyperspace.benchmark_write_visual_observation("{}")
    assert lua.globals().last_observation.visual_challenge_fixture.applied is True
    lua.execute('''player.StartFire=nil; _G.ftl_bench_tick=function() end
        Hyperspace.benchmark_write_visual_observation=function(payload) return payload end''')
    lua.execute(challenge.fixture_bridge(b"", "fire-crew-recovery", "missing").decode())
    lua.globals().ftl_bench_tick()
    lua.globals().Hyperspace.benchmark_write_visual_observation("{}")
    fixture = lua.globals().last_observation.visual_challenge_fixture
    assert fixture.applied is False and fixture.setup_error


def test_parser_freezes_repeats_and_budgets():
    args = challenge.parser().parse_args(["--challenge", "combat", "--mode", "hybrid", "--repeat-index", "3"])
    assert args.max_decisions == 60 and args.max_wall_seconds == 1800
    assert args.seed == 1 and args.max_idle_decisions == 8 and args.reasoning_effort == "medium"
    with pytest.raises(SystemExit):
        challenge.main(["--seed", "2", "--setup-only"])
    with pytest.raises(SystemExit):
        challenge.main(["--repeat-index", "3", "--repeats", "2", "--setup-only"])


def test_frozen_child_refuses_wrong_runtime_before_actor(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(_bench_root() / "scripts"))
    import run_visual_experiment
    checked = []
    monkeypatch.setattr(run_visual_experiment, "verify_protocol", lambda protocol: checked.append(protocol))
    cli = {"sha256": "cli"}
    accepted = {"native_acceptance": {"runtime": {"dll_sha256": "dll", "patch_sha256": "patch",
        "production_bridge_sha256": "source", "fresh_start_seed": True, "fresh_seed_contract_version": 3,
        "fresh_seed_contract": "fresh-start-seed-v3"}}, "codex_cli": cli}
    fingerprint = {"native_dll": {"sha256": "dll"}, "native_build": {"patch_sha256": "patch", "fresh_start_seed": True,
        "fresh_seed_contract_version": 3, "fresh_seed_contract": "fresh-start-seed-v3"},
                   "bridge_lua": {"sha256": "fixture"}}
    challenge.verify_experiment_runtime(accepted, fingerprint, cli, "source", "fixture")
    assert checked == [accepted]
    for change in (lambda f: f["native_dll"].update(sha256="other"),
                   lambda f: f["native_build"].update(patch_sha256="other"),
                   lambda f: f["bridge_lua"].update(sha256="other")):
        invalid = deepcopy(fingerprint)
        change(invalid)
        with pytest.raises(RuntimeError):
            challenge.verify_experiment_runtime(accepted, invalid, cli, "source", "fixture")
    with pytest.raises(RuntimeError):
        challenge.verify_experiment_runtime(accepted, fingerprint, {"sha256": "other"}, "source", "fixture")
    with pytest.raises(RuntimeError):
        challenge.verify_experiment_runtime(accepted, fingerprint, cli, "other", "fixture")


def test_production_cli_executes_argument_validation_before_any_launch():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(_bench_root() / "scripts/validate_visual_challenges.py"),
        "--seed", "2", "--setup-only"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "freezes seed 1" in result.stderr
    assert "Run collect.py" not in result.stderr


def test_fire_task_v2_and_secondary_firefighting_injury_require_all_crew_recovery():
    # Actual historical false-negative state: original patient healed, firefighter hurt.
    trajectory = fire_rows()
    final = trajectory[-1]["obs"]
    final["player_ship"]["crew"][1]["health_current"] = 76.484016418457
    proof = challenge.outcome_proof("fire-crew-recovery", trajectory)
    assert proof["checks"]["ship_and_crew_survive"]
    assert final["player_ship"]["crew"][0]["health_current"] == 100
    assert {key for key, passed in proof["checks"].items() if not passed} == {"all_crew_full_health"}
    assert not proof["achieved"]
    identity = challenge.task_identity("fire-crew-recovery")
    assert identity["task_version"] == "fire-crew-recovery-task-v2"
    assert "ALL crew members to full health" in identity["task"]
    assert "any injuries sustained during firefighting" in identity["task"]
    final["player_ship"]["crew"][1]["health_current"] = 100
    assert challenge.outcome_proof("fire-crew-recovery", trajectory)["achieved"]


@pytest.mark.parametrize("kind", list(challenge.TASKS))
def test_task_protocol_identity_rejects_stale_text_hash_or_version_before_launch(kind, tmp_path):
    import hashlib
    identity = challenge.task_identity(kind)
    assert identity["task_sha256"] == hashlib.sha256(identity["task"].encode()).hexdigest()
    protocol = {"tasks": {kind: identity}, "task_versions": {kind: identity["task_version"]}}
    challenge.verify_task_protocol(protocol, kind)
    challenge.verify_task_protocol(None, kind)
    for mutate in (lambda p: p["tasks"][kind].update(task="old singular task"),
                   lambda p: p["tasks"][kind].update(task_sha256="0" * 64),
                   lambda p: p["tasks"][kind].update(task_version="old-version"),
                   lambda p: p["task_versions"].update({kind: "old-version"}),
                   lambda p: p.pop("tasks"), lambda p: p.pop("task_versions")):
        stale = deepcopy(protocol)
        mutate(stale)
        output = tmp_path / "must-not-start"
        with pytest.raises(RuntimeError, match="Frozen challenge task/version"):
            challenge.run_trial(SimpleNamespace(), kind, 1, output, {}, stale)
        assert not output.exists()


@pytest.mark.parametrize("boundary", ["before_protected", "after_launch", "in_runner"])
def test_cooperative_trial_stop_retains_attribution_before_cleanup(tmp_path, monkeypatch, boundary):
    from contextlib import contextmanager
    from visual_cancellation import request_stop, CooperativeStop
    from test_challenge_setup import first_frame, good_packets
    frame = first_frame(tmp_path)
    raw = initial("fire-crew-recovery")
    raw["visual"].update(frame.observation.raw["visual"])
    frame.observation.raw = raw
    frame.observation.last_action_seq = 4
    stop = tmp_path / "STOP.json"
    out = tmp_path / "trial"
    lifecycle = []
    if boundary == "before_protected":
        request_stop(stop, "cohort", "assistant", "task/scoring mismatch")
    class Protected:
        def __init__(self, user, backup, bridge):
            self.backup = backup
        @contextmanager
        def protected(self):
            lifecycle.append("enter")
            try:
                yield self
            finally:
                terminal = challenge.load_trajectory(out / "trajectory.jsonl")[-1]
                assert terminal["kind"] == "end"
                assert terminal["stop_request"]["request"]["initiator"] == "assistant"
                lifecycle.append("cleanup")
                self.backup.mkdir(parents=True)
                (self.backup / "restoration.json").write_text('{"verified":true}')
        def launch(self):
            lifecycle.append("launch")
            if boundary == "after_launch":
                request_stop(stop, "cohort", "assistant", "task/scoring mismatch")
    monkeypatch.setattr(challenge, "ProtectedGame", Protected)
    monkeypatch.setattr(challenge, "ftl_user_folder", lambda: tmp_path / "user")
    monkeypatch.setattr(challenge, "runtime_fingerprint", lambda root: {"native_build": {"matches_installed_dll": True}})
    monkeypatch.setattr(challenge, "AgentSession", lambda **kw: SimpleNamespace(setup_packets=good_packets()))
    monkeypatch.setattr(challenge, "prepare", lambda *args: None)
    monkeypatch.setattr(challenge, "VisualSession", lambda *args: SimpleNamespace(capture=lambda: frame))
    monkeypatch.setattr(challenge, "verify_visual_setup", lambda *args: {"verified": True})
    monkeypatch.setattr(challenge, "CodexVisualAgent", lambda **kw: SimpleNamespace(instruction_identity=lambda: {}))
    def runner(transport, agent, recorder, **kw):
        lifecycle.append("runner")
        assert kw["stop_control"].path == stop.resolve()
        assert kw["stop_control"].scope == "cohort"
        assert kw["experiment"]["task_version"] == "fire-crew-recovery-task-v2"
        assert kw["experiment"]["actor_identity"]["task_version"] == "fire-crew-recovery-task-v2"
        request_stop(stop, "cohort", "assistant", "task/scoring mismatch")
        kw["stop_control"].check("after_actor_before_dispatch")
    monkeypatch.setattr(challenge, "run_loop", runner)
    args = challenge.parser().parse_args(["--stop-file", str(stop), "--stop-scope", "cohort"])
    with pytest.raises(CooperativeStop):
        challenge.run_trial(args, "fire-crew-recovery", 1, out, {"path": "not-called"}, None)
    archived = json.loads((out / "run.json").read_text())
    validation = json.loads((out / "validation.json").read_text())
    terminal = challenge.load_trajectory(out / "trajectory.jsonl")[-1]
    assert archived["status"] == terminal["status"] == "interrupted"
    assert archived["reason"] == terminal["reason"] == "cooperative_stop_requested"
    assert archived["stop_request"] == validation["stop_request"] == terminal["stop_request"]
    assert archived["stop_request"]["request"]["initiator"] == "assistant"
    assert validation["outcome_category"] == "operator_interruption"
    assert archived["task_version"] == "fire-crew-recovery-task-v2"
    assert not any(r.get("model") for r in challenge.load_trajectory(out / "trajectory.jsonl"))
    if boundary == "before_protected":
        assert lifecycle == []
        assert validation["save_restoration_verified"] is False  # Protection never entered.
    else:
        assert lifecycle[-1] == "cleanup"
        assert validation["save_restoration_verified"] is True


def test_stop_scope_requires_file_before_runtime_identity(monkeypatch):
    monkeypatch.setattr(challenge, "codex_runtime_identity", lambda: pytest.fail("No CLI call allowed"))
    with pytest.raises(SystemExit):
        challenge.main(["--stop-scope", "cohort"])


@pytest.fixture
def portable_child(tmp_path, monkeypatch):
    """Real child/admission gates with offline lifecycle and baseline boundaries."""
    from contextlib import contextmanager
    from ftl_bench import visual_admission, native_acceptance
    from ftl_bench.controller_admission import AdmissionError
    from test_challenge_setup import first_frame, good_packets
    monkeypatch.syspath_prepend(str(_bench_root() / "scripts"))
    import run_visual_experiment
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    cli = {"path": "offline-cli", "sha256": "1" * 64}
    production_hash = challenge.digest((_bench_root() / native_acceptance.BRIDGE).read_bytes())
    runtime = {**native_acceptance.CAPABILITIES, "dll_sha256": "2" * 64,
               "patch_sha256": "3" * 64, "production_bridge_sha256": production_hash}
    installed = {"files_sha256": {name: challenge.digest(name.encode()) for name in native_acceptance.RUNTIME_FILES},
                 "native_build": {**runtime, "matches_installed_dll": True}}
    installed["files_sha256"]["Hyperspace.dll"] = runtime["dll_sha256"]
    protocol = {"contract": "ftl-visual-challenge-matrix-v2", "models": ["gpt-6.1-sol", "gpt-6-luna"],
        "modes": ["image", "hybrid"], "challenges": list(challenge.TASKS), "repetitions": 3,
        "seed": 1, "reasoning_effort": "medium", "budgets": {"decisions": 60, "wall_seconds": 1800, "idle_decisions": 8},
        "codex_cli": deepcopy(cli), "native_acceptance": {"runtime": runtime},
        "tasks": {name: challenge.task_identity(name) for name in challenge.TASKS},
        "task_versions": dict(challenge.TASK_VERSIONS),
        "admission_selector": {"spec": {"sha256": "4" * 64},
            "admission": {"runtime": runtime, "runtime_files": deepcopy(installed["files_sha256"])}}}
    protocol_file = cohort / "protocol.json"
    protocol_file.write_text(json.dumps(protocol))
    args = challenge.parser().parse_args(["--challenge", "combat", "--experiment-file", str(protocol_file)])
    output = cohort / "trials/gpt-6.1-sol/image/combat/repeat-01/repetition-01/combat"
    events, state = [], {"archive_valid": True, "bridge_valid": True, "actor_calls": 0}
    user = tmp_path / "user"
    user.mkdir()
    class Protected:
        def __init__(self, user, backup, bridge):
            self.backup, self.bridge = backup, bridge
        @contextmanager
        def protected(self):
            events.append("protected")
            try:
                yield self
            finally:
                events.append("cleanup")
                self.backup.mkdir(parents=True)
                (self.backup / "restoration.json").write_text('{"verified":true}')
        def launch(self):
            events.append("deploy")
            data = self.bridge.read_bytes()
            (user / "ftl_bench_dev.lua").write_bytes(data)
            state["fixture_hash"] = challenge.digest(data)
    def fingerprint(root):
        return {"native_dll": {"sha256": runtime["dll_sha256"]},
            "native_build": deepcopy(installed["native_build"]),
            "bridge_lua": {"sha256": state["fixture_hash"] if state["bridge_valid"] else "5" * 64}}
    def baseline(value, *, directory, verify_installed):
        events.append("baseline")
        assert value == protocol and directory == cohort and verify_installed is False
        assert (user / "ftl_bench_dev.lua").is_file()
        if not state["archive_valid"]:
            raise AdmissionError("Frozen archive byte mismatch")
    def actual(root):
        events.append("installed")
        return deepcopy(installed)
    frame = first_frame(tmp_path)
    raw = initial("combat")
    raw["visual"].update(frame.observation.raw["visual"])
    frame.observation.raw = raw
    class Actor:
        def __init__(self, **kw):
            events.append("actor_created")
        def instruction_identity(self):
            return {}
        def decide(self, observation):
            receipt = json.loads((output / "controller-admission.json").read_text())
            assert receipt["accepted"] is True
            events.append("actor_call")
            state["actor_calls"] += 1
            raise RuntimeError("Offline actor boundary reached")
    def runner(transport, agent, recorder, **kw):
        agent.decide(None)
    monkeypatch.setattr(challenge, "ProtectedGame", Protected)
    monkeypatch.setattr(challenge, "ftl_user_folder", lambda: user)
    monkeypatch.setattr(challenge, "runtime_fingerprint", fingerprint)
    monkeypatch.setattr(run_visual_experiment, "verify_protocol", baseline)
    monkeypatch.setattr(visual_admission, "installed_runtime", actual)
    monkeypatch.setattr(challenge, "AgentSession", lambda **kw: SimpleNamespace(setup_packets=good_packets()))
    monkeypatch.setattr(challenge, "prepare", lambda *args: events.append("setup"))
    monkeypatch.setattr(challenge, "VisualSession", lambda *args: SimpleNamespace(capture=lambda: frame))
    monkeypatch.setattr(challenge, "verify_visual_setup", lambda *args: {"verified": True})
    monkeypatch.setattr(challenge, "first_capture_proof", lambda *args: {"passed": True})
    monkeypatch.setattr(challenge, "packet_proof", lambda *args: {"passed": True})
    monkeypatch.setattr(challenge, "receipt_proof", lambda *args: {"passed": True})
    monkeypatch.setattr(challenge, "CodexVisualAgent", Actor)
    monkeypatch.setattr(challenge, "run_loop", runner)
    def run():
        return challenge.run_trial(args, "combat", 1, output, cli, protocol)
    return locals()


def test_portable_challenge_real_gate_accepts_before_actor_and_protected_cleanup(portable_child):
    d = portable_child
    result = d["run"]()
    receipt = json.loads((d["output"] / "controller-admission.json").read_text())
    manifest = json.loads((d["output"] / "run.json").read_text())
    assert receipt["accepted"] is True and "error" not in receipt
    assert receipt["configuration"]["model"] == d["args"].model
    assert manifest["controller_admission_sha256"] == challenge.digest((d["output"] / "controller-admission.json").read_bytes())
    assert d["events"].index("deploy") < d["events"].index("baseline") < d["events"].index("installed") < d["events"].index("actor_call")
    assert d["state"]["actor_calls"] == 1 and d["events"][-1] == "cleanup"
    assert result["save_restoration_verified"] is True
    assert not (d["user"] / "ftl_bench_dev.lua").exists()


@pytest.mark.parametrize("mutation", ["model", "mode", "reasoning", "decisions", "wall", "idle", "seed", "setup_only",
    "runtime", "bridge", "archive", "cli", "output", "protocol_file"])
def test_portable_challenge_rejection_keeps_zero_calls_receipt_and_cleanup(portable_child, mutation):
    d = portable_child
    if mutation in ("model", "mode", "reasoning", "decisions", "wall", "idle", "seed", "setup_only"):
        key, value = {"model": ("model", "gpt-6-luna"), "mode": ("mode", "hybrid"),
            "reasoning": ("reasoning_effort", "high"), "decisions": ("max_decisions", 61),
            "wall": ("max_wall_seconds", 1801), "idle": ("max_idle_decisions", 9),
            "seed": ("seed", 2), "setup_only": ("setup_only", True)}[mutation]
        setattr(d["args"], key, value)
    elif mutation == "runtime":
        d["installed"]["files_sha256"]["FTLGame.exe"] = "6" * 64
    elif mutation == "bridge":
        d["state"]["bridge_valid"] = False
    elif mutation == "archive":
        d["state"]["archive_valid"] = False
    elif mutation == "cli":
        # The protocol's recorded CLI remains unchanged on disk.
        d["cli"]["sha256"] = "7" * 64
    elif mutation == "output":
        # Keep every requested argument valid but bind to no frozen cell path.
        d["output"] = d["cohort"] / "other-trial"
    else:
        changed = deepcopy(d["protocol"])
        changed["contract"] = "ftl-visual-challenge-matrix-v1"
        d["protocol_file"].write_text(json.dumps(changed))
    if mutation == "output":
        result = challenge.run_trial(d["args"], "combat", 1, d["output"], d["cli"], d["protocol"])
    else:
        result = d["run"]()
    receipt = json.loads((d["output"] / "controller-admission.json").read_text())
    assert receipt["accepted"] is False and receipt["error"]
    assert d["state"]["actor_calls"] == 0
    assert "actor_created" not in d["events"] and "setup" not in d["events"]
    assert d["events"][-1] == "cleanup"
    assert result["outcome_category"] == "infrastructure_failure"
    assert result["save_restoration_verified"] is True
    assert not any(row.get("model") for row in challenge.load_trajectory(d["output"] / "trajectory.jsonl"))
    assert not (d["user"] / "ftl_bench_dev.lua").exists()


def test_setup_stop_after_ack_preserves_receipt_and_prevents_next_packet(tmp_path):
    from visual_cancellation import StopControl, CooperativeStop, request_stop
    stop = tmp_path / "STOP.json"
    calls = []
    class Session:
        def configure_setup(self, output, delay):
            pass
        def reset_episode(self, seed):
            calls.append(("fresh_start", seed))
            request_stop(stop, "cohort", "assistant", "stop before gameplay")
            return SimpleNamespace(raw={"native_start_ack": True})
        def reset(self):
            pytest.fail("No structured packet may follow observed stop")
    with pytest.raises(CooperativeStop) as raised:
        challenge.prepare(Session(), "fire-crew-recovery", tmp_path, StopControl(stop, "cohort"))
    assert calls == [("fresh_start", 1)]
    assert raised.value.evidence["observed_boundary"] == "after_setup_reset-episode-seed-one"
    assert json.loads((tmp_path / "setup.json").read_text())[0]["obs"] == {"native_start_ack": True}
