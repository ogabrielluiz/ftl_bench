"""Saved full-game projection: five conditions, native endings and confined links."""
import hashlib
import json
from pathlib import Path

import pytest
from ftl_bench.cli import _bench_root
import sys
sys.path.insert(0, str(_bench_root() / "adapter"))
import visual_comparison as comparison
from test_visual_comparison import asgi_request, api, save


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@pytest.fixture
def fullgame(tmp_path):
    directory = tmp_path / "fullgame"
    declared = [{"id": "pilot/sol/image/sector-1", "model": "sol", "mode": "image", "scope": "sector_pilot", "stop_after_sector": 1, "status": "planned"}]
    declared += [{"id": f"fullgame/{model}/{mode}", "model": model, "mode": mode, "scope": "full_game", "stop_after_sector": None, "status": "planned"} for model in ("sol", "luna") for mode in ("image", "hybrid")]
    protocol = {"contract": comparison.FULLGAME_CONTRACT, "seed": 1, "cells": declared,
                "budgets": {"decisions": 300, "wall_seconds": 14400, "idle_decisions": 8}}
    protocol["protocol_sha256"] = digest(protocol)
    save(directory / "protocol.json", protocol)
    cells = [dict(cell, status=status) for cell, status in zip(declared, ("finished", "finished", "finished", "running", "planned"))]
    trials = []
    for index, cell in enumerate(cells[:4]):
        trial = directory / "trials" / cell["id"]
        save(trial / "run.json", {"track": "visual-v1", "model": cell["model"], "observation_mode": cell["mode"]})
        (trial / "trajectory.jsonl").write_text('{"kind":"reset","obs":{}}\n')
        if index == 3:
            continue
        native = ("defeat", "victory", None)[index]
        reason = ("native_game_over", "native_victory", "decision_budget")[index]
        save(trial / "run.json", {"status": "completed", "reason": reason})
        save(trial / "visual-report.json", {"status": "completed", "reason": reason})
        save(trial / "save-backup/manifest.json", {"files": {}})
        save(trial / "save-backup/restoration.json", {"restored": True})
        (trial / "trajectory.jsonl").write_text(json.dumps({"kind": "step", "obs": {
            "victory": native == "victory", "game_over": native == "defeat"}}) + "\n" +
            json.dumps({"kind": "end", "status": "completed", "reason": reason}) + "\n")
        trials.append({"id": cell["id"], "scope": cell["scope"], "requested_model": cell["model"], "mode": cell["mode"],
            "directory": str(trial), "status": "completed", "reason": reason, "native_outcome": native,
            "fullgame_complete": index == 1, "verified_fullgame_complete": index == 1,
            "integrity_passed": True, "audit": {"complete": True, "issues": []},
            "category": ("pilot_defeat", "victory", "incomplete")[index],
            "issues": [], "metrics": {"final_hull": 30 if index == 1 else 0, "crew_alive": 3 if index == 1 else 0},
            "model_calls": {"usage": {"complete_totals": {"input_tokens": None, "output_tokens": 0}}}})
    report = {"contract": comparison.FULLGAME_CONTRACT, "protocol_sha256": protocol["protocol_sha256"],
        "pilot_excluded_from_fullgame_totals": True, "ranking_claimed": False, "trials": trials,
        "counts": {"planned": 1, "running": 1, "finished_attempts": 3, "fullgame_attempts": 2,
                   "verified_fullgame_completions": 1, "victories": 1, "defeats": 0, "incomplete_fullgames": 1}, "limitations": ["Single seed."]}
    save(directory / "comparison.json", report)
    cleanup = directory / "cleanup-checks" / cells[1]["id"] / "2026-10-11-check.json"
    save(cleanup, {"contract": "fullgame-live-cleanup-check-v1", "protocol_sha256": protocol["protocol_sha256"],
        "cell_id": cells[1]["id"], "passed": True, "no_game_process": True, "checked_at": "2026-10-11T01:00:00Z",
        "status": "completed", "reason": "native_victory", "artifact_sha256": {
            name: hashlib.sha256((directory / "trials" / cells[1]["id"] / name).read_bytes()).hexdigest()
            for name in comparison.FULLGAME_ARTIFACTS}})
    cells[1]["cleanup_checks"] = [{"path": cleanup.relative_to(directory).as_posix(), "sha256": hashlib.sha256(cleanup.read_bytes()).hexdigest()}]
    ledger = {"protocol_sha256": protocol["protocol_sha256"], "cells": cells}
    save(directory / "ledger.json", ledger)
    return tmp_path, directory, protocol, ledger, report


def test_fullgame_catalog_and_real_api_expose_all_five_conditions(fullgame, monkeypatch):
    root, directory, _, _, report = fullgame
    monkeypatch.setattr(api, "BENCH", root)
    status, catalog = asgi_request(api.create_app(), "/api/comparisons")
    assert status == 200 and catalog["comparisons"][0]["experiment_kind"] == "full_game"
    status, view = asgi_request(api.create_app(), "/api/comparisons", "key=fullgame")
    assert status == 200 and view["counts"] == {"planned": 1, "running": 1, "finished": 3, "total": 5, "unknown": 0}
    assert len(view["trials"]) == 5 and view["fullgame_summary"] == report["counts"]
    assert view["requested_models"] == ["sol", "luna"]
    assert view["trials"][0]["scope"] == "sector_pilot" and view["trials"][0]["verified_fullgame_complete"] is False
    assert view["trials"][1]["verified_fullgame_complete"] is True
    assert view["trials"][2]["verified_fullgame_complete"] is False
    assert view["trials"][3]["selection"] == "fullgame/trials/fullgame/luna/image/trajectory"
    assert view["trials"][4]["selection"] is None and view["trials"][4]["metrics"] is None
    assert view["trials"][1]["cleanup_evidence"][0]["checked_at"] == "2026-10-11T01:00:00Z"
    assert view["artifact_sha256"]["comparison.json"] == hashlib.sha256((directory / "comparison.json").read_bytes()).hexdigest()


@pytest.mark.parametrize("first_pilot", [False, True])
def test_running_cell_uses_live_ledger_progress_without_rejecting_unchanged_saved_outcomes(fullgame, monkeypatch, first_pilot):
    root, directory, _, ledger, report = fullgame
    if first_pilot:
        # Real controller order: save a summary, then admit the child by updating
        # only the ledger. The summary is refreshed after the child exits.
        for cell in ledger["cells"]:
            cell["status"] = "planned"
            cell.pop("cleanup_checks", None)
        ledger["cells"][0]["status"] = "running"
        report["trials"] = []
        report["counts"] = {key: 0 for key in report["counts"]}
        report["counts"]["planned"] = 5
    else:
        report["counts"].update(planned=2, running=0)
    save(directory / "ledger.json", ledger)
    save(directory / "comparison.json", report)
    saved_bytes = (directory / "comparison.json").read_bytes()
    monkeypatch.setattr(api, "BENCH", root)
    status, view = asgi_request(api.create_app(), "/api/comparisons", "key=fullgame")
    assert status == 200 and view["issues"] == [] and view["partial"]
    assert view["counts"]["running"] == 1
    assert view["fullgame_summary"]["running"] == 1
    assert view["fullgame_summary"]["planned"] == report["counts"]["planned"] - 1
    assert view["fullgame_summary"]["verified_fullgame_completions"] == report["counts"]["verified_fullgame_completions"]
    assert view["summary_refresh"] == "live_progress"
    assert "ledger" in view["source"]
    assert (directory / "comparison.json").read_bytes() == saved_bytes
    assert view["artifact_sha256"]["comparison.json"] == hashlib.sha256(saved_bytes).hexdigest()


@pytest.mark.parametrize("mutation", ["wrong_finished", "wrong_victories", "wrong_planned", "boolean_running", "missing_count", "extra_count", "ledger_finished", "ledger_unknown", "ledger_rollback", "native_contradiction"])
def test_live_refresh_allowance_never_hides_completed_or_inconsistent_evidence(fullgame, mutation):
    root, directory, _, ledger, report = fullgame
    report["counts"].update(planned=2, running=0)
    if mutation == "wrong_finished": report["counts"]["finished_attempts"] = 2
    elif mutation == "wrong_victories": report["counts"]["victories"] = 0
    elif mutation == "wrong_planned": report["counts"]["planned"] = 3
    elif mutation == "boolean_running": report["counts"]["running"] = False
    elif mutation == "missing_count": report["counts"].pop("victories")
    elif mutation == "extra_count": report["counts"]["other"] = 0
    elif mutation == "ledger_finished": ledger["cells"][3]["status"] = "finished"
    elif mutation == "ledger_unknown": ledger["cells"][3]["status"] = "interrupted_unknown"
    elif mutation == "ledger_rollback":
        ledger["cells"][3]["status"] = "planned"
        report["counts"].update(planned=1, running=1)
    else:
        # A completed audit contradiction remains an error even while a later
        # condition starts and its cached execution counts lag.
        report["trials"][1]["audit"]["complete"] = False
    save(directory / "ledger.json", ledger)
    save(directory / "comparison.json", report)
    view = comparison.comparison_view(root, "fullgame")
    assert view["fullgame_summary"] is None and view["issues"]
    assert view["summary_refresh"] == "inconsistent"


@pytest.mark.parametrize("row", [0, 2])
def test_pilot_or_budget_cannot_be_promoted_to_fullgame_completion(fullgame, row):
    root, directory, _, _, report = fullgame
    report["trials"][row].update(fullgame_complete=True, verified_fullgame_complete=True)
    save(directory / "comparison.json", report)
    view = comparison.comparison_view(root, "fullgame")
    assert view["fullgame_summary"] is None and view["issues"]
    assert view["trials"][row]["verified_fullgame_complete"] is None


def test_failed_integrity_native_ending_is_not_counted(fullgame):
    root, directory, _, _, report = fullgame
    report["trials"][1].update(integrity_passed=False, verified_fullgame_complete=False)
    report["counts"].update(verified_fullgame_completions=0, victories=0, incomplete_fullgames=2)
    save(directory / "comparison.json", report)
    view = comparison.comparison_view(root, "fullgame")
    assert view["fullgame_summary"]["verified_fullgame_completions"] == 0
    assert view["trials"][1]["native_outcome"] == "victory" and view["trials"][1]["verified_fullgame_complete"] is False


@pytest.mark.parametrize("mutation", ["audit_incomplete", "audit_issues", "candidate_issues", "missing_cleanup",
    "changed_run", "changed_report", "changed_trajectory", "changed_backup", "changed_restoration",
    "raw_native_contradiction", "missing_terminal", "extra_terminal", "append_after_end", "incomplete_hashes",
    "wrong_raw_reason", "boolean_count"])
def test_verified_completion_requires_nested_audit_and_hashed_raw_native_ending(fullgame, mutation):
    root, directory, _, ledger, report = fullgame
    cell = ledger["cells"][1]
    trial = directory / "trials" / cell["id"]
    receipt_path = directory / cell["cleanup_checks"][0]["path"]
    receipt = json.loads(receipt_path.read_text())
    if mutation == "audit_incomplete": report["trials"][1]["audit"]["complete"] = False
    elif mutation == "audit_issues": report["trials"][1]["audit"]["issues"] = ["failed"]
    elif mutation == "candidate_issues": report["trials"][1]["issues"] = ["failed"]
    elif mutation == "missing_cleanup": cell["cleanup_checks"] = []
    elif mutation == "boolean_count": report["counts"]["victories"] = True
    elif mutation.startswith("changed_"):
        name = {"run": "run.json", "report": "visual-report.json", "trajectory": "trajectory.jsonl",
            "backup": "save-backup/manifest.json", "restoration": "save-backup/restoration.json"}[mutation[8:]]
        with (trial / name).open("ab") as stream: stream.write(b"\n")
    else:
        trajectory = trial / "trajectory.jsonl"
        rows = [json.loads(line) for line in trajectory.read_text().splitlines()]
        if mutation == "raw_native_contradiction": rows[0]["obs"]["victory"] = False
        elif mutation == "missing_terminal": rows.pop()
        elif mutation == "extra_terminal": rows.append(dict(rows[-1]))
        elif mutation == "append_after_end": rows.append({"kind": "step", "obs": {"victory": True}})
        elif mutation == "wrong_raw_reason": rows[-1]["reason"] = "decision_budget"
        else: receipt["artifact_sha256"].pop("run.json")
        trajectory.write_text("".join(json.dumps(row) + "\n" for row in rows))
        receipt["artifact_sha256"]["trajectory.jsonl"] = hashlib.sha256(trajectory.read_bytes()).hexdigest()
        save(receipt_path, receipt)
        cell["cleanup_checks"][0]["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    save(directory / "ledger.json", ledger)
    save(directory / "comparison.json", report)
    view = comparison.comparison_view(root, "fullgame")
    assert view["fullgame_summary"] is None and view["issues"]
    if mutation != "boolean_count": assert view["trials"][1]["verified_fullgame_complete"] is None


@pytest.mark.parametrize("mutation", ["count_includes_pilot", "duplicate_trial", "wrong_cell_directory", "outside_directory", "wrong_requested_model", "wrong_cleanup_hash", "wrong_cleanup_cell", "unknown_trial"])
def test_inconsistent_saved_evidence_hides_totals_without_fabricating_results(fullgame, mutation):
    root, directory, _, ledger, report = fullgame
    if mutation == "count_includes_pilot":
        report["counts"]["verified_fullgame_completions"] = 2
    elif mutation == "duplicate_trial":
        report["trials"][2] = dict(report["trials"][1])
    elif mutation == "wrong_cell_directory":
        report["trials"][1]["directory"] = report["trials"][0]["directory"]
    elif mutation == "outside_directory":
        report["trials"][1]["directory"] = str(root.parent)
    elif mutation == "wrong_requested_model":
        report["trials"][1]["requested_model"] = "luna"
    elif mutation == "wrong_cleanup_hash":
        ledger["cells"][1]["cleanup_checks"][0]["sha256"] = "0" * 64
    elif mutation == "wrong_cleanup_cell":
        cleanup = directory / ledger["cells"][1]["cleanup_checks"][0]["path"]
        value = json.loads(cleanup.read_text()); value["cell_id"] = ledger["cells"][0]["id"]; save(cleanup, value)
        ledger["cells"][1]["cleanup_checks"][0]["sha256"] = hashlib.sha256(cleanup.read_bytes()).hexdigest()
    else:
        report["trials"][2]["id"] = "nonexistent"
    save(directory / "comparison.json", report); save(directory / "ledger.json", ledger)
    view = comparison.comparison_view(root, "fullgame")
    assert view["fullgame_summary"] is None and view["partial"] and view["issues"]
    assert len(view["trials"]) == 5


def test_missing_report_keeps_planned_conditions_and_unknown_metrics(fullgame):
    root, directory, _, _, _ = fullgame
    (directory / "comparison.json").unlink()
    view = comparison.comparison_view(root, "fullgame")
    assert len(view["trials"]) == 5 and view["fullgame_summary"] is None
    assert all(row["metrics"] is None and row["verified_fullgame_complete"] is None for row in view["trials"])


@pytest.mark.parametrize("mutation", ["ledger_mode", "unsafe_cell", "duplicate_cell", "missing_cell", "boolean_sector"])
def test_invalid_declared_protocol_or_ledger_is_refused(fullgame, mutation):
    root, directory, protocol, ledger, _ = fullgame
    if mutation == "ledger_mode":
        ledger["cells"][1]["mode"] = "hybrid"
    elif mutation == "missing_cell":
        ledger["cells"].pop()
    else:
        if mutation == "unsafe_cell": protocol["cells"][1]["id"] = "../outside"
        elif mutation == "duplicate_cell": protocol["cells"][1]["id"] = protocol["cells"][2]["id"]
        else: protocol["cells"][0]["stop_after_sector"] = True
        for cell, original in zip(ledger["cells"], protocol["cells"]):
            for key in ("id", "mode", "stop_after_sector"): cell[key] = original[key]
        protocol.pop("protocol_sha256"); protocol["protocol_sha256"] = digest(protocol); ledger["protocol_sha256"] = protocol["protocol_sha256"]
    save(directory / "protocol.json", protocol); save(directory / "ledger.json", ledger)
    with pytest.raises(ValueError): comparison.comparison_view(root, "fullgame")


def test_fullgame_exact_replay_and_image_use_existing_readonly_routes(fullgame, monkeypatch):
    root, directory, _, ledger, _ = fullgame
    trial = directory / "trials" / ledger["cells"][1]["id"]
    png = b"\x89PNG\r\n\x1a\nfixture"
    (trial / "frame.png").write_bytes(png)
    (trial / "trajectory.jsonl").write_text(json.dumps({"kind": "reset", "visual": {"before": {"path": "frame.png", "sha256": hashlib.sha256(png).hexdigest(), "frame_id": "frame", "width": 1280, "height": 720}}}))
    monkeypatch.setattr(api, "BENCH", root)
    row = comparison.comparison_view(root, "fullgame")["trials"][1]
    status, replay = asgi_request(api.create_app(), "/api/replay", row["replay_url"].split("?", 1)[1])
    assert status == 200 and replay["selected"] == row["selection"]
    status, image = asgi_request(api.create_app(), "/api/artifact", replay["item"]["visual"]["before"]["url"].split("?", 1)[1], json_response=False)
    assert status == 200 and image == png
