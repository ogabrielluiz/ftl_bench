---
title: The benchmark
description: What ftl_bench measures and why FTL is a strong long-horizon agent benchmark.
---

`ftl_bench` measures whether an agent can play a long, failure-prone game by
reading state, choosing actions, and recovering from consequences. The agent
plays *FTL: Faster Than Light* through a paused, intent-level interface. The
harness sets up seeded runs, exposes the current game state, applies the
agent's commands, records the trajectory, and scores the result.

## The core question

Can a model control a real game over many decisions without a scripted policy
helping it?

A good FTL run requires the agent to combine several capabilities:

| Capability | What exposes it |
|---|---|
| Tactical control | Weapon targeting, shield pressure, enemy weapon suppression, cloak/hack/boarding timing. |
| Resource allocation | Reactor bars, scrap, fuel, missiles, drone parts, hull, stores, and upgrades. |
| Crisis recovery | Fires, boarders, oxygen loss, damaged systems, low crew health, missed shots. |
| Long-horizon planning | Route choice across sectors, detours for rewards, exit timing, flagship preparation. |
| Uncertainty handling | Events, hazards, enemy loadouts, stores, and the advancing rebel fleet. |

The benchmark is intentionally not a single scripted puzzle. A fragile policy can
look good for a few turns, then fail when the ship catches fire, weapons go down,
or an event changes the state. That is the behavior the benchmark is meant to
surface.

## How the agent plays

FTL is real-time-with-pause. `ftl_bench` keeps the game paused between turns.
Each turn the agent receives a decision-complete JSON observation and returns an
`ACTION:` block. Commands are applied while paused, then the agent advances the
clock:

```text
ACTION:
  power 3 3
  crew 0 8
  doors close 8
  fire 1 3
  advance 150
```

This is the v4 interface. It is deliberately closer to human pause-play than a
one-click loop: set up the ship, let the game run, then react to the next
decision point.

## What the harness does not do

The harness does not choose strategy. It does not decide whether to fight, flee,
repair, buy, sell, target weapons, path to the exit, or board the enemy. Those
are agent decisions.

The harness only:

- starts a seeded run;
- serializes the current game state;
- validates and applies the agent's commands;
- advances and re-pauses the simulation;
- records the trajectory and manifest;
- scores the outcome.

That separation is what makes a score attributable to the agent rather than to
the environment.

## Evaluation tracks

There are two useful ways to run the benchmark:

- **Full-game track:** use `scenarios/full_game.json`. The agent is told to win
  FTL and plays until a real win, death, or stall. This is the cleanest
  "play the game" number.
- **Mixed v1 suite:** use `scenarios/suite_v1.json`. This includes seeded
  survival, sector progress, health, and full-run progress instances. It is
  useful for fast baselines and regression testing.

Both tracks use the same observation/action interface and the same scoring
pipeline. See [Benchmark protocol](/introduction/protocol/) for the exact
reporting rules.
