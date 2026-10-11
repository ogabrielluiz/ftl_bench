"""Explicitly reviewed controller admission over recomputed portable evidence.

Original build records and reviewer declarations are external trust anchors.
Their hashes bind recorded assertions; they do not prove compiler execution or
the reviewer's identity or independence. Mutation receipts are attestations,
not executable instructions and are never replayed by this module.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import native_acceptance as native

CONTRACT = "portable-visual-controller-admission-v1"
MUTATIONS = frozenset(("source", "bridge", "native_artifact", "build_origin",
    "runtime_baseline", "trial_inventory", "capture_actions", "cleanup"))
VERIFIERS = tuple("harness/src/ftl_bench/" + name + ".py" for name in
    ("native_acceptance", "native_build_origin", "controller_admission"))
SCOPE = "Explicitly reviewed local controller admission; no general full-game determinism or build-execution attestation"


class AdmissionError(ValueError):
    """A required controller gate is missing or contradictory."""


def _require(value, message):
    if not value:
        raise AdmissionError(message)


def _timestamp(value):
    _require(isinstance(value, str) and value.strip(), "Original built_at missing")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(result.tzinfo is not None and result.utcoffset() is not None,
             "Original built_at must have an explicit timezone")
    return result


def _command(toolchain):
    value = toolchain.get("build_command", toolchain.get("command"))
    if isinstance(value, str) and value.lstrip().startswith("["):
        value = native.read_json(value.encode())
    _require(isinstance(value, str) and bool(value.strip()) or
             isinstance(value, list) and bool(value) and
             all(isinstance(item, str) and item for item in value), "Build command missing or malformed")
    return value


def _origin(reader, origin, provenance, identity):
    _require(origin.get("contract") == "portable-native-build-origin-v1", "Wrong build-origin contract")
    kind = origin.get("kind")
    _require(kind in ("fresh", "historical"), "Wrong build-origin kind")
    record = reader.json(origin.get("record"), "original build record")
    _require(kind != "fresh" or (not record.get("production_reuse_of_tested_build")
             and record.get("classification") != "production_reuse_of_tested_build"),
             "Historical production reuse is not a fresh build")
    _require(_timestamp(record.get("built_at")) == _timestamp(provenance.get("built_at")),
             "Original build timestamp differs")
    for name in ("dll_sha256", "dll_size", "platform", "game_version", *native.CAPABILITIES):
        _require(name in record and name in provenance and type(record[name]) is type(provenance[name])
                 and record[name] == provenance[name], "Original build differs: " + name)
    _require(record.get("source_commit" if kind == "fresh" else "base_commit") == identity["source_commit"],
             "Original build base differs")
    old, current = record.get("toolchain"), provenance.get("toolchain")
    _require(isinstance(old, dict) and isinstance(current, dict), "Build toolchain missing")
    _require(isinstance(old.get("image_id"), str) and bool(old["image_id"].strip())
             and old["image_id"] == current.get("image_id"), "Build toolchain image identity differs")
    _require(_command(old) == _command(current), "Build commands differ")
    # Compiler spelling is descriptive; never create evidence absent at origin.
    for toolchain in (old, current):
        if "compiler" in toolchain:
            _require(isinstance(toolchain["compiler"], str) and bool(toolchain["compiler"].strip()),
                     "Compiler identity is empty")
    _require(("compiler" in old) == ("compiler" in current), "Compiler evidence missing from original or current provenance")
    if "compiler" in old:
        _require("".join(old["compiler"].lower().split()) ==
                 "".join(current["compiler"].lower().split()), "Compiler identities differ")
    reconstruction = identity["source_reconstruction"]
    complete = reconstruction.get("source_files_sha256")
    sources = origin.get("build_sources")
    _require(isinstance(complete, dict) and complete and isinstance(sources, dict)
             and set(sources) == set(complete), "Complete build_sources inventory differs")
    actual = {}
    for name in sorted(sources):
        native.relative_path(name)
        actual[name] = native.digest(reader.bytes(sources[name], "build source " + name))
    _require(actual == complete == provenance.get("source_files_sha256"),
             "Build sources differ from reconstruction or provenance")
    if kind == "fresh":
        _require(record.get("source_files_sha256") == actual, "Fresh original source map differs")
        _require(record.get("patch_sha256") == identity["patch_sha256"], "Fresh original patch differs")
    else:
        integration = reader.json(origin.get("integration"), "original integration record")
        _require(integration.get("contract") == "native-production-integration-plan-v1", "Wrong integration contract")
        _require(integration.get("candidate_dll_sha256") == identity["dll_sha256"]
                 and integration.get("staged_complete_patch_sha256") == identity["patch_sha256"],
                 "Integration artifact or patch differs")
        paths = integration.get("complete_patch_paths")
        _require(isinstance(paths, list) and len(paths) == len(actual) and set(paths) == set(actual),
                 "Integration patched-file inventory differs")
        staged = integration.get("staged_sha256")
        _require(isinstance(staged, dict), "Integration source map missing")
        normalized = {}
        for label, sha in staged.items():
            _require(isinstance(label, str), "Malformed integration label")
            label = label.replace("\\", "/")
            if label.startswith("native-source/"):
                name = label[len("native-source/"):]
                native.relative_path(name)
                _require(name not in normalized, "Duplicate normalized integration source")
                normalized[name] = sha
        _require(normalized == actual, "Integration build-source map differs")
        subset = record.get("candidate_source_sha256")
        _require(isinstance(subset, dict) and subset and
                 all(name in actual and actual[name] == sha for name, sha in subset.items()),
                 "Original candidate source subset differs")


def _review(reader, review, spec, report):
    _require(review.get("contract") == "portable-native-admission-review-v1", "Wrong review contract")
    reviewer = review.get("reviewer")
    _require(isinstance(reviewer, dict) and isinstance(reviewer.get("id"), str)
             and bool(reviewer["id"].strip()) and reviewer.get("independent_of_producer") is True,
             "Explicit independent reviewer attestation missing")
    sources = report["source_files"]
    _require(all(name in sources for name in VERIFIERS), "Verifier source pins missing")
    expected = {"candidate_sha256": spec["candidate"]["sha256"],
        "build_origin_sha256": spec["build_origin"]["sha256"],
        "source_sha256": native.source_digest(sources),
        "verification_sha256": native.source_digest(report),
        "verifier_sources": {name: sources[name] for name in VERIFIERS}}
    _require(review.get("bindings") == expected, "Review baseline bindings differ")
    mutations = review.get("mutations")
    _require(isinstance(mutations, list) and len(mutations) == len(MUTATIONS), "Exactly eight mutation receipts required")
    seen = set()
    for row in mutations:
        _require(isinstance(row, dict) and set(row) == {"id", "evidence"}, "Malformed mutation reference")
        case = row["id"]
        _require(isinstance(case, str) and case in MUTATIONS and case not in seen, "Duplicate or unknown mutation case")
        seen.add(case)
        receipt = reader.json(row["evidence"], "mutation " + case)
        _require(receipt.get("case") == case and receipt.get("rejected") is True,
                 "Mutation rejection attestation missing: " + case)
        for name in ("candidate_sha256", "build_origin_sha256", "verifier_sources"):
            _require(receipt.get(name) == expected[name], "Mutation baseline differs: " + case + ": " + name)
        for name in ("error", "method"):
            _require(isinstance(receipt.get(name), str) and bool(receipt[name].strip()),
                     "Mutation " + name + " missing: " + case)
    return reviewer


def require_admission(spec_path, *, source_root, evidence_root):
    """Return deterministic derived admission, or raise AdmissionError.

    Reads only hashed evidence and executable source. No deployment, process,
    compiler, game, model request, or mutation-review replay occurs here.
    """
    try:
        reader = native.Reader(evidence_root)
        path = Path(spec_path)
        if not path.is_absolute():
            path = reader.root / path
        name = path.absolute().relative_to(reader.root).as_posix()
        safe = native._safe_path(reader.root, name)
        spec = reader.json({"path": name, "sha256": native.digest(safe.read_bytes())}, "controller admission spec")
        _require(set(spec) == {"contract", "candidate", "build_origin", "review"}
                 and spec["contract"] == CONTRACT, "Wrong controller admission spec schema")
        candidate = reader.json(spec["candidate"], "candidate")
        report = native.validate(candidate, source_root=Path(source_root), evidence_root=reader.root)
        _require(report.get("status") == "validated_scoped", "Scoped native validation failed: " + str(report))
        _require(report.get("production_accepted") is False and report.get("controller_admission") is False,
                 "Scoped verifier unexpectedly promotes production or controller admission")
        descriptors = candidate.get("producer_descriptors")
        _require(isinstance(descriptors, dict) and all(name in descriptors for name in ("startup", "timing")),
                 "Both producer descriptors required")
        _require(report.get("checks", {}).get("producer_descriptor_joins") == "validated_scoped", "Producer descriptors not validated")
        identity = report.get("native_identity") or {}
        _require(isinstance(identity.get("source_reconstruction"), dict), "Complete source reconstruction required")
        runtime_files = report.get("runtime_files")
        _require(isinstance(runtime_files, dict) and set(runtime_files) == set(native.RUNTIME_FILES)
                 and all(isinstance(sha, str) and native.SHA.fullmatch(sha) for sha in runtime_files.values()),
                 "Common six-file runtime required")
        provenance = reader.json(candidate["native"]["provenance"], "current provenance")
        _origin(reader, reader.json(spec["build_origin"], "build origin"), provenance, identity)
        reviewer = _review(reader, reader.json(spec["review"], "review"), spec, report)
        for name, sha in report["evidence_files"].items():
            reader.bytes({"path": name, "sha256": sha}, "validated evidence " + name)
        _require(reader.unchanged(), "Admission evidence changed during validation")
        _require(native.source_identity(Path(source_root)) == report["source_files"], "Executable sources changed during admission")
        runtime = {name: identity[name] for name in ("dll_sha256", "patch_sha256", "production_bridge_sha256")}
        runtime.update({name: native.CAPABILITIES[name] for name in ("visual_clock_version",
            "fixed_step_numerator", "fixed_step_denominator", "fresh_start_seed", "fresh_seed_contract_version", "fresh_seed_contract")})
        return {"contract": CONTRACT, "controller_admission": True, "production_accepted": False,
            "source_files": report["source_files"], "evidence_files": dict(sorted(reader.pins.items())),
            "runtime_files": runtime_files, "runtime": runtime, "candidate": spec["candidate"],
            "build_origin": spec["build_origin"], "review": spec["review"], "reviewer": reviewer, "scope": SCOPE}
    except AdmissionError:
        raise
    except (ValueError, OSError, KeyError, TypeError, AttributeError, IndexError) as error:
        raise AdmissionError(str(error)) from error
