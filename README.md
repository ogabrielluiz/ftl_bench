# ftl_bench

An agent-evaluation benchmark that lets LLM coding agents **play FTL: Faster Than Light** through a clean, intent-level interface built on the [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) Lua API.

FTL is a real-time-with-pause roguelike: resource management, risk under uncertainty, combat micro, and long-horizon planning across a branching map. That makes it a rich substrate for measuring agent decision-making. `ftl_bench` wraps it into a reproducible, turn-based environment with structured observations, an intent-level action space, seed-pinned runs, and full trajectory logging.

## The benchmark: a scenario suite scored by goal achievement

`ftl_bench` evaluates agents on a suite of reproducible **scenario instances**, not on raw play.

- **Instance** = a fully-specified, seeded scenario `(seed, ship, difficulty, goal)`. The seed pins the map + events; the goal is a set of weighted sub-objectives.
- **The agent decides everything in-game** (fight, flee, target, power, repair, navigate). The harness scores **only goal achievement** — no decision policy is baked into the env or scoring.
- **Goal-conditioned partial credit**: each instance earns `r ∈ [0,1]` = the weighted intersection of achieved vs. requested sub-objectives, × a legitimacy gate that collapses metric-gaming (e.g. jumping in place). `Score = 100·r`.
- **Headline metric: FTL score** = the mean of FTL's own native run score (scrap, kills, sectors, flagship, times difficulty) over the suite (± seed SE), alongside a strict **Solve / Win Rate** and an **efficiency** axis (jumps/turns per instance).
- **Anti-memorization split**: a `public` tier to tune against and a held-out `semi_private` tier that is the leaderboard number.
- **Baseline ladder**: a `random`-legal floor and a `scripted` heuristic floor, so a high agent score is interpretable.

**Scenario types:** `survive_n_jumps` (make N jumps alive), `reach_sector` (advance to sector K), `reach_sector_healthy` (reach K with hull + crew intact — a multi-attribute goal), `full_run` (milestone progress toward beating the flagship — the unsaturated ceiling). Higher-signal micro-encounters (`win_this_combat`, `escape_a_crisis`, `event_risk_choice`) and the flagship/store tiers are next.

**Run it** (the harness runs on native Windows, WSL, or macOS, and drives FTL for you):
```bash
# One-time setup, per platform:
#   Windows: install FTL via Steam + the bench Hyperspace mod (scripts/setup_pc.sh). The runner
#            launches and restarts FTL through Steam itself, so no env vars are needed.
#   macOS:   defaults write com.example.FTL NSAppSleepDisabled -bool YES   # keep it ticking unfocused
#            scripts/restart_ftl.sh none                                    # launch FTL to the menu

cd harness && uv run python ../adapter/run_benchmark.py --agent scripted   # scripted floor
cd harness && uv run python ../adapter/run_benchmark.py --agent random      # random floor
cd harness && uv run python ../adapter/run_benchmark.py --agent scripted --tier semi_private  # held-out leaderboard number
# A real frontier model plays the suite (the LLM track), two backends:
cd harness && uv run python ../adapter/run_benchmark.py --agent llm --backend anthropic --model claude-sonnet-4-6  # needs ANTHROPIC_API_KEY
cd harness && uv run python ../adapter/run_benchmark.py --agent llm --backend claude-cli --model claude-opus-4-8   # no key: local `claude -p`
```
The **LLM track** (`adapter/llm_agent.py`) drives the model over the same intent-level surface the baselines use: each turn it gets the decision-complete observation + the scenario goal + a short action history and replies with one command, dispatched through the shared `apply_command()` in `play_cli.py`. It decides everything — no scripted policy. `--backend anthropic` is the canonical, portable track (Anthropic Messages API); `--backend claude-cli` shells out to a local `claude -p` so you can run it with no API key. The agent's rules/instructions are a **version-controlled operating manual** at `prompts/ftl_agent_<v>.md` (select with `--prompt-version`); the version is recorded in each run's manifest and agent label, so a manual change is a distinct, comparable agent — not a silent drift.
Output: per-instance `ftl_score` + breakdown, then the aggregate `FTL score ± SE | Solve N/M` with per-type/tier breakdown. Each instance's trajectory + a reproducibility manifest (seed, ship, schema, runner/agent version) is saved under `runs/benchmark/`.

**Native baseline (scripted heuristic floor, 12-instance v1 suite, native Windows + Steam, no WSL).** The headline metric is FTL's own native run score (mean over the suite, ± seed SE):

| Agent | FTL score | Solve | survive_n_jumps | reach_sector | reach_sector_healthy | full_run |
|---|---|---|---|---|---|---|
| **scripted** (heuristic floor) | **143.75 ± 13.05** | 3/12 | 133.3 | 124.0 | 195.0 | 157.5 |

Median 11 jumps per instance; public tier 142.9, held-out `semi_private` tier 145.0. The full suite runs end to end on native Windows with no crashes. A native `random` floor and a frontier-LLM row (`--agent llm`, above, scored identically over the same observe/act surface) are the next rows to fill. Earlier macOS/Rosetta numbers used a goal-conditioned 0-100 score (scripted 70.2, random 5.2) and are not comparable to FTL's native score here.

## Why Hyperspace

Hyperspace is an open-source C++ "exe mod" that exposes FTL's engine to **Lua via SWIG bindings**. It already lets scripts *read* full game state (`Hyperspace.ships.player`/`.enemy`, crew, systems, weapons, map) and *drive* much of the simulation (move crew, allocate power, teleport, toggle cloak). It also supports **seeded runs** with the seed readable from Lua, the basis for reproducibility. Where capabilities aren't yet bound — the harness **transport** (the Lua sandbox disables `io`/sockets), JSON serialization, and a few UI-driven actions (weapon room-targeting, event-choice confirm, jump trigger, store) — we extend Hyperspace itself with new SWIG bindings rather than resorting to brittle screen/input automation. The source-grounded map of what's exposed vs. what we build is in [`docs/deepdive/hyperspace-lua-surface.md`](docs/deepdive/hyperspace-lua-surface.md).

## Architecture (four layers)

```
┌─────────────────────────────────────────────────────────────┐
│  Coding agent (LLM)                                          │
│   observes JSON, returns intent-level actions                │
└───────────────▲──────────────────────────┬──────────────────┘
                │ tools (MCP / func-calling)│
┌───────────────┴──────────────────────────▼──────────────────┐
│  adapter/   — exposes env as agent tools                     │
├──────────────────────────────────────────────────────────────┤
│  harness/   — gym-like env server (reset/observe/step),      │
│               episode + seed + scoring + trajectory logging  │
└───────────────▲──────────────────────────┬──────────────────┘
                │ transport (file / socket) │
┌───────────────┴──────────────────────────▼──────────────────┐
│  mod/ftl_bench_bridge  — Hyperspace Lua mod inside FTL:      │
│   • per-frame hook gates the sim (event-driven pause)        │
│   • serializes Observation JSON                              │
│   • applies Action commands via the Lua API                 │
│  (+ extended Hyperspace C++/SWIG bindings for action gaps)  │
└──────────────────────────────────────────────────────────────┘
```

| Dir | Purpose |
|-----|---------|
| `mod/ftl_bench_bridge/` | In-game Hyperspace Lua mod: state serialization, action application, sim gating |
| `harness/` | External environment server (Python): `reset()/observe()/step()`, episodes, seeds, scoring, logging |
| `adapter/` | Exposes the env to a coding agent as MCP / function-calling tools |
| `scenarios/` | Benchmark scenario definitions + pinned seeds (full runs and cheap micro-encounters) |
| `docs/deepdive/` | Source-grounded analysis of the Hyperspace Lua surface |

## Core idea: making a real-time game turn-based

The harness keeps the game **paused by default** and unpauses in controlled increments. The default **event-driven gating** mode runs the sim until the next significant decision point (enemy weapon about to fire, system damaged, projectile incoming, event/store/jump screen) then re-pauses and requests an action — mirroring how a skilled human micro-pauses. A simpler **fixed-tick** mode is available for cheaper runs.

## Platform notes

On **native Windows**, FTL must be launched through Steam (`steam.exe -applaunch 212680`), which the runner does for you; a direct executable launch skips the Hyperspace injection and the bridge never loads. Windows Defender can briefly lock the observation/action files, so the harness retries those file operations. On **macOS**, keep FTL from being App-Napped so it keeps ticking when unfocused: `defaults write com.example.FTL NSAppSleepDisabled -bool YES`.

## Documentation

A documentation site covering the scoring model, the action set and observation schema, the per-platform install guides, and the architecture is in [`site/`](site/) (Astro Starlight). The Hyperspace Lua state/action surface is mapped in [`docs/deepdive/hyperspace-lua-surface.md`](docs/deepdive/hyperspace-lua-surface.md).

## Known gaps

- **Beam weapons** are not yet in the action set; they need two-point, room-to-room targeting.
- The higher-signal micro-encounter scenarios and the flagship tier are planned but not yet in the suite.

## Related

- [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) — the modding API this is built on
- [FTLAV](https://github.com/Niels-NTG/FTLAV) — savefile parser (basis for the state fallback)
