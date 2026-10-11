---
title: Running and results
description: CLI options, unique runs, lifecycle outcomes, manifests and offline reports.
---

Use `ftlbench run --help` for all options. From a checkout, prefix it with `uv run --directory harness`.

| Option | Meaning |
|---|---|
| `--agent scripted|random|llm` | Shared runner/scorer with different policies |
| `--backend anthropic|openai|jev|claude-cli|codex` | Model integration |
| `--model` | Explicit provider model identity |
| `--env-file` | Explicit credential file; e.g. `C:\Projects\.env.txt` |
| `--suite`, `--tier`, `--type` | Scenario selection; default mixed `suite_v1.json` |
| `--mode gameover|budget` | Full-game outcome or bounded jump probe |
| `--stall-limit` | Consecutive unchanged turns allowed; charging/recovery are progress |
| `--budget-cap`, `--max-instances` | Development bounds |
| `--prompt-version v5` | Versioned model interface manual |
| `--retries N` | N extra same-seed tries, reported separately |
| `--out` | Parent directory; each invocation gets a unique child |

Only Kestrel A/easy is supported. After reset, actual seed/blueprint/difficulty and native capabilities must match before an agent acts.

## Results and outcomes

Native FTL score is reported alongside goal progress and solve count. Full-run solve requires explicit native victory. Concession, stalled runs, model/transport errors and interruption remain unsolved. Real loss is a completed game outcome, not an infrastructure error.

Attempts keep the last valid observation and a terminal `end` record with status/reason/error. A missing terminal record is incomplete; the dashboard does not call it a completed attempt.

## Files and provenance

Under the unique run directory:

- `run.json`: invocation identity, configuration, active/final lifecycle status;
- JSONL trajectory per scenario/attempt, with metadata, actions, observations, model telemetry and terminal record;
- `summary_<agent-label>.json`: aggregate, per-instance and retry results.

Manifests record requested and verified setup, suite/scenario, prompt/model/backend/mode/retries, protocol, installed DLL and Lua bridge hashes, and native build provenance. Prompt content is hashed so edits remain identifiable within a named version.

Jev rows additionally identify `jev-actuator-choice-v1`; provider telemetry includes request/usage/latency information where returned. Secrets are never recorded.

```powershell
ftlbench report <run-directory>
ftlbench report <run-directory> --json --output report.json
ftlbench dashboard --runs <output-parent>
```

Offline reports and the dashboard read saved data and never send game commands.

## Comparability

Use `semi_private` for reported rows and `public` for tuning. Keep suite, mode, prompt, native artifacts, backend action-selection contract and retries aligned. Record date/commit and the summary path.

**Ruleset v7 requires `owned-player-crew-v1` and `native-economy-and-fuel-recovery-v1`. Pre-v7 scores are not comparable.** Diagnostic traces retain score/progress but do not enter model comparison metrics. Historical Sol 329 and Jev 59 are not current ranking rows.
