"""Synthetic files and shell parsing only; never start Docker, FTL or a model."""
import importlib.util
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

HEADLESS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("headless_aggregate", HEADLESS / "aggregate_parallel.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from ftl_bench import Scenario, SubObjective


@pytest.fixture
def suite(tmp_path):
    cases = [Scenario("one", "custom", 1, [SubObjective("final_hull", 1)]),
             Scenario("two", "custom", 2, [SubObjective("final_hull", 1)])]
    path = tmp_path / "suite.json"
    path.write_text(json.dumps({"scenarios": [s.to_dict() for s in cases]}))
    return path, cases


def attempt(directory, scenario, *, filename=None, status="completed", manifest=True,
            embedded=True, terminal=True, run_status=None):
    directory.mkdir(parents=True, exist_ok=True)
    meta = {"scenario_id": scenario.id}
    if embedded:
        meta["scenario"] = scenario.to_dict()
    rows = [{"kind": "meta", "meta": meta}, {"kind": "step", "actions": [], "obs": {
        "game_started": True, "player_ship": {"hull": {"current": 30}, "crew": [{"dead": False}]},
        "ftl_score": 40}}]
    if terminal:
        rows.append({"kind": "end", "status": status, "reason": "budget"})
    path = directory / (filename or scenario.id + ".jsonl")
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    if manifest:
        (directory / "run.json").write_text(json.dumps({"run_id": directory.name,
            "scenario_ids": [scenario.id], "status": run_status or status}))
    return path


def test_new_nested_shards_are_found_and_recomputed(tmp_path, suite):
    path, cases = suite
    for index, case in enumerate(cases):
        attempt(tmp_path / "runs" / f"invocation-{index}", case)
    report = module.collect_results(path, tmp_path / "runs")
    assert report["complete"] and report["aggregate"]["instances"] == 2
    assert len(report["attempts"]) == 2 and len(report["invocations"]) == 2
    assert module.main([str(path), str(tmp_path / "runs")]) == 0


def test_explicit_budget_cap_matches_effective_recorded_scenario(tmp_path, suite):
    path, cases = suite
    attempt(tmp_path / "runs/a", replace(cases[0], budget_jumps=3))
    assert not module.collect_results(path, tmp_path / "runs", maxn=1)["complete"]
    report = module.collect_results(path, tmp_path / "runs", maxn=1, budget_cap=3)
    assert report["complete"] and report["aggregate"]["instances"] == 1
    assert report["attempts"][0]["result"]["budget_jumps"] == 3


def test_early_solved_retry_condition_is_retained_and_never_mislabeled_pass_at_one(tmp_path, suite):
    path, cases = suite
    target = attempt(tmp_path / "runs/a", cases[0], filename="one.a0.jsonl")
    manifest = target.parent / "run.json"
    data = json.loads(manifest.read_text())
    data.update(retries=2, mode="budget")
    manifest.write_text(json.dumps(data))
    report = module.collect_results(path, tmp_path / "runs", maxn=1)
    assert not report["complete"] and report["aggregate"]["instances"] == 0
    assert report["attempts"][0]["result"]["solved"]
    assert report["attempts"][0]["requested_retries"] == 2
    assert report["invocations"][0]["mode"] == "budget"


def test_legacy_flat_terminal_files_remain_readable_with_explicit_suite(tmp_path, suite):
    path, cases = suite
    for case in cases:
        attempt(tmp_path / "runs", case, manifest=False, embedded=False)
    report = module.collect_results(path, tmp_path / "runs")
    assert report["complete"] and report["aggregate"]["instances"] == 2
    assert all(a["scenario_source"] == "explicit_legacy_suite" for a in report["attempts"])
    assert report["invocations"][0]["status"] == "legacy_unknown"
    assert report["invocations"][0]["validation"]["valid_for_model_comparison"] is None


def test_capped_legacy_fallback_uses_the_explicit_effective_budget(tmp_path, suite):
    path, cases = suite
    attempt(tmp_path / "runs", cases[0], manifest=False, embedded=False)
    report = module.collect_results(path, tmp_path / "runs", maxn=1, budget_cap=3)
    assert report["complete"]
    assert report["attempts"][0]["result"]["budget_jumps"] == 3
    assert report["attempts"][0]["legacy_budget_cap"] == 3


def test_lone_legacy_retry_file_retained_but_excluded_without_retry_manifest(tmp_path, suite):
    path, cases = suite
    attempt(tmp_path / "runs", cases[0], filename="one.a0.jsonl", manifest=False, embedded=False)
    report = module.collect_results(path, tmp_path / "runs", maxn=1)
    assert not report["complete"] and report["aggregate"]["instances"] == 0
    assert len(report["attempts"]) == 1 and report["attempts"][0]["retry_configured"]


def test_legacy_without_terminal_is_retained_but_not_scored_complete(tmp_path, suite):
    path, cases = suite
    attempt(tmp_path / "runs", cases[0], manifest=False, embedded=False, terminal=False)
    report = module.collect_results(path, tmp_path / "runs", maxn=1)
    assert len(report["attempts"]) == 1 and not report["complete"]
    assert report["aggregate"]["instances"] == 0 and report["issues"]


@pytest.mark.parametrize("status", ["error", "interrupted"])
def test_failed_shard_is_retained_in_denominator_and_exits_nonzero(tmp_path, suite, status):
    path, cases = suite
    attempt(tmp_path / "runs/a", cases[0], status=status)
    attempt(tmp_path / "runs/b", cases[1])
    report = module.collect_results(path, tmp_path / "runs")
    assert not report["complete"] and len(report["failed_attempts"]) == 1
    assert report["aggregate"]["instances"] == 2 and len(report["attempts"]) == 2
    assert report["aggregate"]["failed" if status == "error" else "interrupted"] == 1
    assert module.main([str(path), str(tmp_path / "runs")]) == 1


@pytest.mark.parametrize("layout", ["duplicate_runs", "retry_files"])
def test_multiple_attempts_are_ambiguous_never_best_selected(tmp_path, suite, layout):
    path, cases = suite
    root = tmp_path / "runs"
    attempt(root / "a", cases[0], filename="one.a0.jsonl", status="error")
    attempt(root / ("a" if layout == "retry_files" else "b"), cases[0], filename="one.a1.jsonl")
    report = module.collect_results(path, root, maxn=1)
    assert report["ambiguous_scenarios"] == ["one"] and len(report["attempts"]) == 2
    assert report["aggregate"]["instances"] == 0 and not report["complete"]


@pytest.mark.parametrize("mutation", ["missing", "malformed", "running", "manifest_error", "scenario_changed", "diagnostic"])
def test_missing_and_invalid_evidence_never_reports_complete(tmp_path, suite, mutation):
    path, cases = suite
    root = tmp_path / "runs"
    target = attempt(root / "a", cases[0])
    if mutation == "missing": target.unlink()
    elif mutation == "malformed": target.write_text('{"partial":')
    elif mutation == "scenario_changed":
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        rows[0]["meta"]["scenario"]["goal"][0]["target"] = 99
        target.write_text("\n".join(json.dumps(r) for r in rows))
    else:
        manifest = target.parent / "run.json"
        data = json.loads(manifest.read_text())
        if mutation == "diagnostic": data["valid_for_model_comparison"] = False
        else: data["status"] = "running" if mutation == "running" else "error"
        manifest.write_text(json.dumps(data))
    report = module.collect_results(path, root, maxn=1)
    assert not report["complete"]
    assert report["missing_scenarios"] or report["issues"]


def bash_executable():
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    binary = str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    if binary is None:
        pytest.skip("Bash unavailable; synthetic Python aggregation checks still run")
    return binary


@pytest.mark.parametrize("name", ["run_host.sh", "run_parallel.sh"])
def test_shell_syntax(name):
    result = subprocess.run([bash_executable(), "-n", str(HEADLESS / name)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("arguments,expected", [([], "/workspace/repo/harness/runs/benchmark"),
    (["--out", "custom results"], "/workspace/repo/custom results"),
    (["--out=/other/results"], "/other/results")])
def test_host_harness_and_dashboard_share_output_without_duplicate_option(arguments, expected):
    source = (HEADLESS / "run_host.sh").read_text()
    block = source.split("# One output path", 1)[1].split("PROFILE_DIR=", 1)[0]
    block = block[block.index("HARNESS_ARGS="):]
    script = 'set -eu\nFTLB_DIR=/workspace/repo\nunset FTL_BENCH_OUT\n' + block + '\nprintf "__RESULT__\\n"\nprintf "%s\\0" "$OUT_DIR" "${HARNESS_ARGS[@]}"\n'
    result = subprocess.run([bash_executable(), "-s", "--", *arguments], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    values = result.stdout.split("__RESULT__\n")[1].rstrip("\0").split("\0")
    assert values[0] == expected
    assert sum(arg == "--out" or arg.startswith("--out=") for arg in values[1:]) == 1


def test_parallel_fresh_directory_and_explicit_output_override_are_forwarded():
    source = (HEADLESS / "run_parallel.sh").read_text()
    block = source.split("# A user --out", 1)[1].split('echo "== building image once =="', 1)[0]
    block = block[block.index("OUT_PARENT="):]
    script = ('set -eu\nFTLB_DIR=/workspace/repo\nunset FTL_BENCH_OUT\n'
              'HARNESS_ARGS=(--agent scripted --out "/chosen/results")\n'
              'mkdir(){ :; }; date(){ printf "date"; }; mktemp(){ printf "%s" "${2/XXXXXX/unique}"; }\n')
    # Only the configuration block runs. All filesystem-producing commands above
    # are stubs; the game/container launcher is outside this extracted block.
    script += block + '\nprintf "__RESULT__\\n"\nprintf "%s\\0" "$RUNS" "${HARNESS_ARGS[@]}"\n'
    result = subprocess.run([bash_executable(), "-s"], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    values = result.stdout.split("__RESULT__\n")[1].rstrip("\0").split("\0")
    assert values[0] == "/chosen/results/parallel-date-unique"
    assert values[1:] == ["--agent", "scripted", "--out", values[0]]
    assert 'rm -f "$RUNS"/*.jsonl' not in source


@pytest.mark.parametrize("option", ['--budget-cap 3', '--budget-cap=3'])
def test_parallel_passes_effective_cap_to_aggregate(option):
    source = (HEADLESS / "run_parallel.sh").read_text()
    block = source.split("# A user --out", 1)[1].split('echo "== building image once =="', 1)[0]
    block = block[block.index("OUT_PARENT="):]
    script = ('set -eu\nFTLB_DIR=/workspace/repo\nunset FTL_BENCH_OUT\n'
              f'HARNESS_ARGS=({option})\n'
              'mkdir(){ :; }; date(){ printf "date"; }; mktemp(){ printf "fresh"; }\n')
    script += block + '\nprintf "__RESULT__\\n"\nprintf "%s\\0" "${AGGREGATE_ARGS[@]}"\n'
    result = subprocess.run([bash_executable(), "-s"], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split("__RESULT__\n")[1].rstrip("\0").split("\0") == ["--budget-cap", "3"]
