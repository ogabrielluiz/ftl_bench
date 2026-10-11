"""Regression tests for adapter compacting.

The LLM sees play_cli.compact(), not the raw bridge payload. These tests lock in
small schema details that affect decisions.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parents[2]
_ADAPTER = _REPO / "adapter"
_HARNESS_SRC = _REPO / "harness" / "src"
for _path in (_ADAPTER, _HARNESS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import llm_agent  # noqa: E402
from play_cli import compact  # noqa: E402
import pytest


@pytest.mark.parametrize("hostile", [True, False, None, 1])
def test_compact_requires_native_hostility_for_powered_ship_combat_cues(hostile):
    enemy = {"hull": {"current": 4, "max": 15}, "targetable": True,
             "weapons": [{"powered": True}], "systems": [{"id": 3, "power": 2}],
             "drones": [{"deployed": True, "firing": True, "name": "Combat Drone"}],
             "rooms": [{"room_id": 7, "system_id": 3}]}
    if hostile is not None:
        enemy["hostile"] = hostile
    result = compact(_obs({}, enemy_ship=enemy, raw={"incoming_projectiles": 1}))
    assert result["enemy"]["hull"] == "4/15"
    assert result["enemy"]["active"] is (hostile is True)
    assert result["enemy"]["targetable"] is (hostile is True)
    assert result["enemy"]["hostile"] is (hostile if isinstance(hostile, bool) else None)
    assert result["incoming_fire"] == 1
    assert result["enemy"]["drones"][0]["firing"] is True


def test_native_surrender_without_hull_or_resource_change_is_observed_progress():
    raw = _obs({}, enemy_ship={"hostile": True, "targetable": True, "hull": {"current": 4, "max": 15}})
    before = compact(raw)
    raw.enemy_ship.update(hostile=False, targetable=False)
    after = compact(raw)
    assert llm_agent._progress_sig(before) != llm_agent._progress_sig(after)
    assert llm_agent._state_sig(before) != llm_agent._state_sig(after)


def test_compact_keeps_native_owned_crew_ids_control_flags_and_rejections():
    friendly = {"id": 0, "player_owned": True, "owner_ship_id": 0, "current_ship_id": 0,
                "controllable": False, "mind_controlled": True, "health_current": 70}
    hostile = {"id": 3, "intruder": True, "health_current": 100}
    boarder = {"id": 6, "player_owned": True, "owner_ship_id": 0, "current_ship_id": 1,
               "intruder": True, "on_enemy_ship": True, "controllable": True, "health_current": 90}
    dead = {"id": 8, "player_owned": True, "health_current": 0, "dead": False}
    feedback = [{"action_index": 0, "crew_id": 3, "status": "rejected", "reason": "not_player_owned"}]
    result = compact(_obs({"crew": [friendly, hostile, boarder, dead]}, raw={"action_feedback": feedback}))
    assert result["crew_count"] == 2
    assert [member["id"] for member in result["crew"]] == [0, 6]
    assert result["crew"][0]["controllable"] is False
    assert result["crew"][0]["mind_controlled"] is True
    assert result["crew"][1]["owner_ship_id"] == 0
    assert result["crew"][1]["current_ship_id"] == 1
    assert result["crew"][1]["boarding"] is True
    assert result["action_feedback"] == feedback


def test_compact_preserves_native_choice_availability_delay_and_original_indices():
    feedback = [{"type": "choose_event", "choice_index": 17,
                 "status": "rejected", "reason": "choice_disabled"}]
    choices = [
        {"index": 8, "text": "Continue.", "native_type": 0,
         "disabled": False, "enabled": True, "available": True},
        {"index": 17, "text": "Buy supplies.", "native_type": 1,
         "disabled": True, "enabled": False, "available": False,
         "cost": 60},
    ]
    result = compact(_obs({}, choice_box_open=True,
                          event={"text": "Trade convoy", "choices": choices,
                                 "open_time": 0, "dialog_keys": 2},
                          raw={"action_feedback": feedback}))
    assert result["event"]["choices"] == choices
    assert result["event"]["open_time"] == 0
    assert result["event"]["dialog_keys"] == 2
    assert result["action_feedback"] == feedback


def test_compact_does_not_fabricate_unbound_choice_type_or_event_timing():
    result = compact(_obs({}, choice_box_open=True,
                          event={"text": "Old popup", "open_time": None, "dialog_keys": None,
                                 "choices": [{"index": 12, "text": "Continue.", "native_type": None}]}))
    assert result["event"] == {"text": "Old popup", "choices": [{"index": 12, "text": "Continue."}]}


def _obs(
    player_ship: dict,
    *,
    enemy_ship: dict | None = None,
    raw: dict | None = None,
    game_map: dict | None = None,
    choice_box_open: bool = False,
    event: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        player_ship=player_ship,
        enemy_ship=enemy_ship,
        raw=raw or {},
        game_started=True,
        paused=True,
        map=game_map,
        choice_box_open=choice_box_open,
        event=event,
    )


def test_compact_preserves_needs_repair_when_damage_is_zero():
    c = compact(
        _obs(
            {
                "oxygen_pct": 0,
                "systems": [
                    {
                        "id": 2,
                        "room_id": 13,
                        "power": 0,
                        "power_max": 1,
                        "damage": 0,
                        "needs_repair": True,
                    }
                ],
                "crew": [],
                "weapons": [],
            }
        )
    )

    assert c["oxygen_pct"] == 0
    assert c["systems"] == [
        {
            "id": 2,
            "name": "oxygen",
            "power": "0/1",
            "room": 13,
            "needs_repair": True,
            "broken": "needs_repair",
            "repair_room": 13,
        }
    ]


def test_compact_preserves_airlock_connected_to_space():
    door = {"index": 1, "id": 8, "room_a": 2, "room_b": -1,
            "open": True, "airlock": True}
    assert compact(_obs({"doors": [door]}))["doors"] == [door]


def test_compact_preserves_native_ion_hack_parts_and_setup_evidence():
    c = compact(_obs({
        "blueprint": "PLAYER_SHIP_HARD",
        "resources": {"drone_parts": 4},
        "systems": [{"id": 3, "power": 0, "power_max": 3,
                     "ioned": True, "ion": 2, "hacked": True}],
    }, raw={"difficulty": 2, "victory": False,
            "capabilities": {"victory": True}}))
    assert c["systems"][0]["ioned"] is True
    assert c["systems"][0]["ion"] == 2
    assert c["systems"][0]["hacked"] is True
    assert c["drone_parts"] == 4
    assert c["ship"] == "PLAYER_SHIP_HARD"
    assert c["difficulty"] == 2
    assert c["victory"] is False
    assert c["capabilities"]["victory"] is True


def test_compact_distinguishes_confirmed_victory_from_game_over():
    c = compact(_obs({}, raw={"game_over": True, "victory": True}))
    assert c["game_status"] == "VICTORY"
    c = compact(_obs({}, raw={"game_over": True}))
    assert c["game_status"] == "GAME_OVER"
    assert "victory" not in c


def test_batch_feedback_treats_needs_repair_as_broken_system():
    feedback = llm_agent._batch_feedback(
        [("power", ["2", "1"])],
        {
            "systems": [
                {
                    "id": 2,
                    "name": "oxygen",
                    "power": "0/1",
                    "room": 13,
                    "needs_repair": True,
                }
            ]
        },
    )

    assert "oxygen NEEDS REPAIR" in feedback
    assert "powering does NOT fix it" in feedback
    assert "room 13" in feedback


def test_compact_marks_damaged_sensors_as_broken_not_unpowered():
    c = compact(
        _obs(
            {
                "oxygen_pct": 100,
                "systems": [
                    {
                        "id": 7,
                        "room_id": 3,
                        "power": 0,
                        "power_max": 1,
                        "damage": 0,
                        "needs_repair": True,
                    }
                ],
                "crew": [],
                "weapons": [],
            }
        )
    )

    assert c["systems"] == [
        {
            "id": 7,
            "name": "sensors",
            "power": "0/1",
            "room": 3,
            "needs_repair": True,
            "broken": "needs_repair",
            "repair_room": 3,
        }
    ]


def test_compact_preserves_special_system_readiness_and_enemy_crew_rooms():
    c = compact(
        _obs(
            {
                "oxygen_pct": 100,
                "systems": [],
                "crew": [],
                "weapons": [],
                "cloak": {"installed": True, "ready": True, "active": False},
                "teleporter": {
                    "installed": True,
                    "charged": True,
                    "organic_in_tele_room": 2,
                    "organic_aboard_by_room": [{"room_id": 5, "organic": 2}],
                },
            },
            enemy_ship={
                "hull": {"current": 10, "max": 10},
                "rooms": [{"room_id": 5, "system_id": 3, "hacked": True}],
                "rooms_with_crew": [{"room_id": 5, "crew": 2, "controllable": 1}],
                "systems": [],
                "weapons": [],
            },
        )
    )

    assert c["cloak"] == {"installed": True, "ready": True, "active": False}
    assert c["teleporter"]["organic_in_tele_room"] == 2
    assert c["enemy"]["rooms"] == [{"room_id": 5, "system": "weapons", "hacked": True}]
    assert c["enemy"]["rooms_with_crew"] == [{"room_id": 5, "crew": 2, "controllable": 1}]


def test_compact_preserves_room_door_event_and_flagship_metadata():
    long_event = "Line one\n" + ("choice detail " * 120)
    c = compact(
        _obs(
            {
                "oxygen_pct": 35,
                "systems": [],
                "crew": [],
                "weapons": [],
                "rooms": [
                    {
                        "room_id": 2,
                        "oxygen": 0,
                        "fires": 2,
                        "breached": True,
                        "rect": {"x": 1, "y": 2, "w": 3, "h": 4},
                    }
                ],
                "doors": [
                    {
                        "index": 0,
                        "id": 12,
                        "room_a": 2,
                        "room_b": 3,
                        "open": True,
                        "locked": False,
                        "forced_open": False,
                        "hacked": 0,
                    }
                ],
            },
            enemy_ship={
                "hull": {"current": 20, "max": 20},
                "flagship": True,
                "super_shield": {"value": 5, "max": 5},
                "power_surge_timer": 8,
                "power_surge_timer_max": 20,
                "power_surge_type": "drones",
                "crew": [
                    {
                        "id": 1,
                        "room_id": 4,
                        "health": 38,
                        "health_max": 100,
                        "species": "human",
                        "repairing": True,
                    }
                ],
                "rooms": [],
                "systems": [],
                "weapons": [],
            },
            raw={"flagship": {"present": True, "phase": 2}},
            choice_box_open=True,
            event={
                "text": long_event,
                "selected_choice": 1,
                "choices": [
                    {"index": 0, "text": "Use the blue option.", "blue": True, "enabled": True},
                    {"index": 1, "text": "Hire them.", "disabled": True, "cost": 65},
                ],
            },
        )
    )

    assert c["rooms"] == [
        {
            "room_id": 2,
            "oxygen": 0,
            "fires": 2,
            "breached": True,
            "rect": {"x": 1, "y": 2, "w": 3, "h": 4},
        }
    ]
    assert c["doors"] == [
        {
            "index": 0,
            "id": 12,
            "room_a": 2,
            "room_b": 3,
            "open": True,
            "locked": False,
            "forced_open": False,
            "hacked": 0,
        }
    ]
    assert c["enemy"]["flagship"] is True
    assert c["enemy"]["super_shield"] == {"value": 5, "max": 5}
    assert c["enemy"]["power_surge_timer"] == 8
    assert c["enemy"]["crew"][0]["repairing"] is True
    assert c["flagship"] == {"present": True, "phase": 2}
    assert c["event"]["text"] == long_event.replace("\n", " ")
    assert len(c["event"]["text"]) > 1000
    assert c["event"]["selected_choice"] == 1
    assert c["event"]["choices"] == [
        {"index": 0, "text": "Use the blue option.", "blue": True, "enabled": True},
        {"index": 1, "text": "Hire them.", "disabled": True, "cost": 65},
    ]


def test_compact_preserves_route_metadata_and_indexed_event_choices():
    c = compact(
        _obs(
            {"oxygen_pct": 100, "systems": [], "crew": [], "weapons": []},
            raw={"jump_charged": True},
            game_map={
                "at_exit": False,
                "choosing_new_sector": False,
                "out_of_fuel": False,
                "current_pos": {"x": 0, "y": 0},
                "exit_pos": {"x": 30, "y": 40},
                "connected_beacons": [
                    {
                        "index": 0,
                        "visited": 0,
                        "exit_beacon": False,
                        "fleet": False,
                        "quest": True,
                        "known": True,
                        "danger_zone": False,
                        "boss": False,
                        "nebula": True,
                        "store": True,
                        "distress": False,
                        "has_event": True,
                        "new_sector": False,
                        "pos_x": 3,
                        "pos_y": 4,
                    }
                ],
                "sector_choices": [{"index": 1, "type": "civilian", "reachable": True}],
            },
            choice_box_open=True,
            event={
                "text": "Distress call",
                "choices": [{"text": "Aid them."}, {"text": "Ignore."}],
            },
        )
    )

    assert c["map"]["beacons"] == [
        {
            "index": 0,
            "visited": 0,
            "exit": False,
            "fleet": False,
            "quest": True,
            "known": True,
            "danger_zone": False,
            "boss": False,
            "nebula": True,
            "store": True,
            "distress": False,
            "has_event": True,
            "new_sector": False,
            "pos": [3, 4],
            "dist_to_exit": 45,
        }
    ]
    assert c["map"]["sector_choices"] == [{"index": 1, "type": "civilian", "reachable": True}]
    assert c["event"] == {
        "text": "Distress call",
        "choices": [{"index": 0, "text": "Aid them."}, {"index": 1, "text": "Ignore."}],
    }
