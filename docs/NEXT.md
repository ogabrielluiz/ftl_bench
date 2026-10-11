# Current validation and next work

**WIP / alpha. Snapshot: 2026-10-11 05:46 UTC (02:46 in São Paulo).**
Nine of 36 challenge cells finished in the preserved original cohort. The sector pilot ended in native defeat;
Sol/image full-game was cooperatively stopped at 276 decisions after a confirmed
native store-arrival blocker froze warp. Three full-game cells remain unstarted.
The original failed run restored all seven saves and its 15 baseline paths. No
fixture-free full-game ending or complete model comparison has been established.
The original checkout and failed cohort remain frozen; development continues on
`main`.

The replacement DLL passed the protected natural store-arrival regression at
05:28 UTC: 243 frames to arrival, one frame to resolve Continue, zero simulation
updates at the visible store, and a successful native CLOSE click. Independent
review checked 110 archived artifacts, all input packets, the new six-file runtime
and exact restoration of all seven saves, with no game left running. This covers
the reproduced defect only. Fresh startup, nine timing probes, independent
rejection checks and local admission have now passed. Replacement cohorts are
frozen as described below. See [store-arrival diagnosis](native-store-arrival.md).

## Implemented and verified scope

| Area | Evidence and limits |
| --- | --- |
| Visual play | Authenticated Codex CLI receives archived native PNGs and returns bounded mouse/key inputs. Native protocol 5, visual clock 2 and `fresh-start-seed-v3` are integrated. |
| Observation modes | Image-only play and hybrid HUD numerals extracted from the same PNG; no hidden native-state fallback. The comparative model trials remain incomplete. |
| Repeatable setup | Nine no-model fixture-6 probes passed measured starting-state and step equality across three wall delays. This covers the tested inputs, not every hidden RNG stream or full-game determinism. |
| Protected lifecycle | Save backups, exact restoration, runtime identities and terminal evidence are recorded. Cooperative-stop probes passed before the actor and during one real CLI request; the returned cancelled response was retained and its actions discarded. |
| Challenges | Frozen 36-cell controller, versioned public tasks, outcome audits, retained failures and exact replays. Nine Sol/image cells are complete; results are below. |
| Full-game support | Fixture-free startup and the five-cell controller are implemented. Startup preserves the opening choice. The pilot ended in audited native defeat after 78 decisions; the Sol/image full-game attempt was interrupted by a confirmed harness store-arrival defect. |
| Dashboard | Saved challenge/full-game overviews, exact screenshots and inputs, outcome reasons, task identities and saved cleanup receipts. The dashboard is read-only. |

The visual track is `visual-v1`; historical structured runs retain runner/ruleset
v7 and their own contracts. Do not pool their scores or treat a diagnostic fixture
ending as a fixture-free full game.

## Replacement cohorts and local admission

The repaired runtime's collection is
`harness/runs/validation/visual-v1/main-admission-20261011T053058Z` in the
integration checkout. Fixture-free startup and all nine timing trials passed,
including equality across delays of 0, 0.35 and 1.2 seconds for each challenge.
Raw verification joined 541 evidence files, 78 executable source pins, the common
six-file runtime and all 12 reconstructed native source files. Its receipt
SHA-256 is `8ba525a10d1d9acdccd21e20ed5762db38fc6bda59338551fa899aec6234630c`.

A separate reviewer agent executed eight isolated mutations. Source, bridge,
DLL, original build timestamp, runtime baseline, trial inventory, dispatched
capture identity and cleanup-process alterations all failed their intended
checks. The untouched baseline passed again. Reviewer identity and the shared
collaborating environment are disclosed in `review/review.json`. Independent
cleanup review also matched all ten probe inventories, all seven live saves and
the current runtime, with no FTL process remaining.

`controller-admission-result.json` grants local controller admission while
retaining `production_accepted: false`. It joins 565 evidence files and the same
78 source pins. The admission spec SHA-256 is
`f10dd5787e90f628902069bb54bdb5e3c5b7ea3bcf4ec668479d1154179cfcb3`.
This measured path does not establish unrestricted gameplay or model performance.

New cohorts under `harness/runs/validation/visual-v1/`:

| Cohort | Protocol SHA-256 | Planned scope |
| --- | --- | --- |
| `matrix-portable-store-v1-20261011` | `571a892136eae9206c45f1925b04e104f69dfc1b4981d159d0a397d245673ba0` | 36 challenge cells, Sol then Luna, image and hybrid, three repetitions |
| `fullgame-portable-store-v1-20261011` | `8210928ecb549c85aebc260165d6db00fb52a19ec8c86a1991f5cd8978f54723` | Sol/image sector pilot followed by four native-ending conditions |

At freeze, all cells were planned. Sol/image combat repeat one started at
05:43:35 UTC and passed protected child admission before the first Codex CLI
model call. It is running at this snapshot, with 35 challenge cells and all five
full-game-controller cells still planned. The read-only dashboard on port 8768
reports both new cohorts without catalog issues. Prior results below belong to
their original runtime and are not pooled into these replacement cohorts. No
new completed result or full-game child admission is claimed yet.

## Preserved challenge results

Cohort: `harness/runs/validation/visual-v1/matrix-task-v2-stop-v1-20261011`.
Protocol SHA-256:
`9cab4b1629ebefef5f6686d3865ea19966793a2d6013801d471e51a14f062087`.
All 76 source/runtime pins matched the retained archive and original checkout at
the 02:55 UTC preflight. These pins do not describe merged `main`.

All completed cells requested `gpt-6.1-sol`, image mode, Kestrel A/easy, seed 1,
medium reasoning, 60 decisions, 1,800 seconds and eight consecutive empty
zero-frame decisions. The [protocol](visual-experiment-protocol.md) defines the
remaining controls, setup, audit and exclusion rules.

| Challenge | Repeat | Decisions | Terminal reason | Task success |
| --- | --- | ---: | --- | --- |
| Combat | 01 | 38 | `idle_decision_budget` | No |
| Combat | 02 | 34 | `native_game_over` | No |
| Combat | 03 | 8 | `fixture_goal_observed` | Yes |
| Fire / crew recovery | 01 | 4 | `fixture_goal_observed` | Yes |
| Fire / crew recovery | 02 | 3 | `fixture_goal_observed` | Yes |
| Fire / crew recovery | 03 | 9 | `fixture_goal_observed` | Yes |
| Repair / charge / escape | 01 | 11 | `idle_decision_budget` | No |
| Repair / charge / escape | 02 | 4 | `fixture_goal_observed` | Yes |
| Repair / charge / escape | 03 | 4 | `fixture_goal_observed` | Yes |

This is six task successes, two budget stops and one native crew-loss ending.
Per-challenge success is 1/3, 3/3 and 2/3 respectively. All nine saved individual
audits pass with no exclusions. The overall comparison remains unqualified:
nine Sol/hybrid, nine Luna/image and nine Luna/hybrid cells are still planned.
These small fixed-seed samples establish no model ranking or hybrid advantage.

Failure details matter. Combat repeat 01 let the enemy escape without its reward;
raw native `destroyed` and kill-counter changes alone do not prove a kill.
Repeat 02's final screen reports all crew dead; oxygen was 1%, but the precise
death mechanism is not established. Repair repeat 01 departed and spent fuel,
but did not establish the required repaired, powered, fully charged drive state
before departure. These outcomes remain in the denominator; they are not
silently retried or converted into infrastructure errors.

Each completed cell has a saved gate under `gated-audits/`, joining its terminal
artifacts to verification of all seven original saves at cleanup. The last gate
is dated 2026-10-11 02:17:36 UTC. These are point-in-time restoration checks; the
documentation review did not repeat a live save audit. Requested model IDs,
available token usage and response latencies are retained. Resolved backend
weights and cost are unavailable and must not be inferred.

## Full-game WIP

Cohort: `harness/runs/validation/visual-v1/fullgame-stop-v1-20261011`.
Protocol SHA-256:
`da498515a486baf0eff09564f880342106ce2e156d3a65a24df1b468f844c1fc`.
All 78 source/runtime pins matched at the 03:23 UTC terminal audit. The declared cells are:

1. Sol/image sector-one pilot, native defeat at 03:21 UTC.
2. Sol/image full game, cooperatively interrupted at 04:52 UTC after 276 decisions.
3. Sol/hybrid full game.
4. Luna/image full game.
5. Luna/hybrid full game.

The pilot ran from 02:56 to 03:21 UTC and ended in sector index 0 after 78
decisions. Its final native observation records game over, no victory, hull
13/30, oxygen 0 and the last crew member at zero health. The 03:23 UTC terminal
audit checked 79 unique PNGs with no integrity issues, verified all seven
original saves and all 15 baseline paths, and confirmed the recorded child and
FTL had exited. This is an audited pilot defeat; it contributes zero completed
full games. The failed outcome and all model responses remain preserved.

A retrospective artifact review at 04:02 UTC found concrete model control
mistakes in the pilot. `O` opened Options; decisions 30 and 37 closed doors when
the model intended venting, while decision 32 opened doors when it intended
sealing. The inputs were delivered and their effects were observed. Later
repair deployments and delayed retreats exhausted crew health; medbay healing
and movement also had observed effects. The final PNG explicitly reports all
crew dead. No screenshot, input transport or clock defect was confirmed; oxygen
0% alone does not prove the precise death mechanism. The review passed 78
decisions and 79 PNGs and checked recorded restoration artifacts, without a new
live-save audit. Its local receipt is
`provisional-audits/sol-image-pilot-loss-analysis-20261011T040223420853Z.json`
under the full-game cohort. The pilot remains excluded from full-game totals.

The controller rechecked pilot cleanup at 03:40:11 UTC before launching the
first full-game cell. A provisional artifact check at 04:37 UTC passed 219
completed decisions and the 78 source pins, but did not detect the semantic
stall. Its preserved receipt is
`provisional-audits/sol-image-active-20261011T043732076403Z.json`. Artifact integrity
alone does not prove gameplay can progress.

Independent review of the 04:50 UTC snapshot found decision 151 spent one fuel
and advanced 122 frames toward a store. The native state then stayed jumping
with `store_open`; decisions 152–268 requested 46,621 frames and advanced zero.
Exact screenshots show an empty starfield, without the ship or store dialog.
The shipped blocker treated the hidden store as visible, cancelling the updates
needed to finish arrival. The confirmed defect and proposed repair are documented
in [native-store-arrival.md](native-store-arrival.md).

The official stop was requested at 04:51:58 UTC and observed after an actor call,
before action dispatch. The child completed protected cleanup at 04:52:10 UTC;
its result remains `interrupted` / `cooperative_stop_requested`. The controller
refused to continue to hybrid. A separate post-exit audit passed all retained
artifact checks, all seven live saves and the exact inventory, all 15 original
baseline hashes, and found no FTL process. Receipt:
`dist/store-warp-diagnosis-20261011/interrupted-cleanup.json` in the integration
checkout. The interruption contributes zero full-game completions and must not
be reported as a model defeat or budget failure. Runtime changes require new
prospective cohorts; do not resume this frozen cohort with a replacement DLL.

The declared settings are seed 1, medium reasoning, 300 decisions, 14,400 seconds
and eight idle decisions. Only audited native victory or defeat completes a
fixture-free full game. Pilot results, budget exhaustion, interrupted attempts
and a native loss inside a challenge fixture do not satisfy that requirement.
One attempt per condition will remain descriptive, not a broad ranking.

## Validation evidence and distribution limits

The accepted cooperative-stop package snapshot passed **1,849 tests with ten
Windows skips** (eight host C++ compiler checks and two symlink checks). Its
installed-wheel CLI/helper/dashboard smoke checks passed. The receipt is local:
`dist/fresh-start-v3-production/package-validation-cooperative-stop/receipt.json`,
SHA-256 `7ad330cbfc438132f7e0cbba6cd681b32daa050ef9b10b8aea8a8267b81087dd`.
Its 102 wheel and 176 source-release mappings matched that tested snapshot.
Subsequent documentation edits mean that receipt does not certify byte identity
of packages rebuilt from this commit. No new package release is implied.

Separate checks passed ten native executables, including 72 fresh-start cases,
and 17 dashboard tests plus its build. These scopes do not establish complete
gameplay. The main integration adds dashboard tests before CI/release builds
and runs the headless output-contract regressions in the harness CI matrix.

The historical local visual DLL starts with SHA-256 `a33b9984`; its original
identities are retained in frozen source archives, the native build provenance and
`dist/native-validation.visual-v1.json`. The latter receipt's SHA-256 is
`2fe556557cc00a2cfa23cb0cd67a58e21ac9b4209b1126c669d588b5f90c97da`.
Runtime admission checks the exact accepted files, not the prefix in this note.

`dist/`, generated packages, native binaries, raw runs and credentials are
intentionally absent from Git. A fresh checkout contains source, tests and
documentation, but the frozen experiment controllers additionally require the
locally generated acceptance receipts, referenced evidence and matching installed
FTL/runtime. The local `dist/run_guarded_matrix.py` supervisor is not shipped.
Portable acquisition/build/validation of this evidence remains WIP; documented
`freeze` commands are not a promise that a clean clone is immediately runnable.

The new [portable evidence workflow](native-acceptance.md) supplies protected
no-model startup and varied-delay timing producers, plus a file-only verifier.
It binds source bytes, native build identity, the deployed bridge, PNGs, raw
input packets and trial-specific cleanup receipts. Its finite probe result
does not grant controller admission or production acceptance. The first fresh
collection on merged `main` passed startup and all nine timing probes, followed
by independent cleanup verification at 03:39:23 UTC. Its local evidence is
`harness/runs/validation/visual-v1/main-native-20261011-0330/` in the integration
checkout. The verifier joins 516 evidence files and 73 source pins and reports
`validated_scoped`; `production_accepted` and `controller_admission` remain false.
The verification receipt SHA-256 is
`bae852ffd816b7a3e6ff789ad710ae891ceab651d4a5944d315dce0fe16dc3a3`.
The independent check also matched all seven live saves, all 15 baseline paths
and the six runtime assets shared by all ten diagnostics, with no game left
running. These finite measured paths do not establish full-game determinism.
The later replacement collection above refreshes local admission for the repaired
runtime. This older receipt remains pinned to its original source and DLL.

Subsequent verifier hardening requires a common six-file runtime across all ten
diagnostics and supports authenticated reconstruction of the complete native
patch. A file-only collection at
`dist/native-source-proof-20261011T0406Z/` authenticated 14 Git objects and
reconstructed all 12 patched files; every hash matched the existing DLL's source
provenance. Its verification receipt SHA-256 is
`5c510cd6949cb942c336b36ab14f613fbfa5c6aa01e0bb5681d0b4a165ac7536`.
No compiler, installation or game launch was involved. These source changes
require fresh source-bound diagnostics before prospective controller admission;
the earlier main collection remains evidence for its original pinned sources.
The local harness suite after this hardening passed 2,017 tests with ten
platform/compiler skips. These offline checks do not replace fresh diagnostics
or the remaining model trials.

Portable v2 challenge/full-game controllers now accept an explicit admission
specification and evidence root. They recompute the scoped raw verifier, join
all reconstructed native source bytes to original fresh or historical build
records, and require a hash-bound independent review with eight negative-probe
records. The build records and reviewer independence declaration are explicit
trust inputs; this is not a build-execution or cryptographic identity attestation.
The scoped verifier still reports `production_accepted: false`.

Freezing exclusively archives all consumed evidence and executable sources.
Controllers reject missing, changed, additional or unreadable archive content.
Inside protected children, six installed asset hashes, deployed Lua and actual
model/mode/seed/reasoning/budgets/cell output must match before model calls.
Accepted and rejected gates are retained in `controller-admission.json`; rejected
gates use normal protected cleanup. Saved-result audits require the bound child
gate, and the dashboard exposes stored evidence identities with their limited
scope. The legacy v1 cohorts keep their original behavior.

The first real collection, independent review and v2 freezes passed at
05:41 UTC. The first Sol/image combat child subsequently passed its live
admission gate. The [workflow](native-acceptance.md) gives the schemas and commands.
Source changes require new diagnostics and review. Admission does not replace
the 36 replacement challenge cells or the four native-ending full-game conditions
in the benchmark goal.

The final local controller-admission suite passed **2,247 tests with 12 explicit
skips**: eight unavailable host C++ checks, three Windows symlink checks and one
opt-in authenticated-source flow. That last flow passed separately with the
retained Git-object proof: real raw validation, admission, freezing and relocated
archive verification, using clearly synthetic build/review records. It proves
offline integration, not live acceptance. All 18 dashboard tests and its build
passed, as did the documentation build, isolated installed-wheel CLI/dashboard
smoke and extracted source-release checks (2,194 passed, 65 checkout/platform
skips). No game, model call or runtime installation was part of these checks.

## Main integration

The visual progress is merged with the existing headless Linux/Docker work on
`main`. Shared code retains Linux process detection, headless reset-completion
markers, WSL-to-Windows CLI output paths and enriched crew observations alongside
the visual lifecycle and ownership checks. The package keeps `main`'s version
`0.2.0`; this merge does not publish a new release.

The historical nine-cell snapshot above still belongs to its original frozen
sources. The integration was performed in a separate checkout, preserving the
original `visual-benchmark-progress` checkout and raw evidence. Merged source
bytes differ from those pins: experiments on merged `main` require fresh
acceptance and a new frozen cohort, not reuse of the old cohort under new code.

Initial merge validation at `5a20e79` passed 1,853 harness tests with ten platform skips on
Python 3.13.5, and the same suite from the extracted source release on Python
3.14.8. The installed-wheel smoke, 17 dashboard tests, dashboard build and
documentation-site build pass. The standalone economy, routing and fresh-start
native executables pass in WSL; the fresh-start executable covers 72 cases.
The 25 headless output-contract checks also pass, including nested/legacy
artifacts, budget caps, retries, missing/invalid evidence, output overrides and
Bash syntax. They run separately from the package suite because the Docker
launchers are checkout-only files. The parallel launcher preserves earlier
outputs and propagates failed shard/aggregate status.

Live Linux/headless compatibility and complete visual games remain WIP; neither
is established by merging source or passing offline tests. The headless docs
retain the existing Linux restart and scratch-save limitations. No game or model
run was part of that integration validation. The goal subsequently resumed in
the unchanged original checkout, as recorded above.

The dashboard now allows a balanced planned-to-running count lag while a
full-game controller is active. It labels those counts provisional and retains
strict joins for completed outcomes, native endings and cleanup. The controller
also checks the actual original save inventory instead of requiring the seven
files present on the development machine; an explicitly empty profile is valid,
but missing receipts, changed bytes and unexpected live saves still fail.

[CI at `b862afd`](https://github.com/ogabrielluiz/ftl_bench/actions/runs/38108757217)
passes Python 3.11 and 3.13 on both platforms: 2,004 harness tests with two skips
on Windows, 2,001 with five skips on Linux, plus 25 headless checks in each job.
The package job passes its installed-wheel smoke, dashboard/docs builds and
1,954 extracted-source tests with 52 skips. Of those, 47 explicitly require a
source checkout for native evidence verification; bundled packages instead test
that this guard refuses admission. The remaining skips are platform checks.
Separate local package evidence is preserved under
`dist/package-native-evidence-20261011T033059Z/`. These packages precede this
documentation snapshot, and no new release is published.

## Remaining work

1. Finish and audit the first admitted challenge trial, then exercise the
   full-game child gate and broader gameplay checks. Executable changes require
   a new evidence collection.
2. Execute the replacement 36-cell challenge matrix, sector pilot and four
   fixture-free full-game conditions sequentially. Preserve every attempted
   outcome and stop for technical failures or ambiguous cleanup.
3. Report matched conditions with denominators, exclusions, outcome reasons,
   latency and available usage. Keep incomplete games distinct from native endings.
4. Make native acceptance/evidence setup reproducible from a fresh checkout,
   validate the merged headless runtime, and revalidate any
   changed implementation and rebuild packages before release.

Use the [experiment controller commands](visual-experiment-protocol.md#freezing-and-resumption)
and [full-game sequence](visual-experiment-protocol.md#full-game-progression).
Stop through the owning controller's cooperative `stop` command and keep it
alive until protected cleanup finishes. Never rerun a started cell or remove a
durable stop request to make a cohort continue.

## Historical evidence

The [preserved validation history](validation-history-2026-10-11.md) contains the
prior development narrative, superseded cohorts, timing/RNG investigations,
task-v1 false-negative, manual recovery and package receipts. Its intermediate
"current" and "running" statements are historical. Original raw artifacts remain
unchanged; later repairs never rewrite their outcomes.
