# ftl_bench

An agent-evaluation benchmark that lets LLM coding agents **play FTL: Faster Than Light** through a clean, intent-level interface built on the [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) Lua API.

FTL is a real-time-with-pause roguelike: resource management, risk under uncertainty, combat micro, and long-horizon planning across a branching map. That makes it a rich substrate for measuring agent decision-making. `ftl_bench` wraps it into a reproducible, turn-based environment with structured observations, an intent-level action space, seed-pinned runs, and full trajectory logging.

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
| **Autonomous start/restart** (`start_game('continue'\|'new')`, no human click) | ✅ |
| **Reproducible seeds** (`start_game('new', seed=…)` → identical map) | ✅ M4 |
| **MCP adapter** (LLM agent plays via tools) + scripted baseline agent | ✅ M5 |
| **Trajectory recording + scoring** (decisions, jumps, kills, hull, survival) | ✅ M6 |

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
- **Reset-from-in-game** needs a "return to menu" binding (new-game flow only runs from the menu; for now `restart_ftl.sh` reaches it) — needs a Hyperspace rebuild.
- **Store** transactions (M3 deferred), beam weapons, richer event-choice text.

## Related

- [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) — the modding API this is built on
- [FTLAV](https://github.com/Niels-NTG/FTLAV) — savefile parser (basis for the state fallback)
