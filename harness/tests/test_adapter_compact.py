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
        }
    ]


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
