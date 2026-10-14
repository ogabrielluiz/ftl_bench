"""Offline visual replay and exact-record artifact boundaries."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import ftl_live as live

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf9sAAAAASUVORK5CYII=")


@pytest.fixture
def visual_run(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "BENCH", tmp_path)
    monkeypatch.setattr(live, "process_status", lambda: {"known": False, "alive": None})
    live._snapshot_cache.clear()
    live._score_cache.clear()
    directory = tmp_path / "visual-run"
    directory.mkdir()
    (directory / "screens").mkdir()
    (directory / "screens" / "before.png").write_bytes(PNG)
    frame = {"path": "screens/before.png", "width": 1280, "height": 720, "frame_id": "f-13",
             "sha256": hashlib.sha256(PNG).hexdigest()}
    visual = {"observation_mode": "hybrid", "before": frame, "after": {**frame, "frame_id": "f-14"},
              "inputs": [{"type": "click", "x": 1150, "y": 620, "delivery": "delivered"}],
              "advance": {"requested_frames": 60, "actual_frames": 12},
              "outcome": {"status": "unknown", "summary": "Input delivered; game action unverified."},
              "visible_summary": {"fuel": 5}}
    records = [{"kind": "meta", "meta": {"agent": "visual", "run_id": "visual-run"}}]
    records.extend({"kind": "step", "i": i, "visual": visual, "actions": [],
                    "model": {"model": "gpt-6.1-sol", "latency_seconds": 2.5}, "obs": {}}
                   for i in range(125))
    records.append({"kind": "end", "status": "completed", "reason": "fixture"})
    path = directory / "GAME-s1.jsonl"
    write_records(path, records)
    return path, records


def write_records(path, records):
    path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    live._snapshot_cache.clear()


def test_visual_replay_reads_entire_history_and_does_not_collapse_decisions(visual_run):
    path, _ = visual_run
    snapshot = live.build("visual-run/GAME-s1")
    assert snapshot["header"]["visual_steps"] == 125
    assert len(snapshot["feed"]) == 120
    assert all(not row.get("collapsed") for row in snapshot["feed"])
    replay = live.replay_snapshot("visual-run/GAME-s1", 0)
    assert replay["index"] == 0 and replay["total"] == 125
    assert replay["item"]["i"] == 0
    visual = replay["item"]["visual"]
    assert "record=1&phase=before" in visual["before"]["url"]
    assert visual["advance"] == {"requested_frames": 60, "actual_frames": 12}
    assert visual["inputs"][0]["delivery"] == "delivered"
    assert visual["outcome"]["status"] == "unknown"
    assert "obs" not in replay["item"]
    assert live.replay_snapshot("visual-run/GAME-s1")["item"]["i"] == 124
    with pytest.raises(ValueError):
        live.replay_snapshot("visual-run/GAME-s1", 125)


def test_recorded_image_preserves_exact_bytes_and_hash(visual_run):
    path, _ = visual_run
    image, mime = live.recorded_image("visual-run/GAME-s1", 1, "before")
    assert image == path.parent / "screens" / "before.png"
    assert image.read_bytes() == PNG
    assert mime == "image/png"
    image.write_bytes(PNG + b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        live.recorded_image("visual-run/GAME-s1", 1, "before")


@pytest.mark.parametrize("dispatched", [False, True])
def test_interference_decision_remains_in_replay_with_plans_distinct_from_sent_inputs(visual_run, dispatched):
    path, records = visual_run
    planned = [{"type": "click", "x": 100, "y": 200, "button": "left"}]
    guard = {"packet_dispatched": dispatched, "external_input_detected": True,
             "expected_generation": "0", "observed_generation": "1", "action_seq": 124}
    visual = {**records[-2]["visual"], "after": None, "planned_inputs": planned,
              "inputs": [{**planned[0], "delivery": "unknown"}] if dispatched else [],
              "external_input_guard": guard, "advance": {"requested_frames": 60, "actual_frames": None}}
    records[-1:] = [{"kind": "external_interference", "i": 125, "visual": visual,
                     "actions": planned if dispatched else [], "model": {"model": "fake"}, "obs": {}},
                    {"kind": "end", "status": "interrupted", "reason": "external_interference"}]
    write_records(path, records)
    replay = live.replay_snapshot("visual-run/GAME-s1")
    assert replay["total"] == 126 and replay["item"]["record_kind"] == "external_interference"
    assert replay["item"]["visual"]["planned_inputs"] == planned
    assert replay["item"]["visual"]["external_input_guard"] == guard
    assert replay["item"]["visual"]["inputs"] == visual["inputs"]
    assert "after" not in replay["item"]["visual"]
    snapshot = live.build("visual-run/GAME-s1")
    assert snapshot["header"]["visual_steps"] == 126
    assert snapshot["header"]["status"] == "interrupted"
    assert snapshot["feed"][-1]["record_kind"] == "external_interference"
    assert snapshot["feed"][-1]["visual"]["external_input_guard"] == guard
    assert not snapshot["feed"][-1].get("collapsed")


def test_relative_run_root_keeps_full_selection_keys_in_image_urls(visual_run, monkeypatch):
    path, _ = visual_run
    monkeypatch.chdir(path.parent.parent.parent)
    monkeypatch.setattr(live, "BENCH", Path(path.parent.parent.name))
    replay = live.replay_snapshot("visual-run/GAME-s1", 0)
    assert "sel=visual-run%2FGAME-s1" in replay["item"]["visual"]["before"]["url"]


@pytest.mark.parametrize("name", ["../outside.png", "screens/../../outside.png", "/outside.png",
                                  "C:/outside.png", "C:outside.png", "\\\\server\\outside.png",
                                  "screens\\before.png", "screens/./before.png", "screens/before.png:secret", "\x00"])
def test_recorded_paths_cannot_escape_or_use_windows_aliases(visual_run, name):
    path, records = visual_run
    records[1]["visual"]["before"]["path"] = name
    write_records(path, records)
    with pytest.raises(ValueError):
        live.recorded_image("visual-run/GAME-s1", 1, "before")


@pytest.mark.parametrize("selection,record,phase", [
    ("../visual-run/GAME-s1", 1, "before"), ("visual-run/GAME-s1", 0, "before"),
    ("visual-run/GAME-s1", -1, "before"), ("visual-run/GAME-s1", 999, "before"),
    ("visual-run/GAME-s1", 1, "other"),
])
def test_only_existing_record_image_slots_are_servable(visual_run, selection, record, phase):
    with pytest.raises(ValueError):
        live.recorded_image(selection, record, phase)


def test_image_named_text_file_is_not_servable(visual_run):
    path, records = visual_run
    (path.parent / "screens" / "before.png").write_text("not an image")
    records[1]["visual"]["before"].pop("sha256")
    write_records(path, records)
    with pytest.raises(ValueError, match="content"):
        live.recorded_image("visual-run/GAME-s1", 1, "before")


def test_symlink_image_escape_is_rejected(visual_run, tmp_path):
    path, records = visual_run
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    link = path.parent / "screens" / "linked.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation unavailable on this Windows account")
    records[1]["visual"]["before"]["path"] = "screens/linked.png"
    write_records(path, records)
    with pytest.raises(ValueError, match="outside"):
        live.recorded_image("visual-run/GAME-s1", 1, "before")


def test_legacy_trajectory_replay_is_empty_and_score_exclusion_is_preserved(visual_run):
    path, records = visual_run
    for row in records:
        row.pop("visual", None)
    write_records(path, records)
    (path.parent / "run.json").write_text(json.dumps({"run_id": "visual-run", "status": "completed",
        "validation_status": "diagnostic_only", "validation_limitations": ["Store-exit defect."]}))
    replay = live.replay_snapshot("visual-run/GAME-s1")
    assert replay == {"selected": "visual-run/GAME-s1", "total": 0, "index": None, "item": None}
    state = live.build("visual-run/GAME-s1")
    assert state["header"]["visual_steps"] == 0
    assert state["run"]["validation"]["comparison_eligible"] is False


def test_artifact_http_response_uses_image_type_and_missing_images_are_404(visual_run):
    import asyncio
    from urllib.parse import urlencode
    app = live.create_app()

    async def request(path, **params):
        messages = []

        request_received = False
        disconnected = asyncio.Event()

        async def receive():
            nonlocal request_received
            if not request_received:
                request_received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                disconnected.set()

        await app({"type": "http", "http_version": "1.1", "method": "GET", "scheme": "http",
                   "path": path, "raw_path": path.encode(), "query_string": urlencode(params).encode(),
                   "headers": [], "server": ("127.0.0.1", 8765), "client": ("127.0.0.1", 1234)}, receive, send)
        start = next(row for row in messages if row["type"] == "http.response.start")
        body = b"".join(row.get("body", b"") for row in messages if row["type"] == "http.response.body")
        return start["status"], dict(start["headers"]), body

    status, headers, body = asyncio.run(request("/api/artifact", sel="visual-run/GAME-s1", record=1, phase="before"))
    assert status == 200 and body == PNG
    assert headers[b"content-type"] == b"image/png"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert asyncio.run(request("/api/artifact", sel="visual-run/GAME-s1", record=0, phase="before"))[0] == 404
    status, _, body = asyncio.run(request("/api/replay", sel="visual-run/GAME-s1", index=0))
    assert status == 200 and json.loads(body)["total"] == 125
