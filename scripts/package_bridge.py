#!/usr/bin/env python3
"""Package the patched bootstrap; external dev Lua is deployed separately."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile


class PackagingError(ValueError):
    """An input or output cannot safely be packaged."""


def _no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise PackagingError(f"Symlink or junction is not allowed: {part}")


def _members(mod: Path) -> dict[str, bytes]:
    _no_links(mod)
    data = mod / "data"
    _no_links(data)
    if not data.is_dir():
        raise PackagingError("Missing bridge data directory")
    paths = []
    def scan_error(error: OSError) -> None:
        raise error

    for base, directories, files in os.walk(data, followlinks=False, onerror=scan_error):
        for name in directories + files:
            path = Path(base) / name
            _no_links(path)
            if not path.is_dir():
                if not stat.S_ISREG(path.stat().st_mode):
                    raise PackagingError(f"Not a regular source file: {path}")
                paths.append(path)
    paths.append(mod / "mod-appendix" / "metadata.xml")
    members = {}
    names = set()
    for path in paths:
        _no_links(path)
        if not path.is_file():
            raise PackagingError(f"Missing bridge file: {path}")
        name = path.relative_to(mod).as_posix()
        if "\\" in name or any(ord(c) < 32 for c in name):
            raise PackagingError(f"Unsafe archive name: {name!r}")
        if name.casefold() in names:
            raise PackagingError(f"Duplicate archive name: {name}")
        names.add(name.casefold())
        members[name] = path.read_bytes()
    required = {"data/bridge.lua", "data/json.lua", "data/observation.lua",
                "data/hyperspace.xml.append", "mod-appendix/metadata.xml"}
    if not required <= members.keys():
        raise PackagingError(f"Missing bridge files: {sorted(required - members.keys())}")
    return members


def package_bridge(output: str | Path, *, source_root: str | Path | None = None) -> dict:
    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[1]
    root = Path(os.path.abspath(root))
    target = Path(os.path.abspath(output))
    mod = root / "mod" / "ftl_bench_bridge"
    _no_links(target)
    if target == mod or mod in target.parents:
        raise PackagingError("Output must be outside the bridge source directory")
    if target.exists() and not target.is_file():
        raise PackagingError("Output must be a regular file")
    members = _members(mod)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_STORED
            archive.writestr(entry, members[name])
    content = buffer.getvalue()
    result = {"output": str(target), "sha256": hashlib.sha256(content).hexdigest(),
              "bytes": len(content), "members": sorted(members), "status": "unchanged"}
    if target.exists() and target.read_bytes() == content:
        return result
    target.parent.mkdir(parents=True, exist_ok=True)
    _no_links(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{target.name}.", suffix=".tmp",
                                         dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _no_links(target)
        os.replace(temporary, target)
        result["status"] = "written"
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, help="Repository root (default: this script's checkout)")
    args = parser.parse_args(argv)
    try:
        result = package_bridge(args.output, source_root=args.source_root)
    except (OSError, PackagingError) as exc:
        parser.exit(1, f"Bridge packaging failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
