"""Verify distributed fresh-start helpers and execute their actual C++ include."""
import json
import shutil
import subprocess

import pytest

from ftl_bench.cli import _bench_root


def test_fresh_start_contract_and_distributed_source():
    root = _bench_root()
    manifest = json.loads((root / "native/manifest.json").read_text())
    assert manifest["fresh_start_seed"] is True
    assert manifest["fresh_seed_contract_version"] == 3
    assert manifest["fresh_seed_contract"] == "fresh-start-seed-v3"
    patch = (root / manifest["patch"]).read_text()
    for name in ("Benchmark_FreshStartSeed.inc", "Benchmark_FreshStartUtility.h"):
        section = patch.split(f"diff --git a/{name} b/{name}\n", 1)[1].split("diff --git ", 1)[0]
        added = "\n".join(line[1:] for line in section.splitlines()
                          if line.startswith("+") and not line.startswith("+++")) + "\n"
        assert added == (root / "native/include" / name).read_text()


def test_actual_fresh_start_cpp_include(tmp_path):
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("host C++ compiler unavailable; run native fresh_start_test in WSL")
    root = _bench_root()
    executable = tmp_path / "fresh-start-test"
    subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-pedantic",
                    "-I", str(root / "native/tests/stubs"), "-I", str(root / "native/include"),
                    str(root / "native/tests/fresh_start_test.cpp"), "-o", str(executable)], check=True)
    result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout.splitlines()[-1])["actual_candidate_include_tests_passed"] == 72
