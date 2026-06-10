---
title: How scoring works
description: ftl_bench reports FTL native score, solve/win rate, efficiency, and per-suite breakdowns over seeded instances.
---

`ftl_bench` reports the game's own run score as the headline metric. The runner
evaluates agents on reproducible seeded instances and aggregates the resulting
trajectories.

## Headline metric: FTL score

At the end of a run, FTL computes a native score from real game progress: scrap
collected, ships destroyed, beacons and sectors explored, flagship progress, and
difficulty. `ftl_bench` reports the mean of that value over the evaluated suite.

Using the native score is useful because it is:

- **Holistic:** it rewards the same progress the game rewards.
- **Hard to farm:** it requires real exploration, combat, loot, sector progress,
  and ultimately the flagship.
- **Comparable:** it is easier to interpret than a newly invented scalar.
- **Unsaturated:** full wins and stronger routes leave room for better agents.

## Solve and win rate

Each instance also has a strict goal check. The aggregate reports `Solve N/M`.
For full-game runs, a solve is the real win: destroying the rebel flagship. For
mixed-suite probes, solve means the instance's explicit goal was met, such as
surviving enough jumps or reaching a sector while healthy.

## Efficiency

Efficiency is reported separately, usually as jumps or turns per instance. It is
not the headline number, but it helps distinguish an agent that reaches the same
goal cleanly from one that burns many turns in no-op loops or low-value detours.

## Instances and tiers

An instance pins the run:

```text
(seed, ship, difficulty, tier, goal)
```

The seed fixes map and event RNG. Tiers split development seeds from held-out
reporting seeds:

- `public`: tune, debug, and compare during development.
- `semi_private`: report the benchmark number.

## Baseline ladder

Scores should be interpreted against reference floors:

- `random`: legal actions sampled from the same interface.
- `scripted`: heuristic navigation, fleeing, event handling, and simple combat.
- model rows: real LLM or agent systems, using the same runner and scorer.

The scoring and aggregation code lives in
`harness/src/ftl_bench/{scoring,aggregate}.py`. Suites live in `scenarios/`, and
the runner is `adapter/run_benchmark.py`.
