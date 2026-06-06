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
import os
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
from llm_agent import make_llm_agent  # noqa: E402

RUNNER_VERSION = "v1"
RESTART_SH = REPO / "scripts" / "restart_ftl.sh"


FTL_PROC = "FTL Faster Than Light/FTL.app/Contents/MacOS/FTL"

# Windows-via-WSL when FTL_SAVE_DIR points at a /mnt drive: the game runs as a
# native Windows process (FTLGame.exe) and MUST be launched via Steam — only the
# Steam launch loads the local xinput proxy that injects Hyperspace; a direct exe
# launch (cmd/Start-Process) loads the system xinput and HS never injects.
_WINDOWS = os.environ.get("FTL_SAVE_DIR", "").startswith("/mnt/")
_PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
_TASKLIST = "/mnt/c/Windows/System32/tasklist.exe"
_TASKKILL = "/mnt/c/Windows/System32/taskkill.exe"
_STEAM_WIN = r"C:\Program Files (x86)\Steam\steam.exe"
_FTL_APPID = "212680"


def game_alive() -> bool:
    """Is the FTL game process running? (The freeze watchdog SIGKILLs a spinning game,
    so 'process gone' is our fast, reliable signal that an episode froze and died.)"""
    if _WINDOWS:
        r = subprocess.run([_TASKLIST, "/fi", "imagename eq FTLGame.exe"],
                           capture_output=True, text=True)
        return "FTLGame.exe" in r.stdout
    r = subprocess.run(["pgrep", "-f", FTL_PROC], capture_output=True, text=True)
    return bool(r.stdout.strip())


def restart_ftl() -> None:
    """Relaunch FTL to the MENU (recovers from a frozen/crashed/killed game)."""
    if _WINDOWS:
        save = Path(os.environ["FTL_SAVE_DIR"]).expanduser()
        obs = save / "ftl_agent_observation.json"
        subprocess.run([_TASKKILL, "/F", "/IM", "FTLGame.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        # taskkill /F is not a clean exit, so Hyperspace's hs_crash.flag survives; the next
        # launch would see it, pop the "CRASH DETECTED" recovery (which blocks New Game) and
        # spew a bug-report zip. Delete it (+ the stale obs) so the relaunch boots clean.
        for stale in ("ftl_agent_observation.json", "hs_crash.flag"):
            try:
                (save / stale).unlink()
            except FileNotFoundError:
                pass
        subprocess.run([_PS, "-NoProfile", "-Command",
                        f"Start-Process '{_STEAM_WIN}' -ArgumentList '-applaunch','{_FTL_APPID}'"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # wait for the bridge to write its first observation (HS injected, at menu)
        for _ in range(90):
            if obs.exists():
                time.sleep(2)  # let the menu settle
                return
            time.sleep(2)
        return
    # macOS: relaunch to menu via the launcher script ('none' = leave at menu so
    # reset_episode does a single seeded start_game).
    try:
        subprocess.run(["bash", str(RESTART_SH), "none"], timeout=200,
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

def manifest(scenario, agent: str, extra: dict | None = None) -> dict:
    """Reproducibility manifest: pins what's needed to compare numbers across runs."""
    m = {
        "scenario_id": scenario.id, "type": scenario.type, "seed": scenario.seed,
        "ship": scenario.ship, "difficulty": scenario.difficulty, "tier": scenario.tier,
        "agent": agent, "runner_version": RUNNER_VERSION, "ruleset": "v1",
        "schema_version": 3,
    }
    if extra:
        m.update(extra)  # e.g. the LLM track records {model, backend}
    return m


def run_instance(sess: AgentSession, scenario, agent_fn, agent_name, out_dir, log,
                 extra_manifest=None) -> dict:
    path = out_dir / f"{scenario.id}.jsonl"
    sess.recorder = TrajectoryRecorder(path, meta=manifest(scenario, agent_name, extra_manifest))
    started = False
    for attempt in range(3):
        # FAST freeze recovery: if a prior instance froze, the watchdog already SIGKILLed
        # FTL — relaunch NOW instead of eating a 60s reset_episode timeout to discover it.
        if not game_alive():
            log(f"  [{scenario.id}] FTL not running (prior freeze?) — relaunching")
            restart_ftl()
            sess._sync_seq()
        try:
            # Short timeout: a live game resets in well under 35s; a longer wait just means
            # the game is freezing — fail fast, relaunch, retry rather than hang.
            sess.reset_episode(seed=scenario.seed, timeout=35.0)
            started = True
            break
        except (TimeoutError, FileNotFoundError, OSError) as e:
            log(f"  [{scenario.id}] reset failed ({type(e).__name__}, attempt {attempt + 1}) "
                f"— restarting FTL")
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
    # If the episode froze the game (watchdog killed it during play), relaunch eagerly so
    # the NEXT instance starts clean immediately rather than rediscovering death slowly.
    if not game_alive():
        log(f"  [{scenario.id}] FTL down after play (freeze) — relaunching for next instance")
        restart_ftl()
        sess._sync_seq()
    sess.recorder = None
    result = score_instance(load_trajectory(path), scenario)
    log(f"  [{scenario.id}] score={result['score']} solved={result['solved']} "
        f"breakdown={result['breakdown']}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=list(AGENTS) + ["llm"], default="scripted",
                    help="scripted | random | llm (a real frontier model)")
    ap.add_argument("--model", default=None,
                    help="llm track: model id (default claude-sonnet-4-6 for anthropic)")
    ap.add_argument("--backend", choices=["anthropic", "claude-cli"], default="anthropic",
                    help="llm track: anthropic API (needs ANTHROPIC_API_KEY) | local claude -p")
    ap.add_argument("--step-mult", type=int, default=8,
                    help="llm track: max actions per instance = budget_jumps * this")
    ap.add_argument("--prompt-version", default="v1",
                    help="llm track: which prompts/ftl_agent_<v>.md manual to use (versioned)")
    ap.add_argument("--play-to-gameover", action="store_true",
                    help="llm track: ignore the jump budget; play until the game ends (win/death) "
                         "or the agent stalls (see --stall-limit)")
    ap.add_argument("--stall-limit", type=int, default=10,
                    help="play-to-gameover: end the run as a LOSS after this many consecutive "
                         "turns with no progress (the game state unchanged)")
    ap.add_argument("--suite", default=str(REPO / "scenarios" / "suite_v1.json"))
    ap.add_argument("--tier", default=None, help="filter: public | semi_private | ...")
    ap.add_argument("--type", default=None, help="filter by scenario type")
    ap.add_argument("--max-instances", type=int, default=None, help="cap # instances")
    ap.add_argument("--budget-cap", type=int, default=None,
                    help="cap each instance's jump budget (faster smoke runs)")
    ap.add_argument("--out", default="runs/benchmark")
    args = ap.parse_args()

    scenarios = load_suite(args.suite)
    if args.tier:
        scenarios = [s for s in scenarios if s.tier == args.tier]
    if args.type:
        scenarios = [s for s in scenarios if s.type == args.type]
    if args.budget_cap:
        from dataclasses import replace
        scenarios = [replace(s, budget_jumps=min(s.budget_jumps, args.budget_cap))
                     for s in scenarios]
    if args.max_instances:
        scenarios = scenarios[: args.max_instances]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = AgentSession()
    # The LLM track is a factory (model/backend); scripted/random are plain functions.
    if args.agent == "llm":
        agent_fn = make_llm_agent(args.model, args.backend, args.step_mult, args.prompt_version,
                                  play_to_gameover=args.play_to_gameover,
                                  stall_limit=args.stall_limit)
        _mode = f"-gameover{args.stall_limit}" if args.play_to_gameover else ""
        agent_label = f"llm-{args.backend}-{args.model or 'default'}-{args.prompt_version}{_mode}"
        extra_manifest = {"model": args.model or "default", "backend": args.backend,
                          "prompt_version": args.prompt_version,
                          "play_to_gameover": args.play_to_gameover,
                          "stall_limit": args.stall_limit}
    else:
        agent_fn = AGENTS[args.agent]
        agent_label = args.agent
        extra_manifest = None

    def log(m):
        print(m, flush=True)

    log(f"== ftl_bench: agent={agent_label}  instances={len(scenarios)} ==")
    results = []
    for sc in scenarios:
        log(f"-- {sc.id} ({sc.type}, seed {sc.seed}, budget {sc.budget_jumps}) --")
        results.append(run_instance(sess, sc, agent_fn, agent_label, out_dir, log,
                                    extra_manifest))

    agg = aggregate(results, scenarios)
    agg["agent"] = agent_label
    log("\n== RESULTS ==")
    log(f"  {agg['headline']}")
    for k in ("solve_pct", "median_jumps_per_instance"):
        log(f"  {k}: {agg[k]}")
    log(f"  by_type: {json.dumps(agg['by_type'])}")
    log(f"  by_tier: {json.dumps(agg['by_tier'])}")
    safe = agent_label.replace("/", "-").replace(":", "-")
    (out_dir / f"summary_{safe}.json").write_text(
        json.dumps({"aggregate": agg, "instances": results}, indent=2))
    log(f"\nsummary -> {out_dir / f'summary_{safe}.json'}")


if __name__ == "__main__":
    main()
