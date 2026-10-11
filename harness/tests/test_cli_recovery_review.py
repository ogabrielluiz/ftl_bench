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

def challenge_policy_layout(directory):
    """Actual challenge meta precedes actor; manifest/report carry its identity."""
    rows = recovered_run(directory)
    identity = rows[0]["meta"].pop("actor_identity")
    manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    manifest["experiment"]["actor_identity"] = deepcopy(identity)
    report = json.loads((directory / "visual-report.json").read_text(encoding="utf-8"))
    report["experiment"] = deepcopy(manifest["experiment"])
    write(directory / "run.json", manifest)
    write(directory / "visual-report.json", report)
    save_rows(directory, rows)
    return rows


def test_actual_challenge_optional_meta_identity_absent_is_valid(tmp_path):
    directory = tmp_path / "actual-layout"
    challenge_policy_layout(directory)
    result = reporter.audit_visual_run(directory, verify_live_saves=False)
    assert result["complete"], result["issues"]
    assert result["cli_event_policies"] == [actor.CLI_EVENT_POLICY]


@pytest.mark.parametrize("carrier", ["meta", "meta_experiment", "manifest", "manifest_experiment", "report_experiment"])
@pytest.mark.parametrize("policy", [actor.LEGACY_CLI_EVENT_POLICY, "future", None])
def test_all_present_actor_policy_carriers_must_match(tmp_path, carrier, policy):
    directory = tmp_path / (carrier + str(policy))
    rows = challenge_policy_layout(directory)
    manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    report = json.loads((directory / "visual-report.json").read_text(encoding="utf-8"))
    if carrier == "meta":
        rows[0]["meta"]["actor_identity"] = {"cli_event_policy": policy}
    elif carrier == "meta_experiment":
        rows[0]["meta"]["experiment"]["actor_identity"] = {"cli_event_policy": policy}
    elif carrier == "manifest":
        manifest["actor_identity"]["cli_event_policy"] = policy
    elif carrier == "manifest_experiment":
        manifest["experiment"]["actor_identity"]["cli_event_policy"] = policy
    else:
        report["experiment"]["actor_identity"]["cli_event_policy"] = policy
    write(directory / "run.json", manifest)
    write(directory / "visual-report.json", report)
    save_rows(directory, rows)
    result = reporter.audit_visual_run(directory, verify_live_saves=False)
    assert not result["complete"]
    assert any("CLI event policy" in issue["error"] for issue in result["issues"])


def test_missing_manifest_policy_cannot_be_supplied_by_optional_carrier(tmp_path):
    directory = tmp_path / "manifest-missing"
    challenge_policy_layout(directory)
    manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    manifest.pop("actor_identity")
    write(directory / "run.json", manifest)
    result = reporter.audit_visual_run(directory, verify_live_saves=False)
    assert not result["complete"]
    assert any("CLI event policy" in issue["error"] for issue in result["issues"])


def test_challenge_policy_join_preserves_multiple_step_history(tmp_path):
    directory = tmp_path / "two-steps"
    rows = challenge_policy_layout(directory)
    first = rows[2]
    second = deepcopy(first)
    second["i"] = 2
    second["pre_obs"] = deepcopy(first["obs"])
    second["visual"]["before"] = deepcopy(first["visual"]["after"])
    image_bytes = (directory / "screens/1.png").read_bytes()
    (directory / "screens/2.png").write_bytes(image_bytes)
    for key, value in (("path", "screens/2.png"), ("frame_id", "2"), ("capture_id", "2"),
                       ("action_seq", 2), ("world_updates", "40"), ("simulated_updates", "40")):
        second["visual"]["after"][key] = value
        if key not in ("path",):
            second["obs"]["visual"][key] = value
    second["obs"]["last_action_seq"] = 2
    second["obs"]["capabilities"].update(world_updates="40", simulated_updates="40")
    history = [{"actions": [], "advance_frames": 20, "actual_advance_frames": 20,
                "intent": "Wait", "delivery": "delivered"}]
    observation = actor.VisualObservation(directory / "screens/1.png", "1", history=history)
    _, image = actor.read_screenshot(observation.image_path)
    instructions = first["model"]["prompt"].rsplit("\n\nDECISION INPUT\n", 1)[0]
    prompt = actor.build_visual_prompt(observation, image, instructions)
    second["model"].update(frame_id="1", image=image, prompt=prompt,
                            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
    rows.insert(3, second)
    rows[-1]["decisions"] = 2
    save_rows(directory, rows)
    report = json.loads((directory / "visual-report.json").read_text(encoding="utf-8"))
    report["decisions"] = 2
    write(directory / "visual-report.json", report)
    result = reporter.audit_visual_run(directory, verify_live_saves=False)
    assert result["complete"], result["issues"]
    assert result["checked_decisions"] == 2


def test_present_legacy_meta_identity_does_not_silently_inherit_modern_policy(tmp_path):
    directory = tmp_path / "legacy-declaration"
    rows = challenge_policy_layout(directory)
    rows[0]["meta"]["actor_identity"] = {"task": rows[2]["model"]["task"]}
    save_rows(directory, rows)
    result = reporter.audit_visual_run(directory, verify_live_saves=False)
    assert not result["complete"]
    assert any("CLI event policy" in issue["error"] for issue in result["issues"])


def test_provisional_challenge_audit_does_not_require_terminal_report(tmp_path):
    directory = tmp_path / "provisional"
    rows = challenge_policy_layout(directory)
    save_rows(directory, rows[:-1])
    (directory / "visual-report.json").unlink()
    result = reporter.audit_visual_run(directory, require_terminal=False, verify_live_saves=False)
    assert result["status"] == "provisional"
    assert result["issues"] == []
    assert result["checked_decisions"] == 1
    terminal = reporter.audit_visual_run(directory, verify_live_saves=False)
    assert not terminal["complete"] and terminal["issues"]
