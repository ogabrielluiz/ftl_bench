# ftl_bench

An agent-evaluation benchmark that lets LLM coding agents **play FTL: Faster Than Light** through a clean, intent-level interface built on the [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) Lua API.

FTL is a real-time-with-pause roguelike: resource management, risk under uncertainty, combat micro, and long-horizon planning across a branching map. That makes it a rich substrate for measuring agent decision-making. `ftl_bench` wraps it into a reproducible, turn-based environment with structured observations, an intent-level action space, seed-pinned runs, and full trajectory logging.

## Why Hyperspace

Hyperspace is an open-source C++ "exe mod" that exposes FTL's engine to **Lua via SWIG bindings**. It already lets scripts both *read* full game state (`Hyperspace.ships.player`/`.enemy`, crew, systems, weapons, map) and *drive* the simulation (move crew, allocate power, jump, fire). Crucially, it also supports **seeded runs** with the seed exposed to Lua (since ~v1.6.0), which gives us reproducibility for free. Where actions aren't yet bound (weapon room-targeting, event-choice selection, store buy/sell), we extend Hyperspace itself with new SWIG bindings rather than resorting to brittle screen/input automation.

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

## Status

🚧 **Design phase.** See:
- [`docs/specs/2026-06-03-ftl-agent-interface-design.md`](docs/specs/2026-06-03-ftl-agent-interface-design.md) — the design spec
- `docs/deepdive/` — source-level grounding of the Lua state/action surface (in progress)

## Related

- [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) — the modding API this is built on
- [FTLAV](https://github.com/Niels-NTG/FTLAV) — savefile parser (basis for the state fallback)
