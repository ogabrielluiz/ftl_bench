"""ftl_bench scenario runner — the benchmark entry point.

Runs an AGENT against the scenario suite and reports the headline metrics
(GCS@1 + Solve Rate + per-type/tier breakdown). Each instance:
  reset to the scenario's seed -> agent plays within the jump budget -> record the
  trajectory (with a reproducibility manifest) -> score_instance (goal-conditioned).

The agent only ever decides through the standard observe/act interface; the runner
scores goal achievement only. Freeze-resilient: a stuck reset force-restarts FTL.

  cd harness && uv run python ../adapter/run_benchmark.py --agent scripted
  cd harness && uv run python ../adapter/run_benchmark.py --agent random --tier public
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "harness" / "src"))
sys.path.insert(0, str(REPO / "adapter"))

from ftl_bench import (  # noqa: E402
    AgentSession,
    TrajectoryRecorder,
    load_suite,
    load_trajectory,
    score_instance,
    set_system_power,
)
from ftl_bench.aggregate import aggregate  # noqa: E402
from baseline_agent import play as scripted_play  # noqa: E402

RUNNER_VERSION = "v1"
RESTART_SH = REPO / "scripts" / "restart_ftl.sh"


def restart_ftl() -> None:
    """Force a clean FTL relaunch (recovers from a frozen/crashed game)."""
    try:
        subprocess.run(["bash", str(RESTART_SH), "new"], timeout=200,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass


# --- agents -------------------------------------------------------------------------

def random_play(sess: AgentSession, scenario, log) -> None:
    """Random-LEGAL baseline (the trivial floor): from the same interface, pick a random
    legal action each turn. Resolves events randomly, fires randomly, jumps randomly."""
    rng = random.Random(scenario.seed)
    jumps = 0
    for _ in range(scenario.budget_jumps * 8):
        if jumps >= scenario.budget_jumps:
            break
        try:
            o = sess.observe()
        except Exception:  # noqa: BLE001
            time.sleep(0.2); continue
        if (o.player_ship or {}).get("hull", {}).get("current", 0) <= 0:
            break
        try:
            if o.choice_box_open and (o.event or {}).get("choices"):
                n = len(o.event["choices"])
                sess.choose_event(rng.randrange(n), advance_frames=90)
            elif o.enemy_ship:
                rooms = (o.enemy_ship or {}).get("rooms", [])
                weps = [w for w in (o.player_ship or {}).get("weapons", []) if w.get("powered")]
                if weps and rooms:
                    sess.fire_weapon(rng.choice(weps)["slot"], rng.choice(rooms)["room_id"], advance_frames=120)
                else:
                    sess.step([], advance_frames=120)
            else:
                beac = (o.map or {}).get("connected_beacons", [])
                if (o.map or {}).get("at_exit"):
                    sess.leave_sector(); jumps += 1
                elif beac:
                    sess.jump(rng.choice(beac)["index"], advance_frames=260); jumps += 1
                else:
                    break
        except TimeoutError:
            break


def scripted(sess: AgentSession, scenario, log) -> None:
    scripted_play(sess, scenario.budget_jumps, log)


AGENTS = {"scripted": scripted, "random": random_play}


# --- runner -------------------------------------------------------------------------

def manifest(scenario, agent: str) -> dict:
    """Reproducibility manifest: pins what's needed to compare numbers across runs."""
    return {
        "scenario_id": scenario.id, "type": scenario.type, "seed": scenario.seed,
        "ship": scenario.ship, "difficulty": scenario.difficulty, "tier": scenario.tier,
        "agent": agent, "runner_version": RUNNER_VERSION, "ruleset": "v1",
        "schema_version": 3,
    }


def run_instance(sess: AgentSession, scenario, agent_fn, agent_name, out_dir, log) -> dict:
    path = out_dir / f"{scenario.id}.jsonl"
    sess.recorder = TrajectoryRecorder(path, meta=manifest(scenario, agent_name))
    started = False
    for attempt in range(3):
        try:
            sess.reset_episode(seed=scenario.seed)
            started = True
            break
        except TimeoutError:
            log(f"  [{scenario.id}] reset timed out (attempt {attempt + 1}) — restarting FTL")
            restart_ftl()
            sess._sync_seq()
            time.sleep(1)
    if started:
        try:
            agent_fn(sess, scenario, log)
        except TimeoutError:
            log(f"  [{scenario.id}] run wedged — restarting FTL for the next instance")
            restart_ftl()
        except Exception as e:  # noqa: BLE001
            log(f"  [{scenario.id}] agent error: {e}")
    sess.recorder = None
    result = score_instance(load_trajectory(path), scenario)
    log(f"  [{scenario.id}] score={result['score']} solved={result['solved']} "
        f"breakdown={result['breakdown']}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=list(AGENTS), default="scripted")
    ap.add_argument("--suite", default=str(REPO / "scenarios" / "suite_v1.json"))
    ap.add_argument("--tier", default=None, help="filter: public | semi_private | ...")
    ap.add_argument("--type", default=None, help="filter by scenario type")
    ap.add_argument("--out", default="runs/benchmark")
    args = ap.parse_args()

    scenarios = load_suite(args.suite)
    if args.tier:
        scenarios = [s for s in scenarios if s.tier == args.tier]
    if args.type:
        scenarios = [s for s in scenarios if s.type == args.type]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = AgentSession()
    agent_fn = AGENTS[args.agent]

    def log(m):
        print(m, flush=True)

    log(f"== ftl_bench: agent={args.agent}  instances={len(scenarios)} ==")
    results = []
    for sc in scenarios:
        log(f"-- {sc.id} ({sc.type}, seed {sc.seed}, budget {sc.budget_jumps}) --")
        results.append(run_instance(sess, sc, agent_fn, args.agent, out_dir, log))

    agg = aggregate(results, scenarios)
    agg["agent"] = args.agent
    log("\n== RESULTS ==")
    log(f"  {agg['headline']}")
    for k in ("solve_pct", "median_jumps_per_instance"):
        log(f"  {k}: {agg[k]}")
    log(f"  by_type: {json.dumps(agg['by_type'])}")
    log(f"  by_tier: {json.dumps(agg['by_tier'])}")
    (out_dir / f"summary_{args.agent}.json").write_text(
        json.dumps({"aggregate": agg, "instances": results}, indent=2))
    log(f"\nsummary -> {out_dir / f'summary_{args.agent}.json'}")


if __name__ == "__main__":
    main()
