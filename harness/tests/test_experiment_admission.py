"""Portable archive checks using synthetic bytes only; no game or model access."""
import copy
import os
import shutil

import pytest

from ftl_bench import experiment_admission as a
from ftl_bench.native_acceptance import CAPABILITIES, RUNTIME_FILES, digest


@pytest.fixture
def archive(tmp_path, monkeypatch):
    source, evidence, cohort = (tmp_path / name for name in ("source", "evidence", "cohort"))
    for root in (source, evidence, cohort):
        root.mkdir()
    (source / "runner.py").write_bytes(b"runner bytes")
    (evidence / "spec.json").write_bytes(b"spec bytes")
    (evidence / "nested").mkdir()
    (evidence / "nested/raw.json").write_bytes(b"raw bytes")
    (evidence / "unconsumed.json").write_bytes(b"not admission input")
    sources = {"runner.py": digest(b"runner bytes")}
    pins = {"spec.json": digest(b"spec bytes"), "nested/raw.json": digest(b"raw bytes")}
    files = {name: digest(name.encode()) for name in RUNTIME_FILES}
    admission = {"contract": a.ADMISSION_CONTRACT, "controller_admission": True,
                 "production_accepted": False, "source_files": sources, "evidence_files": pins,
                 "runtime_files": files,
                 "runtime": {"dll_sha256": files["Hyperspace.dll"], "patch_sha256": "a" * 64}}

    def require(spec_path, *, source_root, evidence_root):
        assert spec_path == evidence_root / "spec.json"
        for name, sha in pins.items():
            if digest((evidence_root / name).read_bytes()) != sha:
                raise a.AdmissionError("raw bytes mismatch")
        for name, sha in sources.items():
            if digest((source_root / name).read_bytes()) != sha:
                raise a.AdmissionError("source bytes mismatch")
        return copy.deepcopy(admission)

    monkeypatch.setattr(a, "require_admission", require)
    monkeypatch.setattr(a, "source_identity", lambda root: {
        path.relative_to(root).as_posix(): digest(path.read_bytes())
        for path in root.rglob("*.py")})
    selector = a.freeze_admission(cohort, evidence / "spec.json", source_root=source, evidence_root=evidence)
    return source, evidence, cohort, selector, admission


def test_freeze_consumed_only_and_relocation(archive, tmp_path):
    source, evidence, cohort, selector, admission = archive
    assert set(selector) == {"contract", "spec", "evidence_files", "source_files", "admission"}
    assert not (cohort / "native-evidence/unconsumed.json").exists()
    assert set(p.name for p in cohort.iterdir()) == {"native-evidence", "frozen-source"}
    moved = tmp_path / "relocated"
    shutil.copytree(cohort, moved)
    shutil.rmtree(evidence)
    assert a.verify_admission(moved, selector, source_root=source) == admission


@pytest.mark.parametrize("change", ["missing", "extra", "changed", "source", "archived_source", "extra_archived_source", "added_source", "selector", "spec_hash", "unsafe"])
def test_archive_rejects_drift(archive, change):
    source, _, cohort, selector, _ = archive
    if change == "missing":
        (cohort / "native-evidence/nested/raw.json").unlink()
    elif change == "extra":
        (cohort / "native-evidence/unrelated.json").write_bytes(b"extra")
    elif change == "changed":
        (cohort / "native-evidence/nested/raw.json").write_bytes(b"changed")
    elif change == "source":
        (source / "runner.py").write_bytes(b"changed")
    elif change == "archived_source":
        (cohort / "frozen-source/runner.py").write_bytes(b"changed")
    elif change == "extra_archived_source":
        (cohort / "frozen-source/unrelated.txt").write_bytes(b"extra")
    elif change == "added_source":
        (source / "extra.py").write_bytes(b"extra")
    elif change == "selector":
        selector["admission"]["controller_admission"] = False
    elif change == "spec_hash":
        selector["spec"]["sha256"] = "a" * 64
    else:
        selector["evidence_files"]["../outside"] = "a" * 64
    with pytest.raises(a.AdmissionError):
        a.verify_admission(cohort, selector, source_root=source)


def test_freeze_never_overwrites_partial_archive(archive):
    source, evidence, cohort, _, _ = archive
    (cohort / "native-evidence/nested/raw.json").write_bytes(b"preserve partial")
    with pytest.raises(a.AdmissionError, match="already exists"):
        a.freeze_admission(cohort, evidence / "spec.json", source_root=source, evidence_root=evidence)
    assert (cohort / "native-evidence/nested/raw.json").read_bytes() == b"preserve partial"


def test_stale_input_hash_creates_no_archive(archive, tmp_path):
    source, evidence, _, _, _ = archive
    cohort = tmp_path / "fresh"
    cohort.mkdir()
    (evidence / "nested/raw.json").write_bytes(b"changed")
    with pytest.raises(a.AdmissionError):
        a.freeze_admission(cohort, evidence / "spec.json", source_root=source, evidence_root=evidence)
    assert list(cohort.iterdir()) == []


def test_archive_rejects_link_even_unconsumed(archive, tmp_path):
    source, _, cohort, selector, _ = archive
    target = tmp_path / "target"
    target.write_bytes(b"target")
    link = cohort / "native-evidence/link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    with pytest.raises(a.AdmissionError, match="Links"):
        a.verify_admission(cohort, selector, source_root=source)


def test_consumed_map_cannot_change(archive, monkeypatch):
    source, _, cohort, selector, admission = archive
    changed = copy.deepcopy(admission)
    changed["evidence_files"].pop("nested/raw.json")
    monkeypatch.setattr(a, "require_admission", lambda *args, **kwargs: changed)
    with pytest.raises(a.AdmissionError, match="Consumed"):
        a.verify_admission(cohort, selector, source_root=source)


def test_unreadable_extra_subtree_fails_closed(archive, monkeypatch):
    source, _, cohort, selector, _ = archive
    blocked = cohort / "native-evidence/blocked"
    blocked.mkdir()
    (blocked / "unrelated.json").write_bytes(b"extra")
    original_scandir = os.scandir

    def denied_scandir(path):
        if os.fspath(path) == os.fspath(blocked):
            raise PermissionError("unreadable archive subtree")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", denied_scandir)
    with pytest.raises(a.AdmissionError, match="Cannot inventory admission archive"):
        a.verify_admission(cohort, selector, source_root=source)


def test_installed_runtime_is_six_files_and_enforces_identity(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    for name in RUNTIME_FILES:
        (game / name).write_bytes(name.encode())
    dll = digest(b"Hyperspace.dll")
    build = {**CAPABILITIES, "matches_installed_dll": True, "dll_sha256": dll, "patch_sha256": "a" * 64}
    monkeypatch.setattr(a, "runtime_fingerprint", lambda root: {
        "native_dll": {"path": str(game / "Hyperspace.dll"), "sha256": dll}, "native_build": build})
    installed = a.installed_runtime(tmp_path)
    admission = {"runtime_files": installed["files_sha256"], "runtime": {"dll_sha256": dll, "patch_sha256": "a" * 64}}
    assert a.require_installed(admission, installed) == installed
    for change in ("files", "patch", "capability", "dll", "provenance"):
        bad = copy.deepcopy(installed)
        if change == "files":
            bad["files_sha256"]["ftl.dat"] = "b" * 64
        elif change == "patch":
            bad["native_build"]["patch_sha256"] = "b" * 64
        elif change == "capability":
            bad["native_build"]["native_protocol"] = 6
        elif change == "dll":
            bad["native_build"]["dll_sha256"] = "b" * 64
        else:
            bad["native_build"]["matches_installed_dll"] = False
        with pytest.raises(a.AdmissionError):
            a.require_installed(admission, bad)
    build["matches_installed_dll"] = False
    with pytest.raises(a.AdmissionError):
        a.installed_runtime(tmp_path)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/absolute", "nested\\windows", "nested//double", "nested/./dot"])
def test_selector_rejects_nonportable_paths(archive, name):
    source, _, cohort, selector, _ = archive
    selector["source_files"][name] = "a" * 64
    with pytest.raises(a.AdmissionError):
        a.verify_admission(cohort, selector, source_root=source)


@pytest.mark.parametrize("installed", [None, {}, {"files_sha256": {}, "native_build": None}])
def test_require_installed_rejects_incomplete_objects(installed):
    with pytest.raises(a.AdmissionError):
        a.require_installed({"runtime": {}}, installed)
