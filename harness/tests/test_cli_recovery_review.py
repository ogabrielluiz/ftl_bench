"""Independent offline checks for narrow CLI transport recovery evidence."""
import base64
from copy import deepcopy
import hashlib
import json

import pytest
import visual_agent as actor
import visual_reporting as reporter
from test_visual_reporting import recovered_run, save_rows, write


@pytest.mark.parametrize("boundary", ["started", "updated", "completed"])
def test_reconnect_after_any_agent_message_activity_is_rejected(boundary):
    events = [
        {"type": "thread.started"}, {"type": "turn.started"},
        {"type": "item." + boundary, "item": {"type": "agent_message", "text": "partial"}},
        {"type": "error", "message": "Reconnecting... 2/5 (stream disconnected before completion: websocket closed by server before response.completed)"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "final"}},
        {"type": "turn.completed", "usage": {"input_tokens": 1}},
    ]
    with pytest.raises(actor.VisualProtocolError):
        actor.audit_codex_events("\n".join(json.dumps(event) for event in events))


@pytest.mark.parametrize("damage", ["stderr_text", "stderr_bytes", "stdout_count", "stdout_truncated", "unknown_internal_usage"])
def test_saved_recovery_byte_and_scope_corruption_withholds_completion(tmp_path, damage):
    directory = tmp_path / damage
    rows = recovered_run(directory)
    recovery = rows[2]["model"]["cli_recovery"]
    if damage == "stderr_text":
        recovery["stderr"]["text"] += "altered"
    elif damage == "stderr_bytes":
        recovery["stderr"]["base64"] = base64.b64encode(b"different").decode()
    elif damage == "stdout_count":
        recovery["stdout"]["retained_bytes"] += 1
    elif damage == "stdout_truncated":
        recovery["stdout"]["truncated"] = True
    else:
        recovery["aborted_sampling_usage"] = {"input_tokens": 0}
    save_rows(directory, rows)
    assert not reporter.audit_visual_run(directory, verify_live_saves=False)["complete"]


def test_manifest_cannot_claim_legacy_policy_for_modern_saved_decision(tmp_path):
    directory = tmp_path / "policy"
    recovered_run(directory)
    manifest = json.loads((directory / "run.json").read_text())
    manifest["actor_identity"]["cli_event_policy"] = actor.LEGACY_CLI_EVENT_POLICY
    write(directory / "run.json", manifest)
    assert not reporter.audit_visual_run(directory, verify_live_saves=False)["complete"]


def test_nested_combined_usage_keeps_aborted_internal_requests_unknown(tmp_path):
    directory = tmp_path / "usage"
    recovered_run(directory)
    recovered = reporter.audit_visual_run(directory, verify_live_saves=False)["model_calls"]
    ordinary = reporter.summarize_model_calls([{"model": {"usage": {"input_tokens": 7}}}])
    combined = reporter._combine_call_summaries([reporter._combine_call_summaries([recovered, ordinary]), ordinary])
    assert combined["usage"]["completed_turn_totals"]["input_tokens"] == 115
    assert combined["usage"]["complete_totals"]["input_tokens"] is None
    assert combined["transport_recovery"]["recorded_calls"] == 1
@pytest.mark.parametrize("redacted", [None, "false", True])
def test_invalid_redaction_claim_cannot_bypass_original_stdout_identity(tmp_path, redacted):
    directory = tmp_path / str(redacted)
    rows = recovered_run(directory)
    model = rows[2]["model"]
    stdout = model["cli_recovery"]["stdout"]
    stdout["redacted"] = redacted
    # No bytes were actually redacted; the zero-count retained evidence must
    # not authorize an unrelated claimed original stream hash.
    stdout["sha256"] = "0" * 64
    model["event_stream_sha256"] = "0" * 64
    save_rows(directory, rows)
    assert not reporter.audit_visual_run(directory, verify_live_saves=False)["complete"]

def test_genuine_redacted_stderr_retains_scoped_original_hash(tmp_path):
    directory = tmp_path / "redacted"
    rows = recovered_run(directory)
    model = rows[2]["model"]
    raw = b"Authorization: Bearer syntheticCredentialForOfflineTest"
    stderr = actor._cli_failure("recovered_reconnect", stderr=raw)["stderr"]
    assert stderr["redacted"] is True and stderr["redaction_count"] == 1
    assert stderr["sha256"] == hashlib.sha256(raw).hexdigest()
    assert stderr["sha256"] != stderr["retained_sha256"]
    assert b"syntheticCredentialForOfflineTest" not in base64.b64decode(stderr["base64"])
    model["cli_recovery"]["stderr"] = stderr
    save_rows(directory, rows)
    assert reporter.audit_visual_run(directory, verify_live_saves=False)["complete"]