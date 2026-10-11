# ftl-bench

A Python harness and command line for agents playing the real **FTL: Faster Than Light** engine through paused multi-action turns. Requires Python 3.11+ and a separately installed FTL/Hyperspace benchmark environment.

The supported setup is Kestrel A on easy. The runner verifies the actual seed, blueprint and difficulty after reset and rejects unsupported requests. Full-game evaluation requires native protocol 5, explicit autofire control, and the authoritative victory binding.

Runner/ruleset v7 retains Lua `crew_control_guard` and `crew_ownership` capabilities under `owned-player-crew-v1`, and adds `native-economy-and-fuel-recovery-v1` with `upgrade_rules` and `fuel_recovery`. Crew IDs stay native; hostile, uncontrollable and nonliving movement requests are rejected. Own boarding crew retain player ownership.

## Install and check

```powershell
pip install "ftl-bench[dashboard]"
ftlbench version
ftlbench doctor
ftlbench deploy-bridge
# Launch the patched game through Steam first
ftlbench doctor --live --full-game
ftlbench play obs
```

The package includes suites, prompts, adapters, the Lua bridge, checked native patch, setup helpers and compiled read-only dashboard. FTL and Hyperspace.dll are installed separately. From a checkout, use `scripts/setup_pc.sh` for the Windows source build/install; it applies the native patch before building. `install-mod --url` only downloads a supplied asset and is not a complete native game installer.

With FTL closed and the loader/data mods already installed, `ftlbench install-native --dll <built.dll> --manifest <native-build.json> --game-dir <FTL-directory>` verifies the local DLL/provenance and backs up replaced artifacts. The live doctor requires reliable setup, current-run score and `sector_navigation` capabilities as well as protocol 5 controls; full-game checks also require native victory reporting.

Structured protocol-5 artifacts are `dist/Hyperspace.protocol5.dll` and `dist/native-build.protocol5.json`. The current visual build uses `dist/Hyperspace.visual-v1.dll` and `dist/native-build.visual-v1.json`, with clock 2 and fresh-start seed contract v3. Install the build required by the selected track; visual startup rejects an older native provenance contract. The package includes the complete source patch and archived protocol-4 manifest/patch. Archived native binaries/provenance remain separate historical artifacts.

`doctor` never calls a model or modifies the installation. `deploy-bridge` backs up an existing external Lua script before replacing it.

## Run

```powershell
ftlbench run --agent scripted --mode budget --max-instances 1 --budget-cap 3
$fullSuite = python -c "from ftl_bench.cli import _bench_root; print(_bench_root() / 'scenarios' / 'full_game.json')"
ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend openai --model <model-id> --suite $fullSuite --mode gameover
ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend jev --model jev-1.13.0 --suite $fullSuite --mode gameover
ftlbench dashboard --runs runs/benchmark
```

Backends: `anthropic` (`ANTHROPIC_API_KEY`), `openai` (`OPENAI_API_KEY`, public Responses), `jev` (`TYPESAFE_API_KEY`, typed actuator choices), `claude-cli` and `codex` (local authenticated CLIs). Environment files must be selected explicitly; their contents are not executed or printed.

`ftlbench run --help` lists suite, tier, mode, retry and output options. Source checkout runs use the repository suites; an installed package uses its bundled suites. Each invocation creates a unique output directory, retaining all attempt trajectories and terminal errors. A full-run solve requires explicit native victory evidence.

The example resolves the packaged full-game suite explicitly. From a checkout with `uv run --directory harness`, use `--suite ../scenarios/full_game.json`. Mode `gameover` alone does not select that suite.

Recompute a saved run without game or model calls using `ftlbench report <run-dir> [--json] [--output <path>] [--legacy-suite <path>]`. Errors remain visible alongside completed attempts. Native scores tagged `native_live_v1` use the current run's counters, without a saved high-score fallback.

## Visual runs through Codex CLI

Close FTL before these protected runs and use a new output directory. Codex CLI must already be authenticated; `CODEX_BIN` can select its executable.

```powershell
ftlbench visual --model gpt-6.1-sol --mode image --seed 1 --reasoning-effort medium --max-decisions 300 --max-wall-seconds 14400 --output runs/visual/sol-image-001
ftlbench visual --model gpt-6-luna --mode hybrid --seed 1 --reasoning-effort medium --max-decisions 300 --max-wall-seconds 14400 --output runs/visual/luna-hybrid-001
ftlbench dashboard --runs runs/visual
```

Visual startup always sends an explicit native opt-in for `fresh-start-seed-v3`; there is no additional CLI flag or silent legacy fallback. The runner requires matching installed DLL/provenance, native protocol 5, clock 2 at 1/60 second and exact v3 startup receipts. It starts Kestrel A/easy without a challenge fixture or backstage gameplay. The first archived PNG retains the opening intro for the actor and is recorded before admission validation. Image mode supplies that image and input history; hybrid adds only conservatively transcribed HUD values from the same PNG.

Startup refusal makes zero model calls and preserves `fresh-setup/setup-session.json`, available `fresh-setup/admission.json`, the first image when captured, and terminal/restoration receipts. Protected saves and the external bridge are restored on exit; cleanup failure remains visible. The accepted nine-probe checks and startup-only smoke cover finite measured behavior, not a completed full game or proof of general full-game reproducibility. Ordinary visual attempts remain diagnostic until the separate comparison audit accepts them. Full visual controls, budgets and historical evidence are described in `docs/visual-iteration.md` in the checkout.

Ruleset v7 requires `native-sector-neighbors-v1` alongside exact native upgrades/fuel recovery, owned player survival and verified wins. `economy.sector_navigation_version: 1` plus Lua `sector_navigation: true` confirms the corrected neighboring-sector index contract; a rejected leave is reported explicitly. `native-beacon-readiness-v1` also requires `economy.beacon_navigation_version: 1` and `beacon_navigation: true`; ordinary jumps and sector exit respect native travel readiness; pending enemy defeat is guidance, not an extra eligibility gate. Protocol 5 without both markers is insufficient. `upgrade`, `reactor`, `waitfuel` and `distress on|off` report native acceptance/refusal. `waitfuel` is an actual recovery turn with normal encounter/fleet consequences; ordinary frame waits do not replace it. Native nullable costs/reactor can be omitted in Lua observations; absent cost is unknown, not free.

`native-enemy-hostility-v1` requires Lua `enemy_hostility: true`. A surrendered ship can retain positive hull, weapons and a native ship pointer; combat and targeting use the native `_targetable.hostile` flag. Non-hostile, destroyed, jumping or unknown-state enemy targets reject enemy-directed weapon requests and clear queued enemy fire. Dispatch feedback records `enemy_hostile`, `enemy_targetable` and accepted queue state. `targetable` and compact `active` never become true from hull or equipment alone. Friendly ships do not independently block a charged native-legal sector exit.

Pre-v7 rows are not comparable. V5 was stopped after ordinary jumps bypassed native readiness and enemy-death cleanup. The prior v4 trial was stopped after an incorrect sector type/index mapping. The v3 Sol score 329 is diagnostic because that interface still used approximate upgrades and lacked recovery/event availability; the earlier Jev score 59 remains v2 history. Compare the same suite, tier, mode, prompt, control/economy/routing/beacon/hostility contracts, backend/action-selection contract and retry count.

For a development checkout:

```powershell
uv sync --extra dev --extra dashboard
uv run pytest -q
```

The tests include actual Lua 5.3 execution through Lupa. Game runs also need the live bridge and protocol-5 native build; tests alone do not establish runtime installation health.

Full installation and reporting documentation: https://github.com/ogabrielluiz/ftl_bench
