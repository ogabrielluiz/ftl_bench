---
title: Quickstart
description: Run a baseline, then evaluate a model on ftl_bench.
---

This gets you from a checkout to a scored run. It assumes FTL and Hyperspace are
installed and the game can be launched. For reportable long runs, use the
[native Windows setup](/install/pc/).

## 1. Point the harness at FTL

On native Windows, there is nothing to set: the runner finds
`Documents\My Games\FasterThanLight` and launches FTL through Steam.

On WSL or macOS, set `FTL_SAVE_DIR` to the FTL user folder:

```bash
# WSL
export FTL_SAVE_DIR="/mnt/c/Users/<you>/Documents/My Games/FasterThanLight"

# macOS
export FTL_SAVE_DIR="$HOME/Library/Application Support/FasterThanLight"
```

## 2. Smoke-test a baseline

From the repository root:

```bash
cd harness
uv run python ../adapter/run_benchmark.py --agent scripted --max-instances 1 --budget-cap 8
```

You should see per-instance output and an aggregate:

```text
== RESULTS ==
  FTL score 40.0 +/- 0.0  |  Solve 1/1
```

Run the random floor the same way:

```bash
uv run python ../adapter/run_benchmark.py --agent random --max-instances 1 --budget-cap 8
```

## 3. Run a model

The LLM track uses the same observation/action surface as the baselines. Pick a
backend you can run:

```bash
# Anthropic API: requires ANTHROPIC_API_KEY
uv run python ../adapter/run_benchmark.py --agent llm --backend anthropic --model claude-sonnet-4-6

# Local Claude CLI: uses your local claude login
uv run python ../adapter/run_benchmark.py --agent llm --backend claude-cli --model sonnet

# Local Codex CLI: uses your Codex/ChatGPT auth
uv run python ../adapter/run_benchmark.py --agent llm --backend codex --model gpt-5
```

By default, the LLM track uses `--mode gameover` and `--prompt-version v4`: the
agent plays until a real win, death, or stall, and replies with a paused
multi-command action plan.

## 4. Report a full-game number

For the pure play-the-game track:

```bash
uv run python ../adapter/run_benchmark.py \
  --agent llm \
  --backend <anthropic|claude-cli|codex> \
  --model <model-id> \
  --suite ../scenarios/full_game.json \
  --tier semi_private \
  --mode gameover \
  --prompt-version v4
```

Each run writes trajectories, summaries, and manifests under `runs/benchmark/`.
See [Benchmark protocol](/introduction/protocol/) for what to report.

:::tip[PC: launch via Steam]
On Windows, FTL must be launched through Steam for Hyperspace to inject. The
runner handles relaunches for you.
:::
