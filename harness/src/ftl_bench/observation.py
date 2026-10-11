"""ftl_bench observation client: read + validate the latest observation JSON.

Decoupled from the running game — operates purely on a JSON file path.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)
REQUIRED_FIELDS = ("schema_version", "tick", "seed", "game_started")


@lru_cache(maxsize=1)
def _windows_file_api():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    return create, close


def _open_observation_text(path: Path):
    """Keep a readable snapshot without blocking the native writer's replacement.

    Windows CRT file opens omit FILE_SHARE_DELETE. A short-lived reader can then
    prevent ReplaceFile from atomically publishing the next observation. Opening
    with all three share flags lets an existing handle finish reading its original
    file while subsequent readers see the newly replaced file. The native writer
    must use ReplaceFile for an existing destination; MoveFileEx can still reject
    replacing an open destination even when its readers share deletion.
    """
    if os.name != "nt":
        return path.open("r", encoding="utf-8")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    create, close = _windows_file_api()
    handle = create(str(path), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close(handle)
        raise
    # open_osfhandle transfers ownership to the descriptor. From this point only
    # close the descriptor/stream, never also CloseHandle (which would double-close).
    try:
        return os.fdopen(descriptor, "r", encoding="utf-8")
    except BaseException:
        os.close(descriptor)
        raise


def _read_observation_text(path: Path) -> str:
    if os.name != "nt":
        return path.read_text(encoding="utf-8")
    with _open_observation_text(path) as snapshot:
        return snapshot.read()


class ObservationValidationError(ValueError):
    """Raised when an observation JSON fails schema validation."""


def is_player_crew(member: dict[str, Any]) -> bool:
    """Read ownership independently of location and temporary mind control."""
    owned = member.get("player_owned")
    if isinstance(owned, bool):
        return owned
    owner = member.get("owner_ship_id")
    if owner is not None:
        return owner == 0
    # Older records omit ownership. An owned boarder may be an intruder on
    # the enemy ship; a hostile boarder aboard our ship is not player crew.
    return not member.get("intruder") or member.get("on_enemy_ship") is True


def is_living_player_crew(member: dict[str, Any]) -> bool:
    health = member.get("health_current")
    return (is_player_crew(member) and not member.get("dead") and
            (health is None or isinstance(health, (int, float)) and health > 0))


@dataclass
class Observation:
    schema_version: int
    tick: int
    seed: int
    game_started: bool
    paused: bool = False
    choice_box_open: bool = False
    game_over: bool = False  # the run has ended (crew dead / ship lost / win): GAME OVER screen up
    last_action_seq: Optional[int] = None  # M2: harness ack key (None until first action)
    player_ship: Optional[dict[str, Any]] = None
    enemy_ship: Optional[dict[str, Any]] = None
    map: Optional[dict[str, Any]] = None
    event: Optional[dict[str, Any]] = None  # M3: current event text + choices (when choice box open)
    raw: Optional[dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ObservationValidationError(
                    f"missing required field: {field!r}"
                )
        version = data["schema_version"]
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ObservationValidationError(
                f"unsupported schema_version {version}; supported: {SUPPORTED_SCHEMA_VERSIONS}"
            )
        return cls(
            schema_version=version,
            tick=data["tick"],
            seed=data["seed"],
            game_started=data["game_started"],
            paused=data.get("paused", False),
            choice_box_open=data.get("choice_box_open", False),
            game_over=data.get("game_over", False),
            last_action_seq=data.get("last_action_seq"),
            player_ship=data.get("player_ship"),
            enemy_ship=data.get("enemy_ship"),
            map=data.get("map"),
            event=data.get("event"),
            raw=data,
        )


class ObservationClient:
    """Reads the latest observation snapshot from a JSON file on disk."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read_latest(self) -> Observation:
        # Share-delete reads allow atomic Windows replacement; another process may
        # still briefly cause a sharing violation (PermissionError) or transient drvfs
        # OSError. Just after a restart the file can also be briefly ABSENT — it was deleted and
        # the bridge re-creates it within a tick. FileNotFoundError is an OSError subclass, so the
        # same retry absorbs that window instead of aborting a reset on the first miss. Retry a
        # few times before giving up.
        for attempt in range(9):
            try:
                text = _read_observation_text(self.path)
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ObservationValidationError(f"invalid JSON: {exc}") from exc
                if not isinstance(data, dict):
                    raise ObservationValidationError("observation root must be a JSON object")
                return Observation.from_dict(data)
            except (OSError, ObservationValidationError):
                if attempt == 8:
                    raise
                time.sleep(0.05)
