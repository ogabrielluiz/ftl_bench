"""Platform-resolution and atomic-write tests for ftl_bench.session.

These cover the parts of session.py the existing test_session.py leaves at ~43%:

  * ftl_user_folder() — the per-OS save-folder resolution (FTL_SAVE_DIR override,
    Windows Documents, macOS Application Support, Linux XDG / ~/.local/share).
  * ftl_process_alive() — the freeze-detection process probe (tasklist on Windows /
    WSL, pgrep elsewhere, present / absent / raising).
  * AgentSession._write_action_atomic — its PermissionError retry loop.

Everything that would normally shell out (subprocess.run) or touch the real
filesystem (Path.replace) is monkeypatched; tmp_path holds the session folder.
"""
import json
import os as _real_os
import sys as _real_sys
from pathlib import Path

import pytest

from ftl_bench.session import (
    AgentSession,
    ftl_process_alive,
    ftl_user_folder,
)


# ---------------------------------------------------------------------------
# ftl_user_folder()
# ---------------------------------------------------------------------------
#
# session.py reads os.name / sys.platform as bare module globals. We must NOT
# monkeypatch the *real* os.name, because pathlib uses os.name at instantiation
# time to pick WindowsPath vs PosixPath — flipping it to "posix" on a Windows
# host makes every Path(...) raise UnsupportedOperation. Instead we swap the
# `os` / `sys` names the session module sees for thin stand-ins that override
# only .name / .platform while delegating everything else (notably os.environ)
# to the genuine modules, leaving pathlib untouched.


class _FakeOS:
    def __init__(self, name):
        self.name = name
        self.environ = _real_os.environ  # so monkeypatch.setenv still applies

    def __getattr__(self, attr):  # delegate the rest (e.g. os.sep) to real os
        return getattr(_real_os, attr)


class _FakeSys:
    def __init__(self, platform):
        self.platform = platform

    def __getattr__(self, attr):
        return getattr(_real_sys, attr)


def _fake_platform(monkeypatch, *, os_name, platform):
    monkeypatch.setattr("ftl_bench.session.os", _FakeOS(os_name))
    monkeypatch.setattr("ftl_bench.session.sys", _FakeSys(platform))


def test_user_folder_honors_save_dir_override(monkeypatch, tmp_path):
    """FTL_SAVE_DIR wins over every per-OS default, regardless of os.name."""
    monkeypatch.setenv("FTL_SAVE_DIR", str(tmp_path / "custom_save"))
    # os.name / sys.platform must not matter when the override is set.
    _fake_platform(monkeypatch, os_name="nt", platform="darwin")
    assert ftl_user_folder() == Path(str(tmp_path / "custom_save")).expanduser()


def test_user_folder_override_expands_user(monkeypatch):
    """A '~' in FTL_SAVE_DIR is expanded to the real home directory."""
    monkeypatch.setenv("FTL_SAVE_DIR", "~/my_ftl_dir")
    result = ftl_user_folder()
    assert result == Path("~/my_ftl_dir").expanduser()
    assert "~" not in str(result)


def test_user_folder_empty_override_is_ignored(monkeypatch):
    """An empty FTL_SAVE_DIR is falsy and must fall through to the per-OS default."""
    monkeypatch.setenv("FTL_SAVE_DIR", "")
    _fake_platform(monkeypatch, os_name="nt", platform="win32")
    result = ftl_user_folder()
    assert result == Path("~/Documents/My Games/FasterThanLight").expanduser()


def test_user_folder_windows(monkeypatch):
    """os.name == 'nt' -> Documents/My Games/FasterThanLight."""
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    # Even on a darwin sys.platform, the nt check comes first.
    _fake_platform(monkeypatch, os_name="nt", platform="darwin")
    assert ftl_user_folder() == Path("~/Documents/My Games/FasterThanLight").expanduser()


def test_user_folder_macos(monkeypatch):
    """sys.platform == 'darwin' (posix os.name) -> Library/Application Support."""
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _fake_platform(monkeypatch, os_name="posix", platform="darwin")
    expected = Path("~/Library/Application Support/FasterThanLight").expanduser()
    assert ftl_user_folder() == expected


def test_user_folder_linux_with_xdg(monkeypatch, tmp_path):
    """Linux/other POSIX with XDG_DATA_HOME set -> $XDG_DATA_HOME/FasterThanLight."""
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert ftl_user_folder() == tmp_path / "xdg" / "FasterThanLight"


def test_user_folder_linux_xdg_expands_user(monkeypatch):
    """A '~' in XDG_DATA_HOME is expanded too."""
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    monkeypatch.setenv("XDG_DATA_HOME", "~/somexdg")
    expected = Path("~/somexdg").expanduser() / "FasterThanLight"
    assert ftl_user_folder() == expected
    assert "~" not in str(ftl_user_folder())


def test_user_folder_linux_xdg_fallback(monkeypatch):
    """Linux/other POSIX with XDG_DATA_HOME unset -> ~/.local/share fallback.

    Crucially it must NOT fall through to the macOS Application Support path —
    all POSIX shares os.name == 'posix', so the darwin check guards that branch.
    """
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    expected = Path("~/.local/share").expanduser() / "FasterThanLight"
    result = ftl_user_folder()
    assert result == expected
    assert "Application Support" not in str(result)


def test_user_folder_empty_xdg_falls_back(monkeypatch):
    """An empty XDG_DATA_HOME is falsy and must use the ~/.local/share fallback."""
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "")
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    expected = Path("~/.local/share").expanduser() / "FasterThanLight"
    assert ftl_user_folder() == expected


def test_user_folder_returns_path(monkeypatch):
    """The result is always a pathlib.Path."""
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    assert isinstance(ftl_user_folder(), Path)


# ---------------------------------------------------------------------------
# ftl_process_alive()
# ---------------------------------------------------------------------------

class _FakeProc:
    """Stand-in for subprocess.CompletedProcess (only .stdout is consulted)."""

    def __init__(self, stdout: str = ""):
        self.stdout = stdout


def _patch_run(monkeypatch, *, expect_cmd_contains=None, stdout="", raises=None):
    """Install a fake subprocess.run on the session module.

    If expect_cmd_contains is given, assert the launched argv[0] contains it,
    so we confirm the right tool (tasklist vs pgrep) is being shelled out.
    """
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if raises is not None:
            raise raises
        if expect_cmd_contains is not None:
            assert expect_cmd_contains in cmd[0], f"unexpected probe command: {cmd!r}"
        return _FakeProc(stdout)

    monkeypatch.setattr("ftl_bench.session.subprocess.run", fake_run)
    return calls


def test_process_alive_windows_present(monkeypatch):
    """Native Windows: 'FTLGame.exe' in tasklist stdout -> alive."""
    _fake_platform(monkeypatch, os_name="nt", platform="win32")
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _patch_run(
        monkeypatch,
        expect_cmd_contains="tasklist",
        stdout="Image Name\nFTLGame.exe   1234 Console   100,000 K\n",
    )
    assert ftl_process_alive() is True


def test_process_alive_windows_absent(monkeypatch):
    """Native Windows: no FTLGame.exe line -> not alive."""
    _fake_platform(monkeypatch, os_name="nt", platform="win32")
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _patch_run(
        monkeypatch,
        expect_cmd_contains="tasklist",
        stdout="INFO: No tasks are running which match the specified criteria.\n",
    )
    assert ftl_process_alive() is False


def test_process_alive_wsl_uses_windows_tasklist(monkeypatch):
    """A /mnt/ FTL_SAVE_DIR means WSL -> probe via the Windows tasklist.exe."""
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    monkeypatch.setenv("FTL_SAVE_DIR", "/mnt/c/Users/me/Documents/My Games/FasterThanLight")
    calls = _patch_run(
        monkeypatch,
        expect_cmd_contains="tasklist.exe",
        stdout="FTLGame.exe\n",
    )
    assert ftl_process_alive() is True
    assert calls and calls[0][0].endswith("tasklist.exe")


def test_process_alive_posix_present(monkeypatch):
    """Non-Windows, non-WSL: pgrep with output -> alive."""
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _patch_run(monkeypatch, expect_cmd_contains="pgrep", stdout="4242\n")
    assert ftl_process_alive() is True


def test_process_alive_posix_uses_mac_proc_pattern(monkeypatch):
    """The pgrep probe targets the macOS FTL.app executable path pattern."""
    _fake_platform(monkeypatch, os_name="posix", platform="darwin")
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    calls = _patch_run(monkeypatch, stdout="111\n")
    assert ftl_process_alive() is True
    # pgrep -f <pattern>: the FTL.app MacOS binary path must be the search pattern.
    assert calls[0][0] == "pgrep"
    assert calls[0][1] == "-f"
    assert "FTL.app/Contents/MacOS/FTL" in calls[0][2]


def test_process_alive_posix_absent(monkeypatch):
    """Non-Windows, non-WSL: pgrep with empty/whitespace output -> not alive."""
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _patch_run(monkeypatch, expect_cmd_contains="pgrep", stdout="   \n")
    assert ftl_process_alive() is False


def test_process_alive_raising_returns_true(monkeypatch):
    """If the probe raises (e.g. tool missing), we must NOT declare a live game
    dead -> the function swallows the exception and returns True."""
    _fake_platform(monkeypatch, os_name="posix", platform="linux")
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _patch_run(monkeypatch, raises=FileNotFoundError("pgrep: not found"))
    assert ftl_process_alive() is True


def test_process_alive_windows_raising_returns_true(monkeypatch):
    """Same safety net on the Windows path."""
    _fake_platform(monkeypatch, os_name="nt", platform="win32")
    monkeypatch.delenv("FTL_SAVE_DIR", raising=False)
    _patch_run(monkeypatch, raises=OSError("tasklist exploded"))
    assert ftl_process_alive() is True


# ---------------------------------------------------------------------------
# AgentSession._write_action_atomic — PermissionError retry loop
# ---------------------------------------------------------------------------

def test_write_action_atomic_basic(tmp_path):
    """Happy path: the action file ends up with exactly the payload, atomically."""
    sess = AgentSession(tmp_path)
    payload = {"seq": 7, "advance_frames": 30, "actions": [{"type": "jump"}]}
    sess._write_action_atomic(payload)
    written = json.loads((tmp_path / "ftl_agent_action.json").read_text(encoding="utf-8"))
    assert written == payload
    # No stray temp file should remain after the rename.
    assert not (tmp_path / "ftl_agent_action.json.tmp").exists()


def test_write_action_atomic_retries_then_succeeds(tmp_path, monkeypatch):
    """A transient PermissionError on the rename is retried, then succeeds.

    Mirrors the Windows sharing-violation case: the bridge briefly holds the
    action file open. We patch Path.replace to raise once, then delegate to the
    real replace, and assert the file is written and sleep was actually used.
    """
    real_replace = Path.replace
    state = {"calls": 0}

    def flaky_replace(self, target):
        state["calls"] += 1
        if state["calls"] == 1:
            raise PermissionError("WinError 5: sharing violation")
        return real_replace(self, target)

    sleeps = []
    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr("ftl_bench.session.time.sleep", lambda s: sleeps.append(s))

    sess = AgentSession(tmp_path)
    payload = {"seq": 1, "advance_frames": 0, "actions": []}
    sess._write_action_atomic(payload)

    assert state["calls"] == 2  # one failure + one success
    assert sleeps == [0.05]  # backed off exactly once between attempts
    written = json.loads((tmp_path / "ftl_agent_action.json").read_text(encoding="utf-8"))
    assert written == payload


def test_write_action_atomic_retries_on_oserror(tmp_path, monkeypatch):
    """A generic transient OSError is retried the same way as PermissionError."""
    real_replace = Path.replace
    state = {"calls": 0}

    def flaky_replace(self, target):
        state["calls"] += 1
        if state["calls"] <= 2:
            raise OSError("transient")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr("ftl_bench.session.time.sleep", lambda s: None)

    sess = AgentSession(tmp_path)
    sess._write_action_atomic({"seq": 2, "advance_frames": 0, "actions": []})
    assert state["calls"] == 3
    assert (tmp_path / "ftl_agent_action.json").exists()


def test_write_action_atomic_gives_up_after_9_attempts(tmp_path, monkeypatch):
    """The retry loop is bounded: after 9 failed attempts it re-raises."""
    state = {"calls": 0}

    def always_fail(self, target):
        state["calls"] += 1
        raise PermissionError("permanently locked")

    monkeypatch.setattr(Path, "replace", always_fail)
    monkeypatch.setattr("ftl_bench.session.time.sleep", lambda s: None)

    sess = AgentSession(tmp_path)
    with pytest.raises(PermissionError):
        sess._write_action_atomic({"seq": 3, "advance_frames": 0, "actions": []})
    assert state["calls"] == 9  # exactly 9 tries (attempts 0..8), then raise


def test_write_action_atomic_writes_tmp_first(tmp_path, monkeypatch):
    """The payload is staged in a .json.tmp sibling before the atomic replace."""
    seen = {}

    def capture_replace(self, target):
        # At replace time the tmp file should already hold the full payload.
        seen["tmp_exists"] = self.exists()
        seen["tmp_content"] = self.read_text(encoding="utf-8")
        seen["tmp_name"] = self.name
        seen["target_name"] = Path(target).name

    monkeypatch.setattr(Path, "replace", capture_replace)
    sess = AgentSession(tmp_path)
    payload = {"seq": 9, "advance_frames": 5, "actions": [{"type": "cloak"}]}
    sess._write_action_atomic(payload)

    assert seen["tmp_exists"] is True
    assert json.loads(seen["tmp_content"]) == payload
    assert seen["tmp_name"] == "ftl_agent_action.json.tmp"
    assert seen["target_name"] == "ftl_agent_action.json"
