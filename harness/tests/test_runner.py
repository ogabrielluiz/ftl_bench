"""Runner regressions use recorded observations and never launch the actual game."""
import json
import sys
from pathlib import Path

import pytest

from ftl_bench import Observation, Scenario, SubObjective, load_trajectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import run_benchmark as runner


def observation(*, sector=0, difficulty=0, blueprint="PLAYER_SHIP_HARD", seed=1):
    return Observation.from_dict({
        "schema_version": 3, "tick": 1, "seed": seed, "game_started": True,
        "paused": True, "difficulty": difficulty,
        "capabilities": {"native_protocol": 5, "manual_fire": True,
                         "global_autofire_control": True, "victory": True, "live_score": True,
                         "crew_control_guard": True, "crew_ownership": True,
                         "event_choice_state": True, "upgrade_rules": True, "fuel_recovery": True,
                         "sector_navigation": True, "beacon_navigation": True, "enemy_hostility": True},
        "economy": {"sector_navigation_version": 1, "beacon_navigation_version": 1,
                    "navigation": {"can_jump": True, "enemy_defeat_pending": False}},
        "map": {"sector": sector, "current_pos": {"x": sector, "y": 0}},
        "player_ship": {"blueprint": blueprint, "hull": {"current": 30},
                        "crew": [{"dead": False}]},
    })


class Session:
    def __init__(self, obs=None):
        self.obs = obs or observation()
        self.recorder = None

    def reset_episode(self, **kwargs):
        self.recorder.record("reset_episode", [{"type": "reset_episode", "seed": 1}], self.obs)
        return self.obs

    def observe(self):
        return self.obs

    def _sync_seq(self):
        pass

    def reach_goal(self):
        self.obs = observation(sector=1)
        self.recorder.record("step", [{"type": "leave_sector"}], self.obs)


@pytest.fixture(autouse=True)
def no_native_game(monkeypatch):
    monkeypatch.setattr(runner, "game_alive", lambda: True)
    monkeypatch.setattr(runner, "restart_ftl", lambda: pytest.fail("tests must never restart FTL"))


@pytest.fixture
def scenario():
    return Scenario("probe", "reach_sector", 1, [SubObjective("sector", 1)])


def play_once(sess, scenario, agent, path):
    return runner._play_once(sess, scenario, agent, "test", path, lambda _: None, {}, ())


@pytest.mark.parametrize("missing", ["crew_control_guard", "crew_ownership", "event_choice_state",
                                     "upgrade_rules", "fuel_recovery", "sector_navigation", "beacon_navigation", "enemy_hostility"])
def test_runner_rejects_bridge_without_verified_crew_control_boundary(scenario, missing):
    obs = observation()
    obs.raw["capabilities"][missing] = False
    with pytest.raises(runner.SetupValidationError, match=missing):
        runner.verify_started_setup(obs, scenario)


def test_legacy_native_protocol_is_rejected_before_calling_the_model(tmp_path, scenario):
    obs = observation()
    obs.raw["capabilities"]["native_protocol"] = 4
    result = play_once(Session(obs), scenario,
                       lambda *_: pytest.fail("legacy controls must not reach the model"),
                       tmp_path / "probe.jsonl")
    assert result["status"] == "error" and result["reason"] == "setup_mismatch"
    assert "native_protocol>=5" in result["error"]


def test_completed_attempt_has_terminal_lifecycle_and_its_full_scenario(tmp_path, scenario):
    sess = Session()

    def agent(sess, scenario, log):
        sess.reach_goal()
        return {"status": "completed", "reason": "budget", "turns": 1}

    path = tmp_path / "probe.jsonl"
    result = play_once(sess, scenario, agent, path)
    records = load_trajectory(path)
    assert records[0]["meta"]["scenario"] == scenario.to_dict()
    assert records[0]["meta"]["runner_version"] == "v7"
    assert records[0]["meta"]["economy_contract"] == runner.ECONOMY_CONTRACT
    assert records[0]["meta"]["routing_contract"] == "native-sector-neighbors-v1"
    assert records[0]["meta"]["beacon_contract"] == "native-beacon-readiness-v1"
    assert records[0]["meta"]["hostility_contract"] == "native-enemy-hostility-v1"
    assert records[-1]["kind"] == "end"
    assert records[-1]["obs"] is None
    assert records[-1]["setup_verified"] is True
    assert result["status"] == "completed" and result["reason"] == "budget"
    assert result["solved"] is True and result["jumps_used"] == 1
    assert sess.recorder is None


@pytest.mark.parametrize("marker", [None, 0, True, "1"])
def test_sector_capability_alone_cannot_claim_repaired_native_routing(tmp_path, scenario, marker):
    obs = observation()
    obs.raw["economy"]["sector_navigation_version"] = marker
    result = play_once(Session(obs), scenario, lambda *_: pytest.fail("unrepaired routing reached agent"),
                       tmp_path / "probe.jsonl")
    assert result["reason"] == "setup_mismatch"
    assert "sector_navigation_version==1" in result["error"]


@pytest.mark.parametrize("missing", ["beacon_navigation_version", "can_jump", "enemy_defeat_pending"])
def test_beacon_capability_alone_cannot_claim_native_ready_before_model(tmp_path, scenario, missing):
    obs = observation()
    block = obs.raw["economy"] if missing == "beacon_navigation_version" else obs.raw["economy"]["navigation"]
    del block[missing]
    result = play_once(Session(obs), scenario, lambda *_: pytest.fail("unknown readiness reached model"),
                       tmp_path / "probe.jsonl")
    assert result["reason"] == "setup_mismatch" and missing in result["error"]


def test_agent_exception_is_finalized_unsolved_even_after_reaching_goal(tmp_path, scenario):
    sess = Session()

    def agent(sess, scenario, log):
        sess.reach_goal()
        raise RuntimeError("backend failed")

    path = tmp_path / "probe.jsonl"
    result = play_once(sess, scenario, agent, path)
    assert result["status"] == "error"
    assert result["error"] == "backend failed"
    assert result["solved"] is False
    assert load_trajectory(path)[-1]["reason"] == "agent_error"
    assert sess.recorder is None


def test_failed_agent_outcome_is_not_a_completed_solve(tmp_path, scenario):
    def agent(sess, scenario, log):
        sess.reach_goal()
        return {"status": "failed", "reason": "model_error"}

    result = play_once(Session(), scenario, agent, tmp_path / "probe.jsonl")
    assert result["status"] == "error" and result["solved"] is False


@pytest.mark.parametrize("values", [{"difficulty": 2}, {"blueprint": "PLAYER_SHIP_CIRCLE"},
                                    {"blueprint": None}, {"seed": 2}])
def test_setup_mismatch_cannot_play_or_claim_success(tmp_path, scenario, values):
    result = play_once(Session(observation(**values)), scenario,
                       lambda *_: pytest.fail("wrong setup must not reach agent"),
                       tmp_path / "probe.jsonl")
    assert result["status"] == "error" and result["reason"] == "setup_mismatch"
    assert result["solved"] is False


def test_unsupported_requested_ship_is_rejected_before_recording(tmp_path):
    scenario = Scenario("wrong", "reach_sector", 1, [SubObjective("sector", 1)], ship="engi")
    with pytest.raises(runner.SetupValidationError, match="only Kestrel A"):
        runner.run_instance(Session(), scenario, lambda *_: None, "test", tmp_path, lambda _: None)
    assert not list(tmp_path.iterdir())


def test_keyboard_interrupt_finalizes_and_detaches_the_recorder(tmp_path, scenario):
    sess = Session()

    def interrupted(*_):
        raise KeyboardInterrupt

    path = tmp_path / "probe.jsonl"
    with pytest.raises(KeyboardInterrupt):
        play_once(sess, scenario, interrupted, path)
    assert load_trajectory(path)[-1]["status"] == "interrupted"
    assert sess.recorder is None


def test_repeated_runs_preserve_results_and_publish_completion(tmp_path, monkeypatch):
    for _ in range(2):
        monkeypatch.setattr(sys, "argv", ["ftlbench run", "--max-instances", "0", "--out", str(tmp_path)])
        runner.main()
    directories = list(tmp_path.iterdir())
    assert len(directories) == 2
    assert directories[0].name != directories[1].name
    for directory in directories:
        lifecycle = json.loads((directory / "run.json").read_text())
        assert lifecycle["status"] == "completed"
        assert lifecycle["scenario_ids"] == []
        assert lifecycle["finished_at"] >= lifecycle["started_at"]
        assert (directory / "summary_scripted-gameover10.json").is_file()


def test_manifest_records_resolved_model_settings(tmp_path, monkeypatch):
    def agent(*_):
        pass

    agent.metadata = {"model": "resolved-model", "backend": "anthropic", "reasoning_effort": "high"}
    monkeypatch.setattr(runner, "make_llm_agent", lambda *_args, **_kwargs: agent)
    monkeypatch.setattr(sys, "argv", ["ftlbench run", "--agent", "llm", "--max-instances", "0",
                                     "--out", str(tmp_path)])
    runner.main()
    lifecycle = json.loads(next(tmp_path.glob("*/run.json")).read_text())
    assert lifecycle["model"] == "resolved-model"
    assert lifecycle["reasoning_effort"] == "high"


@pytest.mark.parametrize("hostile", [False, None, 1])
def test_random_baseline_does_not_fire_at_a_retained_nonhostile_or_unknown_ship(hostile):
    before, after = observation(), observation()
    before.map["connected_beacons"] = [{"index": 5}]
    after.map["current_pos"] = {"x": 1, "y": 0}
    before.enemy_ship = {"hull": {"current": 4}, "rooms": [{"room_id": 7}]}
    if hostile is not None:
        before.enemy_ship["hostile"] = hostile
    before.player_ship["weapons"] = [{"slot": 0, "powered": True}]
    scenario = Scenario("one", "full_run", 1, [], budget_jumps=1)
    class RandomSession:
        def observe(self): return before
        def jump(self, index, advance_frames):
            assert index == 5
            return after
        def fire_weapon(self, *_args, **_kwargs):
            pytest.fail("native friendliness/unknown hostility must not imply combat")
    result = runner.random_play(RandomSession(), scenario, lambda _: None)
    assert result["reason"] == "budget" and result["jumps"] == 1
