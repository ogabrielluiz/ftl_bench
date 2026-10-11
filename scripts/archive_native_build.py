"""Retain prospective native build inputs and bind the original output, offline.

This records bytes and declared provenance, not proof of compiler execution or
independent review. Failed and partially written archives are never removed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

PREPARATION = "native-build-preparation-v1"
ORIGIN = "portable-native-build-origin-v1"
CAPABILITIES = ("native_protocol", "visual_io_version", "visual_clock_version",
                "fixed_step_numerator", "fixed_step_denominator", "fresh_start_seed",
                "fresh_seed_contract_version", "fresh_seed_contract")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    path = Path(value)
    if ".." in path.parts:
        raise ValueError("Traversal is forbidden")
    path = path.absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("Links are forbidden: " + str(item))
    return path


def relative(value):
    if not isinstance(value, str) or "\\" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Expected a portable relative path")
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or path.as_posix() != value
            or any(p in ("", ".", "..") or ":" in p for p in path.parts)):
        raise ValueError("Unsafe relative path")
    return value


def read(path):
    path = safe_path(path)
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Input must be a regular file: " + str(path))
    return path.read_bytes()


def write(path, data):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def document(path, value):
    write(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def reference(root, path):
    path = safe_path(path)
    return {"path": relative(path.relative_to(root).as_posix()), "sha256": sha(read(path))}


def inputs(source, source_root):
    manifest_bytes = read(source_root / "native/manifest.json")
    manifest = json.loads(manifest_bytes)
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("base_commit", "")):
        raise ValueError("Manifest base must be an exact Git commit")
    patch = read(source_root / relative(manifest["patch"]))
    if sha(patch) != manifest["patch_sha256"]:
        raise ValueError("Manifest patch hash differs")
    headers = re.findall(rb"^diff --git a/(\S+) b/(\S+)$", patch, re.MULTILINE)
    names = []
    for before, after in headers:
        if before != after:
            raise ValueError("Renamed patch paths are unsupported")
        names.append(relative(before.decode("utf-8")))
    if not names or len(names) != len(set(names)):
        raise ValueError("Patch source inventory is empty or duplicate")
    top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=source, text=True).strip()
    if safe_path(top).resolve() != source.resolve():
        raise ValueError("Source must be the native Git checkout root")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != manifest["base_commit"]:
        raise ValueError("Native source base differs")
    files = {name: read(source / name) for name in sorted(names)}
    diff = subprocess.check_output(["git", "diff", "--no-ext-diff", "--binary", "HEAD"], cwd=source)
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=source).decode().split("\0")
    for name in sorted(set(names).intersection(untracked)):
        result = subprocess.run(["git", "diff", "--no-ext-diff", "--no-index", "--binary", "--", "/dev/null", name],
                                cwd=source, capture_output=True)
        if result.returncode not in (0, 1):
            raise ValueError("Cannot snapshot untracked patched source: " + name)
        diff += result.stdout
    return manifest, manifest_bytes, patch, files, diff


def locations(source, source_root, evidence_root, output):
    source, source_root, evidence_root, output = map(safe_path, (source, source_root, evidence_root, output))
    if not source.is_dir() or not source_root.is_dir():
        raise ValueError("Both source directories must exist")
    if not output.is_relative_to(evidence_root) or output == evidence_root or output.is_relative_to(source):
        raise ValueError("Archive must be below evidence root and outside native source")
    return source, source_root, evidence_root, output


def prepare(*, source, source_root, evidence_root, output):
    source, source_root, evidence_root, output = locations(source, source_root, evidence_root, output)
    if output.exists():
        raise FileExistsError("Build archive already exists")
    manifest, manifest_bytes, patch, files, diff = inputs(source, source_root)
    output.mkdir(parents=True, exist_ok=False)
    write(output / "manifest.json", manifest_bytes)
    write(output / "native.patch", patch)
    write(output / "source.diff", diff)
    refs = {}
    for name, data in files.items():
        path = output / "build-sources" / name
        write(path, data)
        refs[name] = reference(evidence_root, path)
    value = {"contract": PREPARATION, "prepared_at": datetime.now(timezone.utc).isoformat(),
             "source_commit": manifest["base_commit"], "patch_sha256": sha(patch),
             "manifest": reference(evidence_root, output / "manifest.json"),
             "patch": reference(evidence_root, output / "native.patch"),
             "source_diff": reference(evidence_root, output / "source.diff"),
             "build_sources": refs, "scope": "Pre-build bytes only; no compiler or acceptance attestation."}
    document(output / "preparation.json", value)
    return output / "preparation.json"


def finish(*, source, source_root, evidence_root, output, dll, provenance):
    source, source_root, evidence_root, output = locations(source, source_root, evidence_root, output)
    if (output / "build-origin.json").exists() or (output / "artifacts").exists():
        raise FileExistsError("Build finish already started; preserve partial archive")
    prepared = json.loads(read(output / "preparation.json"))
    if prepared.get("contract") != PREPARATION:
        raise ValueError("Wrong preparation contract")
    manifest, manifest_bytes, patch, files, diff = inputs(source, source_root)
    expected_paths = {"manifest.json": manifest_bytes, "native.patch": patch, "source.diff": diff}
    refs = {}
    for name, data in files.items():
        expected_paths["build-sources/" + name] = data
        refs[name] = reference(evidence_root, output / "build-sources" / name)
    for name, data in expected_paths.items():
        if read(output / name) != data:
            raise ValueError("Build source or archive changed: " + name)
    actual = set()
    for path in (output / "build-sources").rglob("*"):
        safe_path(path)
        if path.is_file():
            actual.add(path.relative_to(output / "build-sources").as_posix())
    if actual != set(files):
        raise ValueError("Build source archive inventory differs")
    if (prepared.get("source_commit") != manifest["base_commit"]
            or prepared.get("patch_sha256") != sha(patch) or prepared.get("build_sources") != refs
            or prepared.get("manifest") != reference(evidence_root, output / "manifest.json")
            or prepared.get("patch") != reference(evidence_root, output / "native.patch")
            or prepared.get("source_diff") != reference(evidence_root, output / "source.diff")):
        raise ValueError("Preparation bindings differ")
    dll_bytes = read(dll)
    provenance_bytes = read(provenance)
    record = json.loads(provenance_bytes)
    if record.get("production_reuse_of_tested_build") or record.get("classification") == "production_reuse_of_tested_build":
        raise ValueError("Historical reuse is not a fresh build")
    if (not dll_bytes or record.get("dll_sha256") != sha(dll_bytes)
            or type(record.get("dll_size")) is not int or record["dll_size"] != len(dll_bytes)
            or record.get("source_files_sha256") != {name: sha(data) for name, data in files.items()}
            or record.get("source_diff_sha256") != sha(diff)
            or record.get("source_commit") != manifest["base_commit"]):
        raise ValueError("Original provenance differs from DLL or prepared sources")
    for name in ("repository", "patch_sha256", *CAPABILITIES):
        if name not in manifest or type(record.get(name)) is not type(manifest[name]) or record[name] != manifest[name]:
            raise ValueError("Original provenance differs from manifest: " + name)
    if record.get("platform") != "windows-x86" or record.get("game_version") != "1.6.9":
        raise ValueError("Wrong native platform or game version")
    built = datetime.fromisoformat(record["built_at"])
    prepared_at = datetime.fromisoformat(prepared["prepared_at"])
    if built.tzinfo is None or prepared_at.tzinfo is None or built < prepared_at:
        raise ValueError("Original build timestamp must follow preparation")
    toolchain = record.get("toolchain", {})
    if (not isinstance(toolchain, dict)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", str(toolchain.get("image", "")))
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(toolchain.get("image_id", "")))
            or not isinstance(toolchain.get("build_command"), str) or not toolchain["build_command"].strip()
            or "compiler" in toolchain and (not isinstance(toolchain["compiler"], str) or not toolchain["compiler"].strip())):
        raise ValueError("Original toolchain identities missing or malformed")
    write(output / "artifacts/Hyperspace.visual-v1.dll", dll_bytes)
    write(output / "artifacts/native-build.visual-v1.json", provenance_bytes)
    origin = {"contract": ORIGIN, "kind": "fresh",
              "record": reference(evidence_root, output / "artifacts/native-build.visual-v1.json"),
              "build_sources": refs}
    document(output / "build-origin.json", origin)
    return output / "build-origin.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "finish"))
    for name in ("source", "source-root", "evidence-root", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--dll", type=Path)
    parser.add_argument("--provenance", type=Path)
    args = vars(parser.parse_args())
    operation = args.pop("operation")
    if operation == "prepare":
        if args.pop("dll") is not None or args.pop("provenance") is not None:
            parser.error("prepare excludes --dll and --provenance")
    elif args["dll"] is None or args["provenance"] is None:
        parser.error("finish requires --dll and --provenance")
    try:
        print((prepare if operation == "prepare" else finish)(**args))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
