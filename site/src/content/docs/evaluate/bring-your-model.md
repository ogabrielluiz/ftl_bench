---
title: Bring your model or agent
description: The integration contract for evaluating your own model or agent on ftl_bench.
---

There are two ways to put your system on the benchmark. Pick the one that matches how much of the
loop you want to own.

## Option A: bring a model (recommended)

Reuse the built-in agent loop and just supply how your model answers a turn. The loop handles the
prompt, the observation, the rolling history, parsing the reply, and dispatching the action, so
your results stay comparable to everyone else's.

A backend is one function with this contract:

```python
def complete(system: str, user: str) -> str:
    """Given the system prompt (the operating manual + objective) and the user turn
    (the observation + recent history), return the model's reply as text.
    The reply must end with a line:  ACTION: <command>
    """
```

The reference backends live in `adapter/llm_agent.py`:

- `anthropic_complete(system, user, model)`: Anthropic Messages API over plain `urllib`, no SDK.
- `claude_cli_complete(system, user, model)`: shells out to a local `claude -p`.

To add yours, write a function with the same shape (call your provider or local model), then wire
it into the backend dispatch in `make_llm_agent`:

```python
# adapter/llm_agent.py
def my_model_complete(system: str, user: str, model: str | None) -> str:
    text = call_my_model(system_prompt=system, user_prompt=user, model=model)
    return text  # must contain an `ACTION: <command>` line

# in make_llm_agent(...)'s complete():
if backend == "my-model":
    return my_model_complete(system, user, model)
```

Then run it:

```bash
python3 adapter/run_benchmark.py --agent llm --backend my-model --model <your-model-id>
```

What the loop gives your model each turn:

- a **system prompt**: the version-controlled operating manual (`prompts/ftl_agent_<v>.md`,
  selected with `--prompt-version`) plus the objective.
- a **user turn**: the decision-complete [observation](/reference/observation/) and a short rolling
  history of recent actions.

What it expects back: one short reasoning line, then a final `ACTION: <command>` line. Parsing is
lenient (it will salvage a bare command that starts with a known verb), but `ACTION:` is the
contract.

:::note[Keep the manual fixed for comparable results]
The prompt manual is part of the agent's identity. The version is recorded in the run manifest and
the agent label, so a manual change is a distinct, non-comparable agent rather than silent drift.
Use the shipped `prompts/ftl_agent_v3.md` (interface-only) to compare against others.
:::

## Option B: bring a whole agent

If you want to own the loop (your own prompting, memory, tools, multi-step reasoning), drive the
environment directly. Each turn is one observation in, one command out.

- **`adapter/play_cli.py`**: a thin turn-based CLI. `play_cli.py obs` prints the decision-complete
  observation; `play_cli.py <command>` applies one action and returns the next observation. Your
  agent can shell these, or import `apply_command` and `compact` directly.
- **`harness/src/ftl_bench/session.py`** (`AgentSession`): the Python env API
  (`reset_episode(seed)`, `observe()`, `step(actions, advance_frames)`, plus helpers like `jump`,
  `fire_weapon`, `leave_sector`). This is what the runner and the LLM track are built on.

The action semantics are shared between the CLI and the LLM track (one `apply_command`), so
whichever surface you build on, the game behaves identically.

To get scored, record your run as a trajectory the same way the runner does (see
`adapter/run_benchmark.py` and `harness/src/ftl_bench/{trajectory,scoring}.py`), or run your agent
through the runner's `agent_fn(sess, scenario, log)` hook so scoring and aggregation happen for
free.

See the [Observation schema](/reference/observation/) and [Action set](/reference/actions/) for
exactly what you read and what you can send.
