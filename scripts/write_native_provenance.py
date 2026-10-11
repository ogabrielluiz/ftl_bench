"""Record the exact native source, patch, build image, and produced DLL."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
from pathlib import Path


def source_snapshot(source: Path, patch: Path) -> tuple[bytes, dict[str, str]]:
    """Capture tracked changes and every patched file, including untracked headers."""
    source = source.resolve(strict=True)
    names = sorted(set(re.findall(r"^diff --git a/(\S+) b/\1$", patch.read_text(), re.MULTILINE)))
    if not names:
        raise ValueError("native patch contains no source paths")
    hashes = {}
    for name in names:
        path = (source / name).resolve(strict=True)
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError(f"invalid patched source path: {name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    diff = subprocess.check_output(["git", "diff", "--no-ext-diff", "--binary", "HEAD"], cwd=source)
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                                        cwd=source).decode().split("\0")
    for name in sorted(set(names).intersection(untracked)):
        result = subprocess.run(["git", "diff", "--no-ext-diff", "--no-index", "--binary", "--",
                                 "/dev/null", name], cwd=source, capture_output=True)
        if result.returncode not in (0, 1):
            raise subprocess.CalledProcessError(result.returncode, result.args,
                                                output=result.stdout, stderr=result.stderr)
        diff += result.stdout
    return diff, hashes


def original_build_timestamp(value: str) -> str:
    """Require an explicit timezone when recording an earlier artifact build."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--built-at requires an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--built-at requires an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def immutable_image_ref(value: str) -> str:
    """Require a pullable registry digest, not a mutable tag or local image ID."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("build image must be a registry reference ending @sha256:<64 lowercase hex digits>")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="ghcr.io/ftl-hyperspace/hs-devcontainer:v2")
    parser.add_argument("--require-base", action="store_true", help="require the exact manifest base commit")
    parser.add_argument("--require-immutable-image", action="store_true", help="require a pullable registry digest")
    parser.add_argument("--compiler", help="Actual observed compiler identity; omitted when unavailable")
    parser.add_argument("--build-command", default="buildscripts/windows/build-releaseonly-from-docker.sh",
                        help="Exact build command used to produce this DLL")
    parser.add_argument("--built-at", type=original_build_timestamp,
                        help="Original artifact build timestamp with timezone; omit when recording a build now")
    args = parser.parse_args()
    if args.require_immutable_image:
        try:
            immutable_image_ref(args.image)
        except argparse.ArgumentTypeError as error:
            parser.error(str(error))
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "native/manifest.json").read_text())
    patch = root / manifest["patch"]
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        parser.error("native patch does not match its recorded SHA-256")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.source, text=True).strip()
    if args.require_base and commit != manifest.get("base_commit"):
        parser.error("native checkout HEAD differs from native/manifest.json base_commit")
    diff, source_hashes = source_snapshot(args.source, patch)
    image_id = subprocess.check_output(["docker", "image", "inspect", args.image,
                                       "--format", "{{.Id}}"], text=True).strip()
    if args.require_immutable_image and not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        parser.error("Docker did not return a valid resolved image ID")
    generated_at = datetime.now(timezone.utc).isoformat()
    output = {
        "built_at": args.built_at or generated_at,
        "provenance_generated_at": generated_at,
        "repository": manifest["repository"], "source_commit": commit,
        "source_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "source_files_sha256": source_hashes,
        "patch_sha256": manifest["patch_sha256"], "native_protocol": manifest["native_protocol"],
        "platform": "windows-x86", "game_version": "1.6.9",
        "toolchain": {"image": args.image, "image_id": image_id,
                      "build_command": args.build_command},
        "dll_sha256": hashlib.sha256(args.dll.read_bytes()).hexdigest(),
        "dll_size": args.dll.stat().st_size,
    }
    if args.compiler:
        output["toolchain"]["compiler"] = args.compiler
    for capability in ("visual_io_version", "visual_clock_version", "fixed_step_numerator", "fixed_step_denominator",
                       "fresh_start_seed", "fresh_seed_contract_version", "fresh_seed_contract"):
        if capability in manifest:
            output[capability] = manifest[capability]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
