"""Visual transport must never dispatch a decision against a stale screenshot."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import struct
import zlib

import pytest

from ftl_bench.observation import Observation
from ftl_bench.visual_session import ExternalInputInterference, VisualSession, VisualTransportError


def png(width=80, height=60):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\0\0" * width) * height)) + chunk(b"IEND", b""))


def observed(seq=1, **updates):
    visual = {"visual_io_version": 1, "paused": True, "action_seq": seq,
              "visual_clock_version": 2, "world_updates": "0", "fixed_step_numerator": 1, "fixed_step_denominator": 60,
              "capture_id": seq, "frame_id": f"frame-{seq}", "path": "capture.png",
              "width": 80, "height": 60, "coordinate_space": "client",
              "external_input_generation": "0", "external_input_detected": False,
              "requested_frames": 0, "actual_frames": 0, "input_feedback": [], **updates}
    visual.setdefault("simulated_updates", visual["world_updates"])
    return Observation.from_dict({"schema_version": 3, "tick": seq, "seed": 1,
                                  "game_started": True, "paused": True,
                                  "last_action_seq": seq, "visual": visual,
                                  "capabilities": {"external_input_guard": True, "visual_clock_version": 2,
                                                   "fixed_step_numerator": 1, "fixed_step_denominator": 60,
                                                   "simulated_updates": visual["world_updates"], "world_updates": visual["world_updates"]}})


class FakeSession:
    step_timeout = 1

    def __init__(self, folder):
        self.user_folder = folder
        self.action_seq = 0
        self.current = observed(0)
        self.after = observed(1)
        self.latest_override = None
        self.packets = []

    def _sync_seq(self):
        self.action_seq = max(self.action_seq, self.current.last_action_seq)
        return self.current

    def _write_action_atomic(self, packet):
        self.packets.append(deepcopy(packet))

    def _wait_for(self, predicate, timeout):
        if not predicate(self.after):
            raise TimeoutError("ack absent")
        self.current = self.after
        return self.after

    def observe(self):
        return self.latest_override or self.current


@pytest.fixture
def transport(tmp_path):
    save = tmp_path / "save"
    save.mkdir()
    (save / "capture.png").write_bytes(png())
    return VisualSession(FakeSession(save), tmp_path / "run")


def test_capture_archives_exact_pixels_and_step_accounts_for_only_delivered_input(transport):
    first = transport.capture()
    session = transport.session
    assert first.image_path.read_bytes() == (session.user_folder / "capture.png").read_bytes()
    assert first.reference["sha256"] == hashlib.sha256(first.image_path.read_bytes()).hexdigest()
    assert first.reference["visual_clock_version"] == 2 and first.reference["world_updates"] == "0"
    assert session.packets == [{"seq": 1, "advance_frames": 0, "actions": [], "observation_mode": "visual-v1"}]
    action = {"type": "move", "x": 5, "y": 8}
    session.after = observed(2, requested_frames=120, actual_frames=42, world_updates="42",
                             input_feedback=[{"index": 0, "type": "move", "status": "delivered"}])
    second = transport.step(first, [action], 120)
    assert second.capture_id == 2
    assert second.reference["action_seq"] == 2
    assert second.reference["world_updates"] == "42"
    assert second.image_path != first.image_path
    assert session.packets[-1] == {"seq": 2, "advance_frames": 120, "actions": [action],
                                    "observation_mode": "visual-v1", "expected_capture_id": 1,
                                    "expected_external_input_generation": "0"}


@pytest.mark.parametrize("changed", [{"capture_id": 999}, {"frame_id": "other"}, {"width": 99},
                                     {"path": "other.png"}, {"action_seq": 2}, {"paused": False},
                                     {"world_updates": "1"}])
def test_stale_capture_never_dispatches_input(transport, changed):
    first = transport.capture()
    transport.session.current = observed(1, **changed)
    prior = list(transport.session.packets)
    with pytest.raises(VisualTransportError, match="Stale screenshot"):
        transport.step(first, [{"type": "key", "key": "escape", "modifiers": []}], 0)
    assert transport.session.packets == prior


@pytest.mark.parametrize("change", ["changed", "deleted"])
def test_changed_archived_image_never_dispatches_input(transport, change):
    first = transport.capture()
    if change == "changed":
        first.image_path.write_bytes(png(81, 60))
    else:
        first.image_path.unlink()
    with pytest.raises(VisualTransportError, match="Archived decision screenshot"):
        transport.step(first, [], 1)
    assert len(transport.session.packets) == 1


@pytest.mark.parametrize("updates", [
    {"requested_frames": 4}, {"requested_frames": False}, {"actual_frames": 31}, {"actual_frames": True},
    {"input_feedback": []}, {"input_feedback": [None]},
    {"input_feedback": [{"index": True, "type": "move", "status": "delivered"}]},
    {"input_feedback": [{"index": 0, "type": "click", "status": "delivered"}]},
    {"input_feedback": [{"index": 0, "type": "move", "status": "success"}]},
    {"capture_id": 1}, {"frame_id": "frame-1"},
])
def test_bad_acknowledgement_aborts_without_retry_or_archiving_misleading_after_image(transport, updates):
    first = transport.capture()
    kwargs = {"requested_frames": 30, "actual_frames": 20, "world_updates": "20",
              "input_feedback": [{"index": 0, "type": "move", "status": "delivered"}], **updates}
    transport.session.after = observed(2, **kwargs)
    with pytest.raises(VisualTransportError):
        transport.step(first, [{"type": "move", "x": 1, "y": 1}], 30)
    assert len(transport.session.packets) == 2  # the original request, never a retry
    assert len(list(transport.screens.glob("*.png"))) == 1


@pytest.mark.parametrize("updates", [{"capture_id": 99}, {"frame_id": "different"},
                                     {"path": "another.png"}, {"height": 61}, {"world_updates": "1"}])
def test_capture_identity_changed_during_copy_is_rejected(transport, updates):
    transport.session.latest_override = observed(1, **updates)
    with pytest.raises(VisualTransportError, match="changed while archiving"):
        transport.capture()
    assert not list(transport.screens.iterdir())


@pytest.mark.parametrize("path", ["..\\escape.png", "..//escape.png"])
def test_native_image_path_must_stay_under_save_directory(transport, path):
    # Windows treats either separator as a path separator. On POSIX use its form.
    if "\\" in path and Path("a\\b").name == "a\\b":
        pytest.skip("Windows-specific path separator")
    transport.session.after = observed(1, path=path)
    with pytest.raises(VisualTransportError, match="escapes"):
        transport.capture()


@pytest.mark.parametrize("actions,advance", [([None], 0), ([{"type": "native_cheat"}], 0), ([], True), ([], 601)])
def test_malformed_direct_transport_calls_never_dispatch(transport, actions, advance):
    first = transport.capture()
    with pytest.raises(ValueError):
        transport.step(first, actions, advance)
    assert len(transport.session.packets) == 1


@pytest.mark.parametrize("changed", [{"external_input_detected": True, "external_input_generation": "1"},
                                     {"external_input_detected": True}, {"external_input_generation": "1"}])
def test_external_input_during_model_inference_blocks_dispatch_without_recapture(transport, changed):
    first = transport.capture()
    transport.session.current = observed(1, **changed)
    with pytest.raises(ExternalInputInterference) as caught:
        transport.step(first, [{"type": "key", "key": "escape", "modifiers": []}], 60)
    assert caught.value.dispatched is False
    assert caught.value.evidence["expected_generation"] == "0"
    assert len(transport.session.packets) == 1
    assert len(list(transport.screens.iterdir())) == 1


def test_external_input_during_native_dispatch_aborts_even_before_ack_is_ready(transport):
    first = transport.capture()
    # The event is published while the previous sequence is still acknowledged.
    transport.session.after = observed(1, external_input_detected=True, external_input_generation="1")
    with pytest.raises(ExternalInputInterference) as caught:
        transport.step(first, [{"type": "move", "x": 1, "y": 1}], 60)
    assert caught.value.dispatched is True
    assert len(transport.session.packets) == 2  # sent once; never retry
    assert len(list(transport.screens.iterdir())) == 1


def test_external_input_during_archive_does_not_save_a_contaminated_image(transport):
    transport.session.latest_override = observed(1, external_input_detected=True, external_input_generation="1")
    with pytest.raises(ExternalInputInterference):
        transport.capture()
    assert not list(transport.screens.iterdir())


def test_sticky_external_flag_blocks_fresh_capture_and_cannot_be_reset_by_retry(transport):
    transport.session.current = observed(0, external_input_detected=True, external_input_generation="12")
    with pytest.raises(ExternalInputInterference):
        transport.capture()
    with pytest.raises(ExternalInputInterference):
        transport.capture()
    assert not transport.session.packets and not list(transport.screens.iterdir())


@pytest.mark.parametrize("guard", [None, False, 1])
def test_guard_capability_is_required_before_first_capture_dispatch(transport, guard):
    transport.session.current.raw["capabilities"]["external_input_guard"] = guard
    with pytest.raises(VisualTransportError, match="guard capability"):
        transport.capture()
    assert not transport.session.packets


@pytest.mark.parametrize("value", [None, 0, False, "", "nan", "1.0"])
def test_missing_or_malformed_guard_snapshot_is_not_accepted(transport, value):
    transport.session.after = observed(1, external_input_generation=value)
    with pytest.raises(VisualTransportError, match="guard snapshot"):
        transport.capture()
    assert not list(transport.screens.iterdir())


@pytest.mark.parametrize("version", [None, 0, 1, 3, True, "2"])
def test_pause_only_runtime_cannot_dispatch_initial_capture(transport, version):
    transport.session.current.raw["capabilities"]["visual_clock_version"] = version
    with pytest.raises(VisualTransportError, match="clock version 2 capability"):
        transport.capture()
    assert not transport.session.packets and not list(transport.screens.iterdir())


@pytest.mark.parametrize("version", [None, 0, 1, 3, True, "2"])
def test_clock_snapshot_version_required_once_snapshot_exists(transport, version):
    transport.session.current.raw["visual"]["visual_clock_version"] = version
    with pytest.raises(VisualTransportError, match="clock version 2 snapshot"):
        transport.capture()
    assert not transport.session.packets


def test_first_capture_can_start_without_previous_visual_snapshot(transport):
    del transport.session.current.raw["visual"]
    assert transport.capture().reference["world_updates"] == "0"


@pytest.mark.parametrize("section", ["capabilities", "visual"])
@pytest.mark.parametrize("counter", [None, 0, False, "", "1.0", "-1", "１２"])
def test_invalid_world_counter_is_rejected_before_dispatch(transport, section, counter):
    transport.session.current.raw[section]["world_updates"] = counter
    with pytest.raises(VisualTransportError, match="world-update counter"):
        transport.capture()
    assert not transport.session.packets


@pytest.mark.parametrize("stage", ["inference", "archive"])
def test_live_world_counter_moving_beyond_screenshot_is_rejected(transport, stage):
    first = transport.capture()
    changed = observed(1)
    changed.raw["capabilities"]["world_updates"] = "1"
    changed.raw["capabilities"]["simulated_updates"] = "1"
    if stage == "inference":
        transport.session.current = changed
        action = lambda: transport.step(first, [], 0)
    else:
        transport.session.latest_override = changed
        action = lambda: transport._archive(first.observation)
    with pytest.raises(VisualTransportError, match="World updated beyond"):
        action()
    assert len(transport.session.packets) == 1
    assert len(list(transport.screens.iterdir())) == 1


@pytest.mark.parametrize("counter,actual,requested", [("19", 20, 30), ("21", 20, 30),
                                                       ("1", 0, 0), ("0", 1, 30)])
def test_world_counter_delta_must_equal_actual_frames(transport, counter, actual, requested):
    first = transport.capture()
    transport.session.after = observed(2, requested_frames=requested, actual_frames=actual, world_updates=counter)
    with pytest.raises(VisualTransportError, match="counter disagrees with actual_frames"):
        transport.step(first, [], requested)
    assert len(transport.session.packets) == 2
    assert len(list(transport.screens.iterdir())) == 1


def test_world_counter_must_not_reset_between_captures(transport):
    transport.session.current = observed(0, world_updates="100")
    transport.session.after = observed(1, world_updates="100")
    first = transport.capture()
    transport.session.after = observed(2, requested_frames=30, actual_frames=20, world_updates="20")
    with pytest.raises(VisualTransportError, match="counter disagrees with actual_frames"):
        transport.step(first, [], 30)
    assert len(transport.session.packets) == 2


def test_authorized_advance_can_progress_live_counter_before_capture_acknowledgement(transport):
    first = transport.capture()
    intermediate = observed(1)
    intermediate.raw["capabilities"]["world_updates"] = "5"
    intermediate.raw["capabilities"]["simulated_updates"] = "5"
    intermediate.paused = False
    after = observed(2, requested_frames=30, actual_frames=7, world_updates="7")

    def wait(predicate, timeout):
        assert predicate(intermediate) is False
        assert predicate(after) is True
        transport.session.current = after
        return after

    transport.session._wait_for = wait
    assert transport.step(first, [], 30).reference["world_updates"] == "7"


def test_reference_clock_identity_cannot_be_mutated(transport):
    first = transport.capture()
    first.reference["world_updates"] = "100"
    with pytest.raises(VisualTransportError, match="visual clock identity"):
        transport.step(first, [], 0)
    assert len(transport.session.packets) == 1


@pytest.mark.parametrize("section", ["capabilities", "visual"])
@pytest.mark.parametrize("key,value", [("fixed_step_numerator", None), ("fixed_step_numerator", True),
    ("fixed_step_numerator", 2), ("fixed_step_denominator", 30), ("fixed_step_denominator", "60"),
    ("fixed_step_denominator", 60.0), ("simulated_updates", None), ("simulated_updates", "1")])
def test_fixed_step_contract_is_required_before_any_dispatch(transport, section, key, value):
    transport.session.current.raw[section][key] = value
    with pytest.raises(VisualTransportError):
        transport.capture()
    assert not transport.session.packets and not list(transport.screens.iterdir())


def test_fixed_step_snapshot_identity_is_archived_and_bound_during_model_inference(transport):
    before = transport.capture()
    assert {k: before.reference[k] for k in ("fixed_step_numerator", "fixed_step_denominator", "simulated_updates")} == {
        "fixed_step_numerator": 1, "fixed_step_denominator": 60, "simulated_updates": "0"}
    before.reference["simulated_updates"] = "1"
    with pytest.raises(VisualTransportError, match="visual clock identity"):
        transport.step(before, [], 0)
    assert len(transport.session.packets) == 1


def test_fixed_step_change_during_authorized_advance_cannot_acknowledge_old_budget(transport):
    before = transport.capture()
    transport.session.after = observed(2, requested_frames=30, actual_frames=30, world_updates="30")
    transport.session.after.raw["visual"]["fixed_step_denominator"] = 30
    with pytest.raises(VisualTransportError, match="1/60"):
        transport.step(before, [], 30)
    assert len(transport.session.packets) == 2 and len(list(transport.screens.iterdir())) == 1
