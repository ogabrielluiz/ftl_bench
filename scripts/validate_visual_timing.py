"""Protected no-model clock-v2 probe: identical inputs under varied wall delays.

Run only with the accepted fixed-step native build. Three disposable fixtures
per selected challenge receive the same ordinary visual inputs with delays of
0, 0.35 and 1.2 seconds. Exact native states, not screenshots or input intent,
establish timing invariance. All saves remain protected by the challenge runner.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

import validate_visual_challenges as challenges
from run_visual import visual_record

ROOT = challenges.ROOT
DELAYS = (0.0, 0.35, 1.2)
REPAIR_CASES = (
    ("neutral-zero", ({"type": "move", "x": 5, "y": 5},), 0),
    ("oxygen-off-zero", ({"type": "key", "key": "f", "modifiers": ["shift"]},), 0),
    ("first-fixed-advance", (), 120),
    ("second-fixed-advance", (), 120),
    ("oxygen-on-zero", ({"type": "key", "key": "f", "modifiers": []},), 0),
    ("final-fixed-advance", (), 120),
)
NEUTRAL_CASES = (("neutral-zero", ({"type": "move", "x": 5, "y": 5},), 0),) + tuple(
    (f"fixed-advance-{index}", (), 120) for index in range(1, 13))


def probe_cases(challenge):
    return REPAIR_CASES if challenge == "repair-charge-escape" else NEUTRAL_CASES


def signature_hash(raw):
    return challenges.digest(json.dumps(challenges.gameplay_signature(raw), sort_keys=True,
        separators=(",", ":")).encode())


def fire_progression(raw):
    """Read only crisis state: drive/weapon charging alone cannot pass fire timing."""
    player = challenges._ship(raw)
    return {"rooms": player.get("rooms"), "fires": player.get("fires"),
        "oxygen_pct": player.get("oxygen_pct"), "crew_health": [
            {key: crew.get(key) for key in ("id", "dead", "health_current", "health_max")}
            for crew in player.get("crew", [])],
        "native_system_health": raw.get("visual_challenge_system_health")}


def fire_progression_proof(before, after):
    """Require a local, complete native crisis change rather than ambient charging."""
    old_rows = challenges._ship(before).get("rooms", [])
    new_rows = challenges._ship(after).get("rooms", [])
    initial_rooms = {room.get("room_id"): room for room in old_rows}
    final_rooms = {room.get("room_id"): room for room in new_rows}
    topology_complete = bool(initial_rooms) and set(initial_rooms) == set(final_rooms) and all(
        type(room_id) is int for room_id in initial_rooms) and len(old_rows) == len(initial_rooms) and len(new_rows) == len(final_rooms)
    complete = challenges._fires(before) is not None and challenges._fires(after) is not None
    burning = [room_id for room_id, room in initial_rooms.items() if type(room.get("fires")) is int and room["fires"] > 0]
    localized_oxygen_drop = bool(burning) and all(room_id in final_rooms for room_id in burning) and any(
        all(challenges._number(row.get("oxygen")) and 0 <= row["oxygen"] <= 100
            for row in (initial_rooms[room_id], final_rooms[room_id]))
        and final_rooms[room_id]["oxygen"] < initial_rooms[room_id]["oxygen"] for room_id in burning if room_id in final_rooms)
    old_health = challenges._system_health(before, 2)
    new_health = challenges._system_health(after, 2)
    health_complete = all(type(row.get(key)) is int for row in (old_health, new_health)
        for key in ("health_current", "health_max")) and all(
        0 <= row["health_current"] <= row["health_max"] and row["health_max"] > 0 for row in (old_health, new_health))
    health_complete = health_complete and old_health["health_max"] == new_health["health_max"]
    system_damaged = health_complete and new_health["health_current"] < old_health["health_current"]
    count_changed = complete and any(initial_rooms.get(room_id, {}).get("fires") != final_rooms.get(room_id, {}).get("fires")
        for room_id in set(initial_rooms) | set(final_rooms))
    checks = {"same_complete_room_topology": topology_complete,
        "exhaustive_fire_counts": complete, "initial_fire_present": bool(burning),
        "oxygen_health_available": health_complete,
        "localized_native_crisis_changed": count_changed or localized_oxygen_drop or system_damaged}
    return {"passed": all(checks.values()), "checks": checks,
        "before": fire_progression(before), "after": fire_progression(after)}


def idle_proof(before, observed):
    return {"passed": observed.get("paused") is True and before.get("paused") is True
        and challenges.gameplay_signature(before) == challenges.gameplay_signature(observed)
        and challenges._counter(before) == challenges._counter(observed)
        and challenges.time_contract_proof(observed)["passed"],
        "counter_before": challenges._counter(before), "counter_after": challenges._counter(observed),
        "gameplay_before_sha256": signature_hash(before), "gameplay_after_sha256": signature_hash(observed),
        "time_contract_proof": challenges.time_contract_proof(observed)}


def run_probe(session, transport, recorder, frame, output, args):
    initial = frame.observation.raw
    kind = args.challenge
    cases = probe_cases(kind)
    evidence = []
    observed_effects = {}
    checks = {"initial_clock_v2": challenges.time_contract_proof(initial)["passed"]}
    if kind == "repair-charge-escape":
        checks["oxygen_power_initially_one"] = challenges._system(initial, 2).get("power") == 1
    def save():
        report = {"probe": "fixed-step-wall-delay-v1", "model_calls": 0,
            "challenge": kind, "delay_seconds": args.probe_delay_seconds, "time_contract": challenges.TIME_CONTRACT,
            "initial_gameplay_sha256": signature_hash(initial),
            "passed": all(checks.values()), "checks": checks, "steps": evidence,
            "observed_effects": observed_effects,
            "scope": "Native progression and equality along these exact inputs; internal RNG stream equality is not measured"}
        challenges.write_json(output / "timing-proof.json", report)
        return report
    save()
    for label, packet, requested in cases:
        before = frame
        wait_started = time.monotonic()
        if args.probe_delay_seconds:
            time.sleep(args.probe_delay_seconds)
        # Reading observation files alone can return the preceding cached capture.
        # Request a new native zero-frame snapshot to measure actual idle state.
        fresh = transport.step(before, [], 0)
        observed = fresh.observation.raw
        recorder.record("step", [], fresh.observation, thought=label + "-idle-capture",
            pre_obs=before.observation, visual=visual_record("image", before, fresh, [], 0))
        frozen = idle_proof(before.observation.raw, observed)
        frozen["fresh_capture_identity"] = (fresh.reference.get("capture_id") != before.reference.get("capture_id")
            and fresh.reference.get("frame_id") != before.reference.get("frame_id"))
        frozen["before_image"], frozen["after_image"] = before.reference, fresh.reference
        frozen["passed"] = frozen["passed"] and frozen["fresh_capture_identity"]
        frozen["elapsed_wall_seconds"] = time.monotonic() - wait_started
        checks[label + "_idle_frozen"] = frozen["passed"]
        if not frozen["passed"]:
            save()
            raise RuntimeError("World changed during deliberate wall delay: " + label)
        before = fresh
        actions = [dict(action) for action in packet]
        frame = transport.step(before, actions, requested)
        raw = frame.observation.raw
        record = visual_record("image", before, frame, actions, requested)
        recorder.record("step", actions, frame.observation, thought=label,
            pre_obs=before.observation, visual=record)
        native = raw.get("visual") or {}
        delta = challenges._counter(raw) - challenges._counter(before.observation.raw)
        feedback = native.get("input_feedback") or []
        delivered = len(feedback) == len(actions) and all(item.get("status") == "delivered"
            and item.get("index") == index and item.get("type") == action["type"]
            for index, (action, item) in enumerate(zip(actions, feedback)))
        checks[label + "_clock_v2"] = challenges.time_contract_proof(raw)["passed"]
        checks[label + "_native_budget_exact"] = native.get("actual_frames") == requested and delta == requested
        checks[label + "_inputs_delivered"] = delivered
        if requested == 0:
            checks[label + "_zero_counter"] = delta == 0
        if label == "neutral-zero":
            checks["neutral_zero_gameplay_unchanged"] = challenges.gameplay_signature(raw) == challenges.gameplay_signature(initial)
        if label == "oxygen-off-zero":
            checks["ordinary_key_removed_oxygen_power"] = challenges._system(raw, 2).get("power") == 0
        if label == "oxygen-on-zero":
            checks["ordinary_key_restored_oxygen_power"] = challenges._system(raw, 2).get("power") == 1
        evidence.append({"label": label, "actions": actions, "requested_frames": requested,
            "actual_frames": native.get("actual_frames"), "native_counter_delta": delta,
            "nominal_simulated_seconds": {"numerator": delta, "denominator": 60},
            "idle_proof": frozen, "before_image": before.reference, "after_image": frame.reference,
            "gameplay_signature": challenges.gameplay_signature(raw), "gameplay_sha256": signature_hash(raw)})
        save()
        if not all(checks.values()):
            raise RuntimeError("Native clock/input probe acceptance failed: " + label)
    if kind == "repair-charge-escape":
        drained = evidence[3]["gameplay_signature"]["player_ship"].get("oxygen_pct")
        before_oxygen = challenges._ship(initial).get("oxygen_pct")
        checks["ordinary_simulation_drained_oxygen"] = (challenges._number(before_oxygen)
            and challenges._number(drained) and 0 < drained < before_oxygen)
    elif kind == "combat":
        charge_history = [challenges.gameplay_signature(initial)] + [s["gameplay_signature"] for s in evidence]
        cycled = False
        for old, new in zip(charge_history, charge_history[1:]):
            previous = {w.get("slot"): w for w in (old.get("enemy_ship") or {}).get("weapons", [])}
            for weapon in (new.get("enemy_ship") or {}).get("weapons", []):
                prior = previous.get(weapon.get("slot")) or {}
                if challenges._number(prior.get("charge")) and challenges._number(weapon.get("charge")) and weapon["charge"] < prior["charge"]:
                    cycled = True
        checks["native_enemy_weapon_discharge_cycle_observed"] = cycled
        old_hull = (challenges._ship(initial).get("hull") or {}).get("current")
        new_hull = (challenges._ship(frame.observation.raw).get("hull") or {}).get("current")
        observed_effects["player_hull_damage_observed"] = (challenges._number(old_hull)
            and challenges._number(new_hull) and new_hull < old_hull)
        observed_effects["combat_scope"] = "Weapon cooldown cycle; impact damage evidence recorded separately, no RNG-stream equivalence claim"
    else:
        localized = fire_progression_proof(initial, frame.observation.raw)
        checks["native_fire_progression_observed"] = localized["passed"]
        challenges.write_json(output / "fire-progression-proof.json", localized)
    expected_updates = sum(case[2] for case in cases)
    checks["total_explicit_updates_exact"] = sum(step["native_counter_delta"] for step in evidence) == expected_updates
    report = save()
    if not report["passed"]:
        raise RuntimeError("Native probe did not demonstrate effective gameplay progression")
    return report


def compare_repeats(reports):
    kind = reports[0].get("challenge", "repair-charge-escape") if reports else "repair-charge-escape"
    cases = probe_cases(kind)
    checks = {"three_varied_wall_delays": len(reports) == 3 and tuple(r.get("delay_seconds") for r in reports) == DELAYS,
        "same_challenge": bool(reports) and all(r.get("challenge", "repair-charge-escape") == kind for r in reports),
        "all_native_probes_passed": bool(reports) and all(r.get("passed") is True for r in reports),
        "all_clock_v2_contracts_match": bool(reports) and all(r.get("time_contract") == challenges.TIME_CONTRACT for r in reports),
        "initial_native_states_identical": bool(reports) and len({r.get("initial_gameplay_sha256") for r in reports}) == 1,
        "all_fixed_cases_recorded": bool(reports) and all([s.get("label") for s in r.get("steps", [])] == [c[0] for c in cases] for r in reports)}
    checks["identical_explicit_input_sequence"] = bool(reports) and all(
        len(r.get("steps", [])) == len(cases) and all(
            step.get("actions") == list(packet) and step.get("requested_frames") == frames
            for step, (_, packet, frames) in zip(r["steps"], cases)) for r in reports)
    expected = [step.get("gameplay_sha256") for step in reports[0].get("steps", [])] if reports else []
    checks["every_native_step_identical"] = bool(expected) and all([s.get("gameplay_sha256") for s in r.get("steps", [])] == expected for r in reports)
    return {"passed": all(checks.values()), "checks": checks,
        "per_step_gameplay_sha256": expected,
        "limitations": ["Scoped identical-input challenge probe; this does not establish full-game determinism.",
                        "Observed native states and outcomes are compared; equality of the internal RNG stream is not measured.",
                        "Combat cooldown cycles establish weapon progression; impact damage is checked separately and may not occur on this neutral path.",
                        "Cosmetic crew names, screenshots, timestamps and cumulative counters may differ; gameplay values are compared exactly without rounding."]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    p.add_argument("--challenge", choices=("all", *challenges.TASKS), default="repair-charge-escape")
    args = p.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = (args.output or ROOT / "harness/runs/validation/visual-v1" / ("fixed-step-" + stamp)).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "timing-driver.py").write_bytes(Path(__file__).read_bytes())
    results, by_challenge = [], {}
    selected = list(challenges.TASKS) if args.challenge == "all" else [args.challenge]
    for kind in selected:
        reports = []
        for index, delay in enumerate(DELAYS, 1):
            trial = output / kind / f"repetition-{index:02d}" / kind
            trial_args = challenges.parser().parse_args(["--setup-only", "--challenge", kind])
            trial_args.probe_delay_seconds = delay
            result = challenges.run_trial(trial_args, kind, index, trial, None, None, scripted_probe=run_probe)
            results.append({"directory": str(trial), **result})
            path = trial / "timing-proof.json"
            if path.is_file():
                reports.append(json.loads(path.read_text(encoding="utf-8")))
            if result["outcome_category"] != "setup_verified":
                break
        by_challenge[kind] = compare_repeats(reports)
        if results[-1]["outcome_category"] != "setup_verified":
            break
    all_exact = set(by_challenge) == set(selected) and all(proof["passed"] for proof in by_challenge.values())
    cleanup = len(results) == 3 * len(selected) and all(r.get("save_restoration_verified") is True
        and r.get("production_source_unchanged") is True for r in results)
    report = {"validation_version": "fixed-step-live-acceptance-v1", "classification": "diagnostic_only",
        "model_calls": 0, "time_contract": challenges.TIME_CONTRACT,
        "fixed_step_acceptance": {"claimed": all_exact and cleanup,
            "visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60,
            "checked_cases": {kind: proof["checks"] for kind, proof in by_challenge.items()},
            "fixed_step_case_ids": [kind + ":" + case[0] for kind in selected for case in probe_cases(kind)],
            "checked_challenges": selected, "all_original_saves_restored": cleanup,
            "scope": "Only the listed challenge paths; an oxygen-only pass is not overall game repeatability"},
        "repeatability": by_challenge, "trials": results,
        "script_sha256": challenges.digest(Path(__file__).read_bytes())}
    challenges.write_json(output / "fixed-step-report.json", report)
    print(json.dumps({"fixed_step_acceptance": report["fixed_step_acceptance"], "artifacts": str(output)}), flush=True)
    return 0 if report["fixed_step_acceptance"]["claimed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
