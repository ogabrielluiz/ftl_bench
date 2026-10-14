"""File-only WSL configuration regression tests; no host or WSL operations."""
import importlib.util
from pathlib import Path

import pytest
from ftl_bench.cli import _bench_root

ROOT = _bench_root()
SPEC = importlib.util.spec_from_file_location("configure_wsl_idle", ROOT / "scripts/configure_wsl_idle.py")
idle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(idle)


def test_actual_missing_newline_regression(tmp_path):
    original = b"[wsl2]\r\nnetworkingMode=mirrored\r\nmemory=28GB\r\nprocessors=32"
    path = tmp_path / ".wslconfig"
    path.write_bytes(original)
    assert idle.configure(path)["changed"] is True
    assert path.read_bytes() == original + b"\r\nvmIdleTimeout=-1\r\n"
    before = path.stat()
    assert idle.configure(path) == {"path": str(path), "status": "already_disabled", "changed": False}
    assert path.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_insert_inside_section_preserves_other_sections(newline):
    raw = newline.join([b"; vmIdleTimeout=77", b"[wsl2]", b"memory=28GB", b"[experimental]", b"vmIdleTimeout=88", b""])
    expected = raw.replace(b"[experimental]", b"vmIdleTimeout=-1" + newline + b"[experimental]")
    assert idle.transform(raw) == (expected, "configured")


@pytest.mark.parametrize("raw", [b"", b"# vmIdleTimeout=-1\n", b"[experimental]\nfoo=true"])
def test_missing_section_created_once(raw):
    output, status = idle.transform(raw)
    assert status == "configured" and output.count(b"[wsl2]") == 1
    assert idle.transform(output) == (output, "already_disabled")


@pytest.mark.parametrize("value,status", [("-1", "already_disabled"), ("300", "preserved_explicit_value"), ("0", "preserved_explicit_value")])
def test_explicit_setting_is_byte_identical(tmp_path, value, status):
    path = tmp_path / ".wslconfig"
    raw = ("[wsl2]\r\n vmIdleTimeout = " + value + " ; user choice").encode()
    path.write_bytes(raw)
    before = path.stat().st_mtime_ns
    assert idle.configure(path)["status"] == status
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == before


def test_bom_retained():
    raw = b"\xef\xbb\xbf[wsl2]\r\nmemory=28GB"
    assert idle.transform(raw)[0] == raw + b"\r\nvmIdleTimeout=-1\r\n"


@pytest.mark.parametrize("raw", [
    b"[wsl2]\r\nprocessors=32[wsl2]\nvmIdleTimeout=-1\n",
    b"[wsl2]\n[wsl2]\n", b"[wsl2]\n[WSL2]\n",
    b"[wsl2]\nvmIdleTimeout=-1\nvmIdleTimeout=5\n",
    b"[wsl2]\nvmIdleTimeout=invalid\n", b"[wsl2\n",
    b"memory=28GB\n", b"[wsl2]\nnot a setting\n", b"[wsl2]\n\x00",
])
def test_ambiguity_and_malformed_configuration_rejected_before_write(tmp_path, raw):
    path = tmp_path / ".wslconfig"
    path.write_bytes(raw)
    before = path.stat().st_mtime_ns
    with pytest.raises(ValueError):
        idle.configure(path)
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == before
    assert list(tmp_path.iterdir()) == [path]


def test_missing_file_and_atomic_failure(tmp_path, monkeypatch):
    path = tmp_path / ".wslconfig"
    def fail(*args):
        raise OSError("publication failed")
    monkeypatch.setattr(idle.os, "replace", fail)
    with pytest.raises(OSError):
        idle.configure(path)
    assert not path.exists() and not list(tmp_path.iterdir())


def test_missing_file_configured_exclusively(tmp_path):
    path = tmp_path / ".wslconfig"
    assert idle.configure(path)["status"] == "configured"
    assert path.read_bytes() == b"[wsl2]\nvmIdleTimeout=-1\n"
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_change_refused(tmp_path, monkeypatch):
    path = tmp_path / ".wslconfig"
    path.write_bytes(b"[wsl2]\nmemory=28GB")
    changed = b"[wsl2]\nmemory=16GB"
    monkeypatch.setattr(idle.os, "fsync", lambda fd: path.write_bytes(changed))
    with pytest.raises(RuntimeError, match="changed"):
        idle.configure(path)
    assert path.read_bytes() == changed and list(tmp_path.iterdir()) == [path]


def test_atomic_failure_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / ".wslconfig"
    raw = b"[wsl2]\nmemory=28GB"
    path.write_bytes(raw)
    monkeypatch.setattr(idle.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("failed")))
    with pytest.raises(OSError):
        idle.configure(path)
    assert path.read_bytes() == raw and list(tmp_path.iterdir()) == [path]


def test_linked_target_refused(tmp_path):
    target = tmp_path / "real"
    target.write_bytes(b"[wsl2]\n")
    link = tmp_path / "linked"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    with pytest.raises(ValueError, match="Linked"):
        idle.configure(link)
    assert target.read_bytes() == b"[wsl2]\n"


def test_standalone_bootstrap_preserves_config_when_helper_missing(tmp_path):
    import os
    import shutil
    import subprocess
    bash = Path("C:/Program Files/Git/bin/bash.exe")
    executable = str(bash) if bash.exists() else shutil.which("bash")
    if not executable:
        pytest.skip("Bash unavailable")
    source = (ROOT / "scripts/setup_pc.sh").read_text(encoding="utf-8")
    block = '    IDLE_HELPER=' + source.split('    IDLE_HELPER=', 1)[1].split('\n  else', 1)[0]
    path = tmp_path / ".wslconfig"
    raw = b"[wsl2]\r\nprocessors=32"
    path.write_bytes(raw)
    program = 'warn() { echo "$*"; }; ok() { echo "$*"; };\n' + block
    result = subprocess.run([executable, "-c", program], capture_output=True, text=True,
                            env={**os.environ, "FTLB": (tmp_path / "no-checkout").as_posix(),
                                 "WSLCONF": path.as_posix()}, timeout=10)
    assert result.returncode == 0
    assert "helper/Python unavailable" in result.stdout
    assert "vmIdleTimeout=-1" not in result.stdout
    assert path.read_bytes() == raw
