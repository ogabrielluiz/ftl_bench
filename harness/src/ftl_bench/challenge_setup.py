"""Explicit opt-in setup session and fail-closed receipt validation.

Challenge prerequisite collection. No direct native state writes, and
no random reseeding after the fresh construction boundary.
"""
import copy
import json
import hashlib
from pathlib import Path
import struct
import time

from ftl_bench.session import AgentSession


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def counter(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise ValueError("Native counter must be a decimal string")


def receipt_proof(raw, *, require_visual=True):
    receipt = raw.get("deterministic_setup") or {}
    seed = receipt.get("native_seed") or {}
    creation = receipt.get("creation") or {}
    clock = receipt.get("clock") or {}
    handoff = receipt.get("handoff") or {}
    fixture = raw.get("visual_challenge_fixture") or {}
    factor_bits = struct.unpack("<I", struct.pack("<f", 16 / 60))[0]
    checks = {
        "explicit_setup_contract": receipt.get("contract") == "deterministic-setup-v1"
            and type(receipt.get("version")) is int and receipt["version"] == 1,
        "setup_completed_without_error": receipt.get("phase") in (("visual",) if require_visual else ("ready", "visual"))
            and not receipt.get("error") and not receipt.get("pending"),
        "seed_one": type(receipt.get("seed")) is int and receipt["seed"] == 1
            and type(seed.get("seed")) is int and seed["seed"] == 1,
        "native_seed_contract": seed.get("contract") == "fresh-start-seed-v3"
            and type(seed.get("contract_version")) is int and seed["contract_version"] == 3
            and seed.get("boundary") == "ShipBuilder::Open.before_super",
        "fresh_native_epoch_and_thread": type(seed.get("epoch")) is int and seed["epoch"] == 1
            and type(seed.get("seed_thread_id")) is int and seed["seed_thread_id"] > 0,
        "both_generators_initialized_once": seed.get("applied") is True
            and seed.get("pending") is False and seed.get("failed") is False and not seed.get("error")
            and type(seed.get("native_seed_applications")) is int and seed["native_seed_applications"] == 1
            and type(seed.get("c_runtime_seed_applications")) is int and seed["c_runtime_seed_applications"] == 1,
        "construction_followed_seed": all(type(seed.get(k)) is int and seed[k] == 0 for k in (
            "unclassified_names_before_arm", "unclassified_names_before_seed", "intervening_names_after_arm",
            "ship_inits_before_arm", "ship_inits_before_seed"))
            and type(seed.get("names_during_open")) is int and seed["names_during_open"] >= 3,
        "startup_utility_lookup_classified": all(type(seed.get(k)) is int and seed[k] == 1 for k in (
            "names_before_arm", "names_before_seed", "utility_name_calls", "utility_lookup_calls",
            "utility_lookup_completed")) and seed.get("utility_lookup_valid") is True
            and seed.get("utility_name_provenance") == "StatBoostManager::CreateDummyCrew.GetCrewBlueprint(human)"
            and type(seed.get("utility_name")) is str and bool(seed["utility_name"])
            and type(seed.get("utility_thread_id")) is int and seed["utility_thread_id"] == seed.get("seed_thread_id"),
        "factory_empty_at_clean_start": all(type(seed.get(k)) is int and seed[k] == 0
            for k in (f"factory_{kind}_before_{stage}" for kind in ("crew", "lost", "player", "enemy", "clone")
                for stage in ("arm", "reset"))),
        "orphan_name_reservation_reset": all(type(seed.get(k)) is int and seed[k] == 1 for k in (
            "reservations_before_arm", "reservations_before_reset", "reservation_reset_applications"))
            and type(seed.get("reservations_after_reset")) is int and seed["reservations_after_reset"] == 0
            and seed.get("reservation_names_before_reset") == [seed.get("utility_name")]
            and seed.get("reservation_reset_verified") is True
            and type(seed.get("reservation_reset_thread_id")) is int
            and seed["reservation_reset_thread_id"] == seed.get("seed_thread_id"),
        "construction_clock_controlled": seed.get("constructor_timing_controlled") is True
            and seed.get("clock_owned_at_arm") is True and seed.get("clock_owned_at_boundary") is True
            and seed.get("clock_update_permitted_at_boundary") is False
            and seed.get("construction_scope_active") is False,
        "construction_fixed_factor": seed.get("construction_fixed_step_numerator") == 1
            and seed.get("construction_fixed_step_denominator") == 60
            and seed.get("base_speed_factor_bits_at_boundary") == factor_bits
            and seed.get("construction_speed_factor_bits") == factor_bits,
        "next_loop_start_completed": seed.get("start_pending") is False and seed.get("start_completed") is True
            and seed.get("start_completion_callbacks") == 1 and seed.get("start_extra_hangar_dwell") == 0
            and seed.get("start_timing_controlled") is True and seed.get("start_world_frozen") is True
            and creation.get("completion_callbacks") == 1 and creation.get("extra_hangar_dwell") == 0,
        "start_boundary_measured": seed.get("start_game_calls") == 1 and seed.get("start_game_returns") == 1
            and seed.get("start_cfps_fixed_applications") == 1 and seed.get("start_speed_factor_bits") == factor_bits
            and seed.get("start_thread_id") == seed.get("seed_thread_id")
            and seed.get("start_hangar_onloop_requests") == 1 and seed.get("start_hangar_onloop_executed") == 0
            and seed.get("start_completion_scope_active") is False,
        "fixed_clock_contract": clock.get("version") == 2 and clock.get("numerator") == 1
            and clock.get("denominator") == 60,
        "start_frozen_immediately": creation.get("frozen_immediately") is True
            and creation.get("zero_unbudgeted_world_updates") is True,
        "visual_owner_retained": not require_visual or (receipt.get("active") is False and bool(handoff)),
        "fixture_did_not_reseed": not require_visual or (fixture.get("rng_seed_applied_here") is False
            and fixture.get("initial_rng_seed") == seed.get("seed")),
    }
    try:
        before, after = (counter(creation[k]) for k in ("world_updates_before_start", "world_updates_after_start"))
        checks["construction_updates_zero"] = before == after
        checks["native_construction_counters_agree"] = before == counter(seed["construction_initial_world_updates"]) == counter(seed["construction_final_world_updates"]) == counter(seed["start_world_updates_before"]) == counter(seed["start_world_updates_after"])
        start = counter(clock["initial_world_updates"])
        now = counter(clock["current_world_updates"])
        checks["clock_monotonic"] = start <= before <= now
        rows = receipt["intervals"]
        checks["intervals_present"] = isinstance(rows, list) and bool(rows)
        cursor = start
        seen_structured = False
        exact = True
        for index, row in enumerate(rows, 1):
            requested, actual = row["requested_updates"], row["actual_updates"]
            left, right = counter(row["start_world_updates"]), counter(row["end_world_updates"])
            exact &= (type(requested) is int and 0 <= requested <= 600 and type(actual) is int
                and type(row["index"]) is int and row["index"] == index and type(row["action_seq"]) is int and left == cursor and right - left == actual and actual >= 0)
            if row["kind"] == "structured":
                seen_structured = True
                exact &= left >= after and row["status"] == "complete" and actual == requested
            elif row["kind"] == "reset":
                exact &= not seen_structured and right <= before and (
                    (row["status"] == "complete" and actual == requested)
                    or (row["status"] == "menu_boundary" and actual <= requested))
            else:
                exact = False
            cursor = right
        checks["intervals_exact_and_contiguous"] = bool(exact and seen_structured)
        checks["no_unrecorded_setup_updates"] = cursor == (counter(handoff["world_updates"]) if require_visual else now)
        if require_visual:
            checks["first_visual_counter_matches_handoff"] = counter(raw["visual"]["world_updates"]) == cursor == now
        stages = receipt["menu_stages"]
        checks["bounded_synchronous_menu_chain"] = isinstance(stages, list) and 1 <= len(stages) <= 3
        current = receipt["admission_stage"]
        for row in stages:
            checks["bounded_synchronous_menu_chain"] &= row["before"] == current and row["after"] != current
            checks["bounded_synchronous_menu_chain"] &= counter(row["world_updates_before"]) == before == counter(row["world_updates_after"])
            current = row["after"]
        checks["bounded_synchronous_menu_chain"] &= current == "start_pending"
        checks["native_click_count_matches_chain"] = type(seed.get("construction_clicks")) is int and seed["construction_clicks"] == len(stages) == seed.get("completed_construction_clicks")
    except (ValueError, KeyError, TypeError):
        checks["complete_well_formed_counter_evidence"] = False
    integer_fields = {"construction_fixed_step_numerator": 1, "construction_fixed_step_denominator": 60,
        "base_speed_factor_bits_at_boundary": factor_bits, "construction_speed_factor_bits": factor_bits,
        "start_completion_callbacks": 1, "start_extra_hangar_dwell": 0,
        "start_game_calls": 1, "start_game_returns": 1, "start_cfps_fixed_applications": 1,
        "start_speed_factor_bits": factor_bits, "start_hangar_onloop_requests": 1, "start_hangar_onloop_executed": 0}
    checks["typed_native_counts"] = all(type(seed.get(k)) is int and seed[k] == v for k, v in integer_fields.items())
    checks["typed_creation_counts"] = all(type(creation.get(k)) is int and creation[k] == v
        for k, v in (("completion_callbacks", 1), ("extra_hangar_dwell", 0)))
    checks["typed_fixed_clock"] = all(type(clock.get(k)) is int and clock[k] == v
        for k, v in (("version", 2), ("numerator", 1), ("denominator", 60)))
    return {"passed": all(checks.values()), "checks": checks,
            "scope": "Receipt integrity for this setup, not a proof of full-game determinism."}


def packet_proof(raw, packet_records):
    """Join native intervals to actual archived dispatched requests."""
    receipt = raw.get("deterministic_setup") or {}
    checks = {}
    try:
        packets = [row["packet"] for row in packet_records]
        fresh = [p for p in packets if "benchmark_setup" in p]
        checks["one_fresh_request"] = len(fresh) == 1 and fresh[0] is packets[0]
        first = fresh[0]
        checks["fresh_request_identity"] = first["seq"] == receipt["start_action_seq"]
        checks["fresh_request_seed"] = first["benchmark_setup"] == {"version": 1, "fresh": True, "seed": 1} and all(
            type(first["benchmark_setup"].get(k)) is t for k, t in (("version", int), ("fresh", bool), ("seed", int)))
        action = first["actions"]
        checks["fresh_action_matches_optin"] = len(action) == 1 and action[0].get("type") in ("start_game", "reset_episode") \
            and type(action[0].get("seed")) is int and action[0]["seed"] == 1 \
            and (action[0]["type"] != "start_game" or action[0].get("mode") == "new")

        sequences = [p["seq"] for p in packets]
        checks["packet_sequences_unique_increasing"] = all(type(s) is int for s in sequences) and all(
            a < b for a, b in zip(sequences, sequences[1:]))
        visual = [p for p in packets if p.get("observation_mode") == "visual-v1"]
        checks["handoff_is_first_visual_request"] = bool(visual) and receipt["handoff"]["action_seq"] == visual[0]["seq"]
        checks["handoff_has_no_gameplay"] = type(visual[0].get("advance_frames")) is int and visual[0]["advance_frames"] == 0 and visual[0].get("actions") == []
        handoff_seq = receipt["handoff"]["action_seq"]
        structured = [p for p in packets if p["seq"] > first["seq"] and p["seq"] < handoff_seq]
        intervals = [row for row in receipt["intervals"] if row["kind"] == "structured"]
        checks["every_setup_request_has_one_interval"] = len(structured) == len(intervals) and all(
            row["action_seq"] == p["seq"] and row["requested_updates"] == p["advance_frames"]
            and p.get("observation_mode") != "visual-v1" for row, p in zip(intervals, structured))
        resets = [row for row in receipt["intervals"] if row["kind"] == "reset"]
        checks["reset_intervals_match_request"] = all(row["action_seq"] == first["seq"]
            and first["actions"][0]["type"] == "reset_episode" for row in resets)
    except (KeyError, IndexError, TypeError):
        checks["complete_packet_evidence"] = False
    return {"passed": all(checks.values()), "checks": checks}


def first_capture_proof(frame, packet_records):
    """Join the actual image bytes, native handoff and archived request before actors."""
    raw = frame.observation.raw
    native = receipt_proof(raw)
    packets = packet_proof(raw, packet_records)
    try:
        reference = frame.reference
        image_ok = reference["sha256"] == hashlib.sha256(Path(frame.image_path).read_bytes()).hexdigest() and (
            reference["action_seq"] == frame.observation.last_action_seq == raw["deterministic_setup"]["handoff"]["action_seq"]) and all(
            reference[k] == raw["visual"][k] for k in ("frame_id", "capture_id", "world_updates", "simulated_updates",
                "visual_clock_version", "fixed_step_numerator", "fixed_step_denominator"))
    except (OSError, KeyError, TypeError, AttributeError):
        image_ok = False
    return {"passed": native["passed"] and packets["passed"] and image_ok,
        "receipt_proof": native, "packet_proof": packets, "first_image_verified": image_ok,
        "first_image": copy.deepcopy(frame.reference), "first_observation": copy.deepcopy(raw)}


class DeterministicSetupSession(AgentSession):
    def configure_setup(self, output, delay=0.0):
        if hasattr(self, "setup_output"):
            raise RuntimeError("Setup collector cannot be reconfigured")
        self.setup_output = Path(output)
        self.setup_delay = delay
        self.setup_requested = False
        self.fresh_seq = None
        self.setup_packets = []
        self.setup_receipts = []
        self.last_setup_receipt_json = None

    def _archive(self):
        write_json(self.setup_output / "deterministic-setup-session.json", {
            "contract": "deterministic-setup-collector-v1", "setup_model_calls": 0,
            "scope": "Setup receipt and packet archive; actor call counts are recorded in the trajectory and visual report.",
            "deliberate_setup_delay_seconds": self.setup_delay,
            "packets": self.setup_packets, "observations": self.setup_receipts})

    def _write_action_atomic(self, payload):
        packet = copy.deepcopy(payload)
        if not hasattr(self, "setup_output"):
            raise RuntimeError("Explicit setup collector configuration required")
        actions = packet.get("actions") or []
        fresh = any(a.get("type") in ("start_game", "reset_episode") for a in actions)
        if fresh:
            if self.setup_requested or len(actions) != 1 or type(actions[0].get("seed")) is not int or actions[0]["seed"] != 1:
                raise RuntimeError("Only one explicit seed-one fresh setup is permitted")
            if actions[0]["type"] == "start_game" and actions[0].get("mode") != "new":
                raise RuntimeError("Fresh setup cannot continue a save")
            packet["benchmark_setup"] = {"version": 1, "fresh": True, "seed": 1}
            self.setup_requested = True
            self.fresh_seq = packet["seq"]
        elif not self.setup_requested:
            raise RuntimeError("No action may precede the fresh setup request")
        # Delay prerequisite requests too, not just model-side timing probes.
        if packet.get("observation_mode") != "visual-v1":
            time.sleep(self.setup_delay)
        self.setup_packets.append({"packet": packet, "dispatch_wall_seconds": time.time()})
        self._archive()
        return super()._write_action_atomic(packet)

    def _wait_for(self, predicate, timeout=None):
        def checked(obs):
            receipt = obs.raw.get("deterministic_setup") or {}
            if not isinstance(receipt, dict):
                self.setup_receipts.append({"failed_observation": obs.raw})
                self._archive()
                raise RuntimeError("Malformed deterministic setup receipt")
            if receipt and hasattr(self, "setup_output"):
                encoded = json.dumps(receipt, sort_keys=True)
                if encoded != self.last_setup_receipt_json:
                    self.setup_receipts.append({"last_action_seq": obs.last_action_seq,
                        "receipt": copy.deepcopy(receipt), "observation": obs.raw})
                    self.last_setup_receipt_json = encoded
                    self._archive()
            if receipt.get("phase") == "failed" or receipt.get("error"):
                self.setup_receipts.append({"failed_observation": obs.raw})
                self._archive()
                raise RuntimeError("Deterministic setup failed: " + str(receipt.get("error")))
            if receipt and obs.raw.get("game_started") is True and receipt.get("phase") not in ("ready", "visual"):
                return False
            if self.fresh_seq is not None and obs.raw.get("game_started") is True:
                if type(obs.last_action_seq) is not int or obs.last_action_seq < self.fresh_seq:
                    return False
                if not receipt:
                    self.setup_receipts.append({"failed_observation": obs.raw})
                    self._archive()
                    raise RuntimeError("Acknowledged fresh game lacks deterministic setup receipt")
                if receipt.get("phase") not in ("ready", "visual"):
                    return False
                if type(receipt.get("seed")) is not int or receipt["seed"] != 1:
                    raise RuntimeError("Deterministic setup seed differs from declared seed")
            return predicate(obs)
        obs = super()._wait_for(checked, timeout)
        if hasattr(self, "setup_output"):
            self.setup_receipts.append({"last_action_seq": obs.last_action_seq,
                "receipt": copy.deepcopy(obs.raw.get("deterministic_setup")), "observation": obs.raw})
            self._archive()
        return obs
