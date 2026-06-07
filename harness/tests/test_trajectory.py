"""Tests for ftl_bench.trajectory: TrajectoryRecorder + load_trajectory.

Exercises the JSONL header/record contract and the recorder->loader round-trip
using tmp_path. No game or subprocess is involved here.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ftl_bench import TrajectoryRecorder, load_trajectory
from ftl_bench.observation import Observation


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _read_lines(path: Path):
    return [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _make_obs(raw=None, **overrides):
    data = {
        "schema_version": 2,
        "tick": 5,
        "seed": 0,
        "game_started": True,
    }
    data.update(overrides)
    obs = Observation.from_dict(data)
    if raw is not None:
        obs.raw = raw
    return obs


# --------------------------------------------------------------------------
# header / construction
# --------------------------------------------------------------------------

def test_init_writes_single_meta_header(tmp_path):
    p = tmp_path / "traj.jsonl"
    TrajectoryRecorder(p, meta={"run": "abc"})
    lines = _read_lines(p)
    assert len(lines) == 1
    header = json.loads(lines[0])
    assert header["kind"] == "meta"
    assert header["i"] == -1
    assert header["meta"] == {"run": "abc"}
    assert isinstance(header["t"], float)


def test_init_default_meta_is_empty_dict(tmp_path):
    p = tmp_path / "traj.jsonl"
    TrajectoryRecorder(p)
    header = json.loads(_read_lines(p)[0])
    assert header["meta"] == {}


def test_init_none_meta_becomes_empty_dict(tmp_path):
    p = tmp_path / "traj.jsonl"
    TrajectoryRecorder(p, meta=None)
    header = json.loads(_read_lines(p)[0])
    assert header["meta"] == {}


def test_init_accepts_str_path(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(str(p))
    assert isinstance(rec.path, Path)
    assert p.exists()


def test_init_creates_parent_dirs(tmp_path):
    p = tmp_path / "deep" / "nested" / "traj.jsonl"
    TrajectoryRecorder(p)
    assert p.exists()
    assert p.parent.is_dir()


def test_init_starts_fresh_overwriting_existing(tmp_path):
    p = tmp_path / "traj.jsonl"
    p.write_text("garbage that should be wiped\n", encoding="utf-8")
    TrajectoryRecorder(p, meta={"x": 1})
    lines = _read_lines(p)
    assert len(lines) == 1
    assert json.loads(lines[0])["kind"] == "meta"


def test_init_counter_starts_at_zero(tmp_path):
    rec = TrajectoryRecorder(tmp_path / "traj.jsonl")
    assert rec.n == 0


# --------------------------------------------------------------------------
# record()
# --------------------------------------------------------------------------

def test_record_appends_after_header(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    rec.record("step", [{"type": "jump"}], _make_obs(raw={"tick": 9}))
    lines = _read_lines(p)
    assert len(lines) == 2
    assert json.loads(lines[0])["kind"] == "meta"
    body = json.loads(lines[1])
    assert body["kind"] == "step"
    assert body["i"] == 0


def test_record_entry_shape(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    actions = [{"type": "set_system_power", "system_id": 0, "level": 2}]
    raw = {"schema_version": 2, "tick": 12, "seed": 1, "game_started": True}
    rec.record("step", actions, _make_obs(raw=raw))
    body = json.loads(_read_lines(p)[1])
    assert set(body.keys()) == {"i", "t", "kind", "actions", "obs"}
    assert body["actions"] == actions
    assert body["obs"] == raw
    assert isinstance(body["t"], float)


def test_record_uses_obs_raw_attribute(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    obs = _make_obs(raw={"the": "raw", "payload": 1})
    rec.record("step", None, obs)
    body = json.loads(_read_lines(p)[1])
    assert body["obs"] == {"the": "raw", "payload": 1}


def test_record_obs_without_raw_attribute_is_none(tmp_path):
    # A plain object with no .raw -> getattr default None.
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    rec.record("step", [], SimpleNamespace())
    body = json.loads(_read_lines(p)[1])
    assert body["obs"] is None


def test_record_obs_none_is_none(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    rec.record("step", [], None)
    body = json.loads(_read_lines(p)[1])
    assert body["obs"] is None


def test_record_none_actions_becomes_empty_list(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    rec.record("reset", None, _make_obs(raw={}))
    body = json.loads(_read_lines(p)[1])
    assert body["actions"] == []


def test_record_empty_actions_becomes_empty_list(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    rec.record("reset", [], _make_obs(raw={}))
    body = json.loads(_read_lines(p)[1])
    assert body["actions"] == []


def test_record_consumes_iterable_actions(tmp_path):
    # actions is typed Iterable; a generator should be materialized to a list.
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    gen = (a for a in [{"type": "a"}, {"type": "b"}])
    rec.record("step", gen, _make_obs(raw={}))
    body = json.loads(_read_lines(p)[1])
    assert body["actions"] == [{"type": "a"}, {"type": "b"}]


def test_record_increments_index_and_counter(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    for _ in range(3):
        rec.record("step", [], _make_obs(raw={}))
    assert rec.n == 3
    bodies = [json.loads(l) for l in _read_lines(p)[1:]]
    assert [b["i"] for b in bodies] == [0, 1, 2]


def test_record_preserves_kind_string(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    rec.record("custom_kind", [], _make_obs(raw={}))
    assert json.loads(_read_lines(p)[1])["kind"] == "custom_kind"


def test_record_appends_rather_than_truncates(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    rec.record("step", [{"a": 1}], _make_obs(raw={"r": 1}))
    rec.record("step", [{"a": 2}], _make_obs(raw={"r": 2}))
    lines = _read_lines(p)
    assert len(lines) == 3  # header + 2 records
    assert json.loads(lines[1])["obs"] == {"r": 1}
    assert json.loads(lines[2])["obs"] == {"r": 2}


# --------------------------------------------------------------------------
# load_trajectory()
# --------------------------------------------------------------------------

def test_load_trajectory_reads_header_only(tmp_path):
    p = tmp_path / "traj.jsonl"
    TrajectoryRecorder(p, meta={"k": "v"})
    loaded = load_trajectory(p)
    assert len(loaded) == 1
    assert loaded[0]["kind"] == "meta"
    assert loaded[0]["meta"] == {"k": "v"}


def test_load_trajectory_accepts_str_path(tmp_path):
    p = tmp_path / "traj.jsonl"
    TrajectoryRecorder(p)
    loaded = load_trajectory(str(p))
    assert isinstance(loaded, list)
    assert loaded[0]["kind"] == "meta"


def test_load_trajectory_skips_blank_lines(tmp_path):
    p = tmp_path / "traj.jsonl"
    p.write_text(
        json.dumps({"i": -1, "kind": "meta", "meta": {}}) + "\n"
        + "\n"
        + "   \n"
        + json.dumps({"i": 0, "kind": "step"}) + "\n",
        encoding="utf-8",
    )
    loaded = load_trajectory(p)
    assert len(loaded) == 2
    assert loaded[0]["kind"] == "meta"
    assert loaded[1]["kind"] == "step"


def test_load_trajectory_empty_file_returns_empty_list(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    assert load_trajectory(p) == []


def test_load_trajectory_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_trajectory(tmp_path / "does_not_exist.jsonl")


def test_load_trajectory_invalid_json_raises(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text("{not valid json}\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_trajectory(p)


# --------------------------------------------------------------------------
# round-trip
# --------------------------------------------------------------------------

def test_round_trip_header_and_records(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p, meta={"scenario": "s1", "seed": 7})
    rec.record("reset", None, _make_obs(raw={"tick": 0, "paused": True}))
    rec.record(
        "step",
        [{"type": "jump", "node_id": 3}],
        _make_obs(raw={"tick": 1, "paused": True}),
    )

    loaded = load_trajectory(p)
    assert len(loaded) == 3

    header, r0, r1 = loaded
    assert header["kind"] == "meta"
    assert header["i"] == -1
    assert header["meta"] == {"scenario": "s1", "seed": 7}

    assert r0["kind"] == "reset"
    assert r0["i"] == 0
    assert r0["actions"] == []
    assert r0["obs"] == {"tick": 0, "paused": True}

    assert r1["kind"] == "step"
    assert r1["i"] == 1
    assert r1["actions"] == [{"type": "jump", "node_id": 3}]
    assert r1["obs"] == {"tick": 1, "paused": True}


def test_round_trip_preserves_indices_in_order(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    for k in range(5):
        rec.record("step", [{"n": k}], _make_obs(raw={"tick": k}))
    loaded = load_trajectory(p)
    records = loaded[1:]
    assert [r["i"] for r in records] == [0, 1, 2, 3, 4]
    assert [r["obs"]["tick"] for r in records] == [0, 1, 2, 3, 4]


def test_round_trip_with_real_observation_raw(tmp_path):
    # Observation.from_dict stores the full source dict as .raw; that's what is logged.
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p)
    source = {
        "schema_version": 2,
        "tick": 42,
        "seed": 99,
        "game_started": True,
        "paused": True,
        "player_ship": {"hull": {"current": 30, "max": 30}},
    }
    obs = Observation.from_dict(source)
    rec.record("step", [{"type": "noop"}], obs)
    loaded = load_trajectory(p)
    assert loaded[1]["obs"] == source


def test_round_trip_unicode_in_meta_and_actions(tmp_path):
    p = tmp_path / "traj.jsonl"
    rec = TrajectoryRecorder(p, meta={"note": "café — ünïcödé ✓"})
    rec.record("step", [{"text": "ürön drönes"}], _make_obs(raw={"msg": "✓"}))
    loaded = load_trajectory(p)
    assert loaded[0]["meta"]["note"] == "café — ünïcödé ✓"
    assert loaded[1]["actions"][0]["text"] == "ürön drönes"
    assert loaded[1]["obs"]["msg"] == "✓"
