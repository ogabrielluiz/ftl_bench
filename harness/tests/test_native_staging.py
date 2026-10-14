"""Portable bootstrap contracts with synthetic artifacts; no builds or installs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from ftl_bench.cli import _bench_root


ROOT = _bench_root()
spec = importlib.util.spec_from_file_location("native_staging", ROOT / "scripts/stage_native_artifacts.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
IMAGE = "ghcr.io/example/toolchain@sha256:" + "a" * 64


@pytest.fixture
def artifacts(tmp_path):
    manifest = helper.manifest_from(ROOT)
    dll = tmp_path / "build/Hyperspace.dll"
    dll.parent.mkdir()
    dll.write_bytes(b"synthetic DLL for file-only staging")
    provenance = dll.with_suffix(".json")
    value = {key: manifest[key] for key in ("repository", "patch_sha256", *helper.CAPABILITIES)}
    value.update(source_commit=manifest["base_commit"], platform="windows-x86", game_version="1.6.9",
        dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(), dll_size=dll.stat().st_size,
        toolchain={"image": IMAGE, "image_id": "sha256:" + "b" * 64})
    provenance.write_text(json.dumps(value))
    return dll, provenance, manifest, value


def test_stages_exact_visual_pair_idempotently_and_preserves_structured_pair(tmp_path, artifacts):
    dll, provenance, manifest, _ = artifacts
    output = tmp_path / "dist"
    output.mkdir()
    historical = output / "Hyperspace.protocol5.dll"
    historical.write_bytes(b"historical structured DLL")
    result = helper.stage_pair(dll, provenance, output, manifest)
    assert result["status"] == "staged" and result["acceptance"] == "not_evaluated"
    assert (output / helper.NAMES[0]).read_bytes() == dll.read_bytes()
    assert (output / helper.NAMES[1]).read_bytes() == provenance.read_bytes()
    assert historical.read_bytes() == b"historical structured DLL"
    assert helper.stage_pair(dll, provenance, output, manifest)["status"] == "unchanged"
    assert not (output / "native-history").exists()


def test_replacement_retains_prior_pair_and_rolls_back_an_observed_publish_failure(tmp_path, artifacts, monkeypatch):
    dll, provenance, manifest, _ = artifacts
    output = tmp_path / "dist"
    output.mkdir()
    old = {name: ("previous " + name).encode() for name in helper.NAMES}
    for name, data in old.items(): (output / name).write_bytes(data)
    original_replace = helper.os.replace
    def fail_second(source, destination):
        if destination.name == helper.NAMES[1]:
            raise OSError("synthetic publish failure")
        original_replace(source, destination)
    monkeypatch.setattr(helper.os, "replace", fail_second)
    with pytest.raises(OSError, match="synthetic"):
        helper.stage_pair(dll, provenance, output, manifest)
    assert {name: (output / name).read_bytes() for name in helper.NAMES} == old
    assert not list(output.glob(".*.tmp"))
    archive = next((output / "native-history").iterdir())
    assert {name: (archive / name).read_bytes() for name in helper.NAMES} == old
    monkeypatch.setattr(helper.os, "replace", original_replace)
    result = helper.stage_pair(dll, provenance, output, manifest)
    assert result["previous_artifacts"] and (output / helper.NAMES[0]).read_bytes() == dll.read_bytes()


@pytest.mark.parametrize("change", ["dll", "size", "base", "patch", "clock", "seed", "tag", "local_id", "resolved_id", "platform"])
def test_mismatched_artifacts_never_change_existing_outputs(tmp_path, artifacts, change):
    dll, provenance, manifest, value = artifacts
    output = tmp_path / "dist"
    if change == "dll": dll.write_bytes(b"changed")
    elif change == "size": value["dll_size"] = True
    elif change == "base": value["source_commit"] = "0" * 40
    elif change == "patch": value["patch_sha256"] = "0" * 64
    elif change == "clock": value["visual_clock_version"] = 1
    elif change == "seed": value["fresh_start_seed"] = 1
    elif change == "tag": value["toolchain"]["image"] = "ghcr.io/example/toolchain:v2"
    elif change == "local_id": value["toolchain"]["image"] = "sha256:" + "a" * 64
    elif change == "resolved_id": value["toolchain"]["image_id"] = "unknown"
    else: value["platform"] = "linux-amd64"
    provenance.write_text(json.dumps(value))
    with pytest.raises(ValueError): helper.stage_pair(dll, provenance, output, manifest)
    assert not output.exists()


def bash():
    local = Path("C:/Program Files/Git/bin/bash.exe")
    binary = str(local) if os.name == "nt" and local.exists() else shutil.which("bash")
    if not binary: pytest.skip("Bash unavailable")
    return binary


def test_setup_script_has_valid_bash_syntax():
    result = subprocess.run([bash(), "-n", str(ROOT / "scripts/setup_pc.sh")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("image,failure,expected", [(IMAGE, "", 0), ("ghcr.io/example/toolchain:v2", "", 1),
    ("sha256:" + "a" * 64, "", 1), (IMAGE, "pull", 1), (IMAGE, "base", 1)])
def test_build_stage_uses_pinned_commands_and_stages_visual_pair_only(tmp_path, image, failure, expected, caps=None):
    project = tmp_path / "projects"
    dll = project / "FTL-Hyperspace/build-windows-release/Hyperspace.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"synthetic build output")
    trace = tmp_path / "calls.txt"
    env = dict(os.environ, PROJ=str(project), FTLB_ROOT=str(project / "ftl_bench"), STAGES="build", DEVCONTAINER=image,
               TEST_TRACE=str(trace), TEST_FAILURE=failure)
    env.pop("FTLB_BUILD_MEMORY", None)
    env.pop("FTLB_BUILD_CPUS", None)
    env.pop("FTLB_BUILD_JOBS", None)
    env.update(caps or {})
    script = r'''
docker() { printf 'docker'; printf ' [%s]' "$@"; printf '\n';
  [ "$TEST_FAILURE" != "$1" ]; } >> "$TEST_TRACE"
python3() {
  printf 'python'; printf ' [%s]' "$@"; printf '\n';
  case "$1" in
    */stage_native_artifacts.py) if [ "$2" = config ]; then
      printf 'https://example.invalid/native.git\n1111111111111111111111111111111111111111\n' >&3
    fi ;;
    */apply_native_patch.py) [ "$TEST_FAILURE" != base ] || return 1 ;;
  esac
} 3>&1 >> "$TEST_TRACE"
source "$1"
'''
    result = subprocess.run([bash(), "-s", "--", str(ROOT / "scripts/setup_pc.sh")],
                            input=script, capture_output=True, text=True, env=env)
    assert result.returncode == expected, result.stdout + result.stderr
    calls = trace.read_text() if trace.exists() else ""
    if expected == 0:
        assert f"docker [pull] [--platform] [linux/amd64] [{image}]" in calls
        assert f"[{image}] [bash] [-c]" in calls
        assert "[--require-base]" in calls and "[--require-immutable-image]" in calls
        assert "native-build.visual-v1.json" in calls and "] [stage] [--dll]" in calls
        assert "archive_native_build.py] [prepare]" in calls
        assert "archive_native_build.py] [finish]" in calls
        assert calls.index("archive_native_build.py] [prepare]") < calls.index("docker [run]")
        assert calls.index("archive_native_build.py] [finish]") < calls.index("] [stage] [--dll]")
        assert "/artifacts/Hyperspace.visual-v1.dll] [--provenance]" in calls
        assert "/artifacts/native-build.visual-v1.json]" in calls
        for key, flag in (("FTLB_BUILD_MEMORY", "--memory"), ("FTLB_BUILD_CPUS", "--cpus")):
            if key in (caps or {}):
                assert f"[{flag}] [{caps[key]}]" in calls
            else:
                assert f"[{flag}]" not in calls
        if "FTLB_BUILD_MEMORY" in (caps or {}):
            assert f"[--memory-swap] [{caps['FTLB_BUILD_MEMORY']}]" in calls
        else:
            assert "[--memory-swap]" not in calls
        if "FTLB_BUILD_JOBS" in (caps or {}):
            assert f"[-e] [FTLB_BUILD_JOBS={caps['FTLB_BUILD_JOBS']}]" in calls
            assert f"[-e] [VCPKG_MAX_CONCURRENCY={caps['FTLB_BUILD_JOBS']}]" in calls
            assert 'export -f ninja' in calls
        else:
            assert 'FTLB_BUILD_JOBS=' not in calls and 'export -f ninja' not in calls
        assert "native-build.protocol5.json" not in calls and "build-releaseonly-from-docker.sh" not in calls
    else:
        assert "] [stage]" not in calls and "write_native_provenance.py" not in calls
        assert "docker [run]" not in calls


@pytest.mark.parametrize("caps", [
    {"FTLB_BUILD_MEMORY": "3g"}, {"FTLB_BUILD_CPUS": "1"}, {"FTLB_BUILD_JOBS": "1"},
    {"FTLB_BUILD_MEMORY": "3072m", "FTLB_BUILD_CPUS": "2", "FTLB_BUILD_JOBS": "2"},
])
def test_optional_build_caps_are_exact_docker_arguments(tmp_path, caps):
    test_build_stage_uses_pinned_commands_and_stages_visual_pair_only(tmp_path, IMAGE, "", 0, caps)


@pytest.mark.parametrize("key,value", [
    ("FTLB_BUILD_MEMORY", value) for value in ("", "0g", "-1g", "3", "3.5g", "3g --privileged", " 3g")
] + [("FTLB_BUILD_CPUS", value) for value in ("", "0", "-1", "1.5", "1;true", " 1")] + [("FTLB_BUILD_JOBS", value) for value in ("", "0", "-1", "1.5", "1;true", " 1")])
def test_invalid_build_caps_reject_before_mutation(tmp_path, key, value):
    test_build_stage_uses_pinned_commands_and_stages_visual_pair_only(tmp_path, IMAGE, "", 1, {key: value})
    calls = (tmp_path / "calls.txt").read_text() if (tmp_path / "calls.txt").exists() else ""
    assert "apply_native_patch.py" not in calls
    assert "docker [pull]" not in calls and "docker [run]" not in calls
    assert "archive_native_build.py" not in calls


def test_other_stages_do_not_require_image_and_install_consumes_verified_staged_pair():
    source = (ROOT / "scripts/setup_pc.sh").read_text(encoding="utf-8")
    build = source.split("if want build; then", 1)[1].split("# STAGE datamod", 1)[0]
    install = source.split("if want install; then", 1)[1].split("# STAGE patch", 1)[0]
    assert "registry/repository@sha256" in build
    assert 'DLL="$FTLB/dist/Hyperspace.visual-v1.dll"' in install
    assert 'PROVENANCE="$FTLB/dist/native-build.visual-v1.json"' in install
    assert install.index("stage_native_artifacts.py\" verify") < install.index("powershell.exe")
    assert '--dll "$DLL" --manifest "$PROVENANCE"' in install


@pytest.mark.parametrize("existing", ["fresh", "matching", "different"])
def test_repo_stage_pins_fresh_checkout_and_never_rewrites_an_existing_native_head(tmp_path, existing):
    project = tmp_path / "projects"
    (project / "ftl_bench/.git").mkdir(parents=True)
    native = project / "FTL-Hyperspace"
    if existing != "fresh": (native / ".git").mkdir(parents=True)
    trace = tmp_path / "calls.txt"
    env = dict(os.environ, PROJ=str(project), FTLB_ROOT=str(project / "ftl_bench"), STAGES="repos", DEVCONTAINER="",
               TEST_TRACE=str(trace), TEST_EXISTING=existing)
    script = r'''
python3() { printf 'https://example.invalid/native.git\n1111111111111111111111111111111111111111\n'; }
git() {
  printf 'git'; printf ' [%s]' "$@"; printf '\n' >&3
  if [ "$1" = clone ]; then mkdir -p "${@: -1}/.git"; fi
  if [ "${3:-}" = rev-parse ]; then
    if [ "$TEST_EXISTING" = matching ]; then printf '1111111111111111111111111111111111111111\n' >&4
    else printf '2222222222222222222222222222222222222222\n' >&4; fi
  fi
} 3>> "$TEST_TRACE" 4>&1 >> "$TEST_TRACE"
source "$1"
'''
    result = subprocess.run([bash(), "-s", "--", str(ROOT / "scripts/setup_pc.sh")],
                            input=script, capture_output=True, text=True, env=env)
    assert result.returncode == (1 if existing == "different" else 0), result.stdout + result.stderr
    calls = trace.read_text()
    if existing == "fresh":
        assert "[clone] [--no-checkout] [https://example.invalid/native.git]" in calls
        assert "[checkout] [--detach] [1111111111111111111111111111111111111111]" in calls
    else:
        assert "[checkout]" not in calls and "[reset]" not in calls and "[clone]" not in calls


def test_build_jobs_reaches_nested_bash_direct_ninja(tmp_path):
    source = (ROOT / "scripts/setup_pc.sh").read_text()
    inner = next(line.split("BUILD_INNER='", 1)[1].rsplit("'", 1)[0]
                 for line in source.splitlines() if "BUILD_INNER='ninja()" in line)
    (tmp_path / ".devcontainer").mkdir()
    (tmp_path / ".devcontainer/devcontainer-fixes.sh").write_text("")
    scripts = tmp_path / "buildscripts/windows"
    scripts.mkdir(parents=True)
    (scripts / "build-releaseonly.sh").write_text("#!/usr/bin/env bash\nbash buildscripts/windows/build-one-variant.sh\n")
    (scripts / "build-one-variant.sh").write_text("#!/usr/bin/env bash\nninja -C build-windows-release\n")
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "ninja").write_text("#!/usr/bin/env bash\nprintf '[%s]' \"$@\"\nprintf '\\n'\nprintf 'dependency_jobs=%s\\n' \"$VCPKG_MAX_CONCURRENCY\"\n")
    # Git Bash understands /c/...; bash itself sets executable permissions.
    env = dict(os.environ, FTLB_BUILD_JOBS="1", VCPKG_MAX_CONCURRENCY="1")
    setup = 'chmod +x bin/ninja buildscripts/windows/*.sh; export PATH="$PWD/bin:$PATH"; ' + inner
    result = subprocess.run([bash(), "-c", setup], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "[-j][1][-C][build-windows-release]" in result.stdout
    assert "dependency_jobs=1" in result.stdout
