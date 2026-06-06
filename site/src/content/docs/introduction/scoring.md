---
title: How scoring works
description: The benchmark metric is FTL's own native run score, plus a solve/win rate, over reproducible seeded instances.
---

`ftl_bench` uses **FTL's own native run score** as the metric. It evaluates agents on reproducible
**instances**, so results are comparable across models and runs.

## The metric: FTL's native score

At the end of every FTL run the game computes a score from how well you played: scrap collected,
ships destroyed, beacons and sectors explored, and the flagship kill, all times a difficulty
multiplier. That is the designers' own holistic measure of run quality, and it is what we report.

Using the game's score instead of a coined metric has real advantages:

- **Holistic.** It already weighs the things that matter (loot, kills, depth, the win), so we do
  not have to invent and justify a formula.
- **Non-saturating.** A high score essentially requires beating the flagship and playing
  thoroughly, so the ceiling stays high as models improve.
- **Gaming-resistant.** You cannot farm score by jumping in place; the game only rewards real
  progress.
- **Interpretable.** Anyone who has played FTL knows what a score means.

The run's score is read live from the game (`ftl_score` in the observation) and taken at the
natural game-over, which is exactly when [play-to-game-over](/reference/play-to-gameover/) ends a
run.

## Reported metrics

- **FTL score** (headline): the mean of FTL's native run score over the suite, with a seed-based
  standard error.
- **Solve / win rate**: the fraction of instances that achieve the scenario goal. For full games
  that is the win (flagship defeated).
- **Efficiency**: jumps or turns per instance.

## Instances

An **instance** is a fully specified, seeded scenario: `(seed, ship, difficulty, goal)`. The seed
pins the map and events; difficulty is pinned so the score multiplier is constant and runs are
comparable. The agent decides everything in-game.

## Tiers

To discourage overfitting to known seeds, the suite is split into a `public` tier you tune
against and a held-out `semi_private` tier that is the reported number.

## Baseline ladder

Two reference agents make any score interpretable:

- **`random`**: a legal-move floor.
- **`scripted`**: a heuristic floor (exit navigation, flee on danger, event-choice escalation,
  stalemate-flee).

A high agent score is meaningful because it sits between these floors and the unsaturated ceiling
of actually beating the flagship.

The scoring code lives in `harness/src/ftl_bench/{scoring,aggregate}.py`, the suites in
`scenarios/`, and the runner in `adapter/run_benchmark.py`. See
[Running and results](/evaluate/running/) to produce these numbers.
