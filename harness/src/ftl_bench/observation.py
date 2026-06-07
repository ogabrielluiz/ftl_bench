"""ftl_bench observation client: read + validate the latest observation JSON.

Decoupled from the running game — operates purely on a JSON file path.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)
REQUIRED_FIELDS = ("schema_version", "tick", "seed", "game_started")


class ObservationValidationError(ValueError):
    """Raised when an observation JSON fails schema validation."""


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
        # On Windows the bridge replaces this file atomically (ReplaceFileA), so a concurrent
        # read can briefly hit a sharing violation (PermissionError) or other transient drvfs
        # OSError. Just after a restart the file can also be briefly ABSENT — it was deleted and
        # the bridge re-creates it within a tick. FileNotFoundError is an OSError subclass, so the
        # same retry absorbs that window instead of aborting a reset on the first miss. Retry a
        # few times before giving up.
        text = ""
        for attempt in range(9):
            try:
                text = self.path.read_text(encoding="utf-8")
                break
            except (PermissionError, OSError):
                if attempt == 8:
                    raise
                time.sleep(0.05)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ObservationValidationError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ObservationValidationError("observation root must be a JSON object")
        return Observation.from_dict(data)
