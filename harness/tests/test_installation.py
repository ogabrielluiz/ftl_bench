import json

import pytest

from ftl_bench import installation


def fixture_build(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    for name in ("FTLGame.exe", "xinput1_4.dll", "lua-5.3.dll"):
        (game / name).touch()
    (game / "Hyperspace.dll").write_bytes(b"original-dll")
    dll = tmp_path / "built.dll"
    dll.write_bytes(b"verified-dll")
    manifest = tmp_path / "native-build.json"
    manifest.write_text(json.dumps({"platform": "windows-x86", "game_version": "1.6.9",
                                   "native_protocol": 5, "dll_sha256": installation.sha256(dll),
                                   "dll_size": dll.stat().st_size}))
    monkeypatch.setattr(installation, "ftl_process_alive", lambda: False)
    user = tmp_path / "user-save"
    user.mkdir()
    monkeypatch.setattr(installation, "ftl_user_folder", lambda: user)
    return game, dll, manifest


def test_verified_install_retains_original_and_matching_provenance(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    installed = installation.install_native(dll, manifest, game)
    from pathlib import Path
    assert (Path(installed["backup"]) / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert (game / "Hyperspace.dll").read_bytes() == dll.read_bytes()
    assert (game / "ftlbench-native.json").read_bytes() == manifest.read_bytes()
    monkeypatch.setenv("FTL_GAME_DIR", str(game))
    fingerprint = installation.runtime_fingerprint(tmp_path)
    assert fingerprint["native_build"]["matches_installed_dll"] is True
    (game / "Hyperspace.dll").write_bytes(b"different-dll")
    assert installation.runtime_fingerprint(tmp_path)["native_build"]["matches_installed_dll"] is False


def test_bad_hash_or_live_game_cannot_modify_installation(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    dll.write_bytes(b"unexpected-dll")
    with pytest.raises(ValueError, match="does not match"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-backups").exists()
    monkeypatch.setattr(installation, "ftl_process_alive", lambda: True)
    with pytest.raises(ValueError, match="Close FTL"):
        installation.install_native(dll, manifest, game)


@pytest.mark.parametrize("protocol", [None, True, "5", 4, 0])
def test_incompatible_protocol_preserves_the_installation(tmp_path, monkeypatch, protocol):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    provenance = json.loads(manifest.read_text())
    provenance["native_protocol"] = protocol
    manifest.write_text(json.dumps(provenance))
    with pytest.raises(ValueError, match="protocol 5"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-backups").exists()


def test_install_rolls_back_if_provenance_copy_fails(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    original_copy = installation.shutil.copyfile

    def fail_manifest(source, dest, **kwargs):
        if source == manifest:
            raise OSError("disk full")
        return original_copy(source, dest, **kwargs)

    monkeypatch.setattr(installation.shutil, "copyfile", fail_manifest)
    with pytest.raises(OSError, match="disk full"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-native.json").exists()


@pytest.mark.parametrize("seed_identity", [
    {"fresh_start_seed": True, "fresh_seed_contract_version": 3, "fresh_seed_contract": "fresh-start-seed-v3"},
    {"fresh_start_seed": False, "fresh_seed_contract_version": 2, "fresh_seed_contract": "fresh-start-seed-v2"},
    {},
])
def test_fingerprint_preserves_recorded_fresh_seed_identity_without_inference(tmp_path, monkeypatch, seed_identity):
    game = tmp_path / "game"
    game.mkdir()
    dll = game / "Hyperspace.dll"
    dll.write_bytes(b"actual installed DLL")
    user = tmp_path / "user"
    user.mkdir()
    provenance = {"dll_sha256": installation.sha256(dll), "native_protocol": 5,
                  "visual_clock_version": 2, **seed_identity}
    (game / "ftlbench-native.json").write_text(json.dumps(provenance))
    monkeypatch.setenv("FTL_GAME_DIR", str(game))
    monkeypatch.setattr(installation, "ftl_user_folder", lambda: user)
    result = installation.runtime_fingerprint(tmp_path)["native_build"]
    assert {key: result[key] for key in ("fresh_start_seed", "fresh_seed_contract_version", "fresh_seed_contract")} == {
        key: seed_identity.get(key) for key in ("fresh_start_seed", "fresh_seed_contract_version", "fresh_seed_contract")}
    assert result["matches_installed_dll"] is True
    dll.write_bytes(b"different installed DLL")
    mismatched = installation.runtime_fingerprint(tmp_path)["native_build"]
    assert mismatched["matches_installed_dll"] is False
    assert mismatched["fresh_seed_contract"] == seed_identity.get("fresh_seed_contract")



def test_successful_copy_with_wrong_staged_dll_is_rejected(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    copyfile = installation.shutil.copyfile
    def wrong_copy(source, dest, **kwargs):
        if source == dll:
            installation.Path(dest).write_bytes(b"silently wrong copied DLL")
            return str(dest)
        return copyfile(source, dest, **kwargs)
    monkeypatch.setattr(installation.shutil, "copyfile", wrong_copy)
    with pytest.raises(RuntimeError, match="staged payload"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-native.json").exists()
    assert not list(game.glob(".*.tmp"))


def test_corrupt_original_backup_rejected_before_replacing_files(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    def corrupt_backup(source, dest, **kwargs):
        installation.Path(dest).write_bytes(b"corrupt backup")
        return str(dest)
    monkeypatch.setattr(installation.shutil, "copy2", corrupt_backup)
    monkeypatch.setattr(installation.shutil, "copyfile", lambda *a, **kw: pytest.fail("replacement reached"))
    with pytest.raises(RuntimeError, match="backup verification"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-native.json").exists()


def test_rollback_corrupt_copy_reports_failure_and_retains_verified_backup(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    copyfile, copy2 = installation.shutil.copyfile, installation.shutil.copy2
    def fail_manifest(source, dest, **kwargs):
        if source == manifest:
            raise OSError("provenance copy failed")
        return copyfile(source, dest, **kwargs)
    def corrupt_rollback(source, dest, **kwargs):
        if installation.Path(dest) == game / "Hyperspace.dll":
            installation.Path(dest).write_bytes(b"silently corrupt rollback")
            return str(dest)
        return copy2(source, dest, **kwargs)
    monkeypatch.setattr(installation.shutil, "copyfile", fail_manifest)
    monkeypatch.setattr(installation.shutil, "copy2", corrupt_rollback)
    with pytest.raises(RuntimeError, match="rollback failed") as error:
        installation.install_native(dll, manifest, game)
    assert isinstance(error.value.__cause__, OSError)
    backups = list((game / "ftlbench-backups").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert str(backups[0]) in str(error.value)
    assert not (game / "ftlbench-native.json").exists()


def test_provenance_drift_after_validation_restores_both_original_files(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    original_manifest = b'{"original":"provenance"}'
    (game / "ftlbench-native.json").write_bytes(original_manifest)
    copy2 = installation.shutil.copy2
    def change_incoming_manifest(source, dest, **kwargs):
        result = copy2(source, dest, **kwargs)
        manifest.write_text('{"changed":"after validation"}')
        return result
    monkeypatch.setattr(installation.shutil, "copy2", change_incoming_manifest)
    with pytest.raises(RuntimeError, match="staged payload"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert (game / "ftlbench-native.json").read_bytes() == original_manifest


def test_final_payload_corruption_is_detected_and_rolled_back(tmp_path, monkeypatch):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    replace = installation.Path.replace
    def corrupt_replaced_file(path, target):
        result = replace(path, target)
        if installation.Path(target) == game / "Hyperspace.dll":
            installation.Path(target).write_bytes(b"changed after replacement")
        return result
    monkeypatch.setattr(installation.Path, "replace", corrupt_replaced_file)
    with pytest.raises(RuntimeError, match="final payload"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-native.json").exists()



@pytest.mark.parametrize("marker_kind", ["file", "broken_link"])
def test_pending_launch_marker_blocks_installation_before_any_changes(tmp_path, monkeypatch, marker_kind):
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    marker = installation.ftl_user_folder() / "ftl_bench_pending_launch.json"
    if marker_kind == "file":
        marker.write_bytes(b"pending launch")
    else:
        try:
            marker.symlink_to(marker.parent / "absent-target.json")
        except OSError as error:
            pytest.skip("Windows symlink privilege unavailable: " + str(error))
    monkeypatch.setattr(installation, "ftl_process_alive", lambda: pytest.fail("process query reached after pending marker"))
    with pytest.raises(ValueError, match="pending"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-native.json").exists()
    assert not (game / "ftlbench-backups").exists()
    assert marker.exists() or marker.is_symlink()


@pytest.mark.parametrize("query", ["tasklist_error", "pgrep_error", "timeout"])
def test_failed_process_query_cannot_permit_native_installation(tmp_path, monkeypatch, query):
    from types import SimpleNamespace
    from ftl_bench import session
    import subprocess
    game, dll, manifest = fixture_build(tmp_path, monkeypatch)
    monkeypatch.setattr(installation, "ftl_process_alive", session.ftl_process_alive)
    monkeypatch.setattr(session, "os", SimpleNamespace(name="posix" if query == "pgrep_error" else "nt", environ={}))
    monkeypatch.setattr(session, "sys", SimpleNamespace(platform="linux" if query == "pgrep_error" else "win32"))
    def failed(cmd, **kwargs):
        assert kwargs["timeout"] == 10
        if query == "timeout":
            raise subprocess.TimeoutExpired(cmd, 10)
        return SimpleNamespace(returncode=2, stdout="", stderr="query unavailable")
    monkeypatch.setattr(session.subprocess, "run", failed)
    with pytest.raises(ValueError, match="Close FTL"):
        installation.install_native(dll, manifest, game)
    assert (game / "Hyperspace.dll").read_bytes() == b"original-dll"
    assert not (game / "ftlbench-backups").exists()
