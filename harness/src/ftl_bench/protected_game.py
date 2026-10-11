"""Protect the current Windows save files around one locally launched benchmark."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .installation import game_directory
from .observation import ObservationClient, ObservationValidationError


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _powershell(script: str, **variables) -> str:
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, **variables},
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("FTL process inspection or shutdown failed: " + result.stderr.strip())
    return result.stdout.strip()


def _processes() -> list[dict]:
    output = _powershell("$ErrorActionPreference='Stop'; @((Get-Process FTLGame -ErrorAction SilentlyContinue) | ForEach-Object { @{id=$_.Id;path=$_.Path;started=$_.StartTime.ToUniversalTime().ToString('o')} }) | ConvertTo-Json -Compress")
    data = json.loads(output) if output else []
    return data if isinstance(data, list) else [data]


class ProtectedGame:
    def __init__(self, save: Path, backup: Path, bridge: Path, game_dir: Path | None = None):
        self.save, self.backup, self.bridge = Path(save).resolve(), Path(backup).resolve(), Path(bridge).resolve()
        self.game = game_directory(game_dir)
        self.manifest: dict = {}
        self.launched_at: datetime | None = None

    def backup_saves(self) -> None:
        if not self.save.is_dir():
            raise ValueError("The FTL save folder must exist before protection begins")
        if self.backup == self.save or self.backup.is_relative_to(self.save):
            raise ValueError("Save backups must be outside the live save folder")
        self.backup.mkdir(parents=True, exist_ok=False)
        files = {}
        for path in self.save.glob("*.sav"):
            if path.is_symlink() or not path.is_file():
                raise ValueError("Cannot protect a linked or non-file FTL save")
            shutil.copy2(path, self.backup / path.name)
            files[path.name] = _hash(path)
            if _hash(self.backup / path.name) != files[path.name]:
                raise RuntimeError("Save backup verification failed")
        self.manifest = {"created_at": datetime.now(timezone.utc).isoformat(),
                         "save_directory": str(self.save.resolve()), "files": files}
        (self.backup / "manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")

    def launch(self, timeout: float = 180) -> None:
        if self.game is None or not (self.game / "FTLGame.exe").is_file():
            raise RuntimeError("A patched Windows FTL installation is required")
        # No recursive cleanup; these are known transient bridge files only.
        for name in ("ftl_agent_observation.json", "ftl_agent_action.json", "hs_crash.flag"):
            (self.save / name).unlink(missing_ok=True)
        target = self.save / "ftl_bench_dev.lua"
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeError("Unsafe existing bridge path")
        if target.exists():
            shutil.copy2(target, self.backup / "ftl_bench_dev.lua")
        shutil.copyfile(self.bridge, target)
        (self.save / "ftl_bench_reload").write_text("", encoding="utf-8")
        steam = self.game.parents[2] / "steam.exe"
        if not steam.is_file():
            raise RuntimeError("Steam launcher was not found beside the configured game library")
        self.launched_at = datetime.now(timezone.utc)
        subprocess.Popen([str(steam), "-applaunch", "212680"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + timeout
        client = ObservationClient(self.save / "ftl_agent_observation.json")
        while time.monotonic() < deadline:
            try:
                obs = client.read_latest()
                # A healthy main menu has no simulation to pause and normally
                # reports paused=false. Episode reset happens after launch.
                if obs.game_started is False or obs.paused is True:
                    return
            except (OSError, ObservationValidationError):
                pass
            time.sleep(.25)
        raise TimeoutError("FTL did not publish a main-menu or paused-game bridge observation after launch")

    def stop(self) -> None:
        processes = _processes()
        for process in processes:
            started = datetime.fromisoformat(process["started"])
            expected = self.game / "FTLGame.exe" if self.game else None
            if (expected is None or not process.get("path")
                    or Path(process["path"]).resolve() != expected.resolve()
                    or self.launched_at is None or started < self.launched_at):
                raise RuntimeError("Unowned FTL process is running; saves retained in backup without overwriting live files")
            _powershell("$ErrorActionPreference='Stop'; $p=Get-Process -Id ([int]$env:FTLBENCH_PID) -ErrorAction SilentlyContinue; if ($p) { if ($p.Path -ne $env:FTLBENCH_EXE -or $p.StartTime.ToUniversalTime().ToString('o') -ne $env:FTLBENCH_STARTED) { throw 'Process identity changed' }; Stop-Process -Id $p.Id -Force; $p.WaitForExit() }",
                        FTLBENCH_PID=str(process["id"]), FTLBENCH_EXE=str(expected),
                        FTLBENCH_STARTED=process["started"])
        if _processes():
            raise RuntimeError("FTL is still running; refusing to overwrite live saves")

    def restore_saves(self) -> None:
        if not self.manifest:
            return
        if _processes():
            raise RuntimeError("FTL is still running; refusing to overwrite live saves")
        bridge_backup = self.backup / "ftl_bench_dev.lua"
        bridge_target = self.save / "ftl_bench_dev.lua"
        if bridge_backup.exists() or bridge_backup.is_symlink():
            if (bridge_backup.is_symlink() or not bridge_backup.is_file()
                    or bridge_target.is_symlink()
                    or (bridge_target.exists() and not bridge_target.is_file())):
                raise RuntimeError("Unsafe bridge restoration path")
        # Preflight every source and destination before changing any original. A
        # failed restore stays recoverable; do not follow a newly introduced link.
        for name, digest in self.manifest["files"].items():
            if (not isinstance(name, str) or Path(name).name != name
                    or Path(name).suffix.lower() != ".sav"):
                raise RuntimeError("Unsafe save manifest filename")
            source, target = self.backup / name, self.save / name
            if (source.is_symlink() or not source.is_file() or target.is_symlink()
                    or (target.exists() and not target.is_file())):
                raise RuntimeError("Unsafe original save restoration path")
            if _hash(self.backup / name) != digest:
                raise RuntimeError("Save backup changed; refusing unverified restoration")
        generated_saves = []
        for path in self.save.glob("*.sav"):
            if path.name not in self.manifest["files"]:
                if (path.is_symlink() or not path.is_file()
                        or path.resolve().parent != self.save.resolve()):
                    raise RuntimeError("Unsafe generated save path")
                generated_saves.append((path, _hash(path)))
        generated = self.backup / "benchmark-generated"
        if generated_saves:
            if generated.is_symlink():
                raise RuntimeError("Unsafe generated save backup directory")
            generated.mkdir(exist_ok=True)
        for path, digest in generated_saves:
            archived = generated / path.name
            if archived.exists() or archived.is_symlink():
                if archived.is_symlink() or not archived.is_file() or _hash(archived) != digest:
                    raise RuntimeError("Generated-save archive already contains different data")
            else:
                shutil.copy2(path, archived)
            if _hash(archived) != digest:
                raise RuntimeError("Generated save backup verification failed")
        # All newly generated saves now have verified copies. They must not remain
        # in the live folder when restoring a profile that originally lacked them.
        for path, digest in generated_saves:
            if path.is_symlink() or _hash(path) != digest:
                raise RuntimeError("Generated save changed during restoration")
            path.unlink()
        restored = {}
        for name, digest in self.manifest["files"].items():
            shutil.copy2(self.backup / name, self.save / name)
            restored[name] = _hash(self.save / name) == digest
        if bridge_backup.exists():
            shutil.copy2(bridge_backup, bridge_target)
        receipt = {"restored_at": datetime.now(timezone.utc).isoformat(),
                   "verified": all(restored.values()), "files": restored,
                   "generated_saves_preserved": {path.name: digest for path, digest in generated_saves}}
        (self.backup / "restoration.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        if not receipt["verified"]:
            raise RuntimeError("Original-save restoration verification failed")

    @contextmanager
    def protected(self):
        if os.name != "nt":
            raise RuntimeError("Automatic protected launch currently supports Windows only")
        if _processes():
            raise RuntimeError("Close FTL before a protected benchmark run")
        self.backup_saves()
        try:
            yield self
        finally:
            self.stop()
            self.restore_saves()
