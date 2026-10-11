"""Isolated shell input gates; never invoke a game, installer or patcher."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/setup_pc.sh"


def bash():
    windows = Path("C:/Program Files/Git/bin/bash.exe")
    result = str(windows) if os.name == "nt" and windows.exists() else shutil.which("bash")
    if not result:
        pytest.skip("Bash unavailable")
    return result


@pytest.mark.parametrize("case", ["valid", "missing", "missing_hash", "mismatch", "active", "unavailable"])
def test_patcher_preflight_rejects_before_any_patch(tmp_path, case):
    tool = tmp_path / "synthetic-ftlman.exe"
    tool.write_bytes(b"synthetic executable bytes; never executed")
    tool.chmod(0o755)
    source = SCRIPT.read_text(encoding="utf-8")
    gate = source.split('  [ -n "$FTLMAN" ]', 1)[1].split('  HSFTL=', 1)[0]
    gate = '  [ -n "$FTLMAN" ]' + gate
    gate = gate.replace("/mnt/c/Windows/System32/tasklist.exe", "test_tasklist")
    digest = hashlib.sha256(tool.read_bytes()).hexdigest()
    env = dict(os.environ, FTLMAN=tool.as_posix() if case != "missing" else "",
               FTLMAN_SHA256="" if case == "missing_hash" else "0" * 64 if case == "mismatch" else digest,
               TEST_CASE=case)
    program = '''set -uo pipefail
die() { echo "$*" >&2; exit 1; }
test_tasklist() {
  [ "$TEST_CASE" != unavailable ] || return 1
  [ "$TEST_CASE" != active ] || printf 'FTLGame.exe 1234\\n'
  return 0
}
''' + gate + '\necho preflight-passed\n'
    result = subprocess.run([bash(), "-s"], input=program, text=True, capture_output=True, env=env)
    assert result.returncode == (0 if case == "valid" else 1), result.stdout + result.stderr
    assert ("preflight-passed" in result.stdout) == (case == "valid")


def test_datamod_packages_bridge_and_no_mutable_tool_acquisition():
    source = SCRIPT.read_text(encoding="utf-8")
    datamod = source.split("if want datamod; then", 1)[1].split("# STAGE locate", 1)[0]
    assert 'package_bridge.py" --source-root "$FTLB"' in datamod
    assert '--output "$FTLB/dist/ftl_bench_bridge.ftl" || die' in datamod
    patch = source.split("if want patch; then", 1)[1].split("# STAGE deploy", 1)[0]
    assert "releases/latest" not in patch and "curl" not in patch
    assert patch.index("sha256sum") < patch.index('"$FM" patch')
    assert patch.index("tasklist.exe") < patch.index('"$FM" patch')
    assert 'setup-patch-inputs.XXXXXXXX.json' in patch


@pytest.mark.parametrize("variable,valid", [("FTL_GAME_DIR", True), ("GAME", True), ("FTL_GAME_DIR", False)])
def test_explicit_game_directory_is_authoritative(tmp_path, variable, valid):
    game = tmp_path / "nondefault drive" / "FTL Faster Than Light"
    game.mkdir(parents=True)
    if valid:
        (game / "FTLGame.exe").write_bytes(b"synthetic; never executed")
        (game / "ftl.dat").write_bytes(b"synthetic data")
    source = SCRIPT.read_text(encoding="utf-8")
    locator = source.split('GAME="${FTL_GAME_DIR:', 1)[1].split("if want locate; then", 1)[0]
    locator = 'GAME="${FTL_GAME_DIR:' + locator
    # Discovery is forbidden in this probe: an invalid override must not fall back.
    program = '''set -uo pipefail
die() { echo "$*" >&2; exit 1; }
detect_win_user() { echo synthetic; }
find() { echo unexpected-discovery >&2; exit 99; }
''' + locator + '\nlocate_game\nprintf "selected=%s\\ndata=%s\\n" "$GAME" "$FTLDAT"\n'
    env = {key: value for key, value in os.environ.items() if key not in ("FTL_GAME_DIR", "GAME")}
    env[variable] = str(game)
    result = subprocess.run([bash(), "-s"], input=program, text=True, capture_output=True, env=env)
    assert result.returncode == (0 if valid else 1), result.stdout + result.stderr
    assert "unexpected-discovery" not in result.stderr
    if valid:
        assert f"selected={game}" in result.stdout
        assert f"data={game}/ftl.dat" in result.stdout
    else:
        assert "explicit FTL_GAME_DIR/GAME" in result.stderr


def test_printed_observation_check_passes_windows_save_filename():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'verify_observation.sh \\"$SAVE/ftl_agent_observation.json\\"' in source


@pytest.mark.parametrize("case", ["own", "worktree", "explicit", "standalone"])
def test_selected_benchmark_root(tmp_path, case):
    checkout = tmp_path / "selected checkout"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    if case != "standalone":
        (checkout / "native").mkdir()
        (checkout / "native/manifest.json").write_text("{}")
        if case == "worktree":
            (checkout / ".git").write_text("gitdir: synthetic")
        else:
            (checkout / ".git").mkdir()
    text = SCRIPT.read_text(encoding="utf-8")
    choice = text.split('SCRIPT_FILE=', 1)[1].split('HS="$PROJ/FTL-Hyperspace"', 1)[0]
    copied = scripts / "choose.sh"
    copied.write_text('PROJ="$TEST_PROJ"\nSCRIPT_FILE=' + choice + '\nrealpath -m -- "$FTLB"\n')
    env = {k: v for k, v in os.environ.items() if k != "FTLB_ROOT"}
    project = tmp_path / "projects"
    env["TEST_PROJ"] = str(project)
    explicit = tmp_path / "explicit"
    if case == "explicit":
        env["FTLB_ROOT"] = str(explicit)
    result = subprocess.run([bash(), str(copied)], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    expected = explicit if case == "explicit" else project / "ftl_bench" if case == "standalone" else checkout
    # Git Bash canonicalizes Windows paths into /c/...; compare using its realpath.
    canonical = subprocess.run([bash(), "-c", 'if [ -d "$EXPECTED" ]; then cd -- "$EXPECTED" && pwd -P; else realpath -m -- "$EXPECTED"; fi'],
                               capture_output=True, text=True, env=dict(env, EXPECTED=str(expected)))
    assert result.stdout.strip() == canonical.stdout.strip()


def test_existing_benchmark_revision_is_not_updated(tmp_path):
    source = SCRIPT.read_text(encoding="utf-8")
    repos = source.split("if want repos; then", 1)[1].split("  load_native_pins", 1)[0]
    assert '[ -e "$FTLB/.git" ]' in repos
    assert 'rev-parse --verify HEAD' in repos
    assert 'git pull' not in repos and 'git checkout' not in repos and 'git reset' not in repos
    assert 'git clone "$FTLB_REPO" "$FTLB" || die' in repos
    checkout = tmp_path / "worktree"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: synthetic")
    dirty = checkout / "local-edit.txt"
    dirty.write_bytes(b"preserve these exact local edits")
    program = '''set -uo pipefail
die() { echo "$*" >&2; exit 1; }
log() { :; }
ok() { :; }
git() {
  printf '%s\\n' "$*"
  [ "$3" = rev-parse ] || exit 99
}
''' + repos
    result = subprocess.run([bash(), "-s"], input=program, text=True, capture_output=True,
                            env=dict(os.environ, FTLB=str(checkout), PROJ=str(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert dirty.read_bytes() == b"preserve these exact local edits"
