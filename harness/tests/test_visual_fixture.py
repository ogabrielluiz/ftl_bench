"""A store-to-jump fixture must prove each milestone, not just a changed location."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path

import pytest

from ftl_bench.cli import _bench_root
from ftl_bench.observation import Observation
from ftl_bench.visual_session import VisualFrame
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory

_spec = importlib.util.spec_from_file_location("validate_visual_live", _bench_root() / "scripts/validate_visual_live.py")
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def rows():
    start = {"player_ship": {"resources": {"fuel": 5, "scrap": 12}},
             "store": {"buy": [{"i": 6, "name": "FTL Fuel", "price": 3, "count": 3}]},
             "visual_evaluator": {"store_open": True, "map_open": False, "choice_open": False},
             "economy": {"navigation": {"can_jump": False, "drive_current": 20, "drive_max": 85}},
             "map": {"sector": 0, "current_pos": {"x": 0, "y": 0},
                     "connected_beacons": [{"pos_x": 10, "pos_y": 5}]}}
    observations = [deepcopy(start) for _ in range(7)]
    for obs in observations[1:]:
        obs["player_ship"]["resources"] = {"fuel": 6, "scrap": 9}
        obs["store"]["buy"][0]["count"] = 2
    for obs in observations[2:]:
        obs["visual_evaluator"]["store_open"] = False
    observations[3]["economy"]["navigation"].update(can_jump=True, drive_current=85)
    observations[4]["visual_evaluator"]["map_open"] = True
    observations[4]["economy"]["navigation"]["drive_current"] = 85
    for obs in observations[5:]:
        obs["player_ship"]["resources"]["fuel"] = 5
        obs["economy"]["navigation"]["drive_current"] = 0
    observations[6]["map"]["current_pos"] = {"x": 10, "y": 5}
    return [{"i": i, "kind": "step" if i else "reset", "obs": o,
             "visual": {"before": {"sha256": f"image-{i}"},
                        "inputs": [{"type": "click", "button": "left", "delivery": "delivered"}]},
             "model": {"provider": "codex", "tool_use": False,
                       "image": {"sha256": f"image-{i}"}, "events": [{"type": "turn.completed"}]}}
            for i, o in enumerate(observations)]


def test_store_fixture_proves_purchase_close_charge_map_and_connected_jump():
    result = fixture.validate_store_fixture(rows(), "fixture_goal_observed")
    assert result["status"] == "passed"
    assert all(result["checks"].values())
    assert result["valid_for_model_comparison"] is False
    assert result["evidence"] == {"fuel_purchase_records": [1], "store_close_records": [2], "jump_records": [6]}
    assert "CLOSE button" in result["limitations"][0]


def test_budget_before_warp_preserves_observed_charge_and_map_milestones():
    result = fixture.validate_store_fixture(rows()[:5], "decision_budget")
    assert result["status"] == "incomplete"
    assert result["checks"]["full_charge_observed_before_jump"]
    assert result["checks"]["star_map_open_observed"]
    assert not result["checks"]["jump_to_connected_beacon"]


@pytest.mark.parametrize("problem", [None, "sun", "hostile", "unknown_enemy", "injury", "missing_health", "missing_charge", "full_charge"])
def test_quiet_store_setup_requires_positive_native_prerequisite_evidence(problem):
    obs = {"map": {"hazard": "none"}, "economy": {"navigation": {"drive_current": 10, "drive_max": 85}},
           "player_ship": {"crew": [{"health_current": 100, "health_max": 100} for _ in range(3)]}}
    if problem == "sun":
        obs["map"]["hazard"] = "sun"
    elif problem == "hostile":
        obs["enemy_ship"] = {"hostile": True}
    elif problem == "unknown_enemy":
        obs["enemy_ship"] = {"blueprint": "UNKNOWN"}
    elif problem == "injury":
        obs["player_ship"]["crew"][0]["health_current"] = 90
    elif problem == "missing_health":
        obs["player_ship"]["crew"][0] = {}
    elif problem == "missing_charge":
        obs["economy"]["navigation"].pop("drive_current")
    elif problem == "full_charge":
        obs["economy"]["navigation"]["drive_current"] = 85
    obs.update(schema_version=3, tick=0, seed=1, game_started=True)
    assert fixture.quiet_store_prerequisite(Observation.from_dict(obs)) is (problem is None)


def test_pause_check_detects_sub_percent_oxygen_leak():
    before = {"paused": True, "player_ship": {"oxygen_pct": 99,
              "rooms": [{"room_id": 1, "oxygen": 98.796257019043}]}}
    after = deepcopy(before)
    after["player_ship"]["rooms"][0]["oxygen"] = 98.776257019043
    assert fixture.check_paused_world(before, after, same_capture=False)["checks"]["world_unchanged"] is False


@pytest.mark.parametrize("missing", ["price", "stock", "closure", "mouse_close", "charge", "map", "connection",
                                     "fuel_consumption", "cli_audit", "image_identity", "partial_start", "extra_purchase"])
def test_a_location_change_cannot_hide_missing_acceptance_evidence(missing):
    records = rows()
    if missing == "price":
        records[0]["obs"]["store"]["buy"][0]["price"] = 8
    elif missing == "stock":
        records[1]["obs"]["store"]["buy"][0]["count"] = 3
    elif missing == "closure":
        for record in records:
            record["obs"]["visual_evaluator"]["store_open"] = True
    elif missing == "mouse_close":
        records[2]["visual"]["inputs"] = [{"type": "key", "key": "escape", "delivery": "delivered"}]
    elif missing == "charge":
        records[3]["obs"]["economy"]["navigation"]["can_jump"] = False
    elif missing == "map":
        records[4]["obs"]["visual_evaluator"]["map_open"] = False
    elif missing == "connection":
        records[5]["obs"]["map"]["connected_beacons"] = [{"pos_x": 999, "pos_y": 999}]
    elif missing == "fuel_consumption":
        records[-1]["obs"]["player_ship"]["resources"]["fuel"] = 4
    elif missing == "cli_audit":
        records[1]["model"]["tool_use"] = True
    elif missing == "image_identity":
        records[1]["model"]["image"]["sha256"] = "different-image"
    elif missing == "partial_start":
        records[0]["obs"]["economy"]["navigation"]["drive_current"] = 85
    elif missing == "extra_purchase":
        records[2]["obs"]["player_ship"]["resources"]["fuel"] = 7
    result = fixture.validate_store_fixture(records, "fixture_goal_observed")
    assert result["status"] == "incomplete"
    assert not all(result["checks"].values())


def test_unknown_positions_do_not_count_as_travel():
    records = rows()
    records[-1]["obs"]["map"].pop("current_pos")
    assert fixture.validate_store_fixture(records, "fixture_goal_observed")["checks"]["jump_to_connected_beacon"] is False


def test_budget_exhaustion_remains_incomplete_even_with_other_evidence():
    assert fixture.validate_store_fixture(rows(), "decision_budget")["status"] == "incomplete"


def test_empty_trajectory_is_incomplete_instead_of_vacuous_pass():
    assert fixture.validate_store_fixture([], "fixture_goal_observed")["status"] == "incomplete"


def paused():
    return {"paused": True, "tick": 100, "render_count": 200, "last_action_seq": 5,
            "visual": {"capture_id": 4, "frame_id": "frame4"},
            "player_ship": {"hull": {"current": 30, "max": 30}, "resources": {"fuel": 16, "scrap": 0},
                            "oxygen_pct": 99.8},
            "economy": {"navigation": {"drive_current": 12, "drive_max": 85}},
            "ftl_score": 0, "ftl_score_components": {"ships_destroyed": 0, "scrap_collected": 0}}


def test_paused_proof_allows_render_ticks_but_requires_world_and_capture_identity():
    first = paused()
    later = deepcopy(first)
    later.update(tick=120, render_count=220)
    assert fixture.check_paused_world(first, later)["passed"]
    later["visual"]["capture_id"] += 1
    assert not fixture.check_paused_world(first, later)["passed"]
    later["last_action_seq"] += 1
    assert fixture.check_paused_world(first, later, same_capture=False)["passed"]


@pytest.mark.parametrize("changed", ["hull", "fuel", "drive", "oxygen", "score", "missing", "unpaused"])
def test_paused_proof_rejects_unverified_or_advancing_world(changed):
    first, later = paused(), paused()
    if changed == "hull":
        later["player_ship"]["hull"]["current"] -= 1
    elif changed == "fuel":
        later["player_ship"]["resources"]["fuel"] -= 1
    elif changed == "drive":
        later["economy"]["navigation"]["drive_current"] += 1
    elif changed == "oxygen":
        later["player_ship"]["oxygen_pct"] -= 0.1
    elif changed == "score":
        later["ftl_score"] += 1
    elif changed == "missing":
        first.pop("ftl_score")
        later.pop("ftl_score")
    else:
        later["paused"] = False
    assert fixture.check_paused_world(first, later)["passed"] is False


def test_capture_fixture_manifest_finishes_only_after_cleanup_and_uses_no_model(tmp_path, monkeypatch):
    output = tmp_path / "capture-fixture"
    state = paused()
    state.update(schema_version=3, seed=1, game_started=True)
    state["visual"].update(actual_frames=0, requested_frames=0, input_feedback=[])
    obs = Observation.from_dict(state)
    calls = []

    class Protected:
        def __init__(self, *args):
            pass

        @contextmanager
        def protected(self):
            yield self
            assert json.loads((output / "run.json").read_text())["status"] == "running"
            calls.append("restore")

        def launch(self):
            calls.append("launch")

    class Session:
        def __init__(self, **kwargs):
            pass

        def reset_episode(self, **kwargs):
            pass

        def reset(self):
            pass

        def observe(self):
            return obs

    class Transport:
        def __init__(self, session, directory):
            self.reference = {"path": "screens/first.png", "sha256": "first", "frame_id": "frame4"}

        def capture(self):
            return VisualFrame(obs, output / self.reference["path"], self.reference, 4)

        def step(self, before, actions, frames):
            assert frames == 0 and actions == [{"type": "move", "x": 5, "y": 5}]
            changed = deepcopy(state)
            changed["visual"].update(capture_id=5, frame_id="frame5",
                                    input_feedback=[{"index": 0, "type": "move", "status": "delivered"}])
            changed["last_action_seq"] += 1
            return VisualFrame(Observation.from_dict(changed), output / "second.png",
                               {**self.reference, "sha256": "second", "frame_id": "frame5"}, 5)

    monkeypatch.setattr(fixture, "ProtectedGame", Protected)
    monkeypatch.setattr(fixture, "AgentSession", Session)
    monkeypatch.setattr(fixture, "VisualSession", Transport)
    monkeypatch.setattr(fixture, "prepare_capture_world", lambda session, transport, recorder, output: transport.capture())
    monkeypatch.setattr(fixture, "CodexVisualAgent", lambda **kw: pytest.fail("capture fixture must not call a model"))
    monkeypatch.setattr(fixture, "runtime_fingerprint", lambda root: {"native_build": {"matches_installed_dll": True}})
    monkeypatch.setattr(fixture, "verify_normal_controls", lambda *args: {"normal_controls_fixture": True})
    monkeypatch.setattr(fixture.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))
    fixture.main(["--capture-only", "--output", str(output)])
    assert calls == ["launch", ("sleep", 2), "restore"]
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["status"] == "completed" and manifest["save_restoration"] == "verified"
    assert manifest["fixture_only"] and manifest["valid_for_model_comparison"] is False
    assert manifest["model"] is None and manifest["provider"] == "none"
    assert manifest["scenario_ids"] == ["VISUAL-FIXTURE-capture"]
    assert json.loads((output / "validation.json").read_text())["status"] == "passed"


@pytest.mark.parametrize("delayed_intro", [False, True])
def test_capture_setup_proves_active_oxygen_drain_using_only_normal_controls(tmp_path, monkeypatch, delayed_intro):
    def observation(oxygen, modal=False):
        state = paused()
        state.update(schema_version=3, seed=1, game_started=True, choice_box_open=modal,
                     event={"choices": [{"index": 7, "enabled": True}]})
        state["player_ship"].update(oxygen_pct=oxygen, systems=[{"id": 2, "power": 0}])
        return Observation.from_dict(state)
    calls = []

    class Session:
        def reset_episode(self, **kwargs):
            calls.append(("reset_episode", kwargs))
        def reset(self):
            return observation(100)
        def choose_event(self, index, frames):
            calls.append(("choose_event", index, frames))
            return observation(100)
        def step(self, actions, frames):
            calls.append((actions, frames))
            assert actions == [] and frames == 30
            return observation(100, modal=delayed_intro)

    class Transport:
        def capture(self):
            return VisualFrame(observation(100), tmp_path / "before.png",
                               {"width": 1280, "height": 720, "frame_id": "before"}, 1)
        def step(self, before, actions, frames):
            calls.append(("visual", actions, frames))
            after = observation(99.8)
            after.raw["visual"].update(actual_frames=60,
                input_feedback=[{"index": 0, "type": "click", "status": "delivered"}])
            return VisualFrame(after, tmp_path / "after.png",
                               {"width": 1280, "height": 720, "frame_id": "after"}, 2)

    monkeypatch.setattr(fixture.time, "sleep", lambda seconds: None)
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    final = fixture.prepare_capture_world(Session(), Transport(), recorder, tmp_path)
    assert final.observation.player_ship["oxygen_pct"] == 99.8
    expected = [("reset_episode", {"seed": 1}), ([], 30)]
    if delayed_intro:
        expected.append(("choose_event", 7, 30))
    expected.append(("visual", [{"type": "click", "x": 198, "y": 682, "button": "right", "modifiers": []}], 60))
    assert calls == expected
    proof = json.loads((tmp_path / "fixture.json").read_text())
    assert proof["state_overrides"] is False and proof["modal_open"] is False
    assert proof["oxygen_after"] < proof["oxygen_before"]
    visual_records = load_trajectory(recorder.path)[1:]
    assert [r["kind"] for r in visual_records] == ["reset", "step"]
    assert visual_records[1]["visual"]["advance"]["actual_frames"] == 60
    assert visual_records[1]["actions"][0]["button"] == "right"


def test_capture_fixture_rejects_uncalibrated_resolution_before_mouse_input(tmp_path):
    state = paused()
    state.update(schema_version=3, seed=1, game_started=True, choice_box_open=False)
    obs = Observation.from_dict(state)
    class Session:
        def reset_episode(self, **kwargs): pass
        def reset(self): return obs
        def step(self, actions, frames): return obs
    class Transport:
        def capture(self):
            return VisualFrame(obs, tmp_path / "image.png", {"width": 1600, "height": 900}, 1)
        def step(self, *args):
            pytest.fail("uncalibrated screenshot must not dispatch fixture inputs")
    with pytest.raises(RuntimeError, match="1280x720"):
        fixture.prepare_capture_world(Session(), Transport(), TrajectoryRecorder(tmp_path / "trajectory.jsonl"), tmp_path)
