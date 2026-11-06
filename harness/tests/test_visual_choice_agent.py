"""Typed visual actors select real primitive packets without native observations."""
import hashlib
import json
import re

import pytest

import visual_choice_agent as actor
from visual_agent import VisualBackendError, VisualObservation, VisualProtocolError
from test_visual_agent import png


def observation(tmp_path, width=1280, height=720, **kwargs):
    path = tmp_path / "frame.png"
    path.write_bytes(png(width, height))
    return VisualObservation(path, "frame-1", **kwargs)


def choose_point(options, point):
    for key, description in options.items():
        x0, x1, y0, y1 = map(int, re.findall(r"\d+", description))
        if x0 <= point[0] <= x1 and y0 <= point[1] <= y1:
            return key
    raise AssertionError("Point missing from region partition")


def responder(monkeypatch, control, start=(1279, 719), end=(0, 0), fail_stage=None):
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        question = kwargs["question"]
        stage = question["name"]
        call = {"stage": stage, "status": "completed", "response_received": True,
                "model": kwargs["model"], "attempts": 1, "usage": {"input_tokens": 10, "output_tokens": 0},
                "latency_seconds": .1}
        if stage == fail_stage:
            call.update(status="error", response_received=False, usage=None)
            raise VisualBackendError("Provider unavailable", metadata={"api_call": call})
        if stage == "control":
            choice = control
        elif stage == "advance":
            choice = "120"
        else:
            choice = choose_point(question["choices"], start if stage.startswith("start_") else end)
        return choice, {**call, "choice": choice}
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr(actor, "request_choice", request)
    return calls


@pytest.mark.parametrize("backend", ["jev", "openai-decisions"])
@pytest.mark.parametrize("control,expected", [
    ("wait", []),
    ("key:f:shift", [{"type": "key", "key": "f", "modifiers": ["shift"]}]),
    ("move", [{"type": "move", "x": 1279, "y": 719}]),
    ("click:right:shift+ctrl", [{"type": "click", "button": "right", "modifiers": ["shift", "ctrl"], "x": 1279, "y": 719}]),
    ("drag:left:none", [{"type": "drag", "button": "left", "modifiers": [], "x": 1279, "y": 719, "to_x": 0, "to_y": 0}]),
])
def test_complete_primitive_from_exact_image(tmp_path, monkeypatch, backend, control, expected):
    calls = responder(monkeypatch, control)
    obs = observation(tmp_path)
    agent = actor.TypedVisualAgent(backend, audit_root=tmp_path / "api-decisions")
    decision = agent.decide(obs)
    assert decision.actions == expected
    assert decision.advance_frames == 120
    assert decision.metadata["decision_complete"] is True
    assert all(call["image_bytes"] == obs.image_path.read_bytes() for call in calls)
    assert decision.metadata["image"]["sha256"] == hashlib.sha256(obs.image_path.read_bytes()).hexdigest()
    assert all(2 <= len(call["question"]["choices"]) <= 255 for call in calls)
    assert decision.metadata["usage"] == {"input_tokens": 10 * len(calls), "output_tokens": 0}
    assert len(calls) <= 8
    assert "native" not in json.dumps([call["question"] for call in calls]).lower()
    saved = list((tmp_path / "api-decisions").glob("*/metadata.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text())["api_calls"] == decision.metadata["api_calls"]


def test_partial_chain_retains_calls_and_unknown_total(tmp_path, monkeypatch):
    responder(monkeypatch, "click:left:none", fail_stage="start_1")
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions")
    with pytest.raises(VisualBackendError) as failed:
        agent.decide(observation(tmp_path))
    meta = failed.value.metadata
    assert meta["decision_complete"] is False
    assert [c["status"] for c in meta["api_calls"]] == ["completed", "error"]
    assert meta["usage"] == {}
    assert meta["latency_seconds"] >= 0
    assert not list((tmp_path / "api-decisions").glob("*/decision.json"))
    saved = json.loads(next((tmp_path / "api-decisions").glob("*/metadata.json")).read_text())
    assert saved == meta


@pytest.mark.parametrize("width,height", [(1, 1), (1, 720), (1280, 1), (320, 180), (1280, 720), (8192, 8192)])
def test_regions_reach_every_edge_pixel_within_four_choices(width, height):
    for point in ((0, 0), (width - 1, height - 1), (width // 2, height // 2)):
        bounds = (0, 0, width - 1, height - 1)
        for _ in range(4):
            if bounds[0] == bounds[2] and bounds[1] == bounds[3]:
                break
            cells = actor.regions(bounds)
            assert 2 <= len(cells) <= 225
            matches = [b for b in cells.values() if b[0] <= point[0] <= b[2] and b[1] <= point[1] <= b[3]]
            assert len(matches) == 1
            assert sum((b[2] - b[0] + 1) * (b[3] - b[1] + 1) for b in cells.values()) == (bounds[2] - bounds[0] + 1) * (bounds[3] - bounds[1] + 1)
            bounds = matches[0]
        assert bounds == (*point, *point)


def test_reject_changed_png_before_http(tmp_path, monkeypatch):
    calls = responder(monkeypatch, "wait")
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions")
    with pytest.raises(VisualBackendError, match="archived frame"):
        agent.decide(observation(tmp_path, expected_image_sha256="0" * 64))
    assert calls == []
    assert not (tmp_path / "api-decisions").exists()


def test_hidden_hud_fields_never_reach_http(tmp_path, monkeypatch):
    calls = responder(monkeypatch, "wait")
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions")
    with pytest.raises(VisualProtocolError, match="unapproved"):
        agent.decide(observation(tmp_path, mode="hybrid", visible_hud={"hidden_rng": 7}))
    assert calls == []


def test_stop_between_stages_keeps_partial_evidence(tmp_path, monkeypatch):
    calls = responder(monkeypatch, "wait")
    def stop():
        if calls:
            raise KeyboardInterrupt()
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions", stop_check=stop)
    with pytest.raises(KeyboardInterrupt) as interrupted:
        agent.decide(observation(tmp_path))
    assert len(interrupted.value.metadata["api_calls"]) == 1
    assert interrupted.value.metadata["decision_complete"] is False
    assert not list((tmp_path / "api-decisions").glob("*/decision.json"))


def test_unsupported_model_and_missing_credentials_fail_early(tmp_path, monkeypatch):
    with pytest.raises(VisualProtocolError, match="only gpt-6-luna"):
        actor.TypedVisualAgent("openai-decisions", "gpt-6.1-sol", audit_root=tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions")
    with pytest.raises(VisualBackendError, match="TYPESAFE_API_KEY"):
        agent.decide(observation(tmp_path))
    assert not (tmp_path / "api-decisions").exists()


@pytest.mark.parametrize("source", ["task", "memory", "history"])
def test_configured_credential_in_public_text_is_never_sent_or_archived(tmp_path, monkeypatch, source):
    calls = responder(monkeypatch, "wait")
    secret = "test-only-key"
    kwargs = {"task": secret} if source == "task" else {}
    obs_kwargs = {"memory": secret} if source == "memory" else {}
    if source == "history":
        obs_kwargs["history"] = [{"intent": secret, "actions": [], "advance_frames": 0}]
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions", **kwargs)
    with pytest.raises(VisualBackendError, match="credential"):
        agent.decide(observation(tmp_path, **obs_kwargs))
    assert calls == []
    assert not (tmp_path / "api-decisions").exists()


def test_interrupt_during_second_http_request_preserves_both_attempts(tmp_path, monkeypatch):
    import visual_decision_api as api
    from types import SimpleNamespace
    from test_visual_decision_api import Reply, response

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-interrupt-only")
    attempted = []
    interrupt = KeyboardInterrupt()
    def open_request(request, *, timeout):
        body = json.loads(request.data)
        name, question = next(iter(body["questions"].items()))
        attempted.append(name)
        if name == "advance":
            raise interrupt
        probabilities = {key: float(key == "wait") for key in question["criteria"]}
        return Reply(json.dumps(response("jev", "wait", probabilities, name)).encode())
    monkeypatch.setattr(api, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions")
    with pytest.raises(KeyboardInterrupt) as raised:
        agent.decide(observation(tmp_path))
    assert raised.value is interrupt
    assert attempted == ["control", "advance"]
    metadata = raised.value.metadata
    assert [call["attempts"] for call in metadata["api_calls"]] == [1, 1]
    assert metadata["api_calls"][1]["error_code"] == "operator_interrupted"
    assert metadata["usage"] == {}
    assert metadata["decision_complete"] is False
    directory = tmp_path / metadata["artifact"]
    assert not (directory / "decision.json").exists()
    assert json.loads((directory / "metadata.json").read_text()) == metadata


def test_last_stage_past_decision_deadline_retains_usage_without_result(tmp_path, monkeypatch):
    responder(monkeypatch, "wait")
    request = actor.request_choice
    clock = [0.0]
    monkeypatch.setattr(actor.time, "monotonic", lambda: clock[0])
    def delayed(**kwargs):
        result = request(**kwargs)
        if kwargs["question"]["name"] == "advance":
            clock[0] = 2.0
        return result
    monkeypatch.setattr(actor, "request_choice", delayed)
    agent = actor.TypedVisualAgent("jev", audit_root=tmp_path / "api-decisions", timeout_seconds=1)
    with pytest.raises(VisualBackendError, match="time budget") as raised:
        agent.decide(observation(tmp_path))
    assert len(raised.value.metadata["api_calls"]) == 2
    assert raised.value.metadata["usage"]["input_tokens"] == 20
    assert raised.value.metadata["decision_complete"] is False
    assert not list((tmp_path / "api-decisions").glob("*/decision.json"))
