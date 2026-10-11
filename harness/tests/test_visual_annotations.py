"""Historical notes must bind raw evidence and never repair scores or lifecycle."""
import hashlib
import json
import pytest

from visual_annotations import trial_annotations
import ftl_live as live


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recovery(directory):
    write(directory / "run.json", {"track": "visual-v1", "status": "running"})
    (directory / "trajectory.jsonl").write_text('{"kind":"meta","meta":{}}\n')
    write(directory / "save-backup/restoration.json", {"verified": True, "files": {"original.sav": True}})
    value = {"contract": "operator-recovery-v1", "manual_recovery_verified": True,
        "raw_lifecycle_unchanged": True, "no_game_process": True, "original_save_count": 1,
        "baseline_checks": {"original.sav": True}, "automatic_cleanup_completed": False,
        "raw_artifact_sha256": {name: digest(directory / name) for name in ("run.json", "trajectory.jsonl")},
        "restoration_receipt_sha256": digest(directory / "save-backup/restoration.json")}
    write(directory / "operator-recovery/receipt.json", value)
    return value


def test_verified_manual_recovery_corrects_display_without_fabricating_terminal_or_changing_raw(tmp_path, monkeypatch):
    recovery(tmp_path)
    monkeypatch.setattr(live, "BENCH", tmp_path)
    path = str(tmp_path / "trajectory.jsonl")
    before = digest(tmp_path / "run.json"), digest(tmp_path / "trajectory.jsonl")
    runs, files = live.discover_runs([path])
    run = runs[files[path]]
    assert run["status"] == "interrupted" and run["raw_status"] == "running"
    assert live.lifecycle(path, run) == {"status": "interrupted", "reason": "abrupt_operator_stop", "error": None, "finalized": False}
    report = live.visual_trial_report(path)
    assert report["save_restoration"] is None
    assert report["operator_recovery"]["manual_recovery_verified"] is True
    assert report["operator_recovery"]["automatic_cleanup_completed"] is False
    assert before == (digest(tmp_path / "run.json"), digest(tmp_path / "trajectory.jsonl"))


def test_changed_raw_lifecycle_invalidates_manual_recovery_annotation(tmp_path):
    recovery(tmp_path)
    write(tmp_path / "run.json", {"status": "completed"})
    result = trial_annotations(tmp_path)
    assert result["operator_recovery"] is None
    assert "differ" in result["annotation_issues"][0]


def test_changed_restoration_invalidates_manual_recovery_annotation(tmp_path):
    recovery(tmp_path)
    write(tmp_path / "save-backup/restoration.json", {"verified": False})
    result = trial_annotations(tmp_path)
    assert result["operator_recovery"] is None and result["annotation_issues"]


def test_adjudication_keeps_raw_outcome_and_rejects_changed_support(tmp_path, monkeypatch):
    recovery(tmp_path)
    write(tmp_path / "validation.json", {"outcome_category": "budget_exhausted"})
    write(tmp_path / "adjudication/evidence.json", {"written_task_satisfied": True})
    (tmp_path / "adjudication/report.md").write_text("Scoring mismatch")
    write(tmp_path / "adjudication/receipt.json", {"contract": "challenge-adjudication-v1",
        "recorded_outcome_kept": True, "written_task_satisfied": True, "summary": "Written task satisfied",
        "source_sha256": {name: digest(tmp_path / name) for name in ("run.json", "trajectory.jsonl", "validation.json")},
        "evidence_file": "evidence.json", "evidence_sha256": digest(tmp_path / "adjudication/evidence.json"),
        "report_file": "report.md", "report_sha256": digest(tmp_path / "adjudication/report.md")})
    monkeypatch.setattr(live, "BENCH", tmp_path)
    report = live.visual_trial_report(str(tmp_path / "trajectory.jsonl"))
    assert report["outcome"] == "budget_exhausted"
    assert report["adjudication"]["written_task_satisfied"] is True
    receipt_path = tmp_path / "adjudication/receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["summary"] = {"unexpected": "object"}
    write(receipt_path, receipt)
    assert trial_annotations(tmp_path)["adjudication"] is None
    receipt["summary"] = "Written task satisfied"
    write(receipt_path, receipt)
    (tmp_path / "adjudication/report.md").write_text("Changed interpretation")
    assert trial_annotations(tmp_path)["adjudication"] is None


def test_unexpected_evidence_path_is_rejected_without_reading_external_file(tmp_path):
    receipt = recovery(tmp_path)
    receipt["raw_artifact_sha256"]["../private-file"] = "bad"
    write(tmp_path / "operator-recovery/receipt.json", receipt)
    result = trial_annotations(tmp_path)
    assert result["operator_recovery"] is None
    assert "unexpected evidence" in result["annotation_issues"][0]


@pytest.mark.parametrize("field,value", [("initiator", {"unexpected": "object"}),
    ("recovered_at", []), ("original_save_count", True), ("automatic_cleanup_completed", "false")])
def test_malformed_rendered_fields_fail_closed(tmp_path, field, value):
    receipt = recovery(tmp_path)
    receipt[field] = value
    write(tmp_path / "operator-recovery/receipt.json", receipt)
    result = trial_annotations(tmp_path)
    assert result["operator_recovery"] is None and result["annotation_issues"]
