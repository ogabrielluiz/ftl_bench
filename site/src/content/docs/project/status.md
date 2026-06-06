---
title: Results & baselines
description: Current state of ftl_bench, the baseline ladder, and what runs natively.
---

## What works

The full loop runs end to end: an agent plays FTL through the turn-based interface, and the
trajectory is scored and aggregated automatically. Capabilities verified live:

- Observation stream, pause-gating, and the closed `reset / observe / step` loop.
- The full action set: power, crew, jump, event, fire, beam, leave (sector transition), plus
  cloak, battery, hack, drones, teleporter/boarding, mind control, doors, and store transactions.
- Combat that resolves, autonomous start/restart and in-game reset, reproducible seeds.
- Trajectory recording, scoring, and aggregation (GCS@1, solve rate).
- The LLM track with pluggable backends, and play-to-game-over mode with a stall guard.

## Native x86 vs Rosetta

The benchmark runs on both macOS (under Rosetta) and natively on a Windows/WSL PC. The PC path is
recommended: native x86 removes the address-translation crash class that freezes jumps and sector
transitions under Rosetta. On native x86 the scripted baseline runs jumps, combat, and a sector
crossing crash-free; under Rosetta those same operations can freeze, which caps full-length runs.

## Baseline ladder

The reference floors make any agent score interpretable:

| Agent | What it is |
|---|---|
| `random` | legal-move floor |
| `scripted` | heuristic floor: exit navigation, flee on danger (low oxygen / crew / no powered weapons), event-choice escalation, stalemate-flee |

Run them with `--agent random` and `--agent scripted`. A real model on the LLM track slots in as a
third row, scored identically. See [How scoring works](/introduction/scoring/) and
[Running and results](/evaluate/running/).

## Notes for evaluators

- Tune against the `public` tier; report the held-out `semi_private` tier.
- Keep the prompt manual fixed (`--prompt-version v3`, the interface-only manual) so a number
  reflects the model rather than prompt changes. A different manual is a different, non-comparable
  agent, and the version is recorded in every run's manifest.
- Every run writes a full trajectory plus a reproducibility manifest under `runs/`.
