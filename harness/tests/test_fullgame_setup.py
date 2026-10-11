"""Fake-only admission tests; no processes, models or game actions."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest

from ftl_bench import fullgame_setup as setup

def good_receipt():
    fixed = struct.unpack("<I", struct.pack("<f", 16 / 60))[0]
    native = {"contract": "fresh-start-seed-v3", "contract_version": 3,
        "seed": 1, "boundary": "ShipBuilder::Open.before_super", "applied": True,
        "pending": False, "failed": False, "error": "", "native_seed_applications": 1,
        "c_runtime_seed_applications": 1, "names_before_arm": 1, "names_before_seed": 1,
        "unclassified_names_before_arm": 0, "unclassified_names_before_seed": 0,
        "intervening_names_after_arm": 0, "utility_name_calls": 1, "utility_lookup_calls": 1,
        "utility_lookup_completed": 1, "utility_lookup_valid": True,
        "utility_name_provenance": "StatBoostManager::CreateDummyCrew.GetCrewBlueprint(human)",
        "utility_name": "Orphan dummy", "utility_thread_id": 42,
        "reservations_before_arm": 1, "reservations_before_reset": 1,
        "reservation_names_before_reset": ["Orphan dummy"], "reservations_after_reset": 0,
        "reservation_reset_applications": 1, "reservation_reset_verified": True,
        "reservation_reset_thread_id": 42,
        **{f"factory_{kind}_before_{stage}": 0 for kind in ("crew", "lost", "player", "enemy", "clone")
            for stage in ("arm", "reset")},
        "ship_inits_before_arm": 0, "ship_inits_before_seed": 0, "names_during_open": 3,
        "constructor_timing_controlled": True, "clock_owned_at_arm": True, "clock_owned_at_boundary": True,
        "epoch": 1, "seed_thread_id": 42, "clock_update_permitted_at_boundary": False,
        "construction_scope_active": False, "construction_fixed_step_numerator": 1, "construction_fixed_step_denominator": 60,
        "base_speed_factor_bits_at_boundary": fixed, "construction_speed_factor_bits": fixed,
        "start_pending": False, "start_completed": True, "start_completion_callbacks": 1,
        "start_extra_hangar_dwell": 0, "start_timing_controlled": True, "start_world_frozen": True,
        "construction_clicks": 2, "completed_construction_clicks": 2,
        "start_game_calls": 1, "start_game_returns": 1, "start_cfps_fixed_applications": 1,
        "start_speed_factor_bits": fixed, "start_thread_id": 42, "start_hangar_onloop_requests": 1,
        "start_hangar_onloop_executed": 0, "start_completion_scope_active": False,
        "construction_initial_world_updates": "0", "construction_final_world_updates": "0",
        "start_world_updates_before": "0", "start_world_updates_after": "0"}
    return {"visual": {"world_updates": "90"},
        "visual_challenge_fixture": {"rng_seed_applied_here": False, "initial_rng_seed": 1},
        "deterministic_setup": {"contract": "deterministic-setup-v1", "version": 1,
            "phase": "visual", "seed": 1, "native_seed": native, "active": False, "start_action_seq": 1,
            "creation": {"world_updates_before_start": "0", "world_updates_after_start": "0",
                "frozen_immediately": True, "zero_unbudgeted_world_updates": True, "completion_callbacks": 1, "extra_hangar_dwell": 0},
            "clock": {"version": 2, "numerator": 1, "denominator": 60,
                "initial_world_updates": "0", "current_world_updates": "90"},
            "handoff": {"action_seq": 4, "world_updates": "90"},
            "intervals": [{"index": 1, "kind": "structured", "action_seq": 2,
                "requested_updates": 30, "actual_updates": 30, "start_world_updates": "0",
                "end_world_updates": "30", "status": "complete"},
                {"index": 2, "kind": "structured", "action_seq": 3, "requested_updates": 60,
                "actual_updates": 60, "start_world_updates": "30", "end_world_updates": "90", "status": "complete"}],
            "admission_stage": "main_menu", "menu_stages": [
                {"before": "main_menu", "after": "hangar", "world_updates_before": "0", "world_updates_after": "0"},
                {"before": "hangar", "after": "start_pending", "world_updates_before": "0", "world_updates_after": "0"}]}}


def immediate(seed=23):
    raw = good_receipt()
    del raw["visual_challenge_fixture"]
    r = raw["deterministic_setup"]
    r["seed"] = r["native_seed"]["seed"] = seed
    r["native_seed"]["arm_stage"] = "main_menu"
    r["intervals"] = []
    r["clock"]["current_world_updates"] = "0"
    r["handoff"] = {"action_seq": 2, "world_updates": "0"}
    raw.update(game_started=True, last_action_seq=2)
    raw["visual"] = {"world_updates": "0", "simulated_updates": "0",
        "visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60,
        "action_seq": 2, "frame_id": "fixture-free-frame", "capture_id": 91}
    raw["capabilities"] = {k: v for k, v in raw["visual"].items()
                           if k not in ("action_seq", "frame_id", "capture_id")}
    return raw


def packets(seed=23):
    return [{"packet": p} for p in [
        {"seq": 1, "advance_frames": 0, "actions": [{"type": "start_game", "mode": "new", "seed": seed}],
         "benchmark_setup": {"version": 1, "fresh": True, "seed": seed}},
        {"seq": 2, "advance_frames": 0, "actions": [], "observation_mode": "visual-v1"}]]


@pytest.mark.parametrize("seed", [0, 1, 23, 0xFFFFFFFF])
def test_immediate_fixture_free_start_passes_exactly_zero_updates(seed):
    raw = immediate(seed)
    assert setup.receipt_proof(raw, seed)["passed"]
    assert setup.packet_proof(raw, packets(seed), seed)["passed"]
    assert raw["deterministic_setup"]["native_seed"]["names_before_seed"] == 1


@pytest.mark.parametrize("value", [True, False, -1, 0x100000000, "23", None])
def test_invalid_declared_seed_is_configuration_error(value):
    with pytest.raises(ValueError):
        setup.receipt_proof(immediate(), value)
    with pytest.raises(ValueError):
        setup.packet_proof(immediate(), packets(), value)


@pytest.mark.parametrize("field,value", [
    ("native_seed_applications", 2), ("c_runtime_seed_applications", 0),
    ("contract_version", 2), ("boundary", "hangar.Start"), ("epoch", 2),
    ("names_before_arm", 0), ("names_before_seed", 2), ("names_during_open", 2),
    ("unclassified_names_before_arm", 1), ("unclassified_names_before_seed", 1),
    ("intervening_names_after_arm", 1), ("ship_inits_before_seed", 1),
    ("utility_lookup_calls", 2), ("utility_lookup_valid", False),
    ("utility_name_provenance", "unclassified"), ("utility_name", ""),
    ("reservation_names_before_reset", ["other"]), ("reservations_after_reset", 1),
    ("reservation_reset_applications", 2), ("reservation_reset_verified", False),
    ("utility_thread_id", 43), ("reservation_reset_thread_id", 43), ("start_thread_id", 43),
    ("factory_crew_before_arm", 1), ("factory_lost_before_reset", None),
    ("constructor_timing_controlled", False), ("clock_owned_at_arm", False),
    ("clock_owned_at_boundary", False), ("clock_update_permitted_at_boundary", True),
    ("construction_scope_active", True), ("construction_speed_factor_bits", 0),
    ("construction_final_world_updates", "1"), ("start_world_updates_after", "1"),
    ("start_completion_callbacks", 2), ("start_extra_hangar_dwell", 1),
    ("start_game_returns", 0), ("start_cfps_fixed_applications", 0),
    ("start_hangar_onloop_executed", 1), ("start_completion_scope_active", True),
    ("completed_construction_clicks", 1), ("arm_stage", "hangar"),
    ("pending", True), ("applied", False), ("failed", True), ("error", "native refusal"),
])
def test_native_v3_guard_mutations_are_rejected(field, value):
    raw = immediate()
    raw["deterministic_setup"]["native_seed"][field] = value
    assert not setup.receipt_proof(raw, 23)["passed"]


@pytest.mark.parametrize("field", ["start_completion_callbacks", "start_extra_hangar_dwell",
    "start_game_calls", "start_game_returns", "construction_fixed_step_numerator",
    "utility_thread_id", "reservation_reset_thread_id", "completed_construction_clicks", "seed"])
def test_boolean_cannot_forge_integer_evidence(field):
    raw = immediate(1)
    raw["deterministic_setup"]["native_seed"][field] = True
    assert not setup.receipt_proof(raw, 1)["passed"]


@pytest.mark.parametrize("raw", [None, [], {}, {"deterministic_setup": "bad"},
    {"deterministic_setup": {"native_seed": []}}, {"deterministic_setup": {"creation": 1}}])
def test_missing_or_malformed_receipts_fail_closed(raw):
    assert not setup.receipt_proof(raw, 23)["passed"]


@pytest.mark.parametrize("mutation", ["empty_advanced", "typed_counter", "missing_intervals", "handoff",
    "bool_sequence", "caps_clock", "caps_updates", "native_seed", "setup_seed", "fixture", "unstarted",
    "stage", "clock", "scope", "menu_updates"])
def test_handoff_and_zero_interval_checks_reject_contradictions(mutation):
    raw = immediate()
    r = raw["deterministic_setup"]
    if mutation == "empty_advanced":
        r["clock"]["current_world_updates"] = "1"
        r["handoff"]["world_updates"] = raw["visual"]["world_updates"] = "1"
    elif mutation == "typed_counter":
        r["clock"]["initial_world_updates"] = 0
    elif mutation == "missing_intervals":
        del r["intervals"]
    elif mutation == "handoff":
        raw["visual"]["action_seq"] = 3
    elif mutation == "bool_sequence":
        r["start_action_seq"] = True
    elif mutation == "caps_clock":
        raw["capabilities"]["fixed_step_numerator"] = True
    elif mutation == "caps_updates":
        raw["capabilities"]["simulated_updates"] = "1"
    elif mutation in ("native_seed", "setup_seed"):
        (r["native_seed"] if mutation == "native_seed" else r)["seed"] = 24
    elif mutation == "fixture":
        raw["visual_challenge_fixture"] = {}
    elif mutation == "unstarted":
        raw["game_started"] = False
    elif mutation == "stage":
        r["menu_stages"][0]["after"] = "invented"
    elif mutation == "clock":
        r["clock"]["version"] = 1
    elif mutation == "scope":
        r["active"] = True
    else:
        r["menu_stages"][0]["world_updates_after"] = "1"
    assert not setup.receipt_proof(raw, 23)["passed"]


def with_interval(kind="structured"):
    raw = immediate()
    r = raw["deterministic_setup"]
    r["intervals"] = [{"index": 1, "kind": kind, "action_seq": 2 if kind == "structured" else 1,
        "requested_updates": 30, "actual_updates": 30, "start_world_updates": "0",
        "end_world_updates": "30", "status": "complete"}]
    r["clock"]["current_world_updates"] = "30"
    r["handoff"] = {"action_seq": 3 if kind == "structured" else 2, "world_updates": "30"}
    for obj in (raw["visual"], raw["capabilities"]):
        obj["world_updates"] = obj["simulated_updates"] = "30"
    raw["last_action_seq"] = raw["visual"]["action_seq"] = r["handoff"]["action_seq"]
    ps = packets()
    if kind == "structured":
        ps.insert(1, {"packet": {"seq": 2, "advance_frames": 30, "actions": []}})
        ps[-1]["packet"]["seq"] = 3
    else:
        ps[0]["packet"]["actions"] = [{"type": "reset_episode", "seed": 23}]
        r["creation"]["world_updates_before_start"] = r["creation"]["world_updates_after_start"] = "30"
        for key in ("construction_initial_world_updates", "construction_final_world_updates",
                    "start_world_updates_before", "start_world_updates_after"):
            r["native_seed"][key] = "30"
        for row in r["menu_stages"]:
            row["world_updates_before"] = row["world_updates_after"] = "30"
    return raw, ps


@pytest.mark.parametrize("kind", ["reset"])
def test_exact_recorded_intervals_are_retained(kind):
    raw, ps = with_interval(kind)
    assert setup.receipt_proof(raw, 23)["passed"]
    assert setup.packet_proof(raw, ps, 23)["passed"]
    raw["deterministic_setup"]["intervals"][0]["actual_updates"] = 29
    assert not setup.receipt_proof(raw, 23)["passed"]


def test_structured_gameplay_interval_is_forbidden_even_when_exact():
    raw, ps = with_interval("structured")
    assert not setup.receipt_proof(raw, 23)["passed"]
    assert not setup.packet_proof(raw, ps, 23)["passed"]


def test_no_pre_handoff_structured_dispatch_reaches_transport(tmp_path, monkeypatch):
    session, sent = fake_session(tmp_path, monkeypatch)
    session._write_action_atomic(fresh_packet())
    session.setup_ready = True
    with pytest.raises(RuntimeError, match="Structured setup"):
        session._write_action_atomic({"seq": 2, "advance_frames": 0,
            "actions": [{"type": "choose_event", "choice_index": 0}]})
    with pytest.raises(RuntimeError, match="Structured setup"):
        session._write_action_atomic({"seq": 2, "advance_frames": 30, "actions": []})
    assert len(sent) == 1


@pytest.mark.parametrize("mutation", ["budget", "missing", "repeat", "continue", "late_seed",
    "visual_action", "visual_advance", "bool_optin", "reset_on_start", "wrong_handoff"])
def test_request_archive_must_match_every_setup_interval(mutation):
    raw, ps = with_interval()
    if mutation == "budget":
        ps[1]["packet"]["advance_frames"] = 31
    elif mutation == "missing":
        ps.pop(1)
    elif mutation == "repeat":
        ps.insert(1, copy.deepcopy(ps[0]))
    elif mutation == "continue":
        ps[0]["packet"]["actions"][0]["mode"] = "continue"
    elif mutation == "late_seed":
        ps[1]["packet"]["benchmark_setup"] = ps[0]["packet"]["benchmark_setup"]
    elif mutation == "visual_action":
        ps[-1]["packet"]["actions"] = [{"type": "key", "key": "enter"}]
    elif mutation == "visual_advance":
        ps[-1]["packet"]["advance_frames"] = 1
    elif mutation == "bool_optin":
        ps[0]["packet"]["benchmark_setup"]["version"] = True
    elif mutation == "reset_on_start":
        raw["deterministic_setup"]["intervals"][0]["kind"] = "reset"
    else:
        ps[-1]["packet"]["seq"] = 4
    assert not setup.packet_proof(raw, ps, 23)["passed"]


def fake_session(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(setup.AgentSession, "_write_action_atomic", lambda self, packet: sent.append(packet))
    session = setup.FullGameSetupSession(tmp_path, setup_output=tmp_path / "evidence", seed=23)
    return session, sent


def fresh_packet():
    return {"seq": 1, "advance_frames": 0, "actions": [{"type": "start_game", "mode": "new", "seed": 23}]}


def admit_frame(session, tmp_path, raw=None):
    raw = raw or immediate()
    image = tmp_path / "fake-image.png"
    image.write_bytes(b"fake archived bytes; VisualSession PNG validation is tested separately")
    ref = {k: raw["visual"][k] for k in ("action_seq", "frame_id", "capture_id", "world_updates",
        "simulated_updates", "visual_clock_version", "fixed_step_numerator", "fixed_step_denominator")}
    ref["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
    frame = SimpleNamespace(observation=SimpleNamespace(raw=raw, last_action_seq=2), reference=ref, image_path=image)
    return frame


def test_session_writes_one_optin_and_gates_actual_gameplay(tmp_path, monkeypatch):
    session, sent = fake_session(tmp_path, monkeypatch)
    first = fresh_packet()
    session._write_action_atomic(first)
    assert "benchmark_setup" not in first
    assert sent[0]["benchmark_setup"]["seed"] == 23
    with pytest.raises(RuntimeError, match="ready setup"):
        session._write_action_atomic(packets()[-1]["packet"])
    session.setup_ready = True
    session._write_action_atomic(packets()[-1]["packet"])
    with pytest.raises(RuntimeError, match="First visual"):
        session._write_action_atomic({"seq": 3, "advance_frames": 30, "actions": [], "observation_mode": "visual-v1"})
    proof = session.verify_first_capture(admit_frame(session, tmp_path))
    assert proof["passed"] and session.admitted
    session._write_action_atomic({"seq": 3, "advance_frames": 30, "actions": [], "observation_mode": "visual-v1"})
    assert len(sent) == 3
    assert len(json.loads((session.setup_output / "setup-session.json").read_text())["packets"]) == 2
    with pytest.raises(RuntimeError):
        session._write_action_atomic({**fresh_packet(), "seq": 4})
    with pytest.raises(RuntimeError, match="Structured setup"):
        session._write_action_atomic({"seq": 4, "advance_frames": 0, "actions": []})


@pytest.mark.parametrize("path", ["receipt", "image", "image_identity"])
def test_bad_first_capture_is_archived_and_keeps_gameplay_blocked(tmp_path, monkeypatch, path):
    session, sent = fake_session(tmp_path, monkeypatch)
    session._write_action_atomic(fresh_packet())
    session.setup_ready = True
    session._write_action_atomic(packets()[-1]["packet"])
    frame = admit_frame(session, tmp_path)
    if path == "receipt":
        frame.observation.raw["deterministic_setup"]["native_seed"]["native_seed_applications"] = 2
    elif path == "image":
        frame.image_path.write_bytes(b"different")
    else:
        frame.reference["capture_id"] = 92
    with pytest.raises(RuntimeError, match="admission failed"):
        session.verify_first_capture(frame)
    assert not session.admitted
    assert not json.loads((session.setup_output / "admission.json").read_text())["passed"]
    with pytest.raises(RuntimeError):
        session._write_action_atomic({"seq": 3, "advance_frames": 1, "actions": [], "observation_mode": "visual-v1"})
    assert len(sent) == 2


def test_first_capture_admission_cannot_be_repeated(tmp_path, monkeypatch):
    session, _ = fake_session(tmp_path, monkeypatch)
    session._write_action_atomic(fresh_packet())
    session.setup_ready = True
    frame = admit_frame(session, tmp_path)
    session._write_action_atomic(packets()[-1]["packet"])
    assert session.verify_first_capture(frame)["passed"]
    with pytest.raises(RuntimeError, match="single requested first"):
        session.verify_first_capture(frame)


def test_validation_before_requested_first_capture_is_rejected(tmp_path, monkeypatch):
    session, _ = fake_session(tmp_path, monkeypatch)
    session._write_action_atomic(fresh_packet())
    session.setup_ready = True
    frame = admit_frame(session, tmp_path)
    with pytest.raises(RuntimeError, match="single requested first"):
        session.verify_first_capture(frame)
    assert not session.admitted


def test_pending_start_is_not_ready_and_failure_is_never_retried(tmp_path, monkeypatch):
    session, sent = fake_session(tmp_path, monkeypatch)
    session._write_action_atomic(fresh_packet())
    raw = immediate()
    raw["last_action_seq"] = 1
    ready = copy.deepcopy(raw)
    raw["deterministic_setup"]["phase"] = "starting"
    ready["deterministic_setup"]["phase"] = "ready"
    seen = iter([SimpleNamespace(raw=x, last_action_seq=1) for x in (raw, ready)])
    monkeypatch.setattr(session.client, "read_latest", lambda: next(seen))
    obs = session._wait_for(lambda o: o.raw["game_started"], timeout=.2)
    assert obs.raw["deterministic_setup"]["phase"] == "ready" and session.setup_ready
    archived = json.loads((session.setup_output / "setup-session.json").read_text())
    assert [x["receipt"]["phase"] for x in archived["observations"]] == ["starting", "ready"]
    ready["deterministic_setup"].update(phase="failed", error="native arm refused")
    monkeypatch.setattr(session.client, "read_latest", lambda: SimpleNamespace(raw=ready, last_action_seq=1))
    with pytest.raises(RuntimeError, match="native arm refused"):
        session._wait_for(lambda o: True, timeout=.1)
    assert len(sent) == 1


def test_acknowledged_game_without_setup_receipt_is_rejected(tmp_path, monkeypatch):
    session, _ = fake_session(tmp_path, monkeypatch)
    session._write_action_atomic(fresh_packet())
    monkeypatch.setattr(session.client, "read_latest", lambda: SimpleNamespace(
        raw={"game_started": True}, last_action_seq=1))
    with pytest.raises(RuntimeError, match="lacks deterministic"):
        session._wait_for(lambda o: True, timeout=.1)
    assert json.loads((session.setup_output / "setup-session.json").read_text())["observations"]


@pytest.mark.parametrize("receipt", [[], "native raw refusal", 1])
def test_malformed_receipt_is_archived_before_failure(tmp_path, monkeypatch, receipt):
    session, sent = fake_session(tmp_path, monkeypatch)
    session._write_action_atomic(fresh_packet())
    raw = {"game_started": True, "deterministic_setup": receipt}
    monkeypatch.setattr(session.client, "read_latest", lambda: SimpleNamespace(raw=raw, last_action_seq=1))
    with pytest.raises(RuntimeError, match="Malformed"):
        session._wait_for(lambda o: True, timeout=.1)
    rows = json.loads((session.setup_output / "setup-session.json").read_text())["observations"]
    assert rows[-1]["failed_observation"] == raw and len(sent) == 1


def test_overwrite_confirmation_has_exact_three_click_chain():
    raw = immediate()
    r = raw["deterministic_setup"]
    r["menu_stages"].insert(0, {"before": "main_menu", "after": "overwrite_confirmation",
        "world_updates_before": "0", "world_updates_after": "0"})
    r["menu_stages"][1]["before"] = "overwrite_confirmation"
    r["native_seed"]["construction_clicks"] = r["native_seed"]["completed_construction_clicks"] = 3
    assert setup.receipt_proof(raw, 23)["passed"]


@pytest.mark.parametrize("mutation", ["continue", "wrong_seed", "missing_seed", "frames", "bool_seed", "injected", "mixed"])
def test_bad_fresh_request_never_reaches_transport(tmp_path, monkeypatch, mutation):
    session, sent = fake_session(tmp_path, monkeypatch)
    p = fresh_packet()
    if mutation == "continue":
        p["actions"][0]["mode"] = "continue"
    elif mutation == "wrong_seed":
        p["actions"][0]["seed"] = 1
    elif mutation == "missing_seed":
        del p["actions"][0]["seed"]
    elif mutation == "frames":
        p["advance_frames"] = 1
    elif mutation == "bool_seed":
        p["actions"][0]["seed"] = True
    elif mutation == "injected":
        p["benchmark_setup"] = {"seed": 23}
    else:
        p["actions"].append({"type": "choose_event", "choice_index": 0})
    with pytest.raises(RuntimeError):
        session._write_action_atomic(p)
    assert sent == []

