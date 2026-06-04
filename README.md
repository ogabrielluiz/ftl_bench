# ftl_bench

An agent-evaluation benchmark that lets LLM coding agents **play FTL: Faster Than Light** through a clean, intent-level interface built on the [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) Lua API.

FTL is a real-time-with-pause roguelike: resource management, risk under uncertainty, combat micro, and long-horizon planning across a branching map. That makes it a rich substrate for measuring agent decision-making. `ftl_bench` wraps it into a reproducible, turn-based environment with structured observations, an intent-level action space, seed-pinned runs, and full trajectory logging.

## The benchmark: a scenario suite scored by goal achievement

Inspired by the design of canonical agent benchmarks — **ARC-AGI** (a held-out task suite measuring generalization, not memorization), **WebShop** (instruction-conditioned goals with a dense partial-credit reward), and **VideoGameBench / BALROG** (LLM agents driving real games to milestone progress) — `ftl_bench` evaluates agents on a suite of reproducible **scenario instances**, not on raw play.

- **Instance** = a fully-specified, seeded scenario `(seed, ship, difficulty, goal)`. The seed pins the map + events; the goal is a set of weighted sub-objectives.
- **The agent decides everything in-game** (fight, flee, target, power, repair, navigate). The harness scores **only goal achievement** — no decision policy is baked into the env or scoring.
- **Goal-conditioned partial credit**: each instance earns `r ∈ [0,1]` = the weighted intersection of achieved vs. requested sub-objectives, × a legitimacy gate that collapses metric-gaming (e.g. jumping in place). `Score = 100·r`.
- **Headline metric — GCS@1** (Goal Completion Score) = the mean Score over the suite (± seed SE), alongside a strict **Solve Rate** (% of instances fully achieving the goal) and an **efficiency** axis (jumps/turns per instance).
- **Anti-memorization split**: a `public` tier to tune against and a held-out `semi_private` tier that is the leaderboard number.
- **Baseline ladder**: a `random`-legal floor and a `scripted` heuristic floor, so a high agent score is interpretable.

**Scenario types (v1 — run on today's action set):** `survive_n_jumps` (make N jumps alive), `reach_sector` (advance to sector K), `reach_sector_healthy` (reach K with hull + crew intact — a multi-attribute goal), `full_run` (milestone progress toward beating the flagship — the unsaturated ceiling). Higher-signal micro-encounters (`win_this_combat`, `escape_a_crisis`, `event_risk_choice`) and the flagship/store tiers are next (see `docs/NEXT.md`).

**Run it:**
```bash
defaults write com.example.FTL NSAppSleepDisabled -bool YES   # one-time: tick unfocused
scripts/restart_ftl.sh none                                   # launch FTL to the menu
cd harness && uv run python ../adapter/run_benchmark.py --agent scripted   # scripted floor
cd harness && uv run python ../adapter/run_benchmark.py --agent random      # random floor
cd harness && uv run python ../adapter/run_benchmark.py --agent scripted --tier semi_private  # held-out leaderboard number
```
Output: per-instance `Score` + sub-objective breakdown, then the aggregate `GCS@1 ± SE | Solve N/M` with per-type/tier breakdown. Each instance's trajectory + a reproducibility manifest (seed, ship, schema, runner/agent version) is saved under `runs/benchmark/`. The benchmark code: `harness/src/ftl_bench/{scenario,scoring,aggregate}.py`, `scenarios/suite_v1.json`, `adapter/run_benchmark.py`.

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
| `docs/specs/` | Design spec |
| `docs/deepdive/` | Source-grounded analysis of the Hyperspace Lua surface (what's exposed vs. what we must build) |

## Core idea: making a real-time game turn-based

The harness keeps the game **paused by default** and unpauses in controlled increments. The default **event-driven gating** mode runs the sim until the next significant decision point (enemy weapon about to fire, system damaged, projectile incoming, event/store/jump screen) then re-pauses and requests an action — mirroring how a skilled human micro-pauses. A simpler **fixed-tick** mode is available for cheaper runs.

## Status — working end-to-end ✅

An agent can play FTL through a turn-based loop, all **verified live** on FTL 1.6.13 + Hyperspace 1.22.2 (macOS):

| Capability | State |
|---|---|
| **Observation stream** (hull, reactor, systems, crew, weapons, enemy, map, events) | ✅ M1 |
| **Pause-gating + closed loop** (`reset`/`observe`/`step`) | ✅ M2 |
| **Actions**: `set_system_power`, `move_crew`, `jump`, `choose_event`, `fire_weapon` | ✅ M3 |
| **Autonomous start/restart + in-game reset** (`reset_episode(seed)`, no click) | ✅ |
| **Reproducible seeds** (`start_game('new', seed=…)` → identical map) | ✅ M4 |
| **MCP adapter** (LLM agent plays via tools) + scripted baseline agent | ✅ M5 |
| **Trajectory recording + scoring** (decisions, jumps, kills, hull, survival) | ✅ M6 |
| **Sector progression** (`leave_sector` at the exit beacon → next sector) | ✅ |
| **Richer observation** (exit beacon + position, rebel fleet, sector-choice flag, incoming fire) | ✅ |
| **Smarter baseline** (exit navigation, flee on O2/weapon/crew danger, event-choice escalation, stalemate-flee) | ✅ |

### Quick start (game already built; see `scripts/`)
```bash
defaults write com.example.FTL NSAppSleepDisabled -bool YES   # one-time: tick unfocused
scripts/restart_ftl.sh none                                   # launch FTL to the menu
cd harness && uv run python ../adapter/baseline_agent.py --new --seed 42 --jumps 6 --record runs/run.jsonl
```
The MCP server (`adapter/ftl_mcp_server.py`) exposes the env as tools for an LLM agent.

**Two operating caveats:** (1) FTL must not be App-Napped — the `defaults` line above keeps it ticking in the background so the harness drives it unattended. (2) The mic-permission dialog reappears only after a Hyperspace **C++ rebuild** (code-signature change); it persists across plain relaunches.

### Docs
- [`docs/specs/2026-06-03-ftl-agent-interface-design.md`](docs/specs/2026-06-03-ftl-agent-interface-design.md) — M1 design spec
- [`docs/specs/2026-06-03-m2-pause-action-design.md`](docs/specs/2026-06-03-m2-pause-action-design.md) — M2 design
- [`docs/deepdive/hyperspace-lua-surface.md`](docs/deepdive/hyperspace-lua-surface.md) — source-grounded Lua state/action surface
- [`docs/plans/2026-06-03-m1-observation-stream.md`](docs/plans/2026-06-03-m1-observation-stream.md) — M1 implementation plan

### Known gaps / next
- **Store** transactions (M3 deferred) and beam weapons (M3 deferred).

## Related

- [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) — the modding API this is built on
- [FTLAV](https://github.com/Niels-NTG/FTLAV) — savefile parser (basis for the state fallback)
