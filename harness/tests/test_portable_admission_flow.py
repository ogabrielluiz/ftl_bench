"""Opt-in, file-only portable flow through the real raw-evidence verifier.

Set FTL_NATIVE_SOURCE_TEST_REPOSITORY to a local Git repository containing the
manifest base, or FTL_NATIVE_SOURCE_TEST_PROOF to an existing proof JSON beneath
the executing checkout. No fetch, build, game, model or installation occurs.
Build/reviewer records below are clearly synthetic test fixtures, never real
build-execution or independent-review attestations.
"""
import copy
import importlib.util
import os
import shutil
from pathlib import Path

import pytest

from ftl_bench import controller_admission as controller
from ftl_bench import experiment_admission as archive
from ftl_bench import native_acceptance as native
from ftl_bench import native_build_origin as origin
from test_native_acceptance import add_nine, cleanup, evidence, put, rewrite


def authenticated_proof(root, source):
    repository = os.environ.get("FTL_NATIVE_SOURCE_TEST_REPOSITORY")
    existing = os.environ.get("FTL_NATIVE_SOURCE_TEST_PROOF")
    if not repository and not existing:
        pytest.skip("Opt-in real reconstruction needs FTL_NATIVE_SOURCE_TEST_REPOSITORY or FTL_NATIVE_SOURCE_TEST_PROOF; no Git objects are fetched")
    if repository:
        repository = Path(repository).resolve(strict=True)
        spec = importlib.util.spec_from_file_location("portable_flow_collector", source / "scripts/collect_native_source_evidence.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        path = module.collect(repository=repository, source_root=source,
                              output=root / "native-proof", evidence_root=root)
        return native.read_json(path.read_bytes())
    path = Path(existing).resolve(strict=True)
    name = path.relative_to(source).as_posix()
    reader = native.Reader(source)
    proof = reader.json({"path": name, "sha256": native.digest(path.read_bytes())}, "opt-in source proof")
    result = copy.deepcopy(proof)
    for oid, entry in result["objects"].items():
        data = reader.bytes(entry["reference"], "opt-in Git object " + oid)
        entry["reference"] = put(root, "native-proof/objects/" + oid, data)
    return result


def reconstructed_bytes(proof, root, manifest, patch):
    """Materialize test build inputs from authenticated objects and exact patch."""
    reader = native.Reader(root)
    objects = {oid: reader.bytes(row["reference"], "test Git object") for oid, row in proof["objects"].items()}
    commit = objects[manifest["base_commit"]]
    tree = next(line[5:].decode() for line in commit.split(b"\n\n", 1)[0].splitlines() if line.startswith(b"tree "))

    def lookup(oid, name):
        data, cursor = objects[oid], 0
        while cursor < len(data):
            space, zero = data.index(b" ", cursor), data.index(b"\0", cursor)
            if data[space + 1:zero].decode() == name:
                return data[zero + 1:zero + 21].hex()
            cursor = zero + 21
        return None

    result = {}
    for name, lines in origin.patch_sections(patch):
        oid = tree
        for part in name.split("/"):
            oid = lookup(oid, part)
            if oid is None:
                break
        base = objects[oid] if oid is not None else None
        result[name] = origin.apply_section(name, lines, base)
    return result


def test_real_raw_baseline_admission_freeze_and_relocated_verify(evidence, tmp_path):
    root, source, candidate = evidence
    proof = authenticated_proof(root, source)
    manifest = native.read_json((source / "native/manifest.json").read_bytes())
    patch = (source / manifest["patch"]).read_bytes()
    reconstructed = origin.reconstruct_sources(manifest=manifest, patch=patch, proof=proof, reader=native.Reader(root))
    build_bytes = reconstructed_bytes(proof, root, manifest, patch)
    assert {name: native.digest(data) for name, data in build_bytes.items()} == reconstructed["source_files_sha256"]
    candidate["native"]["source_reconstruction"] = put(root, "native-proof/proof.json", proof)
    provenance_ref = candidate["native"]["provenance"]
    provenance = native.read_json((root / provenance_ref["path"]).read_bytes())
    provenance.update(built_at="2026-10-11T00:00:00Z", source_files_sha256=reconstructed["source_files_sha256"],
                      toolchain={"image_id": "synthetic-test-image", "build_command": ["synthetic-test-build"]})
    provenance_ref.update(put(root, provenance_ref["path"], provenance))
    rewrite(root, candidate["startup"]["runtime"], lambda doc: doc.update(native_build={**provenance, "matches_installed_dll": True}))
    previous_cleanup = native.read_json((root / candidate["startup"]["cleanup"]["path"]).read_bytes())
    hashes = previous_cleanup["before"]
    hashes["runtime/ftlbench-native.json"] = provenance_ref["sha256"]
    candidate["startup"]["cleanup"] = cleanup(root, hashes)
    rewrite(root, candidate["startup"]["cleanup"], lambda doc: doc.update(
        trajectory=candidate["startup"]["trajectory"], session=candidate["startup"]["session"]))
    add_nine(evidence)
    candidate["producer_descriptors"] = {
        "startup": put(root, "startup-producer.json", {"contract": "visual-startup-evidence-v1",
                       "source_snapshot": candidate["source_snapshot"], "startup": candidate["startup"]}),
        "timing": put(root, "timing-producer.json", {"contract": "visual-timing-evidence-v1",
                      "source_snapshot": candidate["source_snapshot"], "probes": candidate["probes"]})}
    report = native.validate(candidate, source_root=source, evidence_root=root)
    assert report["status"] == "validated_scoped", report
    assert report["controller_admission"] is report["production_accepted"] is False
    build_origin = {"contract": "portable-native-build-origin-v1", "kind": "fresh",
                    "record": put(root, "synthetic-original-build.json", provenance),
                    "build_sources": {name: put(root, "synthetic-build-sources/" + name, data)
                                      for name, data in build_bytes.items()}}
    spec = {"contract": controller.CONTRACT, "candidate": put(root, "candidate.json", candidate),
            "build_origin": put(root, "synthetic-build-origin.json", build_origin)}
    bindings = {"candidate_sha256": spec["candidate"]["sha256"],
                "build_origin_sha256": spec["build_origin"]["sha256"],
                "source_sha256": native.source_digest(report["source_files"]),
                "verification_sha256": native.source_digest(report),
                "verifier_sources": {name: report["source_files"][name] for name in controller.VERIFIERS}}
    review = {"contract": "portable-native-admission-review-v1",
              "reviewer": {"id": "SYNTHETIC-TEST-ONLY-reviewer", "independent_of_producer": True},
              "bindings": bindings, "mutations": []}
    for case in sorted(controller.MUTATIONS):
        receipt = {"case": case, **{key: bindings[key] for key in ("candidate_sha256", "build_origin_sha256", "verifier_sources")},
                   "rejected": True, "error": "Synthetic test fixture rejection",
                   "method": "Synthetic unit-test attestation only; no real independent review claimed"}
        review["mutations"].append({"id": case, "evidence": put(root, "synthetic-mutations/" + case + ".json", receipt)})
    spec["review"] = put(root, "synthetic-review.json", review)
    spec_path = root / put(root, "controller-spec.json", spec)["path"]
    admitted = controller.require_admission(spec_path, source_root=source, evidence_root=root)
    assert admitted["controller_admission"] is True and admitted["production_accepted"] is False
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    selector = archive.freeze_admission(cohort, spec_path, source_root=source, evidence_root=root)
    assert selector["admission"] == admitted
    moved = tmp_path / "relocated-cohort"
    shutil.copytree(cohort, moved)
    # The frozen cohort contains every consumed byte and does not need original evidence.
    for name in admitted["evidence_files"]:
        (root / name).unlink()
    assert archive.verify_admission(moved, selector, source_root=source) == admitted
