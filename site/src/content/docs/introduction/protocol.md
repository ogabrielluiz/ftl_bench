---
title: Benchmark protocol
description: Suites, verified setup, native protocol, run modes and comparable reporting.
---

The environment runs the real FTL engine. Agents decide policy through paused observation/action turns; the harness applies commands, records outcomes and scores observed evidence.

## Supported setup and native protocol

The automatic setup is **Kestrel A on easy**. Other ships/difficulties are rejected. After reset, the runner checks the actual seed, `PLAYER_SHIP_HARD` blueprint and difficulty `0`.

Native protocol **5** is required: reliable manual weapon control, setup and victory/score getters, plus exact system/reactor upgrades and native out-of-fuel recovery. The runner checks native and Lua capabilities; full-run scenarios require victory reporting. See [PC installation](/install/pc/) for the checked patch and provenance.

Runner/ruleset **v7** also requires Lua `crew_control_guard` and `crew_ownership` capabilities. The `owned-player-crew-v1` contract exposes only player-owned crew, preserves their original native IDs and rejects movement when native controllability or positive health is absent. Own boarders retain player ownership; hostile boarders are separate intruders. Applied/rejected crew moves include explicit feedback.

`native-economy-and-fuel-recovery-v1` requires `upgrade_rules` and `fuel_recovery`. Upgrade prices, caps, affordability and UI legality come from the game. Missing cost is unknown/unavailable, never free. `waitfuel` requests the native Wait turn, including normal encounters/fleet movement; a following advance resolves it. `distress on|off` uses the native toggle. Frame waits alone do not request recovery or guarantee fuel.

`native-sector-neighbors-v1` requires `economy.sector_navigation_version: 1` and Lua `sector_navigation: true`. Native sector exit selects an actual neighboring-sector vector index; sector type values are not route indices. Acceptance/refusal remains explicit, and travel credit still requires observed movement. The API protocol remains 5, so the routing marker must also be verified.

`native-beacon-readiness-v1` also requires `economy.beacon_navigation_version: 1` and Lua `beacon_navigation: true`. Ordinary jumps and sector exit obey native button, full FTL timer, system, fuel and context readiness; a destroyed flag alone does not authorize travel. Rejections report explicit feedback, and charged combat fleeing retains normal native legality. `economy.navigation.can_jump` is authoritative. `enemy_defeat_pending` signals possible unprocessed defeat/rewards; it does not prohibit an otherwise legal charged jump. Continuing normal simulation lets cleanup/rewards resolve, while jumping away can forgo them.

`native-enemy-hostility-v1` requires Lua `enemy_hostility: true`. A surrendered ship can retain positive hull, weapons and a native ship pointer; combat and targeting use the native `_targetable.hostile` flag. Non-hostile, destroyed, jumping or unknown-state enemy targets reject enemy-directed weapon requests and clear queued enemy fire. Dispatch feedback records `enemy_hostile`, `enemy_targetable` and accepted queue state. `targetable` and compact `active` never become true from hull or equipment alone. Friendly ships do not independently block a charged native-legal sector exit.

Event observations include native choice availability and keyboard timing/settings. Type 1 is disabled. The bridge preserves input delay and refuses requests while another choice is pending; applied feedback proves queued native selection, not a completed event branch.

## Suites and modes

| Suite / mode | Purpose |
|---|---|
| `scenarios/full_game.json` | Full-game track: win FTL; progress toward eight sectors plus three completed flagship phases |
| `scenarios/suite_v1.json` | Default mixed probe suite for survival, sector reach and full-run progress |
| `--mode gameover` | Canonical full-game mode: continue beyond jump budget until victory, loss, stall or safety cap |
| `--mode budget` | Bounded jump-budget probe; report separately from full-game rows |

All agent modes use the same scorer. A budget stop is not a win. A stall, concession, model/transport error or interruption stays unsolved even if partial progress was achieved.

## Agent contract

The v5 interface manual describes observations and actuators without prescribing strategy. Each turn supplies the manual, objective, compact state and recent history. Text backends return a brief reason and a paused plan:

```text
ACTION:
  power 3 3
  crew 1 2
  fire 0 3
  advance 150
```

Plans have at most 12 commands and one bounded advance. Each fire/beam command queues one release, including a charging weapon. `giveup` must stand alone and records an unsolved harness concession.

The OpenAI Responses backend generates the equivalent strict JSON plan. Jev uses the distinct `jev-actuator-choice-v1` contract: independent typed choices over observed actuator settings, at most 255 options per question and 12 commands per plan. Report this contract with its rows.

## Scoring and reporting

FTL's native score is reported alongside strict goal solve rate and partial progress. Full-run solve requires explicit native `victory: true`. Raw flagship phase/stage counters and ordinary game over do not prove victory. The current bridge confirms the completed three phases at victory, without guessing intermediate completion.

Travel credit requires observed beacon/sector transitions; rejected jumps and resets earn none. **Pre-v7 rows are not comparable.** V7 retains the corrected crew/economy/routing/beacon boundaries and adds native enemy hostility. The preceding v6 trial was stopped after accepted surrender left a friendly ship marked targetable. The preceding v5 trial was stopped after ordinary jumps bypassed native charging and enemy-death reward cleanup. The preceding v4 trial was stopped after a sector type/index mismatch and is diagnostic. Sol's v3 fuel-zero concession at score 329 is diagnostic because that interface lacked complete event/economy/recovery controls. Earlier Jev score 59 remains historical v2 score/reset evidence.

Use `public` for development and `semi_private` for held-out reports. Identify runner/ruleset, control/economy/routing/beacon/hostility contracts, suite, tier, mode, backend/model/decision contract, prompt/hash, retries, date/commit, native DLL/bridge hashes, setup and outcome artifacts. Retry rows are separate conditions and retain every attempt. Diagnostic runs retain evidence but are excluded from comparison metrics.

Each invocation creates a unique directory under `--out`, containing run metadata, JSONL attempt trajectories, terminal records and summary JSON. Failed attempts remain visible with their last valid state and error reason.

```powershell
ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend openai --model <model-id> --suite <full_game.json-path> --tier semi_private --mode gameover --prompt-version v5
```

See [scoring](/introduction/scoring/) and [running/results](/evaluate/running/).
