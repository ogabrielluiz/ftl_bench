"""Offline checks for the bootstrap archive, separate from native admission."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest
from ftl_bench.cli import _bench_root


ROOT = _bench_root()
SCRIPT = ROOT / "scripts" / "package_bridge.py"
spec = importlib.util.spec_from_file_location("package_bridge", SCRIPT)
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "clone"
    shutil.copytree(ROOT / "mod" / "ftl_bench_bridge", root / "mod" / "ftl_bench_bridge")
    return root


def test_real_loader_paths_bytes_and_metadata_without_external_dev(tmp_path):
    target = tmp_path / "bridge.ftl"
    result = packager.package_bridge(target)
    expected = ["data/bridge.lua", "data/hyperspace.xml.append", "data/json.lua",
                "data/observation.lua", "mod-appendix/metadata.xml"]
    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == expected
        for entry in archive.infolist():
            assert archive.read(entry) == (ROOT / "mod" / "ftl_bench_bridge" / entry.filename).read_bytes()
            assert entry.date_time == (1980, 1, 1, 0, 0, 0)
            assert entry.create_system == 3
            assert entry.external_attr >> 16 == stat.S_IFREG | 0o644
            assert entry.compress_type == zipfile.ZIP_STORED
            assert entry.extra == entry.comment == b""
        loader = archive.read("data/hyperspace.xml.append")
        for name in [b"data/json.lua", b"data/observation.lua", b"data/bridge.lua"]:
            assert name in loader
        assert "data/hyperspace.xml" not in archive.namelist()
        assert not any("dev" in name or "README" in name for name in archive.namelist())
    assert result["status"] == "written"
    assert result["members"] == expected


def test_repeat_and_relocation_ignore_source_metadata(source, tmp_path):
    first = tmp_path / "a.ftl"
    initial = packager.package_bridge(first, source_root=source)
    timestamp = first.stat().st_mtime_ns
    for path in (source / "mod" / "ftl_bench_bridge").rglob("*"):
        if path.is_file():
            os.utime(path, (1900000000, 1900000000))
    repeated = packager.package_bridge(first, source_root=source)
    assert repeated["status"] == "unchanged"
    assert first.stat().st_mtime_ns == timestamp
    moved = tmp_path / "relocated"
    shutil.copytree(source, moved)
    second = tmp_path / "b.ftl"
    other = packager.package_bridge(second, source_root=moved)
    assert first.read_bytes() == second.read_bytes()
    assert initial["sha256"] == repeated["sha256"] == other["sha256"]


def test_changed_input_replaces_complete_archive(source, tmp_path):
    target = tmp_path / "new" / "bridge.ftl"
    initial = packager.package_bridge(target, source_root=source)
    bridge = source / "mod" / "ftl_bench_bridge" / "data" / "bridge.lua"
    bridge.write_bytes(bridge.read_bytes() + b"\n-- changed\n")
    updated = packager.package_bridge(target, source_root=source)
    assert updated["status"] == "written"
    assert updated["sha256"] != initial["sha256"]
    with zipfile.ZipFile(target) as archive:
        assert archive.read("data/bridge.lua") == bridge.read_bytes()


def test_missing_required_file_preserves_output(source, tmp_path):
    target = tmp_path / "bridge.ftl"
    target.write_bytes(b"previous output")
    (source / "mod" / "ftl_bench_bridge" / "data" / "hyperspace.xml.append").unlink()
    with pytest.raises(packager.PackagingError, match="Missing bridge files"):
        packager.package_bridge(target, source_root=source)
    assert target.read_bytes() == b"previous output"


def test_unreadable_nested_data_fails_without_partial_archive(source, tmp_path, monkeypatch):
    nested = source / "mod" / "ftl_bench_bridge" / "data" / "nested"
    nested.mkdir()
    (nested / "runtime.lua").write_bytes(b"required nested runtime")
    target = tmp_path / "bridge.ftl"
    target.write_bytes(b"previous output")
    original_scandir = packager.os.scandir

    def unreadable(path):
        if Path(path) == nested:
            raise PermissionError("nested input unreadable")
        return original_scandir(path)

    monkeypatch.setattr(packager.os, "scandir", unreadable)
    with pytest.raises(PermissionError, match="nested input unreadable"):
        packager.package_bridge(target, source_root=source)
    assert target.read_bytes() == b"previous output"


def test_atomic_replace_failure_preserves_output_and_removes_temp(source, tmp_path, monkeypatch):
    target = tmp_path / "bridge.ftl"
    target.write_bytes(b"previous output")

    def fail_replace(*args):
        raise OSError("replace refused")

    monkeypatch.setattr(packager.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace refused"):
        packager.package_bridge(target, source_root=source)
    assert target.read_bytes() == b"previous output"
    assert list(tmp_path.glob(".bridge.ftl.*.tmp")) == []


def test_output_cannot_overwrite_source_or_directory(source, tmp_path):
    path = source / "mod" / "ftl_bench_bridge" / "data" / "bridge.lua"
    original = path.read_bytes()
    with pytest.raises(packager.PackagingError, match="outside"):
        packager.package_bridge(path, source_root=source)
    assert path.read_bytes() == original
    with pytest.raises(packager.PackagingError, match="regular file"):
        packager.package_bridge(tmp_path, source_root=source)


def _symlink(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip("Symlink creation unavailable")


@pytest.mark.parametrize("location", ["source_file", "source_directory", "output", "output_parent"])
def test_rejects_symlinks_without_touching_destination(source, tmp_path, location):
    target = tmp_path / "bridge.ftl"
    data = source / "mod" / "ftl_bench_bridge" / "data"
    external = tmp_path / "external.txt"
    external.write_bytes(b"untouched")
    if location == "source_file":
        _symlink(data / "extra.lua", external)
    elif location == "source_directory":
        _symlink(data / "extra", tmp_path, directory=True)
    elif location == "output":
        _symlink(target, external)
    else:
        _symlink(tmp_path / "linked", tmp_path, directory=True)
        target = tmp_path / "linked" / "bridge.ftl"
    with pytest.raises(packager.PackagingError, match="Symlink"):
        packager.package_bridge(target, source_root=source)
    assert external.read_bytes() == b"untouched"


def test_cli_explicit_source_output_and_repeat(source, tmp_path):
    target = tmp_path / "cli.ftl"
    args = [sys.executable, "-B", str(SCRIPT), "--source-root", str(source), "--output", str(target)]
    first = subprocess.run(args, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(args, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    a, b = json.loads(first.stdout), json.loads(second.stdout)
    assert a["sha256"] == b["sha256"]
    assert a["status"] == "written" and b["status"] == "unchanged"
