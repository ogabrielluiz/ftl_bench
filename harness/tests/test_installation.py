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
