"""Apply the versioned native bridge patch without replacing local source changes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def apply_patch(source: Path, *, check_only: bool = False) -> str:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "native/manifest.json").read_text())
    patch = root / manifest["patch"]
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise ValueError("native patch does not match its recorded SHA-256")
    source = source.resolve(strict=True)
    top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=source, text=True).strip()
    if Path(top).resolve() != source:
        raise ValueError("--source must be the native Git checkout root")

    def check(*args):
        return subprocess.run(["git", "apply", "--check", *args, str(patch)],
                              cwd=source, capture_output=True, text=True)

    if check("--reverse").returncode == 0:
        return "already applied"
    result = check()
    if result.returncode:
        raise ValueError("native patch conflicts with this checkout; local changes were preserved:\n"
                         + result.stderr)
    if check_only:
        return "ready to apply"
    subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="validate without modifying the checkout")
    args = parser.parse_args()
    try:
        print(apply_patch(args.source, check_only=args.check))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
