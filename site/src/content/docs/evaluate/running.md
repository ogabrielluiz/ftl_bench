---
title: Running & results
description: The run_benchmark CLI, modes, output, and where results are written.
---

`adapter/run_benchmark.py` runs an agent over a suite and reports the headline metrics. The same
runner drives the scripted, random, and LLM agents, so any result is comparable.

## CLI

```bash
python3 adapter/run_benchmark.py [options]
```

| Option | Meaning |
|---|---|
| `--agent {scripted,random,llm}` | which agent to run |
| `--model MODEL` | LLM track: model id (default `claude-sonnet-4-6` for the anthropic backend) |
| `--backend {anthropic,claude-cli}` | LLM track: how the model is called (add your own; see [Bring your model](/evaluate/bring-your-model/)) |
| `--prompt-version V` | LLM track: which `prompts/ftl_agent_<v>.md` manual to use |
| `--suite PATH` | suite file (default `scenarios/suite_v1.json`) |
| `--tier TIER` | filter: `public`, `semi_private`, … |
| `--type TYPE` | filter by scenario type |
| `--max-instances N` | cap the number of instances |
| `--budget-cap N` | cap each instance's jump budget (faster smoke runs) |
| `--retries N` | give the agent up to N extra tries per instance on the **same seed**, handing it the prior attempts so it can learn from its mistakes (best try scored; see [Bring your model](/evaluate/bring-your-model/)) |
| `--mode {gameover,budget}` | LLM track: **`gameover` (default)** plays a full game to win-or-die (ignores the jump budget; ends on a real win/death or a stall — see [Play-to-game-over](/reference/play-to-gameover/)); `budget` plays a bounded probe within the jump budget. The headline (FTL run score) is the same in both; the mode is recorded in the manifest and agent label so runs never get conflated. |
| `--play-to-gameover` | deprecated alias for `--mode gameover` (gameover is now the default) |
| `--stall-limit N` | gameover mode: end as a loss after N turns with no progress (default 10) |
| `--out DIR` | output directory (default `runs/benchmark`) |

## Output

Per instance you get a `Score` plus the sub-objective breakdown, then the aggregate:

```
== RESULTS ==
  FTL score 184 ± 31  |  Solve 1/7
  solve_pct: 35.7
  median_jumps_per_instance: 6
  by_type: {"survive_n_jumps": {...}, "reach_sector": {...}, ...}
  by_tier: {"public": {...}}
```

`FTL score` (the mean of FTL's native run score) is the headline
([How scoring works](/introduction/scoring/)). `Solve N/M` is the strict count of instances that
achieved the goal (the win, for full games). The per-type and per-tier breakdowns show where an
agent is strong or weak.

With `--retries N` the results also include a **learning curve**: for each attempt budget k, the
best-so-far mean and median FTL score and the cumulative solve rate (`solve@1 -> solve@k`), and the
headline is labeled `[best of up to N tries]`.

## What gets written

Under `--out` (default `runs/benchmark/`):

- `<instance>.jsonl`: the full trajectory (each decision, the action, the resulting state).
- a per-agent `summary_<label>.json` with the aggregate.
- a reproducibility **manifest** per instance: seed, ship, schema version, runner and agent
  version, and for the LLM track the model, backend, and prompt version.

The agent label encodes the configuration, for example
`llm-anthropic-claude-sonnet-4-6-v3`, so different models, backends, prompts, and modes never get
silently mixed.

## Reporting a number

Run the held-out tier for the comparable figure:

```bash
python3 adapter/run_benchmark.py --agent llm --backend <yours> --model <id> --tier semi_private
```

Tune against `public`, report `semi_private`. Keep the prompt manual fixed (`--prompt-version v3`)
so your number reflects the model, not prompt drift.
