"""The outside-input diagnostic uses fake windows; no game, desktop input, or model."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import zlib

import pytest

from ftl_bench.cli import _bench_root
from ftl_bench.observation import Observation
import ftl_bench.protected_game as protection
from ftl_bench.visual_session import VisualSession

_spec = importlib.util.spec_from_file_location("validate_visual_interference", _bench_root() / "scripts/validate_visual_interference.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


@pytest.fixture(autouse=True)
def no_native_boundaries(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Test attempted to inspect or control the actual desktop/game")
    monkeypatch.setattr(probe, "_processes", blocked)
    monkeypatch.setattr(probe.WindowMessages, "__init__", blocked)
    monkeypatch.setattr(protection, "_processes", blocked)


class Messages:
    def __init__(self, game):
        self.started = datetime(2026, 10, 9, 2, 0, 0, tzinfo=timezone.utc)
        self.identity = {"pid": 42, "path": str((game / "FTLGame.exe").resolve()),
                         "creation_filetime": probe.FILETIME_EPOCH + int(self.started.timestamp()) * 10_000_000}
        self.pid = 42
        self.handles = [123]
        self.dimensions = (1280, 720)
        self.cursor = (16, 16)
        self.events = []
        self.posted = []
        self.on_post = lambda: None
        self.on_cursor = lambda: None

    def process_identity(self, pid):
        self.events.append("identity")
        return deepcopy(self.identity)

    def windows(self, pid):
        return self.handles

    def window_pid(self, hwnd):
        self.events.append("window_pid")
        return self.pid

    def client_size(self, hwnd):
        return self.dimensions

    def cursor_client(self, hwnd):
        self.events.append("cursor")
        self.on_cursor()
        return self.cursor

    def post_move(self, hwnd, x, y):
        self.events.append("post")
        self.posted.append((hwnd, x, y))
        self.on_post()


@pytest.fixture
def owner(tmp_path, monkeypatch):
    game = tmp_path / "game"
    messages = Messages(game)
    protected = SimpleNamespace(game=game, launched_at=messages.started - timedelta(seconds=1))
    processes = [{"id": 42, "path": messages.identity["path"], "started": messages.started.isoformat()}]
    monkeypatch.setattr(probe, "_processes", lambda: processes)
    return protected, messages, processes


@pytest.mark.parametrize("change", ["old", "wrong_path", "other_pid", "native_start", "native_path", "windows", "window_pid"])
def test_ownership_must_match_exact_new_process_and_single_window(owner, change):
    protected, messages, processes = owner
    if change == "old":
        protected.launched_at = messages.started + timedelta(seconds=1)
    elif change == "wrong_path":
        processes[0]["path"] = "other/FTLGame.exe"
    elif change == "other_pid":
        messages.identity["pid"] = 43
    elif change == "native_start":
        messages.identity["creation_filetime"] += 100_000
    elif change == "native_path":
        messages.identity["path"] = "other/FTLGame.exe"
    elif change == "windows":
        messages.handles.append(124)
    else:
        messages.pid = 43
    with pytest.raises(RuntimeError):
        probe.owned_window(protected, messages)
    assert not messages.posted


@pytest.mark.parametrize("change", ["pid", "creation", "path"])
def test_recycled_window_or_process_after_cursor_inspection_gets_no_message(owner, change):
    protected, messages, _ = owner
    target = probe.owned_window(protected, messages)

    def race():
        if change == "pid":
            messages.pid += 1
        elif change == "creation":
            messages.identity["creation_filetime"] += 1
        else:
            messages.identity["path"] = "other.exe"
    messages.on_cursor = race
    with pytest.raises(RuntimeError, match="changed before input"):
        probe.post_owned_move(protected, messages, target)
    assert not messages.posted


def test_only_one_addressed_move_after_adjacent_pid_check(owner):
    protected, messages, _ = owner
    target = probe.owned_window(protected, messages)
    evidence = probe.post_owned_move(protected, messages, target)
    assert messages.events[-3:] == ["identity", "window_pid", "post"]
    assert messages.posted == [(123, 1263, 703)]
    assert evidence["physical_cursor_before"] == [16, 16]
    assert evidence["global_input"] is False and evidence["focus_changed"] is False


def observed(seq=0):
    return Observation.from_dict({
        "schema_version": 3, "seed": 1, "tick": 30, "game_started": True, "paused": True,
        "last_action_seq": seq, "victory": False, "difficulty": 0,
        "capabilities": {"external_input_guard": True, "visual_clock_version": 2, "world_updates": "30",
                         "fixed_step_numerator": 1, "fixed_step_denominator": 60, "simulated_updates": "30"},
        "visual": {"visual_io_version": 1, "capture_id": str(seq), "frame_id": f"frame-{seq}",
                   "action_seq": seq, "visual_clock_version": 2, "world_updates": "30", "path": "capture.png",
                   "fixed_step_numerator": 1, "fixed_step_denominator": 60, "simulated_updates": "30",
                   "width": 1280, "height": 720, "coordinate_space": "client", "paused": True,
                   "actual_frames": 0, "requested_frames": 0, "input_feedback": [],
                   "external_input_generation": "0", "external_input_detected": False},
        "player_ship": {"blueprint": "PLAYER_SHIP_HARD", "hull": {"current": 30, "max": 30},
                        "resources": {"fuel": 16, "scrap": 0}, "oxygen_pct": 100,
                        "rooms": [{"room_id": 0, "oxygen": 100.0}],
                        "crew": [{"health_current": 100}], "systems": [{"id": 2, "power": 1}]},
        "economy": {"navigation": {"drive_current": 5, "drive_max": 60}},
        "map": {"current_pos": {"x": 0, "y": 0}, "sector": 0}, "ftl_score": 0})


class NativeSession:
    step_timeout = 1

    def __init__(self, directory):
        self.user_folder = directory
        self.action_seq = 0
        self.current = observed()
        self.packets = []

    def _sync_seq(self):
        self.action_seq = max(self.action_seq, self.current.last_action_seq)
        return self.current

    def _write_action_atomic(self, packet):
        self.packets.append(deepcopy(packet))
        self.current = observed(packet["seq"])

    def _wait_for(self, predicate, timeout):
        assert predicate(self.current)
        return self.current

    def observe(self):
        return self.current


@pytest.fixture
def diagnostic(tmp_path, owner, monkeypatch):
    protected, messages, _ = owner
    save = tmp_path / "save"
    save.mkdir()

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    (save / "capture.png").write_bytes(b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1280, 720, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\0\0" * 1280) * 720)) + chunk(b"IEND", b""))
    session = NativeSession(save)
    output = tmp_path / "run"
    transport = VisualSession(session, output)

    def external_move():
        raw = deepcopy(session.current.raw)
        raw["visual"].update(external_input_detected=True, external_input_generation="1")
        session.current = Observation.from_dict(raw)
    messages.on_post = external_move
    monkeypatch.setattr(probe.time, "sleep", lambda seconds: None)
    return session, transport, protected, messages, output


def test_real_visual_transport_refuses_planned_key_before_packet_dispatch(diagnostic):
    session, transport, protected, messages, output = diagnostic
    writer = session._write_action_atomic
    proof = probe.run_probe(*diagnostic)
    assert proof["passed"] is True and all(proof["checks"].values())
    assert proof["planned_input"] == {"actions": [{"type": "key", "key": "f", "modifiers": []}], "advance_frames": 0}
    assert proof["refusal"]["packet_dispatched"] is False and proof["packet_write_attempts"] == []
    assert len(session.packets) == 1 and session.packets[0]["actions"] == []  # Initial capture only.
    assert session.action_seq == 1 and session._write_action_atomic == writer
    assert len(messages.posted) == 1
    assert proof["classification"] == "diagnostic_only" and proof["valid_for_model_comparison"] is False
    assert json.loads((output / "proof.json").read_text())["passed"] is True


@pytest.mark.parametrize("change", ["clock", "room_oxygen", "crew_health", "action_seq", "latch_clears"])
def test_diagnostic_cannot_pass_when_world_or_guard_changes(diagnostic, change):
    session, transport, _, messages, output = diagnostic
    post = messages.on_post

    def changed():
        post()
        raw = session.current.raw
        if change == "clock":
            raw["visual"]["world_updates"] = raw["capabilities"]["world_updates"] = "31"
            raw["visual"]["simulated_updates"] = raw["capabilities"]["simulated_updates"] = "31"
        elif change == "room_oxygen":
            raw["player_ship"]["rooms"][0]["oxygen"] = 99.999
        elif change == "crew_health":
            raw["player_ship"]["crew"][0]["health_current"] = 99
        elif change == "action_seq":
            raw["last_action_seq"] += 1
            raw["visual"]["action_seq"] += 1
            session.current = Observation.from_dict(raw)
    messages.on_post = changed
    if change == "latch_clears":
        step = transport.step

        def clearing(*args):
            try:
                return step(*args)
            finally:
                raw = deepcopy(session.current.raw)
                raw["visual"]["external_input_detected"] = False
                session.current = Observation.from_dict(raw)
        transport.step = clearing
    with pytest.raises(RuntimeError, match="required safety checks"):
        probe.run_probe(*diagnostic)
    evidence = json.loads((output / "proof.json").read_text())
    assert evidence["passed"] is False and not all(evidence["checks"].values())
    assert len(session.packets) == 1


def test_dispatch_regression_is_recorded_and_trapped_without_sending_key(diagnostic):
    session, transport, _, messages, output = diagnostic
    writer = session._write_action_atomic

    def unsafe_step(before, actions, advance):
        session._write_action_atomic({"seq": 2, "actions": actions, "advance_frames": advance})
    transport.step = unsafe_step
    with pytest.raises(RuntimeError, match="diagnostic blocked the packet"):
        probe.run_probe(*diagnostic)
    evidence = json.loads((output / "proof.json").read_text())
    assert not evidence["passed"] and evidence["packet_write_attempts"][0]["actions"][0]["key"] == "f"
    assert len(session.packets) == 1 and session._write_action_atomic == writer


def test_missing_guard_signal_times_out_without_retrying_mouse_or_sending_key(diagnostic, monkeypatch):
    session, _, _, messages, output = diagnostic
    messages.on_post = lambda: None
    ticks = iter([0, 6])
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError, match="did not reach"):
        probe.run_probe(*diagnostic, timeout=5)
    assert len(messages.posted) == len(session.packets) == 1
    evidence = json.loads((output / "proof.json").read_text())
    assert not evidence["passed"] and evidence["error"]["type"] == "TimeoutError"


@pytest.mark.parametrize("dimensions", [(1024, 576), (1600, 900), (1280, 719)])
def test_client_and_render_dimensions_can_legitimately_differ(diagnostic, dimensions):
    _, _, _, messages, _ = diagnostic
    messages.dimensions = dimensions
    evidence = probe.run_probe(*diagnostic)
    assert evidence["passed"] is True
    assert evidence["coordinate_spaces"] == {
        "captured_image": {"width": 1280, "height": 720, "coordinate_space": "rendered_client_pixels"},
        "windows_client": {"width": dimensions[0], "height": dimensions[1],
                           "coordinate_space": "win32_client_message"},
        "screenshot_coordinate_mapping_used": False,
    }
    assert evidence["input"]["coordinate_space"] == "win32_client_message"
    assert messages.posted == [(123, dimensions[0] - 17, dimensions[1] - 17)]
    assert evidence["verified_target"]["width"] == dimensions[0]
    assert evidence["verified_target"]["height"] == dimensions[1]


@pytest.mark.parametrize("dimensions", [(0, 720), (1280, 0), (32768, 720)])
def test_unsafe_windows_client_dimensions_fail_before_external_message(diagnostic, dimensions):
    _, _, _, messages, _ = diagnostic
    messages.dimensions = dimensions
    with pytest.raises(RuntimeError, match="cannot safely encode"):
        probe.run_probe(*diagnostic)
    assert messages.posted == []


@pytest.mark.parametrize("change", [None, "seed", "ship", "difficulty", "oxygen", "paused"])
def test_preparation_requires_the_actual_fresh_paused_kestrel(change):
    raw = observed().raw
    if change == "seed":
        raw["seed"] = 2
    elif change == "ship":
        raw["player_ship"]["blueprint"] = "OTHER_SHIP"
    elif change == "difficulty":
        raw["difficulty"] = 2
    elif change == "oxygen":
        raw["player_ship"]["systems"][0]["power"] = 0
    elif change == "paused":
        raw["paused"] = False
    actions = []
    session = SimpleNamespace(
        reset_episode=lambda **kwargs: actions.append(("reset_episode", kwargs)),
        reset=lambda: actions.append(("reset", {})),
        step=lambda inputs, advance: Observation.from_dict(raw))
    if change:
        with pytest.raises(RuntimeError, match="fresh Kestrel"):
            probe.prepare_world(session)
    else:
        probe.prepare_world(session)
    assert actions == [("reset_episode", {"seed": 1}), ("reset", {})]


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    save = tmp_path / "personal-save"
    save.mkdir()
    originals = {"continue.sav": b"personal run", "profile.sav": b"personal achievements"}
    for name, data in originals.items():
        (save / name).write_bytes(data)
    events, state = [], {"failure": None}
    monkeypatch.setattr(protection, "_processes", lambda: [])
    monkeypatch.setattr(protection, "os", SimpleNamespace(name="nt"))

    class Protected(protection.ProtectedGame):
        def __init__(self, save, backup, bridge):
            super().__init__(save, backup, bridge, tmp_path / "fake-game")

        def launch(self):
            events.append("launch")
            for name, data in originals.items():
                assert (self.backup / name).read_bytes() == data
                (self.save / name).write_bytes(b"modified by fake game")
            (self.save / "new.sav").write_bytes(b"generated")
            if state["failure"] == "launch":
                raise RuntimeError("launch failed")

        def stop(self):
            events.append("stop")

        def restore_saves(self):
            events.append("restore")
            manifest = json.loads((self.backup.parent / "run.json").read_text())
            assert manifest["status"] == "running"
            if state["failure"] == "restore":
                raise RuntimeError("restore failed")
            super().restore_saves()
            if state["failure"] == "receipt":
                (self.backup / "restoration.json").write_text("incomplete receipt", encoding="utf-8")

    def run(*args, **kwargs):
        events.append("probe")
        if state["failure"] == "probe":
            raise RuntimeError("probe failed")
        return {"passed": True}

    def session(**kwargs):
        assert kwargs["user_folder"] == save
        return object()

    monkeypatch.setattr(probe, "ProtectedGame", Protected)
    monkeypatch.setattr(probe, "ftl_user_folder", lambda: save)
    monkeypatch.setattr(probe, "runtime_fingerprint", lambda root: {
        "native_build": {"matches_installed_dll": state["failure"] != "provenance"}})
    monkeypatch.setattr(probe, "AgentSession", session)
    monkeypatch.setattr(probe, "prepare_world", lambda session: events.append("prepare"))
    monkeypatch.setattr(probe, "VisualSession", lambda *args: object())
    monkeypatch.setattr(probe, "WindowMessages", lambda: object())
    monkeypatch.setattr(probe, "run_probe", run)
    return save, originals, events, state


def test_cli_success_requires_real_save_restoration_before_terminal_manifest(tmp_path, lifecycle):
    save, originals, events, _ = lifecycle
    output = tmp_path / "run"
    probe.main(["--output", str(output)])
    assert events == ["launch", "prepare", "probe", "stop", "restore"]
    for name, data in originals.items():
        assert (save / name).read_bytes() == data
    assert not (save / "new.sav").exists()
    assert (output / "save-backup/benchmark-generated/new.sav").read_bytes() == b"generated"
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["status"] == "completed" and manifest["fixture_acceptance"] == "passed"
    assert manifest["save_restoration"] == "verified" and manifest["classification"] == "diagnostic_only"
    assert manifest["provider"] == "none" and manifest["model"] is None
    assert manifest["valid_for_model_comparison"] is False
    assert json.loads((output / "save-backup/restoration.json").read_text())["verified"] is True
    assert json.loads((output / "runtime-fingerprint.json").read_text())["native_build"]["matches_installed_dll"] is True


@pytest.mark.parametrize("failure", ["launch", "provenance", "probe", "restore", "receipt"])
def test_cli_failure_restores_saves_or_explicitly_reports_cleanup_failure(tmp_path, lifecycle, failure):
    save, originals, events, state = lifecycle
    state["failure"] = failure
    output = tmp_path / "run"
    with pytest.raises(RuntimeError):
        probe.main(["--output", str(output)])
    assert events[-2:] == ["stop", "restore"]
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["status"] == "error" and manifest["fixture_acceptance"] == "failed"
    assert (manifest["save_restoration"] == "verified") is (failure not in ("restore", "receipt"))
    if failure != "restore":
        for name, data in originals.items():
            assert (save / name).read_bytes() == data


@pytest.mark.parametrize("timeout", ["nan", "inf", "0", "-1", "31"])
def test_invalid_timeout_has_no_output_or_process_side_effects(tmp_path, timeout):
    output = tmp_path / "run"
    with pytest.raises(SystemExit):
        probe.main(["--output", str(output), "--timeout", timeout])
    assert not output.exists()
