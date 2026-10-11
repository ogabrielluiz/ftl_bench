"""Offline controller gates; synthetic review receipts are test data only."""
import copy
import json

import pytest

from ftl_bench import controller_admission as c
from ftl_bench import native_acceptance as a


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode())
    return {"path": name, "sha256": a.digest(path.read_bytes())}


@pytest.fixture
def admission(tmp_path, monkeypatch):
    """Isolate admission joins from raw verifier (tested in test_native_acceptance)."""
    sources = {name: a.digest(name.encode()) for name in c.VERIFIERS}
    build_sources = {name: put(tmp_path, "build/" + name, name.encode())
                     for name in ("Engine.cpp", "native/Engine.h")}
    hashes = {name: ref["sha256"] for name, ref in build_sources.items()}
    provenance = {**a.CAPABILITIES, "built_at": "2026-10-11T00:00:00Z",
        "dll_sha256": "a" * 64, "dll_size": 123, "source_commit": "b" * 40,
        "patch_sha256": "c" * 64, "source_files_sha256": hashes,
        "platform": "windows-x86", "game_version": "1.6.9",
        "toolchain": {"image_id": "sha256:" + "d" * 64, "compiler": "clang 12",
                      "build_command": '["ninja", "build"]'}}
    candidate = {"producer_descriptors": {"startup": {"present": True}, "timing": {"present": True}},
                 "native": {"provenance": put(tmp_path, "provenance.json", provenance)}}
    runtime = {name: a.digest(name.encode()) for name in a.RUNTIME_FILES}
    runtime["Hyperspace.dll"] = provenance["dll_sha256"]
    runtime["ftlbench-native.json"] = candidate["native"]["provenance"]["sha256"]
    report = {"status": "validated_scoped", "production_accepted": False, "controller_admission": False,
        "checks": {"producer_descriptor_joins": "validated_scoped"}, "source_files": sources,
        "evidence_files": {"raw-baseline.json": put(tmp_path, "raw-baseline.json", {"raw": True})["sha256"]},
        "runtime_files": runtime, "native_identity": {"dll_sha256": provenance["dll_sha256"],
            "patch_sha256": provenance["patch_sha256"], "production_bridge_sha256": "e" * 64,
            "source_commit": provenance["source_commit"], "source_reconstruction": {"source_files_sha256": hashes}}}
    calls = []
    def validate(value, *, source_root, evidence_root):
        calls.append((value, source_root, evidence_root))
        return copy.deepcopy(report)
    monkeypatch.setattr(a, "validate", validate)
    monkeypatch.setattr(a, "source_identity", lambda root: copy.deepcopy(sources))
    origin = {"contract": "portable-native-build-origin-v1", "kind": "fresh",
              "record": put(tmp_path, "original.json", provenance), "build_sources": build_sources}
    spec = {"contract": c.CONTRACT, "candidate": put(tmp_path, "candidate.json", candidate)}
    review = {"contract": "portable-native-admission-review-v1",
              "reviewer": {"id": "test-independent-reviewer", "independent_of_producer": True}}
    def save():
        spec["build_origin"] = put(tmp_path, "origin.json", origin)
        bindings = {"candidate_sha256": spec["candidate"]["sha256"],
            "build_origin_sha256": spec["build_origin"]["sha256"],
            "source_sha256": a.source_digest(sources), "verification_sha256": a.source_digest(report),
            "verifier_sources": sources}
        review.setdefault("bindings", bindings)
        if "mutations" not in review:
            review["mutations"] = [{"id": case, "evidence": put(tmp_path, "mutations/" + case + ".json",
                {"case": case, **{k: bindings[k] for k in ("candidate_sha256", "build_origin_sha256", "verifier_sources")},
                 "rejected": True, "error": "synthetic expected rejection", "method": "unit test fixture"})}
                for case in sorted(c.MUTATIONS)]
        spec["review"] = put(tmp_path, "review.json", review)
        put(tmp_path, "admission.json", spec)
        return tmp_path / "admission.json"
    def run():
        return c.require_admission(save(), source_root=tmp_path / "checkout", evidence_root=tmp_path)
    return locals()


def test_complete_fresh_admission_is_deterministic_and_preserves_scoped_report(admission):
    d = admission
    result = d["run"]()
    assert result == d["run"]()
    assert result["controller_admission"] is True and result["production_accepted"] is False
    assert d["report"]["controller_admission"] is False
    assert len(d["calls"]) == 2
    assert result["candidate"] == d["spec"]["candidate"]
    assert result["runtime_files"] == d["runtime"]
    assert {"admission.json", "original.json", "origin.json", "review.json", "raw-baseline.json"} <= set(result["evidence_files"])
    assert set(result) == {"contract", "controller_admission", "production_accepted", "source_files",
        "evidence_files", "runtime_files", "runtime", "candidate", "build_origin", "review", "reviewer", "scope"}


def historical(d):
    record = copy.deepcopy(d["provenance"])
    record["base_commit"] = record.pop("source_commit")
    record["candidate_source_sha256"] = {"Engine.cpp": d["hashes"]["Engine.cpp"]}
    record.pop("source_files_sha256")
    record["classification"] = "diagnostic_only"
    record["benchmark_eligible"] = False
    record["toolchain"]["command"] = ["ninja", "build"]
    record["toolchain"].pop("build_command")
    record["toolchain"]["compiler"] = "clang12"
    d["origin"].update(kind="historical", record=put(d["tmp_path"], "original.json", record),
        integration=put(d["tmp_path"], "integration.json", {"contract": "native-production-integration-plan-v1",
        "candidate_dll_sha256": record["dll_sha256"], "staged_complete_patch_sha256": record["patch_sha256"],
        "complete_patch_paths": list(d["hashes"]),
        "staged_sha256": {"native-source\\" + name.replace("/", "\\"): sha for name, sha in d["hashes"].items()}}))
    return record


def test_historical_subset_and_windows_integration_labels(admission):
    historical(admission)
    result = admission["run"]()
    original = a.read_json((admission["tmp_path"] / "original.json").read_bytes())
    assert original["classification"] == "diagnostic_only"
    assert original["benchmark_eligible"] is False
    assert "integration.json" in result["evidence_files"]


@pytest.mark.parametrize("field,value", [("built_at", "2026-10-11T00:00:00"),
    ("built_at", "2026-10-12T00:00:00Z"), ("dll_size", 124), ("dll_sha256", "f" * 64),
    ("source_commit", "f" * 40), ("fresh_start_seed", False), ("platform", "linux"),
    ("production_reuse_of_tested_build", True), ("classification", "production_reuse_of_tested_build"),
    ("source_files_sha256", {"Engine.cpp": "f" * 64})])
def test_fresh_origin_contradictions_reject(admission, field, value):
    record = copy.deepcopy(admission["provenance"])
    record[field] = value
    admission["origin"]["record"] = put(admission["tmp_path"], "original.json", record)
    with pytest.raises(c.AdmissionError):
        admission["run"]()


@pytest.mark.parametrize("change", ["missing_source", "extra_source", "source_bytes", "image", "command", "compiler", "compiler_identity"])
def test_build_source_and_toolchain_joins(admission, change):
    d = admission
    if change == "missing_source":
        d["origin"]["build_sources"].pop("Engine.cpp")
    elif change == "extra_source":
        d["origin"]["build_sources"]["Extra.cpp"] = put(d["tmp_path"], "extra.cpp", b"extra")
    elif change == "source_bytes":
        d["origin"]["build_sources"]["Engine.cpp"] = put(d["tmp_path"], "build/Engine.cpp", b"changed")
    else:
        record = copy.deepcopy(d["provenance"])
        if change == "image":
            record["toolchain"]["image_id"] = "different"
        elif change == "command":
            record["toolchain"]["build_command"] = '["other"]'
        elif change == "compiler_identity":
            record["toolchain"]["compiler"] = "another compiler"
        else:
            record["toolchain"].pop("compiler")
        d["origin"]["record"] = put(d["tmp_path"], "original.json", record)
    with pytest.raises(c.AdmissionError):
        d["run"]()


@pytest.mark.parametrize("change", ["missing", "subset", "integration_source", "patch", "duplicate_label"])
def test_historical_origin_contradictions(admission, change):
    d = admission
    record = historical(d)
    if change == "missing":
        d["origin"].pop("integration")
    elif change == "subset":
        record["candidate_source_sha256"]["Engine.cpp"] = "f" * 64
        d["origin"]["record"] = put(d["tmp_path"], "original.json", record)
    else:
        integration = a.read_json((d["tmp_path"] / "integration.json").read_bytes())
        if change == "patch":
            integration["staged_complete_patch_sha256"] = "f" * 64
        elif change == "duplicate_label":
            integration["staged_sha256"]["native-source/Engine.cpp"] = d["hashes"]["Engine.cpp"]
        else:
            integration["staged_sha256"]["native-source\\Engine.cpp"] = "f" * 64
        d["origin"]["integration"] = put(d["tmp_path"], "integration.json", integration)
    with pytest.raises(c.AdmissionError):
        d["run"]()


@pytest.mark.parametrize("change", ["identity", "independence", "binding", "missing_case", "duplicate_case",
    "receipt_baseline", "receipt_verifier", "receipt_error", "receipt_method", "receipt_rejection", "receipt_hash"])
def test_incomplete_or_unbound_review_rejects(admission, change):
    d = admission
    d["save"]()
    review = d["review"]
    if change == "identity":
        review["reviewer"]["id"] = " "
    elif change == "independence":
        review["reviewer"]["independent_of_producer"] = False
    elif change == "binding":
        review["bindings"]["source_sha256"] = "f" * 64
    elif change == "missing_case":
        review["mutations"].pop()
    elif change == "duplicate_case":
        review["mutations"][-1] = review["mutations"][0]
    else:
        ref = review["mutations"][0]["evidence"]
        receipt = a.read_json((d["tmp_path"] / ref["path"]).read_bytes())
        if change == "receipt_hash":
            (d["tmp_path"] / ref["path"]).write_bytes(b"changed")
        else:
            key, value = {"receipt_baseline": ("candidate_sha256", "f" * 64),
                "receipt_verifier": ("verifier_sources", {}), "receipt_error": ("error", ""),
                "receipt_method": ("method", ""), "receipt_rejection": ("rejected", False)}[change]
            receipt[key] = value
            ref.update(put(d["tmp_path"], ref["path"], receipt))
    with pytest.raises(c.AdmissionError):
        d["run"]()


@pytest.mark.parametrize("change", ["status", "promotion", "reconstruction", "runtime", "descriptors", "source_drift"])
def test_pre_actor_gate_rejects_missing_baseline(admission, change):
    d = admission
    if change == "status":
        d["report"]["status"] = "pending"
    elif change == "promotion":
        d["report"]["controller_admission"] = True
    elif change == "reconstruction":
        d["report"]["native_identity"]["source_reconstruction"] = None
    elif change == "runtime":
        d["report"]["runtime_files"].pop("FTLGame.exe")
    elif change == "descriptors":
        d["candidate"].pop("producer_descriptors")
        d["spec"]["candidate"] = put(d["tmp_path"], "candidate.json", d["candidate"])
    else:
        d["monkeypatch"].setattr(a, "source_identity", lambda root: {})
    with pytest.raises(c.AdmissionError):
        d["run"]()


def test_real_raw_verifier_pending_evidence_cannot_be_attested_into_admission(tmp_path):
    candidate = put(tmp_path, "candidate.json", {"contract": a.CONTRACT})
    spec = put(tmp_path, "admission.json", {"contract": c.CONTRACT, "candidate": candidate,
        "build_origin": {"path": "absent-origin.json", "sha256": "a" * 64},
        "review": {"path": "absent-review.json", "sha256": "b" * 64}})
    with pytest.raises(c.AdmissionError, match="Scoped native validation failed"):
        c.require_admission(tmp_path / spec["path"], source_root=tmp_path, evidence_root=tmp_path)


def test_spec_outside_evidence_root_rejected(tmp_path):
    with pytest.raises(c.AdmissionError):
        c.require_admission(tmp_path.parent / "outside.json", source_root=tmp_path, evidence_root=tmp_path)
