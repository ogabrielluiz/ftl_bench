"""Native economy facts pass through every model action representation without guessed prices."""
from __future__ import annotations

import json

import pytest

import decision_backends as decision
import llm_agent
import openai_backend
from ftl_bench import Observation
from play_cli import apply_command, command_to_action, compact


def economy():
    return {"native_protocol": 5, "upgrade_available": True,
            "systems": [
                {"system_id": 2, "current_max_power": 1, "max_level": 3,
                 "next_upgrade_cost": 30, "can_upgrade": True},
                {"system_id": 8, "current_max_power": 3, "max_level": 3,
                 "next_upgrade_cost": 10, "can_upgrade": False},
                {"system_id": 11, "current_max_power": 1, "max_level": 4,
                 "can_upgrade": True},  # Missing native cost remains unknown.
                {"system_id": 13, "next_upgrade_cost": 60, "can_upgrade": True},
                {"system_id": 9, "next_upgrade_cost": 0, "can_upgrade": True},
            ],
            "reactor": {"current_max_power": 10, "max_level": 25,
                        "next_upgrade_cost": 50, "can_upgrade": True},
            "fuel_recovery": {"out_of_fuel": True, "distress_on": False,
                              "can_wait": True, "waiting": False}}


def observation():
    return Observation.from_dict({"schema_version": 3, "tick": 1, "seed": 1,
        "game_started": True, "paused": True,
        "player_ship": {"resources": {"scrap": 50, "fuel": 0},
                        "systems": [{"id": 0, "power": 1, "power_max": 2}]},
        "capabilities": {"upgrade_rules": True, "fuel_recovery": True}, "economy": economy()})


def request_for(raw=None):
    state = compact(raw or observation())
    return decision.build_jev_request("Observed FTL interface", "OBSERVATION:\n" + json.dumps(state))


def provider_answers(request, selections):
    return {"answers": {key: {"type": "choice", "choice": selections.get(key, "hold" if "hold" in question["criteria"] else "150"),
        "confidence": 1, "probabilities": {option: float(option == selections.get(key, "hold" if "hold" in question["criteria"] else "150"))
            for option in question["criteria"]}} for key, question in request["questions"].items()}}


def test_compact_keeps_original_system_ids_native_costs_and_recovery_flags():
    raw = observation()
    result = compact(raw)
    assert result["economy"] == raw.raw["economy"]
    assert result["economy"]["systems"][0]["system_id"] == 2
    assert "next_upgrade_cost" not in result["economy"]["systems"][2]
    assert result["economy"]["fuel_recovery"]["distress_on"] is False
    del raw.raw["economy"]
    assert "economy" not in compact(raw)


@pytest.mark.parametrize("native", [True, False, None])
def test_compact_ignores_legacy_positive_jump_hint_and_uses_native_navigation(native):
    raw = observation()
    raw.raw.update(jump_charged=True, jump_charge={"current": 41, "max": 85}, jump_charge_pct=1)
    if native is not None:
        raw.raw["economy"]["navigation"] = {"can_jump": native, "enemy_defeat_pending": True,
            "drive_current": 41, "drive_max": 85, "reason": "drive_charging"}
    result = compact(raw)
    assert result["map"]["can_jump"] is native and result["map"]["jump_charged"] is native
    assert result["map"]["jump_charge"] == ({"current": 41, "max": 85} if native is not None else None)
    assert result["map"]["jump_charge_pct"] == (41 / 85 if native is not None else None)


@pytest.mark.parametrize("can_jump", [False, None])
def test_jev_does_not_offer_navigation_from_legacy_ready_hint(can_jump):
    raw = observation()
    raw.player_ship["resources"]["fuel"] = 1
    raw.raw["jump_charged"] = True
    raw.raw["map"] = {"connected_beacons": [{"index": 4}]}
    raw.map = raw.raw["map"]
    if can_jump is not None:
        raw.raw["economy"]["navigation"] = {"can_jump": can_jump}
    request, _ = request_for(raw)
    assert "navigation" not in request["questions"]


def test_jev_only_offers_known_affordable_and_native_available_upgrades():
    request, decisions = request_for()
    choices = request["questions"]["economy"]["criteria"]
    assert set(choices) == {"hold", "upgrade_2", "upgrade_9", "reactor"}
    assert choices["upgrade_2"]["command"] == "upgrade 2"
    assert choices["reactor"]["native_upgrade"]["next_upgrade_cost"] == 50
    assert set(request["questions"]["fuel_recovery"]["criteria"]) == {"hold", "waitfuel", "distress_on"}
    reply = decision.render_jev_plan(provider_answers(request, {"economy": "reactor", "fuel_recovery": "waitfuel"}), request, decisions)
    commands, frames = llm_agent.parse_plan(reply)
    assert [command_to_action(verb, args) for verb, args in commands] == [
        {"type": "upgrade_reactor"}, {"type": "wait_for_fuel"}]
    assert frames == 150


@pytest.mark.parametrize("change", ["no_capability", "unavailable", "old_protocol", "unknown_reactor_cost", "unknown_scrap"])
def test_jev_does_not_guess_upgrade_permissions_or_missing_prices(change):
    raw = observation()
    if change == "no_capability":
        raw.raw["capabilities"]["upgrade_rules"] = False
    elif change == "unavailable":
        raw.raw["economy"]["upgrade_available"] = False
    elif change == "old_protocol":
        raw.raw["economy"]["native_protocol"] = 4
    elif change == "unknown_reactor_cost":
        raw.raw["economy"]["systems"] = []
        raw.raw["economy"]["reactor"]["next_upgrade_cost"] = None
    else:
        del raw.raw["player_ship"]["resources"]["scrap"]
    request, _ = request_for(raw)
    assert "economy" not in request["questions"]


@pytest.mark.parametrize("context", [{"out_of_fuel": False}, {"can_wait": False}, {"waiting": True}])
def test_jev_fuel_controls_require_native_legal_recovery_context(context):
    raw = observation()
    raw.raw["economy"]["fuel_recovery"].update(context)
    request, _ = request_for(raw)
    assert "fuel_recovery" not in request["questions"]


def test_jev_distress_toggle_uses_current_native_state_and_recovery_capability():
    raw = observation()
    raw.raw["economy"]["fuel_recovery"]["distress_on"] = True
    request, decisions = request_for(raw)
    assert set(request["questions"]["fuel_recovery"]["criteria"]) == {"hold", "waitfuel", "distress_off"}
    reply = decision.render_jev_plan(provider_answers(request, {"fuel_recovery": "distress_off"}), request, decisions)
    commands, _ = llm_agent.parse_plan(reply)
    assert [command_to_action(*command) for command in commands] == [{"type": "set_distress", "enabled": False}]
    raw.raw["capabilities"]["fuel_recovery"] = False
    assert "fuel_recovery" not in request_for(raw)[0]["questions"]


@pytest.mark.parametrize("verb,args,action", [
    ("reactor", [], {"type": "upgrade_reactor"}),
    ("waitfuel", [], {"type": "wait_for_fuel"}),
    ("distress", ["on"], {"type": "set_distress", "enabled": True}),
    ("distress", ["off"], {"type": "set_distress", "enabled": False}),
])
def test_single_command_and_parsed_model_plan_dispatch_same_native_action(verb, args, action):
    calls = []
    class Session:
        def step(self, actions, advance_frames):
            calls.append((actions, advance_frames))
            return observation()
    command = " ".join([verb, *args])
    plan, advance = llm_agent.parse_plan(f"ACTION:\n  {command}\n  advance 60")
    assert plan == [(verb, args)] and advance == 60
    assert command_to_action(*plan[0]) == action
    apply_command(Session(), verb, args)
    assert calls == [([action], 20)]
    apply_command(Session(), "wait", ["60"])
    assert calls[-1] == ([], 60)
    assert command_to_action("wait", ["60"]) is None


@pytest.mark.parametrize("verb,args", [("distress", []), ("distress", ["yes"]),
    ("distress", ["off", "on"]), ("reactor", ["10"]), ("waitfuel", ["600"])])
def test_invalid_economy_arguments_are_rejected_without_dispatch(verb, args):
    class Session:
        def step(self, *args, **kwargs):
            pytest.fail("invalid command reached native dispatch")
    with pytest.raises(ValueError):
        command_to_action(verb, args)
    with pytest.raises(ValueError):
        apply_command(Session(), verb, args)


def test_openai_structured_schema_round_trips_native_recovery_commands(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-fixture")
    plan = {"reason": "Use observed native controls", "commands": [
        {"command": "distress", "args": ["on"]}, {"command": "waitfuel", "args": []},
        {"command": "reactor", "args": []}], "advance": 90}
    def post(endpoint, body, key, *, provider):
        allowed = body["text"]["format"]["schema"]["properties"]["commands"]["items"]["properties"]["command"]["enum"]
        assert {"distress", "waitfuel", "reactor"}.issubset(allowed)
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(plan)}]}]}, {"model": "offline-model"}
    monkeypatch.setattr(openai_backend, "post_json", post)
    reply = openai_backend.openai_complete("FTL", "OBSERVATION", "offline-model")
    commands, frames = llm_agent.parse_plan(reply)
    assert [command_to_action(*command) for command in commands] == [
        {"type": "set_distress", "enabled": True}, {"type": "wait_for_fuel"}, {"type": "upgrade_reactor"}]
    assert frames == 90
