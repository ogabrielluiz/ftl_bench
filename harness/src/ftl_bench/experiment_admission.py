"""Exclusive portable admission archives and installed runtime checks."""
from __future__ import annotations

import os
from pathlib import Path

from ftl_bench.controller_admission import AdmissionError, require_admission
from ftl_bench.installation import runtime_fingerprint
from ftl_bench.native_acceptance import (
    CAPABILITIES, RUNTIME_FILES, SHA, _safe_path, digest, relative_path,
    source_identity,
)

MATRIX_CONTRACT = "ftl-visual-challenge-matrix-v2"
FULLGAME_CONTRACT = "ftl-fullgame-experiment-v2"
PORTABLE_CONTRACTS = (MATRIX_CONTRACT, FULLGAME_CONTRACT)
ADMISSION_CONTRACT = "portable-visual-controller-admission-v1"


def _require(condition, message):
    if not condition:
        raise AdmissionError(message)


def _root(value):
    path = Path(value).absolute()
    for item in (path, *path.parents):
        _require(not item.is_symlink() and not (hasattr(item, "is_junction") and item.is_junction()),
                 "Linked admission root: " + str(item))
    _require(path.is_dir(), "Admission directory missing: " + str(path))
    return path.resolve()


def _map(value, label):
    _require(isinstance(value, dict) and bool(value), label + " must be a nonempty hash map")
    for name, sha in value.items():
        relative_path(name)
        _require(isinstance(sha, str) and SHA.fullmatch(sha), label + " has malformed hash")
    return dict(sorted(value.items()))


def _bytes(root, name, sha):
    data = _safe_path(root, name).read_bytes()
    _require(digest(data) == sha, "Admission SHA256 mismatch: " + name)
    return data


def _inventory(root):
    root = _root(root)
    files = {}
    def traversal_error(error):
        raise AdmissionError("Cannot inventory admission archive: " + str(error)) from error

    for directory, subdirs, names in os.walk(root, followlinks=False, onerror=traversal_error):
        for name in subdirs + names:
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            _safe_path(root, rel)
            _require(path.is_dir() or path.is_file(), "Unsafe archive entry: " + rel)
        for name in names:
            path = Path(directory) / name
            files[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return dict(sorted(files.items()))


def freeze_admission(directory, spec_path, *, source_root, evidence_root):
    """Create archives exclusively; leave any failed partial archive unreusable."""
    try:
        directory, source_root, evidence_root = map(_root, (directory, source_root, evidence_root))
        evidence_archive, source_archive = directory / "native-evidence", directory / "frozen-source"
        _require(not os.path.lexists(evidence_archive) and not os.path.lexists(source_archive),
                 "Admission archive already exists")
        spec_path = Path(spec_path).absolute()
        spec_name = spec_path.relative_to(evidence_root).as_posix()
        spec_bytes = _safe_path(evidence_root, spec_name).read_bytes()
        admission = require_admission(spec_path, source_root=source_root, evidence_root=evidence_root)
        evidence = _map(admission["evidence_files"], "Evidence inventory")
        sources = _map(admission["source_files"], "Source inventory")
        _require(evidence.get(spec_name) == digest(spec_bytes), "Spec missing from evidence inventory")
        # Validate all input bytes before creating output, without overwriting any path.
        evidence_bytes = {name: _bytes(evidence_root, name, sha) for name, sha in evidence.items()}
        source_bytes = {name: _bytes(source_root, name, sha) for name, sha in sources.items()}
        evidence_archive.mkdir()
        source_archive.mkdir()
        for archive, items in ((evidence_archive, evidence_bytes), (source_archive, source_bytes)):
            for name, data in items.items():
                target = archive / relative_path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(data)
        # The scoped verifier authenticates the executing checkout. Archived
        # source bytes are checked separately and must equal that checkout.
        frozen = require_admission(evidence_archive / spec_name, source_root=source_root,
                                   evidence_root=evidence_archive)
        _require(frozen == admission, "Frozen admission differs from original admission")
        selector = {"contract": ADMISSION_CONTRACT, "spec": {"path": spec_name, "sha256": digest(spec_bytes)},
                    "evidence_files": evidence, "source_files": sources, "admission": frozen}
        verify_admission(directory, selector, source_root=source_root)
        return selector
    except AdmissionError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise AdmissionError("Cannot freeze admission: " + str(error)) from error


def verify_admission(directory, selector, *, source_root):
    """Recompute from frozen evidence and sources; never use a legacy fallback."""
    try:
        directory, source_root = map(_root, (directory, source_root))
        _require(isinstance(selector, dict) and set(selector) ==
                 {"contract", "spec", "evidence_files", "source_files", "admission"}, "Invalid admission selector")
        _require(selector["contract"] == ADMISSION_CONTRACT, "Unknown admission selector contract")
        spec = selector["spec"]
        _require(isinstance(spec, dict) and set(spec) == {"path", "sha256"}, "Invalid spec reference")
        evidence = _map(selector["evidence_files"], "Evidence inventory")
        sources = _map(selector["source_files"], "Source inventory")
        _require(evidence.get(spec["path"]) == spec["sha256"], "Spec hash is not pinned")
        evidence_archive = directory / "native-evidence"
        source_archive = directory / "frozen-source"
        _require(_inventory(evidence_archive) == evidence, "Frozen evidence inventory mismatch")
        _require(_inventory(source_archive) == sources, "Frozen source inventory mismatch")
        _require(source_identity(source_root) == sources, "Current executable source inventory mismatch")
        for name, sha in sources.items():
            _bytes(source_root, name, sha)
        admission = require_admission(_safe_path(_root(evidence_archive), spec["path"]),
                                      source_root=source_root, evidence_root=_root(evidence_archive))
        _require(admission.get("evidence_files") == evidence and admission.get("source_files") == sources,
                 "Consumed admission inventory mismatch")
        _require(admission == selector["admission"], "Derived admission mismatch")
        return admission
    except AdmissionError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise AdmissionError("Cannot verify admission: " + str(error)) from error


def installed_runtime(root):
    try:
        fingerprint = runtime_fingerprint(Path(root))
        build = fingerprint.get("native_build")
        _require(isinstance(build, dict) and build.get("matches_installed_dll") is True,
                 "Installed native provenance does not match DLL")
        _require(all(type(build.get(k)) is type(v) and build[k] == v for k, v in CAPABILITIES.items()),
                 "Installed native capability mismatch")
        native = fingerprint["native_dll"]
        game = _root(Path(native["path"]).parent)
        files = {name: digest(_safe_path(game, name).read_bytes()) for name in RUNTIME_FILES}
        _require(files["Hyperspace.dll"] == build.get("dll_sha256") == native.get("sha256"),
                 "Installed DLL changed during fingerprint")
        return {"files_sha256": files, "native_build": build}
    except AdmissionError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise AdmissionError("Cannot inspect installed runtime: " + str(error)) from error


def require_installed(admission, installed):
    try:
        _require(isinstance(admission, dict) and isinstance(installed, dict), "Invalid installed runtime objects")
        files, build, runtime = installed["files_sha256"], installed["native_build"], admission["runtime"]
        _require(all(isinstance(value, dict) for value in (files, build, runtime)), "Invalid installed runtime maps")
        _require(set(files) == set(RUNTIME_FILES) and files == admission["runtime_files"],
                 "Installed six-file runtime mismatch")
        _require(build.get("matches_installed_dll") is True, "Installed DLL provenance mismatch")
        _require(build.get("dll_sha256") == runtime["dll_sha256"] == files["Hyperspace.dll"]
                 and build.get("patch_sha256") == runtime["patch_sha256"], "Installed native identity mismatch")
        _require(all(type(build.get(k)) is type(v) and build[k] == v for k, v in CAPABILITIES.items()),
                 "Installed native capability mismatch")
        return installed
    except AdmissionError:
        raise
    except (KeyError, TypeError) as error:
        raise AdmissionError("Invalid installed runtime: " + str(error)) from error
