---
title: Architecture
description: How ftl_bench turns a real-time game into a turn-based, scored environment.
---

`ftl_bench` is built in layers, from the running game up to your agent.

```
┌──────────────────────────────────────────────────────────────┐
│  Your model or agent                                          │
│   reads JSON observations, returns intent-level commands      │
└───────────────▲───────────────────────────┬──────────────────┘
                │                            │
┌───────────────┴───────────────────────────▼──────────────────┐
│  adapter/   play_cli.py (turn CLI), llm_agent.py (LLM track), │
│             run_benchmark.py (suite runner + scoring)         │
├───────────────────────────────────────────────────────────────┤
│  harness/   AgentSession: reset / observe / step,            │
│             seeds, scoring, trajectory logging                │
└───────────────▲───────────────────────────┬──────────────────┘
                │  file transport (JSON)     │
┌───────────────┴───────────────────────────▼──────────────────┐
│  mod/ftl_bench_bridge  (Hyperspace Lua mod inside FTL):       │
│   • per-frame hook gates the sim (pause between turns)        │
│   • serializes the observation JSON                           │
│   • applies action commands via the Lua API                  │
│  (+ extended Hyperspace C++/SWIG bindings for action gaps)   │
└───────────────────────────────────────────────────────────────┘
```

## Making a real-time game turn-based

FTL is real-time-with-pause. The bridge keeps the game **paused by default** and advances it in
controlled increments. Each turn: write the chosen action, unpause for a bounded number of frames,
re-pause, and stamp a fresh observation. The advance also stops early on a critical event (combat
started, took damage, a boarder, a fire, an event popup), so the agent never sleeps through a
crisis. The agent has unlimited thinking time; the clock only moves when it acts.

## Transport

The in-game Lua sandbox has no sockets or file IO of its own, so the bridge talks to the harness
through JSON files in FTL's user folder: an observation file the harness reads and an action file
the bridge applies. The harness is pointed at that folder with `FTL_SAVE_DIR`.

## Why Hyperspace

[FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) is an open-source C++ "exe mod"
that exposes FTL's engine to Lua via SWIG bindings. It already lets scripts read full game state
and drive much of the simulation, and it supports seeded runs with the seed readable from Lua,
which is the basis for reproducibility. Where a capability is not bound (the file transport, JSON
serialization, weapon room-targeting, event confirm, jump trigger, store), `ftl_bench` extends
Hyperspace with new bindings rather than resorting to brittle screen or input automation.

## Layout

| Dir | Purpose |
|---|---|
| `mod/ftl_bench_bridge/` | in-game Lua mod: state serialization, action application, sim gating |
| `harness/` | Python env: `reset / observe / step`, episodes, seeds, scoring, logging |
| `adapter/` | the agent-facing surface: turn CLI, LLM track, suite runner |
| `scenarios/` | benchmark scenario definitions and pinned seeds |
| `prompts/` | versioned agent operating manuals (`ftl_agent_<v>.md`) |
