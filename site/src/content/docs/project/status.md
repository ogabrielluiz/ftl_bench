---
title: Results and baselines
description: Current ftl_bench status, verified capabilities, baseline rows, and open benchmark work.
---

## Current state

The benchmark loop runs end to end: an agent can start a seeded run, observe the
game, issue commands, advance the paused simulation, record a trajectory, and
produce aggregate scores.

Verified capabilities:

- observation stream and pause-gated `reset / observe / step` loop;
- combat, events, jumping, sector transition, stores, and game-over detection;
- full action set: power, crew, fire, beam, jump, event, leave, cloak, battery,
  hack, drones, boarding, mind control, doors, buy, sell, and upgrade;
- scripted and random baselines through the same runner;
- LLM track with Anthropic API, Claude CLI, and Codex CLI backends;
- v5 paused multi-action plans with `advance`;
- explicit terminal `giveup` action, recorded as unsolved `gave_up` telemetry;
- compact observations with `broken` / `repair_room`, room oxygen/fire state,
  door topology, richer enemy crew, and best-effort event/flagship metadata;
- play-to-game-over mode with a stall guard;
- trajectory JSONL, summary JSON, and reproducibility manifests.

## Recommended platform

Native Windows x86 through Steam is the recommended path for reportable long
runs. The runner launches FTL through Steam so Hyperspace injects correctly.

WSL can drive the Windows game if `FTL_SAVE_DIR` points at the Windows FTL user
folder. macOS/Rosetta is useful for short development runs but remains secondary
for long trajectories because it can hit an address-translation freeze class.

## Current public floor

Native Windows + Steam, 12-instance `suite_v1`, scripted heuristic floor:

| Agent | FTL score | Solve | survive_n_jumps | reach_sector | reach_sector_healthy | full_run |
|---|---:|---:|---:|---:|---:|---:|
| `scripted` | 143.75 +/- 13.05 | 3/12 | 133.3 | 124.0 | 195.0 | 157.5 |

Median jumps per instance: 11. Public tier: 142.9. Held-out
`semi_private` tier: 145.0.

## Rows still needed

| Row | Why it matters |
|---|---|
| `random` on native Windows | Legal-action floor for the current native setup. |
| `scripted` on `full_game.json` | Baseline for the pure play-the-game track. |
| Frontier LLMs on `full_game.json` | Main comparison rows. |
| Human references | Validate instance quality and anchor efficiency. |

## Reporting notes

- Tune against `public`; report `semi_private`.
- Keep `--prompt-version` fixed within a comparison set. Use `v5` for new rows unless you are
  reproducing an older `v4` result.
- Treat `--retries N` as a separate benchmark condition.
- Include suite path, tier, mode, prompt version, backend, model, commit hash,
  and summary JSON path with every result.

See [Benchmark protocol](/introduction/protocol/) for the canonical reporting
contract.
