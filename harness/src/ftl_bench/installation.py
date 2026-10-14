"""Backed-up local installation and fingerprints of the actual benchmark runtime."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from ftl_bench.session import ftl_process_alive, ftl_user_folder


def game_directory(game_dir=None) -> Path | None:
    configured = game_dir or os.environ.get("FTL_GAME_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam/steamapps/common/FTL Faster Than Light"
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_fingerprint(root: Path, prompt_version=None) -> dict:
    """Record actual installed files. Missing provenance is explicit, never guessed."""
    game = game_directory()
    candidates = {"bridge_lua": ftl_user_folder() / "ftl_bench_dev.lua"}
    if game is not None:
        candidates["native_dll"] = game / "Hyperspace.dll"
    if prompt_version:
        candidates["prompt"] = root / "prompts" / f"ftl_agent_{prompt_version}.md"
    result = {}
    for name, path in candidates.items():
        try:
            result[name] = {"path": str(path.resolve()), "sha256": sha256(path)}
        except OSError:
            result[name] = {"path": str(path.resolve()), "sha256": None}
    if game is not None:
        try:
            provenance = json.loads((game / "ftlbench-native.json").read_text(encoding="utf-8"))
            if not isinstance(provenance, dict):
                raise ValueError("invalid provenance")
            result["native_build"] = {name: provenance.get(name) for name in (
                "source_commit", "source_diff_sha256", "patch_sha256", "native_protocol", "visual_io_version", "visual_clock_version",
                "fixed_step_numerator", "fixed_step_denominator",
                "fresh_start_seed", "fresh_seed_contract_version", "fresh_seed_contract",
                "platform", "game_version", "dll_sha256", "toolchain")}
            result["native_build"]["matches_installed_dll"] = (
                bool(result["native_dll"]["sha256"])
                and provenance.get("dll_sha256") == result["native_dll"]["sha256"])
        except (OSError, ValueError):
            result["native_build"] = None
    return result


def install_native(dll, manifest, game_dir=None) -> dict:
    """Install a verified DLL into an existing patched Windows game; retain replaced files."""
    source, provenance_path = Path(dll).resolve(), Path(manifest).resolve()
    game = game_directory(game_dir)
    if game is None or not game.is_dir():
        raise ValueError("Specify an existing patched FTL folder with --game-dir or FTL_GAME_DIR.")
    # Same durable marker as protected_game; avoid importing its lifecycle here.
    pending = ftl_user_folder() / "ftl_bench_pending_launch.json"
    if pending.exists() or pending.is_symlink():
        raise ValueError("Resolve the pending protected FTL launch before native installation.")
    if ftl_process_alive():
        raise ValueError("Close FTL before replacing its native DLL.")
    for filename in ("FTLGame.exe", "xinput1_4.dll", "lua-5.3.dll"):
        if not (game / filename).is_file():
            raise ValueError(f"Missing {filename}; complete the Hyperspace setup first.")
    payloads = {"Hyperspace.dll": source.read_bytes(), "ftlbench-native.json": provenance_path.read_bytes()}
    provenance = json.loads(payloads["ftlbench-native.json"].decode("utf-8"))
    if not isinstance(provenance, dict):
        raise ValueError("The build manifest must be a JSON object.")
    if provenance.get("platform") != "windows-x86" or provenance.get("game_version") != "1.6.9":
        raise ValueError("This installer requires the Windows x86 FTL 1.6.9 build.")
    protocol = provenance.get("native_protocol")
    if type(protocol) is not int or protocol < 5:
        raise ValueError("The DLL must implement benchmark protocol 5 or later.")
    digest = hashlib.sha256(payloads["Hyperspace.dll"]).hexdigest()
    if digest != provenance.get("dll_sha256") or len(payloads["Hyperspace.dll"]) != provenance.get("dll_size"):
        raise ValueError("DLL hash or size does not match the build manifest; no files were changed.")
    if source == game / "Hyperspace.dll":
        raise ValueError("Use the built DLL as --dll, not the installed destination.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = game / "ftlbench-backups" / f"{stamp}-{uuid4().hex[:8]}"
    backup.mkdir(parents=True)
    destinations = {"Hyperspace.dll": source, "ftlbench-native.json": provenance_path}
    originals = {}
    for filename in destinations:
        dest = game / filename
        if dest.is_symlink() or (dest.exists() and not dest.is_file()):
            raise ValueError("Unsafe native installation destination: " + filename)
        originals[filename] = dest.read_bytes() if dest.exists() else None
        if originals[filename] is not None:
            shutil.copy2(dest, backup / filename)
            if (backup / filename).read_bytes() != originals[filename]:
                raise RuntimeError("Native installation backup verification failed: " + filename)
    replaced = []
    try:
        for filename, incoming in destinations.items():
            temporary = game / f".{filename}.{uuid4().hex}.tmp"
            try:
                shutil.copyfile(incoming, temporary)
                if temporary.read_bytes() != payloads[filename]:
                    raise RuntimeError("Native installation staged payload differs from validated bytes: " + filename)
                temporary.replace(game / filename)
                replaced.append(filename)
                if (game / filename).read_bytes() != payloads[filename]:
                    raise RuntimeError("Native installation final payload verification failed: " + filename)
            finally:
                temporary.unlink(missing_ok=True)
        if any((game / name).read_bytes() != data for name, data in payloads.items()):
            raise RuntimeError("Native installation payload pair changed before completion")
    except BaseException as failure:
        rollback_errors = []
        for filename in replaced:
            try:
                if originals[filename] is not None:
                    if (backup / filename).read_bytes() != originals[filename]:
                        raise RuntimeError("Original backup bytes changed")
                    shutil.copy2(backup / filename, game / filename)
                else:
                    (game / filename).unlink(missing_ok=True)
            except BaseException as error:
                rollback_errors.append(filename + ": " + str(error))
        for filename, original in originals.items():
            try:
                dest = game / filename
                if (dest.is_symlink() or (original is None and dest.exists())
                        or (original is not None and dest.read_bytes() != original)):
                    raise RuntimeError("Original destination bytes/inventory not restored")
            except BaseException as error:
                rollback_errors.append(filename + ": " + str(error))
        if rollback_errors:
            raise RuntimeError("Native installation failed and rollback failed; retained backup at "
                               + str(backup) + ": " + "; ".join(rollback_errors)) from failure
        raise
    return {"game_dir": str(game), "backup": str(backup), "dll_sha256": digest,
            "native_protocol": provenance["native_protocol"]}
