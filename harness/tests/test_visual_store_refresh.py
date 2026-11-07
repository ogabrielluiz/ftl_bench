"""Offline checks for the protected native store-refresh probe's evidence gates."""
import hashlib
import json
import pytest

import validate_visual_store_refresh as probe
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory
from ftl_bench.visual_session import VisualFrame
from test_visual_session import observed, png


class ScriptedStore:
    def __init__(self, output, *, stale=False, fault=None):
        self.output, self.stale, self.fault = output, stale, fault
        self.seq, self.world, self.phase = 4, 0, 0
        self.hull, self.scrap, self.fuel, self.quote = 30, 30, 16, None
        self.place = {"x": 88, "y": 152}
        self.open = self.jumping = self.choice = False
        self.last_edit = None
        self.armed = None
        self.setup_packets = []
        (output / "screens").mkdir()

    def arm_fixture(self, phase):
        assert self.armed is None
        self.armed = phase

    def capture(self):
        return self.frame([], 0, 0)

    def frame(self, actions, requested, actual):
        image = self.output / "screens" / f"{self.seq}.png"
        image.write_bytes(png(1280, 720))
        feedback = [{"index": index, "type": action["type"], "status": "delivered"}
                    for index, action in enumerate(actions)]
        if self.fault == "input" and self.phase == 2 and actions:
            feedback.append({"index": 1, "type": "key", "status": "delivered"})
        zero_mutation = self.phase == 2 and not self.open and self.hull == 22
        world = self.world + int(self.fault == "world" and zero_mutation)
        timer = self.world / 60 + int(self.fault == "timer" and zero_mutation)
        generation = "1" if self.fault == "guard" and zero_mutation else "0"
        obs = observed(self.seq, width=1280, height=720, world_updates=str(world),
                       simulated_updates=str(world), requested_frames=requested, actual_frames=actual,
                       external_input_generation=generation, external_input_detected=False, input_feedback=feedback)
        obs.raw.update(
            store_refresh_fixture={"phase": self.phase, "last_edit": self.last_edit, "running_time": timer},
            visual_evaluator={"store_open": self.open, "player_jumping": self.jumping,
                              "choice_window_open": self.choice,
                              "blocked_reason": "choice_box_open" if self.choice else
                                                "store_open" if self.open and not self.jumping else ""},
            player_ship={"hull": {"current": self.hull, "max": 30},
                         "resources": {"fuel": self.fuel, "scrap": self.scrap, "missiles": 8}},
            map={"current_pos": self.place},
        )
        if self.quote is not None:
            obs.raw["store"] = {"buy": [
                {"name": "Missile", "i": 7, "price": 6, "count": 6},
                {"name": "Repair Partial Hull", "i": 9, "price": 2, "count": 1},
                {"name": "Repair Entire Hull", "i": 10, "price": self.quote, "count": 1},
            ]}
        if self.choice:
            obs.raw["event"] = {"dialog_keys": 1, "selected_choice": -1,
                                "choices": [{"index": 0, "text": "Continue...", "enabled": True, "disabled": False}]}
        ref = {"path": image.relative_to(self.output).as_posix(), "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
               "width": 1280, "height": 720, "capture_id": self.seq}
        return VisualFrame(obs, image, ref, self.seq)

    def step(self, before, actions, requested):
        self.seq += 1
        actual = 0
        if self.armed is not None:
            assert not self.open and not actions and requested == 0
            assert self.armed == self.phase + 1
            self.armed = None
            self.phase += 1
            before_hull = self.hull
            self.hull = (27, 22)[self.phase - 1]
            self.last_edit = {"seq": self.seq, "before": before_hull, "after": self.hull}
            if self.fault == "closed-cache" and self.phase == 2:
                self.quote = 16
        elif actions:
            click = actions[0]
            assert actions == [{"type": "click", "x": click["x"], "y": click["y"],
                                "button": "left", "modifiers": []}]
            point = click["x"], click["y"]
            if point == probe.COORDINATES["continue"]:
                assert self.choice and requested == 1
                self.choice, actual, self.quote = False, 1, 6
            elif point == probe.COORDINATES["close"]:
                assert self.open and requested == 0
                self.open = False
            elif point == probe.COORDINATES["open"]:
                assert not self.open and requested == 0
                self.open = True
                self.quote = 6 if self.stale else 16
            elif point == probe.COORDINATES["repair-all"]:
                assert self.open and requested == 0
                self.hull = 30
                self.scrap -= self.quote if self.fault != "wrong-charge" else 6
            else:
                pytest.fail(f"Unexpected click {point}")
        elif requested and self.world == 0:
            self.jumping, self.fuel, self.place, actual = True, 15, None, 120
        elif requested and self.world == 120:
            self.open, actual = True, 15
        elif requested and self.jumping and self.fault != "hidden-warp":
            self.jumping, self.choice, actual, self.place = False, True, 108, {"x": 49, "y": 231}
        self.world += actual
        return self.frame(actions, requested, actual)


def execute(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(probe, "packet_proof", lambda *args: {"passed": True})
    monkeypatch.setattr(probe, "receipt_proof", lambda *args, **kwargs: {"passed": True})
    monkeypatch.setattr(probe.time, "sleep", lambda _seconds: None)
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl", {"model_calls": 0})
    scripted = ScriptedStore(tmp_path, **kwargs)
    return probe.run_probe(scripted, scripted, recorder, tmp_path,
                           {"x": 88, "y": 152}, {"x": 49, "y": 231}, 16)


@pytest.mark.parametrize(("stale", "status", "charge"), [(False, "passed", 16), (True, "reproduced", 6)])
def test_store_refresh_distinguishes_cached_quote_and_actual_charge(tmp_path, monkeypatch, stale, status, charge):
    proof = execute(tmp_path, monkeypatch, stale=stale)
    assert proof["status"] == status and proof["model_calls"] == 0 and proof["fixture_only"] is True
    assert proof["valid_for_model_comparison"] is False and proof["valid_for_full_game_comparison"] is False
    assert proof["repair"]["initial"]["all"]["price"] == 6
    assert proof["repair"]["reopened"]["all"]["price"] == proof["repair"]["actual_charge"] == charge
    assert proof["repair"]["expected_charge"] == 16
    assert proof["repair"]["hull_before"] == {"current": 22, "max": 30}
    assert proof["repair"]["hull_after"] == {"current": 30, "max": 30}
    steps = {row["label"]: row for row in proof["steps"]}
    hidden = steps["seek-hidden-store-in-warp"]["after"]
    assert hidden["evaluator"]["store_open"] and hidden["evaluator"]["player_jumping"]
    assert steps["advance-through-hidden-store"]["after"]["clock"]["actual_frames"] == 108
    assert steps["ordinary-continue-one-frame"]["after"]["clock"]["actual_frames"] == 1
    assert steps["visible-store-blocks-advance"]["after"]["clock"]["actual_frames"] == 0
    for label in ("closed-hull-27-to-22", "ordinary-store-reopen-zero-frame", "ordinary-fix-all-zero-frame"):
        after = steps[label]["after"]
        assert after["clock"]["world_updates"] == "244" and after["fixture"]["running_time"] == 244 / 60
        ref = after["capture"]
        assert hashlib.sha256((tmp_path / ref["path"]).read_bytes()).hexdigest() == ref["sha256"]
    assert not any(row.get("model") for row in load_trajectory(tmp_path / "trajectory.jsonl"))


@pytest.mark.parametrize(("fault", "message"), [
    ("input", "acknowledgements"), ("world", "world/frame"), ("timer", "timer"), ("guard", "guard"),
    ("closed-cache", "only the intended"), ("wrong-charge", "actual charge"),
    ("hidden-warp", "bounded natural arrival"),
])
def test_wrong_native_boundaries_fail_closed_and_retain_evidence(tmp_path, monkeypatch, fault, message):
    with pytest.raises(RuntimeError, match=message):
        execute(tmp_path, monkeypatch, fault=fault)
    proof = json.loads((tmp_path / "store-refresh-proof.json").read_text())
    assert proof["status"] == "error"
    assert proof["steps"][-1]["after"]["capture"]["path"]
    if fault == "wrong-charge":
        assert proof["repair"]["reopened"]["all"]["price"] == 16
        assert proof["repair"]["actual_charge"] == 6


def test_quote_requires_unique_native_repair_box_names_and_integral_price():
    one = {"name": "Repair Partial Hull", "i": 9, "price": 2, "count": 1}
    all_hull = {"name": "Repair Entire Hull", "i": 10, "price": 6, "count": 1}
    with pytest.raises(RuntimeError, match="ambiguous"):
        probe.repair_quotes({"store": {"buy": [one, all_hull, all_hull]}})
    with pytest.raises(RuntimeError, match="ambiguous"):
        probe.repair_quotes({"store": {"buy": [one, {**all_hull, "price": True}]}})


def test_fixture_appends_only_to_exact_production_bytes():
    production = b"local S={}\r\n"
    bridge = probe.fixture_bridge(production)
    assert bridge.startswith(production)
    assert b"store_refresh_fixture_phase" in bridge


def test_fixture_phase_is_one_capture_bound_zero_input_packet(monkeypatch):
    sent = []
    monkeypatch.setattr(probe.DeterministicSetupSession, "_write_action_atomic", lambda _self, packet: sent.append(packet))
    session = probe.StoreSetupSession.__new__(probe.StoreSetupSession)
    base = {"seq": 5, "observation_mode": "visual-v1", "actions": [], "advance_frames": 0,
            "expected_capture_id": "capture", "expected_external_input_generation": "0"}
    session.arm_fixture(1)
    with pytest.raises(RuntimeError, match="capture-bound"):
        session._write_action_atomic({**base, "advance_frames": 1})
    assert sent == []
    session._write_action_atomic(base)
    session._write_action_atomic({**base, "seq": 6})
    assert sent == [{**base, "store_refresh_fixture_phase": 1}, {**base, "seq": 6}]
