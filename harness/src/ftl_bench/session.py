"""ftl_bench M2 closed-loop session over the paused FTL bridge.

The bridge keeps the game paused and applies actions written to
`ftl_agent_action.json`, stamping each resulting observation with
`last_action_seq`. `AgentSession.step()` writes an action, then polls the
observation until the bridge acks that seq while paused.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from ftl_bench.observation import (
    Observation,
    ObservationClient,
    ObservationValidationError,
)

# FTL user folder (where the bridge reads/writes its files). Honors the
# FTL_SAVE_DIR env var; otherwise defaults per-OS so a native Windows or macOS
# run needs no env setup at all. On Windows the folder is
# `…/Documents/My Games/FasterThanLight`; on macOS the Application Support folder.
def ftl_user_folder() -> Path:
    env = os.environ.get("FTL_SAVE_DIR")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        return Path("~/Documents/My Games/FasterThanLight").expanduser()
    return Path("~/Library/Application Support/FasterThanLight").expanduser()


DEFAULT_USER_FOLDER = ftl_user_folder()


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


def leave_sector() -> dict[str, Any]:
    """Leave the current sector from the exit beacon -> next sector. Only takes effect
    when standing on the exit beacon with fuel and no active combat."""
    return {"type": "leave_sector"}


def store_buy(index: int) -> dict[str, Any]:
    """Buy the store's `buy`-list item #index (weapon/drone/system/augment/repair/resource).
    Scrap is deducted by the game's StoreBox::Purchase. Only takes effect at a store."""
    return {"type": "store_buy", "index": int(index)}


def store_sell(index: int) -> dict[str, Any]:
    """Sell the store's `sell`-list (your inventory) item #index for scrap."""
    return {"type": "store_sell", "index": int(index)}


def upgrade_system(system_id: int) -> dict[str, Any]:
    """Spend scrap to raise a system's MAX power by one (e.g. a 2nd shield layer = shields
    0). Available anytime, not just at a store."""
    return {"type": "upgrade_system", "system_id": int(system_id)}


def cloak() -> dict[str, Any]:
    """Engage the cloaking system (needs it installed + powered): evasion boost +
    untargetable for a level-scaled timer. No-op if already cloaked / on cooldown."""
    return {"type": "cloak"}


def set_doors(open: bool, ship_id: int = 0, room_id: int | None = None,
              include_airlocks: bool = False) -> dict[str, Any]:
    """Open (vent) or close doors. ship_id 0=player, 1=enemy. `room_id` limits to doors of
    one room (else all interior doors); `include_airlocks` vents to space. Used to fight
    fires / suffocate boarders by venting their room's oxygen."""
    a: dict[str, Any] = {"type": "set_doors", "open": bool(open), "ship_id": int(ship_id),
                         "include_airlocks": bool(include_airlocks)}
    if room_id is not None:
        a["room_id"] = int(room_id)
    return a


def mind_control(target_room_id: int, target_crew_id: int | None = None) -> dict[str, Any]:
    """Mind-control an enemy crew member in `target_room_id` (see enemy.rooms_with_crew).
    Needs the Mind Control system installed + powered + off cooldown."""
    a: dict[str, Any] = {"type": "mind_control", "target_room_id": int(target_room_id)}
    if target_crew_id is not None:
        a["target_crew_id"] = int(target_crew_id)
    return a


def battery() -> dict[str, Any]:
    """Engage the Backup Battery (system id 12, needs it installed + powered): grants
    temporary extra reactor power for a level-scaled timer, then locks on cooldown.
    No-op if already discharging / on cooldown / depowered. Player ship, no target."""
    return {"type": "battery"}


def fire_beam(weapon_slot: int, room_a: int, room_b: int | None = None,
              target_ship_id: int = 1) -> dict[str, Any]:
    """Fire a BEAM weapon: sweep from room_a's center to room_b's center on the target ship
    (1 = enemy, default). Two DISTINCT rooms chain damage across the hull; if room_b is omitted
    it equals room_a (degenerate single point, no chaining). Only takes effect when the slot is
    a powered beam (obs weapon_type=="BEAM" / is_beam / targets_required==2)."""
    if room_b is None:
        room_b = room_a
    return {"type": "fire_beam", "weapon_slot": int(weapon_slot),
            "room_a": int(room_a), "room_b": int(room_b), "target_ship_id": int(target_ship_id)}


def hack_system(target_system_id: int = 0) -> dict[str, Any]:
    """Deploy the Hacking drone at an enemy SYSTEM and arm the disruptive pulse. target_system_id:
    enemy system to hack (shields=0, engines=1, weapons=3, drones=4, piloting=6, cloaking=10,
    mind=14; see enemy.rooms for what the enemy has). Needs the Hacking system installed (buy at
    a store) + powered (set_system_power 15, >=1). No-op if not installed/powered, the enemy lacks
    that system, or our hacking is ion-locked."""
    return {"type": "hack_system", "target_system_id": int(target_system_id)}


def deploy_drone(slot: int | None = None, power_level: int | None = None,
                 allow_crew_drone: bool = False) -> dict[str, Any]:
    """Power the drone system to deploy a drone. `slot` = loadout slot index (from
    obs.player_ship.drones.slots); omit to deploy the first unpowered SAFE (space-drone) slot.
    Needs Drone Control installed + powered + (for combat/boarder) drone parts. Defense(0)/
    Combat(1)/Shield(7) are SpaceDrones (safe). allow_crew_drone=True is required for crew-drone
    types (repair 2, battle 3, boarder 4, ship-repair 5) — off by default (Rosetta teardown class)."""
    a: dict[str, Any] = {"type": "deploy_drone"}
    if slot is not None:
        a["slot"] = int(slot)
    if power_level is not None:
        a["power_level"] = int(power_level)
    if allow_crew_drone:
        a["allow_crew_drone"] = True
    return a


def recall_drones() -> dict[str, Any]:
    """Power the drone system down to 0 (recall all space drones). No-op without the system."""
    return {"type": "recall_drones"}


def teleport_crew(command: int = 1, target_room_id: int = -1) -> dict[str, Any]:
    """Send (command=1) / recall (command=2) ORGANIC boarders to/from an enemy room. SEND:
    target_room_id = enemy room to board (-1 = random); needs >=1 organic crew in
    player_ship.teleporter.tele_room_id (move them there first). RECALL: target_room_id = the
    enemy room your boarders are in (see player_ship.teleporter.organic_aboard_by_room); -1 lets
    the engine resolve it. Needs Teleporter (id 9) installed + powered + charged. Crew-drones are
    skipped (Rosetta teardown safety)."""
    return {"type": "teleport_crew", "command": int(command), "target_room_id": int(target_room_id)}


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

    def abandon_to_menu(self, timeout: float = 30.0) -> Observation:
        """Drive the current run back to the main menu WITHOUT starting a new game, so a
        finished episode leaves FTL cleanly at the menu instead of paused mid-run. Safe/idempotent
        at the menu. Uses the same return_to_menu + confirm (lose-progress dialog) actions the
        reset machinery uses, looped until the menu is reached."""
        try:
            if not self.observe().game_started:
                return self.observe()
        except (FileNotFoundError, OSError):
            pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # The menu transition leaves the in-game paused state, so step()'s seq-ack (which
            # waits for paused + matching seq) often times out even though the action took
            # effect — swallow it and decide from game_started instead.
            for act in ("return_to_menu", "confirm_menu"):
                try:
                    self.step([{"type": act}], advance_frames=30)
                except TimeoutError:
                    pass
            try:
                if not self.observe().game_started:
                    break
            except (FileNotFoundError, OSError):
                pass
        return self.observe()

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

    def fire_beam(self, weapon_slot: int, room_a: int, room_b: int | None = None,
                  target_ship_id: int = 1, advance_frames: int = 150) -> Observation:
        return self.step(
            [fire_beam(weapon_slot, room_a, room_b, target_ship_id)],
            advance_frames=advance_frames,
        )

    def hack_system(self, target_system_id: int = 0, advance_frames: int = 120) -> Observation:
        """Deploy + arm the hacking drone at an enemy system. The generous budget lets the drone
        fly across and the first pulse land before the bridge re-pauses."""
        return self.step([hack_system(target_system_id)], advance_frames=advance_frames)

    def leave_sector(self, advance_frames: int = 360, max_attempts: int = 6) -> Observation:
        """Leave the sector from the exit beacon to the next sector, reliably.

        `benchmark_leave_sector` only SETS the transition flags (bOpen /
        bChoosingNewSector / finalSectorChoice); FTL's StarMap::OnLoop commits them
        (SelectNewSector -> AdvanceWorldLevel -> travel) on a *later* tick. A single
        fixed advance can re-pause mid-transition before the commit lands, so one
        `leave` call read as a silent no-op to a real agent (it took ~5 manual retries
        to cross). Pump the action until the sector actually increments — the action
        should do what it says. Re-issuing mid-warp is a safe no-op (the Lua jump_ready
        guard skips it) that just advances frames, so each retry lets the transition
        progress. Stop early if a hard precondition fails (enemy present / left the
        exit) so a genuinely-refused leave doesn't spin the full budget."""
        start_sector = (self.observe().map or {}).get("sector")
        obs = self.step([leave_sector()], advance_frames=advance_frames)
        for _ in range(max_attempts - 1):
            m = obs.map or {}
            cur = m.get("sector")
            if start_sector is not None and cur is not None and cur > start_sector:
                break  # committed — the sector advanced
            if not m.get("at_exit"):
                break  # no longer on the exit beacon; nothing left to pump
            if obs.enemy_ship is not None:
                break  # refused: can't leave with a live enemy (re-issuing won't help)
            # preconditions still hold (incl. a drive mid-charge) -> pump more frames
            obs = self.step([leave_sector()], advance_frames=advance_frames)
        return obs

    # ---- internals ----------------------------------------------------
    def _write_action_atomic(self, payload: dict[str, Any]) -> None:
        tmp = self.action_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        # The bridge holds ftl_agent_action.json open to read it, so on Windows the
        # replace can briefly hit a sharing violation (PermissionError / WinError 5)
        # or other transient OSError. Retry a few times — mirrors the obs-read retry.
        for attempt in range(9):
            try:
                tmp.replace(self.action_path)  # atomic rename on the same filesystem
                return
            except (PermissionError, OSError):
                if attempt == 8:
                    raise
                time.sleep(0.05)

    def _wait_for(
        self, predicate: Callable[[Observation], bool], timeout: float | None = None
    ) -> Observation:
        deadline = time.monotonic() + (self.step_timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            try:
                obs = self.client.read_latest()
                if predicate(obs):
                    return obs
            except (FileNotFoundError, ObservationValidationError, PermissionError, OSError):
                pass
            time.sleep(self.poll_interval)
        eff = self.step_timeout if timeout is None else timeout
        raise TimeoutError(f"action seq {self.action_seq} not acked within {eff:.1f}s")
