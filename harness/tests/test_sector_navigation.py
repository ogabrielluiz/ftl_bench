"""Sector refusals remain visible through the session and actual play CLI."""
import json
import sys

import pytest
from ftl_bench import AgentSession, Observation
import play_cli


def obs(*, sector=1, reason=None, status="rejected", fuel=2):
    raw = {"schema_version": 3, "tick": 1, "seed": 1, "game_started": True,
           "paused": True, "map": {"sector": sector, "at_exit": True},
           "player_ship": {"resources": {"fuel": fuel}}, "enemy_ship": None,
           "jump_charged": True}
    if reason is not None:
        raw["action_feedback"] = [{"type": "leave_sector", "action_index": 1,
                                   "status": status, "reason": reason}]
    return Observation.from_dict(raw)


@pytest.mark.parametrize("reason", ["native_leave_refused", "no_fuel", "event_open"])
def test_session_stops_after_a_definite_leave_refusal(monkeypatch, tmp_path, reason):
    session = AgentSession(tmp_path)
    calls = []
    monkeypatch.setattr(session, "observe", lambda: obs())
    def refused(actions, **kwargs):
        calls.append(actions)
        return obs(reason=reason)
    monkeypatch.setattr(session, "step", refused)
    result = session.leave_sector()
    assert len(calls) == 1
    assert result.raw["action_feedback"][0]["reason"] == reason


def test_session_keeps_advancing_a_temporary_leave_block_until_committed(monkeypatch, tmp_path):
    session = AgentSession(tmp_path)
    replies = iter([obs(reason="drive_charging"), obs(sector=2)])
    calls = []
    monkeypatch.setattr(session, "observe", lambda: obs())
    def reply(actions, **kwargs):
        calls.append(actions)
        return next(replies)
    monkeypatch.setattr(session, "step", reply)
    assert session.leave_sector().map["sector"] == 2
    assert len(calls) == 2


@pytest.mark.parametrize("hostile,expected_calls", [(False, 2), (True, 1), (None, 2)])
def test_retained_ship_pointer_does_not_block_native_sector_pumping_without_hostility(monkeypatch, tmp_path, hostile, expected_calls):
    session = AgentSession(tmp_path)
    retained = obs(reason="drive_charging")
    retained.enemy_ship = {"hull": {"current": 4}, "destroyed": False}
    if hostile is not None:
        retained.enemy_ship["hostile"] = hostile
    replies = iter([retained, obs(sector=2)])
    calls = []
    monkeypatch.setattr(session, "observe", lambda: obs())
    def reply(actions, **kwargs):
        calls.append(actions)
        return next(replies)
    monkeypatch.setattr(session, "step", reply)
    result = session.leave_sector()
    assert len(calls) == expected_calls
    assert result.map["sector"] == (2 if expected_calls == 2 else 1)


@pytest.mark.parametrize("reason,expected", [
    ("native_leave_refused", "refused"), ("no_fuel", "fuel"),
    ("event_open", "event"), ("not_at_exit", "exit"),
    ("enemy_present", "enemy"), ("drive_charging", "pending"),
    ("mid_warp", "pending"), ("transition_pending", "pending"),
    ("native_leave_failed", "refused"), ("native_leave_unavailable", "refused"),
])
def test_cli_preserves_native_leave_refusals_and_temporary_blocks(monkeypatch, capsys, reason, expected):
    before, after = obs(), obs(reason=reason)
    class Session:
        def observe(self): return before
        def leave_sector(self): return after
    monkeypatch.setattr(play_cli, "AgentSession", Session)
    monkeypatch.setattr(sys, "argv", ["play_cli", "leave"])
    play_cli.main()
    output = json.loads(capsys.readouterr().out)
    assert expected in output["leave_result"]
    assert output["action_feedback"] == after.raw["action_feedback"]
    assert "call leave again" not in output["leave_result"]


def test_cli_recognizes_a_committed_sector_before_any_stale_refusal(monkeypatch, capsys):
    class Session:
        def observe(self): return obs()
        def leave_sector(self): return obs(sector=2, reason="mid_warp")
    monkeypatch.setattr(play_cli, "AgentSession", Session)
    monkeypatch.setattr(sys, "argv", ["play_cli", "leave"])
    play_cli.main()
    assert "committed" in json.loads(capsys.readouterr().out)["leave_result"]
