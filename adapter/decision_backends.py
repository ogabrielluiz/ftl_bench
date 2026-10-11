"""Typed decision providers translated into the shared FTL ACTION contract.

Jev's documented API evaluates Choice/Score/Noul questions; it cannot generate an
arbitrary plan. This adapter enumerates observable actuator settings, asks one
Choice per actuator, and renders the selected commands without a scripted policy.
Questions are independent. Reactor allocations can therefore conflict and are
subject to the same bridge feedback as other agents. Plans over the shared action
limit are rejected, never silently truncated. No OpenAI Decisions endpoint is
assumed: a future provider can return the same Completion once publicly specified.

HTTP/schema: https://docs.typesafe.ai/api
Models: https://docs.typesafe.ai/models
Choice limits: https://docs.typesafe.ai/primitives/choice
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_DEFAULT_MODEL = "jev-1.13.0"
DECISION_CONTRACT = "jev-actuator-choice-v1"
MAX_CHOICE_OPTIONS = 255
MAX_PLAN_ACTIONS = 12
ADVANCE_CHOICES = (30, 60, 90, 150, 260, 600)
_SYSTEM_IDS = {
    "shields": 0, "engines": 1, "oxygen": 2, "weapons": 3, "drones": 4,
    "medbay": 5, "piloting": 6, "sensors": 7, "doors": 8, "teleporter": 9,
    "cloaking": 10, "cloak": 10, "artillery": 11, "battery": 12,
    "clonebay": 13, "mind": 14, "mind_control": 14, "hacking": 15,
}


class DecisionContractError(ValueError):
    """The provider or observation cannot satisfy the typed decision contract."""

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}
        self.metadata = None


def _probability_number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def _numeric_description(value) -> str:
    # Never echo an arbitrary provider string: it could contain sensitive content.
    if isinstance(value, (int, float)):
        return repr(value)
    return f"type {type(value).__name__}"


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _records(value) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _player_owned_crew(member: dict) -> bool:
    if isinstance(member.get("player_owned"), bool):
        return member["player_owned"]
    owner = member.get("owner_ship_id")
    if _integer(owner):
        return owner == 0
    return not member.get("intruder") or member.get("on_enemy_ship") is True


def observation_from_turn(user: str) -> dict:
    """Decode the actual OBSERVATION JSON, not examples or JSON in recent history."""
    marker = "OBSERVATION:\n"
    if marker not in user:
        raise DecisionContractError("Jev requires a turn containing OBSERVATION JSON")
    source = user.split(marker, 1)[1].lstrip()
    try:
        observation, _ = json.JSONDecoder().raw_decode(source)
    except ValueError as error:
        raise DecisionContractError("Invalid OBSERVATION JSON for Jev") from error
    if not isinstance(observation, dict):
        raise DecisionContractError("Jev OBSERVATION must be an object")
    return observation


def _allowed(choice: dict) -> bool:
    return not (choice.get("disabled") is True or choice.get("locked") is True
                or any(choice.get(key) is False for key in ("enabled", "available", "requirements_met")))


def build_jev_request(system: str, user: str, model: str | None = None) -> tuple[dict, list[dict]]:
    observation = observation_from_turn(user)
    questions: dict[str, dict] = {}
    decisions: list[dict] = []

    def question(key: str, instructions: str, choices: dict[str, Any]):
        if not choices or len(choices) > MAX_CHOICE_OPTIONS:
            raise DecisionContractError(f"Jev question {key!r} has {len(choices)} options; maximum is 255")
        questions[key] = {"type": "choice", "instructions": instructions, "criteria": choices}

    def actuator(key: str, instructions: str, choices: dict[str, Any]):
        if not choices:
            return
        options = {"hold": {"command": None, "meaning": "Keep this actuator unchanged this turn."}, **choices}
        question(key, instructions, options)
        decisions.append({"kind": "command", "question": key,
                          "commands": {option: description["command"] for option, description in options.items()}})

    def command(text: str, **context):
        return {"command": text, **context}

    event = observation.get("event")
    if isinstance(event, dict) and event.get("choices"):
        # A modal event permits only a choice or a wait; other actuators cannot act.
        choices = {}
        for fallback, item in enumerate(_records(event["choices"])):
            index = item.get("index", fallback)
            if _integer(index) and _allowed(item):
                choices[f"event_{index}"] = command(f"event {index}", event_choice=item)
        actuator("event", "Which available event choice should be selected now, or should the popup remain open?", choices)
    else:
        systems = _records(observation.get("systems"))
        for item in systems:
            sid = item.get("id")
            if not _integer(sid) or sid in {6, 7, 8}:
                continue  # Passive subsystems do not accept reactor allocation.
            try:
                current, maximum = (int(part) for part in str(item.get("power", "")).split("/"))
            except ValueError:
                continue
            if maximum < 0:
                continue
            if maximum >= MAX_CHOICE_OPTIONS:
                raise DecisionContractError(f"System {sid} exceeds Jev's power Choice option limit")
            choices = {f"level_{level}": command(f"power {sid} {level}", system=item)
                       for level in range(maximum + 1) if level != current}
            actuator(f"power_{sid}", f"Which reactor power setting should system {sid} have for this paused plan?", choices)

        rooms = {item["room_id"] for item in _records(observation.get("rooms")) if _integer(item.get("room_id"))}
        rooms.update(item["room"] for item in systems if _integer(item.get("room")))
        for crew in _records(observation.get("crew")):
            cid = crew.get("id")
            current_ship = crew.get("current_ship_id")
            health = crew.get("health_current")
            if health is None and isinstance(crew.get("hp"), str):
                try:
                    health = float(crew["hp"].split("/", 1)[0])
                except ValueError:
                    pass  # Legacy missing health does not invent a death.
            if (not _integer(cid) or not _player_owned_crew(crew)
                    or crew.get("controllable") is False or crew.get("boarding")
                    or crew.get("on_enemy_ship") or crew.get("dead")
                    or (_integer(current_ship) and current_ship != 0)
                    or (isinstance(health, (int, float)) and health <= 0)):
                continue
            choices = {f"room_{room}": command(f"crew {cid} {room}", destination_room=room)
                       for room in sorted(rooms) if room != crew.get("room")}
            actuator(f"crew_{cid}", f"Where should player crew {cid} move this turn, or should they keep their current assignment?", choices)

        enemy = observation.get("enemy")
        enemy = enemy if isinstance(enemy, dict) else {}
        hostile_enemy = enemy.get("hostile") is True
        enemy_rooms = sorted({item["room_id"] for item in _records(enemy.get("rooms")) if _integer(item.get("room_id"))})
        if hostile_enemy and enemy.get("targetable") is True:
            for weapon in _records(observation.get("weapons")):
                slot = weapon.get("slot")
                if not _integer(slot) or not enemy_rooms:
                    continue
                if weapon.get("is_beam") or weapon.get("type") == "BEAM":
                    enable, start, end = f"beam_{slot}", f"beam_{slot}_start", f"beam_{slot}_end"
                    question(enable, f"Should beam weapon slot {slot} be queued to fire this turn?",
                             {"hold": "Hold this weapon.", "fire": "Queue one beam release using the selected endpoints."})
                    endpoints = {f"room_{room}": {"room_id": room} for room in enemy_rooms}
                    question(start, f"Choose the start room for beam slot {slot}, if this beam is fired.", endpoints)
                    question(end, f"Choose the end room for beam slot {slot}, if this beam is fired.", endpoints)
                    decisions.append({"kind": "beam", "question": enable, "start": start, "end": end,
                                      "rooms": {option: description["room_id"] for option, description in endpoints.items()}, "slot": slot})
                else:
                    actuator(f"weapon_{slot}", f"Should weapon slot {slot} be queued to fire at an observed enemy room, or held?",
                             {f"room_{room}": command(f"fire {slot} {room}", enemy_room=room) for room in enemy_rooms})

        visible_doors = _records(observation.get("doors"))
        door_choices = {}
        if visible_doors:
            for operation in ("open", "close"):
                affected = [door for door in visible_doors if not door.get("locked") and not door.get("hacked")
                            and not (operation == "close" and door.get("forced_open"))
                            and door.get("open") is not (operation == "open")]
                if not affected:
                    continue
                door_choices[f"{operation}_all"] = command(f"doors {operation}", affected_doors=affected, include_airlocks=True)
                door_rooms = {door[key] for door in affected for key in ("room_a", "room_b")
                              if _integer(door.get(key)) and door[key] >= 0}
                for room in sorted(door_rooms):
                    door_choices[f"{operation}_{room}"] = command(f"doors {operation} {room}", include_airlocks=True,
                                                                  affected_doors=[door for door in affected if room in (door.get("room_a"), door.get("room_b"))])
        elif any(item.get("id") == 8 for item in systems):
            # Older snapshots identify the subsystem but do not include topology.
            door_choices = {"open_all": command("doors open", include_airlocks=True),
                            "close_all": command("doors close", include_airlocks=True)}
        actuator("doors", "Which visible door operation should be applied this turn, if any? Door commands include airlocks.", door_choices)

        for key, verb in (("cloak", "cloak"), ("battery", "battery")):
            block = observation.get(key)
            if isinstance(block, dict) and block.get("installed") is not False and not block.get("active"):
                actuator(key, f"Should {key} be activated in this plan?", {"activate": command(verb)})

        hacking = observation.get("hacking")
        if hostile_enemy and isinstance(hacking, dict) and hacking.get("installed") is not False:
            target_systems = set()
            for item in _records(enemy.get("rooms")):
                sid = item.get("system_id", _SYSTEM_IDS.get(item.get("system")))
                if _integer(sid):
                    target_systems.add(sid)
            actuator("hacking", "Which observed enemy system should be hacked this turn, if any?",
                     {f"system_{sid}": command(f"hack {sid}") for sid in sorted(target_systems)})

        mind = observation.get("mind_control")
        if hostile_enemy and isinstance(mind, dict) and mind.get("installed") is not False:
            occupied = sorted({item["room_id"] for item in _records(enemy.get("rooms_with_crew"))
                               if _integer(item.get("room_id")) and item.get("crew", 0) > 0})
            actuator("mind_control", "Which occupied enemy room should be targeted by mind control, if any?",
                     {f"room_{room}": command(f"mindcontrol {room}") for room in occupied})

        drones = observation.get("drones")
        if isinstance(drones, dict) and drones.get("installed") is not False:
            choices = {"recall": command("dronerecall")}
            for item in _records(drones.get("slots")):
                slot = item.get("slot")
                if _integer(slot) and not item.get("deployed") and not item.get("dead"):
                    choices[f"deploy_{slot}"] = command(f"drone {slot}" + (" crew" if item.get("is_space") is False else ""), drone=item)
            actuator("drones", "Which drone operation should be applied this turn, if any?", choices)

        teleporter = observation.get("teleporter")
        if isinstance(teleporter, dict) and teleporter.get("installed") is not False:
            choices = {}
            if hostile_enemy and teleporter.get("organic_in_tele_room", 0) > 0:
                choices.update({f"board_{room}": command(f"board {room}") for room in enemy_rooms})
            for item in _records(teleporter.get("organic_aboard_by_room")):
                room = item.get("room_id")
                if _integer(room) and item.get("organic", 0) > 0:
                    choices[f"recall_{room}"] = command(f"recall {room}")
            actuator("teleporter", "Which teleport operation should be applied this turn, if any?", choices)

        economy = {}
        native_economy = observation.get("economy") or {}
        capabilities = observation.get("capabilities") or {}
        protocol = native_economy.get("native_protocol")
        native_economy_ready = _integer(protocol) and protocol >= 5
        scrap = observation.get("scrap")

        def affordable_upgrade(item):
            cost = item.get("next_upgrade_cost")
            return (item.get("can_upgrade") is True and _integer(cost) and cost >= 0
                    and isinstance(scrap, (int, float)) and not isinstance(scrap, bool)
                    and math.isfinite(scrap) and scrap >= cost)

        if (native_economy_ready and capabilities.get("upgrade_rules") is True
                and native_economy.get("upgrade_available") is True):
            for item in _records(native_economy.get("systems")):
                sid = item.get("system_id")
                if _integer(sid) and sid >= 0 and affordable_upgrade(item):
                    economy[f"upgrade_{sid}"] = command(f"upgrade {sid}", native_upgrade=item)
            reactor = native_economy.get("reactor")
            if isinstance(reactor, dict) and affordable_upgrade(reactor):
                economy["reactor"] = command("reactor", native_upgrade=reactor)
        store = observation.get("store")
        if isinstance(store, dict):
            for verb, entries in (("buy", store.get("buy")), ("sell", store.get("sell"))):
                for item in _records(entries):
                    index = item.get("index", item.get("i"))
                    if _integer(index) and _allowed(item) and item.get("count") != 0:
                        economy[f"{verb}_{index}"] = command(f"{verb} {index}", store_item=item)
        actuator("economy", "Which single store transaction or available native system/reactor upgrade should be made this turn, if any?", economy)

        recovery = native_economy.get("fuel_recovery") or {}
        if (native_economy_ready and capabilities.get("fuel_recovery") is True
                and recovery.get("out_of_fuel") is True):
            fuel_choices = {}
            if recovery.get("can_wait") is True and recovery.get("waiting") is False:
                fuel_choices["waitfuel"] = command("waitfuel", fuel_recovery=recovery)
            if (recovery.get("can_wait") is True and recovery.get("waiting") is False
                    and isinstance(recovery.get("distress_on"), bool)):
                enabled = not recovery["distress_on"]
                setting = "on" if enabled else "off"
                fuel_choices[f"distress_{setting}"] = command(f"distress {setting}", fuel_recovery=recovery)
            actuator("fuel_recovery", "Which single native out-of-fuel control should be used this turn, if any? Frame advance is distinct from a recovery turn.", fuel_choices)

        game_map = observation.get("map") or {}
        transitions = {}
        fuel = observation.get("fuel")
        native_navigation = native_economy.get("navigation") or {}
        if native_navigation.get("can_jump") is True and not game_map.get("out_of_fuel") and fuel != 0:
            transitions.update({f"jump_{item['index']}": command(f"jump {item['index']}", beacon=item)
                                for item in _records(game_map.get("beacons")) if _integer(item.get("index"))})
            if game_map.get("at_exit") and (not enemy or enemy.get("hostile") is False or enemy.get("destroyed") is True):
                transitions["leave"] = command("leave")
        actuator("navigation", "Which observed jump or sector transition should be initiated this turn, if any?", transitions)
        actuator("concession", "Should this instance be conceded? Concession must be the only action in a plan.",
                 {"giveup": command("giveup")})

    question("advance", "How many frames should elapse after the paused plan? Choose the next observation interval.",
             {str(frames): {"frames": frames} for frames in ADVANCE_CHOICES})
    body = {
        "model": model or JEV_DEFAULT_MODEL,
        "state": {"interface_and_goal": system, "turn": user, "observation": observation,
                  "decision_contract": DECISION_CONTRACT,
                  "plan_limit": MAX_PLAN_ACTIONS,
                  "instructions": "Choose only actions you want applied. Use hold for all other actuators. "
                                  "Questions share this state but answers are independent. Do not select more than "
                                  "12 commands in total. A concession must be selected alone. "
                                  "Command order follows observation order: power, crew, weapons, doors, special systems, economy, fuel recovery, navigation."},
        "questions": questions,
    }
    return body, decisions


def render_jev_plan(data: dict, request: dict, decisions: list[dict]) -> str:
    answers = data.get("answers")
    if not isinstance(answers, dict):
        raise DecisionContractError("Jev response is missing typed answers", details={"invariant": "answers_map"})
    selected = {}
    for key, question in request["questions"].items():
        answer = answers.get(key)
        if (not isinstance(answer, dict) or answer.get("type") != "choice"
                or not isinstance(answer.get("choice"), str) or answer["choice"] not in question["criteria"]):
            raise DecisionContractError(f"Jev returned an invalid choice for {key!r}",
                                        details={"question": key, "invariant": "choice_domain",
                                                 "expected_options": len(question["criteria"])})
        confidence, probabilities = answer.get("confidence"), answer.get("probabilities")
        prefix = f"Jev returned invalid probabilities/confidence for {key!r}: "
        if not _probability_number(confidence):
            description = "missing" if "confidence" not in answer else _numeric_description(confidence)
            raise DecisionContractError(prefix + f"confidence is {description}; expected a finite number in [0, 1]",
                                        details={"question": key, "invariant": "confidence_range", "actual": description})
        if not isinstance(probabilities, dict):
            description = "missing" if "probabilities" not in answer else f"type {type(probabilities).__name__}"
            raise DecisionContractError(prefix + f"probabilities are {description}; expected an option-to-number map",
                                        details={"question": key, "invariant": "probability_map", "actual": description})
        expected = question["criteria"]
        if probabilities.keys() != expected.keys():
            counts = {"expected_options": len(expected), "actual_options": len(probabilities),
                      "missing_options": len(expected.keys() - probabilities.keys()),
                      "extra_options": len(probabilities.keys() - expected.keys())}
            raise DecisionContractError(prefix + "option keys differ (" + ", ".join(f"{name}={count}" for name, count in counts.items()) + ")",
                                        details={"question": key, "invariant": "probability_options", **counts})
        for option, probability in probabilities.items():
            if not _probability_number(probability):
                description = _numeric_description(probability)
                raise DecisionContractError(prefix + f"probability for {option!r} is {description}; expected a finite number in [0, 1]",
                                            details={"question": key, "invariant": "probability_range",
                                                     "option": option, "actual": description})
        total = math.fsum(probabilities.values())
        # Compare inclusive bounds directly: abs(0.99 - 1) rounds above 0.01.
        # fsum also avoids accumulated rounding from many individual options.
        if not 1 - 0.01 <= total <= 1 + 0.01:
            raise DecisionContractError(prefix + f"probability sum={total:.12g} across {len(probabilities)} options; expected 1 within tolerance 0.01",
                                        details={"question": key, "invariant": "probability_sum",
                                                 "probability_sum": total, "option_count": len(probabilities), "tolerance": 0.01})
        if probabilities[answer["choice"]] < max(probabilities.values()) - 1e-9:
            chosen, maximum = probabilities[answer["choice"]], max(probabilities.values())
            raise DecisionContractError(f"Jev choice for {key!r} is not the highest-probability option (chosen={chosen:.12g}, maximum={maximum:.12g})",
                                        details={"question": key, "invariant": "highest_probability",
                                                 "chosen_probability": chosen, "maximum_probability": maximum})
        selected[key] = answer["choice"]
    commands = []
    for decision in decisions:
        option = selected[decision["question"]]
        if decision["kind"] == "beam":
            if option == "fire":
                start = decision["rooms"][selected[decision["start"]]]
                end = decision["rooms"][selected[decision["end"]]]
                commands.append(f"beam {decision['slot']} {start} {end}")
        elif decision["commands"][option]:
            commands.append(decision["commands"][option])
    if len(commands) > MAX_PLAN_ACTIONS:
        raise DecisionContractError(f"Jev selected {len(commands)} commands; plan limit is {MAX_PLAN_ACTIONS}")
    if "giveup" in commands:
        if len(commands) != 1:
            raise DecisionContractError("Jev selected concession together with other actions")
        return "ACTION:\n  giveup"
    return "ACTION:\n" + "\n".join(f"  {command}" for command in [*commands, f"advance {selected['advance']}"])


def jev_complete(system: str, user: str, model: str | None = None):
    """Make one typed API request; callers load their explicitly supplied .env file."""
    from model_backend import Completion, post_json

    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
    if not key or not key.strip():
        raise RuntimeError("TYPESAFE_API_KEY is not set for the Jev backend")
    request, decisions = build_jev_request(system, user, model)
    data, metadata = post_json(JEV_ENDPOINT, request, key.strip(), provider="typesafe")
    answers = data.get("answers")
    answers = answers if isinstance(answers, dict) else {}
    metadata = {**metadata, "action_selection": "enumerated", "decision_contract": DECISION_CONTRACT,
                "resolved_model": data.get("model"), "usage": data.get("usage"),
                "question_count": len(request["questions"]),
                "option_count": sum(len(question["criteria"]) for question in request["questions"].values()),
                "decision_confidence": {qid: answer.get("confidence") if isinstance(answer, dict)
                                        and _probability_number(answer.get("confidence")) else None
                                        for qid in request["questions"] for answer in [answers.get(qid)]}}
    try:
        reply = render_jev_plan(data, request, decisions)
    except DecisionContractError as error:
        error.metadata = {**metadata, "response_status": "contract_error",
                          "contract_error": {"message": str(error), **error.details}}
        raise
    return Completion(reply, metadata)
