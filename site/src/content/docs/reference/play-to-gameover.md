---
title: Play-to-game-over mode
description: Run an agent until the game actually ends, with a stall guard that ends idle runs as a loss.
---

**Play-to-game-over is the default LLM mode** (`--mode gameover`). The agent
plays a full game until it actually ends, with a guard that turns dawdling into
an automatic loss. This is the canonical full-game track: win by beating the
rebel flagship, or lose by dying or stalling.

```bash
# gameover is the default full-game run
cd harness
uv run python ../adapter/run_benchmark.py --agent llm --backend <yours> --model <id> --stall-limit 10

# opt out to the bounded jump-budget probe
uv run python ../adapter/run_benchmark.py --agent llm --backend <yours> --model <id> --mode budget
```

## Termination

A run in this mode ends when any of these happen:

- **Natural game-over:** the ship is destroyed, the crew is lost, or the
  flagship is beaten.
- **Stall:** the agent makes no forward progress for `--stall-limit`
  consecutive turns. Default is 10. This is declared a loss.
- **Hard cap:** a high safety limit bounds pathological runs.

When the episode ends, the runner returns the game to a clean state before the
next instance.

## What counts as progress

The stall counter resets on meaningful activity:

- advancing the map, reaching the exit, or changing beacons;
- damaging or destroying an enemy;
- gaining scrap or rewards;
- repairing systems, fighting fires, clearing intruders, or otherwise changing
  ship state.

It does not reset when the agent repeats a no-op, waits at full safety without
moving forward, or stays in a combat stalemate where neither ship state nor goal
progress changes.

## Why it exists

Weak agents can otherwise spend long runs repeating commands that already took
effect or sitting in unwinnable states. The stall rule keeps evaluation bounded
without cutting off active recovery or real play. The rule is stated in the
agent prompt, so avoiding a stall is part of the agent's job.
