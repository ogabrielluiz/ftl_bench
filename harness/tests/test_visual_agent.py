"""Visual decisions: image identity, information boundary, and audited CLI protocol.

All model subprocesses are mocked. These tests never consume provider quota.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace
import zlib

import pytest

import visual_agent as visual


def png(width=320, height=180):
    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + b"\x30\x50\x70" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def answer(**kwargs):
    return {"actions": [{"type": "click", "x": 40, "y": 30, "button": "left", "modifiers": []}],
            "advance_frames": 0, "intent": "Close the store", "memory": "Buy fuel, then travel.", **kwargs}


def event_stream(reply, extra=None):
    events = [{"type": "thread.started", "thread_id": "fixture-thread"}, {"type": "turn.started"}]
    events.extend(extra or [])
    events.extend([{"type": "item.completed", "item": {"id": "reply", "type": "agent_message", "text": reply}},
                   {"type": "turn.completed", "usage": {"input_tokens": 101, "cached_input_tokens": 0, "output_tokens": 21}}])
    return "\n".join(json.dumps(e) for e in events) + "\n"


@pytest.fixture
def observation(tmp_path):
    image = tmp_path / "decision.png"
    image.write_bytes(png())
    return visual.VisualObservation(image, "frame-18")


@pytest.fixture
def executable(tmp_path):
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"mock CLI; never executed")
    return executable


def test_codex_attaches_exact_image_in_separate_workspace_and_audits_answer(monkeypatch, observation, executable):
    captured = {}
    reply = json.dumps(answer())

    def run(command, **kwargs):
        captured.update(command=command, **kwargs)
        staged = Path(command[command.index("--image") + 1])
        assert staged.read_bytes() == observation.image_path.read_bytes()
        assert staged.parent != observation.image_path.parent
        assert kwargs["cwd"] == staged.parent
        assert set(p.name for p in staged.parent.iterdir()) == {"screenshot.png", "decision.schema.json"}
        schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
        assert schema["properties"]["actions"]["items"]["anyOf"][0]["properties"]["x"]["maximum"] == 319
        Path(command[command.index("-o") + 1]).write_text(reply, encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=event_stream(reply), stderr="")

    monkeypatch.setattr(visual.subprocess, "run", run)
    decision = visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    assert decision.as_dict() == answer()
    assert decision.metadata["frame_id"] == "frame-18"
    assert decision.metadata["image"]["width"] == 320
    assert decision.metadata["tool_use"] is False
    assert decision.metadata["usage"]["input_tokens"] == 101
    assert decision.metadata["latency_seconds"] >= 0
    assert "--ignore-user-config" in captured["command"]
    assert "--ephemeral" in captured["command"] and "--json" in captured["command"]
    assert captured["command"][-1] == "-"
    assert "gpt-6.1-sol" in captured["command"]
    assert str(observation.image_path) not in captured["input"].decode("utf-8")
    assert "visible_hud" not in captured["input"].decode("utf-8").split("DECISION INPUT\n")[1]
    assert not Path(captured["cwd"]).exists()
    assert decision.metadata["response_model_identity"]["status"] == "not_reported"
    assert decision.metadata["requested_model"] == "gpt-6.1-sol"


def test_invalid_model_json_retains_provider_usage_and_explicit_model_identity(monkeypatch, observation, executable):
    reply = '{"invalid":"decision"}'
    def run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text(reply)
        events = [json.loads(line) for line in event_stream(reply).splitlines()]
        events[-1]["model"] = "provider-reported-fixture"
        return SimpleNamespace(returncode=0, stderr="", stdout="\n".join(json.dumps(e) for e in events))
    monkeypatch.setattr(visual.subprocess, "run", run)
    with pytest.raises(visual.VisualProtocolError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    metadata = error.value.metadata
    assert metadata["usage"] == {"input_tokens": 101, "cached_input_tokens": 0, "output_tokens": 21}
    assert metadata["tool_use"] is False and "events" not in metadata
    assert "turn.completed" in metadata["cli_failure"]["stdout"]["text"]
    assert metadata["response_model_identity"]["models"] == ["provider-reported-fixture"]
    assert metadata["requested_model"] == "gpt-6.1-sol"


def test_instruction_identity_distinguishes_public_tasks_without_changing_manual():
    first = visual.CodexVisualAgent(task="Recover the crew.").instruction_identity()
    second = visual.CodexVisualAgent(task="Win this combat.").instruction_identity()
    assert first["manual_sha256"] == second["manual_sha256"]
    assert first["instructions_sha256"] != second["instructions_sha256"]
    assert first["task_sha256"] != second["task_sha256"]
    assert first["task"] == "Recover the crew."
    assert first["prompt_version"] == "ftl-visual-v2"


def test_v2_manual_only_versions_and_declares_fixed_time_preserving_v1():
    import hashlib
    original = visual.PROMPT_PATH.with_name("ftl_visual_v1.md").read_bytes()
    assert hashlib.sha256(original).hexdigest() == "2b15a30d735915a939587688f9c6f7bf6925b69e71a1fb097440bc865e589029"
    expected = original.decode("utf-8").replace("FTL visual player — interface v1", "FTL visual player — interface v2", 1)
    expected = expected.replace("the next screenshot. Use zero to inspect the result of menu actions or aiming.",
        "the next screenshot. Each admitted update represents 1/60 second of simulation\n"
        "time: 60 frames = 1 second and 600 frames = 10 seconds.\n"
        "Use zero to inspect the result of menu actions or aiming.", 1)
    assert visual.PROMPT_PATH.read_bytes() == expected.encode("utf-8")


def test_actor_freezes_manual_bytes_at_construction(tmp_path, monkeypatch, observation, executable):
    manual = tmp_path / "manual.md"
    manual.write_text("Original instructions", encoding="utf-8")
    monkeypatch.setattr(visual, "PROMPT_PATH", manual)
    actor = visual.CodexVisualAgent(codex_bin=executable)
    identity = actor.instruction_identity()
    manual.write_text("Changed during trial", encoding="utf-8")
    reply = json.dumps(answer())
    def run(command, **kwargs):
        assert kwargs["input"].decode("utf-8").startswith("Original instructions")
        Path(command[command.index("-o") + 1]).write_text(reply)
        return SimpleNamespace(returncode=0, stdout=event_stream(reply), stderr="")
    monkeypatch.setattr(visual.subprocess, "run", run)
    result = actor.decide(observation)
    assert result.metadata["manual_sha256"] == identity["manual_sha256"]
    assert actor.instruction_identity() == identity


@pytest.mark.parametrize("item_type", ["command_execution", "file_change", "mcp_tool_call", "web_search", "tool_call", "future_item"])
def test_even_successful_final_json_is_rejected_after_any_tool_use(monkeypatch, observation, executable, item_type):
    reply = json.dumps(answer())

    def run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text(reply)
        return SimpleNamespace(returncode=0, stderr="", stdout=event_stream(reply, [
            {"type": "item.started", "item": {"id": "bad", "type": item_type}}]))

    monkeypatch.setattr(visual.subprocess, "run", run)
    with pytest.raises(visual.VisualProtocolError, match="tool use or unknown") as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    assert error.value.metadata["cli_exit_code"] == 0
    assert error.value.metadata["attempts"] == 1


@pytest.mark.parametrize("failure", ["missing_answer", "mismatched_answer", "image_mutated", "nonzero", "timeout", "no_events"])
def test_infrastructure_failures_never_fall_back_to_text_or_retry(monkeypatch, observation, executable, failure):
    calls = []
    reply = json.dumps(answer())

    def run(command, **kwargs):
        calls.append(command)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 3)
        if failure != "missing_answer":
            Path(command[command.index("-o") + 1]).write_text(reply)
        if failure == "image_mutated":
            Path(command[command.index("--image") + 1]).write_bytes(png(200, 100))
        return SimpleNamespace(returncode=2 if failure == "nonzero" else 0,
                               stdout="" if failure == "no_events" else event_stream("{}" if failure == "mismatched_answer" else reply),
                               stderr="transport diagnostic details")

    monkeypatch.setattr(visual.subprocess, "run", run)
    with pytest.raises(visual.VisualProtocolError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    assert len(calls) == 1
    assert "transport diagnostic details" not in str(error.value)
    if failure != "timeout":
        assert "transport diagnostic details" in error.value.metadata["cli_failure"]["stderr"]["text"]


def test_missing_or_corrupt_image_fails_before_model_is_called(monkeypatch, observation, executable):
    monkeypatch.setattr(visual.subprocess, "run", lambda *a, **kw: pytest.fail("model must not be called"))
    observation.image_path.write_bytes(b"not an image")
    with pytest.raises(visual.VisualProtocolError, match="PNG"):
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    observation.image_path.unlink()
    with pytest.raises(visual.VisualProtocolError, match="missing"):
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)


@pytest.mark.parametrize("mutate", [lambda d: d[:-2], lambda d: d + b"extra", lambda d: d[:20] + b"!" + d[21:]])
def test_png_integrity_is_validated(observation, mutate):
    observation.image_path.write_bytes(mutate(observation.image_path.read_bytes()))
    with pytest.raises(visual.VisualProtocolError):
        visual.read_screenshot(observation.image_path)


@pytest.mark.parametrize("bad", [
    answer(actions=[{"type": "fire", "weapon": 1}]),
    answer(actions=[{"type": "click", "x": 320, "y": 0, "button": "left", "modifiers": []}]),
    answer(actions=[{"type": "click", "x": True, "y": 0, "button": "left", "modifiers": []}]),
    answer(actions=[{"type": "click", "x": 1, "y": 1, "button": "left", "modifiers": [], "native_room": 3}]),
    answer(actions=[{"type": "drag", "x": 0, "y": 0, "to_x": -1, "to_y": 1, "button": "left", "modifiers": []}]),
    answer(actions=[{"type": "key", "key": "f12", "modifiers": []}]),
    answer(actions=[{"type": "key", "key": "a", "modifiers": ["shift", "shift"]}]),
    answer(actions=[{"type": "key", "key": "a", "modifiers": ["alt"]}]),
    answer(actions=[{"type": "click", "x": 1, "y": 1, "button": "left", "modifiers": ["alt"]}]),
    answer(actions=[{"type": "move", "x": 1, "y": 1}] * 5),
    answer(advance_frames=601), answer(advance_frames=False), answer(memory="x" * 1201),
    {**answer(), "hidden_state": {}},
])
def test_invalid_actions_and_extra_fields_are_rejected(bad):
    with pytest.raises(visual.VisualProtocolError):
        visual.parse_decision(json.dumps(bad), 320, 180)


@pytest.mark.parametrize("bad", ["```json\n{}\n```", '{"actions":[],"actions":[]}', '{"advance_frames":NaN}', "null"])
def test_json_is_not_salvaged_from_ambiguous_or_non_json_responses(bad):
    with pytest.raises(visual.VisualProtocolError):
        visual.parse_decision(bad, 320, 180)


def test_history_and_hybrid_hud_cannot_smuggle_engine_state(observation):
    _, image = visual.read_screenshot(observation.image_path)
    for kwargs in ({"mode": "hybrid", "visible_hud": {"enemy_rooms": [{"health": 1}]}},
                   {"mode": "image", "visible_hud": {"fuel": 3}},
                   {"history": [{"native_state": {"secret": "x"}}]},
                   {"mode": "hybrid", "visible_hud": {"fuel": {"hidden": "x"}}}):
        obs = visual.VisualObservation(observation.image_path, "frame", **kwargs)
        with pytest.raises(visual.VisualProtocolError):
            visual.build_visual_prompt(obs, image, "manual")
    obs = visual.VisualObservation(observation.image_path, "frame", mode="hybrid",
                                   visible_hud={"fuel": 3, "hull_current": 22, "paused": True},
                                   history=[{"actions": [], "advance_frames": 30, "actual_advance_frames": 12,
                                             "intent": "Wait for charge", "delivery": "interrupted"}] * 12,
                                   memory="Keep fuel for the exit")
    payload = json.loads(visual.build_visual_prompt(obs, image, "manual").split("DECISION INPUT\n")[1])
    assert payload["visible_hud"] == obs.visible_hud
    assert len(payload["recent_inputs"]) == 8
    assert payload["your_memory"] == obs.memory


def test_all_supported_primitive_shapes_and_modifier_combinations():
    actions = [{"type": "click", "x": 319, "y": 179, "button": "right", "modifiers": ["shift", "ctrl"]},
               {"type": "move", "x": 0, "y": 0},
               {"type": "drag", "x": 2, "y": 3, "to_x": 9, "to_y": 8, "button": "left", "modifiers": []},
               {"type": "key", "key": "escape", "modifiers": []}]
    assert visual.parse_decision(json.dumps(answer(actions=actions, advance_frames=600)), 320, 180).actions == actions


@pytest.mark.parametrize("events", [
    [], [{"type": "turn.started"}], [{"type": "turn.completed"}],
    [{"type": "turn.failed", "error": {"message": "rate limited"}}],
    [{"type": "turn.started"}, {"type": "turn.started"}],
    [{"type": "turn.started"}, {"type": "turn.completed"}],
])
def test_incomplete_or_failed_audit_stream_is_rejected(events):
    with pytest.raises(visual.VisualProtocolError):
        visual.audit_codex_events("\n".join(json.dumps(e) for e in events))


def test_task_is_bounded_and_present_in_decision_prompt(monkeypatch, observation, executable):
    task = "Buy one unit of fuel, close the store, and jump."
    reply = json.dumps(answer())

    def run(command, **kwargs):
        assert "CURRENT TASK\n" + task in kwargs["input"].decode("utf-8")
        Path(command[command.index("-o") + 1]).write_text(reply)
        return SimpleNamespace(returncode=0, stderr="", stdout=event_stream(reply))

    monkeypatch.setattr(visual.subprocess, "run", run)
    assert visual.CodexVisualAgent(task=task, codex_bin=executable).decide(observation).intent == "Close the store"
    with pytest.raises(visual.VisualProtocolError):
        visual.CodexVisualAgent(task="x" * 1001)
    with pytest.raises(visual.VisualProtocolError):
        visual.CodexVisualAgent(task="")


@pytest.mark.parametrize("kind", ["unsupported", "error", "turn_failed", "tool", "nonzero", "malformed", "invalid_answer", "invalid_utf8", "timeout"])
def test_rejected_cli_retains_original_output_after_staging_cleanup(monkeypatch, observation, executable, kind):
    import base64
    import hashlib
    captured = {}
    reply = json.dumps(answer() if kind != "invalid_answer" else {"invalid": True})
    stdout = event_stream(reply).encode()
    if kind in ("unsupported", "error"):
        stdout = b'{"type":"turn.started"}\r\n' + json.dumps({"type": "error" if kind == "error" else "unknown.event", "message": "diagnostic detail"}).encode() + b'\r\n'
    elif kind == "turn_failed":
        stdout = b'{"type":"turn.started"}\n{"type":"turn.failed","error":{"message":"failed"}}\n'
    elif kind == "tool":
        stdout = b'{"type":"turn.started"}\n{"type":"item.started","item":{"type":"command_execution"}}\n'
    elif kind == "invalid_utf8":
        stdout = b'invalid UTF8\xff'
    elif kind == "malformed":
        stdout = b'{not JSON}\n'
    elif kind == "timeout":
        stdout = b'{"type":"turn.started"}\npartial\xff'
    stderr = b'CLI diagnostic\r\n\xff'
    def run(command, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        captured["calls"] = captured.get("calls", 0) + 1
        if kind == "timeout":
            raise subprocess.TimeoutExpired(command, 3, output=stdout, stderr=stderr)
        Path(command[command.index("-o") + 1]).write_text(reply)
        return SimpleNamespace(returncode=2 if kind == "nonzero" else 0, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(visual.subprocess, "run", run)
    with pytest.raises(visual.VisualProtocolError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    assert captured["calls"] == 1 and not Path(captured["cwd"]).exists()
    failure = error.value.metadata["cli_failure"]
    for name, raw in (("stdout", stdout), ("stderr", stderr)):
        evidence = failure[name]
        assert base64.b64decode(evidence["base64"]) == raw
        assert evidence["sha256"] == hashlib.sha256(raw).hexdigest()
        assert evidence["bytes"] == evidence["retained_bytes"] == len(raw)
        assert evidence["truncated"] is False
    assert failure["kind"] == {"unsupported": "unsupported_event", "error": "unsupported_event", "turn_failed": "unsupported_event", "tool": "unsupported_activity", "invalid_utf8": "invalid_utf8", "nonzero": "nonzero_exit", "malformed": "malformed_json", "invalid_answer": "invalid_final_answer", "timeout": "timeout"}[kind]
    if kind in ("unsupported", "error"):
        assert failure["event_index"] == 1
        assert failure["event_type"] == ("error" if kind == "error" else "unknown.event")
    if kind == "timeout":
        assert failure["partial"] is True
        assert failure["stdout"]["utf8_valid"] is False


def test_rejected_oversized_cli_evidence_is_bounded(monkeypatch, observation, executable):
    import base64
    import hashlib
    stdout = b'x' * (2 * 1024 * 1024 + 9)
    stderr = b'y' * (64 * 1024 + 7)
    monkeypatch.setattr(visual.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr))
    with pytest.raises(visual.VisualProtocolError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    failure = error.value.metadata["cli_failure"]
    for name, raw, cap in (("stdout", stdout, 2 * 1024 * 1024), ("stderr", stderr, 64 * 1024)):
        e = failure[name]
        assert e["bytes"] == len(raw) and e["retained_bytes"] == cap and e["truncated"] is True
        assert e["sha256"] == hashlib.sha256(raw).hexdigest()
        assert base64.b64decode(e["base64"]) == raw[:cap]


def test_successful_byte_stream_preserves_decision_without_failure_metadata(monkeypatch, observation, executable):
    reply = json.dumps(answer())
    def run(command, **kwargs):
        assert isinstance(kwargs["input"], bytes) and "text" not in kwargs
        Path(command[command.index("-o") + 1]).write_text(reply)
        return SimpleNamespace(returncode=0, stdout=event_stream(reply).encode(), stderr=b'nonfatal notice')
    monkeypatch.setattr(visual.subprocess, "run", run)
    result = visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    assert result.as_dict() == answer()
    assert "cli_failure" not in result.metadata


def test_timeout_without_output_records_unavailable_not_empty(monkeypatch, observation, executable):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 3)
    monkeypatch.setattr(visual.subprocess, "run", run)
    with pytest.raises(visual.VisualBackendError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    failure = error.value.metadata["cli_failure"]
    assert failure["kind"] == "timeout" and failure["partial"] is True
    assert failure["stdout"]["available"] is False and failure["stderr"]["available"] is False
    assert error.value.metadata["attempts"] == 1


@pytest.mark.parametrize("invalid_answer", [False, True])
def test_failure_evidence_redacts_credentials_in_text_base64_and_events(monkeypatch, observation, executable, invalid_answer):
    import base64
    import hashlib
    tokens = ["sk-testCredential123", "apikey_private456", "bearerSecret789", "assignedSecret321"]
    detail = "diagnostic E42 Authorization: Bearer bearerSecret789 api_key=assignedSecret321 sk-testCredential123 apikey_private456"
    reply = json.dumps({"invalid": detail})
    stdout = event_stream(reply).encode() if invalid_answer else json.dumps({"type": "error", "message": detail}).encode()
    stderr = detail.encode()
    def run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text(reply)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(visual.subprocess, "run", run)
    with pytest.raises(visual.VisualProtocolError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    metadata = error.value.metadata
    for token in tokens:
        assert token not in json.dumps(metadata)
    for name, raw in (("stdout", stdout), ("stderr", stderr)):
        e = metadata["cli_failure"][name]
        retained = base64.b64decode(e["base64"])
        assert all(token.encode() not in retained for token in tokens)
        assert b"diagnostic E42" in retained
        assert e["redacted"] is True and e["redaction_count"] == 4
        assert e["sha256"] == hashlib.sha256(raw).hexdigest()
        assert e["retained_sha256"] == hashlib.sha256(retained).hexdigest()
        assert e["hash_scope"] == "original_bytes"
        assert e["retained_hash_scope"] == "redacted_retained_bytes"


@pytest.mark.parametrize("case", ["json_key", "event_type", "item_type"])
def test_failure_context_cannot_bypass_credential_redaction_or_bounds(monkeypatch, observation, executable, case):
    import base64
    secret = "privateAssignedCredential"
    reply = json.dumps({"api_key": secret})
    if case == "json_key":
        stdout = event_stream(reply).encode()
    else:
        value = "sk-privateCredential " + "x" * 4096
        event = {"type": value} if case == "event_type" else {"type": "item.started", "item": {"type": value}}
        stdout = (json.dumps({"type": "turn.started"}) + "\n" + json.dumps(event)).encode()
    def run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text(reply)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=b'')
    monkeypatch.setattr(visual.subprocess, "run", run)
    with pytest.raises(visual.VisualProtocolError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    metadata = error.value.metadata
    assert "events" not in metadata
    assert secret not in json.dumps(metadata)
    assert "sk-privateCredential" not in json.dumps(metadata)
    evidence = metadata["cli_failure"]
    assert secret.encode() not in base64.b64decode(evidence["stdout"]["base64"])
    for field in ("event_type", "item_type"):
        if field in evidence:
            assert isinstance(evidence[field], str) and len(evidence[field].encode()) <= 256


def test_failure_error_diagnostic_is_redacted_and_bounded():
    result = visual._cli_failure("request_failure", error=ValueError("Bearer privateToken " + "x" * 5000))
    assert "privateToken" not in json.dumps(result)
    assert len(result["error"].encode()) <= 1024
    assert result["error"].startswith("Bearer [REDACTED]")


def test_non_scalar_event_type_still_rejects_without_untrusted_context(monkeypatch, observation, executable):
    stdout = b'{"type":{"api_key":"privateToken"}}'
    monkeypatch.setattr(visual.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=stdout, stderr=b''))
    with pytest.raises(visual.VisualProtocolError) as error:
        visual.CodexVisualAgent(codex_bin=executable).decide(observation)
    assert error.value.metadata["cli_failure"]["event_type"] == "<dict>"
    assert "privateToken" not in json.dumps(error.value.metadata)
