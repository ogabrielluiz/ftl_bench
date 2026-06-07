"""AgentSession protocol tests against a simulated bridge.

The fake bridge mimics the Lua bridge's contract: it watches the action file
and, when it sees a new seq, writes an observation stamped with that
last_action_seq while paused. This exercises the real reset/step polling logic
without a running game.
"""
import json
import threading
import time
from pathlib import Path

import pytest

from ftl_bench import AgentSession, set_system_power, move_crew


def _write_obs(folder: Path, *, seq, paused=True, tick=1):
    obs = {
        "schema_version": 2,
        "tick": tick,
        "seed": 0,
        "game_started": True,
        "paused": paused,
        "last_action_seq": seq,
        "player_ship": {"hull": {"current": 30, "max": 30}},
        "enemy_ship": None,
    }
    p = folder / "ftl_agent_observation.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obs))
    # The session reads this file concurrently; on Windows the replace can hit a transient
    # sharing violation (PermissionError / WinError 5). Retry, mirroring the real bridge.
    for attempt in range(9):
        try:
            tmp.replace(p)
            return
        except (PermissionError, OSError):
            if attempt == 8:
                raise
            time.sleep(0.01)


class FakeBridge(threading.Thread):
    """Applies the action file's seq into the observation, like the real bridge."""

    def __init__(self, folder: Path):
        super().__init__(daemon=True)
        self.folder = folder
        self.action_path = folder / "ftl_agent_action.json"
        self._stop = threading.Event()
        self._tick = 1

    def run(self):
        while not self._stop.is_set():
            try:
                if self.action_path.exists():
                    act = json.loads(self.action_path.read_text())
                    self._tick += 1
                    _write_obs(self.folder, seq=act["seq"], paused=True, tick=self._tick)
            except (json.JSONDecodeError, FileNotFoundError, PermissionError, OSError):
                pass  # transient file races on Windows must not kill the bridge thread
            time.sleep(0.005)

    def stop(self):
        self._stop.set()


def test_action_constructors():
    assert set_system_power(0, 2) == {"type": "set_system_power", "system_id": 0, "level": 2}
    assert move_crew(1, 5) == {"type": "move_crew", "crew_id": 1, "room_id": 5, "slot_id": -1}
    assert move_crew(1, 5, 3)["slot_id"] == 3


def test_write_action_atomic_shape(tmp_path):
    sess = AgentSession(tmp_path)
    sess.action_seq = 4
    sess._write_action_atomic({"seq": 5, "advance_frames": 30, "actions": []})
    written = json.loads((tmp_path / "ftl_agent_action.json").read_text())
    assert written == {"seq": 5, "advance_frames": 30, "actions": []}


def test_reset_returns_paused_observation(tmp_path):
    _write_obs(tmp_path, seq=None, paused=True)
    sess = AgentSession(tmp_path, step_timeout=2.0)
    obs = sess.reset()
    assert obs.paused is True
    assert obs.last_action_seq is None


def test_step_acks_seq(tmp_path):
    _write_obs(tmp_path, seq=None, paused=True)
    bridge = FakeBridge(tmp_path)
    bridge.start()
    try:
        sess = AgentSession(tmp_path, step_timeout=3.0)
        sess.reset()
        obs = sess.step([set_system_power(0, 2), move_crew(0, 5)], advance_frames=10)
        assert obs.last_action_seq == 1
        assert obs.paused is True
        # second step increments seq and is acked too
        obs2 = sess.step([set_system_power(1, 3)])
        assert obs2.last_action_seq == 2
    finally:
        bridge.stop()


def test_step_times_out_without_bridge(tmp_path):
    _write_obs(tmp_path, seq=None, paused=True)
    sess = AgentSession(tmp_path, step_timeout=0.3)
    sess.reset()
    with pytest.raises(TimeoutError):
        sess.step([set_system_power(0, 1)])  # no bridge ever acks seq 1


def test_abandon_to_menu_bails_immediately_at_game_over(tmp_path):
    # The crew-death / win GAME OVER screen can't be cleared by return_to_menu/confirm_menu, so
    # abandon_to_menu must NOT spin the menu loop to its timeout — it returns at once and issues
    # no action (the caller's reset hard-restarts FTL instead). With no bridge present, spinning
    # would otherwise burn the full timeout; this returns fast and writes no action file.
    obs = {
        "schema_version": 3, "tick": 1, "seed": 0,
        "game_started": True, "paused": True, "game_over": True,
        "last_action_seq": 7,
        "player_ship": {"hull": {"current": 0, "max": 30}}, "enemy_ship": None,
    }
    (tmp_path / "ftl_agent_observation.json").write_text(json.dumps(obs))
    sess = AgentSession(tmp_path, step_timeout=0.3)
    start = time.monotonic()
    out = sess.abandon_to_menu(timeout=30.0)
    assert out.game_over is True
    assert time.monotonic() - start < 5.0          # did not spin to the 30s timeout
    assert not (tmp_path / "ftl_agent_action.json").exists()   # issued no menu-return action
