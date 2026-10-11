"""Saved-run auditing and paired comparison, with no game/model processes."""
from copy import deepcopy
import hashlib
import json

import pytest

import visual_agent as agent
import visual_reporting as reporting
from test_visual_agent import png, event_stream


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def saved_run(directory, *, model="gpt-6.1-sol", mode="image", reason="fixture_goal_observed",
              task="Win this combat.", repetition=1, clock_version=2):
    directory.mkdir(parents=True)
    (directory / "screens").mkdir()
    (directory / "save-backup").mkdir()
    data = png(320, 180)
    sha = hashlib.sha256(data).hexdigest()
    def frame(index):
        path = directory / "screens" / f"{index}.png"
        path.write_bytes(data)
        ref = {"path": f"screens/{index}.png", "sha256": sha, "width": 320, "height": 180,
               "frame_id": str(index), "capture_id": str(index), "action_seq": index,
               "coordinate_space": "screen_pixels", "world_updates": str(index * 20),
               "external_input_generation": "0", "visual_clock_version": clock_version}
        if clock_version == 2:
            ref.update(fixed_step_numerator=1, fixed_step_denominator=60, simulated_updates=str(index * 20))
        visual = {k: v for k, v in ref.items() if k not in ("path", "sha256")}
        visual.update(paused=True, visual_io_version=1, external_input_detected=False,
                      requested_frames=20, actual_frames=20, input_feedback=[])
        obs = {"paused": True, "game_started": True, "last_action_seq": index, "visual": visual,
               "capabilities": {"visual_clock_version": clock_version, "visual_io_version": 1,
                                "external_input_guard": True, "world_updates": str(index * 20)}}
        if clock_version == 2:
            obs["capabilities"].update(fixed_step_numerator=1, fixed_step_denominator=60, simulated_updates=str(index * 20))
        return ref, obs
    before, pre = frame(0)
    after, post = frame(1)
    actor = agent.CodexVisualAgent(model=model, task=task)
    identity = actor.instruction_identity()
    production, fixture = b"production Lua", b"production Lua\nfixture"
    (directory / "production-bridge.lua").write_bytes(production)
    (directory / "fixture-bridge.lua").write_bytes(fixture)
    fixture_sha = hashlib.sha256(fixture).hexdigest()
    runtime = {"native_dll": {"sha256": "d" * 64}, "bridge_lua": {"sha256": fixture_sha},
               "codex_cli": {"sha256": "c" * 64}, "native_build": {
                   "matches_installed_dll": True, "patch_sha256": "p" * 64, "source_commit": "commit",
                   "native_protocol": 5, "visual_clock_version": clock_version, "visual_io_version": 1}}
    if clock_version == 2:
        runtime["native_build"].update(fixed_step_numerator=1, fixed_step_denominator=60)
    budgets = {"decisions": 60, "wall_seconds": 1800, "idle_decisions": 8}
    signature = {"game_started": True}
    signature_sha = reporting.canonical_sha256(signature)
    experiment = {"protocol": "visual-challenges-v1", "scenario": "combat", "seed": 1,
                  "repetition": repetition, "task": task, "task_sha256": identity["task_sha256"],
                  "fixture_sha256": fixture_sha, "fixture_version": "1", "budgets": budgets,
                  "protocol_sha256": protocol()["protocol_sha256"], "hud_extractor_identity": {"reader": "h" * 64},
                  "prerequisites_verified": True, "initial_gameplay_sha256": signature_sha}
    meta = {"model": model, "observation_mode": mode, "codex_cli": runtime["codex_cli"],
            "reasoning_effort": "medium", "actor_identity": identity, "experiment": experiment,
            "production_bridge_sha256": hashlib.sha256(production).hexdigest()}
    observation = agent.VisualObservation(directory / "screens/0.png", "0", mode=mode,
                                          visible_hud={"paused": True} if mode == "hybrid" else {})
    _, image = agent.read_screenshot(observation.image_path)
    instructions = agent.PROMPT_PATH.read_text(encoding="utf-8") + "\n\nCURRENT TASK\n" + task
    prompt = agent.build_visual_prompt(observation, image, instructions)
    answer = {"actions": [], "advance_frames": 20, "intent": "Wait", "memory": ""}
    reply = json.dumps(answer)
    audit = agent.audit_codex_events(event_stream(reply))
    model_record = {"model": model, "provider": "codex", "mode": mode, "frame_id": "0", "reasoning_effort": "medium",
                    "image": image, "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    **identity, "schema": agent.decision_schema(320, 180), "attempts": 1,
                    "cli_exit_code": 0, "latency_seconds": 1.0,
                    **{k: v for k, v in audit.items() if k != "last_message"}}
    replay = {"observation_mode": mode, "before": before, "after": after, "inputs": [],
              "advance": {"requested_frames": 20, "actual_frames": 20}}
    if clock_version == 2:
        replay["advance"].update(visual_clock_version=2, fixed_step_numerator=1,
                                 fixed_step_denominator=60, simulated_seconds=20 / 60)
    if mode == "hybrid":
        from visible_hud import extract_visible_hud
        replay.update(visible_summary={"paused": True},
                      visible_summary_provenance=extract_visible_hud(directory / "screens/0.png")["provenance"])
    rows = [{"kind": "meta", "meta": meta}, {"kind": "reset", "obs": pre,
             "visual": {"before": before, "after": before}},
            {"kind": "step", "i": 1, "pre_obs": pre, "obs": post, "model": model_record,
             "visual": replay, "thought": "Wait", "actions": []},
            {"kind": "end", "status": "completed", "reason": reason, "decisions": 1}]
    save_rows(directory, rows)
    write(directory / "actor-start.json", {"first_image": before, "initial_observation": pre,
          "canonical_actor_reset": True, "gameplay_signature": signature,
          "gameplay_signature_sha256": signature_sha, "setup_proof": {"passed": True, "checks": {"setup": True}}})
    succeeded = reason == "fixture_goal_observed"
    write(directory / "validation.json", {"protocol": experiment["protocol"], "challenge": "combat",
          "repetition": repetition, "termination": reason, "setup": {"passed": True, "checks": {"setup": True}},
          "outcome": {"achieved": succeeded, "checks": {"goal": succeeded}},
          "save_restoration_verified": True, "production_source_unchanged": True,
          "cli_image_decisions_audited": True, "error": None, "failure_type": None})
    write(directory / "run.json", {**meta, "status": "completed", "reason": reason,
                                    "finished_at": 1, "save_restoration": "verified"})
    write(directory / "runtime-fingerprint.json", runtime)
    write(directory / "visual-report.json", {"status": "completed", "reason": reason, "decisions": 1,
          "budgets": budgets, "experiment": experiment, "experiment_sha256": reporting.canonical_sha256(experiment)})
    (directory / "save-backup/original.sav").write_bytes(b"original")
    digest = hashlib.sha256(b"original").hexdigest()
    write(directory / "save-backup/manifest.json", {"files": {"original.sav": digest}, "save_directory": "unused"})
    write(directory / "save-backup/restoration.json", {"verified": True, "files": {"original.sav": True}})
    return json.loads(json.dumps(rows))


def save_rows(directory, rows):
    (directory / "trajectory.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def protocol():
    value = {"models": ["gpt-6.1-sol", "gpt-6-luna"], "modes": ["image", "hybrid"],
             "challenges": ["combat"], "repetitions": 1,
             "reasoning_effort": "medium", "hud_extractor_identity": {"reader": "h" * 64},
             "source_files": {"dist/acceptance.json": "a" * 64},
             "native_acceptance": {"receipts": {"dist/acceptance.json": "a" * 64}, "runtime": {
                 "dll_sha256": "d" * 64, "patch_sha256": "p" * 64,
                 "visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60,
                 "production_bridge_sha256": hashlib.sha256(b"production Lua").hexdigest()}}}
    return {**value, "protocol_sha256": reporting.canonical_sha256(value)}


@pytest.mark.parametrize("mode", ["image", "hybrid"])
def test_audit_saved_success_does_not_read_live_saves(tmp_path, mode):
    directory = tmp_path / "trial"
    saved_run(directory, mode=mode)
    result = reporting.audit_visual_run(directory)
    assert result["complete"] and result["status"] == "passed", result["issues"]
    assert result["checked_unique_pngs"] == 2 and result["checked_decisions"] == 1
    assert result["terminal_cleanup"]["restored_files"] == 1
    assert not result["terminal_cleanup"]["live_saves_checked"]
    assert result["model_calls"]["usage"]["complete_totals"]["input_tokens"] == 101
    assert not reporting.audit_visual_run(directory, verify_live_saves=True)["complete"]
    assert result["simulation_timing"]["classification"] == "fixed_step_1_over_60_second"


def test_historical_v1_is_auditable_but_never_reinterpreted_as_fixed_step(tmp_path):
    directory = tmp_path / "old"
    saved_run(directory, clock_version=1)
    audit = reporting.audit_visual_run(directory)
    assert audit["complete"], audit["issues"]
    assert audit["simulation_timing"] == {"clock_versions": [1], "fixed_step_verified": False,
        "classification": "historical_update_count_without_fixed_duration", "declared_elapsed_seconds": None}
    trial = reporting.aggregate_visual_runs([directory], protocol())["trials"][0]
    assert not trial["eligible"] and "fixed_step_visual_clock_v2_required" in trial["exclusions"]


@pytest.mark.parametrize("damage", ["counter", "step", "replay_seconds", "provenance"])
def test_timing_contract_tampering_fails_audit(tmp_path, damage):
    directory = tmp_path / "bad-time"
    rows = saved_run(directory)
    if damage == "counter":
        rows[2]["obs"]["visual"]["simulated_updates"] = "19"
    elif damage == "step":
        rows[2]["obs"]["visual"]["fixed_step_denominator"] = 30
    elif damage == "replay_seconds":
        rows[2]["visual"]["advance"]["simulated_seconds"] = round(20 / 60, 3)
    else:
        value = json.loads((directory / "runtime-fingerprint.json").read_text())
        value["native_build"].pop("fixed_step_numerator")
        write(directory / "runtime-fingerprint.json", value)
    save_rows(directory, rows)
    assert not reporting.audit_visual_run(directory)["complete"]


@pytest.mark.parametrize("damage", ["png", "world", "tool", "hidden_hud", "history", "sequence", "usage", "terminal", "backup", "reasoning"])
def test_audit_rejects_independent_evidence_corruption(tmp_path, damage):
    directory = tmp_path / "trial"
    rows = saved_run(directory)
    step = rows[2]
    if damage == "png":
        (directory / "screens/0.png").write_bytes(png(200, 100))
    elif damage == "world":
        step["obs"]["visual"]["actual_frames"] = 19
    elif damage == "tool":
        step["model"]["events"][2]["item"]["type"] = "command_execution"
    elif damage in ("hidden_hud", "history"):
        instruction, raw = step["model"]["prompt"].rsplit("\n\nDECISION INPUT\n", 1)
        payload = json.loads(raw)
        payload["visible_hud" if damage == "hidden_hud" else "recent_inputs"] = {"secret": 1}
        step["model"]["prompt"] = instruction + "\n\nDECISION INPUT\n" + json.dumps(payload)
        step["model"]["prompt_sha256"] = hashlib.sha256(step["model"]["prompt"].encode()).hexdigest()
    elif damage == "sequence":
        step["visual"]["after"]["action_seq"] = 5
    elif damage == "usage":
        step["model"]["usage"]["input_tokens"] = 900
    elif damage == "terminal":
        rows[-1]["reason"] = "native_game_over"
    elif damage == "backup":
        (directory / "save-backup/original.sav").write_bytes(b"changed")
    elif damage == "reasoning":
        step["model"]["reasoning_effort"] = "high"
    save_rows(directory, rows)
    result = reporting.audit_visual_run(directory)
    assert not result["complete"] and result["issues"]


def test_malformed_trajectory_is_an_audit_failure_not_an_unhandled_exception(tmp_path):
    directory = tmp_path / "bad"
    saved_run(directory)
    (directory / "trajectory.jsonl").write_text('[]\n', encoding="utf-8")
    result = reporting.audit_visual_run(directory)
    assert result["status"] == "failed" and not result["complete"]


def test_usage_missing_is_unknown_and_cache_is_not_added_to_input():
    rows = [{"model": {"usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10}, "latency_seconds": 2}},
            {"model": {"usage": None}}]
    report = reporting.summarize_model_calls(rows)
    assert report["calls"] == 2
    assert report["usage"]["observed_totals"]["input_tokens"] == 100
    assert report["usage"]["complete_totals"]["input_tokens"] is None
    assert report["latency_seconds"]["observed_total"] == 2 and report["latency_seconds"]["total"] is None
    assert report["response_model_identity"]["status"] == "not_reported"


def test_complete_paired_challenges_include_native_losses_as_valid_outcomes(tmp_path):
    directories = []
    for model in protocol()["models"]:
        for mode in protocol()["modes"]:
            directory = tmp_path / model / mode
            saved_run(directory, model=model, mode=mode,
                      reason="native_game_over" if model == "gpt-6-luna" else "fixture_goal_observed")
            directories.append(directory)
    report = reporting.aggregate_visual_runs(directories, protocol())
    assert report["qualified_scoped_comparison"], [t["exclusions"] for t in report["trials"]]
    assert not report["valid_for_full_game_comparison"]
    luna = [c for c in report["conditions"] if c["model"] == "gpt-6-luna"]
    assert all(c["eligible_trials"] == 1 and c["outcomes"] == {"game_loss": 1} and c["task_success_rate"] == 0 for c in luna)


@pytest.mark.parametrize("change", ["task", "missing", "duplicate", "protocol_failure", "prerequisite", "initial_state", "acceptance"])
def test_unmatched_or_invalid_trials_never_qualify_a_pair(tmp_path, change):
    directories = []
    for model in protocol()["models"]:
        for mode in protocol()["modes"]:
            directory = tmp_path / model / mode
            saved_run(directory, model=model, mode=mode,
                      task="Different task" if change == "task" and mode == "hybrid" else "Win this combat.",
                      reason="visual_model_error" if change == "protocol_failure" else "fixture_goal_observed")
            directories.append(directory)
    if change == "missing":
        directories.pop()
    if change == "duplicate":
        directories.append(directories[0])
    if change == "prerequisite":
        path = directories[0] / "visual-report.json"
        report = json.loads(path.read_text())
        report["experiment"]["prerequisites_verified"] = False
        report["experiment_sha256"] = reporting.canonical_sha256(report["experiment"])
        write(path, report)
    if change == "initial_state":
        directory = directories[0]
        start = json.loads((directory / "actor-start.json").read_text())
        start["gameplay_signature"]["difficulty"] = 1
        start["initial_observation"]["difficulty"] = 1
        start["gameplay_signature_sha256"] = reporting.canonical_sha256(start["gameplay_signature"])
        write(directory / "actor-start.json", start)
        rows = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()]
        rows[1]["obs"]["difficulty"] = rows[2]["pre_obs"]["difficulty"] = 1
        save_rows(directory, rows)
        for filename in ("visual-report.json", "run.json"):
            record = json.loads((directory / filename).read_text())
            record["experiment"]["initial_gameplay_sha256"] = start["gameplay_signature_sha256"]
            record["experiment_sha256"] = reporting.canonical_sha256(record["experiment"])
            write(directory / filename, record)
    if change == "acceptance":
        (directories[0] / "production-bridge.lua").write_bytes(b"different production source")
    assert not reporting.aggregate_visual_runs(directories, protocol())["qualified_scoped_comparison"]


@pytest.mark.parametrize("damage", ["goal", "setup", "termination", "cleanup", "error"])
def test_positive_lifecycle_reason_cannot_substitute_for_native_validation_proof(tmp_path, damage):
    directory = tmp_path / "trial"
    saved_run(directory)
    proof = json.loads((directory / "validation.json").read_text())
    if damage == "goal":
        proof["outcome"] = {"achieved": False, "checks": {"goal": False}}
    elif damage == "setup":
        proof["setup"]["checks"]["setup"] = False
    elif damage == "termination":
        proof["termination"] = "decision_budget"
    elif damage == "cleanup":
        proof["production_source_unchanged"] = False
    else:
        proof["error"] = "fixture observer failed"
    write(directory / "validation.json", proof)
    trial = reporting.aggregate_visual_runs([directory], protocol())["trials"][0]
    assert not trial["eligible"] and any("challenge_evidence:" in reason for reason in trial["exclusions"])


def cancelled_saved_run(directory):
    rows = saved_run(directory)
    row = rows[2]
    row.update(kind="model_cancelled", obs=deepcopy(rows[1]["obs"]))
    row["visual"].update(after=None, inputs=[], advance={"requested_frames": 0, "actual_frames": None})
    evidence = {"observed_boundary": "after_actor_before_dispatch", "observed_at": "2026-10-10T01:00:00Z",
                "request": {"contract": "visual-cooperative-stop-v1", "request_id": "test-request",
                            "scope": "test-experiment", "initiator": "assistant:test", "reason": "review",
                            "requested_at": "2026-10-10T00:59:00Z", "requester_pid": 123}}
    rows[-1].update(status="interrupted", reason="cooperative_stop_requested", decisions=0, stop_request=evidence)
    for name in ("run.json", "visual-report.json"):
        value = json.loads((directory / name).read_text())
        value.update(status="interrupted", reason="cooperative_stop_requested", decisions=0, stop_request=evidence)
        write(directory / name, value)
    save_rows(directory, rows)
    return rows


def test_cancelled_model_audit_retains_call_and_proves_no_dispatch(tmp_path):
    directory = tmp_path / "cancelled"
    cancelled_saved_run(directory)
    audit = reporting.audit_visual_run(directory)
    assert audit["complete"], audit["issues"]
    assert audit["decisions"][0]["response_audited"] is True
    assert audit["decisions"][0]["dispatch_acknowledged"] is False


@pytest.mark.parametrize("damage", ["actions", "inputs", "after", "frames", "continuity", "reason", "status", "request", "boundary", "manifest"])
def test_cancelled_model_audit_rejects_dispatch_or_unbound_stop(tmp_path, damage):
    directory = tmp_path / "cancelled"
    rows = cancelled_saved_run(directory)
    row = rows[2]
    if damage == "actions": row["actions"] = [{"type": "key", "key": "SPACE"}]
    elif damage == "inputs": row["visual"]["inputs"] = [{"type": "key", "key": "SPACE"}]
    elif damage == "after": row["visual"]["after"] = row["visual"]["before"]
    elif damage == "frames": row["visual"]["advance"]["requested_frames"] = 1
    elif damage == "continuity": row["obs"]["last_action_seq"] = 3
    elif damage == "reason": rows[-1]["reason"] = "user_interrupted"
    elif damage == "status": rows[-1]["status"] = "completed"
    elif damage == "request": rows[-1]["stop_request"]["request"].pop("initiator")
    elif damage == "boundary": rows[-1]["stop_request"]["observed_boundary"] = "before_actor"
    elif damage == "manifest":
        value = json.loads((directory / "run.json").read_text())
        value["stop_request"]["request"]["initiator"] = "someone-else"
        write(directory / "run.json", value)
    save_rows(directory, rows)
    assert not reporting.audit_visual_run(directory)["complete"]


def versioned_saved_run(directory):
    rows = saved_run(directory)
    frozen = protocol()
    task = rows[0]["meta"]["experiment"]["task"]
    version = "combat-task-v1"
    frozen["task_versions"] = {"combat": version}
    frozen["tasks"] = {"combat": {"task": task, "task_version": version,
                                  "task_sha256": hashlib.sha256(task.encode()).hexdigest()}}
    frozen["protocol_sha256"] = reporting.canonical_sha256({k: v for k, v in frozen.items() if k != "protocol_sha256"})
    meta = rows[0]["meta"]
    meta["task_version"] = version
    meta["actor_identity"]["task_version"] = version
    meta["experiment"].update(task_version=version, protocol_sha256=frozen["protocol_sha256"])
    for name in ("run.json", "visual-report.json"):
        value = json.loads((directory / name).read_text())
        value["experiment"] = deepcopy(meta["experiment"])
        if name == "run.json":
            value["task_version"] = version
            value["actor_identity"]["task_version"] = version
        else:
            value["experiment_sha256"] = reporting.canonical_sha256(value["experiment"])
        write(directory / name, value)
    save_rows(directory, rows)
    return frozen, rows


def test_prospective_task_version_joins_frozen_protocol_and_trial(tmp_path):
    directory = tmp_path / "versioned"
    frozen, _ = versioned_saved_run(directory)
    trial = reporting.aggregate_visual_runs([directory], frozen)["trials"][0]
    assert trial["eligible"], trial["exclusions"]


@pytest.mark.parametrize("damage", ["tasks_missing", "versions_missing", "map_incomplete", "map_version", "manifest", "actor", "trajectory", "experiment", "task", "hash"])
def test_prospective_task_version_mutations_are_excluded(tmp_path, damage):
    directory = tmp_path / "versioned"
    frozen, rows = versioned_saved_run(directory)
    manifest = json.loads((directory / "run.json").read_text())
    report = json.loads((directory / "visual-report.json").read_text())
    if damage == "tasks_missing": frozen.pop("tasks")
    elif damage == "versions_missing": frozen.pop("task_versions")
    elif damage == "map_incomplete": frozen["tasks"] = {}
    elif damage == "map_version": frozen["tasks"]["combat"]["task_version"] = "changed"
    elif damage == "manifest": manifest["task_version"] = "changed"
    elif damage == "actor": manifest["actor_identity"]["task_version"] = "changed"
    elif damage == "trajectory": rows[0]["meta"]["task_version"] = "changed"
    elif damage == "experiment": report["experiment"]["task_version"] = "changed"
    elif damage == "task": frozen["tasks"]["combat"]["task"] = "changed"
    elif damage == "hash": frozen["tasks"]["combat"]["task_sha256"] = "changed"
    write(directory / "run.json", manifest)
    write(directory / "visual-report.json", report)
    save_rows(directory, rows)
    trial = reporting.aggregate_visual_runs([directory], frozen)["trials"][0]
    assert not trial["eligible"]
    assert any(reason.startswith("task_version:") for reason in trial["exclusions"])


def portable_saved_run(directory):
    rows = saved_run(directory)
    frozen = protocol()
    frozen.pop("protocol_sha256")
    frozen["contract"] = "ftl-visual-challenge-matrix-v2"
    frozen["native_acceptance"]["receipts"] = {}
    frozen["admission_selector"] = {
        "contract": "portable-visual-controller-admission-v1",
        "admission": {"contract": "portable-visual-controller-admission-v1",
                      "controller_admission": True, "production_accepted": False,
                      "runtime": deepcopy(frozen["native_acceptance"]["runtime"])}}
    bind_portable_protocol(directory, frozen)
    return frozen


def bind_portable_protocol(directory, frozen):
    frozen["protocol_sha256"] = reporting.canonical_sha256({k: v for k, v in frozen.items() if k != "protocol_sha256"})
    rows = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()]
    for name in ("run.json", "visual-report.json"):
        value = json.loads((directory / name).read_text())
        value["experiment"]["protocol_sha256"] = frozen["protocol_sha256"]
        if "admission_selector" in frozen:
            value["experiment"]["admission_selector"] = deepcopy(frozen["admission_selector"])
        if name == "visual-report.json":
            value["experiment_sha256"] = reporting.canonical_sha256(value["experiment"])
        write(directory / name, value)
    rows[0]["meta"]["experiment"] = json.loads((directory / "run.json").read_text())["experiment"]
    save_rows(directory, rows)


def test_portable_aggregation_accepts_empty_legacy_receipts_with_audited_child(tmp_path):
    directory = tmp_path / "portable"
    frozen = portable_saved_run(directory)
    trial = reporting.aggregate_visual_runs([directory], frozen, admission_issues={str(directory): []})["trials"][0]
    assert trial["eligible"], trial["exclusions"]
    assert trial["task_success"]


@pytest.mark.parametrize("audit_entry", [None, {}, {"other": []}, "corrupt", [None], ["Controller admission: rejected"]])
def test_portable_aggregation_requires_explicit_valid_saved_child_audit(tmp_path, audit_entry):
    directory = tmp_path / "portable"
    frozen = portable_saved_run(directory)
    supplied = audit_entry if audit_entry is None or isinstance(audit_entry, dict) else {str(directory): audit_entry}
    trial = reporting.aggregate_visual_runs([directory], frozen, admission_issues=supplied)["trials"][0]
    assert not trial["eligible"]
    assert any("saved child admission audit" in issue or "Controller admission: rejected" in issue
               for issue in trial["exclusions"])


@pytest.mark.parametrize("field,value", [("controller_admission", False), ("controller_admission", 1),
                                         ("production_accepted", True), ("production_accepted", 0),
                                         ("contract", "unknown")])
def test_portable_aggregation_rejects_invalid_admission_state(tmp_path, field, value):
    directory = tmp_path / "portable"
    frozen = portable_saved_run(directory)
    frozen["admission_selector"]["admission"][field] = value
    bind_portable_protocol(directory, frozen)
    trial = reporting.aggregate_visual_runs([directory], frozen, admission_issues={str(directory): []})["trials"][0]
    assert not trial["eligible"]
    assert trial["exclusions"] == ["native_acceptance:portable controller admission missing or rejected"]


@pytest.mark.parametrize("field,value", [("dll_sha256", "x" * 64), ("patch_sha256", "x" * 64),
                                         ("production_bridge_sha256", "x" * 64), ("visual_clock_version", 1)])
def test_portable_aggregation_retains_runtime_join_rejections(tmp_path, field, value):
    directory = tmp_path / "portable"
    frozen = portable_saved_run(directory)
    frozen["admission_selector"]["admission"]["runtime"][field] = value
    frozen["native_acceptance"]["runtime"] = deepcopy(frozen["admission_selector"]["admission"]["runtime"])
    bind_portable_protocol(directory, frozen)
    trial = reporting.aggregate_visual_runs([directory], frozen, admission_issues={str(directory): []})["trials"][0]
    assert not trial["eligible"]
    assert len(trial["exclusions"]) == 1 and trial["exclusions"][0].startswith("native_acceptance:")
    assert "metadata differs" not in trial["exclusions"][0]


def test_unknown_comparison_contract_never_eligible(tmp_path):
    directory = tmp_path / "unknown"
    saved_run(directory)
    frozen = protocol()
    frozen["contract"] = "unknown"
    frozen["protocol_sha256"] = reporting.canonical_sha256({k: v for k, v in frozen.items() if k != "protocol_sha256"})
    trial = reporting.aggregate_visual_runs([directory], frozen)["trials"][0]
    assert not trial["eligible"]
    assert any("unknown" in issue for issue in trial["exclusions"])


@pytest.mark.parametrize("selector", [None, {}, "corrupt"])
def test_portable_aggregation_rejects_absent_or_corrupt_selector(tmp_path, selector):
    directory = tmp_path / "portable"
    frozen = portable_saved_run(directory)
    frozen["admission_selector"] = selector
    bind_portable_protocol(directory, frozen)
    trial = reporting.aggregate_visual_runs([directory], frozen, admission_issues={str(directory): []})["trials"][0]
    assert trial["exclusions"] == ["native_acceptance:portable controller admission missing or rejected"]


@pytest.mark.parametrize("receipts", [True, False])
def test_explicit_v1_retains_legacy_receipt_requirement(tmp_path, receipts):
    directory = tmp_path / "legacy"
    saved_run(directory)
    frozen = protocol()
    frozen["contract"] = "ftl-visual-challenge-matrix-v1"
    if not receipts:
        frozen["native_acceptance"]["receipts"] = {}
    bind_portable_protocol(directory, frozen)
    trial = reporting.aggregate_visual_runs([directory], frozen)["trials"][0]
    assert trial["eligible"] is receipts
    if not receipts:
        assert trial["exclusions"] == ["native_acceptance:native acceptance receipts missing"]
