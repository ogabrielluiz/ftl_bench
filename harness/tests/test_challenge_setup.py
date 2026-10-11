"""Adversarial receipts and fake transport; no game processes or model calls."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import struct
from types import SimpleNamespace

import pytest

from ftl_bench.cli import _bench_root
from ftl_bench.challenge_setup import DeterministicSetupSession as SetupSession, receipt_proof, packet_proof
import ftl_bench.challenge_setup as setup_session
import importlib.util
spec = importlib.util.spec_from_file_location("setup_challenges", _bench_root() / "scripts/validate_visual_challenges.py")
candidate_challenges = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate_challenges)


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


def test_complete_receipt_passes():
    assert receipt_proof(good_receipt())["passed"]


@pytest.mark.parametrize("path,value", [
    (("phase",), "ready"), (("error",), "clock ownership refused"),
    (("native_seed", "c_runtime_seed_applications"), 0),
    (("native_seed", "native_seed_applications"), 2),
    (("native_seed", "native_seed_applications"), True),
    (("native_seed", "names_before_seed"), 0),
    (("native_seed", "names_before_seed"), 2),
    (("native_seed", "contract_version"), 2),
    (("native_seed", "utility_lookup_valid"), False),
    (("native_seed", "utility_name_calls"), 2),
    (("native_seed", "utility_lookup_calls"), 2),
    (("native_seed", "utility_lookup_completed"), 0),
    (("native_seed", "utility_name_provenance"), "MainMenu::Open"),
    (("native_seed", "utility_thread_id"), 43),
    (("native_seed", "utility_name"), ""),
    (("native_seed", "unclassified_names_before_arm"), 1),
    (("native_seed", "unclassified_names_before_seed"), 1),
    (("native_seed", "intervening_names_after_arm"), 1),
    (("native_seed", "reservation_names_before_reset"), ["another name"]),
    (("native_seed", "reservation_names_before_reset"), ["Orphan dummy", "another name"]),
    (("native_seed", "reservations_before_arm"), 2),
    (("native_seed", "reservations_before_reset"), 2),
    (("native_seed", "reservations_after_reset"), 1),
    (("native_seed", "reservation_reset_applications"), 0),
    (("native_seed", "reservation_reset_applications"), 2),
    (("native_seed", "reservation_reset_verified"), False),
    (("native_seed", "reservation_reset_thread_id"), 43),
    (("native_seed", "ship_inits_before_arm"), 1),
    (("native_seed", "constructor_timing_controlled"), False),
    (("native_seed", "epoch"), 2), (("native_seed", "seed_thread_id"), 0),
    (("native_seed", "construction_speed_factor_bits"), 0),
    (("native_seed", "construction_fixed_step_denominator"), 30),
    (("native_seed", "completed_construction_clicks"), 1),
    (("native_seed", "start_completion_callbacks"), 2),
    (("native_seed", "start_extra_hangar_dwell"), 1),
    (("native_seed", "start_world_updates_after"), "1"),
    (("native_seed", "start_thread_id"), 43),
    (("native_seed", "start_hangar_onloop_executed"), 1),
    (("native_seed", "start_game_returns"), 0),
    (("creation", "world_updates_after_start"), "1"),
    (("clock", "current_world_updates"), "91"),
    (("handoff", "world_updates"), "89"),
    (("intervals", 0, "actual_updates"), 29),
    (("intervals", 0, "status"), "menu_boundary"),
    (("intervals", 1, "start_world_updates"), "31"),
    (("intervals", 1, "end_world_updates"), 90),
    (("menu_stages", 0, "world_updates_after"), "1"),
    (("menu_stages", 1, "before"), "main_menu"),
    (("menu_stages", 1, "after"), "hangar"),
    (("active",), True), (("intervals",), []),
])
def test_bad_evidence_fails_closed(path, value):
    raw = good_receipt()
    target = raw["deterministic_setup"]
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    assert not receipt_proof(raw)["passed"]


def test_late_fixture_reseed_rejected():
    raw = good_receipt()
    raw["visual_challenge_fixture"]["rng_seed_applied_here"] = True
    assert not receipt_proof(raw)["passed"]


@pytest.mark.parametrize("kind", ["crew", "lost", "player", "enemy", "clone"])
@pytest.mark.parametrize("stage", ["arm", "reset"])
@pytest.mark.parametrize("value", [1, None, False])
def test_clean_start_rejects_nonempty_or_unproven_factory(kind, stage, value):
    raw = good_receipt()
    raw["deterministic_setup"]["native_seed"][f"factory_{kind}_before_{stage}"] = value
    assert not receipt_proof(raw)["passed"]


def test_all_missing_receipts_are_rejected():
    assert not receipt_proof({})["passed"]


def test_fixture6_has_no_random_seed_call():
    assert "setRandomSeed(" not in candidate_challenges.FIXTURE_LUA
    assert "rng_seed_applied_here=false" in candidate_challenges.FIXTURE_LUA
    assert "visual_requested_frames==0" in candidate_challenges.FIXTURE_LUA


def test_session_writes_explicit_optin_once_and_archives(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(setup_session.AgentSession, "_write_action_atomic", lambda self, p: sent.append(p))
    monkeypatch.setattr(setup_session.time, "sleep", lambda _: None)
    session = SetupSession(tmp_path)
    session.configure_setup(tmp_path, .35)
    original = {"seq": 1, "advance_frames": 0, "actions": [{"type": "start_game", "mode": "new", "seed": 1}]}
    session._write_action_atomic(original)
    assert "benchmark_setup" not in original
    assert sent[0]["benchmark_setup"] == {"version": 1, "fresh": True, "seed": 1}
    session._write_action_atomic({"seq": 2, "advance_frames": 30, "actions": []})
    assert "benchmark_setup" not in sent[1]
    with pytest.raises(RuntimeError, match="Only one"):
        session._write_action_atomic(original)
    assert len(sent) == 2
    audit = json.loads((tmp_path / "deterministic-setup-session.json").read_text())
    assert len(audit["packets"]) == 2 and audit["deliberate_setup_delay_seconds"] == .35


def test_failed_native_receipt_aborts_wait_without_retry(tmp_path, monkeypatch):
    session = SetupSession(tmp_path)
    session.configure_setup(tmp_path, 0)
    observed = SimpleNamespace(last_action_seq=1, raw={"deterministic_setup": {"phase": "failed", "error": "bad seed"}})
    monkeypatch.setattr(session.client, "read_latest", lambda: observed)
    with pytest.raises(RuntimeError, match="bad seed"):
        session._wait_for(lambda obs: False, timeout=.1)
    assert json.loads((tmp_path / "deterministic-setup-session.json").read_text())["observations"]


def good_packets():
    return [{"packet": packet} for packet in [
        {"seq": 1, "advance_frames": 0, "benchmark_setup": {"version": 1, "fresh": True, "seed": 1},
            "actions": [{"type": "start_game", "mode": "new", "seed": 1}]},
        {"seq": 2, "advance_frames": 30, "actions": []},
        {"seq": 3, "advance_frames": 60, "actions": [{"type": "choose_event", "choice_index": 0}]},
        {"seq": 4, "advance_frames": 0, "observation_mode": "visual-v1", "actions": []}]]


def test_archived_packets_match_exact_intervals():
    assert packet_proof(good_receipt(), good_packets())["passed"]


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "budget", "handoff", "sequence"])
def test_packet_receipt_mismatch_rejected(mutation):
    packets = good_packets()
    if mutation == "drop":
        packets.pop(1)
    elif mutation == "duplicate":
        packets.insert(1, copy.deepcopy(packets[1]))
    elif mutation == "budget":
        packets[1]["packet"]["advance_frames"] = 29
    elif mutation == "handoff":
        packets[-1]["packet"]["seq"] = 5
    else:
        packets[1]["packet"]["seq"] = 7
    assert not packet_proof(good_receipt(), packets)["passed"]


def test_pending_world_is_not_a_ready_start(tmp_path, monkeypatch):
    session = SetupSession(tmp_path)
    session.configure_setup(tmp_path, 0)
    observations = iter([
        SimpleNamespace(last_action_seq=1, raw={"game_started": True,
            "deterministic_setup": {"phase": "starting"}}),
        SimpleNamespace(last_action_seq=1, raw={"game_started": True,
            "deterministic_setup": {"phase": "ready"}})])
    monkeypatch.setattr(session.client, "read_latest", lambda: next(observations))
    monkeypatch.setattr(setup_session.time, "sleep", lambda _: None)
    result = session._wait_for(lambda obs: obs.raw["game_started"], timeout=.1)
    assert result.raw["deterministic_setup"]["phase"] == "ready"
    recorded = json.loads((tmp_path / "deterministic-setup-session.json").read_text())
    assert recorded["observations"][0]["receipt"]["phase"] == "starting"




@pytest.mark.parametrize("field", ["start_completion_callbacks", "start_game_calls", "start_hangar_onloop_executed"])
def test_boolean_native_count_cannot_pass_integer_proof(field):
    raw = good_receipt()
    raw["deterministic_setup"]["native_seed"][field] = bool(raw["deterministic_setup"]["native_seed"][field])
    assert not receipt_proof(raw)["passed"]


def test_acknowledged_fresh_start_requires_receipt(tmp_path, monkeypatch):
    session = SetupSession(tmp_path)
    session.configure_setup(tmp_path)
    session.fresh_seq = 4
    observations = iter([SimpleNamespace(last_action_seq=3, raw={"game_started": True}),
        SimpleNamespace(last_action_seq=4, raw={"game_started": True})])
    monkeypatch.setattr(session.client, "read_latest", lambda: next(observations))
    monkeypatch.setattr(setup_session.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="lacks deterministic"):
        session._wait_for(lambda obs: True, timeout=.1)
    assert json.loads((tmp_path / "deterministic-setup-session.json").read_text())["observations"][-1]["failed_observation"]


def first_frame(tmp_path):
    raw = good_receipt()
    raw["visual"].update(frame_id=7, capture_id="capture7", simulated_updates="90",
        visual_clock_version=2, fixed_step_numerator=1, fixed_step_denominator=60)
    image = tmp_path / "first.png"
    image.write_bytes(b"actual capture bytes")
    return SimpleNamespace(observation=SimpleNamespace(raw=raw, last_action_seq=4), image_path=image,
        reference={**raw["visual"], "action_seq": 4, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()})


def test_first_image_bytes_and_native_packet_identity(tmp_path):
    frame = first_frame(tmp_path)
    assert setup_session.first_capture_proof(frame, good_packets())["passed"]
    frame.image_path.write_bytes(b"changed image")
    assert not setup_session.first_capture_proof(frame, good_packets())["passed"]


@pytest.mark.parametrize("mutation", ["sequence", "frame", "clock", "receipt", "packet"])
def test_first_image_refuses_unjoined_evidence(tmp_path, mutation):
    frame = first_frame(tmp_path)
    packets = good_packets()
    if mutation == "sequence":
        frame.reference["action_seq"] = 5
    elif mutation == "frame":
        frame.reference["frame_id"] = 8
    elif mutation == "clock":
        frame.reference["simulated_updates"] = "91"
    elif mutation == "receipt":
        frame.observation.raw.pop("deterministic_setup")
    else:
        packets[-1]["packet"]["actions"] = [{"type": "key", "key": "SPACE"}]
    assert not setup_session.first_capture_proof(frame, packets)["passed"]


@pytest.mark.parametrize("bad", ["receipt", "image", "fixture"])
def test_production_trial_never_constructs_actor_before_admission(tmp_path, monkeypatch, bad):
    from contextlib import contextmanager
    from test_visual_challenges import initial
    challenge = candidate_challenges
    frame = first_frame(tmp_path)
    raw = initial("fire-crew-recovery")
    raw["visual"].update(frame.observation.raw["visual"])
    frame.observation.raw = raw
    frame.observation.last_action_seq = 4
    if bad == "receipt":
        raw["deterministic_setup"]["native_seed"]["native_seed_applications"] = 2
    elif bad == "image":
        frame.reference["sha256"] = "wrong"
    else:
        raw["visual_challenge_fixture"]["applied_before_first_capture"] = False
    class Protected:
        def __init__(self, user, backup, bridge):
            self.backup = backup
        @contextmanager
        def protected(self):
            try:
                yield self
            finally:
                self.backup.mkdir(parents=True)
                (self.backup / "restoration.json").write_text('{"verified":true}')
        def launch(self):
            pass
    monkeypatch.setattr(challenge, "ProtectedGame", Protected)
    monkeypatch.setattr(challenge, "ftl_user_folder", lambda: tmp_path / "user")
    monkeypatch.setattr(challenge, "runtime_fingerprint", lambda root: {"native_build": {"matches_installed_dll": True}})
    monkeypatch.setattr(challenge, "AgentSession", lambda **kw: SimpleNamespace(setup_packets=good_packets()))
    monkeypatch.setattr(challenge, "prepare", lambda *args: None)
    monkeypatch.setattr(challenge, "VisualSession", lambda *args: SimpleNamespace(capture=lambda: frame))
    monkeypatch.setattr(challenge, "verify_visual_setup", lambda *args: {"verified": True})
    called = []
    monkeypatch.setattr(challenge, "CodexVisualAgent", lambda **kwargs: called.append("actor"))
    monkeypatch.setattr(challenge, "run_loop", lambda *args, **kw: called.append("loop"))
    args = challenge.parser().parse_args([])
    out = tmp_path / "trial"
    result = challenge.run_trial(args, "fire-crew-recovery", 1, out, {"path": "never-called"}, None)
    assert called == []
    assert result["outcome_category"] == "infrastructure_failure"
    assert result["save_restoration_verified"] is True
    trajectory = challenge.load_trajectory(out / "trajectory.jsonl")
    assert any(row["kind"] == "fixture_setup" and row["visual"]["before"] == frame.reference for row in trajectory)
    assert not any(row["kind"] == "step" for row in trajectory)
    assert trajectory[-1]["reason"] == "challenge_setup_error"
    assert (out / "initial-fixture-capture.json").is_file()
    if bad != "fixture":
        assert json.loads((out / "deterministic-setup-admission.json").read_text())["passed"] is False
    archived = json.loads((out / "run.json").read_text())
    assert archived["fixture_version"] == 6
    assert "dist/" not in Path(challenge.__file__).read_text()
