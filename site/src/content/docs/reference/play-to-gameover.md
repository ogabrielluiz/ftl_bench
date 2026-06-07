---
title: Play-to-game-over mode
description: Run an agent until the game actually ends, with a stall guard that ends idle runs as a loss.
---

**Play-to-game-over is the default LLM mode** (`--mode gameover`): the agent plays a full game
until it actually ends, with a guard that turns dawdling into an automatic loss. This is the
canonical track — the goal is to *win the game* (beat the rebel flagship), and the headline FTL run
score measures how far it got. The bounded jump-budget run is the opt-in `--mode budget` instead.

```bash
# gameover is the default — this is the canonical run:
python3 adapter/run_benchmark.py --agent llm --backend <yours> --model <id> --stall-limit 10

# opt out to the bounded jump-budget probe:
python3 adapter/run_benchmark.py --agent llm --backend <yours> --model <id> --mode budget
```

## Termination

A run in this mode ends when any of these happen:

- **Natural game-over**: the ship is destroyed, the crew is lost, or the flagship is beaten (a win).
- **Stall**: the agent makes no forward progress for `--stall-limit` consecutive turns (default
  10). This is declared a loss.
- A high hard cap bounds pathological runs.

When the episode ends, the agent returns the game to the main menu, so FTL is left in a clean state
rather than paused mid-run.

## What counts as a stall

The stall counter resets on **any meaningful activity**, and only trips on genuine inactivity. It
counts both:

- **goal progress**: advancing the map (a jump, a new position, reaching the exit), damaging the
  enemy, or gaining scrap; and
- **ship management**: fires being fought, systems repaired, intruders cleared, hull / oxygen /
  crew changing.

So actively handling a crisis (for example, putting out fires) is never penalized. The counter only
climbs when nothing is changing, such as re-issuing a command that already took effect or idling at
full health without jumping. A combat stalemate where the enemy is not dying and you are neither
advancing nor managing anything still counts as a stall.

## Why it exists

A weak agent can otherwise burn a whole budget repeating no-ops or sitting in an unwinnable fight.
Ending such runs as a loss keeps the score honest and the run length bounded, while never cutting
off an agent that is genuinely doing something. The rule is also stated in the agent's prompt, so
the agent can avoid it; the agent still makes every decision.
