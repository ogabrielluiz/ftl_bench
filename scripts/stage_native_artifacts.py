"""Validate and stage a local visual DLL/provenance pair; never install or accept it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4


NAMES = ("Hyperspace.visual-v1.dll", "native-build.visual-v1.json")
CAPABILITIES = ("native_protocol", "visual_io_version", "visual_clock_version", "fixed_step_numerator",
                "fixed_step_denominator", "fresh_start_seed", "fresh_seed_contract_version", "fresh_seed_contract")


def manifest_from(root: Path) -> dict:
    manifest = json.loads((root / "native/manifest.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("base_commit", "")):
        raise ValueError("manifest must declare a full native base_commit")
    repository = manifest.get("repository", "")
    if not isinstance(repository, str) or not repository.startswith("https://") or any(c.isspace() for c in repository):
        raise ValueError("manifest must declare an HTTPS native repository")
    patch = (root / manifest["patch"]).resolve(strict=True)
    if not patch.is_relative_to(root.resolve()) or hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise ValueError("native patch does not match its manifest")
    return manifest


def validate_pair(dll: Path, provenance: Path, manifest: dict) -> dict[str, bytes]:
    """Validate file identities only; this does not prove build or live behavior."""
    payload = {NAMES[0]: dll.read_bytes(), NAMES[1]: provenance.read_bytes()}
    value = json.loads(payload[NAMES[1]])
    if not isinstance(value, dict):
        raise ValueError("provenance must be an object")
    if (not payload[NAMES[0]] or hashlib.sha256(payload[NAMES[0]]).hexdigest() != value.get("dll_sha256")
            or type(value.get("dll_size")) is not int or len(payload[NAMES[0]]) != value["dll_size"]):
        raise ValueError("DLL bytes/size do not match provenance")
    for key in ("repository", "patch_sha256", *CAPABILITIES):
        if key not in manifest or type(value.get(key)) is not type(manifest[key]) or value[key] != manifest[key]:
            raise ValueError("provenance differs from current native manifest: " + key)
    if value.get("source_commit") != manifest["base_commit"]:
        raise ValueError("provenance source_commit differs from manifest base_commit")
    if value.get("platform") != "windows-x86" or value.get("game_version") != "1.6.9":
        raise ValueError("visual artifact requires Windows x86 / FTL 1.6.9")
    toolchain = value.get("toolchain")
    if (not isinstance(toolchain, dict)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", str(toolchain.get("image", "")))
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(toolchain.get("image_id", "")))):
        raise ValueError("provenance must record immutable registry image and resolved image ID")
    return payload


def stage_pair(dll: Path, provenance: Path, output: Path, manifest: dict) -> dict:
    payload = validate_pair(dll, provenance, manifest)
    output.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        if (output / name).is_symlink():
            raise ValueError("linked artifact destinations are refused")
    previous = {name: (output / name).read_bytes() for name in NAMES if (output / name).exists()}
    if previous == payload:
        return {"status": "unchanged", "directory": str(output.resolve()), "acceptance": "not_evaluated"}
    token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex
    backup = output / "native-history" / token
    if previous:
        backup.mkdir(parents=True)
        for name, data in previous.items():
            (backup / name).write_bytes(data)
    staged = {}
    try:
        for name, data in payload.items():
            path = output / ("." + name + "." + token + ".tmp")
            with path.open("xb") as stream:
                stream.write(data)
            staged[name] = path
        for name, path in staged.items():
            os.replace(path, output / name)
    except BaseException:
        # A two-file pair cannot be atomically replaced as one filesystem object.
        # Restore its prior bytes on an observed write failure; a process crash
        # remains detectable by the installer's DLL/provenance hash validation.
        for name in NAMES:
            if name in previous:
                (output / name).write_bytes(previous[name])
            elif (output / name).exists():
                (output / name).unlink()
        raise
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)
    return {"status": "staged", "directory": str(output.resolve()),
            "previous_artifacts": str(backup.resolve()) if previous else None,
            "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
            "acceptance": "not_evaluated"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("config", "verify", "stage"))
    parser.add_argument("--dll", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        manifest = manifest_from(root)
        if args.operation == "config":
            print(manifest["repository"] + "\n" + manifest["base_commit"])
            return
        if args.dll is None or args.provenance is None:
            parser.error("--dll and --provenance are required")
        if args.operation == "verify":
            validate_pair(args.dll, args.provenance, manifest)
            print("DLL/provenance identities verified; live acceptance not evaluated")
        else:
            print(json.dumps(stage_pair(args.dll, args.provenance, args.output_dir or root / "dist", manifest)))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
