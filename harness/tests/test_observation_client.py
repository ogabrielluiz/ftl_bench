import json
import os
from pathlib import Path

import pytest

from ftl_bench.observation import (
    ObservationClient,
    Observation,
    ObservationValidationError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "observation_sample.json"


def test_read_latest_returns_observation():
    client = ObservationClient(FIXTURE)
    obs = client.read_latest()
    assert isinstance(obs, Observation)
    assert obs.tick == 120
    assert obs.seed == 1234567
    assert obs.game_started is True


def test_player_ship_hull_parsed():
    obs = ObservationClient(FIXTURE).read_latest()
    assert obs.player_ship["hull"]["current"] == 30
    assert obs.player_ship["hull"]["max"] == 30


def test_enemy_ship_is_none_when_null():
    obs = ObservationClient(FIXTURE).read_latest()
    assert obs.enemy_ship is None


def test_missing_file_raises(monkeypatch):
    # A genuinely-missing file is now retried (FileNotFoundError is an OSError subclass) and
    # re-raised after the retry budget — patch sleep so the test stays fast.
    import ftl_bench.observation as obs_mod
    monkeypatch.setattr(obs_mod.time, "sleep", lambda *_a, **_k: None)
    client = ObservationClient(Path("/nonexistent/observation.json"))
    with pytest.raises(FileNotFoundError):
        client.read_latest()


def test_schema_version_mismatch_raises(tmp_path):
    bad = tmp_path / "obs.json"
    bad.write_text(json.dumps({"schema_version": 999, "tick": 1, "seed": 0,
                               "game_started": False}))
    client = ObservationClient(bad)
    with pytest.raises(ObservationValidationError):
        client.read_latest()


def test_missing_required_field_raises(tmp_path):
    bad = tmp_path / "obs.json"
    bad.write_text(json.dumps({"schema_version": 1, "tick": 1}))
    client = ObservationClient(bad)
    with pytest.raises(ObservationValidationError):
        client.read_latest()


def test_changing_state_detected(tmp_path):
    p = tmp_path / "obs.json"
    p.write_text(json.dumps({"schema_version": 1, "tick": 10, "seed": 1,
                             "game_started": True}))
    client = ObservationClient(p)
    first = client.read_latest()
    p.write_text(json.dumps({"schema_version": 1, "tick": 20, "seed": 1,
                             "game_started": True}))
    second = client.read_latest()
    assert first.tick == 10
    assert second.tick == 20


def test_transient_partial_json_and_file_lock_are_retried(monkeypatch, tmp_path):
    import ftl_bench.observation as obs_mod
    snapshots = iter([PermissionError("sharing violation"), '{"schema_version":',
                      json.dumps({"schema_version": 3, "tick": 2, "seed": 1, "game_started": True})])
    def read(_path, **_kwargs):
        result = next(snapshots)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(obs_mod, "_read_observation_text", read)
    monkeypatch.setattr(obs_mod.time, "sleep", lambda _: None)
    assert ObservationClient(tmp_path / "observation.json").read_latest().tick == 2


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing regression")
def test_windows_reader_allows_atomic_replace_and_keeps_original_snapshot(tmp_path):
    import ctypes
    from ctypes import wintypes
    from ftl_bench.observation import _open_observation_text

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    replace = kernel.ReplaceFileW
    replace.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID)
    replace.restype = wintypes.BOOL
    path = tmp_path / "observation.json"
    replacement = tmp_path / "replacement.json"
    first = {"schema_version": 3, "tick": 1, "seed": 7, "game_started": True,
             "event": {"text": "Crew São Paulo"}}
    second = {**first, "tick": 2, "event": {"text": "New observation Ω"}}
    path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    replacement.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    with _open_observation_text(path) as existing:
        # Read only after replacement: Windows must retain the opened old snapshot.
        # Match the native writer's ReplaceFile contract. MoveFileEx/os.replace
        # cannot replace an open destination on this Windows installation, even
        # with FILE_SHARE_DELETE, whereas ReplaceFile preserves both snapshots.
        if not replace(str(path), str(replacement), None, 0, None, None):
            raise ctypes.WinError(ctypes.get_last_error())
        assert json.loads(existing.read()) == first
        current = ObservationClient(path).read_latest()
        assert current.tick == 2 and current.event["text"] == "New observation Ω"
    assert ObservationClient(path).read_latest().tick == 2
