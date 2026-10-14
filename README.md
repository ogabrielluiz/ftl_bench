# ftl_bench

An agent benchmark that drives the real **FTL: Faster Than Light** engine through a paused observation/action interface. Agents set power, move crew, target weapons, resolve events, navigate, trade, and advance the clock. The runner records every attempt and reports FTL's native score, goal progress, and verified wins.

[Documentation](https://ogabrielluiz.github.io/ftl_bench/) Â· [Protocol](https://ogabrielluiz.github.io/ftl_bench/introduction/protocol/)

## Status: work in progress

The visual benchmark is an **alpha implementation with partial live validation**.
Future full-game cohorts can declare matched decision, wall-time and idle budgets
at freeze time; defaults remain 300 / 14,400 seconds / 8. See the
[full-game protocol](docs/visual-experiment-protocol.md#full-game-progression).
On 2026-10-14 the operator confirmed Steam sign-in and cancellation of the old
queued launch. A fresh `d430d0e` collection passed eight startup checks, all nine
timing probes, exact save restoration and eight independent rejection probes.
Its scoped controller admission binds 78 executable sources and 565 evidence
files; the original 31 native build/source inputs are explicitly reused, and
`production_accepted` remains false. The historical failed `bb6014b` collection
is preserved separately. See [pending-launch recovery](docs/visual-iteration.md#pending-launch-recovery)
for the durable guard and the limits of operator acknowledgement.

The new `fullgame-main-d430d0e-20261014` cohort freezes matched budgets of
1,500 decisions / 86,400 seconds / 8 idle decisions. Its Sol/image sector pilot
started at 11:24 UTC; this is an in-progress attempt, not a completed full game.
All new Sol conditions precede Luna. Existing failures, budgets and cohorts stay
separate; the earlier 300-decision hybrid stop is not silently resumed.

At the 2026-10-11 13:07:21 UTC snapshot, executable commit `d1c18b8` has
completed all 18 Sol challenges in `matrix-main-d1c18b8-20261011`: image 5/9 and
hybrid 6/9 task successes. All 18 are eligible with no exclusions; seven
budget failures remain recorded. The audits cover 259 calls and 295 PNGs, with
4,499.937 seconds of reported latency and no reconnects. Reported input is
4,869,278 tokens (cached subset 3,149,440), output 67,474 (reasoning subset 23,739).
These finite results establish no population or model ranking. Luna's 18 challenge
cells remain planned. At the 16:02:58 UTC saved full-game checkpoint, Sol/image
ended in audited native crew-loss defeat after 78 calls / 79 PNGs, while
Sol/hybrid exhausted its 300-decision budget after 300 calls / 301 PNGs with two
human crew, sector index 2, hull 21 and oxygen about 3%. Hybrid has no native
ending. The two main Sol attempts total 378 calls / 380 PNGs; native-ending
completion remains **1/4** and both Luna full games remain planned. The native
pilot defeat after 62 calls stays excluded. Independent saved, cleanup and UI
reviews passed; this dated checkpoint is not a current live-cleanup claim.

Fresh admission passed eight startup checks, nine timing equality probes,
protected cleanup and eight executed independent negative probes, binding
78 executable sources and 565 evidence files. The original 31 native build/source
inputs were reused unchanged with their identities and reuse disclosed;
`production_accepted` remains false. The new cohort uses the
[CLI recovery policy](docs/cli-recovery.md) and repaired saved reporter. The first
trial verifies the reporting repair; no reconnect occurred to exercise live recovery.
All 18 trials have independent saved reviews. The current boundary cleanup check
passed at 13:04:56 UTC: seven original saves, prior bridge, six runtime files,
source pins and no FTL process. The separate
`fullgame-stop-d1c18b8-20261011T1305Z` diagnostic subsequently verified a live
response cancelled before input dispatch, retained evidence and exact restoration.
Its 13:08:49 UTC cleanup and rendered interrupted-state checks passed. Intentional
stopping currently exits nonzero; it does not resume or complete that attempt. Initial gameplay signatures match within measured challenge repeats,
while PNG bytes can differ. See the per-group results and exact checkpoint hashes
in [current validation and remaining work](docs/NEXT.md).

Historical cohorts remain separate. `2174cc9` retains 18 Sol challenge attempts
(17 eligible, 12 successes, five budget failures and one technical exclusion),
a pilot native defeat and an incomplete Sol/image full-game attempt after 46
decisions. `463c340` retains its 13-decision combat task success and original
false reporting exclusion. `078a5e2` and all failed attempts also stay unchanged;
no results are pooled or failed cells silently retried. See the dated evidence,
exact protocol identities and remaining [WIP](docs/NEXT.md).

The complete 36-cell fair comparison, four native-ending full-game conditions
and actual clean-build/setup reproduction remain unfinished. The scoped live
cooperative-interruption check passed. Scoped diagnostics,
passing tests and a challenge outcome do not establish those requirements or
general determinism.

The optional [portable v2 workflow](docs/native-acceptance.md) archives local
startup/timing evidence, original build records, reconstructed native sources
and independent review. Controllers verify installed runtime bytes and frozen
trial settings before model calls, retaining accepted and rejected gates in
replay artifacts. The full-game dashboard checks saved child admission before
showing verified completion. Raw runs, native binaries and local acceptance
artifacts are not shipped in Git; controllers require the complete local
evidence chain and matching runtime. Fresh-checkout setup remains WIP. The tested
[Windows/WSL recipe](site/src/content/docs/install/pc.md) now packages the bridge
from runtime files, requires a caller-supplied hash-pinned patcher, retains
exclusive original native build/source archives, and preserves the selected
checkout. Offline setup checks passed (67 passed; five Windows symlink skips),
shell syntax and two identical bridge archives. The official FTLMan v0.7.3 archive
and executable are locally verified, without execution. Docker recovered after
its inaccessible runtime sockets were preserved and recreated. An actual fresh
source build reached compilation but exhausted its 3 GiB container limit, with
five recorded compiler kills. Optional `FTLB_BUILD_JOBS` now controls direct
Ninja jobs and dependency concurrency separately from memory/CPU quotas. Setup
also preserves existing WSL settings when configuring idle behavior, fixing a
missing-newline corruption. A successful clean build, installation and acceptance
of a newly built runtime remain unproven; see the [WIP evidence](docs/NEXT.md).

A separate corrected viewer fixes an HTTP 500 caused by mixed ISO and numeric
run timestamps. Its rendered current-cohort outcome and replay check passed
without changing frozen execution sources or saved evidence. Read the dated
[current results, usage, evidence and remaining work](docs/NEXT.md), the
[experiment protocol](docs/visual-experiment-protocol.md), and
[agent/contributor guidance](AGENTS.md).

The [validation history](docs/validation-history-2026-10-11.md) preserves
earlier diagnostics. The current-results page retains the original cohorts,
sector pilot and portable reporting failure. The
[store-arrival diagnosis](docs/native-store-arrival.md) records both native
defects, their fixes and the limited validation scope.

## Visual iteration

The new `visual-v1` track gives Codex CLI a screenshot at each paused decision and
accepts ordinary clicks, drags, cursor moves and key presses. Native state remains
available to the evaluator and dashboard; it is not included in the model input.
Every decision retains its exact image, input delivery, simulation-frame count and
resulting image for inspection.

This track is under live validation; standalone attempts remain diagnostic until
their experiment audit establishes eligibility. It requires authenticated Codex
CLI, native protocol 5, fixed clock 2 and `fresh-start-seed-v3`. Install the visual
DLL/provenance pair below, close FTL and run:

```powershell
uv run --directory harness ftlbench visual --model gpt-6.1-sol --mode image --seed 1
```

The Windows runner backs up the current saves, launches a fresh run, then closes
its game process and restores/verifies the original saves on exit. `--mode hybrid`
adds conservative HUD numerals read from the same archived PNG, omitting obscured
or uncertain fields without native-state fallback. `--model gpt-6-luna` selects
the other declared CLI model. See [visual iteration](docs/visual-iteration.md) for
the contract. Historical structured runs remain a separate track.

For reproducible full-game cohorts and durable cooperative stopping, use the
[full-game experiment controller](docs/visual-experiment-protocol.md#full-game-progression).
From the repository root with the harness environment configured:

```powershell
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py freeze --output harness/runs/visual/fullgame-sol-luna-001
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py run --output harness/runs/visual/fullgame-sol-luna-001 --limit 1
```

To stop an active run, use a second terminal at the repository root. Let the
original runner finish cleanup before closing it:

```powershell
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py stop --output harness/runs/visual/fullgame-sol-luna-001 --initiator operator --reason operator_requested
```

Use a new output directory and only one game/controller at a time. The controller
requires the tested runtime/acceptance baseline, freezes sources/settings, and
declares a Sol image sector-one pilot followed by Sol/Luna image/hybrid full-game
attempts. It retains interrupted responses and cleanup evidence. Only verified
native victory or defeat completes a full game; budget stops and the pilot do not.
Stopped attempts remain recorded as interrupted; use a fresh output directory
for a new experiment after a stop request.

The commands above retain the historical local acceptance workflow. For a new
source checkout, the [portable admission workflow](docs/native-acceptance.md#prospective-portable-controller-admission)
documents the required source-bound diagnostics, original build evidence and
independent review. Once that evidence passes, select it explicitly when freezing:

```powershell
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py freeze --output harness/runs/visual/fullgame-portable-001 --native-evidence harness/runs/acceptance/admission.json --evidence-root .
```

Both flags are required together and only apply to `freeze`; the same flags work
with the challenge controller. A new cohort retains all consumed evidence and
source bytes. Changed sources require fresh diagnostics and a new cohort.

## Local setup

The supported benchmark setup is **Kestrel A on easy**, on native Windows with FTL 1.6.9 and the benchmark Hyperspace build. Other ship/difficulty requests are rejected before a run. After reset, the runner checks the actual seed, blueprint `PLAYER_SHIP_HARD`, and difficulty `0`; it does not trust the requested settings alone.

Python 3.11+ runs the harness. WSL and Docker are needed to build the Windows native dependency, but native Windows Python can run the installed benchmark.

```powershell
# From the repository root
uv sync --directory harness --extra dashboard --extra dev
uv run --directory harness ftlbench doctor
```

The wheel includes the Python package, adapter, suites, prompts, Lua bridge, native source patch, setup helpers, and compiled dashboard. The Python interpreter, FTL and native Hyperspace DLL are installed separately. See [PC setup](site/src/content/docs/install/pc.md) for the game installation steps.

The native build must include the cumulative patch selected by `native/manifest.json`, currently `native/patches/0003-visual-io.patch`. It retains protocol-5 controls and scoring and adds render-synchronized screenshots and ordinary input handlers. The earlier `0002-economy-fuel-controls.patch` remains a historical structured-only build. `scripts/setup_pc.sh` applies the checked patch before building. For an existing source checkout:

```bash
python3 scripts/apply_native_patch.py --source /path/to/FTL-Hyperspace --check
python3 scripts/apply_native_patch.py --source /path/to/FTL-Hyperspace
```

The helper validates the patch hash and refuses conflicting source changes. `native/manifest.json` records the reference source commit and patch SHA256; `scripts/write_native_provenance.py` records the actual source commit, source diff, toolchain, container image, and DLL hash. The installed provenance file is `ftlbench-native.json` beside the DLL.

The visual artifact is `dist/Hyperspace.visual-v1.dll` with
`dist/native-build.visual-v1.json`. It supplies clock 2 and fresh-start v3;
protocol 5 alone is insufficient for visual startup. The retained structured
pair is `dist/Hyperspace.protocol5.dll` with `dist/native-build.protocol5.json`.
Protocol-4 artifacts remain archived and do not satisfy the current runner.
The bootstrap now stages the visual pair under these names after checking its
file identities. Its build stage requires an explicit immutable Docker image
reference and the native base declared in the manifest. See
[PC build setup](site/src/content/docs/install/pc.md) for selecting those inputs.
Staging does not produce the complete accepted visual evidence bundle. See the
[remaining setup work](docs/NEXT.md#validation-evidence-and-distribution-limits).

To install a locally built DLL into an existing native environment, close FTL and run:

```powershell
# Visual track (from the repository root; uv runs the CLI from harness/):
uv run --directory harness ftlbench install-native --dll ../dist/Hyperspace.visual-v1.dll --manifest ../dist/native-build.visual-v1.json

# Structured-only track, when that is the selected environment:
uv run --directory harness ftlbench install-native --dll ../dist/Hyperspace.protocol5.dll --manifest ../dist/native-build.protocol5.json
```

The installer verifies the artifact hash/protocol and retains replaced files. The loader and data mods must already be installed.

After the data mod and native DLL are installed, deploy the current external Lua bridge and launch FTL through Steam:

```powershell
uv run --directory harness ftlbench deploy-bridge
uv run --directory harness ftlbench doctor --live --full-game
uv run --directory harness ftlbench play obs
```

`deploy-bridge` retains the previous script in the FTL user folder's `ftlbench-backups`. `doctor` is read-only: it checks files and credentials; `--live` also checks the running bridge; `--full-game` requires the victory binding. It never starts a game or calls a model.

## Headless Linux / Docker

The source checkout also contains the [headless launchers](docker/headless/README.md)
from `main`: a Linux FTL process under Xvfb, a host harness with shared saves, and
parallel containers for structured scenarios. The merge retains Linux process
detection, bind-mount reset acknowledgements, WSL CLI output paths and enriched
crew observations. Each container must own a separate game/save directory.

These launchers require their matching Linux native build. The Windows visual
acceptance does not certify the Linux runtime, and live headless validation of
the merged contracts remains WIP. See [integration status](docs/NEXT.md#main-integration).

## Run a benchmark

Use the public tier for development and the `semi_private` tier for reported comparisons. `suite_v1.json` is the default mixed probe suite; `full_game.json` is the full-game track.

```powershell
# Bounded local smoke
uv run --directory harness ftlbench run --agent scripted --mode budget --max-instances 1 --budget-cap 3

# Public OpenAI Responses API
uv run --directory harness ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend openai --model <model-id> --suite ../scenarios/full_game.json --tier public --mode gameover

# Jev typed-choice adapter
uv run --directory harness ftlbench --env-file "C:\Projects\.env.txt" run --agent llm --backend jev --model jev-1.13.0 --suite ../scenarios/full_game.json --tier public --mode gameover

# Read-only live dashboard
uv run --directory harness --extra dashboard ftlbench dashboard
```

Select the environment file explicitly. Simple `KEY=value` lines are loaded literally; existing process environment values win and keys are never printed. No environment file is discovered automatically.

| Backend | Credentials / contract |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY`; Messages API action text |
| `openai` | `OPENAI_API_KEY`; public Responses API with a strict action-plan JSON schema |
| `jev` | `TYPESAFE_API_KEY` (or `JEV_API_KEY`); typed Choice questions for observable actuators |
| `claude-cli` | Installed, authenticated `claude` CLI |
| `codex` | Installed, authenticated `codex` CLI; optional `CODEX_BIN` |

Jev uses the separately labeled `jev-actuator-choice-v1` contract. It chooses from observed power settings, crew destinations, targets, navigation, economy and special-system actuators, then an advance interval. Independent choices can conflict; the same bridge feedback applies. Each question has at most 255 options and each plan at most 12 commands; invalid or oversized plans fail explicitly. It does not generate arbitrary action text. Compare its rows with this action-selection contract stated.

The OpenAI backend uses the [public Responses API](https://developers.openai.com/api/docs/guides/structured-outputs). An OpenAI Decisions preview adapter is not implemented because its request/response schema is unavailable here; preview availability must not be inferred from Responses support.

## Interface and scoring

The game pauses while the agent plans. Commands apply in order, then `advance N` runs the simulation for a bounded interval and re-pauses. A typical reply is:

```text
ACTION:
  power 3 3
  crew 1 2
  fire 0 3
  advance 150
```

Each `fire` or `beam` queues **one release**, including while a weapon charges. Beam endpoints remain distinct. Weapons are not left on continuous autofire. The compact observation preserves weapon charge/pending state, ion and hacking state, drone parts, room/door/airlock topology, events, stores, and optional special-system facts. The interface manual is [prompts/ftl_agent_v5.md](prompts/ftl_agent_v5.md); optional fields and unverified bindings are tracked in [the coverage audit](docs/observation_coverage_audit.md).

The `owned-player-crew-v1` control contract exposes player-owned crew with their original native IDs, ownership, location and controllability. Hostile boarders appear in `intruders`, never as player crew. Movement checks ownership, native controllability and positive health before calling the engine; mind-controlled friendly crew cannot be moved. Own crew boarding the enemy remain player-owned. `action_feedback` reports applied/rejected crew moves and reasons.

Runner/ruleset v7 requires `native-economy-and-fuel-recovery-v1`. `upgrade <system_id>` and `reactor` use the native next-level price, cap, affordability and UI legality; Lua never guesses prices or deducts scrap independently. `economy` reports those costs and `can_upgrade`. Missing cost means unknown or unavailable, never free. `waitfuel` queues the game's out-of-fuel Wait turn; `distress on|off` uses its native distress toggle. A following `advance` resolves the normal animation, encounters and fleet movement. Ordinary `wait`/`advance` only pass simulation frames and do not buy a recovery turn or guarantee fuel.

Events preserve native choice IDs and availability (`native_type: 1` is disabled). Feedback distinguishes disabled choices, keyboard input delay/settings, refused selection and an already queued selection. `applied` proves that the native choice was queued; it does not prove the event branch has finished. The bridge preserves the game's keyboard delay and does not retry branches automatically.

A full-run solve requires explicit native `victory: true`. Game over, disappearing enemy ships, and raw flagship phase/stage counters do not prove a win. Full-run progress is eight sectors plus three completed flagship phases; the current native bridge reports the completed three phases at verified victory, without estimating intermediate phases.

Runner/ruleset v7 also requires `native-sector-neighbors-v1`: `economy.sector_navigation_version: 1` and Lua `sector_navigation: true`. Sector exit selects a real neighboring-sector vector index and reports native acceptance/refusal; sector types are not route indices. The marker is required even though the native API protocol remains 5.

`native-beacon-readiness-v1` additionally requires `economy.beacon_navigation_version: 1` and Lua `beacon_navigation: true`. Ordinary jumps and sector exit obey native button, full FTL timer, system, fuel and context readiness. A destroyed enemy flag alone does not authorize travel. Rejected requests report feedback instead of forcing map travel. Charged combat fleeing remains subject to normal native legality. `economy.navigation.can_jump` is authoritative. `enemy_defeat_pending` signals possible unprocessed defeat/rewards; it does not prohibit an otherwise legal charged jump. Continuing normal simulation lets cleanup/rewards resolve, while jumping away can forgo them.

Navigation credit requires observed beacon/sector movement. Rejected jumps and resets earn no travel credit. Losses retain their final state and score. Concession (`giveup`), stalls, transport/model errors, and interrupted attempts remain unsolved; terminal records explain which occurred.

Native score comes from the current run's live scrap/kill/beacon counters with the exact FTL difficulty multiplier, tagged `native_live_v1`. The saved TopScore snapshot may retain a previous run and is not accepted as live score evidence.

`native-enemy-hostility-v1` requires Lua `enemy_hostility: true`. A surrendered ship can retain positive hull, weapons and a native ship pointer; combat and targeting use the native `_targetable.hostile` flag. Non-hostile, destroyed, jumping or unknown-state enemy targets reject enemy-directed weapon requests and clear queued enemy fire. Dispatch feedback records `enemy_hostile`, `enemy_targetable` and accepted queue state. `targetable` and compact `active` never become true from hull or equipment alone. Friendly ships do not independently block a charged native-legal sector exit.

Each invocation creates a unique subdirectory under `--out`, containing `run.json`, one JSONL trajectory per attempt, and summary JSON. Manifests include runner/ruleset versions, control, economy, routing, beacon and hostility contracts, setup verification, mode, model/backend, prompt and suite identity, installed DLL/bridge hashes, and native provenance when available. Retries are a distinct condition and retain every attempt.

Read a saved run without starting the game: `ftlbench report <run-dir> [--json] [--output <path>]`. `--legacy-suite <path>` is an explicit fallback for older files without embedded scenarios.

**Runner/ruleset v7 requires protocol 5 with verified sector-navigation and beacon-readiness markers, the owned-player crew contract, native economy/fuel recovery and native enemy hostility. Earlier rows are not comparable.** The v6 trial was stopped after accepted surrender left a friendly ship marked targetable. The v5 trial was stopped after ordinary jumps bypassed native charging and enemy-death reward cleanup. The prior v4 trial exposed an incorrect sector type/index mapping and was stopped as a diagnostic. A pre-v3 model trial moved a hostile boarder and was stopped. The corrected v3 Sol trial ended in a fuel-zero concession with native score 329, but exposed missing event availability, approximate upgrade pricing and missing recovery actions; it is retained as a diagnostic, not a model ranking. The earlier Jev score-59 trace remains historical v2 score/reset evidence. See [validation status](docs/NEXT.md).

## Dashboard and development

The dashboard uses `http://127.0.0.1:8765` by default and follows runs and attempts,
including errors and active trajectories. It is read-only and sends no game
actions. Use `ftlbench dashboard --runs <directory> --suite <path> --port 8765`
to select inputs; choose an unused port when another server is already running.
Saved experiment overviews show planned cells, exact replays and outcome reasons.
Saved cleanup receipts describe their recorded time, not a current live-save audit.

```powershell
uv run --directory harness --extra dev --extra dashboard pytest -q
npm --prefix dashboard ci
npm --prefix dashboard test
npm --prefix dashboard run build
npm --prefix site ci
npm --prefix site run build
uv build --directory harness
```

Tests execute the real Lua 5.3 bridge against an engine double, plus adapter, scorer, lifecycle, model backend and dashboard contracts. These do not establish a full-game live win or provider quality. See [docs/NEXT.md](docs/NEXT.md) for current validation and remaining work.

| Path | Purpose |
|---|---|
| `mod/` | In-game Lua observation/action bridge |
| `native/`, `scripts/` | Checked native patch, setup and provenance helpers |
| `harness/` | Sessions, scenarios, scoring, recording and packaged CLI |
| `adapter/` | Runner, baselines, model integrations and dashboard server |
| `dashboard/`, `site/` | Dashboard UI and documentation |
| `scenarios/`, `prompts/` | Seeded suites and versioned interface manuals |

Native Windows is the current full-game validation target. WSL can drive it with `FTL_SAVE_DIR` set to the Windows save folder. macOS/Rosetta remains a secondary development path and requires its own compatible native build and live validation.
