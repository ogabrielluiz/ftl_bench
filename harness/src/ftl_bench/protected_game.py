"""Protect the current Windows save files around one locally launched benchmark."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from os import fsync
from pathlib import Path
import shutil
import stat
import subprocess
import time
from uuid import uuid4

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


PENDING_LAUNCH = "ftl_bench_pending_launch.json"


def _safe_path(path: Path) -> Path:
    """Reject links/junctions before resolving a recovery or ownership path."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Unsafe linked protected-game path")
    return path.resolve()


def _write_json(path: Path, value: dict, *, exclusive: bool = False) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        fsync(stream.fileno())


class ProtectedGame:
    def __init__(self, save: Path, backup: Path, bridge: Path, game_dir: Path | None = None):
        self.save, self.backup = _safe_path(save), _safe_path(backup)
        self.bridge = Path(bridge).resolve()
        self.game = game_directory(game_dir)
        self.manifest: dict = {}
        self.launched_at: datetime | None = None
        self._guard: dict | None = None
        self._recovery: dict | None = None

    @property
    def pending_launch(self) -> Path:
        return self.save / PENDING_LAUNCH

    def _check_guard(self) -> None:
        path = self.pending_launch
        if not path.exists() and not path.is_symlink():
            if self._guard is not None:
                raise RuntimeError("Protected launch ownership marker is missing")
            return
        _safe_path(path)
        if self._guard is None:
            raise RuntimeError("Unresolved or active protected launch; inspect " + str(path))
        if json.loads(path.read_text(encoding="utf-8")) != self._guard:
            raise RuntimeError("Protected launch ownership marker changed")

    def _claim_guard(self) -> None:
        self._check_guard()
        if self._guard is not None:
            return
        _safe_path(self.save)
        _safe_path(self.backup)
        guard = {"contract": "protected-launch-v1", "ownership_id": uuid4().hex,
                 "save_directory": str(self.save), "backup_directory": str(self.backup),
                 "game_directory": str(self.game) if self.game else None,
                 "created_at": datetime.now(timezone.utc).isoformat(),
                 "state": "backup_ready" if self.manifest else "prepared",
                 "manifest_sha256": _hash(self.backup / "manifest.json") if self.manifest else None}
        _write_json(self.pending_launch, guard, exclusive=True)
        self._guard = guard

    def _update_guard(self, **changes) -> None:
        self._check_guard()
        updated = {**self._guard, **changes}
        temporary = self.save / (PENDING_LAUNCH + "." + self._guard["ownership_id"] + ".tmp")
        _write_json(temporary, updated, exclusive=True)
        self._check_guard()
        temporary.replace(self.pending_launch)
        self._guard = updated

    def _release_guard(self) -> None:
        self._check_guard()
        if self._guard is not None:
            self.pending_launch.unlink()
            self._guard = None

    def backup_saves(self) -> None:
        self._check_guard()
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
        original_bridge = self.save / "ftl_bench_dev.lua"
        _safe_path(original_bridge)
        if original_bridge.exists() and not original_bridge.is_file():
            raise RuntimeError("Unsafe original bridge path")
        bridge_digest = None
        if original_bridge.exists():
            shutil.copy2(original_bridge, self.backup / "ftl_bench_dev.lua")
            bridge_digest = _hash(original_bridge)
            if _hash(self.backup / "ftl_bench_dev.lua") != bridge_digest:
                raise RuntimeError("Original bridge backup verification failed")
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(),
                    "save_directory": str(self.save.resolve()), "files": files,
                    "bridge_sha256": bridge_digest, "deployed_bridge_sha256": _hash(self.bridge)}
        _write_json(self.backup / "manifest.json", manifest, exclusive=True)
        self.manifest = manifest
        if self._guard is not None:
            self._update_guard(state="backup_ready", manifest_sha256=_hash(self.backup / "manifest.json"))

    def launch(self, timeout: float = 180) -> None:
        if self.game is None or not (self.game / "FTLGame.exe").is_file():
            raise RuntimeError("A patched Windows FTL installation is required")
        if not self.manifest:
            raise RuntimeError("Verified save backups are required before launching")
        self._claim_guard()
        if self._guard["state"] != "backup_ready":
            raise RuntimeError("This protected launch was already dispatched; do not retry the pending request")
        # No recursive cleanup; these are known transient bridge files only.
        for name in ("ftl_agent_observation.json", "ftl_agent_action.json", "hs_crash.flag"):
            (self.save / name).unlink(missing_ok=True)
        target = self.save / "ftl_bench_dev.lua"
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeError("Unsafe existing bridge path")
        shutil.copyfile(self.bridge, target)
        (self.save / "ftl_bench_reload").write_text("", encoding="utf-8")
        steam = self.game.parents[2] / "steam.exe"
        if not steam.is_file():
            raise RuntimeError("Steam launcher was not found beside the configured game library")
        self.launched_at = datetime.now(timezone.utc)
        self._update_guard(state="launch_pending", launched_at=self.launched_at.isoformat())
        launcher = subprocess.Popen([str(steam), "-applaunch", "212680"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + timeout
        client = ObservationClient(self.save / "ftl_agent_observation.json")
        last_observation = None
        last_read_error = None
        while time.monotonic() < deadline:
            try:
                obs = client.read_latest()
                last_observation = {"game_started": obs.game_started, "paused": obs.paused}
                # A healthy main menu has no simulation to pause and normally
                # reports paused=false. Episode reset happens after launch.
                if obs.game_started is False or obs.paused is True:
                    processes = _processes()
                    if len(processes) == 1 and self._owns_process(processes[0]):
                        self._update_guard(state="ready_owned", process=processes[0])
                        return
            except (OSError, ObservationValidationError) as error:
                # Exception types suffice here; observation content or parser
                # messages may contain untrusted or sensitive bytes.
                last_read_error = type(error).__name__
            time.sleep(.25)
        _write_json(self.backup / "launch-timeout.json", {
            "contract": "protected-launch-timeout-v1", "checked_at": datetime.now(timezone.utc).isoformat(),
            "ownership_id": self._guard["ownership_id"], "state": "launch_pending",
            "launcher_pid": getattr(launcher, "pid", None),
            "last_observation": last_observation, "last_read_error_type": last_read_error,
            "queue_cancellation_verified": False}, exclusive=True)
        raise TimeoutError("FTL did not publish a main-menu or paused-game bridge observation after launch")

    def _owns_process(self, process: dict) -> bool:
        expected = self.game / "FTLGame.exe" if self.game else None
        try:
            started = datetime.fromisoformat(process["started"])
            if self._guard and self._guard["state"] == "ready_owned":
                observed = self._guard["process"]
                if any(process.get(key) != observed.get(key) for key in ("id", "path", "started")):
                    return False
            return (expected is not None and bool(process.get("path"))
                    and Path(process["path"]).resolve() == expected.resolve()
                    and self.launched_at is not None and started >= self.launched_at)
        except (AttributeError, KeyError, TypeError, ValueError):
            return False

    def stop(self) -> None:
        self._check_guard()
        processes = _processes()
        for process in processes:
            expected = self.game / "FTLGame.exe" if self.game else None
            if not self._owns_process(process):
                raise RuntimeError("Unowned FTL process is running; saves retained in backup without overwriting live files")
            _powershell("$ErrorActionPreference='Stop'; $p=Get-Process -Id ([int]$env:FTLBENCH_PID) -ErrorAction SilentlyContinue; if ($p) { if ($p.Path -ne $env:FTLBENCH_EXE -or $p.StartTime.ToUniversalTime().ToString('o') -ne $env:FTLBENCH_STARTED) { throw 'Process identity changed' }; Stop-Process -Id $p.Id -Force; $p.WaitForExit() }",
                        FTLBENCH_PID=str(process["id"]), FTLBENCH_EXE=str(expected),
                        FTLBENCH_STARTED=process["started"])
        if _processes():
            raise RuntimeError("FTL is still running; refusing to overwrite live saves")

    def restore_saves(self) -> None:
        self._check_guard()
        if self._guard and self._guard["state"] == "launch_pending" and self._recovery is None:
            raise RuntimeError("Unresolved Steam launch; cancel the queued request, close FTL, then use "
                               "ftlbench recover-protected with ownership ID " + self._guard["ownership_id"])
        if not self.manifest:
            return
        if _processes():
            raise RuntimeError("FTL is still running; refusing to overwrite live saves")
        bridge_backup = self.backup / "ftl_bench_dev.lua"
        bridge_target = self.save / "ftl_bench_dev.lua"
        _safe_path(self.backup)
        _safe_path(self.save)
        _safe_path(bridge_target)
        if self._guard and _hash(self.backup / "manifest.json") != self._guard["manifest_sha256"]:
            raise RuntimeError("Protected save manifest changed")
        if self.manifest.get("bridge_sha256") is not None:
            _safe_path(bridge_backup)
            if not bridge_backup.is_file() or _hash(bridge_backup) != self.manifest["bridge_sha256"]:
                raise RuntimeError("Original bridge backup changed")
        elif "bridge_sha256" in self.manifest and (bridge_backup.exists() or bridge_backup.is_symlink()):
            raise RuntimeError("Unexpected original bridge backup")
        if (self.manifest.get("bridge_sha256") is None and bridge_target.exists()
                and (not bridge_target.is_file()
                     or _hash(bridge_target) != self.manifest.get("deployed_bridge_sha256"))):
            raise RuntimeError("Unexpected deployed bridge; refusing to remove unowned content")
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
        elif "bridge_sha256" in self.manifest:
            bridge_target.unlink(missing_ok=True)
        self._verify_restored()
        receipt = {"restored_at": datetime.now(timezone.utc).isoformat(),
                   "verified": all(restored.values()), "files": restored,
                   "generated_saves_preserved": {path.name: digest for path, digest in generated_saves}}
        if not receipt["verified"]:
            raise RuntimeError("Original-save restoration verification failed")
        if self._recovery is not None:
            receipt["recovery"] = self._recovery
        name = "recovery-restoration.json" if self._recovery is not None else "restoration.json"
        _write_json(self.backup / name, receipt, exclusive=True)
        self._release_guard()

    def _verify_restored(self) -> None:
        self._check_guard()
        _safe_path(self.save)
        target = _safe_path(self.save / "ftl_bench_dev.lua")
        expected = self.manifest.get("bridge_sha256")
        if "bridge_sha256" in self.manifest and (
                (target.exists() and not target.is_file())
                or (_hash(target) if target.is_file() else None) != expected):
            raise RuntimeError("Original bridge restoration verification failed")
        live = {p.name: _hash(_safe_path(p)) for p in self.save.glob("*.sav")}
        if live != self.manifest["files"]:
            raise RuntimeError("Original save inventory restoration verification failed")
        if _processes():
            raise RuntimeError("FTL appeared during restoration; launch ownership retained")

    @contextmanager
    def protected(self):
        if os.name != "nt":
            raise RuntimeError("Automatic protected launch currently supports Windows only")
        self._check_guard()
        if _processes():
            raise RuntimeError("Close FTL before a protected benchmark run")
        self._claim_guard()
        try:
            self.backup_saves()
            yield self
        finally:
            if self.manifest:
                self.stop()
                self.restore_saves()
            else:
                # Backup failed before any launch or live-file mutation.
                self._release_guard()


def recover_protected(backup: Path, *, ownership_id: str,
                      confirm_pending_launch_cancelled: bool,
                      save_directory: Path | None = None) -> dict:
    """Recover only after the operator cancels Steam's queued launch and closes FTL.

    The acknowledgement is a human trust input, not evidence from an empty
    process list. Recovery never rewrites the failed trial's cleanup receipt.
    """
    if confirm_pending_launch_cancelled is not True:
        raise ValueError("Explicit pending-launch cancellation confirmation is required")
    backup = _safe_path(backup)
    manifest_path = _safe_path(backup / "manifest.json")
    guard = None
    if save_directory is not None:
        save = _safe_path(save_directory)
        marker = _safe_path(save / PENDING_LAUNCH)
        guard = json.loads(marker.read_text(encoding="utf-8"))
    predeployment = (isinstance(guard, dict) and guard.get("state") == "prepared"
                     and guard.get("manifest_sha256") is None)
    # A crash can interrupt the initial manifest write. A valid prepared guard
    # proves no deployment was permitted; preserve that unbound partial file.
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() and not predeployment else None)
    if manifest is not None and (not isinstance(manifest, dict)
            or not isinstance(manifest.get("save_directory"), str)
            or not Path(manifest["save_directory"]).is_absolute()
            or not isinstance(manifest.get("files"), dict)):
        raise ValueError("Invalid protected save manifest")
    if save_directory is None and manifest is None:
        raise ValueError("No complete manifest; provide the explicit --save-dir from the ownership marker")
    save = _safe_path(save_directory if save_directory is not None else Path(manifest["save_directory"]))
    marker = _safe_path(save / PENDING_LAUNCH)
    if guard is None:
        guard = json.loads(marker.read_text(encoding="utf-8"))
    if (not isinstance(guard, dict) or guard.get("contract") != "protected-launch-v1" or not ownership_id
            or guard.get("ownership_id") != ownership_id
            or guard.get("save_directory") != str(save)
            or guard.get("backup_directory") != str(backup)
            or (guard.get("game_directory") is not None
                and (not isinstance(guard["game_directory"], str)
                     or not Path(guard["game_directory"]).is_absolute()))
            or guard.get("state") not in {"prepared", "backup_ready", "launch_pending", "ready_owned"}
            or backup == save or backup.is_relative_to(save)):
        raise RuntimeError("Pending launch marker does not match the requested ownership and backup")
    if guard["state"] != "prepared" and (manifest is None
            or manifest["save_directory"] != str(save)
            or guard.get("manifest_sha256") != _hash(manifest_path)
            or "bridge_sha256" not in manifest):
        raise RuntimeError("Protected save manifest does not match the pending launch")
    if guard["state"] == "prepared" and guard.get("manifest_sha256") is not None:
        raise RuntimeError("Unexpected manifest binding before backup completion")
    if _processes():
        raise RuntimeError("Close FTL before protected recovery; pending request cancellation is also required")
    game = ProtectedGame(save, backup, save / "ftl_bench_dev.lua",
                         _safe_path(Path(guard["game_directory"])) if guard.get("game_directory") else None)
    game.manifest, game._guard = manifest, guard
    game._recovery = {"contract": "protected-launch-recovery-v1", "ownership_id": ownership_id,
                      "save_directory": str(save), "backup_directory": str(backup),
                      "manifest_sha256": guard.get("manifest_sha256"),
                      "operator_confirmed_pending_launch_cancelled": True,
                      "queue_cancellation_verified_by_harness": False,
                      "prior_launch_state": guard["state"]}
    receipt_path = _safe_path(backup / "recovery-restoration.json")
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or receipt.get("recovery") != game._recovery:
            raise RuntimeError("Existing recovery receipt does not match this pending launch")
        if guard["state"] == "prepared":
            if receipt.get("operation") != "release_before_deployment" or receipt.get("no_deployment") is not True:
                raise RuntimeError("Invalid predeployment recovery receipt")
        else:
            if receipt.get("verified") is not True:
                raise RuntimeError("Existing recovery did not verify restoration")
            game._verify_restored()
        game._release_guard()
        return receipt
    if guard["state"] == "prepared":
        # No live-file changes or Steam handoff are permitted before backup_ready.
        backup.mkdir(parents=True, exist_ok=True)
        receipt = {"operation": "release_before_deployment", "save_restoration_required": False,
                   "no_deployment": True,
                   "completed_at": datetime.now(timezone.utc).isoformat(), "recovery": game._recovery}
        _write_json(receipt_path, receipt, exclusive=True)
        game._release_guard()
        return receipt
    game.restore_saves()
    return json.loads(receipt_path.read_text(encoding="utf-8"))
