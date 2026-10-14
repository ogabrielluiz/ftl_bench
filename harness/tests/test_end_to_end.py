"""Offline executable runner -> trajectory -> dashboard -> report contract replay.

Only the game I/O and model I/O boundaries are simulated. No FTL process or paid API
request is launched, and the actual runner, LLM loop and scorer execute together.
"""
from __future__ import annotations

import copy
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import decision_backends as decision  # noqa: E402
import ftl_live as live  # noqa: E402
import llm_agent  # noqa: E402
import run_benchmark as runner  # noqa: E402
from model_backend import Completion  # noqa: E402
from ftl_bench import AgentSession, Observation, Scenario, SubObjective, TrajectoryRecorder  # noqa: E402
from ftl_bench.cli import main as cli  # noqa: E402
from ftl_bench.reporting import load_run_report, render_run_report, summarize_model_usage  # noqa: E402


def state(seed, *, score=0, sector=0, pos=0, hull=30, dead=False, over=False, victory=False, phases=0):
    return {"schema_version": 3, "tick": 1, "render_count": 1, "seed": seed,
            "game_started": True, "paused": True, "difficulty": 0, "game_over": over,
            "victory": victory, "ftl_score": score, "flagship": {"phases_completed": phases},
            "capabilities": {"native_protocol": 5, "manual_fire": True,
                             "global_autofire_control": True, "victory": True, "live_score": True,
                             "crew_control_guard": True, "crew_ownership": True,
                             "event_choice_state": True, "upgrade_rules": True, "fuel_recovery": True,
                             "sector_navigation": True, "beacon_navigation": True, "enemy_hostility": True},
            "economy": {"sector_navigation_version": 1, "beacon_navigation_version": 1,
                        "navigation": {"can_jump": True, "enemy_defeat_pending": False,
                                       "drive_current": 85, "drive_max": 85}},
            "player_ship": {"blueprint": "PLAYER_SHIP_HARD", "hull": {"current": hull, "max": 30},
                            "oxygen_pct": 100, "resources": {"fuel": 20, "scrap": score},
                            "crew": [{"id": 0, "room": 0, "health_current": 100, "health_max": 100, "dead": dead}],
                            "rooms": [{"room_id": 0}], "systems": [], "weapons": []},
            "map": {"sector": sector, "current_pos": {"x": pos, "y": 0},
                    "connected_beacons": [{"index": 1}], "jump_charged": True}}


class SimulatedSession:
    """Session recording and lifecycle behavior with replayed observed game responses."""
    def __init__(self, episodes):
        self.episodes = episodes
        self.recorder = None
        self.pending_model = None
        self.pending_thought = None
        self.pending_decision_obs = None
        self.reset_count = {}
        self.menu()

    def menu(self):
        self.current = Observation.from_dict({"schema_version": 3, "tick": 0, "seed": 0, "game_started": False})

    def _sync_seq(self):
        return self.current

    def observe(self):
        return self.current

    def reset_episode(self, seed, timeout):
        index = self.reset_count.get(seed, 0)
        self.reset_count[seed] = index + 1
        episodes = self.episodes[seed]
        self.remaining = copy.deepcopy(episodes[min(index, len(episodes) - 1)])
        self.current = Observation.from_dict(state(seed))
        if self.recorder:
            self.recorder.record("reset_episode", [{"type": "reset_episode", "seed": seed}], self.current)
        return self.current

    def step(self, actions, advance_frames=150):
        pre_obs = self.current
        if any(action["type"] in {"return_to_menu", "confirm_menu"} for action in actions):
            self.menu()
        else:
            raw = self.remaining.pop(0) if self.remaining else copy.deepcopy(self.current.raw)
            raw["tick"] = self.current.tick + 1
            raw["render_count"] = raw["tick"] * advance_frames
            self.current = Observation.from_dict(raw)
        if self.recorder:
            self.recorder.record("step", actions, self.current,
                                 thought=self.pending_thought, model=self.pending_model,
                                 pre_obs=pre_obs, decision_obs=self.pending_decision_obs)
        self.pending_model = self.pending_thought = None
        self.pending_decision_obs = None
        return self.current

    def abandon_to_menu(self):
        if self.current.game_over:
            return self.current
        return self.step([{"type": "return_to_menu"}], advance_frames=1)


def full_scenario(sid, seed):
    return Scenario(sid, "full_run", seed, [SubObjective("progress", 11, "milestone")], budget_jumps=1)


def win_episode(seed):
    # More turns and confirmed jumps than the bounded budget allows.
    return [state(seed, sector=sector, pos=sector + 1, score=(sector + 1) * 100)
            for sector in range(8)] + [
                state(seed, sector=7, pos=9, score=850, phases=1),
                state(seed, sector=7, pos=10, score=900, phases=2),
                state(seed, sector=7, pos=11, score=950, phases=3, victory=True, over=True)]


def replay_boundaries(monkeypatch, session):
    monkeypatch.setattr(runner, "AgentSession", lambda: session)
    monkeypatch.setattr(runner, "game_alive", lambda: True)
    monkeypatch.setattr(runner, "restart_ftl", session.menu)
    # Prevent installation/process lookups from leaking through an offline replay.
    import ftl_bench.doctor
    monkeypatch.setattr(ftl_bench.doctor, "inspect_installation", lambda **kw: {
        "checks": [{"name": "model_backend", "ok": True, "detail": "offline replay"}]})
    monkeypatch.setattr(live, "process_status", lambda: {"known": True, "alive": False, "label": "offline replay"})
    monkeypatch.setattr(live, "SCENARIOS", {})
    live._snapshot_cache.clear()
    live._score_cache.clear()


@pytest.mark.parametrize("waiting", [False, True])
def test_random_stall_guard_distinguishes_native_waiting_from_ordinary_idle(waiting):
    initial = state(1)
    initial["economy"] = {"native_protocol": 5, "fuel_recovery": {"waiting": waiting}}
    class WaitingSession:
        def __init__(self):
            self.turns = 0
        def observe(self):
            return Observation.from_dict(copy.deepcopy(initial))
        def step(self, actions, advance_frames):
            self.turns += 1
            if self.turns == 8:
                initial.update(game_over=True, victory=True)
            return self.observe()
        def jump(self, beacon_index, advance_frames):
            return self.step([{"type": "jump", "beacon_index": beacon_index}], advance_frames)
    session = WaitingSession()
    result = runner.random_play(session, full_scenario("wait", 1), lambda _: None,
                                play_to_gameover=True, stall_limit=3)
    if waiting:
        assert result["reason"] == "game_over" and session.turns == 8
    else:
        assert result["reason"] == "stalled" and session.turns == 3


def test_actual_full_game_runner_replays_win_loss_refusal_and_backend_error(tmp_path, monkeypatch, capsys):
    scenarios = [full_scenario("win", 1), full_scenario("loss", 2),
                 full_scenario("refused", 3), full_scenario("backend_error", 4)]
    session = SimulatedSession({
        1: [win_episode(1)],
        2: [[state(2, score=120, hull=20, dead=True, over=True)]],
        3: [[state(3, score=10)]],
        4: [[state(4, score=30, hull=26, pos=1)]],
    })
    replay_boundaries(monkeypatch, session)
    calls = {}

    def complete(system, user, model):
        seed = session.current.seed
        calls[seed] = calls.get(seed, 0) + 1
        if seed == 4 and calls[seed] > 1:
            raise RuntimeError("simulated backend unavailable")
        assert "OBSERVATION:\n" in user
        return Completion("THOUGHT: Follow the observed plan.\nACTION:\n  jump 1\n  advance 260", {
            "provider": "offline", "model": "replay-model", "request_id": f"seed-{seed}-call-{calls[seed]}",
            "latency_seconds": 0.25, "usage": {"input_tokens": 100, "output_tokens": 20}})

    monkeypatch.setattr(llm_agent, "anthropic_complete", complete)
    suite = tmp_path / "recorded-suite.json"
    suite.write_text(json.dumps({"scenarios": [scenario.to_dict() for scenario in scenarios]}), encoding="utf-8")
    output = tmp_path / "benchmark"
    monkeypatch.setattr(sys, "argv", ["run_benchmark", "--agent", "llm", "--backend", "anthropic",
        "--model", "replay-model", "--mode", "gameover", "--stall-limit", "2",
        "--suite", str(suite), "--out", str(output)])
    with pytest.raises(SystemExit) as failure:
        runner.main()
    assert failure.value.code == 1  # failure is still recorded and exported, not hidden.
    directory, = output.iterdir()
    summary_path, = directory.glob("summary_*.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    # Changing/removing the live suite cannot reinterpret a recorded benchmark.
    suite.unlink()
    report = load_run_report(directory)
    assert report["aggregate"] == summary["aggregate"]
    assert report["instances"] == summary["instances"]
    assert report["coverage"]["complete"] is True
    assert report["aggregate"]["ftl_score_mean"] == 277.5
    assert report["aggregate"]["solve_rate"] == "1/4"
    assert report["aggregate"]["failed"] == 2
    by_id = {row["scenario"]: row for row in report["instances"]}
    assert by_id["win"]["achieved"]["progress"] == 11
    assert by_id["win"]["achieved"]["victory"] is True
    assert by_id["win"]["jumps_used"] > by_id["win"]["budget_jumps"]
    assert calls[1] == 11 > 1 * 8
    assert by_id["loss"]["solved"] is False
    assert by_id["loss"]["achieved"]["alive"] == 0
    assert by_id["loss"]["achieved"]["final_hull"] == 20
    assert by_id["refused"]["jumps_used"] == 0
    assert by_id["refused"]["reason"] == "stalled"
    assert by_id["refused"]["status"] == "error"
    assert by_id["backend_error"]["status"] == "error"
    assert by_id["backend_error"]["reason"] == "model_error"
    assert by_id["backend_error"]["achieved"]["final_hull"] == 26
    assert report["model_usage"]["input_tokens"] == sum(calls.values()) * 100 - 100
    assert report["model_usage"]["recorded_cost_usd"] is None
    assert "unknown" in report["model_usage"]["scope"]
    win_records = [json.loads(line) for line in (directory / "win.jsonl").read_text().splitlines()]
    assert win_records[0]["meta"]["scenario"]["type"] == "full_run"
    assert win_records[-1]["reason"] == "win"
    assert win_records[1]["obs"]["capabilities"]["native_protocol"] == 5
    assert win_records[1]["obs"]["capabilities"]["victory"] is True
    first_decision = next(row for row in win_records if row.get("model"))
    assert first_decision["decision_obs"] == first_decision["pre_obs"] == win_records[1]["obs"]
    assert first_decision["obs"]["tick"] > first_decision["decision_obs"]["tick"]
    monkeypatch.setattr(live, "BENCH", output)
    dashboard = live.build(f"{directory.name}/backend_error")
    assert dashboard["run"]["status"] == "error"
    assert dashboard["run"]["active_instance"] is None
    assert dashboard["header"]["status"] == "error"
    assert dashboard["header"]["reason"] == "model_error"
    assert dashboard["header"]["hull"] == 26
    assert dashboard["header"]["model_usage"]["input_tokens"] == 100
    assert dashboard["selected_score"]["score"] == 30
    assert dashboard["agg"]["done"] == dashboard["agg"]["scored"] == dashboard["agg"]["total"] == 4
    assert dashboard["agg"]["mean"] == report["aggregate"]["ftl_score_mean"]
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    capsys.readouterr()
    cli(["report", str(directory), "--json"])
    assert json.loads(capsys.readouterr().out) == report
    assert before == {path.name: path.read_bytes() for path in directory.iterdir()}
    export = tmp_path / "export.json"
    cli(["report", str(directory), "--json", "--output", str(export)])
    assert json.loads(export.read_text(encoding="utf-8")) == report
    assert render_run_report(report, as_json=True) == render_run_report(load_run_report(directory), as_json=True)


def test_jev_retry_uses_recorded_digest_and_typed_observation_requests(tmp_path, monkeypatch):
    scenario = full_scenario("retry", 7)
    session = SimulatedSession({7: [[state(7, score=120, hull=20, dead=True, over=True)], win_episode(7)]})
    replay_boundaries(monkeypatch, session)
    systems, requests = [], []
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-placeholder")

    def post(endpoint, body, key, *, provider):
        assert endpoint == "https://api.typesafe.ai/v1/systemone"
        assert body["state"]["observation"]["capabilities"]["native_protocol"] == 5
        systems.append(body["state"]["interface_and_goal"])
        requests.append(body)
        answers = {}
        for name, question in body["questions"].items():
            choices = question["criteria"]
            choice = "jump_1" if name == "navigation" else "260" if name == "advance" else "hold"
            assert choice in choices
            answers[name] = {"type": "choice", "choice": choice, "confidence": 0.95,
                             "probabilities": {option: float(option == choice) for option in choices}}
        return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 50, "output_tokens": 10}}, {
            "provider": provider, "model": "jev-1.13.0", "request_id": f"typed-{len(requests)}", "latency_seconds": 0.1}

    import model_backend
    monkeypatch.setattr(model_backend, "post_json", post)
    agent = llm_agent.make_llm_agent("jev-1.13.0", "jev", play_to_gameover=True, stall_limit=2)
    result = runner.run_instance(session, scenario, agent, "jev-replay", tmp_path, lambda _: None,
        {"run_id": "retry-run", **agent.metadata}, retries=1)
    assert result["solved"] is True
    assert result["attempt_ftl_scores"] == [120, 950]
    assert len(requests) == 12  # 1 losing turn + 11 winning turns; no reflection request.
    assert "Attempt 1:" not in systems[0]
    assert "Attempt 1: LOST: crew lost" in systems[1]
    assert "ftl_score=120" in systems[1]
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "retry-run", "status": "completed",
        "scenario_ids": [scenario.id], "retries": 1, "agent": "jev-replay"}), encoding="utf-8")
    report = load_run_report(tmp_path)
    assert report["instances"] == [result]
    assert report["aggregate"]["solve_at"] == {"@1": "0/1", "@2": "1/1"}
    assert report["model_usage"]["input_tokens"] == 600
    assert report["model_usage"]["requests"][0]["action_selection"] == "enumerated"


def test_native_win_during_ack_timeout_retains_terminal_state_and_request_usage(tmp_path, monkeypatch):
    class LateTerminalSession(SimulatedSession):
        def __init__(self):
            super().__init__({9: [[]]})
            self.action_seq = 0
            self.step_timeout = 0.1

        def _write_action_atomic(self, payload):
            # The native state changed, but the acknowledgement has not become paused.
            self.current = Observation.from_dict(state(9, score=950, sector=7,
                victory=True, phases=3, over=True))

        def _wait_for(self, predicate, timeout=None):
            raise TimeoutError("terminal transition did not pause in time")

        def step(self, actions, advance_frames=150):
            # Exercise the actual session timeout recorder while simulating only its I/O.
            return AgentSession.step(self, actions, advance_frames)

    session = LateTerminalSession()
    replay_boundaries(monkeypatch, session)
    monkeypatch.setattr(llm_agent, "ftl_process_alive", lambda: True)
    monkeypatch.setattr(llm_agent, "anthropic_complete", lambda *args: Completion("ACTION: jump 1", {
        "provider": "offline", "model": "replay-model", "request_id": "late-win-request",
        "usage": {"input_tokens": 100, "output_tokens": 20}, "latency_seconds": 0.25}))
    agent = llm_agent.make_llm_agent("replay-model", "anthropic", play_to_gameover=True, stall_limit=2)
    scenario = full_scenario("late_win", 9)
    result = runner._play_once(session, scenario, agent, "late-replay", tmp_path / "late_win.jsonl",
                               lambda _: None, {"run_id": tmp_path.name}, ())
    assert result["status"] == "completed" and result["reason"] == "win"
    assert result["ftl_score"] == 950 and result["solved"] is True
    records = [json.loads(line) for line in (tmp_path / "late_win.jsonl").read_text().splitlines()]
    timed_out = next(record for record in records if record["kind"] == "step_timeout")
    assert timed_out["obs"]["victory"] is True
    assert timed_out["model"]["request_id"] == "late-win-request"
    assert timed_out["actions"] == [{"type": "jump", "beacon_index": 1}]
    assert any(record["kind"] == "terminal_observation" and record["obs"]["victory"] for record in records)
    (tmp_path / "run.json").write_text(json.dumps({"run_id": tmp_path.name, "agent": "late-replay",
        "status": "completed", "scenario_ids": ["late_win"]}), encoding="utf-8")
    report = load_run_report(tmp_path)
    assert report["instances"] == [result]
    assert report["aggregate"]["solve_rate"] == "1/1"
    assert report["model_usage"]["recorded_completions"] == 1
    assert report["model_usage"]["input_tokens"] == 100
    assert report["model_usage"]["requests"][0]["request_id"] == "late-win-request"
    monkeypatch.setattr(live, "BENCH", tmp_path.parent)
    dashboard = live.build(f"{tmp_path.name}/late_win")
    assert dashboard["header"]["status"] == "completed"
    assert dashboard["header"]["steps"] == 1
    assert len(dashboard["feed"]) == 1
    assert dashboard["feed"][0]["ack_timeout"] is True
    assert dashboard["feed"][0]["actions"][0]["kind"] == "jump"
    assert dashboard["feed"][0]["model"]["request_id"] == "late-win-request"
    assert dashboard["header"]["ftl_score"] == 950
    assert dashboard["header"]["model_usage"]["input_tokens"] == 100
    assert dashboard["selected_score"]["score"] == 950
    assert dashboard["selected_score"]["solved"] is True


def test_invalid_jev_completion_is_finalized_with_usage_and_diagnostic_before_cleanup(tmp_path, monkeypatch):
    class DoorSession(SimulatedSession):
        def reset_episode(self, seed, timeout):
            observation = super().reset_episode(seed, timeout)
            observation.player_ship["doors"] = [{"index": 0, "room_a": 0, "room_b": -1,
                                                "open": False, "airlock": True}]
            return observation

    session = DoorSession({12: [[]]})
    replay_boundaries(monkeypatch, session)
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-placeholder")
    import model_backend

    def post(endpoint, body, key, *, provider):
        answers = {}
        for name, question in body["questions"].items():
            choice = "hold" if "hold" in question["criteria"] else "150"
            answers[name] = {"type": "choice", "choice": choice, "confidence": 1,
                             "probabilities": {option: float(option == choice) for option in question["criteria"]}}
        answers["doors"]["confidence"] = 1.5
        return {"model": "jev-1.13.0", "answers": answers,
                "usage": {"input_tokens": 800, "output_tokens": 30}}, {
                    "provider": provider, "model": "jev-1.13.0", "request_id": "invalid-provider-completion",
                    "latency_seconds": 0.8}

    monkeypatch.setattr(model_backend, "post_json", post)
    agent = llm_agent.make_llm_agent("jev-1.13.0", "jev", play_to_gameover=True)
    result = runner._play_once(session, full_scenario("invalid_jev", 12), agent, "jev-replay",
                               tmp_path / "invalid_jev.jsonl", lambda _: None, {"run_id": tmp_path.name}, ())
    assert result["status"] == "error" and result["reason"] == "model_error"
    assert "confidence is 1.5" in result["error"]
    records = [json.loads(line) for line in (tmp_path / "invalid_jev.jsonl").read_text().splitlines()]
    traces = [record for record in records if record["kind"] == "model_error"]
    assert len(traces) == 1
    trace = traces[0]
    assert trace["obs"]["game_started"] is True
    assert trace["model"]["contract_error"]["invariant"] == "confidence_range"
    assert trace["model"]["contract_error"]["question"] == "doors"
    assert trace["model"]["request_id"] == "invalid-provider-completion"
    assert all(record["actions"] == [{"type": "return_to_menu"}]
               for record in records if record["kind"] == "step")
    (tmp_path / "run.json").write_text(json.dumps({"run_id": tmp_path.name, "status": "error",
        "scenario_ids": ["invalid_jev"], "agent": "jev-replay"}), encoding="utf-8")
    report = load_run_report(tmp_path)
    assert report["instances"] == [result]
    assert report["aggregate"]["failed"] == 1
    assert report["model_usage"]["recorded_completions"] == 1
    assert report["model_usage"]["input_tokens"] == 800
    assert report["model_usage"]["output_tokens"] == 30
    monkeypatch.setattr(live, "BENCH", tmp_path.parent)
    dashboard = live.build(f"{tmp_path.name}/invalid_jev")
    assert dashboard["header"]["status"] == "error"
    assert "confidence is 1.5" in dashboard["header"]["error"]
    assert dashboard["header"]["model_usage"]["recorded_completions"] == 1
    assert dashboard["header"]["model_usage"]["input_tokens"] == 800


def write_attempt(directory, sid, *, finalize=True, definition=True, error=False):
    scenario = full_scenario(sid, 8)
    meta = {"scenario_id": sid, "run_id": directory.name}
    if definition:
        meta["scenario"] = scenario.to_dict()
    recorder = TrajectoryRecorder(directory / f"{sid}.jsonl", meta=meta)
    recorder.record("step", [], Observation.from_dict(state(8, score=25)))
    if finalize:
        recorder.finish(status="error" if error else "completed", reason="model_error" if error else "game_over",
                        error="offline provider failed" if error else None)
    return recorder.path


@pytest.mark.parametrize("restriction", ["manifest", "sidecar", "conflicting_flags", "corrupt_sidecar"])
def test_diagnostic_concession_retains_score_outcome_and_finalized_coverage(tmp_path, monkeypatch, restriction):
    scenario = full_scenario("diagnostic", 1)
    manifest = {"run_id": "diagnostic-trial", "agent": "llm", "status": "completed",
                "scenario_ids": [scenario.id]}
    if restriction == "manifest":
        manifest.update(validation_status="diagnostic_only", validation_limitations=["Native recovery interface was incomplete."])
    elif restriction in {"sidecar", "conflicting_flags"}:
        if restriction == "conflicting_flags":
            manifest["valid_for_model_comparison"] = True
        (tmp_path / "validation.json").write_text(json.dumps({"valid_for_model_comparison": False,
            "limitations": ["Native recovery interface was incomplete."]}), encoding="utf-8")
    else:
        (tmp_path / "validation.json").write_text("{unfinished", encoding="utf-8")
    (tmp_path / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    final = state(1, score=329, sector=1, hull=19)
    final["player_ship"]["resources"]["fuel"] = 0
    final["player_ship"]["crew"] *= 3
    final["ftl_score_source"] = "native_live_v1"
    recorder = TrajectoryRecorder(tmp_path / "diagnostic.jsonl", meta={
        "run_id": manifest["run_id"], "scenario_id": scenario.id, "scenario": scenario.to_dict()})
    recorder.record("step", [{"type": "give_up"}], Observation.from_dict(final))
    recorder.finish(status="completed", reason="gave_up")
    report = load_run_report(tmp_path)
    assert report["coverage"]["complete"] is True  # All recorded files finalized, not a certification.
    assert report["coverage"]["scored_instances"] == 1
    assert report["validation"]["comparison_eligible"] is False
    assert report["validation"]["valid_for_model_comparison"] is False
    assert report["aggregate"]["instances"] == 0
    assert report["aggregate"]["ftl_score_mean"] is None
    assert report["recorded_aggregate"]["ftl_score_mean"] == 329
    assert report["recorded_aggregate"]["solve_rate"] == "0/1"
    assert report["comparison"]["excluded_instances"] == 1
    result, = report["instances"]
    assert result["status"] == "completed" and result["reason"] == "gave_up"
    assert result["solved"] is False and result["ftl_score"] == 329
    assert result["achieved"]["victory"] is False and result["achieved"]["alive"] == 1
    assert result["achieved"]["crew_alive"] == 3 and result["achieved"]["gave_up"] == 1
    text = render_run_report(report)
    assert "DIAGNOSTIC ONLY" in text
    assert "Complete finalized-file coverage" in text
    assert "completed / gave_up" in text
    assert "game_over" not in text
    assert report["validation"]["limitations"][0] in text
    monkeypatch.setattr(live, "BENCH", tmp_path)
    monkeypatch.setattr(live, "SCENARIOS", {})
    monkeypatch.setattr(live, "process_status", lambda: {"known": True, "alive": False, "label": "offline"})
    live._snapshot_cache.clear()
    live._score_cache.clear()
    dashboard = live.build("live")
    assert dashboard["run"]["validation"] == report["validation"]
    assert dashboard["header"]["reason"] == "gave_up" and dashboard["header"]["live"] is False
    assert dashboard["selected_score"]["score"] == 329 and dashboard["selected_score"]["solved"] is False
    assert dashboard["header"]["hull"] == 19 and dashboard["header"]["crew"] == 3
    assert dashboard["agg"]["done"] == dashboard["agg"]["total"] == 1
    assert dashboard["agg"]["comparison_instances"] == 0 and dashboard["agg"]["comparison_excluded"] == 1
    assert dashboard["agg"]["mean"] is report["aggregate"]["ftl_score_mean"] is None
    assert dashboard["agg"]["recorded_mean"] == report["recorded_aggregate"]["ftl_score_mean"]
    assert dashboard["agg"]["recorded_scored"] == report["coverage"]["scored_instances"]
    assert dashboard["instances"][0]["comparison_eligible"] is False


def test_report_exposes_failed_live_missing_corrupt_and_legacy_denominators(tmp_path):
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "partial", "status": "running",
        "scenario_ids": ["failed", "live", "missing", "corrupt", "legacy"]}), encoding="utf-8")
    write_attempt(tmp_path, "failed", error=True)
    write_attempt(tmp_path, "live", finalize=False)
    bad = write_attempt(tmp_path, "corrupt")
    with bad.open("a", encoding="utf-8") as stream:
        stream.write("{partial")
    write_attempt(tmp_path, "legacy", definition=False)
    report = load_run_report(tmp_path)
    assert report["coverage"]["planned_instances"] == 5
    assert report["coverage"]["scored_instances"] == 1
    assert report["coverage"]["missing_scenarios"] == ["missing"]
    assert report["coverage"]["unscored_scenarios"] == ["live", "missing", "corrupt", "legacy"]
    assert report["coverage"]["nonfinal_attempts"] == ["live.jsonl"]
    assert report["aggregate"]["failed"] == 1
    assert report["aggregate"]["solve_rate"] == "0/1"
    assert report["coverage"]["complete"] is False
    assert any("corrupt.jsonl:4" in error for error in report["errors"])
    assert any("no embedded scenario" in error for error in report["errors"])
    assert "1/5 planned" in render_run_report(report)
    assert "scorable subset" in render_run_report(report)
    fallback = tmp_path / "legacy-suite.json"
    fallback.write_text(json.dumps([full_scenario("legacy", 8).to_dict()]), encoding="utf-8")
    legacy = load_run_report(tmp_path, legacy_suite=fallback)
    assert legacy["coverage"]["scored_instances"] == 2
    assert any("original scenario configuration was not recorded" in warning for warning in legacy["warnings"])


def test_report_handles_missing_manifest_and_rejects_parent_directory(tmp_path):
    nested = tmp_path / "run"
    nested.mkdir()
    (nested / "run.json").write_text(json.dumps({"status": "completed", "scenario_ids": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="select one invocation"):
        load_run_report(tmp_path)
    (nested / "run.json").unlink()
    write_attempt(nested, "old")
    report = load_run_report(nested)
    assert report["coverage"]["planned_instances"] is None
    assert report["coverage"]["complete"] is False
    assert report["aggregate"]["instances"] == 1
    assert report["warnings"]


def test_report_does_not_replace_invalid_recorded_scenario_with_legacy_suite(tmp_path):
    path = write_attempt(tmp_path, "bad")
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[0]["meta"]["scenario"]["seed"] = -1
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    suite = tmp_path / "fallback.json"
    suite.write_text(json.dumps([full_scenario("bad", 8).to_dict()]), encoding="utf-8")
    report = load_run_report(tmp_path, legacy_suite=suite)
    assert report["instances"] == []
    assert any("unsigned 32-bit" in error for error in report["errors"])


def test_usage_preserves_partial_coverage_and_does_not_price_unknown_tokens():
    usage = summarize_model_usage([
        {"model": {"model": "m", "usage": {"input_tokens": 10, "output_tokens": 2}, "latency_seconds": 0.5}},
        {"model": {"model": "m", "usage": None}},
        {"kind": "end", "status": "error", "reason": "model_error"}])
    assert usage["recorded_completions"] == 2
    assert usage["input_tokens"] == 10
    assert usage["completions_with_input_usage"] == 1
    assert usage["recorded_cost_usd"] is None
    assert usage["models"] == ["m"]


def test_actual_dashboard_http_is_read_only_and_serves_completed_result(tmp_path, monkeypatch):
    if live.FastAPI is None:
        pytest.skip("optional dashboard dependencies are not installed")
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "run.json").write_text(json.dumps({"run_id": "run", "status": "error", "scenario_ids": ["failed"]}), encoding="utf-8")
    write_attempt(directory, "failed", error=True)
    monkeypatch.setattr(live, "BENCH", tmp_path)
    monkeypatch.setattr(live, "SCENARIOS", {})
    monkeypatch.setattr(live, "process_status", lambda: {"known": True, "alive": False, "label": "offline"})
    live._snapshot_cache.clear()
    live._score_cache.clear()
    app = live.create_app()

    def request(path, method="GET", query=b""):
        async def invoke():
            messages = []
            request_received = False
            disconnected = asyncio.Event()

            async def receive():
                nonlocal request_received
                if not request_received:
                    request_received = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                # An ASGI connection waits after its one complete request;
                # repeated immediate requests would starve FileResponse's task.
                await disconnected.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                messages.append(message)
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    disconnected.set()

            await app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                       "http_version": "1.1", "method": method, "scheme": "http", "path": path,
                       "raw_path": path.encode(), "query_string": query, "root_path": "",
                       "headers": [(b"host", b"127.0.0.1")], "client": ("127.0.0.1", 1),
                       "server": ("127.0.0.1", 8765)}, receive, send)
            start = next(message for message in messages if message["type"] == "http.response.start")
            body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
            return start, body

        return asyncio.run(invoke())

    start, body = request("/api/state", query=b"sel=run%2Ffailed")
    assert start["status"] == 200
    result = json.loads(body)
    assert result["header"]["status"] == "error"
    assert result["header"]["reason"] == "model_error"
    assert result["selected_score"]["score"] == 25
    assert request("/api/state", "POST")[0]["status"] == 405
    assert request("/api/unknown")[0]["status"] == 404
    # No cross-origin API access is configured and the server stays on loopback.
    assert b"access-control-allow-origin" not in dict(start["headers"])
    index, body = request("/")
    assert index["status"] == 200
    assert b"ftl" in body.lower()
    if (live.DASHBOARD_DIST / "index.html").exists():
        assert b"assets/" in body
    monkeypatch.setattr(live, "HOST", "0.0.0.0")
    with pytest.raises(SystemExit) as blocked:
        live.main()
    assert blocked.value.code == 2
