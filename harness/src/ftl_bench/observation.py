"""ftl_bench observation client: read + validate the latest observation JSON.

Decoupled from the running game — operates purely on a JSON file path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1
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
    player_ship: Optional[dict[str, Any]] = None
    enemy_ship: Optional[dict[str, Any]] = None
    map: Optional[dict[str, Any]] = None
    raw: Optional[dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ObservationValidationError(
                    f"missing required field: {field!r}"
                )
        version = data["schema_version"]
        if version != SCHEMA_VERSION:
            raise ObservationValidationError(
                f"schema_version mismatch: expected {SCHEMA_VERSION}, got {version}"
            )
        return cls(
            schema_version=version,
            tick=data["tick"],
            seed=data["seed"],
            game_started=data["game_started"],
            paused=data.get("paused", False),
            choice_box_open=data.get("choice_box_open", False),
            player_ship=data.get("player_ship"),
            enemy_ship=data.get("enemy_ship"),
            map=data.get("map"),
            raw=data,
        )


class ObservationClient:
    """Reads the latest observation snapshot from a JSON file on disk."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read_latest(self) -> Observation:
        if not self.path.exists():
            raise FileNotFoundError(f"observation file not found: {self.path}")
        text = self.path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ObservationValidationError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ObservationValidationError("observation root must be a JSON object")
        return Observation.from_dict(data)
