"""Run the regression suite from an unpacked source release outside the checkout.

This verifies bundled adapter, Lua, scenarios and native helper paths. Tests block
unmocked provider requests and never start FTL or write to the user's installation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile


def isolated_python_environment(environment=None):
    """Discard parent library/launcher overrides without pinning uv's Python choice."""
    inherited = os.environ if environment is None else environment
    overrides = {"PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__", "PYTHONEXECUTABLE"}
    return {key: value for key, value in inherited.items() if key.upper() not in overrides}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdist", type=Path, help="defaults to the newest harness/dist source release")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    candidates = sorted((repo / "harness/dist").glob("*.tar.gz"), key=lambda path: path.stat().st_mtime)
    if args.sdist is None and not candidates:
        parser.error("build a source release first or provide --sdist")
    archive_path = (args.sdist or candidates[-1]).resolve()
    temporary = Path(tempfile.mkdtemp(prefix="ftlbench-sdist-smoke-"))
    child_environment = isolated_python_environment()
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(temporary, filter="data")
    projects = [path for path in temporary.iterdir() if path.is_dir() and (path / "pyproject.toml").is_file()]
    if len(projects) != 1:
        raise RuntimeError("Source release must contain exactly one Python project")
    source = projects[0]
    command = ["uv", "run", "--directory", str(source), "--extra", "dev", "--extra", "dashboard"]
    check = """
from ftl_bench.cli import _bench_root
import ctypes, hashlib, json, subprocess, sys
print(json.dumps({'package_python': {'version': sys.version, 'executable': sys.executable,
    'base_prefix': sys.base_prefix, 'ctypes_file': ctypes.__file__}}))
root = _bench_root()
assert root.name == '_bundled', root
for filename, protocol in (('manifest.json', 5), ('manifest.protocol4.json', 4)):
    manifest = json.loads((root/'native'/filename).read_text())
    assert manifest['native_protocol'] == protocol
    assert hashlib.sha256((root/manifest['patch']).read_bytes()).hexdigest() == manifest['patch_sha256']
current = json.loads((root/'native/manifest.json').read_text())
assert 'sector_navigation_version' in (root/current['patch']).read_text()
assert 'beacon_navigation_version' in (root/current['patch']).read_text()
assert 'sector_navigation' in (root/'mod/ftl_bench_bridge/dev/ftl_bench_dev.lua').read_text()
assert 'beacon_navigation' in (root/'mod/ftl_bench_bridge/dev/ftl_bench_dev.lua').read_text()
assert 'enemy_hostility' in (root/'mod/ftl_bench_bridge/dev/ftl_bench_dev.lua').read_text()
runner = (root/'adapter/run_benchmark.py').read_text()
assert 'RUNNER_VERSION = "v7"' in runner and 'native-sector-neighbors-v1' in runner
assert 'native-beacon-readiness-v1' in runner
assert 'native-enemy-hostility-v1' in runner
assert current['visual_io_version'] == 1
assert current['visual_clock_version'] == 2
assert current['fixed_step_numerator'] == 1 and current['fixed_step_denominator'] == 60
assert current['fresh_start_seed'] is True
assert current['fresh_seed_contract_version'] == 3
assert current['fresh_seed_contract'] == 'fresh-start-seed-v3'
for header in ('Benchmark_FreshStartSeed.inc', 'Benchmark_FreshStartUtility.h'):
    assert (root/'native/include'/header).is_file()
    assert ('diff --git a/' + header + ' b/' + header) in (root/current['patch']).read_text()
assert 'visual_clock_version' in (root/current['patch']).read_text()
assert 'world_updates' in (root/current['patch']).read_text()
for path in ('adapter/visual_agent.py', 'adapter/run_visual.py', 'prompts/ftl_visual_v1.md',
             'scripts/validate_visual_live.py', 'scripts/validate_visual_interference.py', 'scripts/validate_visual_sector.py',
             'native/patches/0003-visual-io.patch'):
    assert (root/path).is_file(), path
from ftl_bench.visual_session import VisualSession, validate_visual_clock
from ftl_bench.protected_game import ProtectedGame
from ftl_bench.fullgame_setup import FullGameSetupSession
from ftl_bench.challenge_setup import DeterministicSetupSession
for script in ('validate_visual_live.py', 'validate_visual_interference.py', 'validate_visual_sector.py',
               'validate_visual_challenges.py', 'run_visual_experiment.py', 'run_fullgame_experiment.py'):
    result = subprocess.run([sys.executable, str(root/'scripts'/script), '--help'], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(script + ' help failed: ' + result.stderr + result.stdout)
print('Isolated source release uses current and archived bundled native patches')
"""
    subprocess.run([*command, "python", "-c", check], cwd=temporary, check=True, env=child_environment)
    subprocess.run([*command, "pytest", "-q", "-rs"], cwd=temporary, check=True, env=child_environment)
    print(json.dumps({"sdist": str(archive_path), "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                      "temporary_directory": str(temporary)}, indent=2))


if __name__ == "__main__":
    main()
