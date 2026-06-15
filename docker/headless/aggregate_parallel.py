#!/usr/bin/env python3
"""Aggregate the per-shard trajectories from a parallel run into one headline result.

Each parallel shard runs ONE scenario and records its trajectory to the shared runs dir as
`<scenario_id>.jsonl`. This re-scores each with the harness scorer and rolls them up exactly like
run_benchmark would, so a sharded run yields the same headline (mean FTL score + solve rate).

    aggregate_parallel.py <suite.json> <runs_dir> [tier] [type] [max]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "harness", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "adapter"))

from ftl_bench import load_suite, load_trajectory, score_instance  # noqa: E402
from ftl_bench.aggregate import aggregate  # noqa: E402


def main() -> int:
    suite_path, runs_dir = sys.argv[1], sys.argv[2]
    tier = sys.argv[3] if len(sys.argv) > 3 else ""
    typ = sys.argv[4] if len(sys.argv) > 4 else ""
    maxn = sys.argv[5] if len(sys.argv) > 5 else ""

    scenarios = load_suite(suite_path)
    scenarios = [s for s in scenarios
                 if (not tier or s.tier == tier) and (not typ or s.type == typ)]
    if maxn:
        scenarios = scenarios[:int(maxn)]

    results, missing = [], []
    for sc in scenarios:
        traj_path = os.path.join(runs_dir, f"{sc.id}.jsonl")
        if os.path.exists(traj_path):
            results.append(score_instance(load_trajectory(traj_path), sc))
        else:
            missing.append(sc.id)

    agg = aggregate(results, scenarios)
    print("\n== PARALLEL AGGREGATE ==")
    print(f"  {agg.get('headline')}")
    print(f"  ftl_score_median: {agg.get('ftl_score_median')}  solve_pct: {agg.get('solve_pct')}")
    print(f"  median_jumps_per_instance: {agg.get('median_jumps_per_instance')}")
    print(f"  by_type: {json.dumps(agg.get('by_type'))}")
    print(f"  by_tier: {json.dumps(agg.get('by_tier'))}")
    if missing:
        print(f"  MISSING (shard produced no trajectory): {', '.join(missing)}")
    print("  per-instance:")
    for r in results:
        print(f"    {r['scenario']:<22} ftl_score={r['ftl_score']:<5} solved={r['solved']} "
              f"jumps={r['achieved'].get('jumps')} breakdown={r['breakdown']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
