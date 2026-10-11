# Adapter and agent integrations

The adapter translates compact observations and paused action plans into the shared `AgentSession` contract. `run_benchmark.py` performs seeded setup, records attempts, and scores trajectories; `play_cli.py` exposes individual commands.

## Use the packaged CLI

```powershell
ftlbench doctor --live --full-game
ftlbench play obs
ftlbench run --agent scripted --mode budget --max-instances 1 --budget-cap 3
ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend openai --model <model-id> --mode gameover
ftlbench dashboard
```

From a checkout, prefix these with `uv run --directory harness`. Runs require the patched real game, native protocol 5 and the current Lua bridge. The canonical setup is Kestrel A on easy; other requested settings are rejected and actual setup is checked after reset.

## Visual runs

`run_visual.py` is the production visual entry point behind `ftlbench visual`. Close FTL first and use an authenticated Codex CLI plus the visual DLL/provenance implementing clock 2 and `fresh-start-seed-v3`.

```powershell
ftlbench visual --model gpt-6.1-sol --mode image --seed 1 --reasoning-effort medium --max-decisions 300 --max-wall-seconds 14400 --output runs/visual/sol-image-001
ftlbench visual --model gpt-6-luna --mode hybrid --seed 1 --reasoning-effort medium --max-decisions 300 --max-wall-seconds 14400 --output runs/visual/luna-hybrid-001
```

Visual startup requires v3 by default and sends its explicit native setup packet automatically. `FullGameSetupSession` permits one fresh request and an empty zero-frame capture, with no fixture mutation or structured gameplay before the actor. `run_loop` records the canonical first image before validating admission; the actor then sees that same image with opening intro choices intact. The hidden receipt and packet proofs never enter actor input. The structured runner and its `AgentSession` contract remain unchanged.

Admission refusal stops before model calls and retains setup observations, available admission/image evidence and terminal cause. The existing protected lifecycle restores saves and the external bridge and records any cleanup failure. Measured no-model setup/progression checks do not establish a completed full game, a model ranking or general full-game reproducibility. See `docs/visual-iteration.md` for the complete visual procedure and comparison scope.

## Model backends

| Backend | Contract | Authentication |
|---|---|---|
| `anthropic` | Messages action text | `ANTHROPIC_API_KEY` |
| `openai` | Public Responses strict JSON action plan | `OPENAI_API_KEY` |
| `jev` | `jev-actuator-choice-v1` typed actuator choices | `TYPESAFE_API_KEY` or `JEV_API_KEY` |
| `claude-cli` | Local completion text | Authenticated `claude` |
| `codex` | Local completion text | Authenticated `codex`; optional `CODEX_BIN` |

`--env-file` loads only the selected literal KEY=value file. Jev chooses observed actuator settings independently, with 255 options per question and 12 commands per plan. Bridge rejection remains visible; oversized/invalid provider plans fail instead of being truncated. Its manifest and per-turn telemetry identify the constrained action-selection contract. OpenAI Decisions preview is not implemented; the public Responses backend is a separate integration.

Custom completion functions may return text or `model_backend.Completion(text, metadata)`. Metadata records provider usage, request identity, latency, retries and decision contract without credentials. Model errors finalize the attempt as an error while retaining its last valid game state.

The interface manual is `prompts/ftl_agent_v5.md`. It describes actuators and observations without a strategy policy. A model submits at most 12 paused commands followed by one bounded `advance`; `giveup` must stand alone.

## Other entry points

`baseline_agent.py` implements the scripted floor. It waits for weapon/FTL charging and counts flee/jump/leave only after observed movement. `eval.py` is a development episode runner; use `run_benchmark.py` for reportable suite rows and lifecycle manifests.

The optional MCP server wraps a single live session:

```powershell
uv run --directory harness --with "mcp[cli]" python ../adapter/ftl_mcp_server.py
```

Its tools include observe/reset/jump/event/power/crew/manual fire/advance and agent-authored Python through `run_strategy`. This executes the agent's code locally and should be used only with trusted agents. Direct Python agents can use `AgentSession.observe()`, `reset_episode(seed)` and `step(actions, advance_frames)`.

`ftl_live.py` serves the read-only dashboard. It reads trajectories and summaries, never game actuator files. The packaged dashboard includes compiled UI assets; source changes need a fresh `dashboard` production build before rebuilding the package.

Runner/ruleset v7 retains `owned-player-crew-v1`: compact crew keep native IDs, ownership/location and controllability. Hostile boarders are excluded from player crew/counts; own boarders remain owned. It adds `native-economy-and-fuel-recovery-v1`, requiring protocol 5 and Lua `upgrade_rules`/`fuel_recovery` capabilities. It also requires `native-sector-neighbors-v1`: native economy marker `sector_navigation_version: 1` plus Lua `sector_navigation: true`. `leave` selects an actual neighboring-sector index and propagates native rejection feedback. It also requires `native-beacon-readiness-v1` through `economy.beacon_navigation_version: 1` and `beacon_navigation: true`. Jump/leave rejection remains explicit when native travel readiness is incomplete; charged combat fleeing still uses native legality. `economy.navigation.can_jump` is authoritative. `enemy_defeat_pending` signals possible unprocessed defeat/rewards; it does not prohibit an otherwise legal charged jump. Continuing normal simulation lets cleanup/rewards resolve, while jumping away can forgo them. Pre-v7 trials are historical diagnostics, not current comparison rows.

`upgrade <system_id>` and `reactor` use authoritative native costs, caps, affordability and UI legality. Compact `economy` preserves system/reactor prices and `can_upgrade`; an omitted cost is unknown/unavailable, never zero/free. `waitfuel` queues a native recovery turn, and `distress on|off` controls its distress beacon. Normal frame progression resolves the turn, including encounters and fleet consequences; `wait` only advances frames.

`native-enemy-hostility-v1` requires Lua `enemy_hostility: true`. A surrendered ship can retain positive hull, weapons and a native ship pointer; combat and targeting use the native `_targetable.hostile` flag. Non-hostile, destroyed, jumping or unknown-state enemy targets reject enemy-directed weapon requests and clear queued enemy fire. Dispatch feedback records `enemy_hostile`, `enemy_targetable` and accepted queue state. `targetable` and compact `active` never become true from hull or equipment alone. Friendly ships do not independently block a charged native-legal sector exit.

Event choices preserve native indices and `native_type`, enabled/available/disabled state, native `open_time` and `dialog_keys`. Type 1 is disabled. The bridge keeps native keyboard delay and rejects a second request while selection is pending. `action_feedback` includes event, upgrade and fuel acceptance/refusal; an applied event is queued, not proof its branch finished.
