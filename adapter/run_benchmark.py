"""ftl_bench scenario runner — the benchmark entry point.

Runs an AGENT against the scenario suite and reports the headline metrics
(mean FTL score + Solve Rate + per-type/tier breakdown). Each instance:
  reset to the scenario's seed -> agent plays within the jump budget -> record the
  trajectory (with a reproducibility manifest) -> score_instance (goal-conditioned).

The agent only ever decides through the standard observe/act interface; the runner
scores goal achievement only. Freeze-resilient: a stuck reset force-restarts FTL.

  cd harness && uv run python ../adapter/run_benchmark.py --agent scripted
  cd harness && uv run python ../adapter/run_benchmark.py --agent random --tier public
"""
from __future__ import annotations

import argparse
import inspect
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
    Attempt,
    TrajectoryRecorder,
    load_suite,
    load_trajectory,
    score_instance,
    set_system_power,
    summarize_attempt,
)
from ftl_bench.aggregate import aggregate  # noqa: E402
from ftl_bench.session import ftl_user_folder  # noqa: E402
from baseline_agent import play as scripted_play  # noqa: E402
from llm_agent import make_llm_agent  # noqa: E402

RUNNER_VERSION = "v1"
RESTART_SH = REPO / "scripts" / "restart_ftl.sh"


FTL_PROC = "FTL Faster Than Light/FTL.app/Contents/MacOS/FTL"

# The FTL game runs as a native Windows process (FTLGame.exe) in two setups: native
# Windows Python (os.name == 'nt'), or WSL Python pointing at a /mnt drive. In BOTH it
# MUST be launched via Steam — only the Steam launch loads the local xinput proxy that
# injects Hyperspace; a direct exe launch (cmd/Start-Process) loads the system xinput and
# HS never injects. The only difference is how we reach the Windows tools: native names on
# PATH and a direct steam.exe launch vs. /mnt/c absolute paths + a powershell shim in WSL.
_NATIVE_WIN = os.name == "nt"
_WSL_WIN = os.environ.get("FTL_SAVE_DIR", "").startswith("/mnt/")
_WINDOWS = _NATIVE_WIN or _WSL_WIN
_STEAM_WIN = os.environ.get("FTL_STEAM_EXE", r"C:\Program Files (x86)\Steam\steam.exe")
_FTL_APPID = "212680"
if _NATIVE_WIN:
    _TASKLIST, _TASKKILL = "tasklist", "taskkill"
else:  # WSL reaches the Windows tools by absolute /mnt/c path
    _TASKLIST = "/mnt/c/Windows/System32/tasklist.exe"
    _TASKKILL = "/mnt/c/Windows/System32/taskkill.exe"
    _PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


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
        save = ftl_user_folder()
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
        # A process restart resets Lua _G, and the in-.dat bootstrap only (re)loads the external
        # dev script when the reload marker is present (a prior launch consumed it). Re-deploy the
        # dev script + touch the marker so the fresh bootstrap loads it and starts writing obs.
        dev_src = REPO / "mod" / "ftl_bench_bridge" / "dev" / "ftl_bench_dev.lua"
        try:
            (save / "ftl_bench_dev.lua").write_bytes(dev_src.read_bytes())
        except OSError:
            pass
        (save / "ftl_bench_reload").write_text("")  # touch: bootstrap consumes it within ~15 ticks
        if _NATIVE_WIN:
            subprocess.run([_STEAM_WIN, "-applaunch", _FTL_APPID],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:  # WSL: shell out through powershell to start the Windows Steam client
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


def _agent_takes_attempts(fn) -> bool:
    """Does this agent_fn accept the retry `attempts` context? Old 3-arg agents don't, so they
    are called the old way — opting into retries is just accepting the parameter."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return True
    return "attempts" in params or any(p.kind == p.VAR_KEYWORD for p in params.values())


def _reset_to_seed(sess: AgentSession, scenario, log) -> bool:
    """Reset the game to the scenario's seed, with fast freeze-recovery. True if started."""
    for attempt in range(3):
        # FAST freeze recovery: if a prior run froze, the watchdog already SIGKILLed FTL —
        # relaunch NOW instead of eating a 35s reset timeout to discover it.
        if not game_alive():
            log(f"  [{scenario.id}] FTL not running (prior freeze?) — relaunching")
            restart_ftl()
            sess._sync_seq()
        try:
            sess.reset_episode(seed=scenario.seed, timeout=35.0)
            return True
        except (TimeoutError, FileNotFoundError, OSError) as e:
            log(f"  [{scenario.id}] reset failed ({type(e).__name__}, attempt {attempt + 1}) "
                f"— restarting FTL")
            restart_ftl()
            sess._sync_seq()
            time.sleep(1)
    return False


def _play_once(sess, scenario, agent_fn, agent_name, path, log, extra_manifest, attempts) -> dict:
    """Reset to the seed, play ONE episode (handing the agent the prior `attempts` if it accepts
    them), and score the recorded trajectory."""
    sess.recorder = TrajectoryRecorder(path, meta=manifest(scenario, agent_name, extra_manifest))
    if _reset_to_seed(sess, scenario, log):
        try:
            if _agent_takes_attempts(agent_fn):
                agent_fn(sess, scenario, log, attempts=attempts)
            else:
                agent_fn(sess, scenario, log)
        except TimeoutError:
            log(f"  [{scenario.id}] run wedged — restarting FTL")
            restart_ftl()
        except Exception as e:  # noqa: BLE001
            log(f"  [{scenario.id}] agent error: {e}")
    # If play froze the game, relaunch eagerly so the next try/instance starts clean.
    if not game_alive():
        log(f"  [{scenario.id}] FTL down after play (freeze) — relaunching")
        restart_ftl()
        sess._sync_seq()
    sess.recorder = None
    return score_instance(load_trajectory(path), scenario)


def run_instance(sess: AgentSession, scenario, agent_fn, agent_name, out_dir, log,
                 extra_manifest=None, retries: int = 0) -> dict:
    """Run one instance. With `retries` > 0 the agent gets up to `retries`+1 tries at the SAME
    seed; before each retry it is handed the prior same-seed attempts (see `ftl_bench.retry`) so
    it can learn from its mistakes. Stops early on a solve. The reported result is the BEST
    attempt, annotated with every attempt's score so the learning curve is visible."""
    attempts: list[Attempt] = []
    results: list[dict] = []
    for i in range(retries + 1):
        path = out_dir / (f"{scenario.id}.jsonl" if retries == 0 else f"{scenario.id}.a{i}.jsonl")
        result = _play_once(sess, scenario, agent_fn, agent_name, path, log, extra_manifest,
                            tuple(attempts))
        results.append(result)
        tag = "" if retries == 0 else f" [try {i + 1}/{retries + 1}]"
        log(f"  [{scenario.id}]{tag} ftl_score={result.get('ftl_score', 0)} "
            f"solved={result['solved']} breakdown={result['breakdown']}")
        if result["solved"]:
            break
        if i < retries:   # build the attempt record handed to the next try
            attempts.append(summarize_attempt(load_trajectory(path), result, i))
    # Best = solved first, then highest FTL score.
    best = dict(max(results, key=lambda r: (r["solved"], r.get("ftl_score", 0))))
    if retries:
        best["attempts_used"] = len(results)
        best["attempt_ftl_scores"] = [r.get("ftl_score", 0) for r in results]
        best["attempt_solved"] = [r["solved"] for r in results]
        log(f"  [{scenario.id}] BEST of {len(results)}: ftl_score={best.get('ftl_score', 0)} "
            f"solved={best['solved']}  per-try={best['attempt_ftl_scores']}")
    return best


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
    ap.add_argument("--prompt-version", default="v3",
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
    ap.add_argument("--retries", type=int, default=0,
                    help="give the agent up to N extra tries per instance on the SAME seed, "
                         "handing it the prior attempts each time so it can learn from its "
                         "mistakes (Reflexion-style). The best attempt is scored.")
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
    # Retries are a distinct, labeled evaluation mode — never silently fold into the pass@1 number.
    if args.retries:
        agent_label += f"-retries{args.retries}"
    extra_manifest = {**(extra_manifest or {}), "retries": args.retries}

    def log(m):
        print(m, flush=True)

    log(f"== ftl_bench: agent={agent_label}  instances={len(scenarios)} ==")
    results = []
    for sc in scenarios:
        log(f"-- {sc.id} ({sc.type}, seed {sc.seed}, budget {sc.budget_jumps}) --")
        results.append(run_instance(sess, sc, agent_fn, agent_label, out_dir, log,
                                    extra_manifest, retries=args.retries))

    agg = aggregate(results, scenarios)
    agg["agent"] = agent_label
    log("\n== RESULTS ==")
    log(f"  {agg['headline']}")
    for k in ("ftl_score_median", "solve_pct", "median_jumps_per_instance"):
        log(f"  {k}: {agg[k]}")
    if agg.get("retries"):
        log("  retry learning curve (best of k tries):")
        for c in agg["retry_curve"]:
            log(f"    @{c['k']}: FTL mean {c['ftl_score_mean']} median {c['ftl_score_median']}  |  "
                f"solve {c['solved']}/{agg['instances']} ({c['solve_pct']}%)")
    log(f"  by_type: {json.dumps(agg['by_type'])}")
    log(f"  by_tier: {json.dumps(agg['by_tier'])}")
    safe = agent_label.replace("/", "-").replace(":", "-")
    (out_dir / f"summary_{safe}.json").write_text(
        json.dumps({"aggregate": agg, "instances": results}, indent=2))
    log(f"\nsummary -> {out_dir / f'summary_{safe}.json'}")


if __name__ == "__main__":
    main()
