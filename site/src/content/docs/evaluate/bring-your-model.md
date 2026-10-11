---
title: Bring your model or agent
description: Text, structured-plan and typed-choice integrations through the shared action interface.
---

Use the built-in agent loop for a model row, or `AgentSession` for a custom agent. All integrations act through the same bridge and record the same scoring evidence.

## Built-in backends

| Backend | Contract | Configuration |
|---|---|---|
| `anthropic` | Messages action text | `ANTHROPIC_API_KEY` |
| `openai` | Public Responses strict JSON action plan | `OPENAI_API_KEY` |
| `jev` | Typed Choice over observed actuators | `TYPESAFE_API_KEY` or `JEV_API_KEY` |
| `claude-cli` | Local action text | Authenticated `claude` |
| `codex` | Local action text | Authenticated `codex`; optional `CODEX_BIN` |

```powershell
ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend <backend> --model <model-id> --mode gameover
```

Environment files are loaded only when explicitly selected. No model call is made by `doctor`.

### Jev contract

The separately labeled `jev-actuator-choice-v1` adapter enumerates observed power settings, crew rooms, weapon/beam targets, door operations, special systems, economy and navigation. Each actuator has a hold option; advance is another typed choice. It uses the documented [Choice API](https://docs.typesafe.ai/api).

Questions are independent, so reactor or other actuator selections can conflict. The bridge reports their effects/rejections under the shared semantics. A question has at most 255 options; a plan has at most 12 commands. Invalid answers and oversized plans fail explicitly. This is a constrained action-selection track and must be labeled when comparing rows.

### OpenAI contract

The adapter calls the [public Responses API with structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), generating a strict JSON action plan translated into the same paused commands. OpenAI Decisions preview is not implemented because its schema is unavailable here. Responses support does not imply preview access.

## Custom completion function

```python
from model_backend import Completion

def complete(system: str, user: str, model: str | None):
    return Completion("ACTION:\n  advance 150", {"provider": "my-provider"})
```

Text replies also remain supported. Wire the function into `make_llm_agent` and the runner backend parser. The loop supplies the interface manual, objective, compact JSON and recent action history; handles plans and recording; and finalizes provider errors.

A plan contains at most 12 paused commands followed by advance. `giveup` alone concedes as unsolved. Changing prompting, memory, policy or the action-selection contract defines a different agent row.

## Custom full agent

Use `AgentSession.reset_episode(seed)`, `observe()` and `step(actions, advance_frames)`. A runner hook accepts `agent_fn(sess, scenario, log, attempts=())` and should return terminal metadata such as `{"status": "completed", "reason": "victory"}` or a failed transport reason. Scoring still requires observation evidence; an agent's claimed win does not prove one.

Retry runs can receive prior attempt summaries and are separately labeled. See [actions](/reference/actions/), [observations](/reference/observation/) and [protocol](/introduction/protocol/).
