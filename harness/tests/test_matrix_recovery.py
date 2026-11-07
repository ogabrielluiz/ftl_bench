"""Offline controller continuation after actual mocked protected-launch recovery."""
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
import ftl_bench.protected_game as protected
from test_pending_launch import pending_steam_request
from test_visual_experiment import experiment


def recovered_matrix(case, empty=False):
    save, bridge, game_dir, launches, root = case
    if empty:
        for path in save.glob("*.sav"):
            path.unlink()
        (save / "ftl_bench_dev.lua").unlink()
    directory = root / "cohort"
    cells = experiment.plan_cells()
    cell = cells[0]
    trial = experiment.saved_trial(directory, cell)
    trial.mkdir(parents=True)
    game = protected.ProtectedGame(save, trial / "save-backup", bridge, game_dir)
    with pytest.raises(RuntimeError, match="Unresolved Steam launch"):
        with game.protected():
            game.launch(timeout=1)
    cell.update(status="finished", result_status="error", result_reason="protected_launch_error", exit_code=1)
    experiment.write_json(trial / "run.json", {"status": "error", "reason": "protected_launch_error",
        "save_restoration": "not_verified", "production_source_unchanged": True, "failure_type": "infrastructure_failure"})
    experiment.write_json(trial / "validation.json", {"status": "failed",
        "valid_for_model_comparison": False, "termination": "protected_launch_error",
        "failure_type": "infrastructure_failure", "outcome_category": "infrastructure_failure",
        "save_restoration_verified": False, "production_source_unchanged": True})
    owner = json.loads(game.pending_launch.read_bytes())["ownership_id"]
    protected.recover_protected(game.backup, ownership_id=owner, confirm_pending_launch_cancelled=True)
    return directory, cells, game


def test_matrix_recovery_check_preserves_failed_artifacts(pending_steam_request):
    directory, cells, game = recovered_matrix(pending_steam_request)
    before = {p: p.read_bytes() for p in game.backup.parent.rglob("*") if p.is_file()}
    experiment.require_restoration(directory, cells[0])
    assert all(p.read_bytes() == content for p, content in before.items())
    assert not (game.backup / "restoration.json").exists()
    check = experiment.read_json(next((directory / "recovery-checks").glob("*.json")))
    assert check["verified"] is True and check["result_eligibility_unchanged"] is True
    assert check["files_sha256"]["save-backup/recovery-restoration.json"] == protected._hash(game.backup / "recovery-restoration.json")


def test_recovery_does_not_change_real_reporting_exclusion(pending_steam_request):
    import visual_reporting as reporting

    directory, cells, game = recovered_matrix(pending_steam_request)
    trial = game.backup.parent
    # A launch failure has metadata and an error ending, with no reset/image/model turn.
    meta = {"model": cells[0]["model"], "observation_mode": "image", "codex_cli": {}}
    run = experiment.read_json(trial / "run.json")
    experiment.write_json(trial / "run.json", {**run, **meta, "finished_at": 1})
    rows = [{"kind": "meta", "meta": meta}, {"kind": "end", "status": "error",
        "reason": "protected_launch_error", "decisions": 0}]
    (trial / "trajectory.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    experiment.write_json(trial / "runtime-fingerprint.json", {"codex_cli": {}})
    experiment.write_json(trial / "visual-report.json", {"status": "error",
        "reason": "protected_launch_error", "decisions": 0})

    def saved_result():
        audit = reporting.audit_visual_run(trial)
        assert audit["outcome_category"] == "infrastructure_failure"
        assert audit["complete"] is False
        assert any(issue["scope"] == "terminal_cleanup" and "does not verify save restoration" in issue["error"]
                   for issue in audit["issues"])
        result = reporting.aggregate_visual_runs([trial])["trials"][0]
        assert result["eligible"] is False
        assert "non_gameplay_outcome:infrastructure_failure" in result["exclusions"]
        assert "protocol_or_cleanup_audit_failed" in result["exclusions"]
        return result

    before = saved_result()
    experiment.require_restoration(directory, cells[0])
    assert saved_result() == before
    assert not (game.backup / "restoration.json").exists()


@pytest.mark.parametrize("empty", [False, True])
def test_matrix_continues_only_next_cell_with_frozen_source_check(pending_steam_request, monkeypatch, empty):
    import validate_visual_challenges as challenges
    import run_visual
    directory, cells, game = recovered_matrix(pending_steam_request, empty)
    # A fresh synthetic source archive pins actual controller bytes. Never edit a historical cohort.
    source = directory / "source"
    (source / "scripts").mkdir(parents=True)
    controller = source / "scripts/run_visual_experiment.py"
    controller.write_bytes(experiment.Path(experiment.__file__).read_bytes())
    (source / "dist").mkdir()
    for name in ("Hyperspace.visual-v1.dll", "native-build.visual-v1.json", "native-validation.visual-v1.live.md"):
        (source / "dist" / name).write_bytes(b"offline fixture")
    (source / "dist/native-validation.visual-v1.json").write_text("{}")
    identity = experiment.source_identity
    monkeypatch.setattr(experiment, "source_identity", lambda root: identity(source))
    monkeypatch.setattr(run_visual, "codex_runtime_identity", lambda: {"offline": True})
    protocol = {**experiment.declared_conditions(), "contract": experiment.CONTRACT,
        "source_files": identity(source), "task_versions": challenges.TASK_VERSIONS,
        "tasks": {c: challenges.task_identity(c) for c in experiment.CHALLENGES},
        "codex_cli": {"offline": True}}
    protocol["protocol_sha256"] = experiment.digest(protocol)
    experiment.write_json(directory / "protocol.json", protocol)
    experiment.write_json(directory / "ledger.json", {"protocol_sha256": protocol["protocol_sha256"], "cells": cells})
    monkeypatch.setattr(experiment, "controller_lock", lambda directory: nullcontext())
    monkeypatch.setattr(experiment, "process_identity", lambda pid: {"pid": pid})
    monkeypatch.setattr(experiment, "wait_for_protected_child", lambda *a: 0)
    monkeypatch.setattr(experiment, "refresh_summary", lambda *a: None)
    launched = []
    def child(command, **kwargs):
        launched.append(command)
        trial = experiment.saved_trial(directory, cells[1])
        (trial / "save-backup").mkdir(parents=True)
        experiment.write_json(trial / "run.json", {"status": "completed", "save_restoration": "verified", "production_source_unchanged": True})
        experiment.write_json(trial / "save-backup/manifest.json", {"files": {}})
        experiment.write_json(trial / "save-backup/restoration.json", {"verified": True, "files": {}})
        return SimpleNamespace(pid=99)
    monkeypatch.setattr(experiment.subprocess, "Popen", child)
    original = (game.backup.parent / "run.json").read_bytes()
    # Source drift blocks before any child creation and does not rewrite pins.
    controller.write_bytes(controller.read_bytes() + b"\n# changed\n")
    with pytest.raises(RuntimeError, match="Frozen experiment source changed"):
        experiment.run(directory, 1)
    assert not launched
    controller.write_bytes(experiment.Path(experiment.__file__).read_bytes())
    experiment.run(directory, 1)
    assert len(launched) == 1
    assert str(directory / "trials" / cells[1]["id"]) in launched[0]
    ledger = experiment.read_json(directory / "ledger.json")
    assert ledger["cells"][0] == cells[0]
    assert ledger["cells"][2]["status"] == "planned"
    assert (game.backup.parent / "run.json").read_bytes() == original
    assert experiment.read_json(game.backup.parent / "validation.json")["valid_for_model_comparison"] is False
    assert not (game.backup / "restoration.json").exists()


@pytest.mark.parametrize("failure", ["owner", "hash", "backup_path", "save_path", "contract", "ack", "queue", "state",
    "timeout_owner", "timeout_state", "missing_file", "extra_file", "false_file", "backup", "bridge_backup",
    "bridge_live", "live", "extra_live", "active", "inspection", "marker", "prepared", "no_manifest",
    "unverified", "missing_mapping", "numeric_file", "reappearing_marker", "missing_live", "manifest_bytes", "model_error", "wrong_failure_type", "missing_save_directory", "unsafe_run_path"])
def test_matrix_recovery_rejects_unsafe_continuation(pending_steam_request, monkeypatch, failure):
    directory, cells, game = recovered_matrix(pending_steam_request, empty=failure == "missing_save_directory")
    receipt_path = game.backup / "recovery-restoration.json"
    receipt = experiment.read_json(receipt_path)
    fields = {"owner": "ownership_id", "hash": "manifest_sha256", "backup_path": "backup_directory",
        "save_path": "save_directory", "contract": "contract", "ack": "operator_confirmed_pending_launch_cancelled",
        "queue": "queue_cancellation_verified_by_harness", "state": "prior_launch_state"}
    if failure == "unsafe_run_path":
        safe_path = protected._safe_path
        def reject_run_path(path):
            if path == game.backup.parent / "run.json":
                raise RuntimeError("Unsafe linked protected-game path")
            return safe_path(path)
        monkeypatch.setattr(protected, "_safe_path", reject_run_path)
    elif failure in {"model_error", "wrong_failure_type"}:
        path = game.backup.parent / "run.json"
        value = experiment.read_json(path)
        value["reason" if failure == "model_error" else "failure_type"] = (
            "visual_model_error" if failure == "model_error" else "protocol_failure")
        experiment.write_json(path, value)
    elif failure == "missing_save_directory":
        # Empty originals and no prior Lua must not make a missing folder pass.
        for path in game.save.iterdir():
            path.unlink()
        game.save.rmdir()
    elif failure in fields:
        receipt["recovery"][fields[failure]] = "wrong"
    elif failure == "unverified": receipt["verified"] = False
    elif failure == "missing_mapping": receipt.pop("files")
    elif failure in {"missing_file", "extra_file", "false_file", "numeric_file"}:
        if failure == "missing_file": receipt["files"].pop("prof.sav")
        elif failure == "extra_file": receipt["files"]["extra.sav"] = True
        else: receipt["files"]["prof.sav"] = 1 if failure == "numeric_file" else False
    elif failure.startswith("timeout_"):
        path = game.backup / "launch-timeout.json"
        value = experiment.read_json(path)
        value["ownership_id" if failure == "timeout_owner" else "state"] = "wrong"
        experiment.write_json(path, value)
    elif failure == "manifest_bytes":
        path = game.backup / "manifest.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif failure == "missing_live": (game.save / "prof.sav").unlink()
    elif failure in {"active", "inspection", "reappearing_marker"}:
        def processes():
            if failure == "inspection": raise RuntimeError("inspection failed")
            if failure == "reappearing_marker":
                game.pending_launch.write_text("{}")
                return []
            return [{"id": 42}]
        monkeypatch.setattr(protected, "_processes", processes)
    elif failure == "prepared": receipt["recovery"]["prior_launch_state"] = "prepared"
    elif failure == "no_manifest": (game.backup / "manifest.json").unlink()
    else:
        path = {"backup": game.backup / "prof.sav", "bridge_backup": game.backup / "ftl_bench_dev.lua",
            "bridge_live": game.save / "ftl_bench_dev.lua", "live": game.save / "prof.sav",
            "extra_live": game.save / "extra.sav", "marker": game.pending_launch}[failure]
        path.write_bytes(b"changed")
    experiment.write_json(receipt_path, receipt)
    experiment.write_json(directory / "protocol.json", {"protocol_sha256": "offline"})
    experiment.write_json(directory / "ledger.json", {"protocol_sha256": "offline", "cells": cells})
    # Source verification is covered above; isolate the cleanup-to-launch boundary here.
    monkeypatch.setattr(experiment, "verify_protocol", lambda *a, **kw: None)
    monkeypatch.setattr(experiment, "controller_lock", lambda directory: nullcontext())
    monkeypatch.setattr(experiment.subprocess, "Popen", lambda *a, **kw: pytest.fail("unsafe child launch"))
    with pytest.raises(RuntimeError, match="restoration is not verified"):
        experiment.run(directory, 1)
    assert not (directory / "recovery-checks").exists()
