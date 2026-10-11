"""Jev HTTP contract and observation-bound options; every request is mocked."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import decision_backends as decision  # noqa: E402
import model_backend  # noqa: E402
from play_cli import command_to_action, compact  # noqa: E402


def turn(observation):
    return "Your recent turns:\n(none yet)\n\nOBSERVATION:\n" + json.dumps(observation) + "\n\nDecide your plan."


def observed():
    return {
        "fuel": 5, "parts": 2, "scrap": 100,
        "economy": {"navigation": {"can_jump": True, "enemy_defeat_pending": False}},
        "systems": [{"id": 3, "name": "weapons", "power": "1/3", "room": 4},
                    {"id": 6, "name": "piloting", "power": "0/1", "room": 7}],
        "rooms": [{"room_id": 4}, {"room_id": 7}, {"room_id": 12}],
        "crew": [{"id": 8, "room": 4}],
        "weapons": [{"slot": 2, "type": "LASER", "powered": True}],
        "enemy": {"targetable": True, "hostile": True, "rooms": [{"room_id": 9, "system": "weapons"},
                                                 {"room_id": 1, "system": "shields"}]},
        "map": {"jump_charged": True, "beacons": [{"index": 11}, {"index": 5}]},
    }


def answers_for(request, selections=None):
    selections = selections or {}
    answers = {}
    for key, question in request["questions"].items():
        criteria = question["criteria"]
        choice = selections.get(key, "hold" if "hold" in criteria else "150" if key == "advance" else next(iter(criteria)))
        answers[key] = {"type": "choice", "choice": choice, "confidence": 1,
                        "probabilities": {option: float(option == choice) for option in criteria}}
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 800, "output_tokens": 30}}


def test_jev_uses_documented_request_and_preserves_trace_metadata(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    captured = {}

    def post(endpoint, body, key, *, provider):
        captured.update(endpoint=endpoint, body=body, key=key, provider=provider)
        return answers_for(body, {"weapon_2": "room_9", "advance": "260"}), {"request_id": "request-1", "latency_seconds": 0.02}

    monkeypatch.setattr(model_backend, "post_json", post)
    reply = decision.jev_complete("Play the actual FTL goal.", turn(observed()), None)
    assert captured["endpoint"] == "https://api.typesafe.ai/v1/systemone"
    assert captured["provider"] == "typesafe"
    assert captured["key"] == "test-key"
    assert set(captured["body"]) == {"model", "state", "questions"}
    assert captured["body"]["model"] == "jev-1.13.0"
    assert reply == "ACTION:\n  fire 2 9\n  advance 260"
    assert reply.metadata["action_selection"] == "enumerated"
    assert reply.metadata["decision_contract"] == "jev-actuator-choice-v1"
    assert reply.metadata["request_id"] == "request-1"
    assert reply.metadata["usage"]["input_tokens"] == 800
    assert "test-key" not in json.dumps(reply.metadata)


def test_held_actuators_generate_only_model_selected_advance():
    request, decisions = decision.build_jev_request("FTL interface", turn(observed()))
    assert decision.render_jev_plan(answers_for(request), request, decisions) == "ACTION:\n  advance 150"
    assert "power_6" not in request["questions"]
    assert "navigation" in request["questions"]
    assert set(request["questions"]["weapon_2"]["criteria"]) == {"hold", "room_1", "room_9"}


@pytest.mark.parametrize("hostile", [True, False, None, 1])
def test_native_hostility_controls_offensive_choices_but_not_recall_upgrade_or_navigation(hostile):
    observation = observed()
    enemy = observation["enemy"]
    if hostile is None:
        enemy.pop("hostile")
    else:
        enemy["hostile"] = hostile
    enemy["rooms_with_crew"] = [{"room_id": 9, "crew": 2}]
    observation.update(hacking={"installed": True}, mind_control={"installed": True},
                       teleporter={"installed": True, "organic_in_tele_room": 2,
                                   "organic_aboard_by_room": [{"room_id": 9, "organic": 1}]},
                       capabilities={"upgrade_rules": True})
    observation["map"]["at_exit"] = True
    observation["economy"].update(native_protocol=5, upgrade_available=True,
                                 systems=[{"system_id": 0, "next_upgrade_cost": 30, "can_upgrade": True}])
    request, _ = decision.build_jev_request("FTL", turn(observation))
    questions = request["questions"]
    for key in ("weapon_2", "hacking", "mind_control"):
        assert (key in questions) is (hostile is True)
    teleporter = questions["teleporter"]["criteria"]
    assert "recall_9" in teleporter
    assert any(key.startswith("board_") for key in teleporter) is (hostile is True)
    assert "upgrade_0" in questions["economy"]["criteria"]
    navigation = questions["navigation"]["criteria"]
    assert "jump_5" in navigation
    assert ("leave" in navigation) is (hostile is False)


def test_crew_questions_only_offer_owned_controllable_crew_on_our_ship():
    observation = {"rooms": [{"room_id": 4}, {"room_id": 7}], "crew": [
        {"id": 0, "room": 4},  # Legacy records without ownership remain usable.
        {"id": 2, "room": 4, "player_owned": True, "controllable": True, "current_ship_id": 0},
        {"id": 3, "room": 4, "intruder": True},
        {"id": 4, "room": 4, "player_owned": False, "controllable": True},
        {"id": 5, "room": 4, "owner_ship_id": 1, "intruder": False},
        {"id": 6, "room": 4, "player_owned": True, "controllable": False},
        {"id": 7, "room": 4, "player_owned": True, "intruder": True, "on_enemy_ship": True},
        {"id": 8, "room": 4, "owner_ship_id": 0, "current_ship_id": 1},
        {"id": 9, "room": 4, "boarding": True},
        {"id": 10, "room": 4, "player_owned": True, "dead": True},
        {"id": 11, "room": 4, "player_owned": True, "controllable": True, "health_current": 0},
        {"id": 12, "room": 4, "player_owned": True, "controllable": True, "hp": "0/100"},
    ]}
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    assert {key for key in request["questions"] if key.startswith("crew_")} == {"crew_0", "crew_2"}
    reply = decision.render_jev_plan(answers_for(request, {"crew_0": "room_7", "crew_2": "room_7"}), request, decisions)
    assert reply == "ACTION:\n  crew 0 7\n  crew 2 7\n  advance 150"


def test_event_popup_only_offers_enabled_choices_and_advance():
    observation = observed()
    observation["event"] = {"choices": [
        {"index": 5, "text": "Blue option", "blue": True, "enabled": True},
        {"index": 8, "text": "Disabled", "enabled": False},
        {"index": 11, "text": "Available alternative"},
    ]}
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    assert set(request["questions"]) == {"event", "advance"}
    assert set(request["questions"]["event"]["criteria"]) == {"hold", "event_5", "event_11"}
    assert decision.render_jev_plan(answers_for(request, {"event": "event_11"}), request, decisions) == "ACTION:\n  event 11\n  advance 150"


def test_native_disabled_choice_survives_compact_and_is_never_offered_to_jev():
    raw_event = {"text": "Trade convoy", "open_time": 0.12, "dialog_keys": 2,
                 "choices": [
                     {"index": 7, "text": "Trade supplies", "native_type": 1,
                      "disabled": True, "enabled": False, "available": False},
                     {"index": 14, "text": "Continue", "native_type": 0,
                      "disabled": False, "enabled": True, "available": True},
                     {"index": 23, "text": "Legacy choice with unknown availability"},
                 ]}
    observation = compact(SimpleNamespace(player_ship={}, enemy_ship=None, raw={},
                                          game_started=True, paused=True, map=None,
                                          choice_box_open=True, event=raw_event))
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    assert set(request["questions"]) == {"event", "advance"}
    assert set(request["questions"]["event"]["criteria"]) == {"hold", "event_14", "event_23"}
    assert request["questions"]["event"]["criteria"]["event_14"]["event_choice"]["native_type"] == 0
    assert "native_type" not in request["questions"]["event"]["criteria"]["event_23"]["event_choice"]
    assert observation["event"]["open_time"] == 0.12
    assert observation["event"]["dialog_keys"] == 2
    assert decision.render_jev_plan(answers_for(request, {"event": "event_14"}), request, decisions) == "ACTION:\n  event 14\n  advance 150"
    with pytest.raises(decision.DecisionContractError, match="invalid choice"):
        decision.render_jev_plan(answers_for(request, {"event": "event_7"}), request, decisions)


def test_all_native_disabled_choices_leave_only_model_selected_wait():
    observation = {"event": {"text": "Blocked popup", "choices": [
        {"index": 5, "native_type": 1, "disabled": True, "enabled": False, "available": False}]}}
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    assert "event" not in request["questions"]
    assert "concession" not in request["questions"]
    assert decision.render_jev_plan(answers_for(request), request, decisions) == "ACTION:\n  advance 150"


def test_store_indices_are_observed_and_single_transaction():
    observation = observed()
    observation["store"] = {"buy": [{"i": 19, "name": "Fuel", "count": 2}, {"i": 20, "count": 0}],
                            "sell": [{"index": 31, "name": "Laser"}]}
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    choices = request["questions"]["economy"]["criteria"]
    assert "buy_19" in choices and "sell_31" in choices and "buy_20" not in choices
    reply = decision.render_jev_plan(answers_for(request, {"economy": "buy_19"}), request, decisions)
    assert reply == "ACTION:\n  buy 19\n  advance 150"
    assert command_to_action("buy", ["19"]) == {"type": "store_buy", "index": 19}


def test_beam_endpoints_are_factorized_without_quadratic_option_truncation():
    observation = observed()
    observation["weapons"] = [{"slot": 2, "is_beam": True}]
    observation["enemy"]["rooms"] = [{"room_id": index} for index in range(20)]
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    assert len(request["questions"]["beam_2_start"]["criteria"]) == 20
    selected = {"beam_2": "fire", "beam_2_start": "room_19", "beam_2_end": "room_4"}
    reply = decision.render_jev_plan(answers_for(request, selected), request, decisions)
    assert reply == "ACTION:\n  beam 2 19 4\n  advance 150"
    assert command_to_action("beam", ["2", "19", "4"])["room_b"] == 4


def test_special_actions_use_visible_state_without_target_preferences():
    observation = observed()
    observation.update(hacking={"installed": True}, drones={"installed": True, "slots": [{"slot": 4, "is_space": True}]},
                       teleporter={"installed": True, "organic_in_tele_room": 2, "organic_aboard_by_room": [{"room_id": 9, "organic": 1}]},
                       mind_control={"installed": True}, cloak={"installed": True}, battery={"installed": False})
    observation["enemy"]["rooms_with_crew"] = [{"room_id": 9, "crew": 2}]
    request, _ = decision.build_jev_request("FTL", turn(observation))
    assert set(request["questions"]["hacking"]["criteria"]) == {"hold", "system_0", "system_3"}
    assert set(request["questions"]["mind_control"]["criteria"]) == {"hold", "room_9"}
    assert set(request["questions"]["teleporter"]["criteria"]) == {"hold", "board_1", "board_9", "recall_9"}
    assert "battery" not in request["questions"]


def test_uncharged_drive_excludes_jumps_without_selecting_a_policy():
    observation = observed()
    observation["map"]["jump_charged"] = False
    observation["economy"]["navigation"]["can_jump"] = False
    request, _ = decision.build_jev_request("FTL", turn(observation))
    assert "navigation" not in request["questions"]


@pytest.mark.parametrize("bad_choice", ["invented_room", None, {"command": "jump 999"}])
def test_out_of_set_or_malformed_choices_are_rejected(bad_choice):
    request, decisions = decision.build_jev_request("FTL", turn(observed()))
    response = answers_for(request)
    response["answers"]["weapon_2"]["choice"] = bad_choice
    with pytest.raises(decision.DecisionContractError, match="invalid choice"):
        decision.render_jev_plan(response, request, decisions)


def test_missing_probability_contract_is_rejected():
    request, decisions = decision.build_jev_request("FTL", turn(observed()))
    response = answers_for(request)
    response["answers"]["advance"].pop("confidence")
    with pytest.raises(decision.DecisionContractError, match="probabilities/confidence"):
        decision.render_jev_plan(response, request, decisions)


def test_choice_option_limit_is_explicit_not_silently_pruned():
    observation = {"crew": [{"id": 1, "room": -1}], "rooms": [{"room_id": index} for index in range(255)]}
    with pytest.raises(decision.DecisionContractError, match="maximum is 255"):
        decision.build_jev_request("FTL", turn(observation))


def test_maximum_actions_is_explicit_not_silently_truncated():
    observation = {"crew": [{"id": index, "room": 1} for index in range(13)], "rooms": [{"room_id": 1}, {"room_id": 2}]}
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    selected = {f"crew_{index}": "room_2" for index in range(13)}
    with pytest.raises(decision.DecisionContractError, match="plan limit is 12"):
        decision.render_jev_plan(answers_for(request, selected), request, decisions)


def test_concession_is_terminal_and_must_be_selected_alone():
    request, decisions = decision.build_jev_request("FTL", turn(observed()))
    assert decision.render_jev_plan(answers_for(request, {"concession": "giveup"}), request, decisions) == "ACTION:\n  giveup"
    with pytest.raises(decision.DecisionContractError, match="concession together"):
        decision.render_jev_plan(answers_for(request, {"concession": "giveup", "weapon_2": "room_9"}), request, decisions)


def test_missing_key_fails_before_http(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.setattr(model_backend, "post_json", lambda *a, **kw: pytest.fail("Unexpected API request"))
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        decision.jev_complete("FTL", turn(observed()))


def test_reflection_without_observation_cannot_invent_a_generated_plan():
    with pytest.raises(decision.DecisionContractError, match="OBSERVATION JSON"):
        decision.build_jev_request("Reflect", "Write free-text lessons")


def test_door_options_follow_visible_topology_and_include_outer_airlocks():
    observation = {"rooms": [{"room_id": 0}, {"room_id": 1}, {"room_id": 99}], "doors": [
        {"index": 0, "room_a": 0, "room_b": 1, "open": False},
        {"index": 1, "room_a": 1, "room_b": -1, "open": True, "airlock": True},
        {"index": 2, "room_a": 99, "room_b": -1, "open": False, "locked": True},
        {"index": 3, "room_a": 99, "room_b": 0, "open": True, "forced_open": True}]}
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    choices = request["questions"]["doors"]["criteria"]
    assert "open_99" not in choices and "close_99" not in choices
    assert "close_1" in choices
    assert choices["close_1"]["include_airlocks"] is True
    assert choices["close_1"]["affected_doors"][0]["airlock"] is True
    reply = decision.render_jev_plan(answers_for(request, {"doors": "close_1"}), request, decisions)
    assert "doors close 1" in reply
    assert command_to_action("doors", ["close", "1"])["include_airlocks"] is True


def test_all_locked_door_snapshot_does_not_offer_unavailable_door_actuator():
    request, _ = decision.build_jev_request("FTL", turn({"doors": [{"room_a": 1, "room_b": -1,
        "airlock": True, "open": False, "hacked": True}]}))
    assert "doors" not in request["questions"]


@pytest.mark.parametrize("change,invariant,message", [
    (lambda answer: answer.pop("confidence"), "confidence_range", "confidence is missing"),
    (lambda answer: answer.update(confidence=1.5), "confidence_range", "confidence is 1.5"),
    (lambda answer: answer.update(probabilities=None), "probability_map", "type NoneType"),
    (lambda answer: answer["probabilities"].pop("hold"), "probability_options", "missing_options=1"),
    (lambda answer: answer["probabilities"].update(hold=-0.1), "probability_range", "probability for 'hold' is -0.1"),
    (lambda answer: answer["probabilities"].update(hold=float("nan")), "probability_range", "probability for 'hold' is nan"),
    (lambda answer: answer["probabilities"].update(hold=0.7), "probability_sum", "probability sum=0.7"),
])
def test_probability_diagnostics_identify_the_exact_failed_invariant(change, invariant, message):
    request, decisions = decision.build_jev_request("FTL", turn(observed()))
    response = answers_for(request)
    change(response["answers"]["weapon_2"])
    with pytest.raises(decision.DecisionContractError) as failure:
        decision.render_jev_plan(response, request, decisions)
    assert failure.value.details["invariant"] == invariant
    assert failure.value.details["question"] == "weapon_2"
    assert message in str(failure.value)
    assert "weapon_2" in str(failure.value)


def test_invalid_provider_completion_preserves_usage_trace_and_safe_diagnostic(monkeypatch):
    secret = "fixture-api-secret"
    monkeypatch.setenv("TYPESAFE_API_KEY", secret)
    observation = observed()
    observation["doors"] = [{"index": 0, "room_a": 4, "room_b": -1, "open": False, "airlock": True}]

    def post(endpoint, body, key, *, provider):
        response = answers_for(body)
        # Arbitrary malformed provider strings are not echoed into logged diagnostics.
        response["answers"]["doors"]["confidence"] = secret
        return response, {"provider": provider, "request_id": "invalid-doors-request",
                          "client_request_id": "invalid-doors-client", "model": "jev-1.13.0",
                          "usage": response["usage"], "latency_seconds": 0.8}

    monkeypatch.setattr(model_backend, "post_json", post)
    with pytest.raises(decision.DecisionContractError) as failure:
        decision.jev_complete("FTL", turn(observation))
    error = failure.value
    assert "confidence is type str" in str(error)
    assert secret not in str(error) + json.dumps(error.metadata)
    assert error.metadata["request_id"] == "invalid-doors-request"
    assert error.metadata["provider"] == "typesafe"
    assert error.metadata["model"] == "jev-1.13.0"
    assert error.metadata["usage"] == {"input_tokens": 800, "output_tokens": 30}
    assert error.metadata["latency_seconds"] == 0.8
    assert error.metadata["action_selection"] == "enumerated"
    assert error.metadata["response_status"] == "contract_error"
    assert error.metadata["contract_error"]["invariant"] == "confidence_range"
    assert error.metadata["contract_error"]["question"] == "doors"
    assert error.metadata["decision_confidence"]["doors"] is None
    from ftl_bench.reporting import summarize_model_usage
    usage = summarize_model_usage([{"kind": "model_error", "model": error.metadata}])
    assert usage["recorded_completions"] == 1
    assert usage["input_tokens"] == 800
    assert usage["output_tokens"] == 30


@pytest.mark.parametrize("total,accepted", [(0.99, True), (1.01, True), (0.989, False), (1.011, False)])
def test_probability_sum_tolerance_includes_both_boundaries(total, accepted):
    request, decisions = decision.build_jev_request("FTL", turn(observed()))
    response = answers_for(request)
    probabilities = response["answers"]["weapon_2"]["probabilities"]
    probabilities.update({option: 0.0 for option in probabilities})
    probabilities["hold"] = min(total, 1.0)
    other = next(option for option in probabilities if option != "hold")
    probabilities[other] = max(0.0, total - 1.0)
    if accepted:
        assert decision.render_jev_plan(response, request, decisions) == "ACTION:\n  advance 150"
    else:
        with pytest.raises(decision.DecisionContractError) as failure:
            decision.render_jev_plan(response, request, decisions)
        assert failure.value.details["invariant"] == "probability_sum"
        assert failure.value.details["tolerance"] == 0.01


def test_seventeen_option_rounded_distribution_accepts_lower_tolerance_boundary():
    observation = {"crew": [{"id": 2, "room": 0}], "rooms": [{"room_id": room} for room in range(17)]}
    request, decisions = decision.build_jev_request("FTL", turn(observation))
    response = answers_for(request)
    probabilities = response["answers"]["crew_2"]["probabilities"]
    assert len(probabilities) == 17
    probabilities.update({option: 0.01 for option in probabilities})
    probabilities["hold"] = 0.83
    assert decision.render_jev_plan(response, request, decisions) == "ACTION:\n  advance 150"
