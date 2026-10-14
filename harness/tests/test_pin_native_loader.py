"""Pin loader inputs from inert Git blobs, using checkout/bundled script roots."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from ftl_bench.cli import _bench_root

SCRIPT = _bench_root() / "scripts/pin_native_loader.py"
spec = importlib.util.spec_from_file_location("pin_native_loader", SCRIPT)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


def git(repo, *args, input=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=input,
                          capture_output=True, check=True).stdout


@pytest.fixture
def native(tmp_path):
    repo = tmp_path / "native repo"
    repo.mkdir()
    git(repo, "init")
    release = repo / "Release Files/Windows"
    files = {"xinput1_4.dll": b"proxy", "lua-5.3.dll": b"lua",
             "patch/flips.exe": b"flips", "patch/patch-1.bps": b"patch one",
             "patch/patch-2.bps": b"patch two"}
    for name, data in files.items():
        target = release / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (release / "unused.txt").write_bytes(b"not a consumed loader input")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Offline test", "-c", "user.email=offline@example.invalid",
        "commit", "--no-gpg-sign", "-m", "inert inputs")
    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"base_commit": commit}))
    return repo, release, manifest, files, commit, tmp_path / "expected.json"


def test_exact_git_blob_manifest_and_cli(native):
    repo, release, manifest, files, commit, output = native
    subprocess.run([sys.executable, "-B", str(SCRIPT), "--source", str(repo),
                    "--manifest", str(manifest), "--output", str(output)], check=True, capture_output=True)
    assert json.loads(output.read_text()) == {"contract": "native-loader-inputs-v1",
        "source_commit": commit, "inputs": {name: {"bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()}}
    original = output.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        loader.pin_native_loader(repo, manifest, output)
    assert output.read_bytes() == original


@pytest.mark.parametrize("change", ["missing_bps", "extra_bps", "extra_uppercase_bps", "dll", "flips", "bps"])
def test_working_release_drift_rejected_before_output(native, change):
    repo, release, manifest, files, commit, output = native
    if change == "missing_bps":
        (release / "patch/patch-1.bps").unlink()
    elif change.startswith("extra"):
        (release / ("patch/extra.BPS" if change == "extra_uppercase_bps" else "patch/extra.bps")).write_bytes(b"extra")
    else:
        name = {"dll": "xinput1_4.dll", "flips": "patch/flips.exe", "bps": "patch/patch-1.bps"}[change]
        (release / name).write_bytes(b"different bytes")
    with pytest.raises(ValueError):
        loader.pin_native_loader(repo, manifest, output)
    assert not output.exists()


def test_pins_declared_base_not_current_head(native):
    repo, release, manifest, files, commit, output = native
    (release / "unused.txt").write_bytes(b"later commit")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Offline test", "-c", "user.email=offline@example.invalid",
        "commit", "--no-gpg-sign", "-m", "later unrelated commit")
    assert git(repo, "rev-parse", "HEAD").decode().strip() != commit
    assert loader.pin_native_loader(repo, manifest, output)["source_commit"] == commit


@pytest.mark.parametrize("value", [None, "HEAD", "not-a-commit", "0" * 40])
def test_invalid_or_unavailable_declared_base_rejected(native, value):
    repo, release, manifest, files, commit, output = native
    manifest.write_text(json.dumps({"base_commit": value}))
    with pytest.raises(ValueError):
        loader.pin_native_loader(repo, manifest, output)
    assert not output.exists()


def test_git_symlink_blob_is_rejected_even_if_working_file_is_regular(native):
    repo, release, manifest, files, commit, output = native
    oid = git(repo, "hash-object", "-w", "--stdin", input=b"other-target").decode().strip()
    git(repo, "update-index", "--cacheinfo", "120000," + oid + ",Release Files/Windows/xinput1_4.dll")
    git(repo, "-c", "user.name=Offline test", "-c", "user.email=offline@example.invalid",
        "commit", "--no-gpg-sign", "-m", "inert symlink tree")
    manifest.write_text(json.dumps({"base_commit": git(repo, "rev-parse", "HEAD").decode().strip()}))
    with pytest.raises(ValueError, match="regular Git blob"):
        loader.pin_native_loader(repo, manifest, output)
    assert not output.exists()


def test_reparse_input_is_rejected_before_receipt(native, monkeypatch):
    repo, release, manifest, files, commit, output = native
    target = release / "xinput1_4.dll"
    original = Path.stat
    def marked(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == target:
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=1024)
        return result
    monkeypatch.setattr(Path, "stat", marked)
    with pytest.raises(ValueError, match="Reparse"):
        loader.pin_native_loader(repo, manifest, output)
    assert not output.exists()


def test_linked_release_directory_is_rejected(native, monkeypatch):
    repo, release, manifest, files, commit, output = native
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == release or original(path))
    with pytest.raises(ValueError, match="Linked"):
        loader.pin_native_loader(repo, manifest, output)
    assert not output.exists()
