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


# --- M3 actions ---

def jump(beacon_index: int) -> dict[str, Any]:
    return {"type": "jump", "beacon_index": int(beacon_index)}


def choose_event(choice_index: int) -> dict[str, Any]:
    return {"type": "choose_event", "choice_index": int(choice_index)}


def start_game(mode: str = "continue", seed: int | None = None) -> dict[str, Any]:
    """mode: 'continue' (resume) or 'new' (fresh run). seed: pin the run seed
    (reproducible map/events) for mode='new'; None = random."""
    act: dict[str, Any] = {"type": "start_game", "mode": str(mode)}
    if seed is not None:
        act["seed"] = int(seed)
    return act


def fire_weapon(weapon_slot: int, target_room_id: int, target_ship_id: int = 1) -> dict[str, Any]:
    return {
        "type": "fire_weapon",
        "weapon_slot": int(weapon_slot),
        "target_room_id": int(target_room_id),
        "target_ship_id": int(target_ship_id),  # 1 = enemy (default)
    }


class AgentSession:
    """Closed-loop session: reset / observe / step over the paused bridge."""

    def __init__(
        self,
        user_folder: Path | str = DEFAULT_USER_FOLDER,
        poll_interval: float = 0.01,
        step_timeout: float = 5.0,
        recorder=None,
    ) -> None:
        self.user_folder = Path(user_folder)
        self.obs_path = self.user_folder / "ftl_agent_observation.json"
        self.action_path = self.user_folder / "ftl_agent_action.json"
        self.client = ObservationClient(self.obs_path)
        self.poll_interval = poll_interval
        self.step_timeout = step_timeout
        self.action_seq = 0
        self.recorder = recorder  # optional TrajectoryRecorder

    def observe(self) -> Observation:
        """Latest validated observation (no action issued)."""
        return self.client.read_latest()

    def reset(self) -> Observation:
        """Clear any stale action file; return the first paused observation.

        Syncs `action_seq` to the bridge's persisted `last_action_seq` so a fresh
        session never sends a seq the bridge's dedup would ignore (the game-side
        seq survives reloads/restarts; the harness counter does not).
        """
        if self.action_path.exists():
            self.action_path.unlink()
        obs = self._wait_for(lambda o: o.paused)
        self.action_seq = obs.last_action_seq or 0
        return obs

    def _sync_seq(self) -> None:
        """Bump action_seq past the game's persisted last_action_seq so the bridge's
        dedup never ignores us (the game-side seq survives reloads/restarts; a fresh
        session — e.g. a new MCP server — starts at 0)."""
        try:
            cur = self.client.read_latest()
            self.action_seq = max(self.action_seq, cur.last_action_seq or 0)
        except (FileNotFoundError, ObservationValidationError):
            pass

    def step(
        self, actions: Iterable[dict[str, Any]], advance_frames: int = 30
    ) -> Observation:
        """Write an action, advance the world, return the resulting observation."""
        self._sync_seq()
        self.action_seq += 1
        payload = {
            "seq": self.action_seq,
            "advance_frames": int(advance_frames),
            "actions": list(actions),
        }
        self._write_action_atomic(payload)
        # The step can't ack until the world has advanced `advance_frames` and
        # re-paused, so the timeout must exceed the frame budget's wall-clock
        # (~60 fps) plus warp/animation slack and poll margin.
        timeout = max(self.step_timeout, advance_frames / 45.0 + 3.0)
        obs = self._wait_for(
            lambda o: o.last_action_seq == self.action_seq and o.paused,
            timeout=timeout,
        )
        if self.recorder is not None:
            self.recorder.record("step", payload["actions"], obs)
        return obs

    # ---- autonomy: start a game from the menu without a human click ----
    def start_game(
        self, mode: str = "continue", seed: int | None = None, timeout: float = 12.0
    ) -> Observation:
        """Continue/new-game from the menu; waits until the run is loaded.
        `seed` (mode='new') pins the run for reproducibility."""
        if mode == "new":
            timeout = max(timeout, 30.0)  # New Game -> CONFIRM -> hangar Start is multi-step
        self._sync_seq()
        self.action_seq += 1
        acts = [start_game(mode, seed)]
        self._write_action_atomic(
            {"seq": self.action_seq, "advance_frames": 0, "actions": acts}
        )
        obs = self._wait_for(lambda o: o.game_started, timeout=timeout)
        if self.recorder is not None:
            self.recorder.record("start_game", acts, obs)
        return obs

    def reset_episode(self, seed: int | None = None, timeout: float = 60.0) -> Observation:
        """Start a fresh seeded episode, even from in-game: abandon the current run
        back to the main menu, then launch a new game. (start_game only works from
        the menu; this works anywhere.)"""
        if not self.observe().game_started:
            return self.start_game("new", seed=seed)
        self._sync_seq()
        self.action_seq += 1
        act: dict[str, Any] = {"type": "reset_episode"}
        if seed is not None:
            act["seed"] = int(seed)
        self._write_action_atomic(
            {"seq": self.action_seq, "advance_frames": 0, "actions": [act]})
        deadline = time.monotonic() + timeout
        self._wait_for(lambda o: not o.game_started,           # reached the menu
                       timeout=max(2.0, deadline - time.monotonic()))
        obs = self._wait_for(lambda o: o.game_started,         # new run loaded
                             timeout=max(2.0, deadline - time.monotonic()))
        if self.recorder is not None:
            self.recorder.record("reset_episode", [act], obs)
        return obs

    # ---- M3 convenience helpers (sensible per-action frame budgets) ----
    def jump(self, beacon_index: int, advance_frames: int = 240) -> Observation:
        """Jump and let the warp/arrival sequence settle before re-pausing."""
        return self.step([jump(beacon_index)], advance_frames=advance_frames)

    def choose_event(self, choice_index: int, advance_frames: int = 60) -> Observation:
        return self.step([choose_event(choice_index)], advance_frames=advance_frames)

    def fire_weapon(self, weapon_slot: int, target_room_id: int,
                    target_ship_id: int = 1, advance_frames: int = 60) -> Observation:
        return self.step(
            [fire_weapon(weapon_slot, target_room_id, target_ship_id)],
            advance_frames=advance_frames,
        )

    # ---- internals ----------------------------------------------------
    def _write_action_atomic(self, payload: dict[str, Any]) -> None:
        tmp = self.action_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self.action_path)  # atomic rename on the same filesystem

    def _wait_for(
        self, predicate: Callable[[Observation], bool], timeout: float | None = None
    ) -> Observation:
        deadline = time.monotonic() + (self.step_timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            try:
                obs = self.client.read_latest()
                if predicate(obs):
                    return obs
            except (FileNotFoundError, ObservationValidationError):
                pass
            time.sleep(self.poll_interval)
        eff = self.step_timeout if timeout is None else timeout
        raise TimeoutError(f"action seq {self.action_seq} not acked within {eff:.1f}s")
