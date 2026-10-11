#!/usr/bin/env python3
"""Inspect nested parallel shard attempts and legacy flat trajectories.

Only one finalized, unambiguous attempt per selected scenario enters the suite
aggregate. Retries and duplicate invocations remain visible; no best is selected.
Missing, invalid, interrupted and failed shards produce a nonzero exit status.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness/src"))

from ftl_bench import Scenario, load_suite, load_trajectory  # noqa: E402
from ftl_bench.aggregate import aggregate  # noqa: E402
from ftl_bench.reporting import load_run_report  # noqa: E402
from ftl_bench.scoring import score_instance  # noqa: E402


def collect_results(suite_path, runs_dir, tier="", typ="", maxn="", *, budget_cap=None):
    scenarios = [s for s in load_suite(suite_path) if (not tier or s.tier == tier) and (not typ or s.type == typ)]
    if budget_cap is not None:
        if type(budget_cap) is not int or budget_cap <= 0:
            raise ValueError("budget cap must be a positive integer")
        scenarios = [replace(s, budget_jumps=min(s.budget_jumps, budget_cap)) for s in scenarios]
    if maxn:
        scenarios = scenarios[:int(maxn)]
    selected = {s.id: s for s in scenarios}
    root = Path(runs_dir).resolve()
    issues, attempts, invocations = [], [], []
    directories = {p.parent for pattern in ("*.jsonl", "run.json") for p in root.rglob(pattern)}
    for directory in sorted(directories):
        if (not directory.resolve().is_relative_to(root)
                or any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                       for p in (directory, *directory.parents) if p != root.parent)):
            issues.append(f"Linked invocation refused: {directory}")
            continue
        try:
            if any(p.is_symlink() for p in directory.glob("*")):
                raise ValueError("linked invocation artifacts")
            report = load_run_report(directory, legacy_suite=suite_path)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            issues.append(f"{directory}: {error}")
            continue
        run = report["run"]
        relevant = [a for a in report["attempts"] if a["scenario"] in selected]
        declared = run.get("scenario_ids")
        planned = set(x for x in declared if isinstance(x, str)) & selected.keys() if isinstance(declared, list) else set()
        if not relevant and not planned:
            if report["errors"]:
                issues.extend(f"{directory}: {error}" for error in report["errors"])
            continue
        invocations.append({"directory": str(directory), "run_id": run.get("run_id"),
                            "status": run.get("status", "legacy_unknown"), "warnings": report["warnings"],
                            "requested_retries": run.get("retries", 0), "mode": run.get("mode"),
                            "validation": report["validation"]})
        issues.extend(f"{directory}: {error}" for error in report["errors"])
        if run and run.get("status") not in ("completed", "error", "interrupted"):
            issues.append(f"{directory}: invocation has not finalized")
        elif run.get("status") in ("error", "interrupted"):
            issues.append(f"{directory}: invocation ended with {run['status']}")
        retry_configured = (type(run.get("retries", 0)) is not int or run.get("retries", 0) != 0
                            or any(re.search(r"\.a\d+\.jsonl$", a["file"]) for a in relevant))
        if retry_configured:
            issues.append(f"{directory}: retry-configured invocation retained but excluded from single-attempt aggregate")
        for attempt in relevant:
            row = {**attempt, "directory": str(directory), "path": str(directory / attempt["file"]),
                   "run_id": run.get("run_id"), "comparison_eligible": report["validation"]["comparison_eligible"],
                   "validation": report["validation"], "requested_retries": run.get("retries", 0),
                   "mode": run.get("mode"), "retry_configured": retry_configured}
            try:
                records = load_trajectory(row["path"])
                metadata = records[0].get("meta") or {}
                if "scenario" in metadata and Scenario.from_dict(metadata["scenario"]).to_dict() != selected[row["scenario"]].to_dict():
                    row["errors"] = [*row["errors"], "recorded scenario differs from the selected suite"]
                elif row["scenario_source"] == "explicit_legacy_suite" and budget_cap is not None and row["result"] is not None:
                    # The cap is part of the caller's explicit legacy definition;
                    # never report an uncapped score for a capped fallback suite.
                    row["result"] = score_instance(records, selected[row["scenario"]])
                    row["result"]["trajectory"] = row["path"]
                    row["legacy_budget_cap"] = budget_cap
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                row["errors"] = [*row["errors"], str(error)]
            attempts.append(row)
    results, missing, ambiguous = [], [], []
    for scenario in scenarios:
        found = [a for a in attempts if a["scenario"] == scenario.id]
        if not found:
            missing.append(scenario.id)
        elif len(found) != 1:
            ambiguous.append(scenario.id)
        else:
            attempt = found[0]
            if attempt["errors"] or not attempt["finalized"] or attempt["result"] is None:
                issues.append(f"{attempt['path']}: incomplete or invalid attempt")
            elif not attempt["comparison_eligible"]:
                issues.append(f"{attempt['path']}: diagnostic attempt excluded from comparison")
            elif attempt["retry_configured"]:
                pass
            else:
                results.append(attempt["result"])
    failed = [a["path"] for a in attempts if a["status"] in ("error", "failed", "interrupted")]
    return {"schema": "headless-parallel-report-v2", "runs_directory": str(root),
            "planned_scenarios": list(selected), "invocations": invocations, "attempts": attempts,
            "missing_scenarios": missing, "ambiguous_scenarios": ambiguous, "failed_attempts": failed,
            "issues": issues, "aggregate": aggregate(results, scenarios),
            "complete": bool(scenarios) and not (missing or ambiguous or issues or failed),
            "scope": "File-derived finalized unambiguous attempts only; invocation issues remain explicit. All attempts retained; retry conditions excluded, no best-of selection. Legacy flat files use the explicit suite. This does not certify native runtime acceptance or model comparability."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite")
    parser.add_argument("runs")
    for name in ("tier", "typ", "maxn"):
        parser.add_argument(name, nargs="?", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--budget-cap", type=int)
    args = parser.parse_args(argv)
    if args.budget_cap is not None and args.budget_cap <= 0:
        parser.error("--budget-cap must be positive")
    report = collect_results(args.suite, args.runs, args.tier, args.typ, args.maxn, budget_cap=args.budget_cap)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n== PARALLEL AGGREGATE ==\n  " + report["aggregate"]["headline"])
        print("  " + report["scope"])
        print(f"  Finalized-attempt coverage: {report['aggregate']['instances']}/{len(report['planned_scenarios'])} selected scenarios")
        for label in ("missing_scenarios", "ambiguous_scenarios", "failed_attempts", "issues"):
            for value in report[label]:
                print(f"  {label.upper()}: {value}")
        for attempt in report["attempts"]:
            result = attempt["result"] or {}
            print(f"  {attempt['path']}: {attempt['status']} / {attempt['reason']}; "
                  f"FTL={result.get('ftl_score')} solved={result.get('solved')}")
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
