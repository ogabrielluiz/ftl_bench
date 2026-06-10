# ftl_bench

`ftl_bench` is an agent benchmark for long-horizon control in
**FTL: Faster Than Light**. It lets a model play the real game through a
paused, intent-level interface, then scores the resulting run with FTL's own
native score plus solve/win rate and reproducibility metadata.

The benchmark is built on [FTL-Hyperspace](https://github.com/FTL-Hyperspace/FTL-Hyperspace).
The game stays paused while the agent reasons, the agent receives a structured
JSON observation, and it returns a short action plan: power systems, move crew,
target weapons, resolve events, jump, buy, sell, board, cloak, hack, and finally
advance the clock.

[Docs](https://ogabrielluiz.github.io/ftl_bench/) |
[Benchmark protocol](https://ogabrielluiz.github.io/ftl_bench/introduction/protocol/) |
[Quickstart](https://ogabrielluiz.github.io/ftl_bench/evaluate/quickstart/)

## Why this benchmark

FTL is a compact but unforgiving agent environment. A good run requires tactical
combat, resource allocation, recovery from damage, risk management, and planning
across a branching map toward the rebel flagship. The agent cannot solve it with
a single policy template: it has to read the current state, preserve the ship,
choose fights, spend scrap, and recover when the run goes sideways.

`ftl_bench` turns that into a reproducible evaluation:

| Benchmark property | What it means here |
|---|---|
| Real game dynamics | Runs use the actual FTL engine and seeded game state, not a toy simulator. |
| Decision-complete observations | The agent sees structured ship, enemy, crew, system, weapon, event, store, and map state. |
| Paused multi-action turns | The agent can issue a whole paused plan, then advance time, like a strong human player. |
| Reportable scores | Headline metric is FTL's native run score, with solve/win rate and seed standard error. |
| Anti-memorization split | Public seeds are for tuning; `semi_private` seeds are the reportable number. |
| Full trajectories | Every run writes the actions, outcomes, manifest, seed, model, backend, prompt version, and mode. |

## Agent loop

Each turn follows the same contract for baselines and models:

```text
observe JSON state
  -> model returns an ACTION block
  -> harness applies commands while paused
  -> advance N frames
  -> bridge re-pauses on the next decision point
  -> score the trajectory
```

Example v5 model reply:

```text
I need weapons online, crew repairing oxygen, and the enemy weapons suppressed.
ACTION:
  power 3 3
  crew 1 2
  fire 0 3
  fire 1 3
  advance 150
```

The agent decides everything in game. The harness does not choose targets, flee,
repair, navigate, spend scrap, or script strategy.

## Benchmark protocol

An **instance** is a seeded FTL setup: `(seed, ship, difficulty, tier, goal)`.
The seed pins the map and events. The current repository includes:

- `scenarios/full_game.json`: the pure play-the-game track. The objective is to
  win FTL by beating the flagship; scoring measures how far the run gets.
- `scenarios/suite_v1.json`: a mixed suite of reproducible probes and full-run
  progress instances, useful for fast baselines and interface development.

Reported metrics:

- **FTL score**: mean native FTL run score over the suite, with seed standard
  error.
- **Solve / win rate**: fraction of instances that meet the scenario goal. For
  full-game runs, this is the flagship win.
- **Efficiency**: jumps or turns per instance.
- **Breakdowns**: per type and per tier.

See the docs for the full [benchmark protocol](https://ogabrielluiz.github.io/ftl_bench/introduction/protocol/)
and [scoring model](https://ogabrielluiz.github.io/ftl_bench/introduction/scoring/).

## Quickstart

Install FTL through Steam, install the bench Hyperspace mod, then run from the
repository checkout. Native Windows is the recommended platform.

```bash
# smoke test the scripted floor
cd harness
uv run python ../adapter/run_benchmark.py --agent scripted --max-instances 1 --budget-cap 8

# random legal-move floor
uv run python ../adapter/run_benchmark.py --agent random --max-instances 1 --budget-cap 8

# Anthropic API backend
uv run python ../adapter/run_benchmark.py --agent llm --backend anthropic --model claude-sonnet-4-6

# Local Claude CLI backend
uv run python ../adapter/run_benchmark.py --agent llm --backend claude-cli --model sonnet

# Local Codex CLI backend
uv run python ../adapter/run_benchmark.py --agent llm --backend codex --model gpt-5
```

For the pure full-game track, point the runner at `full_game.json`:

```bash
uv run python ../adapter/run_benchmark.py \
  --agent llm \
  --backend <anthropic|claude-cli|codex> \
  --model <model-id> \
  --suite ../scenarios/full_game.json \
  --tier semi_private
```

Output includes per-instance `ftl_score`, a breakdown, and an aggregate line:

```text
== RESULTS ==
  FTL score 184 +/- 31  |  Solve 1/7
```

Trajectories and manifests are written under `runs/benchmark/`.

## Live dashboard

The benchmark runner writes JSONL trajectories as it plays. A read-only
dashboard can follow the newest trajectory, inspect prior attempts, and collapse
repeated recovery/stabilization turns into one summarized decision block.

```bash
# build the React UI once
cd dashboard
npm install
npm run build

# serve it from the read-only FastAPI process
cd ../harness
uv run --extra dashboard python ../adapter/ftl_live.py
```

Open <http://127.0.0.1:8765>. If a dashboard server is already running on that
port, restart it after rebuilding the UI or editing `adapter/ftl_live.py`.

The dashboard surfaces hull, oxygen, crew health, enemy hull, resources, system
power, aggregate progress, run metadata, exact action parameters, and grouped
decision loops. It does not send actions to the game.

## Current baseline

Native Windows + Steam, 12-instance `suite_v1`, scripted heuristic floor:

| Agent | FTL score | Solve | survive_n_jumps | reach_sector | reach_sector_healthy | full_run |
|---|---:|---:|---:|---:|---:|---:|
| `scripted` | 143.75 +/- 13.05 | 3/12 | 133.3 | 124.0 | 195.0 | 157.5 |

Median jumps per instance: 11. Public tier: 142.9. Held-out
`semi_private` tier: 145.0. The next public rows to fill are the native
`random` floor and comparable frontier-model runs over the same protocol.

## Repository map

| Path | Purpose |
|---|---|
| `mod/ftl_bench_bridge/` | In-game Hyperspace Lua bridge: observations, actions, pause gating. |
| `harness/` | Python environment, scenario loading, scoring, aggregation, trajectories. |
| `adapter/` | CLI, benchmark runner, scripted/random baselines, LLM backends. |
| `dashboard/` | React/Vite live dashboard served by `adapter/ftl_live.py`. |
| `prompts/` | Versioned agent interface manuals. `v5` is the current multi-action contract. |
| `scenarios/` | Seeded benchmark suites. |
| `site/` | Astro Starlight documentation site. |
| `docs/deepdive/` | Source-grounded notes on Hyperspace and engine integration. |

## Architecture

```text
Model or agent
  reads compact JSON observations
  writes paused action plans
        |
adapter/
  play_cli.py, llm_agent.py, run_benchmark.py
        |
harness/
  AgentSession, reset/observe/step, scoring, manifests
        |
mod/ftl_bench_bridge/
  Hyperspace Lua bridge inside FTL
        |
FTL engine
```

The bridge keeps the game paused by default and advances it only when the
agent asks. It stops early on important events, such as combat starting,
damage, boarders, fire, event popups, or other decision points.

## Platform notes

- **Native Windows x86 is recommended.** The runner launches FTL through Steam,
  which is required for Hyperspace injection.
- **WSL can drive the Windows game** if `FTL_SAVE_DIR` points at the Windows FTL
  user folder.
- **macOS/Rosetta works for short runs**, but full-length runs can hit a
  Rosetta-specific freeze class. Use native Windows for reportable long runs.

## Known gaps

- The full-game track needs more public reference rows: random, scripted,
  frontier LLMs, and human runs.
- Micro-encounter scenarios for combat, crisis escape, events, stores, and
  flagship-specific play are planned for higher signal-per-token evaluation.
- macOS/Rosetta remains a secondary path because native Windows is more stable
  for long trajectories.
