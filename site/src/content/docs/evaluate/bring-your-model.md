---
title: Bring your model or agent
description: The integration contract for evaluating your own model or agent on ftl_bench.
---

There are two integration paths. Use the built-in LLM loop if you want a
comparable model row. Drive the environment directly if you want to evaluate a
larger custom agent system.

## Option A: bring a model

Reuse the benchmark's agent loop and provide one completion function. The loop
handles the prompt manual, objective, observation, rolling history, response
parsing, dispatch, trajectory logging, and scoring.

The backend contract is:

```python
def complete(system: str, user: str) -> str:
    """Return the model reply for one turn.

    The reply should include brief reasoning and an ACTION block. In v5, the
    ACTION block may contain multiple commands and should end with advance N.
    """
```

Example model reply:

```text
I should stabilize oxygen and suppress the enemy weapons before waiting.
ACTION:
  power 3 3
  crew 1 2
  fire 0 3
  fire 1 3
  advance 150
```

The reference backends live in `adapter/llm_agent.py`:

| Backend | Function | Notes |
|---|---|---|
| `anthropic` | `anthropic_complete(system, user, model)` | Anthropic Messages API over `urllib`; needs `ANTHROPIC_API_KEY`. |
| `claude-cli` | `claude_cli_complete(system, user, model)` | Shells out to local `claude -p`. |
| `codex` | `codex_complete(system, user, model)` | Shells out to local `codex exec`. |

To add a backend, implement the same shape and wire it into `make_llm_agent`:

```python
# adapter/llm_agent.py
def my_model_complete(system: str, user: str, model: str | None) -> str:
    return call_my_model(system_prompt=system, user_prompt=user, model=model)

# in make_llm_agent(...)'s complete():
if backend == "my-model":
    return my_model_complete(system, user, model)
```

Then run:

```bash
cd harness
uv run python ../adapter/run_benchmark.py --agent llm --backend my-model --model <your-model-id>
```

## What the model sees

Each turn includes:

- a **system prompt**: the versioned interface manual
  (`prompts/ftl_agent_v5.md` by default) plus the objective and run rules;
- a **user turn**: the compact [observation](/reference/observation/) and recent
  action history.

The prompt manual is part of the agent identity. If you change it, report a new
row and keep the version in the run label. The manifest records model, backend,
prompt version, suite, mode, and retry count.

## Option B: bring a whole agent

If you want custom prompting, memory, tools, self-critique, planning, or
multi-process orchestration, drive the environment directly. Each loop is still
observation in, action out.

- `adapter/play_cli.py`: turn CLI. `play_cli.py obs` prints the compact
  observation; command invocations apply one action and return the next state.
- `harness/src/ftl_bench/session.py`: Python API via `AgentSession`
  (`reset_episode(seed)`, `observe()`, `step(actions, advance_frames)`, plus
  helpers such as `jump`, `fire_weapon`, and `leave_sector`).
- `adapter/run_benchmark.py`: runner hook. If your agent can be exposed as
  `agent_fn(sess, scenario, log)`, the runner gives you scoring and aggregation
  for free.

The CLI, LLM track, and runner share the same command semantics, so results stay
comparable.

## Retry mode

Run with `--retries N` to give the agent up to `N + 1` tries on the same seed.
Before a retry, the runner passes prior attempts to agents that accept the
`attempts` parameter:

```python
def agent_fn(sess, scenario, log, attempts=()):
    ...
```

Each `Attempt` contains score, solve status, outcome, final state, breakdown,
and a compact transcript. Retry mode scores the best try and reports a solve@k
learning curve. Because this is a different evaluation condition, the agent
label and manifest include `retries=N`.

See [Action set](/reference/actions/) and [Observation schema](/reference/observation/)
for the exact surface.
