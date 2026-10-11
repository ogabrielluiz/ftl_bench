"""Exercise the production runner; no subprocess/game/model/network calls."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

import pytest

import run_visual as runner

from ftl_bench.observation import Observation
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory
from ftl_bench.visual_session import ExternalInputInterference, VisualFrame
from ftl_bench.fullgame_setup import FullGameSetupSession
from visual_agent import VisualDecision
import ftl_live


@pytest.fixture(autouse=True)
def no_external_execution(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Runner tests cannot launch subprocesses or contact providers")
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(ftl_live, "ftl_process_alive", lambda: False)


def frame(directory, index=0, **updates):
    image = directory / f"fake-{index}.png"
    image.write_bytes(b"synthetic image; actual PNG transport validation is tested separately")
    world = str(index * 60)
    raw = {"schema_version": 3, "tick": index, "seed": 1, "game_started": True, "paused": True,
        "difficulty": 0, "ftl_score": 418, "victory": False,
        "capabilities": {"native_protocol": 5, "live_score": True, "victory": True,
            "external_input_guard": True, "visual_clock_version": 2, "world_updates": world,
            "fixed_step_numerator": 1, "fixed_step_denominator": 60, "simulated_updates": world},
        "player_ship": {"blueprint": "PLAYER_SHIP_HARD", "resources": {"fuel": 16},
            "hull": {"current": 30, "max": 30}},
        "map": {"sector": 0, "current_pos": {"x": 0, "y": 0}},
        "visual": {"visual_clock_version": 2, "world_updates": world, "fixed_step_numerator": 1,
            "fixed_step_denominator": 60, "simulated_updates": world, "actual_frames": 60,
            "input_feedback": []}, **updates}
    ref = {"path": image.name, "frame_id": f"first-{index}", "width": 1280, "height": 720,
        "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
    return VisualFrame(Observation.from_dict(raw), image, ref, index)


class Transport:
    def __init__(self, first, after=None):
        self.first, self.after = first, after
        self.captures, self.steps = 0, []

    def capture(self):
        self.captures += 1
        return self.first

    def step(self, before, actions, advance):
        self.steps.append((before, actions, advance))
        return self.after


class Agent:
    def __init__(self):
        self.seen = []

    def decide(self, obs):
        self.seen.append(obs)
        return VisualDecision([], 60, "Proceed through ordinary gameplay", "", {"model": "fake", "latency_seconds": .01})


@pytest.mark.parametrize("mode", ["image", "hybrid"])
def test_rejected_native_admission_retains_reset_before_seed_or_model(tmp_path, monkeypatch, mode):
    native = {"phase": "failed", "error": "fresh native seed arm refused",
        "native_seed": {"failed": True, "error": "construction_observed_before_arm"}}
    first = frame(tmp_path, deterministic_setup=native)
    transport, agent = Transport(first), Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    seen = []
    def reject(captured):
        assert captured is first
        rows = load_trajectory(recorder.path)
        assert [r["kind"] for r in rows] == ["meta", "reset"]
        assert rows[-1]["obs"]["deterministic_setup"] == native
        assert rows[-1]["visual"]["before"] == first.reference
        seen.append(captured)
        raise RuntimeError(native["error"])
    monkeypatch.setattr(runner, "verify_visual_setup", lambda *a: pytest.fail("admission precedes seed verification"))
    monkeypatch.setattr(runner, "extract_visible_hud", lambda *a: pytest.fail("admission precedes HUD extraction"))
    with pytest.raises(RuntimeError, match="fresh native seed arm refused"):
        runner.run_loop(transport, agent, recorder, mode=mode, expected_seed=1, initial_frame_validator=reject)
    rows = load_trajectory(recorder.path)
    assert [r["kind"] for r in rows] == ["meta", "reset", "end"]
    assert rows[-1]["reason"] == "visual_infrastructure_error" and rows[-1]["status"] == "error"
    assert rows[-1]["error"] == native["error"] and rows[-1]["decisions"] == 0
    assert recorder.closed and len(seen) == transport.captures == 1
    assert not agent.seen and not transport.steps
    assert first.image_path.is_file() and hashlib.sha256(first.image_path.read_bytes()).hexdigest() == first.reference["sha256"]
    report = json.loads((tmp_path / "visual-report.json").read_text())
    assert report["reason"] == rows[-1]["reason"] and report["status"] == "error"
    assert report["outcome_category"] == "infrastructure_failure"
    assert report["decisions"] == report["model_calls"]["calls"] == 0
    assert report["recorded_game_observations"] == 1
    assert not (tmp_path / "setup-verification.json").exists()


def test_callback_success_keeps_exact_same_initial_frame_and_no_extra_capture(tmp_path, monkeypatch):
    first, after = frame(tmp_path), frame(tmp_path, 1, game_over=True)
    transport, agent = Transport(first, after), Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    order = []
    def validate(captured):
        assert captured is first
        assert load_trajectory(recorder.path)[-1]["visual"]["before"] == first.reference
        assert not agent.seen and not transport.steps
        order.append("admission")
        return {"passed": True, "hidden_native_receipt": "never give this to actor"}
    original = runner.verify_visual_setup
    def setup(captured, seed):
        assert captured is first and order == ["admission"]
        order.append("seed")
        return original(captured, seed)
    monkeypatch.setattr(runner, "verify_visual_setup", setup)
    report = runner.run_loop(transport, agent, recorder, expected_seed=1, max_decisions=1,
                             initial_frame_validator=validate)
    assert order == ["admission", "seed"] and transport.captures == 1
    assert transport.steps[0][0] is first and agent.seen[0].image_path == first.image_path
    assert agent.seen[0].frame_id == first.reference["frame_id"]
    assert "hidden_native_receipt" not in json.dumps(asdict(agent.seen[0]), default=str)
    assert report["reason"] == "native_game_over" and report["outcome_category"] == "game_loss"
    assert report["decisions"] == 1


@pytest.mark.parametrize("terminal", ["victory", "game_over"])
def test_successful_admission_preserves_native_terminal_precedence(tmp_path, terminal):
    first = frame(tmp_path, **{terminal: True})
    transport, agent = Transport(first), Agent()
    seen = []
    report = runner.run_loop(transport, agent, TrajectoryRecorder(tmp_path / "trajectory.jsonl"),
        initial_frame_validator=lambda captured: seen.append(captured),
        stop_when=lambda *a: pytest.fail("native terminal must precede stop predicate"))
    assert seen == [first] and not agent.seen and not transport.steps
    assert report["reason"] == ("native_victory" if terminal == "victory" else "native_game_over")
    assert report["decisions"] == 0


def test_first_frame_validator_can_be_omitted_for_existing_callers(tmp_path):
    report = runner.run_loop(Transport(frame(tmp_path, victory=True)), Agent(),
        TrajectoryRecorder(tmp_path / "trajectory.jsonl"))
    assert report["reason"] == "native_victory"


@pytest.mark.parametrize("kind", ["operator", "interference"])
def test_validator_interruption_keeps_existing_lifecycle_category(tmp_path, kind):
    first = frame(tmp_path)
    error = KeyboardInterrupt() if kind == "operator" else ExternalInputInterference(first.observation)
    def interrupted(captured):
        raise error
    transport, agent = Transport(first), Agent()
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    with pytest.raises(type(error)):
        runner.run_loop(transport, agent, recorder, initial_frame_validator=interrupted)
    rows = load_trajectory(recorder.path)
    assert rows[-2]["kind"] == "reset" and rows[-1]["status"] == "interrupted"
    assert rows[-1]["reason"] == ("user_interrupted" if kind == "operator" else "external_interference")
    assert not agent.seen and not transport.steps


def test_real_fullgame_proof_failure_is_recorded_without_actor_decision(tmp_path, monkeypatch):
    first = frame(tmp_path, last_action_seq=2, deterministic_setup={
        "contract": "deterministic-setup-v1", "version": 1, "seed": 1, "phase": "visual",
        "native_seed": {"contract": "fresh-start-seed-v3", "contract_version": 3,
            "native_seed_applications": 0, "error": "fresh seed did not apply"}})
    session = FullGameSetupSession(tmp_path, setup_output=tmp_path / "fresh-setup", seed=1)
    monkeypatch.setattr(session, "_write_action_atomic", lambda *a: None)
    session.handoff_requested = True
    agent, transport = Agent(), Transport(first)
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    with pytest.raises(RuntimeError, match="admission failed"):
        runner.run_loop(transport, agent, recorder, initial_frame_validator=session.verify_first_capture)
    proof = json.loads((session.setup_output / "admission.json").read_text())
    assert not proof["passed"] and not session.admitted
    assert proof["first_image"] == load_trajectory(recorder.path)[-2]["visual"]["before"]
    assert proof["first_observation"]["deterministic_setup"]["native_seed"]["error"] == "fresh seed did not apply"
    assert not agent.seen and not transport.steps

