"""Pin Windows loader inputs to native manifest Git blobs; no build or install."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

RELEASE = "Release Files/Windows/"
REQUIRED = {"xinput1_4.dll", "lua-5.3.dll", "patch/flips.exe"}


def safe_path(value):
    path = Path(value).absolute()
    if ".." in path.parts:
        raise ValueError("Unsafe path traversal")
    for entry in (path, *path.parents):
        if entry.is_symlink() or getattr(entry, "is_junction", lambda: False)():
            raise ValueError("Linked loader input/output path: " + str(entry))
        if entry.exists() and getattr(entry.stat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise ValueError("Reparse loader input/output path: " + str(entry))
    return path


def git(source, *args):
    result = subprocess.run(["git", "-C", str(source), *args], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("Cannot read declared native Git objects")
    return result.stdout


def pin_native_loader(source, manifest, output):
    source, manifest, output = map(safe_path, (source, manifest, output))
    if output.exists():
        raise ValueError("Loader input receipt already exists")
    document = json.loads(manifest.read_bytes())
    commit = document.get("base_commit") if isinstance(document, dict) else None
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Native manifest requires full base_commit")
    if git(source, "rev-parse", "--verify", commit + "^{commit}").decode().strip() != commit:
        raise ValueError("Declared native base commit is not available")
    entries = {}
    for entry in git(source, "ls-tree", "-rz", commit, "--", RELEASE.rstrip("/")).split(b"\0"):
        if not entry:
            continue
        header, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if not name.startswith(RELEASE):
            raise ValueError("Unexpected native release tree path")
        rel = name[len(RELEASE):]
        path = PurePosixPath(rel)
        if (path.is_absolute() or path.as_posix() != rel or ".." in path.parts
                or "\\" in rel or ":" in rel):
            raise ValueError("Unsafe native release tree path")
        if rel in REQUIRED or (len(path.parts) == 2 and path.parts[0] == "patch" and path.suffix == ".bps"):
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError("Loader input is not a regular Git blob: " + rel)
            entries[rel] = oid
    if not REQUIRED <= entries.keys() or not any(name.endswith(".bps") for name in entries):
        raise ValueError("Missing declared loader or BPS inputs")
    release = safe_path(source / RELEASE)
    patch = safe_path(release / "patch")
    actual_bps = set()
    for file in patch.iterdir():
        if file.suffix.lower() == ".bps":
            safe_path(file)
            if not file.is_file():
                raise ValueError("BPS input must be a regular file")
            actual_bps.add("patch/" + file.name)
    expected_bps = {name for name in entries if name.endswith(".bps")}
    if actual_bps != expected_bps:
        raise ValueError("Working release has missing or extra BPS inputs")
    inputs = {}
    for name, oid in sorted(entries.items()):
        path = safe_path(release / name)
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("Loader input must be a regular file: " + name)
        expected = git(source, "cat-file", "blob", oid)
        if path.read_bytes() != expected:
            raise ValueError("Loader input differs from declared base Git bytes: " + name)
        inputs[name] = {"bytes": len(expected), "sha256": hashlib.sha256(expected).hexdigest()}
    result = {"contract": "native-loader-inputs-v1", "source_commit": commit, "inputs": inputs}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as receipt:
        json.dump(result, receipt, sort_keys=True, indent=2)
        receipt.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    pin_native_loader(args.source, args.manifest, args.output)


if __name__ == "__main__":
    main()
