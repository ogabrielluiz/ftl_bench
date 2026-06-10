---
title: Benchmark protocol
description: "The canonical ftl_bench evaluation contract: suites, modes, tiers, metrics, and reporting rules."
---

This page is the source of truth for reporting an `ftl_bench` number.

## Canonical question

Evaluate the agent's ability to play FTL from seeded starts through the standard
observe/act interface. The agent decides all in-game policy. The harness only
sets up the run, applies commands, records the trajectory, and scores the result.

## Suites

| Suite | Use it for | Notes |
|---|---|---|
| `scenarios/full_game.json` | The pure play-the-game track | The agent is told to win FTL. Progress is measured toward 8 sectors plus 3 flagship phases. |
| `scenarios/suite_v1.json` | Fast probes, baselines, and regression testing | Mixed seeded instances: survival, sector reach, healthy sector reach, and full-run progress. This is the runner default today. |

If you are reporting a headline model result, prefer `full_game.json` unless
you explicitly state you are reporting `suite_v1`.

## Run modes

| Mode | Meaning |
|---|---|
| `--mode gameover` | Default for the LLM track. Play until a real win, death, or stall. Best for full-game reporting. |
| `--mode budget` | Stop within the instance jump budget. Useful for cheaper probes and fast regressions. |

The mode is recorded in the manifest and agent label, so gameover and budget
runs are never silently mixed.

## Agent contract

The agent receives:

- a system prompt containing the versioned interface manual, currently
  `prompts/ftl_agent_v4.md`;
- the objective and evaluation rules;
- a compact JSON observation;
- recent action history.

The agent returns a brief reason plus an `ACTION:` block. In v4 the block may
contain multiple paused commands and should end with `advance <frames>`:

```text
ACTION:
  power 3 3
  crew 1 2
  fire 0 3
  advance 150
```

Changing the prompt manual changes the agent identity. Report the prompt
version, model, backend, suite, mode, tier, and retry setting with every result.

## Tiers

| Tier | Purpose |
|---|---|
| `public` | Tune and debug against these seeds. |
| `semi_private` | Report this number. Treat these seeds as held out. |

Report public results only as development numbers. A comparable benchmark row
should use `--tier semi_private`.

## Metrics

| Metric | Definition |
|---|---|
| `FTL score` | Mean of FTL's native run score over the evaluated instances, with seed standard error. |
| `Solve / win rate` | Fraction of instances that met the goal. For full-game runs, this means beating the flagship. |
| `Efficiency` | Jumps or turns per instance. |
| `Breakdowns` | Per-type and per-tier aggregates for diagnosing strengths and failures. |

Every run writes a trajectory and manifest under `runs/benchmark/`.

## Baselines

Report model rows next to reference floors:

| Agent | Purpose |
|---|---|
| `random` | Legal-move floor. |
| `scripted` | Heuristic floor for navigation, events, fleeing, and simple combat. |
| human reference | Planned row for sanity-checking instance quality and efficiency. |

## Recommended reporting command

From the repository checkout:

```bash
cd harness
uv run python ../adapter/run_benchmark.py \
  --agent llm \
  --backend <anthropic|claude-cli|codex> \
  --model <model-id> \
  --suite ../scenarios/full_game.json \
  --tier semi_private \
  --mode gameover \
  --prompt-version v4
```

For retries, include `--retries N` and report it as a separate row. Retry runs
score the best attempt and also emit a solve@k learning curve.

## Minimum report

A complete row should include:

- model and backend;
- suite path;
- tier;
- mode;
- prompt version;
- retry count;
- FTL score with standard error;
- solve/win rate;
- date and commit hash;
- link or path to the saved summary JSON.
