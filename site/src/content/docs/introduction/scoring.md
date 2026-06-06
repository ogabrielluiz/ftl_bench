---
title: How scoring works
description: Instances, goal-conditioned partial credit, GCS@1, tiers, and the baseline ladder.
---

`ftl_bench` evaluates agents on reproducible **instances**, not on raw play, so results are
comparable across models and runs.

## Instances

An **instance** is a fully specified, seeded scenario: `(seed, ship, difficulty, goal)`. The seed
pins the map and events. The goal is a set of weighted sub-objectives, or, for full runs,
milestone progress toward beating the flagship. The agent decides everything in-game; the harness
scores only goal achievement.

## Scoring

- **Goal-conditioned partial credit.** Each instance earns `r ∈ [0,1]`, the weighted intersection
  of achieved versus requested sub-objectives, times a **legitimacy gate** that collapses
  metric-gaming (for example, jumping in place). `Score = 100 · r`.
- **GCS@1** (Goal Completion Score), the headline metric, is the mean Score over the suite, with a
  seed-based standard error.
- **Solve rate** is the strict fraction of instances that fully achieve the goal.
- **Efficiency** reports jumps or turns per instance.

## Tiers

To discourage overfitting to known seeds, the suite is split into a `public` tier you tune
against and a held-out `semi_private` tier that is the reported number.

## Baseline ladder

Two reference agents make any score interpretable:

- **`random`**: a legal-move floor.
- **`scripted`**: a heuristic floor (exit navigation, flee on danger, event-choice escalation,
  stalemate-flee).

A high agent score is meaningful because it sits between these floors and the unsaturated ceiling
of full-run, beat-the-flagship progress.

## Scenario types

| Type | Goal |
|---|---|
| `survive_n_jumps` | make N jumps while staying alive |
| `reach_sector` | advance to sector K |
| `reach_sector_healthy` | reach sector K with hull and crew intact |
| `full_run` | milestone progress toward beating the flagship (the unsaturated ceiling) |

The benchmark code lives in `harness/src/ftl_bench/{scenario,scoring,aggregate}.py`, the suites in
`scenarios/`, and the runner in `adapter/run_benchmark.py`. See
[Running and results](/evaluate/running/) to produce these numbers.
