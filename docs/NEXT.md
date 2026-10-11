# Current validation and next work

Updated 2026-10-11 UTC. The local visual track is `visual-v1`; the structured track remains runner/ruleset v7. Both require native protocol 5, with additional capability checks for the visual interface. Earlier traces retain their original artifacts and contracts.

## Current integration

Fresh-start v3 is now integrated into production: the complete native patch,
bridge, package helpers, full-game entry point and fixture-6 challenge runner use
the tested contract. DLL `a33b9984...` is installed with newly generated provenance
`2851d40d...`, preserving its original build timestamp and verifying all twelve
native source hashes. The previous release is archived at
`dist/releases/visual-v1-before-fresh-start-v3-20261011`.

The accepted cooperative-stop source release passes 1,849 tests with ten explicit
Windows skips (eight host C++ compiler checks and two symlink checks). Installed
wheel CLI, fresh helpers, validator/controller help commands and dashboard smoke
checks pass on unpinned Python 3.14.8. All 102 wheel and 176 source-release source
files match the frozen tested source bytes. The passing receipt is
`dist/fresh-start-v3-production/package-validation-cooperative-stop/receipt.json`
(`7ad330cbfc438132f7e0cbba6cd681b32daa050ef9b10b8aea8a8267b81087dd`).
The prior accepted receipts (`62125b29...` and `86f0aa21...`), packages, archives,
earlier failures and temporary environments are preserved.
Ten native executables pass separately, including all 72 fresh-start cases. New live
controls, transition, interference, sector and fuel-wait checks pass; fixture-free
full-game startup preserves the opening choice with zero native updates and zero
model calls. The production challenge CLI also passes all three setup-only
scenarios. Original saves, deployed bridge and installed runtime baselines are
verified after cleanup. Evidence is under `dist/fresh-start-v3-production` and
the corresponding `*-v3-production-20261011*` validation directories.

The immutable nine-probe acceptance remains
`dist/deterministic-setup-candidate/challenge-repeatability-acceptance-v2.json`.
Its measured equality is reused only for the exact tested DLL/bridge; it does not
establish full-game determinism or challenge completion. The current production
acceptance is promoted at `dist/native-validation.visual-v1.json`
(`2fe55655...`) and additionally binds the six new live cases and original
build/provenance origins. The recorded controller revision passed admission. The nested
Python interpreter environment mismatch is fixed and the final package checks
above pass.

The stopped Sol/Luna cohort is preserved at
`harness/runs/validation/visual-v1/matrix-fresh-v3-20261011`, with protocol
`551c712f1a273e957c31c5b9210e3e766f8df929dcb4e1adfa84c4dd90051dc6`
and 74 pinned source files preserved in `frozen-sources`. All three Sol image-only
combat repetitions succeeded in 13, 16 and 13 decisions, respectively, with final
hull 28/30, 26/30 and 23/30; all three crew survived each trial. Their completed
reports record `fixture_goal_observed` and passed validation. The first trial's
audit verifies 15 unique PNGs, model requests, exact restoration of seven saves,
and no remaining game process before continuation. `gated-audits` retains the
point-in-time live cleanup checks. All 15 production baseline files also matched
before the next trial started.
The requested CLI model is Sol; the response stream does not independently name
resolved backend weights. For repetition one, recorded usage is 247,526 input and
3,865 output tokens; median response latency is 17.072 seconds. Cost is unavailable.

Fire repetition one ended at `idle_decision_budget`, but its public task asked
only for the initially injured crew member's full recovery while the evaluator
required every crew member at full health. The initially injured crew recovered
from 50/100 to 100/100. The other fire/oxygen/survival checks
passed; the retained false-negative is a task/evaluator defect, not evidence of
failure under an aligned task. Its raw failed validation remains unchanged.

Fire repetition two was interrupted by the assistant operator after this defect
was confirmed; the human did not request that stop. The execution-session
interrupt terminated Python before its cleanup handler. Its raw `run.json`
remains `running` and its trajectory has no terminal end record. The separate
`operator-recovery/receipt.json` in that trial records explicit manual restoration,
not automatic or graceful cleanup. Independent read-only verification at
2026-10-11 01:17:51 UTC matched all seven original live-save hashes and inventory,
all 15 baseline paths, the raw run/trajectory hashes and the restoration receipt;
no FTL process remained. The operator receipt is `13f27d51...`.

Both supervisors are terminal. The ledger retains four finished cells, one
`interrupted_unknown` cell and 31 planned cells. This cohort cannot be resumed
with repaired sources or have its raw outcomes rewritten. The recorded starting gameplay signature
of the first two repetitions matches exactly; this is not a claim that their
images or subsequent model decisions are identical. The 36-cell comparison is
still incomplete, and these challenge outcomes are not full-game results.

The separate unstarted full-game protocol is preserved at
`harness/runs/validation/visual-v1/fullgame-fresh-v3-20261011`:
`873bd288af408ba7b22c836788476b9a49c922898f44231637162268d13c8a77`.
All 76 source files are archived byte-for-byte in `frozen-source`. It declares a
Sol image sector-one pilot followed by Sol/Luna image/hybrid full-game attempts,
seed 1, medium reasoning, 300 decisions, 14,400 seconds and eight idle decisions.
The controller has 60 passing tests and an independent review, joins actual
request settings and all five installed runtime files to accepted evidence, and
retains timestamped post-child cleanup receipts. No full-game cell has started;
shared-source repairs prospectively supersede this frozen protocol, so it must
not be executed with the changed sources.
Only native victory or defeat counts as a complete game. The dashboard now
supports both saved challenge and full-game experiment overviews, including the
pilot and all four full-game conditions. A verified completion requires the
nested saved audit, hash-joined cleanup artifacts and raw native terminal state
to agree; pilot outcomes and budget stops never count as completed full games.
Focused overview tests and the dashboard build pass. These are offline display
checks, not new gameplay results.

Cooperative cancellation (`visual-cooperative-stop-v1`) and public fire-task
alignment (`fire-crew-recovery-task-v2`) are implemented. The fire task explicitly
requires ALL crew at full health, including injuries sustained during
firefighting, matching the retained evaluator. Frozen protocols bind task
versions and text hashes and reject stale task contracts before game startup.
Use the controller's `stop --output <experiment-directory> --initiator operator
--reason operator_requested` command; see the experiment protocol for examples.
The two protected no-model probes, `cooperative-stop-challenge-20261011` and
`cooperative-stop-fullgame-20261011`, passed at the first `before_actor` boundary:
matching stop requests, normal automatic cleanup, seven original saves and all
15 baseline paths verified, with no remaining FTL process. Cancellation during
an actual CLI call now also has one protected live probe:
`cooperative-stop-cli-20261011/receipt.json` (`822720df...`). The official request
was published while the same authenticated Sol CLI child was live before and
after publication. Its one real response was retained as `model_cancelled`,
then discarded at `after_actor_before_dispatch`; zero actor actions were sent.
Terminal/request/call evidence and automatic cleanup passed, with seven original
saves and all 15 baselines verified. This establishes one cooperative-stop path,
not forced termination of the CLI, gameplay completion or model performance.

The repaired challenge cohort is now frozen at
`harness/runs/validation/visual-v1/matrix-task-v2-stop-v1-20261011`, protocol
`9cab4b1629ebefef5f6686d3865ea19966793a2d6013801d471e51a14f062087`.
All 76 pinned files match their archive. The three Sol image combat trials have
identical canonical initial gameplay signatures (`1759586d...`). All are scoped
eligible with no exclusions and complete, issue-free response/PNG audits.

| Combat repeat | Terminal reason | Decisions / PNGs | Task success | Final hull | Crew outcome |
| --- | --- | --- | --- | --- | --- |
| 01 | `idle_decision_budget` | 38 / 40 | False | 17/30 | Three alive, each 100/100 |
| 02 | `native_game_over` | 34 / 36 | False | 19/30 | All died; remaining native entry health 0 |
| 03 | `fixture_goal_observed` | 8 / 10 | True | 27/30 | Three alive; lowest health 71.91/100 |

This is 1/3 scoped combat successes, not a model ranking or fixture-free full-game
proof. Repeat three ended with enemy hull 0 and `fleeing: false`, plus the normal
18-scrap reward (player scrap 48). Its 02:02:48 UTC gate joins the exact trajectory
(`cbe0f4e8...00c7a`), all seven original save backups and point-in-time live restoration.

Supporting failure evidence remains intact. Repeat one finished at 01:45:51 UTC;
the enemy escaped at trajectory record 22 without reward, despite raw engine
`destroyed`/counter increments. Those fields alone are not kill proof; the reward
requirement correctly rejects success, and review found no wrong score formula
or benchmark score mutation. Final oxygen was 77%. Its gated audit checked seven
live originals, and independent checks matched all 15 baselines/no FTL before
continuation; trajectory SHA is `7542a634231ea27177e7f5aa274f6c064cdd1edd99af09a5b493257e9afea64b`.
Usage was 720,315 input / 12,162 output tokens, including 366,080 cached input;
response time 616.167 seconds total / 16.696 median. Cost and resolved backend
identity remain unavailable.
Repeat two's final PNG says all crew died, with oxygen 1%; the precise death
mechanism is unproven. Its final advance stopped after 589 of 600 requested
updates. The saved gate at 01:59:42 UTC (`3d04a6d9...`) verified seven live
originals before repeat three; backup hashes match repeat one. These saved gates
are under `gated-audits/gpt-6.1-sol__image__combat__repeat-0N.json`; they do not
claim current live cleanup or another 15-baseline check during the active trial.

At 2026-10-11 02:04:54 UTC, the ledger showed four finished cells (three combat
and fire repetition one), fire repetition two running and 31 planned. Root's
supervisor session 17511 remains the guarded `--max-cells 8` batch. The six
fire/repair cells follow combat; one is finished and five remain in that batch
at this snapshot. Sources are unchanged and the cohort retains its frozen
contract. No completed matrix comparison is established.
The separate `fullgame-stop-v1-20261011` protocol is
`da498515a486baf0eff09564f880342106ce2e156d3a65a24df1b468f844c1fc`;
all 78 archived pins match and all five cells were planned at that snapshot.
No full-game completion or general full-game reproducibility is established.
Remaining priorities are the declared challenge matrix and the separate native-
ending full-game sequence; preserve every attempted outcome and cleanup gate.
The updated dashboard session is served at `http://127.0.0.1:8766`; port 8765
still belongs to an older backend and should not be used for current overview
acceptance.

## Historical comparison and diagnostic progression

The screenshot-only HUD reader, repeated challenge runner, frozen matrix controller,
and trial-result dashboard are implemented. The first frozen comparison at
`harness/runs/validation/visual-v1/matrix-clock2-20261010` is now preserved as a
partial historical cohort. Two Sol image combat trials achieved their goals;
repetition 3 stopped before any model decision with a stale-screenshot setup
failure. The audit supervisor stopped the sequence. All seven original saves
and the production bridge were independently verified after cleanup; the 63
pinned source/runtime files are preserved in its `frozen-sources` directory.
The race was reproduced offline and in a separate live no-model probe: the
fixture changed state after the first capture, causing a second capture for the
same request. The strict transport guard correctly refused stale input.
Fixture version 5 repairs admission by initializing after the single request is
accepted but before its first render. The first returned image must already show
completed initialization; setup no longer polls past an incomplete first image.
The exact live reproduction now passes three repetitions in
`stale-capture-probe-after-fixture5-20261010`. The full checkout passes 1,285 tests
with eight skips; independent admission/bridge review passes 73 focused tests.
Nine new no-model timing probes completed in
`timing-clock2-fixture5-all-20261010`. All first captures already contain the
applied fixture and all individual timing/input checks pass. Fire and repair
match across three repetitions. Combat differs at the 12-second impact despite
equal recorded initial and earlier states, so overall acceptance is false and
no replacement model cohort has been started. Paused RNG use, outer native hook
side effects and unrecorded initial timers are being investigated. Manual review
of the three initial PNGs confirms the visible fire/injury and damaged engines
already appear in the first capture. All original saves were restored.

The follow-up `rng-idle-fixture5-20261010` completed three protected no-model
combat probes. All 168 native RNG sample pairs agree within each double read;
none of the sampled equal-counter idle intervals changes the native RNG words.
During explicit gameplay, however, repetition 1 reaches recurrence position 367
at 120 updates while repetitions 2/3 reach 368. They reconverge at 240 updates
and diverge later. Recorded initial/coarse gameplay equality therefore does not
establish equivalent hidden state. This diagnostic covers the native shared
generator, not C-library `rand()` or other streams. The exact analysis and seven
independently verified original-save restorations are in its
[`rng-analysis/REPORT.md`](../harness/runs/validation/visual-v1/rng-idle-fixture5-20261010/rng-analysis/REPORT.md).
Source and archived setup observations also confirm that prerequisite traversal
uses legacy wall-derived timing before visual clock ownership; the first-image
fixture normalizes only selected charges. Hidden setup timing and the distinct
C-library target-selection path are now the next diagnostic boundaries. No
runtime fix or replacement model cohort is accepted from these measurements.

The subsequent `rng-target-trace-fixture5-20261010` used a temporarily installed,
explicitly diagnostic DLL for three further no-model repetitions. All 81
capture-referenced traces pass hash/identity/serial/seed checks; their cumulative
native draw counts agree with every corresponding external RNG sample. The
first random-draw schedule already differs on the first admitted world update.
At update 485, one run selects a random room at `(245,140)` while another
prioritizes engines at `(70,175)`; the actual fallback branch is recorded, not
inferred from later damage. The third run matches the first draw/target stream.
Initial hidden fields also differ, but the observed player stance does not
track the stream split and weapon animation charges normalize after one update;
neither is established as the cause. No `TimerHelper` trace events were observed,
so that hook supplies no evidence about the remaining hidden timing mechanism.
The refined ordering also shows the same RNG value consumed by general world
work at update 480 in one run and by combat AI at update 485 in the other;
matching the sequence of random values does not make their consumers equivalent.
See the [complete trace analysis](../harness/runs/validation/visual-v1/rng-target-trace-fixture5-20261010/native-trace-analysis-v3/REPORT.md).
The original installed DLL/build receipt and all seven saves were restored and
independently checked. The next setup iteration must own fixed time before
fresh-world construction and through prerequisite travel, with one-time seed
initialization at the real construction boundary. It must demonstrate repeated
impact equality before further model comparisons; per-action reseeding or more
isolated timer resets would not establish equivalent starting histories.

The isolated replacement is being developed under
`dist/deterministic-setup-candidate`. Its fixture6 collector removes all late
fixture reseeding, records setup requests and native receipts, and joins each
request to its exact native update interval. The collector and runtime
restoration suite now participates in 218 passing focused collector/bridge/runtime
checks, including actual fixture and bridge Lua execution. Native contract v2
was built and tested in two protected no-model smokes. Both stopped before ship
creation; the second retained the exact native refusal: one name had already
been generated, with zero ship initializations. All seven original saves and
the original DLL, provenance and deployed bridge were restored; both independent
cleanup audits passed all 13 checks.

Source and exact-binary review identified the name as the startup stat-evaluation
dummy. Its name reservation survives through initial crew blueprint selection,
so simply exempting the call would leave uncontrolled initial state. Isolated
native contract v3 instead classifies that exact lookup and requires an empty
crew factory, its sole orphan reservation, and no other prior construction.
Immediately before normal ship construction it clears that reservation once,
verifies the result, and initializes both generators once. Historical name
counts remain visible. The collector verifies reset contents/counts/thread and
pins the executable, DLLs and packed data/mod scripts. This claim is restricted
to those exact inputs; arbitrary mods are not covered. Native v3 built successfully
as diagnostic DLL `5e26b0c8...`, after 57 actual C++ checks and syntax validation
of both affected Windows translation units. Its build restored all original
native source files, WSL build DLL and production artifacts. Four protected v3
smokes pass the exact startup-dummy admission checks, then refuse the first
normal New Game click with `construction_menu_no_progress`. No seed reset,
player construction or model decision occurred. The second smoke preserves the
post-click native cause; the bridge's 101 actual-Lua tests cover that evidence
and guarded menu diagnostics. Lua exposes too little menu state, so a separate
native diagnostic DLL (`6667b0e6...`) records the actual button and modal fields.
It passes 63 executable C++ checks and all three affected Windows syntax checks.
The fourth smoke, `setup6-v3-native-menu-diagnostic-20261010`, establishes that
the click succeeds: the active, hovered New Game button opens the overwrite
confirmation and also sets `bSelectSave`, with zero world updates. The fresh
menu classifier currently rejects that paired native state before checking
the confirmation; this is the confirmed next fix. Every smoke restored all
seven saves and original runtime files, with 13 independent cleanup checks.
The classifier fix accepts only the native paired confirmation flags and keeps
unmatched flags and conflicting modals blocked. It passes 72 executable native
checks and three Windows syntax checks. Diagnostic DLL `a33b9984...` now passes
the protected startup smoke and all receipt/packet checks in
`setup6-v3-menu-classification-smoke-20261010`. Three no-model combat repetitions
in `setup6-v3-combat-repeatability-20261010` also pass: initial gameplay state and
all 13 measured steps match exactly across delays of 0, 0.35 and 1.2 seconds,
including actual hull damage. Clock, input delivery, paused-idle and save/runtime
restoration checks pass. The three fire repetitions in
`setup6-v3-fire-repeatability-20261010` and three repair-fixture repetitions in
`setup6-v3-repair-repeatability-20261010` also pass with exact measured-state
matches. These cover fire progression and ordinary oxygen power/drain behavior
in the damaged-engine fixture; they do not complete the actor's challenge tasks.
All nine trials verify fresh construction, exact setup packets/budgets, capture
handoff and save/runtime restoration. A separate combined verifier rederives
comparison results, native signatures/counters, fresh image identities/bytes,
seed receipts/packets and per-trial save restoration from the archived evidence.
This establishes equality along the tested inputs, not full-game RNG equivalence.
Runtime/source packaging and production runner integration precede a replacement
model comparison. Production runtime deployment and the old model cohort remain
unchanged.

The fixture-free full-game admission helper is separately prepared and reviewed:
117 offline cases retain native v3 checks, allow an immediate zero-interval
handoff, and reject backstage gameplay before the actor. Its optional runner
callback patch passes 94 fake integration/regression cases. Admission runs after
recording the first screenshot and before any model decision, preserving the
failed image and native cause if verification rejects. These isolated artifacts
are not yet wired into the production full-game entry point.

Reviewable promotion artifacts are staged under
`dist/deterministic-setup-candidate/native/production-integration-plan`: a complete
12-file native patch that reconstructs the tested bytes, two include mirrors,
the 72-case native test, and proposed manifest/CMake/pytest changes. A separate
tooling patch passes 22 tests and preserves the original DLL build time while
recording provenance generation separately; fingerprints retain the fresh-seed
contract. The bridge's production test candidate passes 106 actual Lua 5.3 cases
through the shipped `_bench_root()` layout without relying on `dist` paths.
The full-game runner callback patch, native promotion, provenance tooling and
bridge tests remain isolated; no production source/runtime promotion has happened.
Archive originals before applying them, regenerate provenance from the exact
tested native tree/DLL and complete patch, then run production and built-package
checks. Existing diagnostic provenance must not be relabeled as a new build or
as installed acceptance, and the old comparison cohort must remain historical.

The actual packed data archive was extracted read-only and audited. It contains
six Lua files, of which exactly the benchmark JSON, observation and bootstrap
scripts are registered. No relevant crew-construction/stat callbacks occur in
those Lua files or the 122 XML files. The installed archive hash stayed unchanged;
the external hot-reloaded bridge is pinned separately. Exact source differences
and scope limits are recorded in `dist/deterministic-setup-candidate/runtime-data-audit`.

The comparison overview is integrated into the dashboard and verified in the
local browser. It displays all 36 planned trials, three finished and 33 waiting,
with explicit partial/unqualified status. Exact trial links and direct query
links select the recorded Sol replay; before/after images, step navigation,
input delivery, timing, outcomes and save restoration are visible. History
discovery now recognizes trajectory records and excludes 98 diagnostic sidecars,
including 81 native trace files. The focused discovery/comparison suite passes
60 tests with one Windows symlink privilege skip; the prior integration passed
113 Python checks, 11 UI checks and the production build. Browser evidence and
screenshots are in `dist/dashboard-comparison-candidate/browser-acceptance`.
These are dashboard checks over historical data, not new model results.

The first Sol image
combat trial achieved all seven outcome checks in 16 decisions: one enemy
destroyed, its reward collected, hull 19/30 and all three crew alive. Its final
audit passed for 18 images, 4,475 admitted updates (74.5833 simulated seconds),
and all seven restored live saves. Model response time was 313.623 seconds.
The second achieved the same task in 13 decisions. These are two historical
challenge results; a complete repeated comparison and full games remain.
Its `ledger.json` is authoritative for current execution status,
and `comparison.json` is generated after each finished trial. The
[experiment protocol](visual-experiment-protocol.md) records the complete goal,
36 planned challenge trials, full-game progression, and evidence requirements.

Nine earlier pristine setup checks exposed varying combat charge fractions and
fire placement. Fixture version 4 and visual clock version 2 passed nine
timing probes: three repetitions of combat, fire and repair with identical inputs
and delays of 0, 0.35 and 1.2 seconds. Initial and all 96 scripted-step gameplay
signatures match their corresponding repetitions. Every idle boundary uses a
fresh native capture; all seven original saves were restored byte-for-byte.
Evidence is in `harness/runs/validation/visual-v1/timing-clock2-all-20261010`.

The same clock-v2 DLL passed current live capture/control (9 checks), travel
boundaries (4), sector travel (11), fuel waiting (11), and outside-input rejection
(9). Seven compiled native tests passed separately. Rebuilt Python packages pass
their installed-wheel smoke, and the extracted source suite passes 1,276 tests
with eight skips (seven covered by those native executables, one Windows symlink
privilege check). These establish scoped infrastructure behavior, not model
challenge success or complete games. Full-game RNG initialization still needs
the separately versioned checks in [full-game-seeding-review.md](full-game-seeding-review.md).

The pre-change native DLL, sources, build provenance, and acceptance receipts are
archived in `dist/releases/visual-v1-before-fixed-step`. The evidence below remains
historical and does not establish fixed simulated duration or complete games.

## Visual iteration snapshot (2026-10-09)

The visual runner uses the locally authenticated Codex CLI, paused native screenshots, and ordinary mouse/key inputs. GPT-6.1 Sol is the live validation model. Native telemetry is evaluator-only; the actor receives the image, its own bounded history/memory, and an optional provisional paused-only summary. Image and hybrid modes must not yet be presented as a meaningful HUD comparison.

Run `ftlbench visual --model gpt-6.1-sol --mode image --seed 1 --output <new-directory>`. The Windows runner protects every current save file and verifies restoration before marking the run complete. The dashboard replays the exact input image, requested inputs, actual simulated frames, model latency, and resulting image. See [visual-iteration.md](visual-iteration.md) for usage and acceptance scope.

The cumulative current native patch is `native/patches/0003-visual-io.patch`; build artifacts are `dist/Hyperspace.visual-v1.dll` and `dist/native-build.visual-v1.json`. The manifest and provenance contain exact hashes. The former protocol-5 DLL/patch and archived visual candidates remain available for reproducing their historical traces.

The runtime requires `visual_clock_version: 1` and the external-input guard. Native world updates, including travel, stay frozen during inference and zero-frame steps. Every acknowledged frame count must match the native counter change. Valid queued sector choices and active fuel waiting can advance only through an explicit budget. An idle map or unselected dialog remains blocking. Current DLL `75c71eb6…` / patch `2c657fdd…` refreshes ordinary idle-map controls without progressing travel and keeps native hover text current after pointer/key batches and during stationary paused frames. It preserves normal tooltip delay and targeting state. The Lua bridge `89406693…` reads one immutable action packet per tick, preventing a newly arrived visual request from being acknowledged by the structured handler.

Live evidence is under `harness/runs/validation/visual-v1/`:

- `sol-store-final-20261009T0347`: Sol completed all eleven store-to-arrival checks in four audited image decisions on DLL `8cd1573b…` / patch `4b9d9dac…`. It bought one fuel at the native price, clicked CLOSE, charged the drive, opened the map, and reached the selected connected beacon. Travel requested 600 frames and stopped at the arrival dialog after 241. `manual-image-review.json` verifies the visible button and completed arrival.
- `tooltip-final-20261009T0504`: the current native build passed fourteen clock/input checks and thirteen directly inspected image cases, including stale-text removal, delayed stationary hover, and keyboard-opened/closed menus. All world counters remained zero. `acceptance.json` pins both independent image reviews and the raw evidence.
- `controls-final-20261009T0507`: the current build passed all nine capture, inference pause, zero-frame input, key/Shift power control, and crew-drag checks. Two selected crew reached the medbay while the pilot stayed in place.
- `transition-final-20261009T0417`: the preceding `607776a6…` build passed queued-jump and mid-warp idle/zero-frame freezes, explicit bounded arrival in 241 actual world updates, and exactly one fuel spent.
- `sector-final-20261009T0416`: all eleven checks passed for ordinary sector-map inputs, queued/started/final freeze boundaries, and sector 0 to 1 travel with one fuel spent in 241 actual world updates. Only the current-beacon exit prerequisite was supplied by the fixture.
- `wait-final-20261009T0415`: all eleven checks passed for the native zero-fuel WAIT flow, frozen idle/zero-frame boundaries, and a recovery event after 120 actual world updates. Only the zero-fuel prerequisite was supplied. The final screenshot offers four fuel; that choice was not accepted and no fuel award is claimed.
- `startup-final-20261009T0428`: all six direct reset-to-screenshot checks passed on the current Lua bridge, retaining the unselected opening event across two captures with zero world updates. This covers the production full-game startup path without backstage event dismissal.
- `interference-final-20261009T0339`: on the earlier `512d4a2a…` build, a process-scoped Windows mouse message changed the external-input generation and caused refusal before any new action packet, with unchanged world state and frame counter. All seven native executable regression groups also pass on the current source, including input guard and clock gates.

All seven original saves were restored and verified after these runs. Earlier captures and store trials retain their original artifacts and bridge identities. The first clock implementation permitted travel during inference; its traces have explicit limitations. The later `sol-store-final-20261009T0340` trial correctly froze travel but the model mistook its small-ship animation for arrival and exhausted 45 decisions. That failed attempt is preserved. The following prompt revision explains the animation, and `--max-idle-decisions` now ends consecutive empty zero-frame responses after eight by default, without playing for the model.

The fresh `sol-fullgame-20261009T0420` attempt exposed the Lua double-read race before any model decision. Its failed artifacts and seven verified save restorations are retained; it has no recorded gameplay score. Runner failure reporting now preserves the specific cause, uses null metrics without an in-game observation, and reports verified restoration from its receipt.

After direct-startup validation, `sol-fullgame-20261009T0429` ran Sol through Codex CLI, screenshots only, seed 1. The assistant intentionally stopped it after 53 decisions to repair a confirmed same-batch tooltip display defect: text from an earlier button could remain at the final cursor position. The raw `user_interrupted` reason is the generic Ctrl+C label, not a human cancellation request. The trial recorded two jumps, three visited beacons, one destroyed ship, 31 collected scrap, native score 81, hull 27, fuel 16, and three surviving crew; no victory or completed full game. Its independent audit passed for all 53 decisions, 54 PNGs, actor input boundaries, native delivery/clock accounting, and seven restored save hashes. The audit explicitly does not certify tooltip fidelity. `operator-review.json` preserves the limitation and the original evidence hashes.

Future visual reports now mark event counts and intermediate flagship phases unavailable when the necessary native telemetry is absent. Their earlier zero placeholders are not evidence of zero events or completed phases. Historical raw reports remain unchanged. After the tooltip and ordinary-control regressions passed, `sol-pilot-final-20261009T0508` completed a fresh image-only run on the repaired build: 24 decisions in 542.959 seconds, ending normally at `decision_budget`. It recorded one jump, two beacons, no kills, native score 20, hull 17, fuel 15, scrap 30, three surviving crew, and no victory. The independent audit passed for all 24 decisions and 25 PNGs, image-only/no-tool actor boundaries, exact runtime identity, input/clock accounting, consistent terminal reports, and all seven restored live save hashes. FTL is closed. This validates bounded end-to-end execution, not a completed full game or model-performance improvement.

Current packaging passes 1,114 tests with eight skips in both the checkout and an independently extracted source package. Seven compiler-dependent checks also pass as WSL native executables; the remaining skip requires Windows symlink privilege. Installed-wheel CLI/validator/clock/provenance/dashboard checks pass, with all packaged source files matching the frozen checkout. Exact hashes and scope are recorded in `dist/package-validation.visual-v1-python.json` and `dist/SHA256SUMS.visual-v1-python.txt`.

These are diagnostic control checks, excluded from model-comparison totals. No visual full-game victory or image-versus-hybrid result is established by them. The older structured checks below describe their recorded builds, not validation of every visual control.

## Structured track v7 snapshot (2026-10-04)

### Implementation

- Reliable native setup, explicit autofire control, idle hacking readiness, authoritative victory and exact current-run score.
- Manual one-release weapon queues, distinct beam endpoints, ion/hack/resource facts and airlock topology.
- `owned-player-crew-v1`: original native crew IDs, ownership/location/control fields, hostile rejection and ownership-aware survival counts.
- `native-economy-and-fuel-recovery-v1`: exact system/reactor prices, caps, affordability and UI legality; native Wait/distress actions and visible recovery state. No approximate price or independent Lua scrap deduction remains.
- Native event choice type/availability, keyboard timing/settings and explicit selection feedback. Disabled and already pending selections are rejected; input delay is preserved.
- `native-sector-neighbors-v1`: verified native neighboring-sector indices, explicit leave acceptance/refusal and routing capability/version gates.
- `native-beacon-readiness-v1`: native button/full-timer/system/fuel/context readiness, pending-defeat guidance and strict jump feedback, with additive native/Lua capability gates.
- `native-enemy-hostility-v1`: authoritative combat/targeting facts, guarded weapon queues and a friendly-aware native sector restriction.
- Verified seeded Kestrel A/easy setup, confirmed navigation, explicit victory gating, retained terminal errors and unique run directories.
- Public OpenAI Responses and separately labeled Jev typed choices, explicit environment files, model telemetry and a read-only packaged dashboard.

The complete current patch is `native/patches/0002-economy-fuel-controls.patch`, pinned by `native/manifest.json`. Current local artifacts are `dist/Hyperspace.protocol5.dll` and `dist/native-build.protocol5.json`. The build manifest records actual source/diff, patch hash, toolchain/container and DLL SHA256. Protocol-4 history remains at `native/manifest.protocol4.json`, the original `0001` patch, `dist/Hyperspace.protocol4.dll`, `dist/native-build.json` and its byte-identical `dist/native-build.protocol4.json` copy.

The current Windows x86 protocol-5 DLL SHA256 is `bfc72a7fbfb7aaf599b824b59eda80cdbfe8afc9d1f81d140ab2dff8a492f6d6`. It includes both version-1 sector-navigation and beacon-readiness markers; the API remains protocol 5. The v7 source suite has 731 passing tests; current release packaging checks are recorded separately. GCC Release native routing/readiness regressions passed, and the Windows DLL compiled with Clang 12/MinGW. The provenance helper hashes every patched file, including untracked headers, and includes their content in the source-diff hash. Native upgrade/recovery checks remain under `harness/runs/validation/native-protocol5/`; the earlier sector-only fixture under `harness/runs/validation/native-sector-routing-v5/` is historical and comparison-excluded. V7 retains strict native button/full-timer/system/fuel/context readiness for both travel actions; pending defeat is guidance only, never an independent prohibition on charged legal travel. Release checks and artifact hashes are recorded separately in `dist/package-validation.json`. No full-game win is established by these unit/fixture checks.

The retained v6 live fixtures passed: `harness/runs/validation/native-beacon-readiness/` verifies partial-charge refusal, normal enemy death/reward credit, modal-free post-reward charging refusal and a charged one-fuel escape. `harness/runs/validation/native-sector-routing/` verifies all seven sector transitions from index 0 through 7, full native charge before each departure, exact one-fuel charges and off-exit refusal. These fixtures are comparison-excluded; the sector fixture supplies the exit-location prerequisite and is not a full-game run.

The current v7 hostility fixture passed on the exact recorded DLL and Lua: `harness/runs/validation/native-enemy-hostility/` verifies normal hostile fire and native kill/reward credit, a natural surrender with its bribe reward, a retained friendly ship marked `hostile: false, targetable: false`, and rejected weapon requests without ammunition loss even after 720 native frames. A fully charged friendly sector exit advanced index 0 to 1 and consumed one fuel. Combat/surrender checks used no state injection; sector departure supplied only the exit-location prerequisite. The fixture is excluded from model comparisons, and all six original save hashes were restored.

## Historical validation

The v6 trial was stopped after an accepted surrender left a friendly ship serialized as targetable for repeated turns. Its final native score was 81, with two confirmed jumps and hull 28; there was no real game over or victory. V6 artifacts and release checks are preserved at `dist/releases/protocol5-before-target-validity/` and superseded for comparison. V7 adds `native-enemy-hostility-v1`, using the native hostility flag for combat, targeting, queued weapons and the sector enemy restriction. The native API and bindings remain protocol 5.

The v5 trial was stopped after ordinary beacon jumps bypassed native readiness at partial charge and interrupted defeated-enemy cleanup/rewards. Its runtime evidence is diagnostic; the d443 DLL, Lua6f, packages, prompt, patch/provenance and release checks remain at `dist/releases/protocol5-before-beacon-readiness/`. V6 adds a separate beacon-readiness contract and marker while retaining native API protocol 5.

The preceding v4 trial was stopped after sector exit used a random sector type (0–2) as a global sector-vector index. It is diagnostic, with its exact runtime artifacts preserved. V5 requires a corrected native marker and explicit routing contract; native API protocol 5 alone does not prove compatibility. Pre-routing package/native build evidence is archived under `dist/releases/protocol5-before-sector-index/` and is superseded for current comparisons.

The retained v3 GPT-6.1-Sol/Codex CLI trial is `harness/runs/validation/gpt-6.1-sol-codex-v3/20261002T180050Z-ed0317356b`. It completed 89 turns and 21 confirmed jumps, reached sector index 1, and conceded at fuel 0 with hull 19 and three living owned crew. Native score was 329: 69 collected scrap + 40 for two kills + 220 for 22 explored beacons. There was no native game over or victory. `validation.json` verifies crew control, all 91 scored snapshots among 93 observations, and archived Lua/DLL/prompt hashes. `save-restoration.json` records original-save restoration. This trace is `diagnostic_only`: missing event availability, approximate upgrade prices and missing fuel recovery prevent a current model comparison. Its score is not a ranking row.

An earlier pre-v3 Sol trial exposed and moved a hostile boarder through direct native movement. It was stopped and retained at `harness/runs/validation/gpt-6.1-sol-codex/20261002T173602Z-e672cf6f23`. V3 repaired that control boundary; v7 retains it.

Historical Jev v2 validation remains at `harness/runs/validation/final/20261002T133446Z-865cd6722e`, including `recomputed.json` and `validation.json`. A model-error attempt scored 20; the retry reached native crew-loss game over with hull 21 and score 59: 19 scrap + one kill + two explored beacons. The probability-tolerance error was subsequently fixed. The score formula matched all 35 scored snapshots, and retries started at score 10 without carryover. This validates historical score/reset/loss behavior, not a v7 model row. The old protocol-4 DLL hash was `af7764153578b616eb50be3566ba88ac1b9cfbd181515974cc8c2a032bfe0d9e`.

The earlier v3 package passed 390 checkout/source-release tests and isolated installed CLI/UI/native-patch smoke checks. Those artifacts and checks are historical; protocol-5 release evidence is recorded separately.

## Reporting limits and remaining work

Only Kestrel A/easy is selected and verified automatically. Full-run solve requires explicit `victory: true`; ordinary game over, concession and raw boss-stage counters do not prove a win. Intermediate completed flagship phases remain unavailable.

Native nullable economy costs/reactor may be omitted by the Lua codec. Missing cost means unknown/unavailable, never free. `can_upgrade` and recovery legality remain authoritative. `waitfuel` requests a normal recovery turn, with encounter/fleet consequences; frame waits do not substitute for it or guarantee fuel.

Pre-v7 rows are noncomparable. Report all control/economy/routing/beacon/hostility contracts plus suite, tier, mode, prompt, native artifacts, backend/decision contract and retries. Jev remains `jev-actuator-choice-v1`; OpenAI Decisions preview remains unsupported without its schema.

Next work is fresh public baseline/model rows and then held-out comparisons. Optional sector-choice, flagship surge, breach and special-system coverage needs representative traces. macOS needs an equivalent native build and live validation. No retained full-game win or held-out reference rows are established here.

No push, release or site publication is part of these local validation steps.
