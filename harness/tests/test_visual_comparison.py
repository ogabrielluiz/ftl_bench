"""Read-only API projection: authoritative results, confined paths, partial runs."""
import hashlib
import json
import asyncio
import importlib.util
from urllib.parse import urlencode
from pathlib import Path
import sys

import pytest
from ftl_bench.cli import _bench_root

sys.path.insert(0, str(_bench_root() / "adapter"))
import visual_comparison as comparison

spec = importlib.util.spec_from_file_location("dashboard_comparison_candidate_api",
    _bench_root() / "adapter/ftl_live.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def matrix(tmp_path):
    directory = tmp_path / "matrix"
    protocol = {"contract": "ftl-visual-challenge-matrix-v1", "models": ["sol", "luna"],
        "budgets": {"decisions": 60, "wall_seconds": 1800, "idle_decisions": 8}}
    protocol["protocol_sha256"] = hashlib.sha256(json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    save(directory / "protocol.json", protocol)
    cell = {"id": "sol/image/combat/repeat-01", "model": "sol", "mode": "image", "challenge": "combat", "repetition": 1, "status": "finished"}
    save(directory / "ledger.json", {"protocol_sha256": protocol["protocol_sha256"], "cells": [cell, {**cell, "id": "luna/image/combat/repeat-01", "model": "luna", "status": "planned"}]})
    trial = directory / "trials" / cell["id"] / "repetition-01/combat"
    save(trial / "run.json", {"track": "visual-v1", "model": "sol", "provider": "codex", "challenge": "combat", "observation_mode": "image", "repetition": 1})
    (trial / "trajectory.jsonl").write_text('{"kind":"end"}\n')
    condition = {"scenario": "combat", "model": "sol", "mode": "image", "attempts": 1, "outcomes": {"budget_exhausted": 1}, "task_success_rate": 0.0}
    report = {"report_version": "visual-comparison-v1", "protocol_sha256": protocol["protocol_sha256"], "qualified_scoped_comparison": False,
        "conditions": [condition], "trials": [{"directory": str(trial), "scenario": "combat", "model": "sol", "mode": "image", "repetition": 1,
            "outcome_category": "budget_exhausted", "task_success": False, "eligible": True, "model_calls": {"usage": {"complete_totals": {"input_tokens": None}}}}]}
    save(directory / "comparison.json", report)
    return tmp_path, directory, trial, report


def test_passes_authoritative_conditions_without_scoring(matrix):
    root, directory, trial, report = matrix
    result = comparison.comparison_view(root, "matrix")
    assert result["conditions"] == report["conditions"]
    assert result["partial"] is True
    assert result["counts"] == {"total": 2, "planned": 1, "running": 0, "finished": 1, "unknown": 0}
    assert result["trials"][0]["model_calls"]["usage"]["complete_totals"]["input_tokens"] is None
    assert result["trials"][0]["replay_url"].startswith('/?sel=matrix%2Ftrials%2Fsol')
    assert result["trials"][1]["selection"] is None
    assert result["valid_for_full_game_comparison"] is False


def test_partial_report_does_not_fabricate_zero_results(matrix):
    root, directory, _, _ = matrix
    (directory / "comparison.json").write_text('{"trials":')
    result = comparison.comparison_view(root, "matrix")
    assert result["conditions"] == []
    assert result["trials"][0]["task_success"] is None
    assert result["qualified_scoped_comparison"] is False
    assert len(result["issues"]) == 2


def test_ledger_report_refresh_gap_disables_qualification(matrix):
    root, directory, _, report = matrix
    report.update(qualified_scoped_comparison=True, trials=[])
    save(directory / "comparison.json", report)
    result = comparison.comparison_view(root, "matrix")
    assert result["partial"] and not result["qualified_scoped_comparison"]
    assert result["issues"]


def test_wrong_report_identity_is_not_used(matrix):
    root, directory, _, report = matrix
    report["protocol_sha256"] = "different"
    save(directory / "comparison.json", report)
    assert comparison.comparison_view(root, "matrix")["conditions"] == []


@pytest.mark.parametrize("key", ["../outside", "matrix/../../outside"])
def test_path_traversal_rejected(matrix, key):
    with pytest.raises(ValueError):
        comparison.comparison_view(matrix[0], key)


def test_untrusted_report_trial_cannot_link_outside_its_cell(matrix):
    root, directory, _, report = matrix
    report["trials"][0]["directory"] = str(root.parent)
    save(directory / "comparison.json", report)
    row = comparison.comparison_view(root, "matrix")["trials"][0]
    assert row["replay_url"] is None and row["selection"] is None


def test_symlinked_json_is_rejected(matrix):
    root, directory, _, _ = matrix
    path = directory / "comparison.json"
    backup = root / "external.json"
    backup.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(backup)
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = comparison.comparison_view(root, "matrix")
    assert result["conditions"] == [] and result["issues"]


def test_link_rejection_is_covered_without_windows_symlink_privileges(matrix, monkeypatch):
    root, directory, _, _ = matrix
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path:
        path == directory / "comparison.json" or original(path))
    view = comparison.comparison_view(root, "matrix")
    assert view["conditions"] == [] and view["issues"]


def test_lexical_path_without_matching_ancestor_cannot_loop_forever(matrix):
    root, _, _, _ = matrix
    # The resolved target is confined, but lexical ancestors never reach root.
    path = root.parent / (root.name + "-nonexistent") / ".." / root.name / "matrix"
    with pytest.raises(ValueError, match="ancestor"):
        comparison.safe_path(root, path)


def test_size_limit_rejects_large_json(matrix, monkeypatch):
    monkeypatch.setattr(comparison, "MAX_JSON_BYTES", 10)
    with pytest.raises(ValueError, match="size limit"):
        comparison.comparison_view(matrix[0], "matrix")


def test_catalog_only_exposes_verified_matrix_protocol(matrix):
    root, _, _, _ = matrix
    save(root / "other/protocol.json", {"contract": "something-else"})
    assert [item["key"] for item in comparison.comparison_catalog(root)["comparisons"]] == ["matrix"]


def test_labels_distinguish_model_setup_and_scripted_probe():
    run = {"track": "visual-v1", "challenge": "combat", "model": "sol", "observation_mode": "image", "repetition": 2}
    assert comparison.trial_label(run, "trajectory") == "combat · sol · image · Repeat 2"
    assert "Setup check" in comparison.trial_label({**run, "setup_only": True}, "trajectory")
    assert "Scripted probe" in comparison.trial_label({**run, "setup_only": True, "reason": "timing_probe_completed"}, "trajectory")


def asgi_request(app, path, query="", method="GET", json_response=True):
    """Exercise real routing/serialization without TestClient/httpx or a server."""
    async def request():
        messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
            "root_path": "", "query_string": query.encode(), "headers": [],
            "server": ("test", 80), "client": ("test", 1)}
        await app(scope, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, json.loads(body) if json_response else body
    return asyncio.run(request())


def test_api_scoped_readonly_endpoint(matrix, monkeypatch):
    monkeypatch.setattr(api, "BENCH", matrix[0])
    app = api.create_app()
    status, catalog = asgi_request(app, "/api/comparisons")
    assert status == 200 and catalog["comparisons"][0]["key"] == "matrix"
    status, view = asgi_request(app, "/api/comparisons", "key=matrix")
    assert status == 200 and view["counts"]["finished"] == 1
    assert asgi_request(app, "/api/comparisons", "key=..%2Foutside")[0] == 404
    assert asgi_request(app, "/api/comparisons", method="POST")[0] == 405


def test_equal_trial_count_with_wrong_identity_cannot_qualify(matrix):
    root, directory, _, report = matrix
    report["qualified_scoped_comparison"] = True
    report["trials"][0].update(model="other", directory=str(root / "missing"))
    save(directory / "comparison.json", report)
    view = comparison.comparison_view(root, "matrix")
    assert view["partial"] and not view["qualified_scoped_comparison"]
    assert view["trials"][0]["outcome_category"] is None


def test_unreadable_run_preserves_saved_exclusion_and_exact_replay(matrix):
    root, directory, trial, report = matrix
    report["trials"] = [{"directory": str(trial), "eligible": False, "exclusions": ["unreadable_run:missing report"]}]
    save(directory / "comparison.json", report)
    row = comparison.comparison_view(root, "matrix")["trials"][0]
    assert row["eligible"] is False
    assert row["exclusions"] == ["unreadable_run:missing report"]
    assert row["selection"] and row["task_success"] is None


def test_duplicate_trial_count_cannot_hide_missing_finished_cell(matrix):
    root, directory, _, report = matrix
    ledger = json.loads((directory / "ledger.json").read_text())
    ledger["cells"][1]["status"] = "finished"
    save(directory / "ledger.json", ledger)
    report["trials"].append(dict(report["trials"][0]))
    report["qualified_scoped_comparison"] = True
    save(directory / "comparison.json", report)
    view = comparison.comparison_view(root, "matrix")
    assert view["partial"] and not view["qualified_scoped_comparison"]
    assert view["trials"][0]["task_success"] is None


def test_malformed_report_returns_404_via_real_asgi_route(matrix, monkeypatch):
    root, directory, _, report = matrix
    report["conditions"] = [None]
    save(directory / "comparison.json", report)
    monkeypatch.setattr(api, "BENCH", root)
    assert asgi_request(api.create_app(), "/api/comparisons", "key=matrix")[0] == 404


def test_complete_matching_saved_report_can_qualify(matrix):
    root, directory, _, report = matrix
    ledger = json.loads((directory / "ledger.json").read_text())
    ledger["cells"] = ledger["cells"][:1]
    save(directory / "ledger.json", ledger)
    report["qualified_scoped_comparison"] = True
    save(directory / "comparison.json", report)
    view = comparison.comparison_view(root, "matrix")
    assert view["qualified_scoped_comparison"] and not view["partial"]
    assert not view["valid_for_full_game_comparison"]


def test_protocol_hash_uses_same_unicode_encoding_as_matrix_controller(matrix):
    root, directory, _, _ = matrix
    protocol = json.loads((directory / "protocol.json").read_text())
    protocol.pop("protocol_sha256")
    protocol["scope"] = "Comparação de desafios"
    protocol["protocol_sha256"] = hashlib.sha256(json.dumps(protocol,
        sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    save(directory / "protocol.json", protocol)
    ledger = json.loads((directory / "ledger.json").read_text())
    ledger["protocol_sha256"] = protocol["protocol_sha256"]
    save(directory / "ledger.json", ledger)
    assert comparison.comparison_view(root, "matrix")["protocol_sha256"] == protocol["protocol_sha256"]


def test_comparison_exact_selection_roundtrips_through_replay_and_image_routes(matrix, monkeypatch):
    root, _, trial, _ = matrix
    png = b"\x89PNG\r\n\x1a\n" + b"fixture-image"
    (trial / "first.png").write_bytes(png)
    (trial / "trajectory.jsonl").write_text(json.dumps({"kind": "fixture_setup", "visual": {
        "before": {"path": "first.png", "sha256": hashlib.sha256(png).hexdigest(),
                   "frame_id": "first", "width": 1280, "height": 720}}}) + "\n")
    monkeypatch.setattr(api, "BENCH", root)
    app = api.create_app()
    _, view = asgi_request(app, "/api/comparisons", "key=matrix")
    selection = view["trials"][0]["selection"]
    status, replay = asgi_request(app, "/api/replay", urlencode({"sel": selection}))
    assert status == 200 and replay["selected"] == selection
    assert replay["item"]["record_kind"] == "fixture_setup"
    frame = replay["item"]["visual"]["before"]
    assert frame["frame_id"] == "first"
    query = frame["url"].split("?", 1)[1]
    status, image = asgi_request(app, "/api/artifact", query, json_response=False)
    assert status == 200 and image == png
    (trial / "first.png").write_bytes(png + b"tampered")
    assert asgi_request(app, "/api/artifact", query)[0] == 404
