"""Protected diagnostic of the game's real window-message input boundary.

Posts exactly one WM_MOUSEMOVE to the newly owned FTL client window. No global
input, focus changes, models, native state overrides, or simulation advance.
Run explicitly with the checkout's harness Python after closing other FTL runs.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from ftl_bench.installation import runtime_fingerprint
from ftl_bench.protected_game import ProtectedGame, _processes
from ftl_bench.session import AgentSession, ftl_user_folder
from ftl_bench.visual_session import ExternalInputInterference, VisualSession, validate_visual_clock

ROOT = Path(__file__).resolve().parents[1]
FILETIME_EPOCH = 116444736000000000


class WindowMessages:
    """Only process/window inspection and one addressed window message."""

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("The interference probe requires Windows")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wintypes.LPARAM]
        self.user.EnumWindows.restype = wintypes.BOOL
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.IsWindowVisible.restype = wintypes.BOOL
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.GetClientRect.restype = wintypes.BOOL
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user.GetCursorPos.restype = wintypes.BOOL
        self.user.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user.ScreenToClient.restype = wintypes.BOOL
        self.user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.PostMessageW.restype = wintypes.BOOL
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL

    def process_identity(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)  # query only
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            path, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in (created, exited, kernel, user))):
                raise ctypes.WinError(ctypes.get_last_error())
            return {"pid": pid, "path": str(Path(path.value).resolve()),
                    "creation_filetime": (created.dwHighDateTime << 32) | created.dwLowDateTime}
        finally:
            self.kernel.CloseHandle(handle)

    def window_pid(self, hwnd):
        pid = wintypes.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise ctypes.WinError(ctypes.get_last_error())
        return pid.value

    def client_size(self, hwnd):
        rect = wintypes.RECT()
        if not self.user.GetClientRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rect.right - rect.left, rect.bottom - rect.top

    def windows(self, pid):
        windows = []

        @self.callback_type
        def visit(hwnd, _):
            candidate = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(candidate))
            if candidate.value == pid and self.user.IsWindowVisible(hwnd):
                width, height = self.client_size(hwnd)
                if width > 0 and height > 0:
                    windows.append(int(hwnd))
            return True

        if not self.user.EnumWindows(visit, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return windows

    def cursor_client(self, hwnd):
        point = wintypes.POINT()
        if not self.user.GetCursorPos(ctypes.byref(point)) or not self.user.ScreenToClient(hwnd, ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        return point.x, point.y

    def post_move(self, hwnd, x, y):
        if not self.user.PostMessageW(hwnd, 0x0200, 0, (y << 16) | x):
            raise ctypes.WinError(ctypes.get_last_error())


def _same_path(first, second):
    return os.path.normcase(str(Path(first).resolve())) == os.path.normcase(str(Path(second).resolve()))


def owned_window(protected, messages, processes=None):
    processes = _processes() if processes is None else processes
    if len(processes) != 1 or protected.launched_at is None or protected.game is None:
        raise RuntimeError("Exactly one newly owned FTL process is required")
    process = processes[0]
    expected = protected.game / "FTLGame.exe"
    started = datetime.fromisoformat(process["started"])
    if not _same_path(process.get("path", ""), expected) or started < protected.launched_at:
        raise RuntimeError("FTL process path or start time is outside protected ownership")
    identity = messages.process_identity(process["id"])
    native_started = datetime.fromtimestamp((identity["creation_filetime"] - FILETIME_EPOCH) / 10_000_000,
                                           timezone.utc)
    if (identity["pid"] != process["id"] or not _same_path(identity["path"], expected)
            or native_started < protected.launched_at
            or abs((native_started - started).total_seconds()) > .000002):
        raise RuntimeError("Native process identity disagrees with the protected process")
    windows = messages.windows(process["id"])
    if len(windows) != 1:
        raise RuntimeError("Exactly one visible client window must belong to the owned FTL process")
    hwnd = windows[0]
    if messages.window_pid(hwnd) != process["id"]:
        raise RuntimeError("FTL window ownership changed during inspection")
    width, height = messages.client_size(hwnd)
    if not (64 <= width <= 32767 and 64 <= height <= 32767):
        raise RuntimeError("FTL client dimensions cannot safely encode a mouse message")
    return {**identity, "hwnd": hwnd, "width": width, "height": height,
            "protected_started": process["started"]}


def post_owned_move(protected, messages, target):
    # Repeat every ownership check directly before the only posted message.
    checked = owned_window(protected, messages)
    if checked != target:
        raise RuntimeError("FTL process/window identity changed before input; nothing posted")
    cursor = messages.cursor_client(target["hwnd"])
    candidates = [(16, 16), (target["width"] - 17, target["height"] - 17)]
    x, y = max(candidates, key=lambda p: (p[0] - cursor[0]) ** 2 + (p[1] - cursor[1]) ** 2)
    if (x, y) == cursor:
        raise RuntimeError("Diagnostic movement must differ from the physical client pointer")
    # Cursor inspection is another API round trip. Recheck exact process identity,
    # then the HWND's owner immediately before posting; never send global input.
    identity = messages.process_identity(target["pid"])
    if any(identity.get(key) != target[key] for key in ("pid", "path", "creation_filetime")):
        raise RuntimeError("FTL process identity changed before input; nothing posted")
    if messages.window_pid(target["hwnd"]) != target["pid"]:
        raise RuntimeError("FTL window ownership changed before input; nothing posted")
    messages.post_move(target["hwnd"], x, y)
    return {"message": "WM_MOUSEMOVE", "message_id": 0x0200, "wparam": 0,
            "x": x, "y": y, "physical_cursor_before": list(cursor), "posted_count": 1,
            "coordinate_space": "win32_client_message",
            "target": target, "global_input": False, "focus_changed": False}


def world_signature(obs):
    ship = obs.get("player_ship") or {}
    navigation = (obs.get("economy") or {}).get("navigation") or {}
    return {"game_started": obs.get("game_started"), "player_ship": ship,
            "enemy_ship": obs.get("enemy_ship"), "victory": obs.get("victory"),
            "drive_current": navigation.get("drive_current"), "drive_max": navigation.get("drive_max"),
            "position": (obs.get("map") or {}).get("current_pos"),
            "sector": (obs.get("map") or {}).get("sector"),
            "ftl_score": obs.get("ftl_score"), "score_components": obs.get("ftl_score_components")}


def prepare_world(session):
    session.reset_episode(seed=1)
    session.reset()
    obs = session.step([], 30)  # settle the ordinary intro event before capture
    for _ in range(20):
        if not obs.choice_box_open:
            break
        time.sleep(.35)
        choices = [c for c in (obs.event or {}).get("choices", []) if c.get("enabled") is True]
        if not choices:
            raise RuntimeError("No enabled ordinary intro choice")
        obs = session.choose_event(choices[0]["index"], 30)
    oxygen = next((s.get("power") for s in (obs.player_ship or {}).get("systems", []) if s.get("id") == 2), None)
    if (not obs.game_started or obs.choice_box_open or obs.paused is not True or oxygen != 1
            or obs.seed != 1 or (obs.player_ship or {}).get("blueprint") != "PLAYER_SHIP_HARD"
            or obs.raw.get("difficulty") != 0):
        raise RuntimeError("A paused fresh Kestrel with powered oxygen is required")


def run_probe(session, transport, protected, messages, output, *, timeout=5):
    proof = {"fixture_only": True, "classification": "diagnostic_only",
             "valid_for_model_comparison": False, "passed": False,
             "planned_input": {"actions": [{"type": "key", "key": "f", "modifiers": []}],
                               "advance_frames": 0}, "packet_write_attempts": []}

    def save_proof():
        (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")

    try:
        return _run_probe(session, transport, protected, messages, proof, save_proof, timeout)
    except BaseException as error:
        proof.update(passed=False, error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        save_proof()


def _run_probe(session, transport, protected, messages, proof, save_proof, timeout):
    before = transport.capture()
    original = deepcopy(before.observation.raw)
    visual = original.get("visual") or {}
    proof.update(before=original, before_image=before.reference)
    initial_world_updates = validate_visual_clock(before.observation, synchronized=True)
    if (visual.get("external_input_generation") != "0" or visual.get("external_input_detected") is not False
            or visual.get("actual_frames") != 0 or visual.get("requested_frames") != 0):
        raise RuntimeError("Initial capture must be clean and have zero simulation advance")
    if (visual.get("width"), visual.get("height")) != (1280, 720):
        raise RuntimeError("The interference fixture requires a captured 1280x720 client image")
    target = owned_window(protected, messages)
    # Win32 client coordinates can differ from render pixels (for example under
    # DPI virtualization). This movement does not target a screenshot element:
    # choose it wholly within the inspected Windows client coordinate space.
    proof["coordinate_spaces"] = {
        "captured_image": {"width": visual["width"], "height": visual["height"],
                           "coordinate_space": "rendered_client_pixels"},
        "windows_client": {"width": target["width"], "height": target["height"],
                           "coordinate_space": "win32_client_message"},
        "screenshot_coordinate_mapping_used": False,
    }
    proof["verified_target"] = target
    save_proof()
    initial_action_seq = session.action_seq
    proof["input"] = post_owned_move(protected, messages, target)
    save_proof()
    deadline = time.monotonic() + timeout
    while True:
        after = session.observe()
        state = (after.raw.get("visual") or {})
        generation = state.get("external_input_generation")
        if (state.get("external_input_detected") is True and isinstance(generation, str)
                and generation.isascii() and generation.isdecimal() and int(generation) > 0):
            break
        if time.monotonic() >= deadline:
            proof["last_observation"] = after.raw
            raise TimeoutError("Posted WM_MOUSEMOVE did not reach the native external-input guard")
        time.sleep(.05)
    proof["after_interference"] = deepcopy(after.raw)
    packets = []
    write_action = session._write_action_atomic

    def observe_dispatch(packet):
        packets.append(deepcopy(packet))
        proof["packet_write_attempts"] = packets
        # An unexpected transport regression must not send the planned key to
        # the game. Acceptance still requires that this trap is never reached.
        raise RuntimeError("Transport attempted to dispatch after outside input; diagnostic blocked the packet")

    session._write_action_atomic = observe_dispatch
    try:
        try:
            transport.step(before, proof["planned_input"]["actions"], 0)
        except ExternalInputInterference as error:
            proof["refusal"] = error.evidence
        else:
            raise RuntimeError("Contaminated screenshot was accepted by the visual transport")
    finally:
        session._write_action_atomic = write_action
    time.sleep(.1)  # Require the guard to remain latched in a later observation.
    latest = session.observe()
    proof["after_refusal"] = deepcopy(latest.raw)
    latest_visual = latest.raw.get("visual") or {}
    oxygen = next((s.get("power") for s in (original.get("player_ship") or {}).get("systems", []) if s.get("id") == 2), None)
    proof["checks"] = {
        "clean_initial_guard": visual.get("external_input_generation") == "0" and visual.get("external_input_detected") is False,
        "actual_os_message_guard_advanced": state.get("external_input_generation", "0").isascii()
            and state.get("external_input_generation", "0").isdecimal() and int(state["external_input_generation"]) > 0,
        "sticky_interference_observed": state.get("external_input_detected") is True
            and latest_visual.get("external_input_detected") is True
            and latest_visual.get("external_input_generation") == state.get("external_input_generation"),
        "refused_before_packet_dispatch": proof["refusal"].get("packet_dispatched") is False and not packets,
        "same_action_sequence": original.get("last_action_seq") == after.last_action_seq == latest.last_action_seq
            and initial_action_seq == session.action_seq == latest.last_action_seq
            and all((o.get("visual") or {}).get("action_seq") == latest.last_action_seq
                    for o in (original, after.raw, latest.raw)),
        "powered_oxygen_unchanged": oxygen == 1 and all(next((s.get("power") for s in
            (o.get("player_ship") or {}).get("systems", []) if s.get("id") == 2), None) == oxygen
            for o in (after.raw, latest.raw)),
        "paused_and_world_unchanged": original.get("paused") is True and after.paused is True and latest.paused is True
            and world_signature(original) == world_signature(after.raw) == world_signature(latest.raw),
        "no_simulation_advance": all((o.get("visual") or {}).get("actual_frames") == 0 for o in (original, after.raw, latest.raw)),
        "world_update_counter_unchanged": initial_world_updates
            == validate_visual_clock(after, synchronized=True) == validate_visual_clock(latest, synchronized=True),
    }
    proof["passed"] = all(proof["checks"].values())
    if not proof["passed"]:
        raise RuntimeError("External-input diagnostic did not establish all required safety checks")
    return proof


def restoration_verified(backup):
    try:
        receipt = json.loads((backup / "restoration.json").read_text(encoding="utf-8"))
        return isinstance(receipt, dict) and receipt.get("verified") is True
    except (OSError, ValueError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 30:
        parser.error("--timeout must be in (0,30]")
    name = datetime.now(timezone.utc).strftime("interference-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    output = (args.output or ROOT / "harness/runs/validation/visual-v1" / name).resolve()
    output.mkdir(parents=True, exist_ok=False)
    protected = ProtectedGame(ftl_user_folder(), output / "save-backup",
                              ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua")
    manifest = {"run_id": output.name, "status": "running", "started_at": time.time(),
                "fixture_only": True, "valid_for_model_comparison": False,
                "classification": "diagnostic_only", "validation_status": "diagnostic_only",
                "track": "visual-v1", "observation_mode": "image", "seed": 1,
                "agent": "native-visual-interference-fixture",
                "scenario_ids": ["VISUAL-FIXTURE-interference"], "model": None, "provider": "none",
                "validation_limitations": ["One process-scoped mouse message; no model gameplay or comparison evidence."]}

    def write_manifest(**updates):
        manifest.update(updates)
        (output / "run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    write_manifest()
    try:
        with protected.protected():
            protected.launch()
            fingerprint = runtime_fingerprint(ROOT)
            (output / "runtime-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
            if not (fingerprint.get("native_build") or {}).get("matches_installed_dll"):
                raise RuntimeError("Installed DLL provenance mismatch")
            session = AgentSession(user_folder=protected.save, step_timeout=20)
            prepare_world(session)
            run_probe(session, VisualSession(session, output), protected, WindowMessages(), output, timeout=args.timeout)
        if not restoration_verified(protected.backup):
            raise RuntimeError("Save restoration receipt is not verified")
        write_manifest(status="completed", reason="external_input_guard_verified", finished_at=time.time(),
                       save_restoration="verified", fixture_acceptance="passed")
    except BaseException as error:
        restored = restoration_verified(protected.backup)
        write_manifest(status="interrupted" if isinstance(error, KeyboardInterrupt) else "error",
                       reason="fixture_failed", error=str(error), finished_at=time.time(),
                       save_restoration="verified" if restored else "see_save_backup_receipt",
                       fixture_acceptance="failed")
        raise
    print(f"External-input diagnostic artifacts: {output}", flush=True)


if __name__ == "__main__":
    main()
