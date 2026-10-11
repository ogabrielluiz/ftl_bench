# Visual benchmark acceptance and comparison protocol

Status: WIP; experiments paused. At 2026-10-11 02:32 UTC, nine of 36 challenge
cells were complete and all five full-game cells were unstarted. No complete
model/observation comparison or fixture-free full-game ending is established.
See [current results and remaining work](NEXT.md) for the dated status and
[validation history](validation-history-2026-10-11.md) for superseded evidence.

## Preserved cohort and prospective repairs (2026-10-11)

The `matrix-fresh-v3-20261011` cohort, protocol `551c712f...`, is stopped and its
raw artifacts and frozen sources remain preserved. Sol image-only combat
repetitions succeeded in 13, 16 and 13 decisions, with final hull 28/30, 26/30
and 23/30 and all three crew alive. These are scoped challenge results.

Fire repetition one exposes a false-negative: the public task requested full
health for the initially injured crew member, while the evaluator required all
crew at full health. The initially injured crew recovered from 50/100 to 100/100.
The retained validation reports the latter check false,
with the other fire, oxygen and survival checks true, and an idle-budget ending.
Do not turn that mismatch into an aligned-task model loss or silently relabel its
raw result. The prospective `fire-crew-recovery-task-v2` now explicitly requires
all crew to reach full health, including injuries sustained during firefighting.

Fire repetition two was stopped by the assistant operator, not at the human's
request. The execution-session interrupt abruptly terminated Python before its
cleanup handler; raw `run.json` remains running and the trajectory lacks a
terminal end. Its separate `operator-recovery/receipt.json` records manual
recovery at 2026-10-11 01:16:01 UTC, with automatic cleanup explicitly false.
Independent read-only verification matched seven original live saves and their
exact inventory, all 15 baseline paths, preserved raw artifact hashes and the
restoration receipt, with no remaining FTL process. This establishes recovery,
not graceful interruption or completed gameplay. The ledger retains this cell
as interrupted/unknown.

This cohort cannot resume after source repairs. The separate unstarted full-game
protocol `873bd288...` is likewise superseded prospectively by shared-source
changes; retain it without launching its cells on changed sources. Cooperative
cancellation and task-v2 alignment are now implemented and packaged. The accepted
cooperative-stop package receipt is
`dist/fresh-start-v3-production/package-validation-cooperative-stop/receipt.json`
(`7ad330cb...`): 1,849 extracted-source tests pass with ten explicit skips, and
102 wheel/176 source-release source files matched that frozen package revision.
Later documentation edits are not covered by that package byte-identity claim.
Prior package receipts and artifacts remain preserved.

The replacement challenge cohort is `matrix-task-v2-stop-v1-20261011`, protocol
`9cab4b1629ebefef5f6686d3865ea19966793a2d6013801d471e51a14f062087`,
with 76 verified archived source pins. All three Sol image combat trials share
the canonical initial gameplay signature (`1759586d...`) and are scoped eligible,
with no exclusions and complete issue-free audits.

| Combat repeat | Terminal reason | Decisions / PNGs | Task success | Final hull |
| --- | --- | --- | --- | --- |
| 01 | `idle_decision_budget` | 38 / 40 | False | 17/30 |
| 02 | `native_game_over` | 34 / 36 | False | 19/30 |
| 03 | `fixture_goal_observed` | 8 / 10 | True | 27/30 |

The measured result is 1/3 scoped combat successes, not a ranking or fixture-free
full-game proof. Repeat three has enemy hull 0, `fleeing: false`, an 18-scrap
reward (player scrap 48), and all three crew alive, with lowest health 71.91/100.
Its saved gate at 02:02:48 UTC joins trajectory `cbe0f4e8...00c7a` and seven
original save backups to point-in-time live restoration.
Repeat one's escape without reward at record 22 remains a task failure; raw
engine `destroyed`/counter increments alone are not kill proof or a wrong-score
formula. Repeat two's final PNG reports all crew dead, oxygen 1%, and native
remaining crew health 0; its precise death mechanism is unproven. Its final
advance stopped after 589 of 600 requested updates. The prior saved gates
(`7542a634...afea64b` trajectory for repeat one; `3d04a6d9...` gate for repeat two)
retain their cleanup scope. All three gate receipts are under
`gated-audits/gpt-6.1-sol__image__combat__repeat-0N.json`. These are historical
point-in-time cleanup checks; supporting usage and failure details remain in the
[validation history](validation-history-2026-10-11.md) and raw reports.

At 2026-10-11 02:32 UTC, all nine Sol/image cells were finished and the other
27 cells were planned, with no benchmark process live. Combat had 1/3 task
successes, fire/crew recovery 3/3 and repair/charge/escape 2/3. The nine outcomes
comprise six task successes, two idle-budget stops and one native crew loss.
All nine individual audits passed with no exclusions, but the overall comparison
remains unqualified until the missing conditions are evaluated. The last saved
cleanup gate is dated 02:17:36 UTC. Source pins are unchanged.
The separately frozen `fullgame-stop-v1-20261011` protocol
`da498515a486baf0eff09564f880342106ce2e156d3a65a24df1b468f844c1fc`
has 78 verified archived pins and all five cells planned at that snapshot.
The remaining matrix and native-ending full-game sequence are paused. A native
loss inside a challenge fixture does not complete a fixture-free full game.
Unavailable cost and resolved backend identity are not estimated. Current counts
are a dated snapshot, not a live monitor; preserve all failures when work resumes.

### Cooperative stopping and task identity

Request a stop through the owning controller, keeping its process alive for
normal protected cleanup:

```powershell
python scripts/run_visual_experiment.py stop --output <challenge-directory> --initiator operator --reason operator_requested
python scripts/run_fullgame_experiment.py stop --output <fullgame-directory> --initiator operator --reason operator_requested
```

The `visual-cooperative-stop-v1` request records its ID, scope, initiator, reason
and timestamp. The runner retains the observed boundary and request in its raw
terminal evidence; a cancelled response cannot become delivered gameplay input.
The supervisor stops continuation after cleanup. Do not substitute execution-
session termination for this command: abrupt termination can bypass cleanup, as
the preserved fire repetition-two evidence demonstrates.

Protected live probes at `cooperative-stop-challenge-20261011` and
`cooperative-stop-fullgame-20261011` published the official request at the first
`before_actor` boundary after native startup. Both made zero model calls and
dispatched zero actor actions, retained matching raw stop requests, and passed
normal automatic cleanup with seven originals, all 15 baselines and no remaining
game process. These probes establish that boundary only.

The separate `cooperative-stop-cli-20261011` live receipt (`822720df...`) verifies
one real authenticated Sol CLI call: the same child process identity was live
before and after publication of the official stop request. The response returned
and was retained as `model_cancelled`; the runner observed the request at
`after_actor_before_dispatch` and discarded the response's actions. One real
model call and zero dispatched actor actions are recorded. The raw terminal,
request/call metadata, save restoration and all 15 baseline checks passed.
This is cooperative cancellation with retained response evidence, not a claim
that the CLI was forcibly terminated. It establishes that observed path only,
and no gameplay completion or model-performance result.

Public tasks are versioned separately from fixture mechanics. The prospective
fire task is `fire-crew-recovery-task-v2`; combat and repair remain task-v1.
Protocols pin the task-version map and exact public text hashes, and the
challenge driver rejects stale contracts before startup or model spending.
The fire evaluator still requires all living crew at full health; the repaired
task now states that requirement. Historical task-v1 raw outcomes remain intact.

## Objective and completion evidence

The target is reliable full-game execution through Codex CLI, repeatable visual
challenges, fair Sol/Luna and image/hybrid measurements, and inspectable dashboard
replays. Model victories and a hybrid performance gain are measured outcomes,
not prerequisites for declaring the infrastructure reliable.

| Requirement | Evidence needed |
| --- | --- |
| Core gameplay | Three recorded repetitions of combat, fire/crew recovery, and repair/charge/departure under each declared condition; verified prerequisites, native outcomes, retained failures. |
| Attribution | Exact actor images, instructions and outputs; input acknowledgements and clock accounting; separately identified infrastructure, screenshot, control, protocol and tactical problems. |
| Complete games | First-sector trial followed by uninterrupted games ending in native victory or defeat; terminal reports, native terminal state/image, exact save-restoration receipts. Budget cutoffs do not prove a complete game. |
| Fair observation comparison | Screenshot-only HUD reader acceptance, frozen extraction version, matched setup/seed/actions/budgets, three paired repetitions and explicit exclusions. |
| Both models | Sol and Luna receive the same scenario instructions, controls, memory, effort and budgets; report success, survival, native score where meaningful, latency and available usage. |
| Inspectability | Every trial has a replay, immutable source/runtime identities, outcome/reason, receipts, reproduction command and clearly scoped comparison/report. |

## Challenge matrix

The planned matrix contains 36 cells: `gpt-6.1-sol` and `gpt-6-luna`, image and
hybrid modes, three challenges, and three repetitions. Sol conditions run first,
as requested; execution order is recorded and is not randomized. This local
sample describes these fixed situations, not general model capability.

Each challenge uses Kestrel A on easy, seed 1. Each cell allows 60 decisions,
1,800 wall-clock seconds, and eight consecutive empty zero-frame decisions.
Existing controls allow four inputs and at most 600 native simulation frames
per decision. The actor keeps its own last eight actions and a 1,200-character
memory. Reasoning effort is medium. The same limits apply to both models and
both observation modes. Wall limits are safeguards; they do not consume native
game time during inference.

The active `ftl_visual_v2.md` manual states the fixed-time interface: 60 admitted
updates represent one declared simulation second, and 600 represent ten. Its
only changes from the preserved v1 manual are the version header and this timing
sentence. Both models and observation modes use the identical manual.

The scenarios have public, fixed tasks. Setup may use explicit diagnostic
prerequisites before the first actor observation. Thereafter all actor gameplay
uses ordinary mouse and keyboard controls. Exact setup actions/mutations and the
resulting native state are archived outside actor inputs:

- Combat starts at a fixed hostile seed-1 encounter. Outcome checks require
  authoritative native enemy destruction and survival, not merely weapon clicks.
- Fire/crew recovery starts at the pristine starting beacon, with a seeded native
  fire in the oxygen room and one crew member at half health. Native fire
  extinction, full living-crew recovery and restored oxygen establish completion.
- Repair/charge/departure starts at the pristine starting beacon, with damaged
  engines and an empty drive timer. Native system health, full charge, and
  confirmed arrival establish completion. This does not establish escape while
  under enemy fire. The damage request is recorded separately from actual missing
  health bars; the native damage-progress field alone cannot prove repair.

Current fixture version 6 owns the fixed clock before native ship construction
and all prerequisite actions. `fresh-start-seed-v3` initializes native and DLL
C-runtime randomness exactly once before `ShipBuilder::Open` constructs the
new ship; the verified clean-start receipt records the classified startup
utility lookup, empty real crew factory, orphan-name reset and same-thread seed
applications. There is no late encounter, fire-placement or fixture reseeding.
The diagnostic fixture clears initial drive charge once for all three starts
and enemy weapon charge once for combat, with actual before values archived.
All later gameplay follows admitted fixed-frame budgets. The exact prerequisite
actions, mutations, receipts and starting-state signatures accompany each trial.

Nine no-model fixture-6 probes passed the rederived initial and corresponding
step gameplay signatures under three wall delays, with independent image,
packet, seed, frame and cleanup checks. The accepted record is
`dist/deterministic-setup-candidate/challenge-repeatability-acceptance-v2.json`.
It covers measured combat damage, fire progression and oxygen control/progression
in the repair fixture. It does not establish challenge task completion, internal
RNG-stream equality, model performance or general full-game reproducibility.

### Historical fixture-5 race repair and combat divergence

Fixture version 5 retained version 4's initial charge mutations and seeded
native randomness during setup, including immediately before fire placement.
Its first-capture repair and subsequent divergence are preserved below; new
cohorts use fixture 6 and the pre-construction seed boundary.

Version 5 fixes a first-capture race. The fixture wrapper calls the production
tick exactly once, then initializes only after a valid initial zero-frame
visual request has been admitted and before rendering. The first returned
capture must already contain the applied fixture; an uninitialized first image
is rejected rather than polled past. No actor input, prompt, production bridge,
native DLL or subsequent gameplay mutation changed. Three live reproduction
repeats pass after the fix. That nine-trial timing run records matching fire
and repair repetitions, but combat diverges at the 12-second impact despite
matching recorded starts and preceding states. Its overall acceptance is false;
that historical run is not acceptance for a replacement model cohort.

Matching uses the recorded gameplay signature, not byte-identical screenshots.
Cosmetic crew names and rendered animation phases may differ and remain visible
in the archived images. Exact repeated observed states along the timing probes
do not establish equality of hidden RNG streams or full-game determinism.

The live prerequisite checks must validate these proposed starts before the
matrix is frozen. A setup failure is an infrastructure outcome, not a model
failure. A model loss or budget cutoff remains a recorded trial and cannot be
replaced silently by a better attempt. Reports distinguish delivered inputs from
their intended gameplay consequences.

## Freezing and resumption

These commands assume the configured harness environment and accepted local
native runtime/evidence are already present. A clean Git checkout does not
contain `dist/native-validation.visual-v1.json`, its referenced acceptance
artifacts or the native DLL. Portable setup of that evidence is still WIP; never
fabricate acceptance receipts or bypass admission to make `freeze` succeed.
For a new challenge cohort, from the repository root:

```powershell
harness/.venv/Scripts/python.exe scripts/run_visual_experiment.py freeze --output harness/runs/visual/challenges-sol-luna-001
harness/.venv/Scripts/python.exe scripts/run_visual_experiment.py run --output harness/runs/visual/challenges-sol-luna-001 --limit 1
harness/.venv/Scripts/python.exe scripts/run_visual_experiment.py report --output harness/runs/visual/challenges-sol-luna-001
```

`scripts/run_visual_experiment.py freeze --output <new-directory>` records the
matrix, budgets, native DLL/build, CLI identity, actor/runner/fixture sources,
prompt and HUD-reader assets. `run --output <directory> --limit <N>` executes at
most N new cells sequentially, with one protected game per cell. The default is
one cell. `report --output <directory>` recomputes the saved comparison.

The controller refuses changed sources or changed matrix identities. It uses a
live process handle with creation time when reconciling an interrupted parent;
an old PID, missing log update or stale lock file does not establish completion.
A started cell is never automatically rerun. Missing terminal evidence remains
an interrupted/unknown result. Cleanup must verify save restoration before the
controller starts another trial.

The first clock-v2 matrix is preserved at
`harness/runs/validation/visual-v1/matrix-clock2-20261010`, protocol SHA-256
`fec304cf123a51d8734f01eb68f70afc872479b9aff3162a9449e05c4c739791`.
It pins 63 source/runtime files. Sol image combat repetitions 1 and 2 achieved
their tasks. Repetition 3 failed before any model decision because the fixture
could change the state and publish another screenshot after the initial capture.
The guarded supervisor stopped immediately. A separate no-model live probe and
actual-Lua offline reproduction confirmed this race. The strict stale-capture
guard was correct. This incomplete cohort and its exact `frozen-sources` remain
historical; do not resume it with repaired sources or rewrite its outcomes.

The optional local supervisor `dist/run_guarded_matrix.py` performs that same
one-cell sequence automatically, without changing frozen experiment sources.
It is an ignored development helper, not a shipped checkout command; use the
tracked controller above unless that separately reviewed helper is available:

```powershell
harness/.venv/Scripts/python.exe -u dist/run_guarded_matrix.py --output <new-frozen-matrix-directory>
```

Run only one supervisor/controller at a time. Start it only when the preceding controller has exited and no FTL process
remains. It re-audits completed cells before resuming and checks every new cell
before admitting the next: terminal artifact integrity, scoped comparison
eligibility, original live-save hashes, unchanged production bridge and process
cleanup. Native losses and budget stops remain legitimate recorded outcomes;
technical failures, interference, interruption or ambiguous state stop the
sequence without retrying or discarding the attempt. `gated-audits/` retains
the successful audits, the supervisor hash and the protocol identity. Four
offline gate tests cover allowed losses/budgets, rejected technical failures,
corrupt evidence, and the requirement for current live-save verification.

Fixtures are scoped diagnostic comparisons, separate from full-game scores.
Qualifying a challenge cohort requires matched starting gameplay state and
compatible actor/runtime/protocol identities, not an unrelated full-game win.
Historical pilots with different prompts or native builds remain separate.

## Observation boundary

Image mode supplies the exact native PNG, the fixed task/interface instructions,
and the actor's own bounded history and memory. Hybrid additionally supplies
only HUD numerals recognized from that same PNG. It has no native-state fallback.
Unknown layout, dimming, overlap, partial glyphs or unsupported formats must omit
the affected value. Maximum hull, hidden health/oxygen values and unrendered
resource data are not admitted.

Hybrid acceptance requires independently reviewed pixel examples, malformed and
occluded examples, hash/crop provenance and tests that hidden native changes
cannot affect extraction. Capture and extraction identities are retained in
replays. The reader stays frozen throughout the comparison.

## Full-game progression

`scripts/run_fullgame_experiment.py` implements the separate
`ftl-fullgame-experiment-v1` protocol. From the checkout root, use the configured
harness environment; these commands freeze a new output, run at most one new
cell by default, and recompute the report from saved artifacts:

```powershell
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py freeze --output <new-fullgame-directory>
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py run --output <fullgame-directory> --limit 1
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py report --output <fullgame-directory>
```

The recorded order is fixed:

| Order | Requested model | Observation | Objective |
| --- | --- | --- | --- |
| 1 | `gpt-6.1-sol` | image | Pilot through sector index 1 (`--stop-after-sector 1`). |
| 2 | `gpt-6.1-sol` | image | Full game. |
| 3 | `gpt-6.1-sol` | hybrid | Full game. |
| 4 | `gpt-6-luna` | image | Full game. |
| 5 | `gpt-6-luna` | hybrid | Full game. |

Every cell uses seed 1, medium reasoning, 300 decisions, 14,400 wall-clock
seconds and eight consecutive empty zero-frame decisions. The ordinary visual
limits remain four inputs and at most 600 admitted updates per decision. Each
protected child uses mandatory fixture-free fresh-start v3 admission: the actor
receives the untouched opening choice in its first archived screenshot. No
challenge fixture or prerequisite gameplay is inserted. A pilot loss or cutoff
remains an audited attempt; reaching sector 1 is reported separately and is not
required by the controller to admit the later full-game attempts. The pilot is
excluded from full-game totals.

`freeze` pins source, prompt/schema, Codex CLI, native acceptance and the tested
runtime baseline, and copies the pinned bytes into `frozen-source`. In particular,
all five installed files (`FTLGame.exe`, `ftl.dat`, `Hyperspace.dll`,
`xinput1_4.dll`, `lua-5.3.dll`) must match the hash-pinned accepted baseline.
Source/runtime changes require a new cohort. `run` verifies these identities
before each new cell, retains process creation identities, refuses an existing
trial directory and never automatically reruns a started cell. Only one
controller may own the output at a time; stop any preceding game/controller
before starting this sequence.

The audit joins requested conditions to actual per-call model and reasoning
settings, recorded effective budgets, actor instructions/schema, CLI/runtime
identities, native fresh-seed receipts and the canonical first image. Response
model identity is retained only when supplied; a requested CLI name does not
independently identify the resolved weights. Terminal input/capture accounting,
final screenshot/report and cleanup must also agree. A full game is complete
only when an integrity-passing completed terminal record has `native_victory`
with native `victory: true`, or `native_game_over` with native `game_over: true`
and no native victory. Decision, wall or idle cutoffs are preserved incomplete
attempts. Technical errors, interference, interruption or ambiguous child state
block continuation; they do not authorize a retry or count as a loss.

Before continuing, the controller checks the seven original live saves and exact
save inventory against the protected backup, requires no remaining FTL process,
and retains an exclusive timestamp/UUID receipt under
`cleanup-checks/<cell-id>/`. Each receipt binds the protocol/controller, terminal
artifact hashes, trajectory snapshot, child verification and point-in-time live
cleanup; its path and hash are appended to the ledger. Rechecking creates a new
receipt rather than overwriting an earlier one. `comparison.json` separates
attempts, verified native victories/defeats and incomplete full games. Larger
budgets or repaired sources require a newly declared protocol. One seed and one
attempt per full-game condition do not establish a ranking or general full-game
reproducibility.

## Reporting

Publish observed outcomes and denominators, individual repetitions, latency
distributions and native token-usage fields with coverage counts. Requested
model IDs are recorded; an actual served model ID is reported only if the CLI
supplies it. No estimated price, missing usage as zero, unavailable event count,
or inferred victory is allowed. Paired summaries retain every exclusion and
show both modes' outcomes. The sample is too small for broad ranking claims.

The dashboard accepts saved challenge (`ftl-visual-challenge-matrix-v1`) and
full-game (`ftl-fullgame-experiment-v1`) protocols. The full-game overview shows
the pilot and all four conditions, including waiting/running cells, exact replay
links, available usage and saved cleanup timestamps/hashes. Pilot and budget
outcomes remain separate from native completion. A verified native-ending label
requires a complete nested audit without issues, matching five artifact hashes
from a hash-joined cleanup receipt, and agreement between the raw trajectory's
terminal record, final native observation and saved lifecycle. Missing or
contradictory evidence leaves verification/totals unavailable. The overview is
read-only and performs no live save/process audit or model scoring; its cleanup
checks describe the saved point in time. Individual replays retain archived
images, inputs and model records. Replay availability alone does not establish a
complete game, model ranking or comparison eligibility.

Prompt or harness repairs create a new frozen cohort. Preserve the evidence
that motivated them and distinguish pixel/control defects from a model's
tactical decisions. Documentation and dashboard summaries must never promote
an incomplete run, a fixture prerequisite, or input delivery into proof of
successful full-game play.

## Prerequisite evidence and timing limitation (2026-10-10)

The nine setup-only runs in
`harness/runs/validation/visual-v1/challenges-pristine-setup-20261010`
passed their scenario prerequisite checks and restored all seven original save
files. They used fixture version 3 and no model calls. Only the repair scenario
had identical gameplay signatures across all three repetitions. Combat differed
in initial charge fractions, and fire placement differed in the number of native
fire tiles. These runs therefore do not establish matched model-comparison starts.
Earlier store-based starts and their failed checks are also preserved.

Visual clock version 1 freezes world updates during inference and counts explicit
updates, but each permitted update still uses a variable native wall-time factor.
Equal frame budgets therefore do not prove equal simulated durations. Archived
version 1 DLL, sources, and receipts are retained in
`dist/releases/visual-v1-before-fixed-step`; historical acceptance is limited to
the exact update-count and control claims it tested.

Clock version 2 and fixture version 4 passed
`harness/runs/validation/visual-v1/timing-clock2-all-20261010`: three repetitions
per challenge with identical ordinary inputs and delays of 0, 0.35 and 1.2 seconds.
All initial states and corresponding scripted-step native signatures matched.
Root independently recomputed all 96 step signatures from the archived native
trajectory observations and checked frame accounting and exact restoration of
all seven original saves. Each idle check requests a fresh zero-frame native
capture; a cached observation cannot establish the freeze. These are no-model
timing/setup checks, not evidence of model task success or full-game determinism.

The former full-game initialization limitation applied the map seed after
native hangar crew creation; the [seeding review](full-game-seeding-review.md)
preserves that evidence. Production visual startup now integrates the verified
v3 pre-construction native/CRT seed boundary, controlled construction timing and
fixture-free first-image admission. The no-model live startup check
`fullgame-startup-v3-production-20261011-v3` passed admission, verified the first
PNG, kept opening choices visible for the actor and verified cleanup. The first
two diagnostic probe errors were extra evaluator assertions using the wrong
event field; their raw records remain preserved. Repeated full games, native
win/loss endings under model control and matched full-game model/observation
comparisons remain unproven. Startup acceptance does not close those requirements.
