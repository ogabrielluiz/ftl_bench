"""Synthetic file/Git fixtures only; never compile or operate a game."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def helper():
    path = Path(__file__).resolve().parents[2] / "scripts/archive_native_build.py"
    spec = importlib.util.spec_from_file_location("archive_native_build", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def build(tmp_path):
    module = helper()
    source = tmp_path / "native"
    source.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args])
    git("init", "-q")
    (source / "old.cpp").write_bytes(b"before\n")
    git("add", "old.cpp")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
    commit = git("rev-parse", "HEAD").decode().strip()
    (source / "old.cpp").write_bytes(b"after\n")
    (source / "new.h").write_bytes(b"new source\n")
    patch = git("diff", "--binary", "HEAD")
    new_diff = subprocess.run(["git", "-C", str(source), "diff", "--no-index", "--binary", "--", "/dev/null", "new.h"], capture_output=True)
    assert new_diff.returncode == 1
    patch += new_diff.stdout
    root = tmp_path / "benchmark"
    (root / "native").mkdir(parents=True)
    (root / "native/patch.patch").write_bytes(patch)
    manifest = {"repository": "https://example.invalid/native.git", "base_commit": commit,
                "patch": "native/patch.patch", "patch_sha256": module.sha(patch),
                "native_protocol": 5, "visual_io_version": 1, "visual_clock_version": 2,
                "fixed_step_numerator": 1, "fixed_step_denominator": 60,
                "fresh_start_seed": True, "fresh_seed_contract_version": 3,
                "fresh_seed_contract": "fresh-start-seed-v3"}
    (root / "native/manifest.json").write_text(json.dumps(manifest))
    output = root / "dist/native-build-evidence/unique-build"
    kwargs = dict(source=source, source_root=root, evidence_root=root, output=output)
    module.prepare(**kwargs)
    dll = source / "Hyperspace.dll"
    dll.write_bytes(b"synthetic DLL, not executable")
    _, _, _, files, diff = module.inputs(source, root)
    record = {**manifest, "source_commit": commit, "built_at": datetime.now(timezone.utc).isoformat(),
              "dll_sha256": module.sha(dll.read_bytes()), "dll_size": dll.stat().st_size,
              "source_files_sha256": {k: module.sha(v) for k, v in files.items()},
              "source_diff_sha256": module.sha(diff), "platform": "windows-x86", "game_version": "1.6.9",
              "toolchain": {"image": "registry.invalid/compiler@sha256:" + "a" * 64,
                            "image_id": "sha256:" + "b" * 64, "build_command": "synthetic test command"}}
    provenance = output / "native-build.visual-v1.json"
    provenance.write_text(json.dumps(record))
    return module, kwargs, dll, provenance, record


def finish(build):
    module, kwargs, dll, provenance, _ = build
    return module.finish(**kwargs, dll=dll, provenance=provenance)


def test_fresh_origin_consumed_by_controller_and_relocated_reader(build, tmp_path):
    from ftl_bench.controller_admission import _origin
    from ftl_bench.native_acceptance import Reader
    _, kwargs, dll, provenance, record = build
    original_bytes = provenance.read_bytes()
    path = finish(build)
    origin = json.loads(path.read_bytes())
    assert set(origin) == {"contract", "kind", "record", "build_sources"}
    assert set(origin["build_sources"]) == {"old.cpp", "new.h"}
    assert all(v["path"].startswith("dist/native-build-evidence/unique-build/") for v in origin["build_sources"].values())
    assert (kwargs["output"] / "artifacts/native-build.visual-v1.json").read_bytes() == original_bytes
    assert (kwargs["output"] / "artifacts/Hyperspace.visual-v1.dll").read_bytes() == dll.read_bytes()
    assert "compiler" not in json.loads(original_bytes)["toolchain"]
    relocated = tmp_path / "relocated"
    shutil.copytree(kwargs["source_root"], relocated)
    identity = {"source_commit": record["source_commit"],
                "patch_sha256": record["patch_sha256"],
                "source_reconstruction": {"source_files_sha256": record["source_files_sha256"]}}
    _origin(Reader(relocated), origin, record, identity)


def test_prepare_refuses_existing_and_preserves_archive(build):
    module, kwargs, *_ = build
    before = (kwargs["output"] / "preparation.json").read_bytes()
    with pytest.raises(FileExistsError):
        module.prepare(**kwargs)
    assert (kwargs["output"] / "preparation.json").read_bytes() == before


@pytest.mark.parametrize("where", ["source", "archive", "unrelated_tracked"])
def test_post_build_drift_rejected_without_origin(build, where):
    _, kwargs, *_ = build
    path = (kwargs["source"] / "old.cpp" if where != "archive"
            else kwargs["output"] / "build-sources/old.cpp")
    if where == "unrelated_tracked":
        # A tracked local change beyond the selected source map is in source.diff.
        subprocess.run(["git", "-C", str(kwargs["source"]), "add", "old.cpp"], check=True)
        path = kwargs["source"] / "new-tracked.txt"
        path.write_bytes(b"first")
        subprocess.run(["git", "-C", str(kwargs["source"]), "add", "new-tracked.txt"], check=True)
    path.write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="changed|differs"):
        finish(build)
    assert (kwargs["output"] / "preparation.json").exists()
    assert not (kwargs["output"] / "build-origin.json").exists()


@pytest.mark.parametrize("change", ["dll", "source_map", "patch", "base", "toolchain", "reuse", "timestamp"])
def test_wrong_original_output_rejected(build, change):
    _, kwargs, dll, provenance, record = build
    if change == "dll":
        dll.write_bytes(b"substituted")
    else:
        if change == "source_map": record["source_files_sha256"].pop("new.h")
        if change == "patch": record["patch_sha256"] = "c" * 64
        if change == "base": record["source_commit"] = "d" * 40
        if change == "toolchain": record["toolchain"].pop("image_id")
        if change == "reuse": record["production_reuse_of_tested_build"] = True
        if change == "timestamp": record["built_at"] = "2000-01-01T00:00:00+00:00"
        provenance.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        finish(build)
    assert not (kwargs["output"] / "build-origin.json").exists()


def test_extra_archived_source_rejected(build):
    _, kwargs, *_ = build
    (kwargs["output"] / "build-sources/extra.cpp").write_bytes(b"extra")
    with pytest.raises(ValueError, match="inventory"):
        finish(build)


def test_finish_exclusive_and_partial_attempt_retained(build, monkeypatch):
    module, kwargs, *_ = build
    write = module.write
    def interrupted(path, data):
        if path.name == "native-build.visual-v1.json":
            raise OSError("simulated interruption")
        write(path, data)
    monkeypatch.setattr(module, "write", interrupted)
    with pytest.raises(OSError, match="interruption"):
        finish(build)
    assert (kwargs["output"] / "artifacts/Hyperspace.visual-v1.dll").exists()
    with pytest.raises(FileExistsError, match="partial archive"):
        finish(build)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/absolute", "a/../b", "a\\b", "a/./b"])
def test_relative_paths_fail_closed(name):
    with pytest.raises(ValueError): helper().relative(name)


def test_output_outside_root_or_inside_native_refused(build):
    module, kwargs, *_ = build
    for output in (kwargs["source"] / "archive", kwargs["source_root"].parent / "outside"):
        with pytest.raises(ValueError, match="Archive"):
            module.prepare(**{**kwargs, "output": output})
    with pytest.raises(ValueError, match="Traversal"):
        module.prepare(**{**kwargs, "output": kwargs["source_root"] / ".." / "escape"})


def test_symlink_source_rejected(build, tmp_path):
    _, kwargs, *_ = build
    path = kwargs["source"] / "old.cpp"
    target = tmp_path / "real.cpp"
    target.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Host cannot create symlinks")
    with pytest.raises(ValueError, match="Links"):
        finish(build)
