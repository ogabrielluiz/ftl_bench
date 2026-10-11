"""Runner integration uses fake model/game transports and real local save copies."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_visual as runner
import ftl_live as live
from ftl_bench.observation import Observation
import ftl_bench.protected_game as protected
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory
from ftl_bench.visual_session import ExternalInputInterference, VisualFrame, VisualTransportError
from visual_agent import CodexVisualAgent, VisualDecision, VisualProtocolError, VisualBackendError


def frame(directory, index=0, **updates):
    image = directory / f"frame-{index}.png"
    image.write_bytes(b"fake image; no backend invoked")
    raw = {"schema_version": 3, "tick": index, "seed": 1, "game_started": True,
           "paused": True, "difficulty": 0, "ftl_score": 418, "victory": False,
           "capabilities": {"native_protocol": 5, "live_score": True, "victory": True, "external_input_guard": True,
                            "visual_clock_version": 2, "world_updates": str(index * 7),
                            "fixed_step_numerator": 1, "fixed_step_denominator": 60, "simulated_updates": str(index * 7)},
           "player_ship": {"blueprint": "PLAYER_SHIP_HARD", "resources": {"fuel": 11, "scrap": 999},
                           "hull": {"current": 30, "max": 30}},
           "enemy_ship": {"hidden_fact": "enemy-secret"}, "map": {"sector": 0, "current_pos": {"x": index, "y": 0}},
           "hidden_rng": "native-secret", "visual": {"visual_clock_version": 2, "world_updates": str(index * 7),
                                                        "fixed_step_numerator": 1, "fixed_step_denominator": 60,
                                                        "simulated_updates": str(index * 7),
                                                        "actual_frames": 7, "input_feedback": [
               {"index": 0, "type": "click", "status": "delivered"}]}, **updates}
    return VisualFrame(Observation.from_dict(raw), image,
                       {"path": image.name, "frame_id": f"frame-{index}", "width": 1280, "height": 720,
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}, index)


class Agent:
    def instruction_identity(self):
        return CodexVisualAgent().instruction_identity()

    def __init__(self, error=None):
        self.seen = []
        self.error = error

    def decide(self, observation):
        self.seen.append(observation)
        if self.error:
            raise self.error
        return VisualDecision([{"type": "click", "x": 100, "y": 200, "button": "left", "modifiers": []}],
                              60, "Open the map", "Remember my route", {"latency_seconds": 1.25, "model": "fake"})


def test_image_mode_never_calls_pixel_extractor_and_initial_image_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "extract_visible_hud", lambda path: pytest.fail("image mode must not extract HUD"))
    initial = frame(tmp_path)
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    runner.run_loop(Transport([initial, frame(tmp_path, 1)]), Agent(), recorder, max_decisions=1)
    reset = next(r for r in load_trajectory(recorder.path) if r["kind"] == "reset")
    assert reset["kind"] == "reset"
    assert reset["visual"]["before"] == reset["visual"]["after"] == initial.reference


def test_hybrid_extracts_once_and_records_exact_supplied_values_and_provenance(tmp_path, monkeypatch):
    frames = [frame(tmp_path), frame(tmp_path, 1)]
    provenance = {"image_sha256": frames[0].reference["sha256"], "method": "test-pixels"}
    calls = []
    def extract(path):
        calls.append(path)
        return {"values": {"fuel": 12}, "provenance": provenance}
    monkeypatch.setattr(runner, "extract_visible_hud", extract)
    agent = Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    runner.run_loop(Transport(frames), agent, recorder, mode="hybrid", max_decisions=1)
    step = next(r for r in load_trajectory(recorder.path) if r["kind"] == "step")
    assert calls == [frames[0].image_path]
    assert step["visual"]["visible_summary"] == agent.seen[0].visible_hud == {"fuel": 12, "paused": True}
    assert step["visual"]["visible_summary_provenance"] == provenance


def test_hybrid_hash_mismatch_ends_before_actor_or_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "extract_visible_hud", lambda path: {"values": {}, "provenance": {"image_sha256": "wrong"}})
    agent, transport = Agent(), Transport([frame(tmp_path)])
    with pytest.raises(RuntimeError, match="differs"):
        runner.run_loop(transport, agent, TrajectoryRecorder(tmp_path / "trajectory.jsonl"), mode="hybrid")
    assert not agent.seen and not transport.calls


def test_backend_failure_is_not_model_protocol_failure(tmp_path):
    with pytest.raises(VisualBackendError):
        runner.run_loop(Transport([frame(tmp_path)]), Agent(VisualBackendError("timeout")),
                        TrajectoryRecorder(tmp_path / "trajectory.jsonl"))
    report = json.loads((tmp_path / "visual-report.json").read_text())
    assert report["reason"] == "visual_backend_error"
    assert report["outcome_category"] == "infrastructure_failure"


def test_replay_records_exact_declared_fixed_step_seconds_without_rounding(tmp_path):
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    runner.run_loop(Transport([frame(tmp_path), frame(tmp_path, 1)]), Agent(), recorder, max_decisions=1)
    step = next(r for r in load_trajectory(recorder.path) if r["kind"] == "step")
    assert step["visual"]["advance"] == {"requested_frames": 60, "actual_frames": 7,
        "visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60,
        "simulated_seconds": 7 / 60}
    assert runner.advance_evidence({"visual_clock_version": 1}, 60, 7) == {"requested_frames": 60, "actual_frames": 7}


def test_experiment_snapshot_cannot_be_mutated_by_stop_callback(tmp_path):
    experiment = {"task": "fixed", "budgets": {"decisions": 1}}
    def stop(initial, current):
        experiment["task"] = "mutated"
        return current.capture_id == 1
    report = runner.run_loop(Transport([frame(tmp_path), frame(tmp_path, 1)]), Agent(),
                             TrajectoryRecorder(tmp_path / "trajectory.jsonl"), max_decisions=1,
                             experiment=experiment, stop_when=stop)
    assert report["experiment"]["task"] == "fixed" and experiment["task"] == "mutated"
    assert report["experiment_sha256"] == runner.canonical_sha256(report["experiment"])


class DecisionAgent(Agent):
    def __init__(self, requests):
        super().__init__()
        self.requests = iter(requests)

    def decide(self, observation):
        self.seen.append(observation)
        actions, advance = next(self.requests)
        return VisualDecision(actions, advance, "The task is complete", "Remember my route",
                              {"latency_seconds": 0.1, "model": "fake"})


class Transport:
    def __init__(self, frames, *, error=None, capture_error=None):
        self.frames = frames
        self.calls = []
        self.error = error
        self.capture_error = capture_error

    def capture(self):
        if self.capture_error:
            raise self.capture_error
        return self.frames[0]

    def step(self, before, actions, advance):
        self.calls.append((before, actions, advance))
        if self.error:
            raise self.error
        return self.frames[len(self.calls)]


@pytest.mark.parametrize("mode", ["image", "hybrid"])
def test_actor_boundary_and_replay_text_match_without_native_state(tmp_path, mode):
    transport = Transport([frame(tmp_path, i) for i in range(3)])
    agent = Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    report = runner.run_loop(transport, agent, recorder, mode=mode, max_decisions=2, expected_seed=1)
    assert report["reason"] == "decision_budget" and report["decisions"] == 2
    assert report["valid_for_model_comparison"] is False
    assert len(agent.seen) == 2
    for observed in agent.seen:
        assert set(vars(observed)) == {"image_path", "frame_id", "mode", "visible_hud", "history", "memory"}
        serialized = json.dumps(asdict(observed), default=str)
        assert "native-secret" not in serialized and "enemy-secret" not in serialized
        assert "999" not in serialized and "418" not in serialized
        assert observed.visible_hud == ({"paused": True} if mode == "hybrid" else {})
    assert agent.seen[1].memory == "Remember my route"
    assert len(agent.seen[1].history) == 1
    assert agent.seen[1].history[0]["actual_advance_frames"] == 7
    steps = [row for row in load_trajectory(recorder.path) if row["kind"] == "step"]
    assert len(steps) == 2
    for step, observation in zip(steps, agent.seen):
        if mode == "hybrid":
            assert step["visual"]["visible_summary"] == observation.visible_hud
        else:
            assert "visible_summary" not in step["visual"]
        assert step["obs"]["hidden_rng"] == "native-secret"  # retained for evaluator only


def test_ack_failure_records_unknown_delivery_once_and_remains_replayable(tmp_path, monkeypatch):
    transport = Transport([frame(tmp_path)], error=VisualTransportError("ack missing"))
    agent = Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    with pytest.raises(VisualTransportError, match="ack missing"):
        runner.run_loop(transport, agent, recorder, max_decisions=2)
    rows = load_trajectory(recorder.path)
    attempted = rows[-2]
    assert attempted["kind"] == "step_unacknowledged"
    assert attempted["visual"]["inputs"][0]["delivery"] == "unknown"
    assert attempted["visual"]["after"] is None
    assert attempted["visual"]["advance"] == {"requested_frames": 60, "actual_frames": None}
    assert rows[-1]["status"] == "error" and rows[-1]["reason"] == "visual_infrastructure_error"
    assert len(agent.seen) == len(transport.calls) == 1
    assert json.loads((tmp_path / "visual-report.json").read_text())["status"] == "error"
    monkeypatch.setattr(live, "BENCH", tmp_path)
    replay = live.replay_snapshot("trajectory")
    assert replay["total"] == 1 and replay["item"]["ack_timeout"] is True
    assert replay["item"]["visual"]["inputs"][0]["delivery"] == "unknown"


def test_initial_capture_failure_is_finalized_and_reported(tmp_path):
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    agent = Agent()
    with pytest.raises(VisualTransportError):
        runner.run_loop(Transport([], capture_error=VisualTransportError("no capture")), agent, recorder)
    assert load_trajectory(recorder.path)[-1]["status"] == "error"
    report = json.loads((tmp_path / "visual-report.json").read_text())
    assert report["reason"] == "visual_infrastructure_error"
    assert report["metrics_status"] == "unavailable_no_observations" and report["recorded_game_observations"] == 0
    assert report["metrics"] and all(value is None for value in report["metrics"].values())
    assert all(reason == "no_recorded_game_observations" for reason in report["metric_unavailable_reasons"].values())
    assert not agent.seen


def test_model_error_preserves_seen_frame_without_dispatch(tmp_path, monkeypatch):
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    transport = Transport([frame(tmp_path)])
    with pytest.raises(VisualProtocolError):
        runner.run_loop(transport, Agent(VisualProtocolError("invalid model JSON", metadata={"model": "fake"})), recorder)
    rows = load_trajectory(recorder.path)
    assert rows[-2]["kind"] == "model_error" and rows[-2]["visual"]["inputs"] == []
    assert rows[-1]["reason"] == "visual_model_error" and not transport.calls
    report = json.loads((tmp_path / "visual-report.json").read_text())
    assert report["metrics_status"] == "partially_available" and report["recorded_game_observations"] == 2
    assert report["metrics"]["final_hull"] == 30 and report["metrics"]["ftl_score"] == 418
    monkeypatch.setattr(live, "BENCH", tmp_path)
    assert live.replay_snapshot("trajectory")["item"]["record_kind"] == "model_error"


def test_visual_event_dismissal_does_not_report_zero_or_infer_event_count_from_primitive(tmp_path):
    frames = [frame(tmp_path, choice_box_open=True), frame(tmp_path, 1, choice_box_open=False)]
    frames[1].observation.raw["visual"]["input_feedback"] = [{"index": 0, "type": "key", "status": "delivered"}]
    agent = DecisionAgent([([{"type": "key", "key": "1", "modifiers": []}], 0)])
    report = runner.run_loop(Transport(frames), agent, TrajectoryRecorder(tmp_path / "trajectory.jsonl"), max_decisions=1)
    assert report["metrics"]["events"] is None
    assert report["metric_unavailable_reasons"]["events"] == "native_event_count_unavailable_for_visual_actions"
    assert report["metrics"]["flagship_phases_completed"] is None
    assert report["metric_unavailable_reasons"]["flagship_phases_completed"] == "native_flagship_phase_count_unavailable"
    assert report["metrics"]["ftl_score"] == 418 and report["metrics"]["final_hull"] == 30
    assert report["metrics"]["victory"] is False


@pytest.mark.parametrize("phase", [0, 1, 2, 3])
def test_explicit_native_phase_telemetry_preserves_observed_zero_and_progress(tmp_path, phase):
    records = [{"kind": "reset", "obs": frame(tmp_path, flagship={"phases_completed": phase}).observation.raw}]
    metrics, unavailable = runner.visual_report_metrics(records)
    assert metrics["flagship_phases_completed"] == phase
    assert "flagship_phases_completed" not in unavailable
    assert metrics["events"] is None


@pytest.mark.parametrize("phase", [None, True, False, -1, 4, "0", 0.0])
def test_invalid_phase_telemetry_is_unavailable_not_an_observed_zero(tmp_path, phase):
    records = [{"kind": "reset", "obs": frame(tmp_path, flagship={"phases_completed": phase}).observation.raw}]
    metrics, unavailable = runner.visual_report_metrics(records)
    assert metrics["flagship_phases_completed"] is None
    assert unavailable["flagship_phases_completed"] == "native_flagship_phase_count_unavailable"


def test_native_victory_authoritatively_establishes_three_completed_phases(tmp_path):
    records = [{"kind": "reset", "obs": frame(tmp_path, victory=True).observation.raw}]
    metrics, unavailable = runner.visual_report_metrics(records)
    assert metrics["flagship_phases_completed"] == 3 and metrics["victory"] is True
    assert "flagship_phases_completed" not in unavailable


def test_phase_evidence_from_an_earlier_episode_does_not_fill_new_episode_missing_signal(tmp_path):
    records = [{"kind": "reset", "obs": frame(tmp_path, flagship={"phases_completed": 2}).observation.raw},
               {"kind": "reset", "obs": frame(tmp_path, 1).observation.raw}]
    metrics, unavailable = runner.visual_report_metrics(records)
    assert metrics["flagship_phases_completed"] is None
    assert "flagship_phases_completed" in unavailable


def test_visual_metric_availability_does_not_change_structured_event_scorer(tmp_path):
    records = [{"kind": "step", "actions": [{"type": "choose_event", "choice_index": 0}],
                "obs": frame(tmp_path).observation.raw}]
    assert runner.achieved_metrics(records)["events"] == 1
    assert runner.visual_report_metrics(records)[0]["events"] is None


@pytest.mark.parametrize("terminal", ["fixture", "victory", "game_over"])
def test_goal_reached_on_final_allowed_decision_wins_over_budget_reason(tmp_path, terminal):
    updates = {"victory": terminal == "victory", "game_over": terminal == "game_over"}
    frames = [frame(tmp_path), frame(tmp_path, 1, **updates)]
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    report = runner.run_loop(Transport(frames), Agent(), recorder, max_decisions=1,
                             stop_when=(lambda initial, current: current.capture_id == 1) if terminal == "fixture" else None)
    assert report["reason"] == {"fixture": "fixture_goal_observed", "victory": "native_victory", "game_over": "native_game_over"}[terminal]
    assert report["decisions"] == 1
    assert load_trajectory(recorder.path)[-2]["visual"]["after"]["frame_id"] == "frame-1"


@pytest.mark.parametrize("max_decisions", [8, 100])
def test_eight_idle_decisions_stop_without_coaching_or_hidden_state_and_preserve_replay(tmp_path, max_decisions):
    # Location/score changes in this fake evaluator state do not affect a guard
    # defined exclusively by the requested decisions.
    frames = [frame(tmp_path, i, ftl_score=418 + i) for i in range(9)]
    for current in frames:
        current.observation.raw["visual"].update(actual_frames=0, input_feedback=[])
    transport = Transport(frames)
    agent = DecisionAgent([([], 0)] * 8)
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    report = runner.run_loop(transport, agent, recorder, max_decisions=max_decisions)
    assert report["status"] == "completed" and report["reason"] == "idle_decision_budget"
    assert report["classification"] == "diagnostic_only" and report["valid_for_model_comparison"] is False
    assert report["decisions"] == report["consecutive_idle_decisions"] == report["budgets"]["idle_decisions"] == 8
    assert len(agent.seen) == len(transport.calls) == 8
    assert all(actions == [] and advance == 0 for _, actions, advance in transport.calls)
    rows = load_trajectory(recorder.path)
    steps = [row for row in rows if row["kind"] == "step"]
    assert len(steps) == 8
    assert all(row["actions"] == [] and row["visual"]["advance"] == {"requested_frames": 0, "actual_frames": 0,
                   "visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60, "simulated_seconds": 0.0}
               and row["visual"]["after"] is not None for row in steps)
    assert rows[-1]["reason"] == "idle_decision_budget" and rows[-1]["consecutive_idle_decisions"] == 8
    assert all(observation.visible_hud == {} for observation in agent.seen)


@pytest.mark.parametrize("active_decision", [([{"type": "move", "x": 2, "y": 3}], 0), ([], 30)])
def test_requested_input_or_positive_budget_resets_idle_streak_even_without_native_progress(tmp_path, active_decision):
    requests = [([], 0), active_decision, ([], 0), ([], 0)]
    frames = [frame(tmp_path, i) for i in range(len(requests) + 1)]
    for current in frames:
        current.observation.raw["visual"].update(actual_frames=0, input_feedback=[])
    if active_decision[0]:
        frames[2].observation.raw["visual"]["input_feedback"] = [{"index": 0, "type": "move", "status": "rejected"}]
    transport = Transport(frames)
    agent = DecisionAgent(requests)
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    report = runner.run_loop(transport, agent, recorder, max_idle_decisions=2)
    assert report["reason"] == "idle_decision_budget" and report["decisions"] == 4
    assert report["consecutive_idle_decisions"] == 2
    assert len(agent.seen) == len(transport.calls) == 4


@pytest.mark.parametrize("terminal", ["fixture", "victory", "game_over"])
def test_real_terminal_evidence_wins_over_idle_limit_on_last_decision(tmp_path, terminal):
    frames = [frame(tmp_path), frame(tmp_path, 1, victory=terminal == "victory", game_over=terminal == "game_over")]
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    report = runner.run_loop(Transport(frames), DecisionAgent([([], 0)]), recorder, max_idle_decisions=1,
                             stop_when=(lambda initial, current: current.capture_id == 1) if terminal == "fixture" else None)
    assert report["reason"] == {"fixture": "fixture_goal_observed", "victory": "native_victory", "game_over": "native_game_over"}[terminal]
    assert report["consecutive_idle_decisions"] == 1


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_idle_limit_fails_before_capture_or_model(tmp_path, limit):
    agent = DecisionAgent([])
    transport = Transport([])
    with pytest.raises(ValueError, match="positive integer"):
        runner.run_loop(transport, agent, TrajectoryRecorder(tmp_path / "trajectory.jsonl"), max_idle_decisions=limit)
    assert not agent.seen and not transport.calls


@pytest.mark.parametrize("updates", [
    {"seed": 2}, {"seed": True}, {"difficulty": 1}, {"difficulty": False}, {"game_started": False},
    {"player_ship": {"blueprint": "OTHER_SHIP"}}, {"victory": None}, {"ftl_score": None},
    {"capabilities": {"native_protocol": 5, "live_score": True, "victory": False}},
    {"capabilities": {"native_protocol": 5, "live_score": True, "victory": True}},
])
def test_unverified_setup_stops_before_model_call(tmp_path, updates):
    agent = Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    with pytest.raises(RuntimeError):
        runner.run_loop(Transport([frame(tmp_path, **updates)]), agent, recorder, expected_seed=1)
    assert not agent.seen
    assert load_trajectory(recorder.path)[-1]["status"] == "error"


@pytest.mark.parametrize("section", ["capabilities", "visual"])
@pytest.mark.parametrize("version", [None, 0, 1, True, "2"])
def test_pause_only_visual_dll_cannot_start_actor(tmp_path, section, version):
    first = frame(tmp_path)
    first.observation.raw[section]["visual_clock_version"] = version
    agent = Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    transport = Transport([first])
    with pytest.raises(VisualTransportError, match="clock version 2"):
        runner.run_loop(transport, agent, recorder, expected_seed=1)
    assert not agent.seen and not transport.calls
    assert load_trajectory(recorder.path)[-1]["reason"] == "visual_infrastructure_error"


@pytest.fixture
def protected_cli(tmp_path, monkeypatch):
    save = tmp_path / "save"
    save.mkdir()
    original = b"original personal progress"
    (save / "continue.sav").write_bytes(original)
    events = []
    state = {"failure": None}
    monkeypatch.setattr(protected, "_processes", lambda: [])
    monkeypatch.setattr(protected, "os", SimpleNamespace(name="nt"))

    class FakeProtected(protected.ProtectedGame):
        def __init__(self, save, backup, bridge):
            super().__init__(save, backup, bridge, tmp_path / "game")

        def launch(self):
            events.append("launch")
            assert (self.backup / "continue.sav").read_bytes() == original
            (self.save / "continue.sav").write_bytes(b"benchmark modified progress")
            (self.save / "generated.sav").write_bytes(b"generated progress")
            if state["failure"] == "launch":
                raise RuntimeError("launch failed")

        def stop(self):
            events.append("stop")

        def restore_saves(self):
            events.append("restore")
            if state["failure"] == "restore":
                raise RuntimeError("restore failed")
            super().restore_saves()

    class FakeSession:
        def __init__(self, user_folder, **kwargs):
            assert user_folder == save
            assert kwargs["setup_output"].name == "fresh-setup"
            state["declared_seed"] = kwargs["seed"]
            pass

        def reset_episode(self, **kwargs):
            events.append("reset_episode")

        def reset(self):
            events.append("reset")

        def verify_first_capture(self, captured):
            trajectory = load_trajectory(captured.image_path.parent / "trajectory.jsonl")
            assert trajectory[-1]["kind"] == "reset"
            assert trajectory[-1]["visual"]["before"] == captured.reference
            assert captured.image_path.is_file()
            assert not agent.seen
            state["admission_frame"] = captured
            if state["failure"] == "admission":
                raise RuntimeError("fresh native seed arm refused")

    def fingerprint(*args):
        events.append("fingerprint")
        return {"native_build": {"matches_installed_dll": state["failure"] != "provenance",
                                  "fresh_start_seed": True, "fresh_seed_contract_version": 3,
                                  "fresh_seed_contract": "fresh-start-seed-v3"}}

    agent = Agent()
    monkeypatch.setattr(runner, "ProtectedGame", FakeProtected)
    executable = tmp_path / "fake-codex.exe"
    executable.write_bytes(b"fake CLI identity; never executed")
    monkeypatch.setattr(runner, "_codex_executable", lambda explicit: str(executable))
    monkeypatch.setattr(runner, "ftl_user_folder", lambda: save)
    monkeypatch.setattr(runner, "runtime_fingerprint", fingerprint)
    monkeypatch.setattr(runner, "FullGameSetupSession", FakeSession)
    monkeypatch.setattr(runner, "CodexVisualAgent", lambda **kwargs: agent)
    monkeypatch.setattr(runner, "VisualSession", lambda session, directory: Transport([frame(directory), frame(directory, 1, victory=True)]))
    return save, original, events, state, agent


def test_sector_trial_stops_at_native_target_and_declares_its_separate_scope(tmp_path, protected_cli, monkeypatch):
    directory = tmp_path / "sector-run"
    monkeypatch.setattr(runner, "VisualSession", lambda session, directory: Transport([
        frame(directory), frame(directory, 1, map={"sector": 1, "current_pos": {"x": 0, "y": 0}})]))
    runner.main(["--output", str(directory), "--stop-after-sector", "1", "--max-decisions", "3"])
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["trial_scope"] == "sector_progress" and manifest["stop_after_sector"] == 1
    assert manifest["scenario"]["type"] == "reach_sector"
    assert manifest["scenario"]["goal"][0]["key"] == "sector"
    assert manifest["reason"] == "sector_target_observed"
    report = json.loads((directory / "visual-report.json").read_text())
    assert report["outcome_category"] == "sector_target" and report["decisions"] == 1
    assert report["metrics"]["victory"] is False


@pytest.mark.parametrize("target", ["0", "-1"])
def test_sector_trial_rejects_invalid_targets_before_creating_output(tmp_path, target):
    directory = tmp_path / "bad-sector"
    with pytest.raises(SystemExit):
        runner.main(["--output", str(directory), "--stop-after-sector", target])
    assert not directory.exists()


def test_cli_saves_are_protected_before_launch_and_restored_before_success_manifest(tmp_path, protected_cli, monkeypatch):
    save, original, events, _, _ = protected_cli
    directory = tmp_path / "run"
    runner.main(["--output", str(directory), "--max-decisions", "1", "--mode", "hybrid"])
    assert events == ["launch", "fingerprint", "reset_episode", "reset", "stop", "restore"]
    assert (save / "continue.sav").read_bytes() == original and not (save / "generated.sav").exists()
    assert (directory / "save-backup/benchmark-generated/generated.sav").is_file()
    assert json.loads((directory / "save-backup/restoration.json").read_text())["verified"] is True
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["status"] == "completed" and manifest["reason"] == "native_victory"
    assert manifest["save_restoration"] == "verified" and manifest["valid_for_model_comparison"] is False
    assert manifest["budgets"]["idle_decisions"] == 8
    assert manifest["codex_cli"]["sha256"] == hashlib.sha256(b"fake CLI identity; never executed").hexdigest()
    assert json.loads((directory / "runtime-fingerprint.json").read_text())["codex_cli"] == manifest["codex_cli"]
    monkeypatch.setattr(live, "BENCH", tmp_path)
    snapshot = live.build("run/trajectory")
    assert snapshot["selected_score"]["score"] == 418
    assert snapshot["agg"]["mean"] is None and snapshot["agg"]["comparison_excluded"] == 1


@pytest.mark.parametrize("failure", ["launch", "provenance"])
def test_cli_failure_after_save_backup_restores_originals_and_closes_lifecycle(tmp_path, protected_cli, failure):
    save, original, events, state, agent = protected_cli
    state["failure"] = failure
    directory = tmp_path / "run"
    with pytest.raises(RuntimeError):
        runner.main(["--output", str(directory)])
    assert events[-2:] == ["stop", "restore"]
    assert (save / "continue.sav").read_bytes() == original
    assert load_trajectory(directory / "trajectory.jsonl")[-1]["status"] == "error"
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["status"] == "error" and manifest["save_restoration"] == "verified"
    assert not agent.seen


def test_cleanup_failure_is_reported_even_after_native_terminal_result(tmp_path, protected_cli):
    _, _, _, state, _ = protected_cli
    state["failure"] = "restore"
    directory = tmp_path / "run"
    with pytest.raises(RuntimeError, match="restore failed"):
        runner.main(["--output", str(directory), "--max-decisions", "1"])
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["status"] == "error" and manifest["error"] == "restore failed"
    assert manifest["save_restoration"] != "verified"
    assert load_trajectory(directory / "trajectory.jsonl")[-1]["reason"] == "native_victory"


@pytest.mark.parametrize("failure", ["capture", "model"])
def test_cli_preserves_specific_execution_error_and_verified_restoration(tmp_path, protected_cli, monkeypatch, failure):
    save, original, _, _, agent = protected_cli
    directory = tmp_path / "run"
    if failure == "capture":
        error = TimeoutError("action seq 2 not acked within 20.0s")
        monkeypatch.setattr(runner, "VisualSession", lambda session, folder: Transport([], capture_error=error))
    else:
        error = VisualProtocolError("invalid model JSON")
        agent.error = error
    with pytest.raises(type(error), match=str(error)):
        runner.main(["--output", str(directory)])
    assert (save / "continue.sav").read_bytes() == original
    manifest = json.loads((directory / "run.json").read_text())
    terminal = load_trajectory(directory / "trajectory.jsonl")[-1]
    report = json.loads((directory / "visual-report.json").read_text())
    expected = "visual_infrastructure_error" if failure == "capture" else "visual_model_error"
    assert manifest["reason"] == terminal["reason"] == report["reason"] == expected
    assert manifest["save_restoration"] == "verified"
    if failure == "capture":
        assert not agent.seen and report["decisions"] == 0
        assert all(value is None for value in report["metrics"].values())


def test_cleanup_failure_is_not_hidden_by_an_earlier_execution_error(tmp_path, protected_cli, monkeypatch):
    _, _, _, state, _ = protected_cli
    state["failure"] = "restore"
    directory = tmp_path / "run"
    monkeypatch.setattr(runner, "VisualSession", lambda session, folder: Transport([], capture_error=TimeoutError("capture timed out")))
    with pytest.raises(RuntimeError, match="restore failed"):
        runner.main(["--output", str(directory)])
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["reason"] == "protected_run_failed" and manifest["error"] == "restore failed"
    assert manifest["save_restoration"] != "verified"
    assert load_trajectory(directory / "trajectory.jsonl")[-1]["reason"] == "visual_infrastructure_error"


@pytest.mark.parametrize("args", [["--max-wall-seconds", "nan"], ["--max-wall-seconds", "inf"],
                                  ["--max-decisions", "0"], ["--max-idle-decisions", "0"],
                                  ["--max-idle-decisions", "-1"], ["--seed", "-1"], ["--seed", "4294967296"]])
def test_invalid_budgets_and_seeds_fail_before_creating_a_run(tmp_path, args):
    directory = tmp_path / "run"
    with pytest.raises(SystemExit):
        runner.main(["--output", str(directory), *args])
    assert not directory.exists()


def test_cli_idle_limit_is_forwarded_recorded_and_restores_saves(tmp_path, protected_cli, monkeypatch):
    save, original, events, _, _ = protected_cli
    directory = tmp_path / "run"
    agent = DecisionAgent([([], 0)] * 2)
    monkeypatch.setattr(runner, "CodexVisualAgent", lambda **kwargs: agent)
    monkeypatch.setattr(runner, "VisualSession", lambda session, folder: Transport([frame(folder, i) for i in range(3)]))
    runner.main(["--output", str(directory), "--max-idle-decisions", "2"])
    assert events[-2:] == ["stop", "restore"] and (save / "continue.sav").read_bytes() == original
    assert len(agent.seen) == 2
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["reason"] == "idle_decision_budget" and manifest["status"] == "completed"
    assert manifest["budgets"]["idle_decisions"] == 2 and manifest["save_restoration"] == "verified"
    assert load_trajectory(directory / "trajectory.jsonl")[0]["meta"]["budgets"]["idle_decisions"] == 2


@pytest.mark.parametrize("dispatched", [False, True])
def test_external_input_stops_run_once_and_preserves_distinct_interference_reason(tmp_path, dispatched):
    initial = frame(tmp_path)
    interrupted = frame(tmp_path, 1)
    interrupted.observation.raw["visual"].update(external_input_detected=True, external_input_generation="1")
    error = ExternalInputInterference(interrupted.observation, expected_generation="0", dispatched=dispatched)
    transport = Transport([initial], error=error)
    agent = Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    with pytest.raises(ExternalInputInterference):
        runner.run_loop(transport, agent, recorder, max_decisions=100)
    rows = load_trajectory(recorder.path)
    incident = rows[-2]
    assert incident["kind"] == "external_interference"
    assert incident["visual"]["external_input_guard"]["packet_dispatched"] is dispatched
    assert bool(incident["actions"]) is dispatched
    assert bool(incident["visual"]["inputs"]) is dispatched
    assert incident["visual"]["planned_inputs"]
    assert rows[-1]["status"] == "interrupted" and rows[-1]["reason"] == "external_interference"
    assert len(agent.seen) == len(transport.calls) == 1
    report = json.loads((tmp_path / "visual-report.json").read_text())
    assert report["comparison_exclusion_reason"] == "external_interference"


def test_external_input_on_first_capture_prevents_all_model_calls(tmp_path):
    observed = frame(tmp_path).observation
    observed.raw["visual"].update(external_input_detected=True, external_input_generation="1")
    agent = Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    with pytest.raises(ExternalInputInterference):
        runner.run_loop(Transport([], capture_error=ExternalInputInterference(observed)), agent, recorder)
    assert not agent.seen
    assert load_trajectory(recorder.path)[-1]["reason"] == "external_interference"


def test_cli_external_interference_preserves_reason_after_save_restoration(tmp_path, protected_cli, monkeypatch):
    save, original, events, _, agent = protected_cli
    directory = tmp_path / "run"
    def transport(session, directory):
        initial = frame(directory)
        obs = initial.observation
        obs.raw["visual"].update(external_input_detected=True, external_input_generation="1")
        return Transport([], capture_error=ExternalInputInterference(obs))
    monkeypatch.setattr(runner, "VisualSession", transport)
    with pytest.raises(ExternalInputInterference):
        runner.main(["--output", str(directory)])
    assert events[-2:] == ["stop", "restore"]
    assert (save / "continue.sav").read_bytes() == original
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["status"] == "interrupted" and manifest["reason"] == "external_interference"
    assert manifest["comparison_exclusion_reason"] == "external_interference"
    assert not agent.seen


@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_main_v3_admission_refusal_preserves_first_image_and_protected_cleanup(tmp_path, protected_cli, monkeypatch, cleanup_failure):
    save, original, events, state, agent = protected_cli
    directory = tmp_path / "admission-run"
    state["failure"] = "admission"
    if cleanup_failure:
        # The validation refusal remains in the trajectory even if later cleanup fails.
        original_restore = runner.ProtectedGame.restore_saves
        def failed_restore(self):
            state["failure"] = "restore"
            return original_restore(self)
        monkeypatch.setattr(runner.ProtectedGame, "restore_saves", failed_restore)
    with pytest.raises(RuntimeError, match="restore failed" if cleanup_failure else "fresh native seed arm refused"):
        runner.main(["--output", str(directory)])
    rows = load_trajectory(directory / "trajectory.jsonl")
    assert [r["kind"] for r in rows] == ["meta", "reset", "end"]
    assert rows[-1]["reason"] == "visual_infrastructure_error"
    assert rows[-1]["error"] == "fresh native seed arm refused"
    assert events[-2:] == ["stop", "restore"] and not agent.seen
    assert state["admission_frame"].image_path.is_file()
    report = json.loads((directory / "visual-report.json").read_text())
    manifest = json.loads((directory / "run.json").read_text())
    assert report["model_calls"]["calls"] == 0 and report["decisions"] == 0
    assert manifest["startup_contract"] == "fresh-start-seed-v3"
    assert manifest["fixture_free_startup"] is True
    if cleanup_failure:
        assert manifest["reason"] == "protected_run_failed" and manifest["save_restoration"] != "verified"
    else:
        assert manifest["reason"] == "visual_infrastructure_error" and manifest["save_restoration"] == "verified"
        assert (save / "continue.sav").read_bytes() == original
        assert not (save / "generated.sav").exists()


@pytest.mark.parametrize("bad_fields", [
    {"fresh_start_seed": None}, {"fresh_start_seed": False},
    {"fresh_seed_contract_version": 2}, {"fresh_seed_contract_version": True},
    {"fresh_seed_contract": "fresh-start-seed-v2"},
])
def test_main_requires_v3_before_any_setup_or_actor(tmp_path, protected_cli, monkeypatch, bad_fields):
    save, original, events, _, agent = protected_cli
    directory = tmp_path / "refused-runtime"
    old_fingerprint = runner.runtime_fingerprint
    def fingerprint(*args):
        result = old_fingerprint(*args)
        result["native_build"].update(bad_fields)
        return result
    monkeypatch.setattr(runner, "runtime_fingerprint", fingerprint)
    with pytest.raises(RuntimeError, match="fresh-start seed contract v3"):
        runner.main(["--output", str(directory)])
    assert events == ["launch", "fingerprint", "stop", "restore"]
    assert not agent.seen and (save / "continue.sav").read_bytes() == original
    assert [r["kind"] for r in load_trajectory(directory / "trajectory.jsonl")] == ["meta", "end"]


def test_main_default_v3_passes_same_initial_intro_image_to_actor(tmp_path, protected_cli, monkeypatch):
    _, _, events, state, agent = protected_cli
    directory = tmp_path / "intro-run"
    first = None
    def transport(session, folder):
        nonlocal first
        first = frame(folder, seed=17, event={"text": "Untouched initial intro", "choices": ["Continue"]})
        return Transport([first, frame(folder, 1, victory=True)])
    monkeypatch.setattr(runner, "VisualSession", transport)
    runner.main(["--output", str(directory), "--seed", "17", "--max-decisions", "1"])
    assert state["declared_seed"] == 17
    assert state["admission_frame"] is first
    assert agent.seen[0].image_path == first.image_path
    assert agent.seen[0].history == [] and agent.seen[0].memory == ""
    assert events == ["launch", "fingerprint", "reset_episode", "reset", "stop", "restore"]


def test_cooperative_stop_after_actor_restores_saves_and_preserves_call(tmp_path, protected_cli, monkeypatch):
    from visual_cancellation import request_stop, CooperativeStop
    save, original, events, _, agent = protected_cli
    stop = tmp_path / "stop.json"
    decide = agent.decide
    def stopping_decide(observation):
        decision = decide(observation)
        request_stop(stop, "test-experiment", "assistant:test", "pause_for_review")
        return decision
    monkeypatch.setattr(agent, "decide", stopping_decide)
    directory = tmp_path / "cancelled-run"
    with pytest.raises(CooperativeStop):
        runner.main(["--output", str(directory), "--stop-file", str(stop), "--stop-scope", "test-experiment"])
    assert (save / "continue.sav").read_bytes() == original
    assert not (save / "generated.sav").exists()
    assert events[-2:] == ["stop", "restore"]
    rows = load_trajectory(directory / "trajectory.jsonl")
    assert rows[-2]["kind"] == "model_cancelled" and rows[-2]["actions"] == []
    assert not any(row["kind"].startswith("step") for row in rows)
    manifest = json.loads((directory / "run.json").read_text())
    assert manifest["status"] == "interrupted" and manifest["save_restoration"] == "verified"
    assert manifest["reason"] == "cooperative_stop_requested"
    assert manifest["stop_request"]["request"]["initiator"] == "assistant:test"
    report = json.loads((directory / "visual-report.json").read_text())
    assert report["model_calls"]["calls"] == 1
    assert report["outcome_category"] == "operator_interruption"


def test_preexisting_stop_avoids_game_launch(tmp_path, protected_cli):
    from visual_cancellation import request_stop, CooperativeStop
    stop = tmp_path / "stop.json"
    request_stop(stop, "test", "operator")
    save, original, events, _, agent = protected_cli
    with pytest.raises(CooperativeStop):
        runner.main(["--output", str(tmp_path / "pre-stopped"), "--stop-file", str(stop), "--stop-scope", "test"])
    assert not events and not agent.seen
    assert (save / "continue.sav").read_bytes() == original


def test_stop_scope_requires_control_file(tmp_path):
    with pytest.raises(SystemExit):
        runner.main(["--output", str(tmp_path / "no-control"), "--stop-scope", "test"])
    assert not (tmp_path / "no-control").exists()


def test_startup_stop_is_recorded_before_protected_save_cleanup(tmp_path, protected_cli, monkeypatch):
    from visual_cancellation import request_stop, CooperativeStop
    save, original, events, _, agent = protected_cli
    stop, directory = tmp_path / "startup-stop.json", tmp_path / "startup-stopped"
    launch = runner.ProtectedGame.launch
    restore = runner.ProtectedGame.restore_saves
    def stopped_launch(self):
        launch(self)
        request_stop(stop, "startup-test", "assistant:test")
    def checked_restore(self):
        terminal = load_trajectory(directory / "trajectory.jsonl")[-1]
        assert terminal["kind"] == "end" and terminal["reason"] == "cooperative_stop_requested"
        assert terminal["stop_request"]["observed_boundary"] == "after_game_launch"
        restore(self)
    monkeypatch.setattr(runner.ProtectedGame, "launch", stopped_launch)
    monkeypatch.setattr(runner.ProtectedGame, "restore_saves", checked_restore)
    with pytest.raises(CooperativeStop):
        runner.main(["--output", str(directory), "--stop-file", str(stop), "--stop-scope", "startup-test"])
    assert events == ["launch", "stop", "restore"] and not agent.seen
    assert (save / "continue.sav").read_bytes() == original


@pytest.fixture
def portable_fullgame(tmp_path, protected_cli, monkeypatch):
    from ftl_bench import visual_admission
    from ftl_bench.native_acceptance import CAPABILITIES, RUNTIME_FILES
    import run_fullgame_experiment as controller
    _, _, events, state, _ = protected_cli
    cohort = tmp_path / "portable-cohort"
    cohort.mkdir()
    protocol_file = cohort / "protocol.json"
    directory = cohort / "trials/fullgame/gpt-6.1-sol/image"
    bridge_hash = hashlib.sha256((runner.ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua").read_bytes()).hexdigest()
    files = {name: "a" * 64 for name in RUNTIME_FILES}
    build = {**CAPABILITIES, "matches_installed_dll": True, "dll_sha256": "a" * 64, "patch_sha256": "b" * 64}
    admitted = {"runtime_files": files, "runtime": {"dll_sha256": "a" * 64,
                "patch_sha256": "b" * 64, "production_bridge_sha256": bridge_hash}}
    protocol = {"contract": visual_admission.FULLGAME_CONTRACT,
                "codex_cli": runner.codex_runtime_identity(), "seed": 1, "reasoning_effort": "medium",
                "budgets": {"decisions": 1, "wall_seconds": 14400, "idle_decisions": 8},
                "cells": [controller.plan_cells()[1]],
                "admission_selector": {"spec": {"sha256": "c" * 64}, "admission": admitted}}
    protocol_file.write_text(json.dumps(protocol), encoding="utf-8")
    def verify(received, *, directory, verify_installed):
        events.append("portable-gate")
        assert directory == cohort and verify_installed is False and received == protocol
        if state["failure"] == "archive":
            raise ValueError("Archived evidence changed")
    def installed(root):
        actual = dict(files)
        if state["failure"] == "runtime":
            actual["ftl.dat"] = "d" * 64
        return {"files_sha256": actual, "native_build": build}
    def fingerprint(root):
        events.append("fingerprint")
        return {"native_build": build, "native_dll": {"sha256": files["Hyperspace.dll"]},
                "bridge_lua": {"sha256": "e" * 64 if state["failure"] == "bridge" else bridge_hash}}
    monkeypatch.setattr(controller, "verify_protocol", verify)
    monkeypatch.setattr(visual_admission, "installed_runtime", installed)
    monkeypatch.setattr(runner, "runtime_fingerprint", fingerprint)
    return protocol_file, directory, protocol


def test_portable_fullgame_gate_precedes_actor_and_preserves_cleanup(portable_fullgame, protected_cli):
    from ftl_bench.visual_admission import audit_trial_admission
    protocol_file, directory, protocol = portable_fullgame
    save, original, events, _, agent = protected_cli
    runner.main(["--output", str(directory), "--experiment-file", str(protocol_file), "--max-decisions", "1"])
    receipt = json.loads((directory / "controller-admission.json").read_text())
    assert receipt["accepted"] is True and len(agent.seen) == 1
    assert events.index("portable-gate") < events.index("reset_episode")
    assert events[-2:] == ["stop", "restore"]
    assert (save / "continue.sav").read_bytes() == original
    assert not audit_trial_admission(directory, protocol, protocol_file=protocol_file)


@pytest.mark.parametrize("failure, overrides", [
    ("archive", []), ("runtime", []), ("bridge", []),
    (None, ["--model", "gpt-6-luna"]), (None, ["--mode", "hybrid"]),
    (None, ["--seed", "2"]), (None, ["--reasoning-effort", "high"]),
    (None, ["--max-decisions", "2"]), (None, ["--max-wall-seconds", "60"]),
    (None, ["--max-idle-decisions", "3"]), (None, ["--stop-after-sector", "1"]),
])
def test_portable_fullgame_rejection_retains_receipt_without_calls(
        portable_fullgame, protected_cli, failure, overrides):
    protocol_file, directory, _ = portable_fullgame
    save, original, events, state, agent = protected_cli
    state["failure"] = failure
    with pytest.raises(ValueError):
        runner.main(["--output", str(directory), "--experiment-file", str(protocol_file),
                     "--max-decisions", "1", *overrides])
    receipt = json.loads((directory / "controller-admission.json").read_text())
    manifest = json.loads((directory / "run.json").read_text())
    assert receipt["accepted"] is False and receipt["error"]
    assert manifest["controller_admission_sha256"] == hashlib.sha256(
        (directory / "controller-admission.json").read_bytes()).hexdigest()
    assert manifest["reason"] == "protected_run_failed" and manifest["save_restoration"] == "verified"
    assert events[-2:] == ["stop", "restore"] and "reset_episode" not in events and not agent.seen
    assert (save / "continue.sav").read_bytes() == original
    assert not (save / "generated.sav").exists()
