"""Portable, file-only evidence verification; never a runtime promotion operation.

The native artifact identity and the current bridge's measured behavior are
separate joins. All references are hashed and relative to an explicit evidence
root. Missing producer evidence remains pending rather than inheriting a local
historical acceptance claim.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import struct
import sys
import zlib

from ftl_bench import challenge_setup, fullgame_setup
from ftl_bench.cli import _bench_root

CONTRACT = "portable-visual-native-acceptance-v1"
BRIDGE = "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
CHALLENGES = ("combat", "fire-crew-recovery", "repair-charge-escape")
DELAYS = (0.0, 0.35, 1.2)
RUNTIME_FILES = ("FTLGame.exe", "ftl.dat", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll", "ftlbench-native.json")
CAPABILITIES = {"native_protocol": 5, "visual_io_version": 1,
    "visual_clock_version": 2, "fixed_step_numerator": 1,
    "fixed_step_denominator": 60, "fresh_start_seed": True,
    "fresh_seed_contract_version": 3, "fresh_seed_contract": "fresh-start-seed-v3"}
SHA = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceError(ValueError):
    pass


class MissingEvidence(EvidenceError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_digest(files: dict[str, str]) -> str:
    return digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(data: bytes):
    return json.loads(data, object_pairs_hook=_object,
        parse_constant=lambda value: (_ for _ in ()).throw(EvidenceError("Nonfinite JSON: " + value)))


def relative_path(value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise EvidenceError("Expected a portable relative POSIX path")
    p = PurePosixPath(value)
    if p.is_absolute() or PureWindowsPath(value).drive or any(x in ("", ".", "..") for x in value.split("/")):
        raise EvidenceError("Unsafe relative path: " + value)
    return Path(*p.parts)


def _safe_path(root: Path, value: str) -> Path:
    path = root / relative_path(value)
    for item in (path, *path.parents):
        if item == root.parent:
            break
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise EvidenceError("Links are not evidence paths: " + value)
    if not path.resolve().is_relative_to(root):
        raise EvidenceError("Path escapes evidence root: " + value)
    return path


def source_identity(root: Path) -> dict[str, str]:
    """Executable visual inputs only; local DLL/acceptance records are separate."""
    root = Path(root).resolve()
    if not (root / "harness/src/ftl_bench/native_acceptance.py").is_file():
        raise MissingEvidence("Portable acceptance currently requires a source checkout and its harness/src package; run with uv --directory harness, not a bundled wheel root")
    names = set()
    for directory in ("adapter", "harness/src/ftl_bench", "prompts", "native", "mod"):
        for path in (root / directory).rglob("*"):
            rel = path.relative_to(root)
            if (path.is_file() and not any(p in {"__pycache__", "_bundled", "build", "dist"} for p in rel.parts)
                    and path.suffix in {".py", ".json", ".md", ".lua", ".patch", ".h", ".inc", ".png"}):
                names.add(rel.as_posix())
    names.update(p.relative_to(root).as_posix() for p in (root / "scripts").glob("*visual*.py"))
    names.update(("scripts/run_fullgame_experiment.py", "scripts/validate_native_acceptance.py",
                  "scripts/write_native_provenance.py", "scripts/collect_native_source_evidence.py"))
    return {name: digest(_safe_path(root, name).read_bytes()) for name in sorted(names)}


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.pins = {}

    def bytes(self, reference, label):
        if reference is None:
            raise MissingEvidence(label + ": required hashed reference missing")
        if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            raise EvidenceError(label + ": expected {path, sha256}")
        name, expected = reference["path"], reference["sha256"]
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise EvidenceError(label + ": malformed SHA256")
        path = _safe_path(self.root, name)
        try:
            data = path.read_bytes()
        except FileNotFoundError as error:
            raise MissingEvidence(label + ": file missing: " + name) from error
        if digest(data) != expected:
            raise EvidenceError(label + ": SHA256 mismatch: " + name)
        if name in self.pins and self.pins[name] != expected:
            raise EvidenceError(label + ": conflicting pin: " + name)
        self.pins[name] = expected
        return data

    def json(self, reference, label):
        data = read_json(self.bytes(reference, label))
        if not isinstance(data, dict):
            raise EvidenceError(label + ": expected JSON object")
        return data

    def unchanged(self):
        return all(digest(_safe_path(self.root, name).read_bytes()) == sha for name, sha in self.pins.items())


def _require(value, message):
    if not value:
        raise EvidenceError(message)


def _fields(value, names, label):
    _require(isinstance(value, dict), label + ": expected object")
    missing = [name for name in names if name not in value]
    if missing:
        raise MissingEvidence(label + ": required raw fields missing: " + ", ".join(missing))


def _proof(proof, label):
    _require(proof.get("passed") is True and bool(proof.get("checks"))
        and all(v is True for v in proof["checks"].values()), label + ": " + str(proof))


def _drivers():
    """Load only shipped trusted source, never scripts under the evidence root."""
    root = _bench_root()
    scripts = root / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        modules = []
        for name in ("validate_visual_challenges", "validate_visual_timing"):
            spec = importlib.util.spec_from_file_location("_portable_" + name, scripts / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            previous = sys.modules.get("validate_visual_challenges")
            if modules:
                sys.modules["validate_visual_challenges"] = modules[0]
            try:
                spec.loader.exec_module(module)
            finally:
                if modules:
                    if previous is None:
                        sys.modules.pop("validate_visual_challenges", None)
                    else:
                        sys.modules["validate_visual_challenges"] = previous
            modules.append(module)
        return modules
    finally:
        sys.path.pop(0)


def _png(data):
    _require(data[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG signature")
    offset, dimensions, ended, compressed, channels = 8, None, False, [], None
    while offset < len(data):
        _require(offset + 12 <= len(data), "Truncated PNG")
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        _require(end <= len(data), "Truncated PNG chunk")
        kind, payload = data[offset + 4:offset + 8], data[offset + 8:end - 4]
        _require(zlib.crc32(kind + payload) & 0xffffffff == struct.unpack_from(">I", data, end - 4)[0], "PNG CRC mismatch")
        if offset == 8:
            _require(kind == b"IHDR" and size == 13, "PNG needs IHDR")
            dimensions = struct.unpack_from(">II", payload)
            depth, color, compression, filtering, interlace = payload[8:]
            _require(depth == 8 and color in (2, 6) and compression == filtering == interlace == 0,
                     "Unsupported native PNG pixel encoding")
            channels = 3 if color == 2 else 4
        elif kind == b"IHDR":
            raise EvidenceError("Duplicate PNG IHDR")
        if kind == b"IDAT":
            compressed.append(payload)
        if kind == b"IEND":
            _require(size == 0 and end == len(data), "PNG trailing bytes")
            ended = True
        offset = end
    _require(ended, "PNG missing IEND")
    _require(dimensions == (1280, 720) and compressed, "Native PNG needs full image data")
    expected = dimensions[1] * (1 + dimensions[0] * channels)
    decoder = zlib.decompressobj()
    try:
        pixels = decoder.decompress(b"".join(compressed), expected + 1)
    except zlib.error as error:
        raise EvidenceError("PNG pixel decompression failed") from error
    _require(len(pixels) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
             "PNG pixel stream is incomplete or oversized")
    _require(all(pixels[i] <= 4 for i in range(0, expected, 1 + dimensions[0] * channels)),
             "Invalid PNG row filter")
    return dimensions


def _capture(reader, trial, raw, ref):
    if not isinstance(ref, dict) or not isinstance(raw, dict):
        raise MissingEvidence("Canonical image/native reference missing")
    sha = ref.get("sha256")
    image = (trial.get("images") or {}).get(sha)
    data = reader.bytes(image, "image " + str(sha))
    _require(image["sha256"] == sha, "Image ref/native SHA mismatch")
    _require(_png(data) == (1280, 720) == (ref.get("width"), ref.get("height")), "Image layout mismatch")
    v = raw.get("visual") or {}
    for k in ("action_seq", "frame_id", "capture_id", "world_updates", "simulated_updates",
              "visual_clock_version", "fixed_step_numerator", "fixed_step_denominator", "external_input_generation",
              "width", "height", "coordinate_space"):
        _require(k in ref and k in v and ref[k] == v[k] and type(ref[k]) is type(v[k]), "Capture/native mismatch: " + k)
    _require(raw.get("last_action_seq") == v["action_seq"] and type(v["action_seq"]) is int
             and v["action_seq"] > 0 and type(v.get("visual_io_version")) is int and v["visual_io_version"] == 1
             and raw.get("paused") is True and v.get("paused") is True,
             "Capture/action acknowledgement mismatch")
    _require(type(v["capture_id"]) in (int, str) and v["capture_id"] != ""
             and isinstance(v["frame_id"], str) and bool(v["frame_id"]), "Malformed native screenshot identity")
    _require(ref["coordinate_space"] == "client", "Native capture coordinate space differs")
    caps = raw.get("capabilities") or {}
    for current in (v, caps):
        _require(all(type(current.get(k)) is int and current[k] == val for k, val in CAPABILITIES.items()
                     if k in ("visual_clock_version", "fixed_step_numerator", "fixed_step_denominator")),
                 "Capture fixed-step contract mismatch")
        counter = current.get("world_updates")
        _require(isinstance(counter, str) and counter.isascii() and counter.isdecimal()
                 and counter == current.get("simulated_updates") == v["world_updates"], "Capture counter mismatch")
    generation = v.get("external_input_generation")
    _require((raw.get("capabilities") or {}).get("external_input_guard") is True
             and v.get("external_input_detected") is False and isinstance(generation, str)
             and generation.isascii() and generation.isdecimal(),
             "External-input guard missing or tripped")
    return (v["action_seq"], v["frame_id"], v["capture_id"])


def _trajectory(reader, trial):
    data = reader.bytes(trial.get("trajectory"), "trajectory")
    rows = [read_json(line) for line in data.splitlines() if line.strip()]
    _require(all(isinstance(row, dict) for row in rows), "Malformed trajectory row")
    meta = [r for r in rows if r.get("kind") == "meta"]
    resets = [r for r in rows if r.get("kind") == "reset"]
    _require(len(meta) == len(resets) == 1 and rows.index(meta[0]) < rows.index(resets[0]), "One canonical meta/reset required")
    ends = [r for r in rows if r.get("kind") == "end"]
    _require(len(ends) == 1 and ends[0] is rows[-1] and ends[0].get("status") == "completed",
             "Evidence trajectory has no successful final lifecycle marker")
    _require(all(type(r.get("i")) is int and r["i"] == i - 1 for i, r in enumerate(rows)),
             "Trajectory indices incomplete or reordered")
    _require(not any(r.get("model") or str(r.get("kind", "")).startswith("model_") for r in rows),
             "No-model evidence contains model calls")
    m = meta[0]["meta"]
    _require(m.get("provider") == "none" and m.get("model") is None, "No-model provenance missing")
    _require(resets[0].get("actions") == [], "Reset must archive empty actor actions")
    return rows, meta[0]["meta"], resets[0]


def _runtime(reader, trial, dll_sha, bridge_sha):
    value = reader.json(trial.get("runtime"), "runtime fingerprint")
    _fields(value, ("native_dll", "bridge_lua", "native_build"), "runtime fingerprint")
    _require((value.get("native_dll") or {}).get("sha256") == dll_sha, "Observed DLL differs from build identity")
    _require((value.get("bridge_lua") or {}).get("sha256") == bridge_sha, "Observed bridge differs from prospective bridge")
    build = value.get("native_build") or {}
    _require(build.get("dll_sha256") == dll_sha and build.get("matches_installed_dll") is True,
             "Runtime/build DLL mismatch")
    _require(all(type(build.get(k)) is type(v) and build[k] == v for k, v in CAPABILITIES.items()),
             "Observed native capabilities differ")


def _cleanup(reader, trial, dll_sha, bridge_sha, provenance_sha):
    """Recorded point-in-time inventory, not a new live/process audit."""
    value = reader.json(trial.get("cleanup"), "portable cleanup")
    if value.get("contract") != "portable-cleanup-attestation-v1":
        raise MissingEvidence("Producer must record portable-cleanup-attestation-v1 with before/after inventory hashes, backup refs and checked_at; legacy passed booleans cannot supply those joins")
    required = ("before", "after", "backups", "restoration", "processes", "checked_at", "inventory_ids", "raw_inventory_refs", "trajectory", "session")
    if any(k not in value for k in required):
        raise MissingEvidence("Cleanup missing required fields: " + ", ".join(k for k in required if k not in value))
    for role in ("trajectory", "session"):
        _require(value[role] == trial.get(role), "Cleanup belongs to a different trial: " + role)
        reader.bytes(value[role], "cleanup bound " + role)
    before, after = value["before"], value["after"]
    _require(isinstance(before, dict) and before and before == after, "Recorded cleanup inventories differ")
    _require(all(isinstance(k, str) and k and (v is None or isinstance(v, str) and SHA.fullmatch(v))
                 for k, v in before.items()), "Malformed inventory hashes")
    roles = {"runtime/" + n for n in RUNTIME_FILES}
    roles.add("source/ftl_bench_dev.lua")
    if not roles.issubset(before) or any(before[k] is None for k in roles if k in before):
        raise MissingEvidence("Required runtime/production inventory roles missing")
    _require(before["runtime/Hyperspace.dll"] == dll_sha and before["source/ftl_bench_dev.lua"] == bridge_sha
             and before["runtime/ftlbench-native.json"] == provenance_sha, "Cleanup/runtime/current production identity mismatch")
    ids = value["inventory_ids"]
    raw_before = reader.json(value["raw_inventory_refs"].get("before"), "raw before inventory")
    raw_after = reader.json(value["raw_inventory_refs"].get("after"), "raw after inventory")
    _fields(raw_before, ("files_sha256",), "raw before inventory")
    _fields(raw_after, ("files_sha256", "processes", "no_game_process", "checked_at"), "raw after inventory")
    _require(isinstance(ids, dict) and set(ids) == set(raw_before.get("files_sha256") or {}) == set(raw_after.get("files_sha256") or {})
             and len(set(ids.values())) == len(ids) and set(ids.values()) == set(before), "Cleanup inventory ID map is not lossless")
    _require({ids[k]: v for k, v in raw_before["files_sha256"].items()} == before
             and {ids[k]: v for k, v in raw_after["files_sha256"].items()} == after, "Normalized/raw cleanup inventory mismatch")
    _require(raw_after.get("processes") == [] and raw_after.get("no_game_process") is True,
             "Raw post-cleanup process attestation missing")
    _require(value["processes"] == [], "Recorded cleanup still has game processes")
    parsed = datetime.fromisoformat(value["checked_at"].replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None, "Cleanup time must have timezone")
    raw_checked = datetime.fromisoformat(raw_after["checked_at"].replace("Z", "+00:00"))
    _require(raw_checked.tzinfo is not None and raw_checked <= parsed, "Normalized cleanup predates raw audit")
    restoration = reader.json(value["restoration"], "restoration")
    manifest = reader.json(value.get("backup_manifest"), "backup manifest")
    files = manifest.get("files")
    _require(isinstance(files, dict), "Missing original save inventory")
    _require({k[5:]: v for k, v in before.items() if k.startswith("save/") and k.endswith(".sav")} == files,
             "Original save inventory differs from backup manifest")
    _require(all(isinstance(v, str) and SHA.fullmatch(v) for v in files.values()), "Original save hash missing")
    _require(set(value["backups"]) == set(files) == set(restoration.get("files") or {}), "Backup/restoration save set mismatch")
    _require(restoration.get("verified") is True and all(v is True for v in restoration["files"].values()), "Restoration not verified")
    restored = datetime.fromisoformat(restoration["restored_at"].replace("Z", "+00:00"))
    _require(restored.tzinfo is not None and restored <= raw_checked <= parsed, "Cleanup predates restoration")
    for name, sha in files.items():
        _require(before.get("save/" + name) == sha, "Backup does not join original inventory: " + name)
        if sha is None:
            _require(value["backups"][name] is None, "Absent original has backup bytes")
        else:
            _require(digest(reader.bytes(value["backups"][name], "backup " + name)) == sha, "Backup bytes mismatch")
    joined_runtime = {ids[k]: v for k, v in raw_before["files_sha256"].items()}
    return {"checked_at": value["checked_at"], "inventory_paths": len(before), "save_paths": len(files),
            "runtime_files": {name: joined_runtime["runtime/" + name] for name in RUNTIME_FILES},
            "production_bridge_sha256": joined_runtime["source/ftl_bench_dev.lua"],
            "scope": "Saved point-in-time inventory/process attestation; no current live audit"}


def _common_runtime(startup, probes, identity, bridge_sha):
    """Join validated raw cleanup inventories, never saved acceptance flags."""
    if not startup or not isinstance(probes, list) or len(probes) != 9:
        raise MissingEvidence("Common runtime requires validated startup and exactly nine validated timing trials")
    inventories = []
    for trial in [startup, *probes]:
        cleanup = trial.get("cleanup") or {}
        files = cleanup.get("runtime_files")
        if not isinstance(files, dict) or any(files.get(n) is None for n in RUNTIME_FILES):
            raise MissingEvidence("Common runtime requires all six raw cleanup runtime hashes")
        _require(set(files) == set(RUNTIME_FILES) and all(isinstance(v, str) and SHA.fullmatch(v)
                 for v in files.values()), "Malformed common runtime inventory")
        _require(files["Hyperspace.dll"] == identity["dll_sha256"]
                 and files["ftlbench-native.json"] == identity["provenance_sha256"]
                 and cleanup.get("production_bridge_sha256") == bridge_sha,
                 "Common runtime/native/production bridge identity mismatch")
        inventories.append(files)
    _require(all(files == inventories[0] for files in inventories[1:]),
             "Runtime assets differ across startup and timing trials")
    return dict(sorted(inventories[0].items()))


def _startup(reader, trial, dll_sha, bridge_sha, expected_source_digest=None, provenance_sha=None):
    rows, meta, reset = _trajectory(reader, trial)
    _require([r.get("kind") for r in rows] == ["meta", "reset", "end"]
             and type(rows[-1].get("decisions")) is int and rows[-1]["decisions"] == 0,
             "Startup must be exact meta/reset/end with zero actor decisions")
    if expected_source_digest is not None:
        if "source_files_sha256" not in meta:
            raise MissingEvidence("Startup producer must record source_files_sha256 in canonical trajectory meta before launch")
        _require(meta["source_files_sha256"] == expected_source_digest, "Startup current source join mismatch")
    raw = reset["obs"]
    _require(type(meta.get("seed")) is int, "Startup seed missing")
    session = reader.json(trial.get("session"), "startup packet session")
    admission = reader.json(trial.get("admission"), "startup canonical admission")
    _fields(session, ("packets",), "startup session")
    _fields(admission, ("first_observation", "first_image"), "startup admission")
    _require(admission.get("first_observation") == raw and admission.get("first_image") == reset.get("visual", {}).get("before"),
             "Admission/trajectory first native image mismatch")
    _proof(fullgame_setup.receipt_proof(raw, meta["seed"]), "Fixture-free startup")
    _proof(fullgame_setup.packet_proof(raw, session.get("packets"), meta["seed"]), "Startup dispatched packets")
    _require(not any(r.get("kind") == "step" for r in rows), "Startup has backstage gameplay")
    image = (reset.get("visual") or {}).get("before")
    _require(image == (reset.get("visual") or {}).get("after"), "Startup image changed before actor")
    _capture(reader, trial, raw, image)
    _require(raw["visual"].get("requested_frames") == raw["visual"].get("actual_frames") == 0
             and type(raw["visual"].get("requested_frames")) is int
             and type(raw["visual"].get("actual_frames")) is int
             and raw["visual"].get("input_feedback") == [], "Startup capture advanced or delivered inputs")
    _require(raw.get("paused") is True and (raw.get("visual_evaluator") or {}).get("choice_window_open") is True,
             "Native first intro choice is not open and paused")
    _runtime(reader, trial, dll_sha, bridge_sha)
    return {"seed": meta["seed"], "first_image_sha256": image["sha256"], "world_updates": "0",
            "cleanup": _cleanup(reader, trial, dll_sha, bridge_sha, provenance_sha)}


def _probe(reader, trial, dll_sha, bridge_data, challenges, timing, expected_source_digest, provenance_sha):
    kind = trial.get("challenge")
    _require(kind in CHALLENGES, "Unknown probe challenge")
    rows, meta, reset = _trajectory(reader, trial)
    if "source_files_sha256" not in meta or "probe_delay_seconds" not in meta:
        raise MissingEvidence("Timing producer must record source_files_sha256 and probe_delay_seconds before launch")
    _require(meta["source_files_sha256"] == expected_source_digest
             and type(meta["probe_delay_seconds"]) in (int, float)
             and meta["probe_delay_seconds"] == trial["delay_seconds"], "Probe source/delay join mismatch")
    timing_sha = digest((_bench_root() / "scripts/validate_visual_timing.py").read_bytes())
    _require(digest(reader.bytes(trial.get("timing_script"), "timing producer")) == timing_sha
             and meta.get("timing_driver_sha256") == timing_sha, "Timing producer source join mismatch")
    raw = reset["obs"]
    session = reader.json(trial.get("session"), "probe packet session")
    _fields(session, ("packets",), "probe session")
    _proof(challenge_setup.receipt_proof(raw), "Probe fresh seed")
    _proof(challenge_setup.packet_proof(raw, session.get("packets")), "Probe setup packets")
    _proof(challenges.setup_proof(kind, raw), "Probe prerequisite")
    admission = reader.json(trial.get("admission"), "probe first admission")
    _fields(admission, ("first_observation", "first_image"), "probe admission")
    admitted, first_image = admission.get("first_observation"), admission.get("first_image")
    _proof(challenge_setup.receipt_proof(admitted), "Probe first native admission")
    _proof(challenge_setup.packet_proof(admitted, session.get("packets")), "Probe first admission packets")
    _capture(reader, trial, admitted, first_image)
    prior_packets = [r["packet"] for r in session["packets"]
                     if admitted["last_action_seq"] < r["packet"]["seq"] <= raw["last_action_seq"]]
    reset_image = reset["visual"]["after"]
    if not prior_packets:
        _require(admitted == raw and first_image == reset_image, "Probe reset is not the admitted native capture")
    else:
        close_actions = [{"type": "click", "x": 854, "y": 572, "button": "left", "modifiers": []}]
        move_actions = [{"type": "move", "x": 5, "y": 5}]
        _require(len(prior_packets) == 2, "Unknown pre-reset visual prerequisite packets")
        close = reader.json(trial.get("setup_store_close"), "ordinary store-close prerequisite")
        _require(close.get("before_observation") == admitted and close.get("before_image") == first_image
                 and close.get("actions") == close_actions and type(close.get("requested_frames")) is int
                 and close["requested_frames"] == 0, "Store-close source/input mismatch")
        closed, close_image = close["after_observation"], close["after_image"]
        _capture(reader, trial, closed, close_image)
        _require((admitted.get("visual_evaluator") or {}).get("store_open") is True
                 and (closed.get("visual_evaluator") or {}).get("store_open") is False,
                 "Native store-close transition not observed")
        for packet, before_image, observed, expected_actions in (
                (prior_packets[0], first_image, closed, close_actions),
                (prior_packets[1], close_image, raw, move_actions)):
            native = observed["visual"]
            _require(type(packet.get("seq")) is int and packet["seq"] == native["action_seq"]
                     and packet.get("actions") == expected_actions and packet.get("observation_mode") == "visual-v1"
                     and type(packet.get("advance_frames")) is int and packet["advance_frames"] == 0
                     and packet.get("expected_capture_id") == before_image["capture_id"]
                     and packet.get("expected_external_input_generation") == before_image["external_input_generation"]
                     and type(native.get("actual_frames")) is int and native["actual_frames"] == 0
                     and type(native.get("requested_frames")) is int and native["requested_frames"] == 0
                     and native["world_updates"] == before_image["world_updates"], "Store-close packet/native budget mismatch")
            feedback = native.get("input_feedback")
            _require(isinstance(feedback, list) and len(feedback) == 1 and feedback[0].get("index") == 0
                     and type(feedback[0].get("index")) is int and feedback[0].get("status") == "delivered"
                     and feedback[0].get("type") == expected_actions[0]["type"], "Store-close native delivery mismatch")
        _require(challenges.gameplay_signature(closed) == challenges.gameplay_signature(raw),
                 "Ordinary neutral cursor changed gameplay before reset")
    _require(meta.get("challenge") == kind and meta.get("fixture_version") == 6,
             "Probe fixture metadata mismatch")
    _require(type(meta.get("repetition")) is int and meta["repetition"] == trial["repetition"], "Probe repetition mismatch")
    _require(meta.get("production_bridge_sha256") == digest(bridge_data), "Probe measured a different production bridge")
    _require(meta.get("script_sha256") == digest((_bench_root() / "scripts/validate_visual_challenges.py").read_bytes())
             and meta.get("setup_helper_sha256") == digest((_bench_root() / "harness/src/ftl_bench/challenge_setup.py").read_bytes()),
             "Probe producer/helper source mismatch")
    fixture_sha = digest(challenges.fixture_bridge(bridge_data, kind, meta["run_id"]))
    _require(meta.get("fixture_bridge_sha256") == fixture_sha, "Fixture byte identity mismatch")
    _runtime(reader, trial, dll_sha, fixture_sha)
    steps = [r for r in rows if r.get("kind") == "step"]
    cases = timing.probe_cases(kind)
    _require(len(steps) == 2 * len(cases), "Probe lacks exact idle/action step pairs")
    _require([r.get("kind") for r in rows] == ["meta", "reset"] + ["step"] * len(steps) + ["end"],
             "Probe contains unknown or extra gameplay rows")
    image = reset["visual"]["after"]
    seen = {_capture(reader, trial, raw, image)}
    states, previous = [challenges.gameplay_signature(raw)], raw
    previous_time = reset.get("t")
    dispatched = [row["packet"] for row in session["packets"] if row["packet"]["seq"] > raw["last_action_seq"]]
    _require(len(dispatched) == len(steps), "Post-reset dispatched packet inventory differs from trajectory")
    packet_index = 0
    for index, (label, packet, frames) in enumerate(cases):
        idle, action = steps[2 * index:2 * index + 2]
        _require(type(previous_time) in (int, float) and type(idle.get("t")) in (int, float)
                 and idle["t"] - previous_time >= trial["delay_seconds"] - 0.05,
                 "Recorded idle interval is shorter than declared wall delay")
        _require(idle.get("thought") == label + "-idle-capture" and action.get("thought") == label,
                 "Probe step labels mismatch")
        for row, expected_actions, requested in ((idle, [], 0), (action, list(packet), frames)):
            _require(row.get("pre_obs") == previous and row.get("actions") == expected_actions,
                     "Trajectory predecessor/input mismatch")
            record = row.get("visual") or {}
            _require(record.get("before") == image, "Visual source capture mismatch")
            nxt = row["obs"]
            native = nxt.get("visual") or {}
            dispatched_packet = dispatched[packet_index]
            packet_index += 1
            _require(type(dispatched_packet.get("seq")) is int and dispatched_packet["seq"] == native.get("action_seq")
                     and dispatched_packet.get("observation_mode") == "visual-v1"
                     and dispatched_packet.get("actions") == expected_actions
                     and type(dispatched_packet.get("advance_frames")) is int and dispatched_packet["advance_frames"] == requested
                     and dispatched_packet.get("expected_capture_id") == image["capture_id"]
                     and dispatched_packet.get("expected_external_input_generation") == image["external_input_generation"],
                     "Actual dispatched visual packet/source capture mismatch")
            _proof(challenges.time_contract_proof(nxt), "Probe clock")
            _require(type(record.get("advance", {}).get("requested_frames")) is int
                     and record["advance"]["requested_frames"] == requested
                     and type(native.get("actual_frames")) is int and native["actual_frames"] == requested
                     and type(native.get("requested_frames")) is int and native["requested_frames"] == requested
                     and record["advance"].get("actual_frames") == requested
                     and challenges._counter(nxt) - challenges._counter(previous) == requested,
                     "Native update budget mismatch")
            feedback = native.get("input_feedback")
            _require(isinstance(feedback, list) and len(feedback) == len(expected_actions) and all(
                f.get("status") == "delivered" and type(f.get("index")) is int and f["index"] == i
                and f.get("type") == a["type"] for i, (a, f) in enumerate(zip(expected_actions, feedback))),
                "Input delivery mismatch")
            enriched = [{**a, "delivery": f["status"], **({"reason": f["reason"]} if f.get("reason") else {})}
                        for a, f in zip(expected_actions, feedback)]
            _require(record.get("inputs") == enriched, "Enriched visual/native input delivery mismatch")
            ref = record["after"]
            identity = _capture(reader, trial, nxt, ref)
            _require(identity not in seen and identity[0] > max(s[0] for s in seen)
                     and all(identity[n] not in {s[n] for s in seen} for n in (1, 2)), "Stale/reused native capture")
            _require(ref["external_input_generation"] == image["external_input_generation"], "External input generation changed")
            seen.add(identity)
            if row is idle:
                frozen = timing.idle_proof(previous, nxt)
                _require(frozen.get("passed") is True, "Fresh idle world did not remain frozen")
                _proof(frozen["time_contract_proof"], "Fresh idle clock")
            previous, image = nxt, ref
        states.append(challenges.gameplay_signature(previous))
        previous_time = action.get("t")
    if kind == "combat":
        _require(challenges._ship(previous)["hull"]["current"] < challenges._ship(raw)["hull"]["current"],
                 "Combat probe lacks actual hull damage")
    elif kind == "fire-crew-recovery":
        _proof(timing.fire_progression_proof(raw, previous), "Localized fire progression")
    else:
        _require(states[0]["player_ship"]["oxygen_pct"] > states[4]["player_ship"]["oxygen_pct"] > 0,
                 "Repair probe lacks ordinary oxygen depletion")
        for state, expected in ((states[0], 1), (states[2], 0), (states[5], 1)):
            _require(next(s for s in state["player_ship"]["systems"] if s["id"] == 2)["power"] == expected,
                     "Repair ordinary key effect missing")
    return {"states": states, "cleanup": _cleanup(reader, trial, dll_sha, digest(bridge_data), provenance_sha)}


def validate(spec: dict, *, source_root: Path, evidence_root: Path) -> dict:
    """Return derived scoped findings. Never installs, writes or accepts a cohort."""
    reader = Reader(evidence_root)
    source_root = Path(source_root).resolve()
    report = {"contract": CONTRACT, "status": "pending", "production_accepted": False,
        "controller_admission": False, "checks": {}, "missing_requirements": [], "errors": [],
        "scope": "Current-source native identity, fixture-free startup and finite nine-probe measured equality; no model/full-game or all-RNG determinism claim"}

    def run(label, operation):
        try:
            result = operation()
        except MissingEvidence as error:
            report["missing_requirements"].append(str(error))
            report["checks"][label] = "pending"
        except (EvidenceError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration) as error:
            report["errors"].append(label + ": " + str(error))
            report["checks"][label] = "invalid"
        else:
            report["checks"][label] = "validated_scoped"
            return result

    if not isinstance(spec, dict) or spec.get("contract") != CONTRACT:
        report["status"] = "invalid"
        report["errors"].append("Wrong portable acceptance spec contract")
        return report

    def sources():
        snapshot = reader.json(spec.get("source_snapshot"), "source snapshot")
        _fields(snapshot, ("source_files", "archived_files"), "source snapshot")
        current = source_identity(source_root)
        _require(snapshot.get("source_files") == current, "Source snapshot differs from current source inventory/bytes")
        archived = snapshot.get("archived_files")
        if not isinstance(archived, dict):
            raise MissingEvidence("source snapshot requires archived_files hashed refs for every source_files entry")
        _require(set(archived) == set(current), "Archived source inventory mismatch")
        for name, sha in current.items():
            _require(digest(reader.bytes(archived[name], "source " + name)) == sha, "Archived source bytes mismatch: " + name)
        _require(current == source_identity(_bench_root()), "Verifier's executable source differs from requested source root")
        for module in (sys.modules[__name__], challenge_setup, fullgame_setup):
            expected = source_root / "harness/src/ftl_bench" / (module.__name__.split(".")[-1] + ".py")
            _require(Path(module.__file__).resolve() == expected.resolve(), "Executing Python helper is outside the source checkout")
        return current

    current = run("current_source_snapshot", sources)
    if current is not None and "producer_descriptors" in spec:
        def descriptors():
            producers = spec["producer_descriptors"]
            first = reader.json(producers.get("startup"), "startup producer descriptor")
            second = reader.json(producers.get("timing"), "timing producer descriptor")
            _require(first.get("contract") == "visual-startup-evidence-v1"
                     and second.get("contract") == "visual-timing-evidence-v1", "Producer descriptor contract mismatch")
            _require(first.get("startup") == spec.get("startup") and second.get("probes") == spec.get("probes"),
                     "Spec/producer descriptor trial inventory differs")
            for name, doc in (("startup", first), ("timing", second)):
                snapshot = reader.json(doc.get("source_snapshot"), name + " source snapshot")
                _require(snapshot.get("source_files") == current, "Producer source snapshots differ")
                archived = snapshot.get("archived_files") or {}
                _require(set(archived) == set(current), "Producer archived source inventory differs")
                for source_name, sha in current.items():
                    _require(digest(reader.bytes(archived[source_name], name + " archived " + source_name)) == sha,
                             "Producer archived source bytes differ")
        run("producer_descriptor_joins", descriptors)

    def native():
        fields = spec.get("native") or {}
        data = reader.bytes(fields.get("dll"), "native DLL")
        prov = reader.json(fields.get("provenance"), "native provenance")
        manifest = read_json(_safe_path(source_root, "native/manifest.json").read_bytes())
        patch = _safe_path(source_root, manifest["patch"]).read_bytes()
        _require(digest(patch) == manifest["patch_sha256"] == prov.get("patch_sha256"), "Native patch identity mismatch")
        _require(prov.get("dll_sha256") == digest(data) and type(prov.get("dll_size")) is int and prov["dll_size"] == len(data), "DLL provenance mismatch")
        _require(prov.get("source_commit") == manifest["base_commit"] and prov.get("repository") == manifest["repository"], "Native build base differs")
        for doc in (manifest, prov):
            _require(all(type(doc.get(k)) is type(v) and doc[k] == v for k, v in CAPABILITIES.items()), "Native capability contract mismatch")
        _require(prov.get("platform") == "windows-x86" and prov.get("game_version") == "1.6.9", "Wrong native target")
        source_hashes = prov.get("source_files_sha256") or {}
        names = set(re.findall(r"^diff --git a/(\S+) b/\1$", patch.decode("utf-8"), re.MULTILINE))
        _require(names and set(source_hashes) == names and all(isinstance(v, str) and SHA.fullmatch(v)
             for v in source_hashes.values()), "Native patched source provenance is incomplete or malformed")
        for path in (source_root / "native/include").glob("*"):
            if path.is_file():
                _require(source_hashes.get(path.name) == digest(path.read_bytes()), "Native include/provenance mismatch: " + path.name)
        reconstruction = None
        if "source_reconstruction" in fields:
            from ftl_bench.native_build_origin import reconstruct_sources
            reconstruction = reconstruct_sources(manifest=manifest, patch=patch,
                proof=reader.json(fields["source_reconstruction"], "native source reconstruction"), reader=reader)
            _require(reconstruction["source_files_sha256"] == source_hashes,
                     "Reconstructed native source bytes differ from build provenance")
        return {"dll_sha256": digest(data), "provenance_sha256": fields["provenance"]["sha256"],
            "patch_sha256": digest(patch), "source_commit": prov["source_commit"], "built_at": prov.get("built_at"),
            "source_reconstruction": reconstruction,
            "scope": "Artifact/source-provenance joins only; no compiler or live execution inferred"}

    identity = run("native_build_identity", native)
    if identity:
        report["native_identity"] = identity

    def bridge():
        data = reader.bytes(spec.get("bridge"), "prospective bridge")
        _require(data == _safe_path(source_root, BRIDGE).read_bytes(), "Prospective bridge differs from current source")
        return data

    bridge_data = run("prospective_bridge_identity", bridge)
    if bridge_data is not None:
        report["bridge_identity"] = {"sha256": digest(bridge_data), "source_path": BRIDGE}
    startup_result, probe_results = None, None
    if current is not None and identity and bridge_data is not None:
        startup = spec.get("startup")
        if not isinstance(startup, dict):
            report["missing_requirements"].append("startup: required trajectory/session/runtime/cleanup/images refs missing")
            report["checks"]["fixture_free_startup"] = "pending"
        else:
            result = run("fixture_free_startup", lambda: _startup(reader, startup, identity["dll_sha256"], digest(bridge_data), source_digest(current), identity["provenance_sha256"]))
            if result:
                report["startup"] = result
                startup_result = result
        probes = spec.get("probes")
        if not isinstance(probes, list) or len(probes) != 9:
            report["missing_requirements"].append("probes: exactly nine current-bridge raw trials required (3 challenges × delays 0, 0.35, 1.2; repetition 1..3)")
            report["checks"]["nine_probe_repeatability"] = "pending"
        else:
            def repeats():
                _require(all(isinstance(t, dict) for t in probes), "Malformed probe descriptor")
                expected = {(c, i + 1, d) for c in CHALLENGES for i, d in enumerate(DELAYS)}
                actual = [(t.get("challenge"), t.get("repetition"), t.get("delay_seconds")) for t in probes]
                _require(all(type(t.get("repetition")) is int and type(t.get("delay_seconds")) in (int, float) for t in probes)
                         and len(set(actual)) == 9 and set(actual) == expected, "Probe inventory/delay mismatch")
                challenges, timing = _drivers()
                states, trials = {}, []
                for trial in probes:
                    result = _probe(reader, trial, identity["dll_sha256"], bridge_data, challenges, timing, source_digest(current), identity["provenance_sha256"])
                    states.setdefault(trial["challenge"], []).append(result["states"])
                    trials.append(result)
                _require(all(values[0] == values[1] == values[2] for values in states.values()), "Measured gameplay trajectories diverged across delays")
                return {"summary": {"trials": 9, "challenges": list(CHALLENGES), "delays_seconds": list(DELAYS)}, "results": trials}
            result = run("nine_probe_repeatability", repeats)
            if result:
                report["repeatability"] = result["summary"]
                probe_results = result["results"]
    def common_runtime():
        if identity is None or bridge_data is None:
            raise MissingEvidence("Common runtime requires native and production bridge identities")
        return _common_runtime(startup_result, probe_results, identity, digest(bridge_data))
    runtime_files = run("common_runtime_identity", common_runtime)
    if runtime_files is not None:
        report["runtime_files"] = runtime_files
        report["native_identity"]["runtime_files"] = runtime_files
        report["native_identity"]["production_bridge_sha256"] = digest(bridge_data)
    run("evidence_unchanged", lambda: _require(reader.unchanged(), "Evidence changed during validation"))
    if current is not None:
        run("current_sources_unchanged", lambda: _require(source_identity(source_root) == current, "Current sources changed during validation"))
    report["evidence_files"] = dict(sorted(reader.pins.items()))
    report["source_files"] = current or {}
    report["status"] = "invalid" if report["errors"] else "pending" if report["missing_requirements"] else "validated_scoped"
    return report


def write_report(path: Path, report: dict):
    """Exclusive creation: preserving prior evidence is part of the API."""
    with Path(path).open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
