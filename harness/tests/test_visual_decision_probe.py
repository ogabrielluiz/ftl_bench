"""Provider HTTP fixtures exercise complete actor, audit, and command routing."""
import json
from types import SimpleNamespace

import pytest

import visual_decision_api as api
from visual_choice_agent import TypedVisualAgent, sha
from visual_decision_audit import audit_decision
from visual_decision_probe import main
from visual_agent import VisualObservation
from test_visual_agent import png
from test_visual_choice_agent import choose_point
from test_visual_decision_api import Reply, response


def provider(monkeypatch, backend, control="click:left:none", point=(319, 179)):
    sent = []
    def open_request(request, *, timeout):
        body = json.loads(request.data)
        sent.append(body)
        if backend == "jev":
            name, question = next(iter(body["questions"].items()))
            options = question["criteria"]
        else:
            question = body["questions"][0]
            name = question["name"]
            options = {item["value"]: item["description"] for item in question["choices"]}
        choice = control if name == "control" else "120" if name == "advance" else choose_point(options, point)
        probabilities = {key: float(key == choice) for key in options}
        return Reply(json.dumps(response(backend, choice, probabilities, name)).encode())
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-visual-probe-only")
    monkeypatch.setenv("OPENAI_API_KEY", "test-visual-probe-only")
    monkeypatch.setattr(api, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    return sent


def saved_decision(tmp_path, monkeypatch, backend):
    provider(monkeypatch, backend, control="key:f:shift")
    image = tmp_path / "input.png"
    image_bytes = png()
    image.write_bytes(image_bytes)
    agent = TypedVisualAgent(backend, audit_root=tmp_path / "api-decisions")
    decision = agent.decide(VisualObservation(image, "test"))
    directory = tmp_path / decision.metadata["artifact"]
    assert audit_decision(directory)["valid"] is True
    return directory, image_bytes


@pytest.mark.parametrize("backend", ["jev", "openai-decisions"])
def test_one_screenshot_command_archives_and_replays_actual_wire_chain(tmp_path, monkeypatch, backend):
    sent = provider(monkeypatch, backend)
    image = tmp_path / "input.png"
    image.write_bytes(png())
    output = tmp_path / "probe"
    main(["--backend", backend, "--image", str(image), "--output", str(output)])
    probe = json.loads((output / "probe.json").read_text())
    assert probe["status"] == "completed" and probe["audit"]["valid"] is True
    assert probe["model_comparison"] is False
    assert probe["decision"]["actions"] == [{"type": "click", "button": "left", "modifiers": [], "x": 319, "y": 179}]
    assert len(sent) == probe["audit"]["http_requests"] == 5
    for path in output.rglob("*.json"):
        assert "test-visual-probe-only" not in path.read_text()
    assert not (output / "save-backup").exists()
    assert not (output / "run.json").exists()


@pytest.mark.parametrize("tamper", ["action", "context", "probabilities", "image"])
def test_saved_audit_rejects_changed_evidence(tmp_path, monkeypatch, tamper):
    directory, image_bytes = saved_decision(tmp_path, monkeypatch, "jev")
    if tamper == "action":
        path = directory / "decision.json"
        value = json.loads(path.read_text())
        value["actions"][0]["key"] = "g"
        path.write_text(json.dumps(value))
    elif tamper == "image":
        (directory / "screenshot.png").write_bytes(png(31, 18))
    elif tamper == "context":
        path = directory / "01-control/request.json"
        value = json.loads(path.read_text())
        value["body"]["state"]["context"] += " hidden native state"
        wire = api._wire_body(value, image_bytes)
        value.update(wire_sha256=sha(wire), wire_bytes=len(wire))
        path.write_text(json.dumps(value))
    else:
        path = directory / "01-control/response.json"
        value = json.loads(path.read_text())
        value["answers"]["control"]["probabilities"]["wait"] = 1
        path.write_text(json.dumps(value))
    assert audit_decision(directory)["valid"] is False


@pytest.mark.parametrize("backend,expected_error", [
    ("jev", "Unexpected Jev"),
    ("openai-decisions", "Unexpected Decisions"),
])
def test_saved_audit_rejects_nested_native_fields_even_with_matching_wire_hash(tmp_path, monkeypatch, backend, expected_error):
    directory, image_bytes = saved_decision(tmp_path, monkeypatch, backend)
    path = directory / "01-control/request.json"
    request = json.loads(path.read_text())
    body = request["body"]
    image_part = (body["assets"][body["state"]["screenshot"]] if backend == "jev"
                  else body["input"][0]["content"][1])
    image_part["hidden_native_state"] = {"world_updates": 1042}
    wire = api._wire_body(request, image_bytes)
    request.update(wire_sha256=sha(wire), wire_bytes=len(wire))
    path.write_text(json.dumps(request))
    assert api.reconstruct_request(request, image_bytes) == wire
    result = audit_decision(directory)
    assert result["valid"] is False and expected_error in result["reason"]


@pytest.mark.parametrize("field,value,expected_error", [
    ("http_status", 503, "Stage was not a successful HTTP response"),
    ("client_request_id", "unbound-client-id", "HTTP request identity is missing or reused"),
])
def test_saved_audit_joins_http_success_and_request_identity(tmp_path, monkeypatch, field, value, expected_error):
    directory, _ = saved_decision(tmp_path, monkeypatch, "openai-decisions")
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["api_calls"][0][field] = value
    metadata_path.write_text(json.dumps(metadata))
    call_path = directory / "01-control/call.json"
    call = json.loads(call_path.read_text())
    call[field] = value
    call_path.write_text(json.dumps(call))
    result = audit_decision(directory)
    assert result["valid"] is False and expected_error in result["reason"]


def test_saved_audit_returns_invalid_for_malformed_png(tmp_path, monkeypatch):
    directory, _ = saved_decision(tmp_path, monkeypatch, "jev")
    (directory / "screenshot.png").write_bytes(b"not a PNG")
    result = audit_decision(directory)
    assert result["valid"] is False and "PNG" in result["reason"]


@pytest.mark.parametrize("prefix", ['{"decision_complete":false,', '{"unexpected_field":NaN,', '{"unexpected_field":1e999,'])
def test_saved_audit_rejects_ambiguous_metadata_json(tmp_path, monkeypatch, prefix):
    directory, _ = saved_decision(tmp_path, monkeypatch, "jev")
    metadata_path = directory / "metadata.json"
    text = metadata_path.read_text()
    metadata_path.write_text(prefix + text[1:])
    assert audit_decision(directory)["valid"] is False


def test_saved_audit_rejects_linked_response_with_matching_bytes(tmp_path, monkeypatch):
    directory, _ = saved_decision(tmp_path, monkeypatch, "jev")
    response_path = directory / "01-control/response.json"
    external = tmp_path / "response.json"
    response_path.replace(external)
    try:
        response_path.symlink_to(external)
    except OSError as error:
        pytest.skip(f"Creating a file symlink is unavailable ({error})")
    result = audit_decision(directory)
    assert result["valid"] is False and "Linked" in result["reason"]


def test_saved_audit_rejects_oversized_response(tmp_path, monkeypatch):
    directory, _ = saved_decision(tmp_path, monkeypatch, "jev")
    with (directory / "01-control/response.json").open("ab") as stream:
        stream.truncate(1024 * 1024 + 1)
    result = audit_decision(directory)
    assert result["valid"] is False and "Oversized" in result["reason"]


def test_cli_routes_probe_without_game_dependencies(tmp_path, monkeypatch):
    from ftl_bench.cli import main as cli_main
    provider(monkeypatch, "openai-decisions", control="wait")
    image = tmp_path / "input.png"
    image.write_bytes(png())
    output = tmp_path / "probe"
    cli_main(["visual-decide", "--backend", "openai-decisions", "--image", str(image), "--output", str(output)])
    assert json.loads((output / "probe.json").read_text())["audit"]["valid"] is True
