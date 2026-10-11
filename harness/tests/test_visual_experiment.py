"""Matrix scheduling preserves matched conditions and never duplicates live trials."""
from contextlib import nullcontext
import importlib.util
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "scripts").is_dir():
    ROOT = Path(__file__).resolve().parents[1] / "src/ftl_bench/_bundled"
spec = importlib.util.spec_from_file_location("visual_experiment", ROOT / "scripts/run_visual_experiment.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def test_declared_matrix_has_all_matched_repetitions():
    cells = experiment.plan_cells()
    assert len(cells) == len({cell["id"] for cell in cells}) == 36
    assert {cell["model"] for cell in cells[:18]} == {"gpt-6.1-sol"}
    assert {cell["model"] for cell in cells[18:]} == {"gpt-6-luna"}
    for challenge in experiment.CHALLENGES:
        for repeat in range(1, 4):
            subset = [c for c in cells if c["challenge"] == challenge and c["repetition"] == repeat]
            assert {(c["model"], c["mode"]) for c in subset} == {
                (model, mode) for model in experiment.MODELS for mode in experiment.MODES}


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "rename", "reorder", "protocol"])
def test_resume_rejects_changed_matrix(mutation):
    ledger = {"protocol_sha256": "a", "cells": experiment.plan_cells()}
    if mutation == "drop":
        ledger["cells"].pop()
    elif mutation == "duplicate":
        ledger["cells"][1] = dict(ledger["cells"][0])
    elif mutation == "rename":
        ledger["cells"][0]["model"] = "another-model"
    elif mutation == "reorder":
        ledger["cells"].reverse()
    else:
        ledger["protocol_sha256"] = "b"
    with pytest.raises(RuntimeError):
        experiment.validate_ledger(ledger, {"protocol_sha256": "a"})


def test_live_process_blocks_resumption_even_with_terminal_file(tmp_path, monkeypatch):
    cell = experiment.plan_cells()[0]
    cell.update(status="running", process={"pid": 1, "creation_filetime": 2})
    path = experiment.saved_trial(tmp_path, cell)
    path.mkdir(parents=True)
    experiment.write_json(path / "run.json", {"status": "completed", "reason": "fixture_goal_observed"})
    monkeypatch.setattr(experiment, "process_identity", lambda pid: cell["process"])
    with pytest.raises(RuntimeError, match="still running"):
        experiment.reconcile(tmp_path, cell)
    assert cell["status"] == "running"


def test_missing_handle_without_terminal_evidence_is_preserved_not_retried(tmp_path, monkeypatch):
    cell = experiment.plan_cells()[0]
    cell.update(status="running", process={"pid": 1, "creation_filetime": 2})
    monkeypatch.setattr(experiment, "process_identity", lambda pid: None)
    experiment.reconcile(tmp_path, cell)
    assert cell["status"] == "interrupted_unknown"


def test_reused_pid_is_not_the_recorded_trial(tmp_path, monkeypatch):
    cell = experiment.plan_cells()[0]
    cell.update(status="running", process={"pid": 1, "creation_filetime": 2})
    path = experiment.saved_trial(tmp_path, cell)
    path.mkdir(parents=True)
    experiment.write_json(path / "run.json", {"status": "error", "reason": "visual_model_error"})
    monkeypatch.setattr(experiment, "process_identity", lambda pid: {"pid": 1, "creation_filetime": 3})
    experiment.reconcile(tmp_path, cell)
    assert cell["status"] == "finished"
    assert cell["result_status"] == "error"


def test_process_inspection_failure_is_not_proof_of_exit(tmp_path, monkeypatch):
    cell = experiment.plan_cells()[0]
    cell.update(status="running", process={"pid": 1, "creation_filetime": 2})
    def unavailable(pid):
        raise OSError("temporary inspection failure")
    monkeypatch.setattr(experiment, "process_identity", unavailable)
    with pytest.raises(OSError):
        experiment.reconcile(tmp_path, cell)
    assert cell["status"] == "running"


def test_started_cell_without_identity_requires_inspection(tmp_path):
    cell = experiment.plan_cells()[0]
    cell["status"] = "running"
    with pytest.raises(RuntimeError, match="no verified process identity"):
        experiment.reconcile(tmp_path, cell)


def test_command_preserves_frozen_budgets_and_paired_repeat(tmp_path):
    cell = experiment.plan_cells()[-1]
    protocol = {"seed": 1, "reasoning_effort": "medium",
                "budgets": {"decisions": 60, "wall_seconds": 1800, "idle_decisions": 8}}
    command = experiment.trial_command(tmp_path, cell, protocol)
    values = {flag: command[command.index(flag) + 1] for flag in (
        "--seed", "--model", "--mode", "--repeat-index", "--max-decisions", "--max-wall-seconds",
        "--max-idle-decisions", "--repeats", "--reasoning-effort")}
    assert values == {"--seed": "1", "--model": "gpt-6-luna", "--mode": "hybrid",
        "--repeat-index": "3", "--max-decisions": "60", "--max-wall-seconds": "1800",
        "--max-idle-decisions": "8", "--repeats": "1", "--reasoning-effort": "medium"}


def test_restoration_requires_every_original_in_receipt(tmp_path):
    cell = experiment.plan_cells()[0]
    backup = experiment.saved_trial(tmp_path, cell) / "save-backup"
    backup.mkdir(parents=True)
    experiment.write_json(backup.parent / "run.json", {"status": "completed", "save_restoration": "verified",
                                                       "production_source_unchanged": True})
    experiment.write_json(backup / "manifest.json", {"files": {"continue.sav": "a", "prof.sav": "b"}})
    experiment.write_json(backup / "restoration.json", {"verified": True, "files": {"continue.sav": True}})
    with pytest.raises(RuntimeError, match="restoration is not verified"):
        experiment.require_restoration(tmp_path, cell)
    experiment.write_json(backup / "restoration.json", {"verified": True, "files": {"continue.sav": True, "prof.sav": True}})
    experiment.require_restoration(tmp_path, cell)
    experiment.write_json(backup.parent / "run.json", {"status": "error", "save_restoration": "not_verified",
                                                       "production_source_unchanged": True})
    with pytest.raises(RuntimeError, match="restoration is not verified"):
        experiment.require_restoration(tmp_path, cell)


def test_restoration_accepts_explicitly_empty_original_inventory(tmp_path):
    cell = experiment.plan_cells()[0]
    backup = experiment.saved_trial(tmp_path, cell) / "save-backup"
    backup.mkdir(parents=True)
    experiment.write_json(backup.parent / "run.json", {"status": "completed", "save_restoration": "verified",
                                                       "production_source_unchanged": True})
    experiment.write_json(backup / "manifest.json", {"files": {}})
    experiment.write_json(backup / "restoration.json", {"verified": True, "files": {}})
    experiment.require_restoration(tmp_path, cell)
    experiment.write_json(backup / "restoration.json", {"verified": True})
    with pytest.raises(RuntimeError, match="restoration is not verified"):
        experiment.require_restoration(tmp_path, cell)


def accepted_files(root, changes=()):
    """Small immutable evidence chain: deliberately no live game or source access."""
    def write(path, value):
        path = root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            experiment.write_json(path, value)
        return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    dll = write("dist/Hyperspace.visual-v1.dll", b"tested dll")["sha256"]
    patch = write("native/patches/0003-visual-io.patch", b"full patch")["sha256"]
    lua = write("mod/ftl_bench_bridge/dev/ftl_bench_dev.lua", b"tested bridge")["sha256"]
    write("dist/native-validation.visual-v1.live.md", b"scoped current controls")
    clock = {"visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60}
    fresh = dict(experiment.FRESH_CONTRACT)
    sources = {f"source-{i}.cpp": str(i) * 64 for i in range(10)}
    sources.update({"utility.h": "a" * 64, "visual.h": "b" * 64})
    build_time = "2026-10-10T23:51:44.240528+00:00"
    docs = {
        "manifest": {"base_commit": "base", "patch_sha256": patch, **clock, **fresh},
        "build": {"dll_sha256": dll, "built_at": build_time, "base_commit": "base",
                  "candidate_source_sha256": dict(sources), **clock, **fresh},
        "provenance": {"dll_sha256": dll, "built_at": build_time, "source_commit": "base",
            "patch_sha256": patch, "source_files_sha256": dict(sources), **clock, **fresh},
        "verification": {"passed": True, "checks": {"rederived": True}, "dll_sha256": dll,
            "full_game_determinism_claimed": False, "internal_rng_stream_equality_measured": False,
            "model_calls": 0, "verifier_sha256": "c" * 64,
            "collections": [{"challenge": challenge, "trials": [{"rederived_checks": {"actual": True}}
                for _ in range(3)]} for challenge in experiment.CHALLENGES]},
        "review": {"verifier_sha256": "c" * 64, "actual_nine_trials_passed": True,
            "all_mutations_rejected": True, "mutations": [{"rejected": True} for _ in range(8)]},
        "acceptance": {"status": "accepted_for_production_integration",
            "acceptance_kind": "fresh-start-v3-nine-challenge-probes", "fresh_seed_contract": fresh["fresh_seed_contract"],
            "fixture_version": 6, "trial_count": 9, "model_calls": 0, "dll_sha256": dll,
            "full_game_determinism_claimed": False, "model_evaluation_performed": False},
        "integration": {"contract": "native-production-integration-plan-v1", "candidate_dll_sha256": dll,
            "staged_complete_patch_sha256": patch, "complete_patch_reconstructed_exact_base": True,
            "reconstructed_source_hashes_match_tested_build": True, "repeatability_gate_passed": False,
            "complete_patch_paths": sorted(sources),
            "staged_sha256": {"native-source/" + key: value for key, value in sources.items()}},
    }
    for document, path, value in changes:
        target = docs[document]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    manifest = write("native/manifest.json", docs["manifest"])
    build = write("dist/origins/build.json", docs["build"])
    docs["verification"]["build_manifest_sha256"] = build["sha256"]
    verification = write("dist/origins/verification.json", docs["verification"])
    docs["review"].update(verification_receipt_sha256=verification["sha256"], build_manifest_sha256=build["sha256"])
    review = write("dist/origins/review.json", docs["review"])
    docs["acceptance"].update(evidence=verification, independent_review=review, build_manifest=build)
    acceptance = write("dist/origins/acceptance.json", docs["acceptance"])
    docs["integration"]["staged_sha256"].update({"repo/native/manifest.json": manifest["sha256"],
        "repo/mod/ftl_bench_bridge/dev/ftl_bench_dev.lua": lua})
    integration = write("dist/origins/integration.json", docs["integration"])
    provenance = write("dist/native-build.visual-v1.json", docs["provenance"])
    receipt = {"artifacts": {"dll_sha256": dll, "patch_sha256": patch, "lua_sha256": lua,
        "dll_build_provenance_sha256": provenance["sha256"], "manifest_sha256": manifest["sha256"], **clock, **fresh},
        "live_acceptance": {"claimed": True, "fixed_step_verified": True, "fixed_step_case_ids": ["scoped-current"]},
        "fresh_start_evidence": {"contract": "fresh-start-v3-nine-probes-v1", "acceptance": acceptance, "integration": integration}}
    write("dist/native-validation.visual-v1.json", receipt)
    return experiment.source_identity(root), receipt


def test_native_acceptance_cannot_be_reused_for_changed_binary(tmp_path):
    source, _ = accepted_files(tmp_path)
    accepted = experiment.accepted_native_runtime(source, tmp_path)
    assert accepted["dll_sha256"] == source["dist/Hyperspace.visual-v1.dll"]
    assert all(accepted[key] == value for key, value in experiment.FRESH_CONTRACT.items())
    source["dist/Hyperspace.visual-v1.dll"] = "new"
    with pytest.raises(RuntimeError, match="matching recorded live acceptance"):
        experiment.accepted_native_runtime(source, tmp_path)


@pytest.mark.parametrize("change", ["v1", "no_live_timing", "no_cases", "wrong_step", "bool_step"])
def test_comparison_rejects_update_count_only_or_unverified_time_contract(tmp_path, change):
    source, receipt = accepted_files(tmp_path)
    if change == "v1":
        receipt["artifacts"]["visual_clock_version"] = 1
    elif change == "no_live_timing":
        receipt["live_acceptance"].pop("fixed_step_verified")
    elif change == "no_cases":
        receipt["live_acceptance"]["fixed_step_case_ids"] = []
    elif change == "wrong_step":
        receipt["artifacts"]["fixed_step_denominator"] = 30
    else:
        receipt["artifacts"]["fixed_step_numerator"] = True
    path = tmp_path / "dist/native-validation.visual-v1.json"
    experiment.write_json(path, receipt)
    with pytest.raises(RuntimeError, match="live repeatability acceptance"):
        experiment.accepted_native_runtime(source, tmp_path)


@pytest.mark.parametrize("document,path,value", [
    ("manifest", ("fresh_start_seed",), 1),
    ("provenance", ("fresh_seed_contract_version",), 2),
    ("build", ("fresh_seed_contract",), None),
    ("acceptance", ("status",), "pending"),
    ("acceptance", ("fixture_version",), 5),
    ("acceptance", ("trial_count",), 8),
    ("acceptance", ("model_calls",), False),
    ("acceptance", ("full_game_determinism_claimed",), True),
    ("verification", ("checks", "rederived"), False),
    ("verification", ("collections", 1, "trials"), []),
    ("verification", ("collections", 0, "trials", 0, "rederived_checks", "actual"), False),
    ("review", ("all_mutations_rejected",), False),
    ("review", ("verifier_sha256",), "d" * 64),
    ("review", ("mutations", 1, "rejected"), False),
    ("build", ("dll_sha256",), "d" * 64),
    ("provenance", ("built_at",), "2026-10-11T00:00:00+00:00"),
    ("provenance", ("source_commit",), "different"),
    ("provenance", ("source_files_sha256", "source-1.cpp"), "changed"),
    ("integration", ("complete_patch_reconstructed_exact_base",), False),
    ("integration", ("staged_complete_patch_sha256",), "d" * 64),
])
def test_fresh_start_evidence_rejects_wrong_scope_or_artifact_join(tmp_path, document, path, value):
    source, _ = accepted_files(tmp_path, [(document, path, value)])
    with pytest.raises(RuntimeError, match="Fresh-start v3"):
        experiment.accepted_native_runtime(source, tmp_path)


def test_origins_and_new_runtime_modules_are_frozen_and_detect_changed_receipts(tmp_path):
    source, _ = accepted_files(tmp_path)
    assert len([key for key in source if key.startswith("dist/origins/")]) == 5
    helper = tmp_path / "harness/src/ftl_bench/fullgame_setup.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# new runtime helper\n")
    assert "harness/src/ftl_bench/fullgame_setup.py" in experiment.source_identity(tmp_path)
    (tmp_path / "dist/origins/review.json").write_text("{}")
    with pytest.raises(RuntimeError, match="evidence hash mismatch"):
        experiment.source_identity(tmp_path)


@pytest.mark.parametrize("change", ["legacy", "escape", "hash", "unfrozen"])
def test_missing_unpinned_or_unsafe_fresh_evidence_refuses_new_cohort(tmp_path, change):
    source, receipt = accepted_files(tmp_path)
    if change == "legacy":
        receipt.pop("fresh_start_evidence")
    elif change == "escape":
        receipt["fresh_start_evidence"]["acceptance"]["path"] = "../outside.json"
    elif change == "hash":
        receipt["fresh_start_evidence"]["acceptance"]["sha256"] = "f" * 64
    else:
        source.pop("dist/origins/review.json")
    experiment.write_json(tmp_path / "dist/native-validation.visual-v1.json", receipt)
    with pytest.raises(RuntimeError, match="Fresh-start"):
        experiment.accepted_native_runtime(source, tmp_path)


def test_stop_request_prevents_controller_launch(tmp_path, monkeypatch):
    from visual_cancellation import request_stop
    protocol = {"protocol_sha256": "test"}
    experiment.write_json(tmp_path / "protocol.json", protocol)
    experiment.write_json(tmp_path / "ledger.json", {"protocol_sha256": "test", "cells": experiment.plan_cells()})
    request_stop(tmp_path / "stop-request.json", str(tmp_path.resolve()), "assistant:test")
    monkeypatch.setattr(experiment, "verify_protocol", lambda protocol: None)
    monkeypatch.setattr(experiment, "controller_lock", lambda directory: nullcontext())
    monkeypatch.setattr(experiment.subprocess, "Popen", lambda *a, **kw: pytest.fail("stopped controller launched child"))
    experiment.run(tmp_path, 36)
    ledger = experiment.read_json(tmp_path / "ledger.json")
    assert ledger["stop_requested"] is True
    assert all(cell["status"] == "planned" for cell in ledger["cells"])


def test_stop_during_protocol_verification_preserves_planned_cell(tmp_path, monkeypatch):
    from visual_cancellation import request_stop
    experiment.write_json(tmp_path / "protocol.json", {"protocol_sha256": "test"})
    experiment.write_json(tmp_path / "ledger.json", {"protocol_sha256": "test", "cells": experiment.plan_cells()})
    checks = []
    def verify(protocol):
        checks.append(True)
        if len(checks) == 2:
            request_stop(tmp_path / "stop-request.json", str(tmp_path.resolve()), "assistant:test")
    monkeypatch.setattr(experiment, "verify_protocol", verify)
    monkeypatch.setattr(experiment, "controller_lock", lambda directory: nullcontext())
    monkeypatch.setattr(experiment.subprocess, "Popen", lambda *a, **kw: pytest.fail("stop during verify launched child"))
    experiment.run(tmp_path, 36)
    assert len(checks) == 2
    assert all(cell["status"] == "planned" for cell in experiment.read_json(tmp_path / "ledger.json")["cells"])
