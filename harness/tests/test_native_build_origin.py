"""Authenticated source reconstruction without game/runtime/compiler access."""
import importlib.util
from pathlib import Path

import pytest

from ftl_bench.native_acceptance import EvidenceError, Reader, digest
from ftl_bench.native_build_origin import CONTRACT, object_id, reconstruct_sources
from ftl_bench.cli import _bench_root


def fixture(tmp_path):
    objects = {}

    def put(kind, data):
        oid = object_id(kind, data)
        (tmp_path / oid).write_bytes(data)
        objects[oid] = {"type": kind, "reference": {"path": oid, "sha256": digest(data)}}
        return oid

    blob = put("blob", b"old\n")
    tree = put("tree", b"100644 other.cpp\0" + bytes.fromhex(blob))
    commit = put("commit", b"tree " + tree.encode() + b"\nauthor Test <t@example.com> 0 +0000\ncommitter Test <t@example.com> 0 +0000\n\nbase\n")
    patch = b"diff --git a/other.cpp b/other.cpp\nindex 111..222 100644\n--- a/other.cpp\n+++ b/other.cpp\n@@ -1 +1 @@\n-old\n+new\n" + b"diff --git a/new.h b/new.h\nnew file mode 100644\nindex 000..333\n--- /dev/null\n+++ b/new.h\n@@ -0,0 +1 @@\n+added\n"
    manifest = {"base_commit": commit, "patch_sha256": digest(patch)}
    return manifest, patch, {"contract": CONTRACT, "objects": objects}


def run(root, values):
    manifest, patch, proof = values
    return reconstruct_sources(manifest=manifest, patch=patch, proof=proof, reader=Reader(root))


def test_complete_reconstruction_is_read_only(tmp_path):
    values = fixture(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = run(tmp_path, values)
    assert result["source_files_sha256"] == {"other.cpp": digest(b"new\n"), "new.h": digest(b"added\n")}
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("kind", ["commit", "tree", "blob"])
def test_tampered_git_objects_reject_even_rehashed_refs(tmp_path, kind):
    manifest, patch, proof = fixture(tmp_path)
    oid, entry = next((oid, entry) for oid, entry in proof["objects"].items() if entry["type"] == kind)
    data = (tmp_path / oid).read_bytes() + b"tamper"
    (tmp_path / oid).write_bytes(data)
    entry["reference"]["sha256"] = digest(data)
    with pytest.raises(EvidenceError, match="authenticate"):
        run(tmp_path, (manifest, patch, proof))


def test_wrong_base_and_missing_object_reject(tmp_path):
    manifest, patch, proof = fixture(tmp_path)
    with pytest.raises(EvidenceError):
        run(tmp_path, ({**manifest, "base_commit": "0" * 40}, patch, proof))
    del proof["objects"][next(oid for oid, e in proof["objects"].items() if e["type"] == "blob")]
    with pytest.raises(EvidenceError, match="missing"):
        run(tmp_path, (manifest, patch, proof))


@pytest.mark.parametrize("change", ["context", "unsafe", "false_add", "missing_old"])
def test_bad_patch_semantics_reject(tmp_path, change):
    manifest, patch, proof = fixture(tmp_path)
    if change == "context":
        patch = patch.replace(b"-old\n", b"-wrong\n")
    elif change == "unsafe":
        patch = patch.replace(b"other.cpp", b"../other.cpp")
    elif change == "false_add":
        patch = patch.replace(b"new.h", b"other.cpp")
    else:
        patch = patch.replace(b"other.cpp", b"missing.cpp")
    manifest["patch_sha256"] = digest(patch)
    with pytest.raises(EvidenceError):
        run(tmp_path, (manifest, patch, proof))


def test_noninclude_source_result_changes(tmp_path):
    manifest, patch, proof = fixture(tmp_path)
    first = run(tmp_path, (manifest, patch, proof))
    patch = patch.replace(b"+new\n", b"+bad\n")
    manifest["patch_sha256"] = digest(patch)
    second = run(tmp_path, (manifest, patch, proof))
    assert first["source_files_sha256"]["other.cpp"] != second["source_files_sha256"]["other.cpp"]


@pytest.mark.parametrize("mode", [b"120000", b"160000"])
def test_symlink_and_gitlink_reject(tmp_path, mode):
    manifest, patch, proof = fixture(tmp_path)
    blob = next(oid for oid, row in proof["objects"].items() if row["type"] == "blob")
    tree_data = mode + b" other.cpp\0" + bytes.fromhex(blob)
    tree = object_id("tree", tree_data)
    commit_data = b"tree " + tree.encode() + b"\n\nbase\n"
    commit = object_id("commit", commit_data)
    for oid, kind, data in ((tree, "tree", tree_data), (commit, "commit", commit_data)):
        (tmp_path / oid).write_bytes(data)
        proof["objects"][oid] = {"type": kind, "reference": {"path": oid, "sha256": digest(data)}}
    manifest["base_commit"] = commit
    with pytest.raises(EvidenceError, match="regular blob"):
        run(tmp_path, (manifest, patch, proof))


def test_no_newline_and_hunk_count(tmp_path):
    from ftl_bench.native_build_origin import apply_section
    lines = [b"--- a/file\n", b"+++ b/file\n", b"@@ -1 +1 @@\n", b"-old\n", b"\\ No newline at end of file\n", b"+new\n", b"\\ No newline at end of file\n"]
    assert apply_section("file", lines, b"old") == b"new"
    lines[2] = b"@@ -1,2 +1 @@\n"
    with pytest.raises(EvidenceError, match="line counts"):
        apply_section("file", lines, b"old")


def test_lf_only_line_boundaries():
    from ftl_bench.native_build_origin import apply_section
    lines = [b"--- a/file\n", b"+++ b/file\n", b"@@ -1 +1 @@\n", b"-old\rbare\x0bvertical\x0cform\n", b"+new\rbare\x0bvertical\x0cform\n"]
    assert apply_section("file", lines, b"old\rbare\x0bvertical\x0cform\n") == b"new\rbare\x0bvertical\x0cform\n"


def test_collector_synthetic_git_repository(tmp_path):
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])
    git("init")
    (repo / "other.cpp").write_bytes(b"old\n")
    git("add", "other.cpp")
    git("-c", "user.name=Test", "-c", "user.email=t@example.com", "commit", "-m", "base")
    commit = git("rev-parse", "HEAD").decode().strip()
    source = tmp_path / "source"
    (source / "native").mkdir(parents=True)
    patch = b"diff --git a/other.cpp b/other.cpp\n--- a/other.cpp\n+++ b/other.cpp\n@@ -1 +1 @@\n-old\n+new\n"
    import json
    (source / "native/patch.patch").write_bytes(patch)
    (source / "native/manifest.json").write_text(json.dumps({"base_commit": commit, "patch": "native/patch.patch", "patch_sha256": digest(patch)}))
    script = _bench_root() / "scripts/collect_native_source_evidence.py"
    spec = importlib.util.spec_from_file_location("source_collector", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    head, status = git("rev-parse", "HEAD"), git("status", "--porcelain")
    path = module.collect(repository=repo, source_root=source, output=tmp_path / "evidence/collection", evidence_root=tmp_path / "evidence")
    assert path.is_file()
    assert git("rev-parse", "HEAD") == head and git("status", "--porcelain") == status
    with pytest.raises(FileExistsError):
        module.collect(repository=repo, source_root=source, output=tmp_path / "evidence/collection", evidence_root=tmp_path / "evidence")
