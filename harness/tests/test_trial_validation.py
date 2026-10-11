"""Evidence verifier fails closed for unavailable proof and distinguishes contradictions."""
import copy
import hashlib
import json

import pytest

from ftl_bench import Scenario, SubObjective
from ftl_bench.trial_validation import CAPABILITIES, verify_codex_trial_v4, verify_codex_trial_v5, verify_codex_trial_v6, verify_codex_trial_v7


@pytest.fixture
def trial(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    identities = {}
    for kind, name in (("bridge_lua", "bridge.lua"), ("native_dll", "Hyperspace.dll"), ("prompt", "ftl_agent_v5.md")):
        file = runtime / name
        file.write_bytes(kind.encode())
        identities[kind] = {"path": "C:\\installed\\" + name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
    identities["native_build"] = {"native_protocol": 5, "matches_installed_dll": True,
                                   "dll_sha256": identities["native_dll"]["sha256"]}
    manifest = {"run_id": "test", "status": "completed", "scenario_ids": ["GAME-s1"], "runtime": identities,
        "runner_version": "v4", "ruleset": "v4", "model": "gpt-6.1-sol", "backend": "codex",
        "reasoning_effort": "medium", "prompt_version": "v5", "mode": "gameover", "retries": 0,
        "control_contract": "owned-player-crew-v1", "economy_contract": "native-economy-and-fuel-recovery-v1"}
    (tmp_path / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    binary = runtime / "codex.exe"
    binary.write_bytes(b"CLI binary fixture")
    client = {"backend": "codex", "requested_model": "gpt-6.1-sol", "reasoning_effort": "medium", "authentication": "ChatGPT",
              "client_version": "codex-cli 0.160.0", "binary_path": "C:\\client\\codex.exe", "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    (tmp_path / "client-metadata.json").write_text(json.dumps(client), encoding="utf-8")
    scenario = Scenario("GAME-s1", "full_run", 1, [SubObjective("progress", 11, "milestone")])
    initial = {"schema_version": 3, "tick": 1, "seed": 1, "game_started": True, "game_over": False, "victory": False,
        "difficulty": 0, "ftl_score": 10, "ftl_score_source": "native_live_v1",
        "ftl_score_components": {"scrap_collected": 0, "ships_destroyed": 0, "beacons_explored": 1, "difficulty": 0},
        "capabilities": {**dict.fromkeys(CAPABILITIES, True), "native_protocol": 5},
        "player_ship": {"blueprint": "PLAYER_SHIP_HARD", "hull": {"current": 30, "max": 30},
            "crew": [{"id": 0, "room": 0, "player_owned": True, "owner_ship_id": 0, "current_ship_id": 0,
                      "controllable": True, "health_current": 100, "dead": False}], "resources": {"scrap": 100, "fuel": 0}},
        "map": {"sector": 0}, "choice_box_open": True,
        "event": {"dialog_keys": 2, "open_time": 0.3, "choices": [
            {"index": 3, "native_type": 1, "disabled": True, "enabled": False, "available": False},
            {"index": 7, "native_type": 0, "disabled": False, "enabled": True, "available": True}]},
        "economy": {"native_protocol": 5, "upgrade_available": True,
            "systems": [{"system_id": 2, "current_max_power": 1, "max_level": 3, "next_upgrade_cost": 30, "can_upgrade": True}],
            "reactor": {"current_max_power": 10, "max_level": 25, "next_upgrade_cost": 50, "can_upgrade": True},
            "fuel_recovery": {"out_of_fuel": True, "distress_on": False, "can_wait": True, "waiting": False}}}
    metadata = {**manifest, "scenario_id": scenario.id, "scenario": scenario.to_dict()}
    rows = [{"kind": "meta", "meta": metadata}, {"kind": "reset_episode", "i": 0, "actions": [], "obs": copy.deepcopy(initial)}]
    steps = [
        {"type": "move_crew", "crew_id": 0, "room_id": 1},
        {"type": "choose_event", "choice_index": 7},
        {"type": "upgrade_system", "system_id": 2},
        {"type": "upgrade_reactor"}, {"type": "wait_for_fuel"}, None,
        {"type": "set_distress", "enabled": True}, {"type": "give_up"}]
    current = copy.deepcopy(initial)
    for number, action in enumerate(steps, 1):
        pre_obs = copy.deepcopy(current)
        current = copy.deepcopy(current)
        current["tick"] += 1
        if number == 2:
            current["event"] = None
            current["choice_box_open"] = False
        elif number == 3:
            current["economy"]["systems"][0]["current_max_power"] = 2
            current["player_ship"]["resources"]["scrap"] = 70
        elif number == 4:
            current["economy"]["reactor"]["current_max_power"] = 11
            current["player_ship"]["resources"]["scrap"] = 20
        elif number in (5, 6):
            current["economy"]["fuel_recovery"].update(waiting=number == 5, can_wait=number != 5)
        elif number == 7:
            current["economy"]["fuel_recovery"]["distress_on"] = True
        current["action_feedback"] = [{"action_index": 1, **action, "status": "applied",
            **({"selected_choice": 7} if number == 2 else {})}] if action and action["type"] != "give_up" else []
        rows.append({"kind": "step", "i": number, "actions": [action] if action else [], "obs": current,
                     "pre_obs": pre_obs, "decision_obs": copy.deepcopy(pre_obs),
                     "model": {"provider": "codex", "model": "gpt-6.1-sol", "latency_seconds": 0.25, "usage": None}})
    rows.append({"kind": "end", "obs": None, "actions": [], "status": "completed", "reason": "gave_up", "setup_verified": True})
    path = tmp_path / "GAME-s1.jsonl"
    def save():
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    save()
    return tmp_path, rows, save


def test_complete_recorded_native_and_feedback_evidence_is_verified(trial):
    directory, _, _ = trial
    result = verify_codex_trial_v4(directory)
    assert result["errors"] == result["limitations"] == []
    assert result["validation_status"] == "verified" and result["valid_for_model_comparison"] is True
    assert result["last_score"] == 10 and result["final_state"]["victory"] is False
    assert result["terminal_record"]["reason"] == "gave_up" and result["report_complete"] is True
    assert result["client_binary_hash_verified"] is True and result["client_binary_source"] == "archive"
    assert all(result["runtime_hash_matches"].values())
    assert all(counts["applied"] == 1 for counts in result["action_feedback"].values())


@pytest.mark.parametrize("missing", ["runtime", "feedback", "cost", "latency", "terminal", "client"])
def test_missing_proof_is_inconclusive_and_not_comparable(trial, missing):
    directory, rows, save = trial
    if missing == "runtime":
        (directory / "runtime" / "ftl_agent_v5.md").unlink()
    elif missing == "feedback":
        rows[6]["obs"]["action_feedback"] = []
    elif missing == "cost":
        del rows[4]["pre_obs"]["economy"]["systems"][0]["next_upgrade_cost"]
    elif missing == "latency":
        del rows[2]["model"]["latency_seconds"]
    elif missing == "terminal":
        rows.pop()
    else:
        (directory / "client-metadata.json").unlink()
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "inconclusive"
    assert result["valid_for_model_comparison"] is False and result["limitations"]


@pytest.mark.parametrize("bad", ["model", "score", "hostile_move", "disabled_event", "runtime", "upgrade", "fuel"])
def test_contradictory_contract_or_applied_guard_evidence_is_invalid(trial, bad):
    directory, rows, save = trial
    if bad == "model":
        rows[2]["model"]["model"] = "wrong-model"
    elif bad == "score":
        rows[2]["obs"]["ftl_score"] = 999
    elif bad == "hostile_move":
        rows[2]["pre_obs"]["player_ship"]["crew"][0]["controllable"] = False
    elif bad == "disabled_event":
        rows[3]["actions"][0]["choice_index"] = 3
        rows[3]["obs"]["action_feedback"][0].update(choice_index=3, selected_choice=3)
    elif bad == "runtime":
        (directory / "runtime" / "Hyperspace.dll").write_bytes(b"changed")
    elif bad == "upgrade":
        rows[4]["pre_obs"]["player_ship"]["resources"]["scrap"] = 0
    else:
        rows[8]["actions"][0]["enabled"] = "true"
        rows[8]["obs"]["action_feedback"][0]["enabled"] = "true"
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "invalid"
    assert result["valid_for_model_comparison"] is False and result["errors"]


def test_predecision_pending_delay_does_not_falsely_prove_illegal_dispatch(trial):
    directory, rows, save = trial
    rows[3]["pre_obs"]["event"]["open_time"] = 0.1
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "inconclusive"
    assert result["errors"] == []
    assert any("dispatch-time UI timer" in gap for gap in result["limitations"])


def test_unexercised_action_families_are_coverage_not_automatic_disqualification(trial):
    directory, rows, save = trial
    for row in rows:
        if row.get("kind") == "step" and row.get("actions") and row["actions"][0]["type"] != "give_up":
            row["actions"] = []
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "verified"
    assert len(result["unexercised_action_families"]) == 6
    assert result["limitations"] == []


def test_rejected_disabled_choice_preserves_honest_feedback_counts(trial):
    directory, rows, save = trial
    rows[3]["actions"][0]["choice_index"] = 3
    rows[3]["obs"]["action_feedback"][0].update(choice_index=3, status="rejected", reason="choice_disabled")
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "verified"
    assert result["action_feedback"]["choose_event"]["rejected"] == 1
    assert result["action_feedback"]["choose_event"]["applied"] == 0


def test_ack_timeout_retained_feedback_is_inconclusive(trial):
    directory, rows, save = trial
    rows[6]["kind"] = "step_timeout"
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "inconclusive"
    assert result["action_feedback"]["wait_for_fuel"]["unproven"] == 1


def test_misleading_disabled_flag_is_an_observation_contract_violation(trial):
    directory, rows, save = trial
    rows[1]["obs"]["event"]["choices"][0]["disabled"] = False
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "invalid"
    assert any("choice 3.disabled" in error for error in result["errors"])


def test_malformed_nested_artifact_does_not_claim_validity_or_crash(trial):
    directory, _, _ = trial
    manifest = json.loads((directory / "run.json").read_text())
    manifest["runtime"] = ["invalid nested schema"]
    (directory / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "inconclusive" and result["valid_for_model_comparison"] is False


@pytest.mark.parametrize("control", ["upgrade", "fuel"])
def test_dynamic_gui_precontext_mismatch_is_unproven_not_illegal(trial, control):
    directory, rows, save = trial
    if control == "upgrade":
        rows[4]["pre_obs"]["economy"]["upgrade_available"] = False
    else:
        rows[6]["pre_obs"]["economy"]["fuel_recovery"].update(waiting=True, can_wait=False)
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "inconclusive"
    assert result["errors"] == []
    assert any("dispatch-time GUI legality" in gap for gap in result["limitations"])


def test_fresh_pre_dispatch_snapshot_overrides_stale_prior_and_model_input(trial):
    directory, rows, save = trial
    rows[2]["obs"]["event"]["choices"][1].update(native_type=1, disabled=True, enabled=False, available=False)
    rows[3]["decision_obs"] = copy.deepcopy(rows[2]["obs"])
    rows[5]["obs"]["economy"]["fuel_recovery"].update(waiting=True, can_wait=False)
    rows[6]["decision_obs"] = copy.deepcopy(rows[5]["obs"])
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "verified"
    assert result["errors"] == result["limitations"] == []


def test_legacy_stale_prior_is_context_only_and_never_illegality_proof(trial):
    directory, rows, save = trial
    del rows[3]["pre_obs"]
    rows[2]["obs"]["event"]["choices"][1].update(native_type=1, disabled=True, enabled=False, available=False)
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "inconclusive"
    assert result["errors"] == []
    assert any("previous result may be stale" in gap for gap in result["limitations"])


def test_missing_actual_model_input_is_inconclusive(trial):
    directory, rows, save = trial
    del rows[3]["decision_obs"]
    save()
    result = verify_codex_trial_v4(directory)
    assert result["validation_status"] == "inconclusive"
    assert any("actual model-input observation unavailable" in gap for gap in result["limitations"])


@pytest.fixture
def trial_v5(trial):
    directory, rows, save = trial
    manifest = json.loads((directory / "run.json").read_text())
    for metadata in (manifest, rows[0]["meta"]):
        metadata.update(runner_version="v5", ruleset="v5", routing_contract="native-sector-neighbors-v1")
    (directory / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    for row in rows:
        for name in ("obs", "pre_obs", "decision_obs"):
            snapshot = row.get(name)
            if isinstance(snapshot, dict):
                snapshot["capabilities"]["sector_navigation"] = True
                snapshot["economy"]["sector_navigation_version"] = 1
    route = copy.deepcopy(rows[-2])
    route.update(i=8, actions=[{"type": "leave_sector"}])
    route["pre_obs"]["map"].update(sector=0, at_exit=True)
    route["pre_obs"]["player_ship"]["resources"]["fuel"] = 1
    route["decision_obs"] = copy.deepcopy(route["pre_obs"])
    route["obs"]["map"].update(sector=1, at_exit=False)
    route["obs"]["action_feedback"] = [{"action_index": 1, "type": "leave_sector", "status": "applied"}]
    rows.insert(-2, route)
    rows[-2]["i"] = 9
    rows[-2]["obs"]["map"]["sector"] = 1
    rows[-2]["pre_obs"] = copy.deepcopy(route["obs"])
    rows[-2]["decision_obs"] = copy.deepcopy(route["obs"])
    save()
    return directory, rows, save


def test_v5_route_requires_native_identity_and_observed_transition(trial_v5):
    directory, _, _ = trial_v5
    result = verify_codex_trial_v5(directory)
    assert result["validation_status"] == "verified"
    assert result["routing_contract"] == "native-sector-neighbors-v1"
    assert result["action_feedback"]["leave_sector"]["transitions_confirmed"] == 1
    assert result["errors"] == result["limitations"] == []
    assert verify_codex_trial_v4(directory)["validation_status"] == "invalid"


@pytest.mark.parametrize("missing", ["capability", "marker", "feedback", "advance"])
def test_v5_route_cannot_be_claimed_from_old_binding_or_unproved_transition(trial_v5, missing):
    directory, rows, save = trial_v5
    if missing == "capability":
        rows[1]["obs"]["capabilities"]["sector_navigation"] = False
    elif missing == "marker":
        del rows[1]["obs"]["economy"]["sector_navigation_version"]
    elif missing == "feedback":
        rows[-3]["obs"]["action_feedback"] = []
    else:
        rows[-3]["obs"]["map"]["sector"] = rows[-2]["obs"]["map"]["sector"] = 0
    save()
    result = verify_codex_trial_v5(directory)
    assert result["validation_status"] == ("invalid" if missing == "capability" else "inconclusive")
    assert result["valid_for_model_comparison"] is False


def test_v5_native_route_refusal_is_honest_feedback_not_a_claimed_transition(trial_v5):
    directory, rows, save = trial_v5
    rows[-3]["obs"]["action_feedback"][0].update(status="rejected", reason="native_sector_route_refused")
    rows[-3]["obs"]["map"]["sector"] = rows[-2]["obs"]["map"]["sector"] = 0
    save()
    result = verify_codex_trial_v5(directory)
    assert result["validation_status"] == "verified"
    route = result["action_feedback"]["leave_sector"]
    assert route["rejected"] == 1 and route["applied"] == 0
    assert route.get("transitions_confirmed", 0) == 0


@pytest.mark.parametrize("destroyed", [True, False, None])
def test_v5_route_uses_native_destroyed_flag_for_lingering_enemy_objects(trial_v5, destroyed):
    directory, rows, save = trial_v5
    enemy = {"hull": {"current": 0}, "targetable": False}
    if destroyed is not None:
        enemy["destroyed"] = destroyed
    rows[-3]["pre_obs"]["enemy_ship"] = enemy
    save()
    result = verify_codex_trial_v5(directory)
    assert result["errors"] == []
    assert result["validation_status"] == ("verified" if destroyed is True else "inconclusive")
    assert result["valid_for_model_comparison"] is (destroyed is True)


@pytest.fixture
def trial_v6(trial_v5):
    directory, rows, save = trial_v5
    manifest = json.loads((directory / "run.json").read_text())
    patch = directory / "runtime" / "native-benchmark.patch"
    patch.write_bytes(b"native beacon readiness fixture patch")
    manifest["runtime"]["native_build"]["patch_sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
    for metadata in (manifest, rows[0]["meta"]):
        metadata.update(runner_version="v6", ruleset="v6", beacon_contract="native-beacon-readiness-v1")
    (directory / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    for row in rows:
        for name in ("obs", "pre_obs", "decision_obs"):
            snapshot = row.get(name)
            if isinstance(snapshot, dict):
                snapshot["capabilities"]["beacon_navigation"] = True
                snapshot["economy"].update(beacon_navigation_version=1, navigation={
                    "can_jump": True, "enemy_defeat_pending": False, "drive_current": 85, "drive_max": 85})
    jump = copy.deepcopy(rows[-2])
    jump.update(i=9, actions=[{"type": "jump", "beacon_index": 4}])
    jump["pre_obs"]["map"].update(current_pos={"x": 10, "y": 0}, connected_beacons=[{"index": 4}])
    jump["decision_obs"] = copy.deepcopy(jump["pre_obs"])
    jump["obs"]["map"]["current_pos"] = {"x": 20, "y": 0}
    jump["obs"]["action_feedback"] = [{"action_index": 1, "type": "jump", "beacon_index": 4, "status": "applied"}]
    jump["obs"]["economy"]["navigation"].update(can_jump=False, drive_current=0)
    rows.insert(-2, jump)
    rows[-2]["i"] = 10
    rows[-2]["obs"]["map"]["current_pos"] = {"x": 20, "y": 0}
    rows[-2]["pre_obs"] = copy.deepcopy(jump["obs"])
    rows[-2]["decision_obs"] = copy.deepcopy(jump["obs"])
    save()
    return directory, rows, save


def test_v6_records_actual_ready_guard_feedback_and_beacon_transition(trial_v6):
    directory, _, _ = trial_v6
    result = verify_codex_trial_v6(directory)
    assert result["validation_status"] == "verified"
    assert result["beacon_contract"] == "native-beacon-readiness-v1"
    assert result["action_feedback"]["jump"]["transitions_confirmed"] == 1


@pytest.mark.parametrize("case", ["partial", "index", "feedback", "marker", "transition", "blocked", "pending"])
def test_v6_jump_proof_distinguishes_contradictions_missing_evidence_and_legal_pending(trial_v6, case):
    directory, rows, save = trial_v6
    jump = rows[-3]
    navigation = jump["pre_obs"]["economy"]["navigation"]
    if case == "partial":
        navigation["drive_current"] = 41
    elif case == "index":
        jump["obs"]["action_feedback"][0]["beacon_index"] = 99
    elif case == "feedback":
        jump["obs"]["action_feedback"] = []
    elif case == "marker":
        del rows[1]["obs"]["economy"]["beacon_navigation_version"]
    elif case == "transition":
        jump["obs"]["map"]["current_pos"] = {"x": 10, "y": 0}
    elif case == "blocked":
        navigation.update(can_jump=False, drive_current=41)
    else:
        navigation["enemy_defeat_pending"] = True
    save()
    result = verify_codex_trial_v6(directory)
    expected = "invalid" if case in ("partial", "index") else "verified" if case == "pending" else "inconclusive"
    assert result["validation_status"] == expected


def test_v6_second_jump_in_plan_can_be_truthfully_rejected_midwarp(trial_v6):
    directory, rows, save = trial_v6
    jump = rows[-3]
    jump["actions"].append({"type": "jump", "beacon_index": 4})
    jump["obs"]["action_feedback"].append({"action_index": 2, "type": "jump", "beacon_index": 4,
        "status": "rejected", "reason": "travel_pending"})
    save()
    result = verify_codex_trial_v6(directory)
    assert result["validation_status"] == "verified"
    assert result["action_feedback"]["jump"]["requested"] == 2
    assert result["action_feedback"]["jump"]["rejected"] == 1


@pytest.fixture
def trial_v7(trial_v6):
    directory, rows, save = trial_v6
    manifest = json.loads((directory / "run.json").read_text())
    for metadata in (manifest, rows[0]["meta"]):
        metadata.update(runner_version="v7", ruleset="v7", hostility_contract="native-enemy-hostility-v1")
    (directory / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    for row in rows:
        for name in ("obs", "pre_obs", "decision_obs"):
            snapshot = row.get(name)
            if isinstance(snapshot, dict):
                snapshot["capabilities"]["enemy_hostility"] = True
    fire = copy.deepcopy(rows[-2])
    fire.update(i=10, actions=[{"type": "fire_weapon", "weapon_slot": 2, "target_room_id": 7, "target_ship_id": 1}])
    for name in ("obs", "pre_obs", "decision_obs"):
        fire[name]["enemy_ship"] = {"hostile": True, "targetable": True, "destroyed": False,
                                    "hull": {"current": 4, "max": 15}, "rooms": [{"room_id": 7}]}
        fire[name]["player_ship"]["weapons"] = [{"slot": 2, "weapon_type": "LASER", "powered": True}]
    fire["obs"]["action_feedback"] = [{"action_index": 1, **fire["actions"][0], "status": "applied",
        "enemy_hostile": True, "enemy_targetable": True, "queued": True}]
    rows.insert(-2, fire)
    rows[-2]["i"] = 11
    rows[-2]["pre_obs"] = copy.deepcopy(fire["obs"])
    rows[-2]["decision_obs"] = copy.deepcopy(fire["obs"])
    rows[-2]["obs"] = copy.deepcopy(fire["obs"])
    rows[-2]["obs"]["action_feedback"] = []
    save()
    return directory, rows, save


def test_v7_verifies_hostility_guard_identity_and_queued_fire_without_claiming_a_hit(trial_v7):
    directory, rows, _ = trial_v7
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "verified"
    assert result["hostility_contract"] == "native-enemy-hostility-v1"
    assert result["action_feedback"]["fire_weapon"]["applied"] == 1
    assert rows[-3]["obs"]["enemy_ship"]["hull"] == rows[-3]["pre_obs"]["enemy_ship"]["hull"]
    assert result["last_score"] == 10 and result["final_state"]["victory"] is False


@pytest.mark.parametrize("missing", ["contract", "capability", "hostility", "feedback"])
def test_v7_missing_hostility_contract_or_fire_proof_cannot_claim_comparability(trial_v7, missing):
    directory, rows, save = trial_v7
    if missing == "contract":
        manifest = json.loads((directory / "run.json").read_text())
        del manifest["hostility_contract"]
        (directory / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    elif missing == "capability":
        rows[1]["obs"]["capabilities"]["enemy_hostility"] = False
    elif missing == "hostility":
        rows[-3]["pre_obs"]["enemy_ship"].pop("hostile")
        rows[-3]["pre_obs"]["enemy_ship"]["targetable"] = False
    else:
        rows[-3]["obs"]["action_feedback"] = []
    save()
    result = verify_codex_trial_v7(directory)
    assert result["valid_for_model_comparison"] is False
    assert result["validation_status"] == ("invalid" if missing == "capability" else "inconclusive")


@pytest.mark.parametrize("case", ["friendly_applied", "friendly_targetable", "slot", "ship", "room"])
def test_v7_rejects_friendly_fire_claims_and_mismatched_feedback(trial_v7, case):
    directory, rows, save = trial_v7
    fire = rows[-3]
    if case == "friendly_applied":
        fire["pre_obs"]["enemy_ship"].update(hostile=False, targetable=False)
        fire["obs"]["action_feedback"][0].update(enemy_hostile=False, enemy_targetable=False)
    elif case == "friendly_targetable":
        fire["obs"]["enemy_ship"]["hostile"] = False
    else:
        field = {"slot": "weapon_slot", "ship": "target_ship_id", "room": "target_room_id"}[case]
        fire["obs"]["action_feedback"][0][field] = 99
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "invalid"
    assert result["errors"]


@pytest.mark.parametrize("reason,hostile", [("enemy_not_hostile", False), ("enemy_hostility_unknown", None)])
def test_v7_truthful_fire_refusal_preserves_friendly_pointer_and_native_score(trial_v7, reason, hostile):
    directory, rows, save = trial_v7
    fire = rows[-3]
    # All actual native result snapshots remain known friendly; an unknown precontext only
    # needs a truthful refusal, not a claim that firing was legal or dispatched.
    for row in rows[-3:-1]:
        for name in ("obs", "pre_obs", "decision_obs"):
            row[name]["enemy_ship"].update(hostile=False, targetable=False)
    if hostile is None:
        fire["pre_obs"]["enemy_ship"].pop("hostile")
    fire["obs"]["action_feedback"][0].update(status="rejected", reason=reason, queued=False)
    save()
    result = verify_codex_trial_v7(directory)
    # Unknown observed input is disclosed even though the safe dispatch refused it.
    assert result["validation_status"] == ("verified" if hostile is False else "inconclusive")
    assert result["errors"] == []
    assert result["last_score"] == 10
    assert result["action_feedback"]["fire_weapon"]["rejected"] == 1


@pytest.mark.parametrize("kind,weapon_type,expected", [
    ("fire_weapon", "BOMB", "verified"), ("fire_weapon", "LASER", "invalid"),
    ("fire_beam", "BEAM", "invalid")])
def test_v7_self_target_uses_native_bomb_constraint_independent_of_enemy_hostility(trial_v7, kind, weapon_type, expected):
    directory, rows, save = trial_v7
    fire = rows[-3]
    action = {"type": kind, "weapon_slot": 2, "target_ship_id": 0,
              **({"target_room_id": 7} if kind == "fire_weapon" else {"room_a": 7, "room_b": 8})}
    fire["actions"] = [action]
    fire["obs"]["action_feedback"] = [{"action_index": 1, **action, "status": "applied", "queued": True}]
    for row in rows[-3:-1]:
        for name in ("obs", "pre_obs", "decision_obs"):
            row[name]["enemy_ship"].update(hostile=False, targetable=False)
            row[name]["player_ship"]["weapons"][0]["weapon_type"] = weapon_type
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == expected


def test_v7_friendly_retained_ship_allows_native_sector_transition_proof(trial_v7):
    directory, rows, save = trial_v7
    route = next(row for row in rows if row.get("actions") == [{"type": "leave_sector"}])
    route["pre_obs"]["enemy_ship"] = {"hostile": False, "targetable": False,
                                      "destroyed": False, "hull": {"current": 4}}
    save()
    assert verify_codex_trial_v7(directory)["validation_status"] == "verified"


@pytest.mark.parametrize("field", ["enemy_hostile", "enemy_targetable", "queued"])
@pytest.mark.parametrize("value", [False, None])
def test_v7_dispatch_proof_missing_is_inconclusive_and_false_acceptance_is_invalid(trial_v7, field, value):
    directory, rows, save = trial_v7
    feedback = rows[-3]["obs"]["action_feedback"][0]
    if value is None:
        feedback.pop(field)
    else:
        feedback[field] = value
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == ("invalid" if value is False else "inconclusive")


def test_v7_event_then_fire_uses_guard_dispatch_facts_after_prior_event_changes(trial_v7):
    directory, rows, save = trial_v7
    fire = rows[-3]
    fire["pre_obs"] = copy.deepcopy(rows[2]["pre_obs"])
    fire["pre_obs"]["enemy_ship"] = {"hostile": False, "targetable": False, "hull": {"current": 4}}
    fire["decision_obs"] = copy.deepcopy(fire["pre_obs"])
    fire["actions"].insert(0, {"type": "choose_event", "choice_index": 7})
    fire["obs"]["action_feedback"][0]["action_index"] = 2
    fire["obs"]["action_feedback"].insert(0, {"action_index": 1, "type": "choose_event", "choice_index": 7,
        "status": "applied", "selected_choice": 7})
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "verified"
    assert result["action_feedback"]["fire_weapon"]["applied"] == 1
    assert result["errors"] == result["limitations"] == []


@pytest.fixture
def distinct_upgrade_batch(trial_v7):
    directory, rows, save = trial_v7
    system, reactor = rows[4], rows[5]
    system["actions"].extend([{"type": "upgrade_reactor"},
                              {"type": "set_system_power", "system_id": 2, "level": 1}])
    system["obs"] = copy.deepcopy(reactor["obs"])
    system["obs"]["action_feedback"] = [
        {"action_index": 1, "type": "upgrade_system", "system_id": 2, "status": "applied"},
        {"action_index": 2, "type": "upgrade_reactor", "status": "applied"},
    ]
    rows.pop(5)
    save()
    return directory, rows, save


def test_distinct_system_and_reactor_batch_reconciles_native_prices_levels_and_scrap(distinct_upgrade_batch):
    directory, _, _ = distinct_upgrade_batch
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "verified"
    assert result["action_feedback"]["upgrade_system"]["applied"] == 1
    assert result["action_feedback"]["upgrade_reactor"]["applied"] == 1
    assert result["errors"] == result["limitations"] == []


def test_distinct_batch_checks_remaining_scrap_at_each_accepted_purchase(distinct_upgrade_batch):
    directory, rows, save = distinct_upgrade_batch
    # Each purchase is individually affordable against 70; the reactor is not affordable
    # after the accepted 30-scrap system upgrade. Reusing pre-scrap would miss this.
    rows[4]["pre_obs"]["player_ship"]["resources"]["scrap"] = 70
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "invalid"
    assert any("unaffordable native upgrade" in error for error in result["errors"])


def test_repeated_system_upgrade_does_not_reuse_its_initial_native_next_price(distinct_upgrade_batch):
    directory, rows, save = distinct_upgrade_batch
    batch = rows[4]
    batch["actions"][1] = {"type": "upgrade_system", "system_id": 2}
    batch["obs"]["action_feedback"][1] = {"action_index": 2, "type": "upgrade_system", "system_id": 2, "status": "applied"}
    batch["obs"]["economy"]["systems"][0]["current_max_power"] = 3
    batch["obs"]["economy"]["reactor"]["current_max_power"] = 10
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "inconclusive" and result["errors"] == []
    assert any("intermediate native next price" in gap for gap in result["limitations"])


@pytest.mark.parametrize("missing", ["price", "feedback", "post_scrap", "pre_level", "post_level", "availability"])
def test_partial_distinct_batch_data_remains_inconclusive(distinct_upgrade_batch, missing):
    directory, rows, save = distinct_upgrade_batch
    batch = rows[4]
    if missing == "price":
        batch["pre_obs"]["economy"]["reactor"].pop("next_upgrade_cost")
    elif missing == "feedback":
        batch["obs"]["action_feedback"].pop()
    elif missing == "post_scrap":
        batch["obs"]["player_ship"]["resources"].pop("scrap")
    elif missing == "availability":
        batch["pre_obs"]["economy"]["reactor"]["can_upgrade"] = False
    else:
        state = "pre_obs" if missing == "pre_level" else "obs"
        batch[state]["economy"]["reactor"].pop("current_max_power")
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "inconclusive" and result["errors"] == []


@pytest.mark.parametrize("case", ["post_scrap_mismatch", "extra_level", "store", "event", "timeout"])
def test_distinct_upgrade_batch_cannot_claim_unobserved_context_or_transactions(distinct_upgrade_batch, case):
    directory, rows, save = distinct_upgrade_batch
    batch = rows[4]
    if case == "post_scrap_mismatch":
        batch["obs"]["player_ship"]["resources"]["scrap"] += 1
    elif case == "extra_level":
        batch["obs"]["economy"]["reactor"]["current_max_power"] += 1
    elif case == "timeout":
        batch["kind"] = "step_timeout"
    else:
        batch["actions"].insert(1, {"type": "store_buy", "store_index": 0} if case == "store" else {"type": "choose_event", "choice_index": 7})
        batch["obs"]["action_feedback"][1]["action_index"] = 3
        if case == "event":
            batch["obs"]["action_feedback"].insert(1, {"action_index": 2, "type": "choose_event",
                "choice_index": 7, "selected_choice": 7, "status": "rejected", "reason": "event_closed"})
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "inconclusive" and result["errors"] == []


def test_distinct_batch_counts_rejected_upgrade_as_unchanged_capacity_and_no_purchase(distinct_upgrade_batch):
    directory, rows, save = distinct_upgrade_batch
    batch = rows[4]
    batch["obs"]["action_feedback"][0].update(status="rejected", reason="native_upgrade_refused")
    batch["obs"]["economy"]["systems"][0]["current_max_power"] = 1
    batch["obs"]["player_ship"]["resources"]["scrap"] = 50
    save()
    result = verify_codex_trial_v7(directory)
    assert result["validation_status"] == "verified"
    assert result["action_feedback"]["upgrade_system"]["rejected"] == 1
    assert result["action_feedback"]["upgrade_reactor"]["applied"] == 1
