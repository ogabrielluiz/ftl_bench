---
title: The benchmark
description: What ftl_bench measures and why a full game of FTL makes a strong agent benchmark.
---

`ftl_bench` measures **agent decision-making** by having an LLM agent play a full game of
*FTL: Faster Than Light* through a turn-based, intent-level interface. You bring a model or an
agent; the harness runs it over a fixed set of seeded scenarios and scores how far it gets.

## Why a game, and why this one

A single scripted task is easy to saturate and easy to overfit. A full FTL run is the opposite: a
long sequence of interdependent decisions under uncertainty, with no single right move and a
ceiling that rises as agents get better. To do well, an agent has to:

- **Manage scarce resources**: reactor power bars, missiles, drone parts, scrap, fuel, crew.
- **Read and resolve combat**: is this fight winnable? target shields or the weapons room? flee an
  evasive enemy? put out fires before they suffocate the crew?
- **Handle risk under uncertainty**: branching events with hidden outcomes, hazards (asteroids,
  ion storms, suns, pulsars), and the advancing rebel fleet.
- **Plan across the long horizon**: navigate a branching map across eight sectors toward the rebel
  flagship, trading detours for loot against the pursuit closing in.

No fixed policy wins; the agent must adapt. That is the capability the benchmark is built to
expose.

## What the agent does each turn

The game is **paused** between turns. Each turn the agent receives one decision-complete JSON
[observation](/reference/observation/), the whole game state, and replies with exactly one
intent-level [command](/reference/actions/) such as `jump 3`, `fire 0 1`, `power 0 2`, or
`crew 1 4`. The command unpauses the sim briefly, then it re-pauses and the next observation is
produced. The agent has unlimited thinking time per turn; the clock only moves when it acts.

## The agent decides everything

Fight, flee, target, power, repair, navigate, spend scrap: all of it is the agent's call. **No
decision policy is baked into the environment or the scoring.** The harness only sets up the game,
exposes the state and the action set, and measures the outcome. That is what makes a score
attributable to the agent rather than to the harness.

See [How scoring works](/introduction/scoring/) for the metrics, and
[Bring your model or agent](/evaluate/bring-your-model/) to plug yours in.
