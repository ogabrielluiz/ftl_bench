"""ftl_bench M2 closed-loop session over the paused FTL bridge.

The bridge keeps the game paused and applies actions written to
`ftl_agent_action.json`, stamping each resulting observation with
`last_action_seq`. `AgentSession.step()` writes an action, then polls the
observation until the bridge acks that seq while paused.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from ftl_bench.observation import (
    Observation,
    ObservationClient,
    ObservationValidationError,
)

# Default macOS FTL user folder (where the bridge reads/writes its files).
DEFAULT_USER_FOLDER = Path(
    "~/Library/Application Support/FasterThanLight"
).expanduser()


def set_system_power(system_id: int, level: int) -> dict[str, Any]:
    return {"type": "set_system_power", "system_id": int(system_id), "level": int(level)}


def move_crew(crew_id: int, room_id: int, slot_id: int = -1) -> dict[str, Any]:
    return {
        "type": "move_crew",
        "crew_id": int(crew_id),
        "room_id": int(room_id),
        "slot_id": int(slot_id),
    }


class AgentSession:
    """Closed-loop session: reset / observe / step over the paused bridge."""

    def __init__(
        self,
        user_folder: Path | str = DEFAULT_USER_FOLDER,
        poll_interval: float = 0.01,
        step_timeout: float = 5.0,
    ) -> None:
        self.user_folder = Path(user_folder)
        self.obs_path = self.user_folder / "ftl_agent_observation.json"
        self.action_path = self.user_folder / "ftl_agent_action.json"
        self.client = ObservationClient(self.obs_path)
        self.poll_interval = poll_interval
        self.step_timeout = step_timeout
        self.action_seq = 0

    def observe(self) -> Observation:
        """Latest validated observation (no action issued)."""
        return self.client.read_latest()

    def reset(self) -> Observation:
        """Clear any stale action file; return the first paused observation."""
        if self.action_path.exists():
            self.action_path.unlink()
        self.action_seq = 0
        return self._wait_for(lambda obs: obs.paused)

    def step(
        self, actions: Iterable[dict[str, Any]], advance_frames: int = 30
    ) -> Observation:
        """Write an action, advance the world, return the resulting observation."""
        self.action_seq += 1
        payload = {
            "seq": self.action_seq,
            "advance_frames": int(advance_frames),
            "actions": list(actions),
        }
        self._write_action_atomic(payload)
        return self._wait_for(
            lambda obs: obs.last_action_seq == self.action_seq and obs.paused
        )

    # ---- internals ----------------------------------------------------
    def _write_action_atomic(self, payload: dict[str, Any]) -> None:
        tmp = self.action_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self.action_path)  # atomic rename on the same filesystem

    def _wait_for(self, predicate: Callable[[Observation], bool]) -> Observation:
        deadline = time.monotonic() + self.step_timeout
        while time.monotonic() < deadline:
            try:
                obs = self.client.read_latest()
                if predicate(obs):
                    return obs
            except (FileNotFoundError, ObservationValidationError):
                pass
            time.sleep(self.poll_interval)
        raise TimeoutError(
            f"action seq {self.action_seq} not acked within {self.step_timeout}s"
        )
