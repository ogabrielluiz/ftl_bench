"""Offline acceptance checks for the separate protected sector/Wait diagnostic."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ftl_bench.cli import _bench_root
from ftl_bench.observation import Observation


def load_fixture():
    path = _bench_root() / "scripts/validate_visual_sector.py"
    spec = importlib.util.spec_from_file_location("visual_sector_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load_fixture()


def observed(mode="sector"):
    return {"schema_version": 3, "tick": 0, "seed": 1, "game_started": True,
            "paused": True, "choice_box_open": False,
            "player_ship": {"hull": {"current": 30, "max": 30},
                            "resources": {"fuel": 0 if mode == "wait" else 16}},
            "map": {"sector": 1, "current_pos": [10, 20]},
            "economy": {"fuel_recovery": {"waiting": False, "out_of_fuel": mode == "wait"},
                        "navigation": {"drive_current": 10, "drive_max": 10}},
            "visual": {"world_updates": "0", "actual_frames": 0},
            "visual_evaluator": {"map_open": False, "choice_open": False,
                                 "player_jumping": False},
            "visual_fixture": {"applied": True, "world_level": 0, "current_beacon": True,
                               "choosing_new_sector": False, "danger_zone": {"x": 0, "y": 0}}}


def test_idle_and_fresh_capture_must_detect_native_transition_leak():
    before = observed()
    after = deepcopy(before)
    assert fixture.freeze_proof(before, after)["passed"]
    after["visual_fixture"]["world_level"] = 1
    assert not fixture.freeze_proof(before, after)["passed"]
    after = deepcopy(before)
    after["visual"]["world_updates"] = "1"
    assert not fixture.freeze_proof(before, after)["passed"]
    after = deepcopy(before)
    after["economy"]["fuel_recovery"]["waiting"] = True
    assert not fixture.freeze_proof(before, after)["passed"]


def test_freeze_requires_observed_native_level_fuel_and_clock():
    for keys in (("visual_fixture", "world_level"), ("visual", "world_updates")):
        raw = observed()
        raw[keys[0]].pop(keys[1])
        assert not fixture.freeze_proof(raw, raw)["passed"]
    raw = observed()
    raw["player_ship"]["resources"].pop("fuel")
    assert not fixture.freeze_proof(raw, raw)["passed"]


def test_sector_acceptance_requires_fuel_sector_arrival_and_actual_updates():
    before = observed()
    after = deepcopy(before)
    after["visual_fixture"]["world_level"] = 1
    after["player_ship"]["resources"]["fuel"] = 15
    assert fixture.transition_proof("sector", before, after, 1)["passed"]
    assert not fixture.transition_proof("sector", before, after, 0)["passed"]
    for change in (lambda r: r["player_ship"]["resources"].update(fuel=16),
                   lambda r: r["visual_fixture"].update(world_level=2),
                   lambda r: r["visual_evaluator"].update(player_jumping=True),
                   lambda r: r["map"].update(current_pos=None)):
        invalid = deepcopy(after)
        change(invalid)
        assert not fixture.transition_proof("sector", before, invalid, 1)["passed"]


def test_wait_acceptance_requires_native_running_then_finished_in_same_sector():
    before = observed("wait")
    before["economy"]["fuel_recovery"]["waiting"] = True
    after = deepcopy(before)
    after["economy"]["fuel_recovery"]["waiting"] = False
    assert fixture.transition_proof("wait", before, after, 120)["passed"]
    assert not fixture.transition_proof("wait", before, after, 0)["passed"]
    assert not fixture.transition_proof("wait", after, after, 120)["passed"]
    after["visual_fixture"]["world_level"] = 1
    assert not fixture.transition_proof("wait", before, after, 120)["passed"]


@pytest.mark.parametrize("point", [(-1, 50), (1280, 50), (50, 720), (True, 2), (1.5, 2)])
def test_calibrated_click_rejects_invalid_pixels(point):
    frame = SimpleNamespace(reference={"width": 1280, "height": 720})
    with pytest.raises(ValueError):
        fixture.click_action(point, frame, (1280, 720))


def test_calibrated_click_requires_same_capture_dimensions():
    frame = SimpleNamespace(reference={"width": 1280, "height": 720})
    with pytest.raises(RuntimeError, match="Calibration size"):
        fixture.click_action((10, 20), frame, (1920, 1080))
    assert fixture.click_action((10, 20), frame, (1280, 720)) == {
        "type": "click", "x": 10, "y": 20, "button": "left", "modifiers": []}


class FakeTransport:
    """Controlled normal UI acknowledgements; no filesystem/game/model boundary."""
    def __init__(self, folder, mode="sector", progress=False):
        self.raw = observed(mode)
        self.mode = mode
        self.progress = progress
        self.inputs = []
        self.ordinal = 0
        self.folder = folder
        self.session = SimpleNamespace(observe=lambda: Observation.from_dict(deepcopy(self.raw)))

    def capture(self):
        self.ordinal += 1
        reference = {"width": 1280, "height": 720, "capture_id": self.ordinal,
                     "world_updates": self.raw["visual"]["world_updates"]}
        return SimpleNamespace(observation=Observation.from_dict(deepcopy(self.raw)),
                               reference=reference, image_path=self.folder / f"{self.ordinal}.png")

    def step(self, before, actions, frames):
        self.inputs.append((actions, frames))
        for action in actions:
            if action["type"] == "key":
                self.raw["visual_evaluator"]["map_open"] = True
            elif self.mode == "wait":
                self.raw["economy"]["fuel_recovery"]["waiting"] = True
            else:
                self.raw["visual_fixture"]["choosing_new_sector"] = True
        actual = 0
        if frames and self.progress:
            actual = 1
            self.raw["visual"]["world_updates"] = str(int(self.raw["visual"]["world_updates"]) + 1)
            if self.mode == "sector":
                self.raw["visual_fixture"]["world_level"] = 1
                self.raw["player_ship"]["resources"]["fuel"] = 15
            else:
                self.raw["economy"]["fuel_recovery"]["waiting"] = False
            self.progress = False
        self.raw["visual"]["actual_frames"] = actual
        self.raw["visual"]["input_feedback"] = [
            {"index": index, "type": action["type"], "status": "delivered"}
            for index, action in enumerate(actions)]
        return self.capture()


def run_offline(tmp_path, monkeypatch, args, transport):
    monkeypatch.setattr(fixture.time, "sleep", lambda _: None)
    recorder = SimpleNamespace(record=lambda *a, **kw: None)
    return fixture.run_fixture(args, transport.session, transport, recorder, tmp_path)


def test_missing_end_coordinate_archives_map_then_exits_without_simulation(tmp_path, monkeypatch):
    args = fixture.parser().parse_args([])
    transport = FakeTransport(tmp_path)
    result = run_offline(tmp_path, monkeypatch, args, transport)
    assert result["status"] == "incomplete" and "--end" in result["reason"]
    assert all(frames == 0 for _, frames in transport.inputs)
    assert transport.inputs[0][0] == [{"type": "key", "key": "j", "modifiers": []}]
    assert json.loads((tmp_path / "captures.json").read_text())[-1]["capture"]["capture_id"] == 3


def test_missing_neighbor_coordinate_archives_picker_then_stops(tmp_path, monkeypatch):
    args = fixture.parser().parse_args(["--end", "100", "200"])
    transport = FakeTransport(tmp_path)
    result = run_offline(tmp_path, monkeypatch, args, transport)
    assert result["status"] == "incomplete" and "--neighbor" in result["reason"]
    assert all(frames == 0 for _, frames in transport.inputs)
    assert result["calibration"]["visual_fixture"]["choosing_new_sector"] is True


@pytest.mark.parametrize("bad_feedback", [[], [{"index": 1, "type": "key", "status": "delivered"}],
                                          [{"index": 0, "type": "click", "status": "delivered"}]])
def test_capture_cannot_claim_delivery_without_matching_input_ack(tmp_path, monkeypatch, bad_feedback):
    args = fixture.parser().parse_args([])
    transport = FakeTransport(tmp_path)
    original_step = transport.step
    def wrong_ack(before, actions, frames):
        frame = original_step(before, actions, frames)
        frame.observation.raw["visual"]["input_feedback"] = bad_feedback
        return frame
    transport.step = wrong_ack
    with pytest.raises(RuntimeError, match="Native input was rejected"):
        run_offline(tmp_path, monkeypatch, args, transport)


@pytest.mark.parametrize("mode", ["sector", "wait"])
def test_bounded_zero_update_ack_is_failure_not_success(tmp_path, monkeypatch, mode):
    args = fixture.parser().parse_args(["--mode", mode, "--end", "100", "200",
                                       "--neighbor", "300", "400", "--wait", "500", "600"])
    transport = FakeTransport(tmp_path, mode)
    result = run_offline(tmp_path, monkeypatch, args, transport)
    assert result["status"] == "failed"
    assert not result["checks"]["native_transition"]["checks"]["explicit_world_updates"]
    assert [n for _, n in transport.inputs if n] == [1, 600]


@pytest.mark.parametrize("mode", ["sector", "wait"])
def test_only_explicit_native_progress_accepts_fixture(tmp_path, monkeypatch, mode):
    args = fixture.parser().parse_args(["--mode", mode, "--end", "100", "200",
                                       "--neighbor", "300", "400", "--wait", "500", "600"])
    transport = FakeTransport(tmp_path, mode, progress=True)
    result = run_offline(tmp_path, monkeypatch, args, transport)
    assert result["status"] == "passed"
    assert result["checks"]["native_transition"]["actual_frames"] == 1
    assert [n for _, n in transport.inputs if n] == [1]


def test_temporary_bridge_preserves_source_and_never_forces_travel_or_timers():
    source = b"-- production prefix\n"
    generated = fixture.fixture_bridge(source, "sector", "fixture-test")
    assert generated.startswith(source)
    assert b'currentLoc.beacon=true' in generated
    assert b'Hyperspace.ships.player.fuel_count=0' in generated
    assert b'local visualFixtureWriter=Hyperspace.benchmark_write_visual_observation' in generated
    for assignment in (b"finalSectorChoice=", b"readyToTravel=", b"worldLevel=", b"openTime=",
                       b"selectedChoice=", b"waiting.running=", b"frame_budget="):
        assert assignment not in generated


def test_temporary_wait_setup_uses_the_actual_player_manager_binding():
    lua = pytest.importorskip("lupa").LuaRuntime(unpack_returned_tuples=True)
    # world.playerShip is deliberately absent: the Lua API exposes the manager
    # through Hyperspace.ships.player, as the production observer already uses.
    lua.execute("""
      Hyperspace={App={world={bStartedGame=true,starMap={worldLevel=0}},
                          gui={choiceBoxOpen=false}},ships={player={fuel_count=16}}}
      _G.ftl_bench_state={observation_mode='visual-v1'}
      _G.ftl_bench_tick=function() end
      json={decode=function() return {} end,
            encode=function(obs) encoded_observation=obs; return 'encoded' end}
      Hyperspace.benchmark_write_visual_observation=function(payload) return payload end
    """)
    lua.execute(fixture.fixture_bridge(b"", "wait", "fuel-binding-regression").decode())
    lua.globals().ftl_bench_tick()
    assert lua.globals().Hyperspace.ships.player.fuel_count == 0
    assert lua.globals().Hyperspace.benchmark_write_visual_observation("{}") == "encoded"
    proof = lua.globals().encoded_observation.visual_fixture
    assert proof.applied is True and proof.setup_error is None
    assert proof.fuel == 0


def test_fixture_trajectory_is_visible_in_the_actual_typed_dashboard_replay(tmp_path, monkeypatch):
    import base64
    import hashlib
    from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory

    monkeypatch.syspath_prepend(str(_bench_root() / "adapter"))
    import ftl_live as live

    directory = tmp_path / "sector-fixture"
    directory.mkdir()
    (directory / "screens").mkdir()
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf9sAAAAASUVORK5CYII=")

    class RecordedTransport(FakeTransport):
        def capture(self):
            frame = super().capture()
            frame.image_path = directory / "screens" / f"{self.ordinal}.png"
            frame.image_path.write_bytes(png)
            frame.reference.update(path=f"screens/{self.ordinal}.png",
                                   frame_id=f"frame-{self.ordinal}",
                                   sha256=hashlib.sha256(png).hexdigest())
            return frame

    transport = RecordedTransport(directory)
    recorder = TrajectoryRecorder(directory / "trajectory.jsonl",
        {"track": "visual-v1", "observation_mode": "image", "fixture_only": True})
    monkeypatch.setattr(fixture.time, "sleep", lambda _: None)
    result = fixture.run_fixture(fixture.parser().parse_args([]), transport.session,
                                 transport, recorder, directory)
    recorder.finish(reason=result["reason"])
    records = load_trajectory(recorder.path)
    assert records[1]["kind"] == "reset"
    assert records[2]["kind"] == "step" and records[2]["thought"] == "visible-map"
    assert records[2]["pre_obs"]["visual_evaluator"]["map_open"] is False
    monkeypatch.setattr(live, "BENCH", tmp_path)
    monkeypatch.setattr(live, "process_status", lambda: {"known": False, "alive": None})
    live._snapshot_cache.clear()
    live._score_cache.clear()
    selection = live.name_of(recorder.path)
    replay = live.replay_snapshot(selection, 0)
    assert replay["total"] == 2
    assert replay["item"]["thought"] == "visible-map"
    visual = replay["item"]["visual"]
    assert visual["observation_mode"] == "image"
    assert visual["advance"] == {"requested_frames": 0, "actual_frames": 0}
    assert visual["inputs"] == [{"type": "key", "key": "j", "modifiers": [], "delivery": "delivered"}]
    assert visual["outcome"] == {"status": "unknown", "summary": "visible-map"}
    assert "phase=before" in visual["before"]["url"] and "phase=after" in visual["after"]["url"]
    image, mime = live.recorded_image(selection, 2, "after")
    assert image.read_bytes() == png and mime == "image/png"
    assert live.build(selection)["header"]["visual_steps"] == 2

