"""A timed-out Steam request remains unsafe even while no FTL process exists."""
from types import SimpleNamespace
import json

import pytest
import ftl_bench.protected_game as protected


@pytest.fixture
def pending_steam_request(tmp_path, monkeypatch):
    save = tmp_path / "save"
    save.mkdir()
    for name in ("ae_prof.sav", "continue.sav", "hs_continue.sav", "hs_prof.sav",
                 "hs_prof_backup.sav", "hs_version.sav", "prof.sav"):
        (save / name).write_bytes(("original " + name).encode())
    bridge = tmp_path / "bridge.lua"
    bridge.write_bytes(b"prospective bridge")
    (save / "ftl_bench_dev.lua").write_bytes(b"original bridge")
    steam = tmp_path / "Steam"
    game_dir = steam / "steamapps/common/FTL Faster Than Light"
    game_dir.mkdir(parents=True)
    (game_dir / "FTLGame.exe").write_bytes(b"fake FTL executable")
    (steam / "steam.exe").write_bytes(b"fake Steam executable")
    launches = []
    clock = [0.0]

    class UnreadyClient:
        def __init__(self, path):
            self.path = path
        def read_latest(self):
            raise FileNotFoundError("Steam request is waiting for cloud/login")

    def fake_popen(command, **kwargs):
        launches.append(command)
        return SimpleNamespace(pid=12345, returncode=0, poll=lambda: 0)

    monkeypatch.setattr(protected, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(protected, "_processes", lambda: [])
    monkeypatch.setattr(protected, "ObservationClient", UnreadyClient)
    monkeypatch.setattr(protected.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(protected.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(protected.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    return save, bridge, game_dir, launches, tmp_path


def time_out_real_context(case):
    save, bridge, game_dir, launches, root = case
    game = protected.ProtectedGame(save, root / "first-backup", bridge, game_dir)
    with pytest.raises((TimeoutError, RuntimeError)):
        with game.protected():
            game.launch(timeout=1)
    assert launches == [[str(game_dir.parents[2] / "steam.exe"), "-applaunch", "212680"]]
    return game


def test_pending_steam_timeout_does_not_claim_successful_restoration(pending_steam_request):
    game = time_out_real_context(pending_steam_request)
    receipt = game.backup / "restoration.json"
    assert not receipt.exists() or json.loads(receipt.read_text()).get("verified") is not True, (
        "No FTL process does not establish cancellation of Steam's pending launch request")
    assert (game.save / "ftl_bench_pending_launch.json").is_file()
    assert (game.backup / "prof.sav").read_bytes() == b"original prof.sav"


def test_pending_steam_timeout_blocks_another_protected_context_persistently(pending_steam_request):
    first = time_out_real_context(pending_steam_request)
    # A new Python object must not forget the unresolved request when Steam is idle.
    next_game = protected.ProtectedGame(first.save, first.backup.parent / "second-backup",
                                        first.bridge, first.game)
    with pytest.raises(RuntimeError, match="(?i)pending|unresolved"):
        with next_game.protected():
            pytest.fail("A second protected context was admitted before cancelling the pending launch")
    assert not next_game.backup.exists()
    assert len(pending_steam_request[3]) == 1


def test_same_object_cannot_dispatch_a_second_pending_request(pending_steam_request):
    game = time_out_real_context(pending_steam_request)
    before = game.pending_launch.read_bytes()
    with pytest.raises(RuntimeError, match="already dispatched"):
        game.launch(timeout=1)
    assert game.pending_launch.read_bytes() == before
    assert len(pending_steam_request[3]) == 1


def test_ready_launch_keeps_ownership_until_verified_cleanup(pending_steam_request, monkeypatch):
    save, bridge, game_dir, launches, root = pending_steam_request
    game = protected.ProtectedGame(save, root / "ready-backup", bridge, game_dir)
    processes = []
    def popen(command, **kwargs):
        launches.append(command)
        processes.append({"id": 42, "path": str(game_dir / "FTLGame.exe"),
                          "started": game.launched_at.isoformat()})
        return SimpleNamespace(pid=12345)
    monkeypatch.setattr(protected.subprocess, "Popen", popen)
    monkeypatch.setattr(protected, "_processes", lambda: processes[:])
    monkeypatch.setattr(protected, "ObservationClient", lambda path: SimpleNamespace(
        read_latest=lambda: SimpleNamespace(game_started=False, paused=False)))
    stopped = []
    def stop(script, **variables):
        assert variables["FTLBENCH_PID"] == "42"
        assert (save / "prof.sav").read_bytes() == b"benchmark progress"
        stopped.append(variables)
        processes.clear()
    monkeypatch.setattr(protected, "_powershell", stop)
    with game.protected():
        game.launch(timeout=1)
        assert json.loads(game.pending_launch.read_bytes())["state"] == "ready_owned"
        (save / "prof.sav").write_bytes(b"benchmark progress")
        with pytest.raises(RuntimeError, match="active|Unresolved"):
            with protected.ProtectedGame(save, root / "other", bridge, game_dir).protected():
                pytest.fail("A ready protected run must still own its save folder")
    assert len(stopped) == 1 and not processes and len(launches) == 1
    assert not game.pending_launch.exists()
    assert (save / "prof.sav").read_bytes() == b"original prof.sav"
    assert (save / "ftl_bench_dev.lua").read_bytes() == b"original bridge"
    assert json.loads((game.backup / "restoration.json").read_bytes())["verified"] is True


@pytest.mark.parametrize("failure", ["no_ack", "wrong_id", "corrupt_backup", "running_ftl"])
def test_pending_recovery_rejects_without_consuming_guard_or_backup(pending_steam_request, monkeypatch, failure):
    game = time_out_real_context(pending_steam_request)
    marker = game.save / "ftl_bench_pending_launch.json"
    guard_bytes = marker.read_bytes()
    guard = json.loads(guard_bytes)
    assert guard["state"] == "launch_pending"
    ownership_id = guard["ownership_id"]
    acknowledge = True
    if failure == "no_ack":
        acknowledge = False
    elif failure == "wrong_id":
        ownership_id += "-wrong"
    elif failure == "corrupt_backup":
        (game.backup / "prof.sav").write_bytes(b"corrupted backup")
    else:
        monkeypatch.setattr(protected, "_processes", lambda: [{"id": 9876}])
    backup_before = {p.name: p.read_bytes() for p in game.backup.iterdir() if p.is_file()}
    live_before = {p.name: p.read_bytes() for p in game.save.iterdir() if p.is_file()}
    with pytest.raises((RuntimeError, ValueError)):
        protected.recover_protected(game.backup, ownership_id=ownership_id,
                                    confirm_pending_launch_cancelled=acknowledge)
    assert marker.read_bytes() == guard_bytes
    assert {p.name: p.read_bytes() for p in game.backup.iterdir() if p.is_file()} == backup_before
    assert {p.name: p.read_bytes() for p in game.save.iterdir() if p.is_file()} == live_before
    assert not (game.backup / "recovery-restoration.json").exists()
    assert not (game.backup / "restoration.json").exists()
    assert len(pending_steam_request[3]) == 1


def test_acknowledged_pending_recovery_restores_without_relabeling_timeout(pending_steam_request):
    game = time_out_real_context(pending_steam_request)
    marker = game.save / "ftl_bench_pending_launch.json"
    guard = json.loads(marker.read_bytes())
    assert guard["state"] == "launch_pending"
    historical = game.backup / "restoration.json"
    assert not historical.exists()
    # Simulate changed live bytes; recovery must use the authenticated original backup.
    (game.save / "prof.sav").write_bytes(b"later changed live save")
    (game.save / "ftl_bench_dev.lua").write_bytes(b"later changed bridge")
    protected.recover_protected(game.backup, ownership_id=guard["ownership_id"],
                                confirm_pending_launch_cancelled=True)
    assert (game.save / "prof.sav").read_bytes() == b"original prof.sav"
    assert (game.save / "ftl_bench_dev.lua").read_bytes() == b"original bridge"
    manifest = json.loads((game.backup / "manifest.json").read_text())
    import hashlib
    assert {name: hashlib.sha256((game.save / name).read_bytes()).hexdigest()
            for name in manifest["files"]} == manifest["files"]
    assert not marker.exists()
    recovery = json.loads((game.backup / "recovery-restoration.json").read_text())
    assert recovery["verified"] is True
    assert not historical.exists(), "Recovery must not turn the failed launch into historical cleanup success"
    assert len(pending_steam_request[3]) == 1, "Recovery must not launch Steam or FTL"
    next_game = protected.ProtectedGame(game.save, game.backup.parent / "after-recovery-backup",
                                        game.bridge, game.game)
    with next_game.protected():
        assert next_game.backup.is_dir()
    assert len(pending_steam_request[3]) == 1



def test_recovery_verifies_bridge_copy_before_receipt_and_guard_release(pending_steam_request, monkeypatch):
    game = time_out_real_context(pending_steam_request)
    marker = game.save / "ftl_bench_pending_launch.json"
    guard = json.loads(marker.read_bytes())
    real_copy = protected.shutil.copy2
    def silently_wrong_bridge_copy(source, target, *args, **kwargs):
        if protected.Path(target) == game.save / "ftl_bench_dev.lua":
            return str(target)  # Successful return is not proof of byte equality.
        return real_copy(source, target, *args, **kwargs)
    monkeypatch.setattr(protected.shutil, "copy2", silently_wrong_bridge_copy)
    with pytest.raises(RuntimeError, match="(?i)bridge"):
        protected.recover_protected(game.backup, ownership_id=guard["ownership_id"],
                                    confirm_pending_launch_cancelled=True)
    assert marker.is_file()
    assert not (game.backup / "recovery-restoration.json").exists()
    assert not (game.backup / "restoration.json").exists()


def recovery_with_failed_marker_release(case, monkeypatch):
    game = time_out_real_context(case)
    marker = game.save / "ftl_bench_pending_launch.json"
    guard = json.loads(marker.read_bytes())
    real_unlink = protected.Path.unlink
    def fail_marker_only(path, *args, **kwargs):
        if path == marker:
            raise PermissionError("simulated locked pending marker")
        return real_unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(protected.Path, "unlink", fail_marker_only)
        with pytest.raises(PermissionError, match="locked pending marker"):
            protected.recover_protected(game.backup, ownership_id=guard["ownership_id"],
                                        confirm_pending_launch_cancelled=True)
    assert marker.is_file()
    receipt = game.backup / "recovery-restoration.json"
    assert json.loads(receipt.read_text())["verified"] is True
    return game, guard, receipt


def test_recovery_retry_finishes_marker_removal_without_rewriting_receipt(pending_steam_request, monkeypatch):
    game, guard, receipt = recovery_with_failed_marker_release(pending_steam_request, monkeypatch)
    original = receipt.read_bytes(), receipt.stat().st_mtime_ns
    protected.recover_protected(game.backup, ownership_id=guard["ownership_id"],
                                confirm_pending_launch_cancelled=True)
    assert (receipt.read_bytes(), receipt.stat().st_mtime_ns) == original
    assert not (game.save / "ftl_bench_pending_launch.json").exists()
    assert not (game.backup / "restoration.json").exists()
    assert len(pending_steam_request[3]) == 1


@pytest.mark.parametrize("changed", ["save", "bridge", "receipt_owner"])
def test_recovery_retry_rejects_changed_current_originals_or_receipt_owner(pending_steam_request, monkeypatch, changed):
    game, guard, receipt = recovery_with_failed_marker_release(pending_steam_request, monkeypatch)
    if changed == "save":
        (game.save / "prof.sav").write_bytes(b"changed after first recovery")
    elif changed == "bridge":
        (game.save / "ftl_bench_dev.lua").write_bytes(b"changed after first recovery")
    else:
        value = json.loads(receipt.read_text())
        value["recovery"]["ownership_id"] += "-wrong"
        receipt.write_text(json.dumps(value))
    original = receipt.read_bytes(), receipt.stat().st_mtime_ns
    with pytest.raises(RuntimeError):
        protected.recover_protected(game.backup, ownership_id=guard["ownership_id"],
                                    confirm_pending_launch_cancelled=True)
    assert (game.save / "ftl_bench_pending_launch.json").is_file()
    assert (receipt.read_bytes(), receipt.stat().st_mtime_ns) == original


def test_prepared_guard_without_manifest_recovers_as_no_deployment(pending_steam_request):
    save, bridge, game_dir, launches, root = pending_steam_request
    game = protected.ProtectedGame(save, root / "prepared-backup", bridge, game_dir)
    game._claim_guard()  # Durable claim before backup/deployment; simulate interruption here.
    marker = save / "ftl_bench_pending_launch.json"
    guard = json.loads(marker.read_bytes())
    assert guard["state"] == "prepared" and not (game.backup / "manifest.json").exists()
    live_before = {p.name: p.read_bytes() for p in save.iterdir() if p.is_file() and p != marker}
    protected.recover_protected(game.backup, save_directory=save, ownership_id=guard["ownership_id"],
                                confirm_pending_launch_cancelled=True)
    assert not marker.exists()
    assert {p.name: p.read_bytes() for p in save.iterdir() if p.is_file()} == live_before
    receipt = json.loads((game.backup / "recovery-restoration.json").read_text())
    assert receipt["recovery"]["prior_launch_state"] == "prepared"
    assert receipt["operation"] == "release_before_deployment"
    assert receipt["save_restoration_required"] is False
    assert not (game.backup / "restoration.json").exists()
    assert launches == []



def test_prepared_guard_with_truncated_manifest_can_release_without_consuming_partial_evidence(pending_steam_request):
    save, bridge, game_dir, launches, root = pending_steam_request
    game = protected.ProtectedGame(save, root / "interrupted-backup", bridge, game_dir)
    game._claim_guard()
    marker = save / "ftl_bench_pending_launch.json"
    guard = json.loads(marker.read_bytes())
    assert guard["state"] == "prepared" and guard["manifest_sha256"] is None
    game.backup.mkdir()
    manifest = game.backup / "manifest.json"
    partial_bytes = b'{"created_at":"interrupted-before-deployment", "files":'
    manifest.write_bytes(partial_bytes)
    (game.backup / "prof.sav").write_bytes(b"partial backup evidence")
    live_before = {p.name: p.read_bytes() for p in save.iterdir() if p.is_file() and p != marker}
    protected.recover_protected(game.backup, save_directory=save, ownership_id=guard["ownership_id"],
                                confirm_pending_launch_cancelled=True)
    assert not marker.exists()
    assert manifest.read_bytes() == partial_bytes
    assert (game.backup / "prof.sav").read_bytes() == b"partial backup evidence"
    assert {p.name: p.read_bytes() for p in save.iterdir() if p.is_file()} == live_before
    receipt = json.loads((game.backup / "recovery-restoration.json").read_text())
    assert receipt["operation"] == "release_before_deployment"
    assert receipt["save_restoration_required"] is False
    assert not (game.backup / "restoration.json").exists()
    assert launches == []
