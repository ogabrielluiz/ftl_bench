"""Native patch deployment validates content and preserves conflicting local edits."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import re

import pytest
from ftl_bench.cli import _bench_root


def helper(tmp_path, monkeypatch):
    script = _bench_root() / "scripts/apply_native_patch.py"
    spec = importlib.util.spec_from_file_location("bench_native_patch", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = tmp_path / "distribution"
    (fixture / "native").mkdir(parents=True)
    patch = b"--- a/control.cpp\n+++ b/control.cpp\n@@ -1 +1 @@\n-idle=-1\n+idle=0\n"
    (fixture / "native/controls.patch").write_bytes(patch)
    (fixture / "native/manifest.json").write_text(json.dumps({
        "patch": "native/controls.patch", "patch_sha256": hashlib.sha256(patch).hexdigest()}))
    monkeypatch.setattr(module, "__file__", str(fixture / "scripts/apply_native_patch.py"))
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=source, check=True, capture_output=True)
    (source / "control.cpp").write_bytes(b"idle=-1\n")
    return module, source, fixture


def test_native_patch_checks_applies_and_recognizes_repeat(tmp_path, monkeypatch):
    module, source, _ = helper(tmp_path, monkeypatch)
    assert module.apply_patch(source, check_only=True) == "ready to apply"
    assert (source / "control.cpp").read_bytes() == b"idle=-1\n"
    assert module.apply_patch(source) == "applied"
    assert (source / "control.cpp").read_bytes() == b"idle=0\n"
    assert module.apply_patch(source) == "already applied"


def test_native_patch_conflict_and_bad_hash_preserve_source(tmp_path, monkeypatch):
    module, source, fixture = helper(tmp_path, monkeypatch)
    (source / "control.cpp").write_bytes(b"user local change\n")
    with pytest.raises(ValueError, match="local changes were preserved"):
        module.apply_patch(source)
    assert (source / "control.cpp").read_bytes() == b"user local change\n"
    (fixture / "native/controls.patch").write_bytes(b"changed patch content")
    with pytest.raises(ValueError, match="SHA-256"):
        module.apply_patch(source)
    assert (source / "control.cpp").read_bytes() == b"user local change\n"


@pytest.mark.parametrize("available", [False, True])
def test_shipped_economy_getter_serializes_sector_navigation_version(available):
    """Decode the actual getter prefix used in both menus and an active game.

    Mocking the Lua economy response missed a release whose C++ JSON omitted
    this field, so this checks the implementation shipped in the native patch.
    """
    root = _bench_root()
    manifest = json.loads((root / "native/manifest.json").read_text())
    patch = (root / manifest["patch"]).read_text()
    getter = patch.split("+const char* hs_benchmark_economy_state()", 1)[1].split("\n+}", 1)[0]
    literal = re.search(
        r'json\s*<<\s*std::boolalpha\s*<<\s*("(?:[^"\\]|\\.)*")', getter
    )
    assert literal is not None, "economy getter must serialize a JSON prefix"
    prefix = ast.literal_eval(literal.group(1))
    header = json.loads(prefix + json.dumps(available) + "}")
    assert header["native_protocol"] == manifest["native_protocol"] == 5
    assert header["sector_navigation_version"] == 1
    assert header["beacon_navigation_version"] == 1
    assert header["upgrade_available"] is available


@pytest.mark.parametrize("can_jump,pending,charge", [(False, False, 0), (True, True, 85)])
def test_shipped_navigation_json_uses_exact_native_fields(can_jump, pending, charge):
    root = _bench_root()
    manifest = json.loads((root / "native/manifest.json").read_text())
    patch = (root / manifest["patch"]).read_text()
    getter = patch.split("+const char* hs_benchmark_economy_state()", 1)[1].split("\n+}", 1)[0]
    navigation = getter.split("const auto navigation = travel_context(app, player);", 1)[1]
    literals = re.findall(r'<<\s*("(?:[^"\\]|\\.)*")', navigation)
    fragments = [ast.literal_eval(value) for value in literals[:5]]
    output = "{" + fragments[0].lstrip(",") + json.dumps(can_jump)
    output += fragments[1] + json.dumps(pending) + fragments[2] + str(charge)
    output += fragments[3] + "85" + fragments[4] + "null}}"
    assert json.loads(output) == {"navigation": {"can_jump": can_jump,
        "enemy_defeat_pending": pending, "drive_current": charge, "drive_max": 85, "reason": None}}


def test_shipped_sector_leave_uses_native_hostility_not_retained_pointer_as_combat():
    root = _bench_root()
    manifest = json.loads((root / "native/manifest.json").read_text())
    patch = (root / manifest["patch"]).read_text()
    hunks = patch.split("hs_benchmark_leave_sector()", 1)[1].split("diff --git", 1)[0]
    leave = "\n".join(line[1:] for line in hunks.splitlines() if line.startswith(("+", " ")))
    assert re.search(r"sector_enemy_blocks\(\s*enemy->_targetable\.hostile,\s*enemy->bDestroyed\)", leave)
    assert "if (enemy && !enemy->bDestroyed)" not in leave
