"""Portable evidence producers shared by opt-in no-model visual diagnostics.

These helpers capture files and attest a point in time; they never launch a
game, install a runtime, or promote an acceptance claim.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .native_acceptance import source_identity

RUNTIME_FILES = ("FTLGame.exe", "ftl.dat", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll", "ftlbench-native.json")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reference(root, path):
    path, root = Path(path).resolve(), Path(root).resolve()
    return {"path": path.relative_to(root).as_posix(), "sha256": digest(path)}


def evidence_root(output, root=None):
    output = Path(output).resolve()
    root = output if root is None else Path(root).resolve()
    if not output.is_relative_to(root):
        raise ValueError("Diagnostic output must remain inside its explicit evidence root")
    return root


def snapshot_sources(root, output, reference_root=None):
    root, output = Path(root), Path(output)
    reference_root = evidence_root(output, reference_root)
    files = {}
    for name, expected in source_identity(root).items():
        data = (root / name).read_bytes()
        destination = output / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        files[name] = hashlib.sha256(data).hexdigest()
        if files[name] != expected:
            raise RuntimeError("Source changed while snapshotting: " + name)
    write(output / "source-snapshot.json", {"contract": "visual-source-snapshot-v1", "root": str(root),
        "captured_at": stamp(), "source_files": files,
        "archived_files": {name: reference(reference_root, output / "sources" / name) for name in files}})
    return files


def inventory(protected, production_bridge=None):
    paths = [*protected.save.glob("*.sav"), protected.save / "ftl_bench_dev.lua", protected.bridge,
        *(protected.game / name for name in RUNTIME_FILES)]
    if production_bridge is not None:
        paths.append(Path(production_bridge))
    return {str(path): digest(path) if path.is_file() else None for path in sorted(set(paths))}


def portable_inventory(protected, values):
    result = {}
    for name, sha in values.items():
        path = Path(name)
        prefix = "save" if path.parent == protected.save else "runtime" if path.parent == protected.game else "source"
        key = prefix + "/" + path.name
        if key in result:
            raise RuntimeError("Ambiguous portable inventory identity: " + key)
        result[key] = sha
    return result


def inventory_ids(protected, values):
    result = {}
    for name in values:
        path = Path(name)
        prefix = "save" if path.parent == protected.save else "runtime" if path.parent == protected.game else "source"
        result[name] = prefix + "/" + path.name
    if len(set(result.values())) != len(result):
        raise RuntimeError("Portable inventory identities must be one-to-one")
    return result


def cleanup_attestation(evidence_root, output, protected, before, after, processes, *, session):
    if processes or before != after:
        raise RuntimeError("Cleanup inventory/process attestation failed")
    ref = lambda name: reference(evidence_root, output / name)
    value = {"contract": "portable-cleanup-attestation-v1", "checked_at": stamp(),
        "before": portable_inventory(protected, before), "after": portable_inventory(protected, after),
        "inventory_ids": inventory_ids(protected, before),
        "processes": processes, "backups": {name: ref("save-backup/" + name) for name in protected.manifest["files"]},
        "backup_manifest": ref("save-backup/manifest.json"), "restoration": ref("save-backup/restoration.json"),
        "raw_inventory_refs": {"before": ref("before-inventory.json"), "after": ref("after-inventory.json")},
        "trajectory": ref("trajectory.jsonl"), "session": ref(session),
        "scope": "Saved point-in-time cleanup for this diagnostic; no current live audit."}
    write(output / "portable-cleanup.json", value)
    return ref("portable-cleanup.json")


def trial_descriptor(evidence_root, output, *, session, admission=None):
    ref = lambda name: reference(evidence_root, output / name)
    value = {"trajectory": ref("trajectory.jsonl"), "session": ref(session),
        "runtime": ref("runtime-fingerprint.json"), "cleanup": ref("portable-cleanup.json"),
        "images": {digest(path): reference(evidence_root, path) for path in sorted((output / "screens").glob("*.png"))}}
    if admission is not None:
        value["admission"] = ref(admission)
    if (output / "setup-store-close.json").is_file():
        value["setup_store_close"] = ref("setup-store-close.json")
    return value


class TimingTrialEvidence:
    """Opt-in hooks; the caller still owns the actual protected run lifecycle."""
    def __init__(self, root, collection, files, challenge, repetition, delay, timing_driver, reference_root=None):
        self.root, self.collection = Path(root), Path(collection)
        self.reference_root = evidence_root(collection, reference_root)
        self.files, self.challenge, self.delay = dict(files), challenge, delay
        self.repetition = repetition
        self.timing_driver = Path(timing_driver)
        self.before = None
        self.descriptor = None
        if type(delay) not in (int, float) or delay not in (0.0, 0.35, 1.2):
            raise ValueError("Timing evidence requires a declared finite wall delay")

    def metadata(self):
        if source_identity(self.root) != self.files:
            raise RuntimeError("Timing collection source identity changed before launch")
        if digest(self.timing_driver) != self.files["scripts/validate_visual_timing.py"]:
            raise RuntimeError("Archived timing driver differs from source snapshot")
        return {"source_files_sha256": source_digest(self.files), "probe_delay_seconds": self.delay,
            "timing_driver_sha256": digest(self.timing_driver)}

    def before_protected(self, protected, output):
        self.metadata()
        self.before = inventory(protected, self.root / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua")
        write(output / "before-inventory.json", {"checked_at": stamp(), "files_sha256": self.before})

    def after_cleanup(self, protected, output, processes):
        if self.before is None:
            raise RuntimeError("Timing portable inventory was not captured before launch")
        if processes:
            raise RuntimeError("FTL still exists after protected cleanup; inventory withheld")
        after = inventory(protected, self.root / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua")
        write(output / "after-inventory.json", {"checked_at": stamp(), "files_sha256": after,
            "no_game_process": True, "processes": processes})
        self.metadata()
        cleanup_attestation(self.reference_root, output, protected, self.before, after, processes,
                            session="deterministic-setup-session.json")
        self.descriptor = {"challenge": self.challenge, "repetition": self.repetition, "delay_seconds": self.delay,
            **trial_descriptor(self.reference_root, output, session="deterministic-setup-session.json",
                               admission="deterministic-setup-admission.json"),
            "timing_script": reference(self.reference_root, self.timing_driver)}
        write(output / "timing-evidence.json", self.descriptor)
        return self.descriptor
