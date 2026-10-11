"""Verify portable native/bridge evidence without live game or model access."""
import argparse
from pathlib import Path

from ftl_bench.native_acceptance import CONTRACT, Reader, digest, read_json, validate, write_report


def assemble(*, evidence_root, startup_evidence, timing_evidence, dll, provenance, bridge, source_evidence=None):
    """Hash explicitly selected artifacts/descriptors; do not claim validation."""
    reader = Reader(evidence_root)

    def ref(path):
        path = Path(path).absolute()
        relative = path.relative_to(reader.root).as_posix()
        reference = {"path": relative, "sha256": digest(path.read_bytes())}
        reader.bytes(reference, "assembly input")
        return reference

    startup_ref, timing_ref = ref(startup_evidence), ref(timing_evidence)
    startup = reader.json(startup_ref, "startup descriptor")
    timing = reader.json(timing_ref, "timing descriptor")
    first = reader.json(startup.get("source_snapshot"), "startup source snapshot")
    second = reader.json(timing.get("source_snapshot"), "timing source snapshot")
    if first.get("source_files") != second.get("source_files"):
        raise ValueError("Startup and timing measured different source snapshots; create a new prospective collection")
    native = {"dll": ref(dll), "provenance": ref(provenance)}
    if source_evidence is not None:
        native["source_reconstruction"] = ref(source_evidence)
    return {"contract": CONTRACT, "source_snapshot": startup["source_snapshot"],
        "native": native, "bridge": ref(bridge),
        "startup": startup["startup"], "probes": timing["probes"],
        "producer_descriptors": {"startup": startup_ref, "timing": timing_ref}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--assemble-spec", action="store_true", help="Write an unaccepted candidate spec from explicit producer descriptors")
    for name in ("startup-evidence", "timing-evidence", "dll", "provenance", "bridge"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--source-evidence", type=Path, help="Optional authenticated Git-base reconstruction proof for assembly")
    parser.add_argument("--output", required=True, type=Path, help="New receipt path; existing files are refused")
    args = parser.parse_args(argv)
    if args.assemble_spec:
        if args.spec is not None or any(getattr(args, name) is None for name in ("startup_evidence", "timing_evidence", "dll", "provenance", "bridge")):
            parser.error("--assemble-spec requires --startup-evidence/--timing-evidence/--dll/--provenance/--bridge and excludes --spec")
        spec = assemble(evidence_root=args.evidence_root, startup_evidence=args.startup_evidence,
            timing_evidence=args.timing_evidence, dll=args.dll, provenance=args.provenance, bridge=args.bridge,
            source_evidence=args.source_evidence)
        write_report(args.output, spec)
        print("candidate_spec_written; not validated or accepted")
        return 0
    if args.spec is None or any(getattr(args, name) is not None for name in ("startup_evidence", "timing_evidence", "dll", "provenance", "bridge", "source_evidence")):
        parser.error("Verification requires --spec and excludes assembly inputs")
    report = validate(read_json(args.spec.read_bytes()), source_root=args.source_root, evidence_root=args.evidence_root)
    write_report(args.output, report)
    print(report["status"])
    return 0 if report["status"] == "validated_scoped" else 2 if report["status"] == "pending" else 1


if __name__ == "__main__":
    raise SystemExit(main())
