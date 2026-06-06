---
title: Quickstart
description: Run a baseline, then evaluate your own model on ftl_bench.
---

This gets you from a fresh checkout to a scored run. It assumes FTL and Hyperspace are installed
(see [Install the game](/install/pc/)) and the game is launched and sitting at the main menu.

## 1. Point the harness at FTL

The harness talks to the running game through files in FTL's user folder. Set `FTL_SAVE_DIR` to
that folder so the harness reads and writes the right place.

```bash
# PC (Windows / WSL): the Windows user folder, via /mnt/c
export FTL_SAVE_DIR="/mnt/c/Users/<you>/Documents/My Games/FasterThanLight"
# macOS
export FTL_SAVE_DIR="$HOME/Library/Application Support/FasterThanLight"
```

## 2. Run a baseline

Start with the scripted baseline on one instance and a small jump budget, so a full pass does not
get in the way of a smoke test:

```bash
python3 adapter/run_benchmark.py --agent scripted --max-instances 1 --budget-cap 8
```

You should see per-instance scoring and then an aggregate line:

```
== RESULTS ==
  FTL score 40.0 ± 0.0  |  Solve 1/1
```

`--agent random` gives the legal-move floor for comparison.

## 3. Run your model

The LLM track drives a real model over the same observe/act surface the baselines use:

```bash
# Anthropic API (set ANTHROPIC_API_KEY first)
python3 adapter/run_benchmark.py --agent llm --backend anthropic --model claude-sonnet-4-6

# Local Claude CLI (no API key; uses your claude login)
python3 adapter/run_benchmark.py --agent llm --backend claude-cli --model sonnet
```

To run your **own** model (any provider, a local model, or a full custom agent), see
[Bring your model or agent](/evaluate/bring-your-model/).

## 4. Read the results

Each run prints per-instance `ftl_score` plus the aggregate `FTL score ± SE | Solve N/M`, and writes the
trajectory and a reproducibility manifest under `runs/`. See
[Running and results](/evaluate/running/) for the full flag set and how to interpret the output.

:::tip[PC: launch via Steam]
On Windows, FTL must be launched through Steam for Hyperspace to inject. The runner handles
relaunches for you. See [Install the game (PC)](/install/pc/).
:::
