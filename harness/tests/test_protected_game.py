"""Protect originals, preserve generated saves, and refuse unowned game processes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import ftl_bench.protected_game as protected


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setattr(protected, "_processes", lambda: [])
    save = tmp_path / "save"
    save.mkdir()
    for name in ("ae_prof.sav", "continue.sav", "hs_prof_backup.sav", "hs_prof.sav", "hs_version.sav", "prof.sav"):
        (save / name).write_bytes(("original " + name).encode())
    bridge = tmp_path / "bridge.lua"
    bridge.write_text("bridge")
    return protected.ProtectedGame(save, tmp_path / "backup", bridge, tmp_path / "game")


def test_all_original_saves_restored_and_generated_save_preserved_outside_live_folder(game):
    originals = {p.name: p.read_bytes() for p in game.save.glob("*.sav")}
    game.backup_saves()
    for p in game.save.glob("*.sav"):
        p.write_bytes(b"benchmark changed this")
    (game.save / "continue.sav").unlink()  # game can remove a save when a run ends
    (game.save / "new_campaign.sav").write_bytes(b"generated during benchmark")
    (game.save / "user-notes.txt").write_text("keep")
    game.restore_saves()
    assert {p.name: p.read_bytes() for p in game.save.glob("*.sav")} == originals
    assert (game.backup / "benchmark-generated/new_campaign.sav").read_bytes() == b"generated during benchmark"
    assert (game.save / "user-notes.txt").read_text() == "keep"
    receipt = json.loads((game.backup / "restoration.json").read_text())
    assert receipt["verified"] and all(receipt["files"].values()) and len(receipt["files"]) == 6
    assert receipt["generated_saves_preserved"] == {"new_campaign.sav": hashlib.sha256(b"generated during benchmark").hexdigest()}


def test_corrupted_backup_refuses_before_any_live_file_is_changed(game):
    game.backup_saves()
    (game.backup / "prof.sav").write_bytes(b"corrupted backup")
    before = {p.name: p.read_bytes() for p in game.save.glob("*.sav")}
    with pytest.raises(RuntimeError, match="backup changed"):
        game.restore_saves()
    assert {p.name: p.read_bytes() for p in game.save.glob("*.sav")} == before
    assert not (game.backup / "restoration.json").exists()


def test_generated_save_is_not_removed_until_backup_is_verified(game, monkeypatch):
    game.backup_saves()
    generated = game.save / "new.sav"
    generated.write_bytes(b"must preserve")
    copy = protected.shutil.copy2

    def corrupt(src, dest, *args, **kwargs):
        if Path(src) == generated:
            Path(dest).write_bytes(b"truncated")
            return dest
        return copy(src, dest, *args, **kwargs)

    monkeypatch.setattr(protected.shutil, "copy2", corrupt)
    with pytest.raises(RuntimeError, match="Generated save backup verification"):
        game.restore_saves()
    assert generated.read_bytes() == b"must preserve"


def test_restore_does_not_overwrite_earlier_generated_save_archive(game):
    game.backup_saves()
    generated = game.save / "new.sav"
    generated.write_bytes(b"new run")
    archived = game.backup / "benchmark-generated/new.sav"
    archived.parent.mkdir()
    archived.write_bytes(b"previous preserved save")
    with pytest.raises(RuntimeError, match="already contains different"):
        game.restore_saves()
    assert generated.read_bytes() == b"new run"
    assert archived.read_bytes() == b"previous preserved save"


def test_unsafe_original_target_preflight_prevents_partial_restoration(game):
    game.backup_saves()
    (game.save / "ae_prof.sav").write_bytes(b"still benchmark data")
    (game.save / "prof.sav").unlink()
    (game.save / "prof.sav").mkdir()
    with pytest.raises(RuntimeError, match="Unsafe original"):
        game.restore_saves()
    assert (game.save / "ae_prof.sav").read_bytes() == b"still benchmark data"


def test_restore_refuses_to_touch_saves_when_game_is_running(game, monkeypatch):
    game.backup_saves()
    (game.save / "ae_prof.sav").write_bytes(b"currently playing")
    monkeypatch.setattr(protected, "_processes", lambda: [{"id": 1}])
    with pytest.raises(RuntimeError, match="still running"):
        game.restore_saves()
    assert (game.save / "ae_prof.sav").read_bytes() == b"currently playing"


@pytest.mark.parametrize("unsafe_name", ["../outside.sav", "different.txt"])
def test_tampered_manifest_path_is_rejected(game, unsafe_name):
    game.backup_saves()
    game.manifest["files"] = {unsafe_name: "0" * 64}
    with pytest.raises(RuntimeError, match="Unsafe save manifest"):
        game.restore_saves()


def test_existing_backup_is_not_overwritten(game):
    game.backup_saves()
    manifest = (game.backup / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        game.backup_saves()
    assert (game.backup / "manifest.json").read_bytes() == manifest


def test_previous_bridge_is_restored_alongside_original_saves(game):
    game.backup_saves()
    (game.backup / "ftl_bench_dev.lua").write_bytes(b"original bridge")
    (game.save / "ftl_bench_dev.lua").write_bytes(b"fixture bridge")
    game.restore_saves()
    assert (game.save / "ftl_bench_dev.lua").read_bytes() == b"original bridge"


def test_exception_in_protected_context_still_restores_originals(game):
    if protected.os.name != "nt":
        pytest.skip("protected launch is Windows-only")
    original = (game.save / "prof.sav").read_bytes()
    with pytest.raises(ValueError, match="simulated failure"):
        with game.protected():
            (game.save / "prof.sav").write_bytes(b"modified")
            raise ValueError("simulated failure")
    assert (game.save / "prof.sav").read_bytes() == original


@pytest.mark.parametrize("unowned", ["older", "other_path", "never_launched"])
def test_stop_refuses_unowned_game_processes(game, monkeypatch, unowned):
    game.launched_at = datetime.now(timezone.utc)
    process = {"id": 123, "path": str(game.game / "FTLGame.exe"),
               "started": (game.launched_at + timedelta(seconds=1)).isoformat()}
    if unowned == "older":
        process["started"] = (game.launched_at - timedelta(seconds=1)).isoformat()
    elif unowned == "other_path":
        process["path"] = str(game.game / "other/FTLGame.exe")
    else:
        game.launched_at = None
    monkeypatch.setattr(protected, "_processes", lambda: [process])
    monkeypatch.setattr(protected, "_powershell", lambda *a, **kw: pytest.fail("must not stop unowned process"))
    with pytest.raises(RuntimeError, match="Unowned"):
        game.stop()


def test_steam_path_is_derived_from_steamapps_common_game_layout(game):
    game.game = Path("C:/Steam/steamapps/common/FTL Faster Than Light")
    assert game.game.parents[2] / "steam.exe" == Path("C:/Steam/steam.exe")


@pytest.mark.parametrize("states", [[(False, False)], [(True, True)], [(True, False), (False, False)]])
def test_launch_accepts_main_menu_without_requiring_game_pause(game, monkeypatch, tmp_path, states):
    steam = tmp_path / "Steam"
    game.game = steam / "steamapps/common/FTL Faster Than Light"
    game.game.mkdir(parents=True)
    (game.game / "FTLGame.exe").write_bytes(b"mock")
    (steam / "steam.exe").write_bytes(b"mock")
    game.backup_saves()
    observed = iter(states)
    calls, sleeps = [], []

    class Client:
        def __init__(self, path):
            pass
        def read_latest(self):
            started, paused = next(observed)
            return SimpleNamespace(game_started=started, paused=paused)

    monkeypatch.setattr(protected, "ObservationClient", Client)
    monkeypatch.setattr(protected.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(protected.time, "sleep", lambda seconds: sleeps.append(seconds))
    game.launch()
    assert len(calls) == 1
    assert calls[0][0][0] == [str(steam / "steam.exe"), "-applaunch", "212680"]
    assert len(sleeps) == len(states) - 1
    assert game.launched_at is not None


def test_launch_timeout_mentions_both_ready_states(game, monkeypatch, tmp_path):
    steam = tmp_path / "Steam"
    game.game = steam / "steamapps/common/FTL Faster Than Light"
    game.game.mkdir(parents=True)
    (game.game / "FTLGame.exe").write_bytes(b"mock")
    (steam / "steam.exe").write_bytes(b"mock")
    game.backup_saves()
    clocks = iter([0, 2])
    monkeypatch.setattr(protected.time, "monotonic", lambda: next(clocks))
    monkeypatch.setattr(protected.subprocess, "Popen", lambda *args, **kwargs: None)
    with pytest.raises(TimeoutError, match="main-menu or paused-game"):
        game.launch(timeout=1)
