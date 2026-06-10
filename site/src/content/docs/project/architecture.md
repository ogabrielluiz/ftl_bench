---
title: Architecture
description: How ftl_bench turns a real-time game into a paused, scored agent environment.
---

`ftl_bench` is built in layers, from the running game up to the model or agent.

```text
Model or agent
  reads compact JSON observations
  writes paused action plans
        |
        v
adapter/
  play_cli.py       manual or agent-facing CLI
  llm_agent.py      built-in LLM loop and provider backends
  run_benchmark.py  suite runner, manifests, scoring
        |
        v
harness/
  AgentSession      reset / observe / step
  scoring           per-instance scoring
  aggregate         suite metrics
  trajectory        JSONL logging
        |
        v
mod/ftl_bench_bridge/
  Hyperspace Lua bridge inside FTL
  pause gating, observation JSON, command application
        |
        v
FTL engine
```

## Control loop

FTL is real-time-with-pause. The bridge keeps the game paused by default. A
turn looks like this:

1. The harness reads the latest observation JSON.
2. The agent returns an action plan.
3. The bridge applies the commands while the game is paused.
4. The bridge advances the simulation for the requested frame budget.
5. The bridge re-pauses on the next decision point or when the budget ends.
6. The harness records the resulting state and action outcome.

This gives the agent unlimited thinking time, while the game clock only moves
when the agent explicitly advances it.

## Decision interrupts

The advance can stop early when the bridge sees a critical event: combat starts,
the ship takes damage, a boarder appears, a fire starts, an event popup blocks
the game, or another important decision point is reached. The next observation
sets `interrupted_by` so the agent knows why it got control back.

## Transport

The in-game Lua sandbox does not expose sockets. The bridge communicates through
JSON files in FTL's user folder:

- observation file: written by the bridge and read by the harness;
- action file: written by the harness and consumed by the bridge;
- sequence numbers: make action application idempotent and race-tolerant.

Native Windows resolves the FTL user folder automatically. WSL and macOS use
`FTL_SAVE_DIR`.

## Why Hyperspace

[FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace) is an
open-source C++ executable mod that exposes FTL's engine to Lua through SWIG
bindings. It already gives scripts access to ship state, crew, systems, weapons,
map state, and seeded runs. `ftl_bench` extends that surface where the benchmark
needs reliable action bindings or richer observations.

The project avoids brittle screen scraping and click automation for core game
control. Visual capture can be added for agents that need it, but the benchmark
contract is the structured observe/act loop.

## Layout

| Dir | Purpose |
|---|---|
| `mod/ftl_bench_bridge/` | In-game Lua bridge: state serialization, action application, pause gating. |
| `harness/` | Python environment: reset, observe, step, scoring, aggregation, trajectories. |
| `adapter/` | Agent-facing surfaces: CLI, LLM track, suite runner. |
| `scenarios/` | Seeded benchmark suites. |
| `prompts/` | Versioned agent interface manuals. |
| `docs/deepdive/` | Source-grounded notes on Hyperspace internals. |
