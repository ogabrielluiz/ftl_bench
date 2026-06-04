"""ftl_bench eval harness — run N seeded episodes of an agent and aggregate scores.

Uses reset_episode() to start each fresh seeded run from the previous one (no FTL
restart). Records a trajectory per episode and aggregates score_trajectory across them.

Run:  cd harness && uv run python ../adapter/eval.py --seeds 1,2,3 --jumps 6
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # baseline_agent

from ftl_bench import (  # noqa: E402
    AgentSession,
    TrajectoryRecorder,
    load_trajectory,
    score_trajectory,
)
from baseline_agent import play  # noqa: E402


def run_episode(sess: AgentSession, seed: int, jumps: int, path: Path) -> dict:
    sess.recorder = TrajectoryRecorder(path, meta={"seed": seed, "jumps": jumps})
    sess.reset_episode(seed=seed)          # fresh seeded run (from in-game or menu)
    play(sess, jumps, log=lambda *_: None)  # silent baseline policy
    sess.recorder = None
    return score_trajectory(load_trajectory(path))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3", help="comma-separated run seeds")
    ap.add_argument("--jumps", type=int, default=6)
    ap.add_argument("--out", default="runs/eval")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    sess = AgentSession()
    rows = []
    for seed in seeds:
        score = run_episode(sess, seed, args.jumps, out / f"ep_{seed}.jsonl")
        rows.append({"seed": seed, **score})
        print(f"seed {seed:>4}: {score}", flush=True)

    def mean(key):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        return round(statistics.mean(vals), 2) if vals else None

    survived = sum(1 for r in rows if r.get("alive"))
    summary = {
        "episodes": len(rows),
        "survival_rate": f"{survived}/{len(rows)}",
        "mean_kills": mean("kills"),
        "mean_jumps": mean("jumps"),
        "mean_events": mean("events"),
        "mean_final_hull": mean("final_hull"),
        "mean_final_scrap": mean("final_scrap"),
        "rows": rows,
    }
    print("\n== aggregate ==")
    for k, v in summary.items():
        if k != "rows":
            print(f"  {k}: {v}")
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nsummary -> {out / 'summary.json'}")


if __name__ == "__main__":
    main()
