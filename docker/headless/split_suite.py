#!/usr/bin/env python3
"""Split a scenario suite into one single-scenario suite file per instance.

run_benchmark has no per-scenario selector, so to run instances in PARALLEL (one FTL container
each, which sidesteps the broken between-instance reset) we give every shard its own suite of
exactly one scenario. Filters by tier/type and caps the count, mirroring run_benchmark's flags.

    split_suite.py <suite.json> <out_dir> [tier] [type] [max]
Prints one output suite path per line (for the parallel runner to consume).
"""
import json
import os
import sys


def main() -> int:
    suite_path, out_dir = sys.argv[1], sys.argv[2]
    tier = sys.argv[3] if len(sys.argv) > 3 else ""
    typ = sys.argv[4] if len(sys.argv) > 4 else ""
    maxn = sys.argv[5] if len(sys.argv) > 5 else ""

    with open(suite_path, encoding="utf-8") as f:
        data = json.load(f)
    scenarios = data["scenarios"] if isinstance(data, dict) else data
    top = {k: v for k, v in data.items() if k != "scenarios"} if isinstance(data, dict) else {}

    sel = [s for s in scenarios
           if (not tier or s.get("tier") == tier) and (not typ or s.get("type") == typ)]
    if maxn:
        sel = sel[:int(maxn)]

    os.makedirs(out_dir, exist_ok=True)
    for s in sel:
        path = os.path.join(out_dir, f"{s['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**top, "scenarios": [s]}, f)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
