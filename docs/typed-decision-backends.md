# Typed decision backends

## Select a backend

| Backend | Structured `ftlbench run --agent llm` | `ftlbench visual` | Authentication |
| --- | --- | --- | --- |
| `codex` | Codex CLI action plans | Default visual backend, `gpt-6.1-sol` | Authenticated Codex CLI |
| `openai` | OpenAI Responses with a strict plan schema | — | `OPENAI_API_KEY` |
| `openai-decisions` | Observed actuator Choices, `gpt-6-luna` | Typed screenshot Choices, `gpt-6-luna` | `OPENAI_API_KEY` |
| `jev` | Observed actuator Choices, defaults to `jev-1.13.0` | Typed screenshot Choices, defaults to `jev-1.14.0` | `TYPESAFE_API_KEY` or `JEV_API_KEY` |

OpenAI made `POST /v1/decisions` generally available on October 22, 2026.
Its only supported model is `gpt-6-luna`. The Responses integration uses a
separate endpoint and contract. [OpenAI changelog](https://developers.openai.com/api/docs/changelog#oct-22) ·
[Decisions API reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)

Jev uses TypeSafe System One. Its visual requests include the experimental
`TypeSafe-Danger-Zone-Images: true` header and attach the exact PNG as an image
asset. [TypeSafe models](https://docs.typesafe.ai/models) ·
[System One API reference](https://docs.typesafe.ai/api/system-one)

Set the selected provider's key in the process environment or pass
`ftlbench --env-file "<credential-file>" ...`. The file uses literal
`KEY=value` lines. Existing process values take precedence. Keep keys outside
the repository and all task, history and screenshot inputs.

## Try one screenshot

Use a PNG you intend to send to the selected provider and an output directory
that does not exist. Substitute the placeholders with your own paths.

```powershell
ftlbench --env-file "<credential-file>" visual-decide --backend openai-decisions --image "<archived-png>" --output "<new-directory>"
ftlbench --env-file "<credential-file>" visual-decide --backend jev --image "<archived-png>" --output "<different-new-directory>"
```

From a checkout, prefix the command with `uv run --directory harness`.
The probe sends the screenshot to the API, saves and audits one complete
decision, then prints its proposed input and output path. It neither opens
FTL nor dispatches the input. `--task` supplies a specific objective, and
`--model` overrides the selected backend's default where supported.

## Run a diagnostic

With the native visual runtime installed and FTL closed, the standalone visual
runner can apply typed decisions under the protected save lifecycle.

```powershell
ftlbench --env-file "<credential-file>" visual --backend openai-decisions --mode image --seed 1 --max-decisions 1 --output "<new-directory>"
```

Use `--backend jev` for the same visual contract. `--reasoning-effort` and
`--experiment-file` apply to Codex only. Image mode supplies the archived PNG,
the task and permitted history. Hybrid mode adds conservative HUD readings
from that PNG. The native evaluator state stays outside the actor input.

The structured backend uses compact observations and emits a paused action plan.

```powershell
ftlbench --env-file "<credential-file>" run --agent llm --backend openai-decisions --model gpt-6-luna
```

The structured `openai-decisions-actuator-choice-v1` and
`jev-actuator-choice-v1` contracts ask independent questions over available
actuators, then render the chosen commands and advance interval. Shared safety
checks enforce the 12-command plan limit and require a concession to stand
alone. OpenAI Decisions accepts up to 400 questions, with 2–255 options per
Choice. If only one beam endpoint is legal, the adapter records it as fixed
and sends no question for that endpoint. The model still chooses whether to
fire. Structured OpenAI Decisions makes one request per plan.

## Interpret the visual audit

`ftl-visual-typed-choice-v1` first selects a click, pointer move, drag, key
press or wait. Pointer targets are narrowed by successive grids of up to
15 × 15 rectangles on the same screenshot. A drag resolves the start and
destination separately. The final question chooses 0, 1, 30, 60, 120, 300 or
600 frames. The actor emits one primitive at most and keeps the supplied
memory. Each stage makes at most one HTTP attempt. A refusal, invalid choice, transport
failure or missing audit evidence stops the decision before dispatch, with no
retry or provider fallback.

A monotonic deadline covers socket I/O across each stage. The operating
system's synchronous DNS lookup can finish after that deadline, which the
transport checks before connecting. The actor also shares a time budget across
all stages. The live runner withholds typed input if its wall-time budget has
elapsed before dispatch.

Under `api-decisions/decision-*/`, the saved PNG and stage requests allow
offline reconstruction of the submitted JSON. Each stage records request IDs,
the request and response byte identities, latency, reported usage, and the
selected option with its confidence and probability. The archived response
retains the distribution for replay. Failed stages retain bounded failure
evidence. A token total is unknown if any attempted stage omits the relevant
count. The one-screenshot command records its replay result in `probe.json`.

The visual backends have offline contract coverage. Live provider validation
remains pending. The rebuilt native runtime separately passed scoped startup,
timing and local controller admission on November 6; that does not establish
provider compatibility. These diagnostic decisions
are separate from frozen Codex cohorts. Comparing providers requires a
protocol that accounts for action granularity and HTTP requests per decision.
