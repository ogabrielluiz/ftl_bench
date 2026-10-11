"""Smoke a built wheel in an isolated directory, including bundled UI and native patch.

Does not read game files, start FTL, deploy artifacts, or contact model providers.
Creates a temporary venv and downloads the wheel's dashboard dependencies via uv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile


def isolated_python_environment(environment=None):
    """Let the selected interpreter locate its own libraries and virtual environment.

    Some managed Python launchers populate PYTHONHOME in the running parent.
    Inheriting that home into a different Python version mixes its Lib/DLLs.
    Preserve uv's interpreter selection and ordinary process settings.
    """
    inherited = os.environ if environment is None else environment
    overrides = {"PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__", "PYTHONEXECUTABLE"}
    return {key: value for key, value in inherited.items() if key.upper() not in overrides}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, help="defaults to the newest harness/dist wheel")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    candidates = sorted((repo / "harness/dist").glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if args.wheel is None and not candidates:
        parser.error("build a wheel first or provide --wheel")
    wheel = (args.wheel or candidates[-1]).resolve()
    required = ["README.md", "adapter/README.md", "adapter/run_benchmark.py", "adapter/decision_backends.py",
                "adapter/visual_agent.py", "adapter/run_visual.py", "adapter/visible_hud.py",
                "adapter/visual_reporting.py", "prompts/ftl_visual_v1.md", "prompts/ftl_visual_v2.md",
                "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua", "prompts/ftl_agent_v5.md",
                "native/manifest.json", "native/patches/0002-economy-fuel-controls.patch",
                "native/patches/0003-visual-io.patch", "native/include/Benchmark_FreshStartSeed.inc",
                "native/include/Benchmark_FreshStartUtility.h", "scripts/validate_visual_live.py",
                "scripts/validate_visual_interference.py", "scripts/validate_visual_sector.py",
                "scripts/validate_visual_challenges.py", "scripts/validate_visual_timing.py",
                "scripts/run_visual_experiment.py", "scripts/run_fullgame_experiment.py",
                "native/manifest.protocol4.json", "native/patches/0001-reliable-benchmark-controls.patch",
                "scripts/apply_native_patch.py", "scripts/smoke_package.py", "dashboard/dist/index.html"]
    with zipfile.ZipFile(wheel) as archive:
        for relative in required:
            bundled = archive.read("ftl_bench/_bundled/" + relative)
            if bundled != (repo / relative).read_bytes():
                raise RuntimeError(f"Wheel is stale or incomplete: {relative}")
        for relative in ("observation.py", "protected_game.py", "visual_session.py",
                         "fullgame_setup.py", "challenge_setup.py", "controller_admission.py",
                         "experiment_admission.py", "visual_admission.py"):
            if archive.read("ftl_bench/" + relative) != (repo / "harness/src/ftl_bench" / relative).read_bytes():
                raise RuntimeError(f"Wheel runtime module is stale: {relative}")
        for asset in (repo / "dashboard/dist/assets").iterdir():
            if asset.is_file() and archive.read("ftl_bench/_bundled/dashboard/dist/assets/" + asset.name) != asset.read_bytes():
                raise RuntimeError(f"Wheel dashboard asset is stale: {asset.name}")
    temporary = Path(tempfile.mkdtemp(prefix="ftlbench-package-smoke-"))
    child_environment = isolated_python_environment()
    environment = temporary / "venv"
    subprocess.run(["uv", "venv", str(environment)], cwd=temporary, check=True, env=child_environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel) + "[dashboard]"],
                   cwd=temporary, check=True, env=child_environment)
    for arguments in (["version"], ["run", "--help"], ["visual", "--help"], ["install-native", "--help"], ["report", "--help"]):
        result = subprocess.run([str(python), "-m", "ftl_bench.cli", *arguments],
                                cwd=temporary, check=True, capture_output=True, text=True, env=child_environment)
        print(result.stdout.splitlines()[0])
    code = """
from ftl_bench.cli import _bench_root
import ctypes, hashlib, json, subprocess, sys
print(json.dumps({'package_python': {'version': sys.version, 'executable': sys.executable,
    'base_prefix': sys.base_prefix, 'ctypes_file': ctypes.__file__}}))
root = _bench_root()
assert root.name == '_bundled', root
manifest = json.loads((root/'native/manifest.json').read_text())
assert manifest['native_protocol'] >= 5
assert hashlib.sha256((root/manifest['patch']).read_bytes()).hexdigest() == manifest['patch_sha256']
patch = (root/manifest['patch']).read_text()
for binding in ('benchmark_set_difficulty', 'benchmark_upgrade_system', 'benchmark_upgrade_reactor',
                'benchmark_wait_for_fuel', 'benchmark_set_distress', 'benchmark_economy_state',
                'benchmark_leave_sector', 'benchmark_jump_to_beacon'):
    assert binding in patch, binding
assert 'sector_navigation_version' in patch
assert 'beacon_navigation_version' in patch
lua = (root/'mod/ftl_bench_bridge/dev/ftl_bench_dev.lua').read_text()
assert 'sector_navigation' in lua
assert 'beacon_navigation' in lua
assert 'enemy_hostility' in lua
runner = (root/'adapter/run_benchmark.py').read_text()
assert 'RUNNER_VERSION = "v7"' in runner
assert 'native-sector-neighbors-v1' in runner
assert 'native-beacon-readiness-v1' in runner
assert 'native-enemy-hostility-v1' in runner
assert manifest['visual_io_version'] == 1
assert manifest['visual_clock_version'] == 2
assert manifest['fixed_step_numerator'] == 1 and manifest['fixed_step_denominator'] == 60
assert manifest['fresh_start_seed'] is True
assert manifest['fresh_seed_contract_version'] == 3
assert manifest['fresh_seed_contract'] == 'fresh-start-seed-v3'
for header in ('Benchmark_FreshStartSeed.inc', 'Benchmark_FreshStartUtility.h'):
    assert (root/'native/include'/header).is_file()
    assert ('diff --git a/' + header + ' b/' + header) in patch
assert 'benchmark_setup' in lua and 'fresh-start-seed-v3' in lua
assert 'benchmark_visual' in patch
assert 'visual_clock_version' in patch and 'world_updates' in patch
assert 'visual_clock_version' in lua and 'world_updates' in lua
sys.path.insert(0, str(root/'adapter'))
from visual_agent import CodexVisualAgent, VisualObservation, decision_schema
from ftl_bench.visual_session import VisualSession, VisualTransportError, validate_visual_clock
from ftl_bench.observation import Observation
from ftl_bench.protected_game import ProtectedGame
from ftl_bench.fullgame_setup import FullGameSetupSession
from ftl_bench.challenge_setup import DeterministicSetupSession
assert CodexVisualAgent().model == 'gpt-6.1-sol'
assert decision_schema(1280, 720)['properties']['actions']['maxItems'] == 4
assert (root/'prompts/ftl_visual_v1.md').is_file()
clock = Observation.from_dict({'schema_version': 3, 'tick': 0, 'seed': 1, 'game_started': True, 'paused': True,
    'capabilities': {'visual_clock_version': 2, 'world_updates': '42', 'simulated_updates': '42',
                     'fixed_step_numerator': 1, 'fixed_step_denominator': 60},
    'visual': {'visual_clock_version': 2, 'world_updates': '42', 'simulated_updates': '42',
               'fixed_step_numerator': 1, 'fixed_step_denominator': 60}})
assert validate_visual_clock(clock, synchronized=True) == '42'
del clock.raw['capabilities']['visual_clock_version']
try:
    validate_visual_clock(clock, synchronized=True)
except VisualTransportError:
    pass
else:
    raise AssertionError('Installed runtime accepted the old pause-only clock')
for script in ('validate_visual_live.py', 'validate_visual_interference.py', 'validate_visual_sector.py',
               'validate_visual_challenges.py', 'run_visual_experiment.py', 'run_fullgame_experiment.py',
               'validate_visual_startup.py', 'validate_visual_timing.py', 'validate_native_acceptance.py',
               'collect_native_source_evidence.py'):
    result = subprocess.run([sys.executable, str(root/'scripts'/script), '--help'], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(script + ' help failed: ' + result.stderr + result.stdout)
archived = json.loads((root/'native/manifest.protocol4.json').read_text())
assert archived['native_protocol'] == 4
assert hashlib.sha256((root/archived['patch']).read_bytes()).hexdigest() == archived['patch_sha256']
subprocess.run([sys.executable, str(root/'scripts/apply_native_patch.py'), '--help'], check=True, capture_output=True)
print('Isolated bundled CLI/native patch verified')
"""
    subprocess.run([str(python), "-c", code], cwd=temporary, check=True, env=child_environment)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    command = [str(python), "-m", "ftl_bench.cli", "dashboard", "--runs", str(temporary/"runs"),
               "--port", str(port)]
    with (temporary/"dashboard.log").open("w") as log:
        process = subprocess.Popen(command, cwd=temporary, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                   env=child_environment)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError((temporary/"dashboard.log").read_text())
                try:
                    with urllib.request.urlopen(base+"/api/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Installed dashboard did not start")
            assert health["dashboard_built"] and health["scorer"], health
            with urllib.request.urlopen(base, timeout=5) as response:
                page = response.read().decode()
            assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', page)
            assert assets, "Installed UI has no production assets"
            for asset in assets:
                with urllib.request.urlopen(base+asset, timeout=5) as response:
                    assert response.status == 200 and response.read()
            with urllib.request.urlopen(base+"/api/state", timeout=5) as response:
                assert isinstance(json.load(response), dict)
            print("Installed dashboard HTML/assets/API verified")
        finally:
            process.terminate()
            process.wait(timeout=10)
    print(json.dumps({"wheel": str(wheel), "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                      "temporary_directory": str(temporary)}, indent=2))


if __name__ == "__main__":
    main()
