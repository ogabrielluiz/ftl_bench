---
title: Running and results
description: The run_benchmark CLI, modes, output, manifests, and reporting conventions.
---

`adapter/run_benchmark.py` runs an agent over a suite and reports the headline
metrics. Scripted, random, and LLM agents all use the same runner and scorer.

## CLI

Run from the repository checkout:

```bash
cd harness
uv run python ../adapter/run_benchmark.py [options]
```

| Option | Meaning |
|---|---|
| `--agent {scripted,random,llm}` | Which agent to run. |
| `--backend {anthropic,claude-cli,codex}` | LLM track backend. Add your own in `adapter/llm_agent.py`. |
| `--model MODEL` | LLM model id. Anthropic defaults to `claude-sonnet-4-6`; CLI backends use their local defaults when omitted. |
| `--prompt-version V` | Which `prompts/ftl_agent_<v>.md` manual to use. Default is `v5`. |
| `--suite PATH` | Suite file. Default is `scenarios/suite_v1.json`; use `../scenarios/full_game.json` for the pure full-game track. |
| `--tier TIER` | Filter by tier, usually `public` or `semi_private`. |
| `--type TYPE` | Filter by scenario type. |
| `--max-instances N` | Cap the number of instances. |
| `--budget-cap N` | Cap jump budget for faster smoke runs. |
| `--mode {gameover,budget}` | LLM track mode. `gameover` is default and plays to real win/death/stall; `budget` stops within the jump budget. |
| `--stall-limit N` | Gameover mode: declare a loss after N no-progress turns. Default is 10. |
| `--retries N` | Give up to N extra same-seed tries and score the best attempt. |
| `--out DIR` | Output directory. Default is `runs/benchmark`. |

## Output

Per instance, the runner prints score, solve status, and sub-objective
breakdown. It then prints the aggregate:

```text
== RESULTS ==
  FTL score 184 +/- 31  |  Solve 1/7
  ftl_score_median: 160
  solve_pct: 14.3
  median_jumps_per_instance: 6
  by_type: {"full_run": {...}}
  by_tier: {"semi_private": {...}}
```

`FTL score` is the mean of the native FTL run score. `Solve N/M` is the strict
goal count. For full-game runs, a solve is a flagship win.

With `--retries N`, output also includes the best-of-k learning curve:
mean/median best FTL score and cumulative solve rate at each attempt budget.

## Files written

Under `--out`:

- `<instance>.jsonl`: full trajectory for one attempt.
- `summary_<agent-label>.json`: aggregate plus per-instance results.
- manifest metadata in each trajectory: seed, ship, difficulty, tier, schema,
  runner version, agent label, backend, model, prompt version, mode, and retry
  count.

The agent label encodes configuration, for example:

```text
llm-anthropic-claude-sonnet-4-6-v5-gameover10
llm-codex-gpt-5-v5-gameover10-retries2
```

Different prompts, modes, backends, models, and retry settings are distinct
benchmark rows.

## Reporting a number

Use the held-out tier:

```bash
uv run python ../adapter/run_benchmark.py \
  --agent llm \
  --backend <anthropic|claude-cli|codex> \
  --model <id> \
  --suite ../scenarios/full_game.json \
  --tier semi_private \
  --mode gameover \
  --prompt-version v5
```

Tune against `public`; report `semi_private`. Include the suite path and commit
hash with the score.
