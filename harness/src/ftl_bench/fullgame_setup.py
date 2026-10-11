"""Explicit opt-in setup session and fail-closed receipt validation.

Fixture-free full-game admission. No model calls or native writes, and
no random reseeding after the fresh construction boundary.
"""
import copy
import hashlib
import json
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


def _receipt_proof(raw, expected_seed, *, require_visual=True):
    receipt = raw.get("deterministic_setup") or {}
    seed = receipt.get("native_seed") or {}
    creation = receipt.get("creation") or {}
    clock = receipt.get("clock") or {}
    handoff = receipt.get("handoff") or {}
    factor_bits = struct.unpack("<I", struct.pack("<f", 16 / 60))[0]
    checks = {
        "explicit_setup_contract": receipt.get("contract") == "deterministic-setup-v1"
            and type(receipt.get("version")) is int and receipt["version"] == 1,
        "setup_completed_without_error": receipt.get("phase") in (("visual",) if require_visual else ("ready", "visual"))
            and not receipt.get("error") and not receipt.get("pending"),
        "declared_seed_matches": type(receipt.get("seed")) is int and receipt["seed"] == expected_seed
            and type(seed.get("seed")) is int and seed["seed"] == expected_seed,
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
        "fixture_free": "visual_challenge_fixture" not in raw,
    }
    try:
        before, after = (counter(creation[k]) for k in ("world_updates_before_start", "world_updates_after_start"))
        checks["construction_updates_zero"] = before == after
        checks["native_construction_counters_agree"] = before == counter(seed["construction_initial_world_updates"]) == counter(seed["construction_final_world_updates"]) == counter(seed["start_world_updates_before"]) == counter(seed["start_world_updates_after"])
        start = counter(clock["initial_world_updates"])
        now = counter(clock["current_world_updates"])
        checks["clock_monotonic"] = start <= before <= now
        rows = receipt["intervals"]
        checks["intervals_present"] = isinstance(rows, list)
        cursor = start
        seen_structured = False
        exact = True
        for index, row in enumerate(rows, 1):
            requested, actual = row["requested_updates"], row["actual_updates"]
            left, right = counter(row["start_world_updates"]), counter(row["end_world_updates"])
            exact &= (type(requested) is int and 0 <= requested <= 600 and type(actual) is int
                and row["index"] == index and left == cursor and right - left == actual and actual >= 0)
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
        checks["intervals_exact_and_contiguous"] = bool(exact)
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
    return {"passed": all(checks.values()), "checks": checks,
            "scope": "Receipt integrity for this setup, not a proof of full-game determinism."}


def declared_seed(value):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("Declared seed must be an unsigned 32-bit integer")
    return value


def _ints(obj, values):
    return all(type(obj.get(k)) is int and obj[k] == v for k, v in values.items())


def receipt_proof(raw, expected_seed, *, require_visual=True):
    """Fail closed on incomplete/malformed evidence, including bool-as-int values.

    A ready receipt is diagnostic; only the first visual receipt is admission.
    This validates observed receipts, not every possible native RNG consumer.
    """
    declared_seed(expected_seed)
    checks = {}
    try:
        if not isinstance(raw, dict):
            raise ValueError("Observation must be an object")
        checks.update(_receipt_proof(raw, expected_seed, require_visual=require_visual)["checks"])
        r = raw["deterministic_setup"]
        n, c, clock = r["native_seed"], r["creation"], r["clock"]
        integer_evidence = {
            "contract_version": 3, "epoch": 1, "seed": expected_seed,
            "native_seed_applications": 1, "c_runtime_seed_applications": 1,
            "names_before_arm": 1, "names_before_seed": 1,
            "utility_name_calls": 1, "utility_lookup_calls": 1, "utility_lookup_completed": 1,
            "unclassified_names_before_arm": 0, "unclassified_names_before_seed": 0,
            "intervening_names_after_arm": 0, "ship_inits_before_arm": 0, "ship_inits_before_seed": 0,
            "reservations_before_arm": 1, "reservations_before_reset": 1,
            "reservations_after_reset": 0, "reservation_reset_applications": 1,
            "construction_fixed_step_numerator": 1, "construction_fixed_step_denominator": 60,
            "base_speed_factor_bits_at_boundary": 1049135241, "construction_speed_factor_bits": 1049135241,
            "start_completion_callbacks": 1, "start_extra_hangar_dwell": 0,
            "start_game_calls": 1, "start_game_returns": 1, "start_cfps_fixed_applications": 1,
            "start_speed_factor_bits": 1049135241, "start_hangar_onloop_requests": 1,
            "start_hangar_onloop_executed": 0,
        }
        checks["typed_native_integer_evidence"] = _ints(n, integer_evidence)
        thread = n["seed_thread_id"]
        checks["typed_game_thread_identity"] = type(thread) is int and thread > 0 and _ints(n, {
            "seed_thread_id": thread, "utility_thread_id": thread,
            "reservation_reset_thread_id": thread, "start_thread_id": thread})
        checks["typed_setup_integer_evidence"] = _ints(r, {"version": 1, "seed": expected_seed}) and (
            type(r["start_action_seq"]) is int and r["start_action_seq"] > 0) and _ints(c, {
            "completion_callbacks": 1, "extra_hangar_dwell": 0}) and _ints(clock, {
            "version": 2, "numerator": 1, "denominator": 60})
        checks["typed_intervals"] = isinstance(r["intervals"], list) and all(
            type(row["index"]) is int and type(row["action_seq"]) is int and row["action_seq"] > 0
            for row in r["intervals"])
        checks["no_structured_gameplay_before_actor"] = all(row["kind"] == "reset" for row in r["intervals"])
        # Native arm cannot admit a preexisting hangar or a continued world.
        allowed = {("main_menu", "overwrite_confirmation"), ("main_menu", "hangar"),
                   ("overwrite_confirmation", "hangar"), ("hangar", "start_pending")}
        checks["native_menu_admission"] = r["admission_stage"] in ("main_menu", "overwrite_confirmation") and (
            n["arm_stage"] == r["admission_stage"]) and all(
            (row["before"], row["after"]) in allowed for row in r["menu_stages"])
        checks["typed_click_count"] = _ints(n, {
            "construction_clicks": len(r["menu_stages"]),
            "completed_construction_clicks": len(r["menu_stages"])})
        if require_visual:
            h, visual, caps = r["handoff"], raw["visual"], raw["capabilities"]
            world = h["world_updates"]
            checks["first_visual_fixed_clock"] = all(_ints(obj, {
                "visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60})
                and obj["world_updates"] == world == obj["simulated_updates"] for obj in (visual, caps))
            checks["typed_visual_handoff_identity"] = type(h["action_seq"]) is int and h["action_seq"] > r["start_action_seq"] and (
                type(visual["action_seq"]) is int and visual["action_seq"] == h["action_seq"]
                == raw["last_action_seq"] and type(raw["last_action_seq"]) is int)
            checks["first_visual_game_started"] = raw.get("game_started") is True
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        checks["complete_well_formed_receipt"] = False
        detail = str(error)
    else:
        detail = None
    return {"contract": "fullgame-setup-proof-v1", "passed": bool(checks) and all(checks.values()),
            "expected_seed": expected_seed, "checks": checks, "error": detail,
            "scope": "Fixture-free v3 admission receipt integrity; full-game RNG equivalence is not proved."}


def packet_proof(raw, packet_records, expected_seed):
    """Join the complete pre-actor request archive to native intervals/handoff."""
    declared_seed(expected_seed)
    checks = {}
    try:
        r = raw["deterministic_setup"]
        packets = [row["packet"] for row in packet_records]
        first, visual = packets[0], packets[-1]
        actions = first["actions"]
        action = actions[0]
        fresh_actions = [{"type": "start_game", "mode": "new", "seed": expected_seed},
                         {"type": "reset_episode", "seed": expected_seed}]
        checks["one_explicit_fresh_request"] = len(actions) == 1 and action in fresh_actions and (
            first["advance_frames"] == 0 and type(first["advance_frames"]) is int) and (
            first["benchmark_setup"] == {"version": 1, "fresh": True, "seed": expected_seed})
        checks["typed_fresh_contract"] = _ints(first["benchmark_setup"], {"version": 1, "seed": expected_seed}) and (
            first["benchmark_setup"]["fresh"] is True and type(action["seed"]) is int)
        checks["fresh_only_once"] = all("benchmark_setup" not in p and not any(
            a.get("type") in ("start_game", "reset_episode") for a in p["actions"]) for p in packets[1:])
        seqs = [p["seq"] for p in packets]
        checks["packet_sequences_unique_increasing"] = all(type(s) is int and s > 0 for s in seqs) and all(
            a < b for a, b in zip(seqs, seqs[1:]))
        checks["fresh_request_identity"] = first["seq"] == r["start_action_seq"]
        checks["exact_empty_zero_frame_handoff"] = len(packets) >= 2 and visual.get("observation_mode") == "visual-v1" and (
            visual["seq"] == r["handoff"]["action_seq"] and visual["actions"] == []
            and type(visual["advance_frames"]) is int and visual["advance_frames"] == 0) and all(
            p.get("observation_mode") != "visual-v1" for p in packets[:-1])
        checks["fresh_request_then_immediate_capture_only"] = len(packets) == 2
        structured = packets[1:-1]
        intervals = [row for row in r["intervals"] if row["kind"] == "structured"]
        checks["every_setup_request_has_one_interval"] = len(structured) == len(intervals) and all(
            type(p["advance_frames"]) is int and 0 <= p["advance_frames"] <= 600
            and row["action_seq"] == p["seq"] and row["requested_updates"] == p["advance_frames"]
            and p.get("observation_mode") not in ("visual-v1",) for row, p in zip(intervals, structured))
        resets = [row for row in r["intervals"] if row["kind"] == "reset"]
        checks["reset_intervals_match_fresh_request"] = all(row["action_seq"] == first["seq"] and (
            action["type"] == "reset_episode") for row in resets)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        checks["complete_packet_evidence"] = False
        detail = str(error)
    else:
        detail = None
    return {"passed": bool(checks) and all(checks.values()), "checks": checks, "error": detail}


class FullGameSetupSession(AgentSession):
    """One explicit fresh admission; ordinary visual gameplay after checked handoff.

    Construct only inside ProtectedGame. This class does not launch/install,
    restore saves, decide gameplay, or guarantee native startup acceptance.
    """
    def __init__(self, user_folder, *, setup_output, seed, poll_interval=.01, step_timeout=20):
        self.expected_seed = declared_seed(seed)
        self.setup_output = Path(setup_output)
        self.setup_output.mkdir(parents=True, exist_ok=False)
        self.setup_packets, self.setup_receipts = [], []
        self.fresh_seq = None
        self.setup_ready = False
        self.handoff_requested = False
        self.admitted = False
        self.last_dispatched_seq = 0
        self.last_receipt_json = None
        super().__init__(user_folder, poll_interval=poll_interval, step_timeout=step_timeout)

    def _archive(self):
        write_json(self.setup_output / "setup-session.json", {
            "contract": "fullgame-setup-session-v1", "expected_seed": self.expected_seed,
            "admitted": self.admitted, "packets": self.setup_packets, "observations": self.setup_receipts})

    def _write_action_atomic(self, payload):
        packet = copy.deepcopy(payload)
        if not isinstance(packet, dict) or "benchmark_setup" in packet:
            raise RuntimeError("Caller cannot inject a setup contract")
        actions = packet.get("actions")
        if not isinstance(actions, list) or not all(isinstance(a, dict) for a in actions):
            raise RuntimeError("Malformed action packet")
        if type(packet.get("seq")) is not int or packet["seq"] < 1:
            raise RuntimeError("Action sequence must be a positive integer")
        if packet["seq"] <= self.last_dispatched_seq:
            raise RuntimeError("Action sequence must increase")
        if type(packet.get("advance_frames")) is not int or not 0 <= packet["advance_frames"] <= 600:
            raise RuntimeError("Native update budget must be an integer in 0..600")
        fresh = any(a.get("type") in ("start_game", "reset_episode") for a in actions)
        if fresh:
            expected = [{"type": "start_game", "mode": "new", "seed": self.expected_seed},
                        {"type": "reset_episode", "seed": self.expected_seed}]
            if self.fresh_seq is not None or len(actions) != 1 or actions[0] not in expected or (
                type(actions[0].get("seed")) is not int or type(packet.get("advance_frames")) is not int
                or packet["advance_frames"] != 0 or packet.get("observation_mode") is not None):
                raise RuntimeError("Only one explicit declared-seed zero-frame fresh request is permitted")
            packet["benchmark_setup"] = {"version": 1, "fresh": True, "seed": self.expected_seed}
            self.fresh_seq = packet["seq"]
        elif self.fresh_seq is None:
            raise RuntimeError("No action may precede explicit fresh setup")
        elif packet.get("observation_mode") == "visual-v1":
            if not self.admitted:
                if self.handoff_requested or not self.setup_ready or actions or (
                    type(packet.get("advance_frames")) is not int or packet["advance_frames"] != 0):
                    raise RuntimeError("First visual handoff requires ready setup and an empty zero-frame capture")
                self.handoff_requested = True
        else:
            raise RuntimeError("Structured setup cannot mutate a pure full-game start")
        self.last_dispatched_seq = packet["seq"]
        if not self.admitted:
            self.setup_packets.append({"packet": packet, "dispatch_wall_seconds": time.time()})
            self._archive()
        return super()._write_action_atomic(packet)

    def _wait_for(self, predicate, timeout=None):
        def checked(obs):
            raw = obs.raw
            if not isinstance(raw, dict):
                self.setup_receipts.append({"failed_observation": copy.deepcopy(raw)})
                self._archive()
                raise RuntimeError("Malformed deterministic setup observation")
            receipt = raw.get("deterministic_setup")
            if receipt is not None and not isinstance(receipt, dict):
                self.setup_receipts.append({"failed_observation": copy.deepcopy(raw)})
                self._archive()
                raise RuntimeError("Malformed deterministic setup receipt")
            if receipt is not None and not self.admitted:
                encoded = json.dumps(receipt, sort_keys=True)
                if encoded != self.last_receipt_json:
                    self.setup_receipts.append({"last_action_seq": obs.last_action_seq,
                        "receipt": copy.deepcopy(receipt), "observation": copy.deepcopy(raw)})
                    self.last_receipt_json = encoded
                    self._archive()
                if receipt.get("phase") == "failed" or receipt.get("error"):
                    raise RuntimeError("Deterministic setup failed: " + str(receipt.get("error")))
            if self.fresh_seq is not None and raw.get("game_started") is True:
                if type(obs.last_action_seq) is not int or obs.last_action_seq < self.fresh_seq:
                    return False
                if receipt is None:
                    self.setup_receipts.append({"failed_observation": copy.deepcopy(raw)})
                    self._archive()
                    raise RuntimeError("Acknowledged fresh game lacks deterministic setup receipt")
                if receipt.get("phase") not in ("ready", "visual"):
                    return False
                if receipt.get("phase") == "visual" and not self.handoff_requested:
                    raise RuntimeError("Unrequested visual handoff")
                if type(receipt.get("seed")) is not int or receipt["seed"] != self.expected_seed:
                    raise RuntimeError("Deterministic setup seed differs from declared seed")
                self.setup_ready = True
            return predicate(obs)
        return super()._wait_for(checked, timeout)

    def verify_first_capture(self, frame):
        """Call after VisualSession.capture and before any actor/model request."""
        if self.admitted or not self.handoff_requested:
            raise RuntimeError("A single requested first visual capture must precede admission")
        raw = frame.observation.raw
        proof = receipt_proof(raw, self.expected_seed)
        packets = packet_proof(raw, self.setup_packets, self.expected_seed)
        try:
            reference = frame.reference
            image_sha = hashlib.sha256(Path(frame.image_path).read_bytes()).hexdigest()
            image_ok = reference["sha256"] == image_sha and (
                reference["action_seq"] == frame.observation.last_action_seq
                == raw["deterministic_setup"]["handoff"]["action_seq"]) and all(
                reference[k] == raw["visual"][k] for k in (
                    "frame_id", "capture_id", "world_updates", "simulated_updates",
                    "visual_clock_version", "fixed_step_numerator", "fixed_step_denominator"))
        except (OSError, KeyError, TypeError, AttributeError):
            image_ok = False
        result = {"contract": "fullgame-admission-v1", "receipt_proof": proof, "packet_proof": packets,
            "first_image_verified": image_ok, "first_image": copy.deepcopy(frame.reference),
            "first_observation": copy.deepcopy(raw),
            "passed": proof["passed"] and packets["passed"] and image_ok}
        write_json(self.setup_output / "admission.json", result)
        if not result["passed"]:
            raise RuntimeError("Fixture-free full-game admission failed; evidence archived")
        self.admitted = True
        self._archive()
        return result



