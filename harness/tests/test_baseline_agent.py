"""Baseline decisions count effects and tolerate ordinary charging waits."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import baseline_agent as baseline
import pytest


@pytest.mark.parametrize("hostile", [False, None, 1])
def test_baseline_does_not_start_fighting_a_surviving_friendly_or_unknown_ship(hostile):
    before = obs(weapon_charge=20)
    if hostile is None:
        before.enemy_ship.pop("hostile")
    else:
        before.enemy_ship["hostile"] = hostile
    session = Session(before, before)
    assert baseline.fight(session, before, lambda _: None)[1] == "peace"
    assert session.waits == [] and session.jump_calls == 0


def test_baseline_surrender_change_is_observable_progress_without_resource_reward():
    before = obs()
    signature = baseline._progress_state(before)
    before.enemy_ship["hostile"] = False
    assert baseline._progress_state(before) != signature


def obs(x=0, charged=True, weapon_charge=0):
    return SimpleNamespace(
        game_started=True, choice_box_open=False, event=None,
        raw={"jump_charged": charged},
        map={"sector": 0, "current_pos": {"x": x, "y": 0},
             "connected_beacons": [{"index": 0, "visited": 0}]},
        player_ship={"hull": {"current": 30}, "oxygen_pct": 100,
                     "crew": [{"health_current": 100}], "systems": [],
                     "weapons": [{"slot": 0, "powered": True, "charge": weapon_charge,
                                  "charge_max": 20, "weapon_type": "LASER"}]},
        enemy_ship={"hostile": True, "hull": {"current": 10}, "rooms": [{"room_id": 1, "system_id": 3}]},
    )


class Session:
    def __init__(self, before, after):
        self.before, self.after = before, after
        self.waits, self.jump_calls = [], 0

    def step(self, actions, advance_frames):
        self.waits.append(advance_frames)
        return self.before

    def jump(self, target, advance_frames):
        self.jump_calls += 1
        self.before = self.after
        return self.after

    def observe(self):
        return self.before


def test_flee_requires_observed_movement():
    before = obs()
    session = Session(before, obs())
    assert baseline._flee(session, before, lambda _: None)[1] == "stuck"
    session = Session(before, obs(x=35))
    assert baseline._flee(session, before, lambda _: None)[1] == "flee"


def test_health_danger_ignores_enemy_boarders_but_keeps_our_boarding_crew():
    before = obs()
    before.player_ship["crew"] = [
        {"health_current": 100}, {"intruder": True, "health_current": 1},
        {"player_owned": True, "on_enemy_ship": True, "intruder": True, "health_current": 60},
    ]
    assert baseline.min_crew_health(before) == 60


def test_flee_does_not_issue_jump_while_drive_is_uncharged():
    before = obs(charged=False)
    session = Session(before, obs(x=35))
    assert baseline._flee(session, before, lambda _: None)[1] == "stuck"
    assert session.jump_calls == 0
    assert len(session.waits) == 30


def test_wait_budget_targets_charge_and_skips_already_pending_weapons():
    o = obs(weapon_charge=17)
    assert baseline.charge_frames(o) == 180
    o.player_ship["weapons"][0]["charge"] = 20
    assert len(baseline.ready_weapons(o)) == 1
    o.player_ship["weapons"][0]["manual_fire_pending"] = True
    assert baseline.ready_weapons(o) == []


def test_missing_map_identity_cannot_prove_successful_jump():
    before, after = obs(), obs(x=35)
    before.map.pop("current_pos")
    assert baseline.moved(before, after) is False


def test_play_counts_only_successful_jumps_and_returns_termination_metadata():
    before, after = obs(), obs(x=35)
    before.enemy_ship = after.enemy_ship = None
    session = Session(before, after)
    result = baseline.play(session, 1, lambda _: None)
    assert result["jumps"] == 1
    assert result["status"] == "completed"
    assert result["reason"] == "budget"
    stationary = obs()
    stationary.enemy_ship = None
    result = baseline.play(Session(stationary, stationary), 1, lambda _: None)
    assert result["jumps"] == 0
    assert result["status"] == "failed"


def test_play_marks_a_valid_loss_completed():
    dead = obs()
    dead.player_ship["hull"]["current"] = 0
    result = baseline.play(Session(dead, dead), 1, lambda _: None)
    assert result["status"] == "completed"
    assert result["reason"] == "destroyed"


def test_gameover_mode_passes_jump_budget_and_finishes_on_verified_victory():
    initial = obs()
    initial.enemy_ship = None

    class WinningSession(Session):
        def jump(self, target, advance_frames):
            self.jump_calls += 1
            self.before = obs(x=self.jump_calls * 35)
            self.before.enemy_ship = None
            if self.jump_calls == 2:
                self.before.raw["victory"] = True
            return self.before

    session = WinningSession(initial, initial)
    result = baseline.play(session, 1, lambda _: None, play_to_gameover=True)
    assert result["jumps"] == 2
    assert result["status"] == "completed"
    assert result["reason"] == "victory"


def test_gameover_stall_guard_and_charging_progress():
    initial = obs()
    initial.enemy_ship = None
    result = baseline.play(Session(initial, initial), 1, lambda _: None,
                           play_to_gameover=True, stall_limit=1)
    assert result["status"] == "failed"
    assert result["reason"] == "stalled"
    before = baseline._progress_state(initial)
    initial.player_ship["weapons"][0]["charge"] += 1
    assert baseline._progress_state(initial) != before


def test_pending_native_fuel_animation_survives_short_baseline_stall_limit():
    initial = obs(charged=False)
    initial.enemy_ship = None
    initial.raw["economy"] = {"fuel_recovery": {"waiting": True, "can_wait": False}}
    class WaitingSession(Session):
        def step(self, actions, advance_frames):
            result = super().step(actions, advance_frames)
            if len(self.waits) >= 8:
                result.raw["victory"] = True
            return result
    session = WaitingSession(initial, initial)
    result = baseline.play(session, 1, lambda _: None, play_to_gameover=True, stall_limit=1)
    assert result["reason"] == "victory"
    assert len(session.waits) == 8
    prior = baseline._progress_state(initial)
    initial.raw["economy"]["fuel_recovery"]["distress_on"] = True
    assert baseline._progress_state(initial) != prior
