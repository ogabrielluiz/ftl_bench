---
title: Quickstart
description: Check the local game, run a bounded baseline, then evaluate a model.
---

First install the protocol-5 native dependency and data mod using [PC setup](/install/pc/). With the patched game launched through Steam:

```powershell
uv run --directory harness ftlbench doctor --live --full-game
uv run --directory harness ftlbench play obs
uv run --directory harness ftlbench run --agent scripted --mode budget --max-instances 1 --budget-cap 3
```

These checkout examples run from the repository root; `uv --directory harness` changes the working directory to `harness`. An installed wheel uses `ftlbench` directly.

## Select a model backend

```powershell
# Select your credentials file explicitly
uv run --directory harness ftlbench --env-file "C:\Projects\.env.txt" doctor --backend openai
uv run --directory harness ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend openai --model <model-id> --mode gameover
uv run --directory harness ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend jev --model jev-1.13.0 --mode gameover
```

OpenAI uses `OPENAI_API_KEY` and the public Responses API. Jev uses `TYPESAFE_API_KEY` and typed actuator choices. Anthropic, Claude CLI and Codex CLI are also available. Credentials are not printed; existing environment values take precedence over the explicitly selected file.

## Full-game reporting

```powershell
uv run --directory harness ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend openai --model <model-id> --suite ../scenarios/full_game.json --tier semi_private --mode gameover --prompt-version v5
```

Use `public` while developing. Full-run solve requires native victory evidence. Kestrel A/easy is the verified automatic setup; unsupported ships/difficulties are rejected. Budget probes are separate from full-game rows.

Every invocation creates a unique output directory with run metadata, trajectories, terminal records and summary JSON. Errors and interruptions remain visible. Runner/ruleset v7 requires `owned-player-crew-v1` and `native-economy-and-fuel-recovery-v1`; pre-v7 scores are not comparable.

## Watch a run

```powershell
uv run --directory harness --extra dashboard ftlbench dashboard
```

Open `http://127.0.0.1:8765`. The dashboard is read-only and can browse active or completed attempts. Use `--runs <directory>`, `--suite <path>` and `--port` to select inputs.

See [protocol](/introduction/protocol/) for the reporting contract.
