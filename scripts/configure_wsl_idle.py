"""Set a missing WSL idle timeout without replacing explicit user settings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4


def safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("Linked configuration paths are refused")
    if path.exists() and not path.is_file():
        raise ValueError("Configuration must be a regular file")
    return path


def transform(raw: bytes) -> tuple[bytes, str]:
    text = raw.decode("utf-8-sig")
    if "\x00" in text or "\r" in text.replace("\r\n", ""):
        raise ValueError("Malformed configuration encoding or line endings")
    lines = text.splitlines(keepends=True)
    section = None
    sections = set()
    wsl_start = wsl_end = None
    idle = None
    for index, line in enumerate(lines):
        value = line.strip()
        if not value or value.startswith(("#", ";")):
            continue
        header = re.fullmatch(r"\[([^\[\]]+)\]\s*(?:[;#].*)?", value)
        if header:
            name = header[1].strip().casefold()
            if not name or name in sections:
                raise ValueError("Empty or duplicate configuration section")
            sections.add(name)
            if section == "wsl2":
                wsl_end = index
            section = name
            if name == "wsl2":
                wsl_start = index
            continue
        if "[" in value or "]" in value or "=" not in value or section is None:
            raise ValueError("Malformed configuration line")
        key, setting = value.split("=", 1)
        if not key.strip():
            raise ValueError("Empty configuration key")
        if section == "wsl2" and key.strip().casefold() == "vmidletimeout":
            if idle is not None:
                raise ValueError("Duplicate vmIdleTimeout setting")
            setting = re.split(r"[;#]", setting, maxsplit=1)[0].strip()
            if not re.fullmatch(r"-?\d+", setting):
                raise ValueError("Malformed vmIdleTimeout value")
            idle = setting
    if idle is not None:
        return raw, "already_disabled" if int(idle) == -1 else "preserved_explicit_value"
    newline = "\r\n" if "\r\n" in text else "\n"
    if wsl_start is None:
        result = text + (newline if text and not text.endswith("\n") else "")
        result += "[wsl2]" + newline + "vmIdleTimeout=-1" + newline
    else:
        index = len(lines) if wsl_end is None else wsl_end
        prefix = "".join(lines[:index])
        suffix = "".join(lines[index:])
        result = prefix + (newline if prefix and not prefix.endswith("\n") else "")
        result += "vmIdleTimeout=-1" + newline + suffix
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + result.encode("utf-8"), "configured"


def configure(path: Path) -> dict:
    path = safe_path(path)
    existed = path.exists()
    raw = path.read_bytes() if existed else b""
    output, status = transform(raw)
    if output == raw:
        return {"path": str(path), "status": status, "changed": False}
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(output)
            handle.flush()
            os.fsync(handle.fileno())
        if existed:
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        safe_path(path)
        if path.exists() != existed or (existed and path.read_bytes() != raw):
            raise RuntimeError("Configuration changed before publication")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(path), "status": status, "changed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = configure(args.path)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
