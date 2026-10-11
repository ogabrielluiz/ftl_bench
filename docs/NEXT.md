# Current validation and next work

**WIP / alpha. Challenge snapshot: 2026-10-11 13:07:21 UTC; stop review: 13:10 UTC; full-game milestone: 14:24 UTC.**

## Prospective configurable full-game budgets

The controller now accepts freeze-only positive-integer `--max-decisions`,
`--max-wall-seconds` and `--max-idle-decisions`. Defaults remain 300 / 14,400 / 8;
one frozen budget applies to the pilot and all four model/mode conditions.
Runtime overrides and malformed or unrepresentable values are rejected.
The focused controller suite passes 169 tests, covering custom/default freezes,
all five child commands, validation before side effects and tamper rejection.

This executable change is not yet admitted for model measurements. The active
`d1c18b8` trial and its source checkout remain unchanged. If a larger budget is
needed, collect fresh startup/timing evidence and independent admission, then
freeze a new complete four-condition cohort. A prospective 1,500 / 86,400 / 8
example is documented in the [protocol](visual-experiment-protocol.md); it has
not been launched and does not guarantee native endings. Preserve all prior
attempts and report cohorts separately, with all Sol calls before Luna.

## Current admitted cohorts (`d1c18b8`)

Executable commit `d1c18b8fd5a9ac67a1e27da56dd9343a2ec86943` has fresh collection
`main-admission-policy-audit-20261011T110830Z`: eight startup checks, nine timing
equality probes, protected cleanup and eight executed independent negative cases
passed. Admission binds 78 source files and 565 evidence files. The 31 original
native-build/source-proof inputs remain byte-identical with their original
identities and timestamps; reuse is disclosed, not a new build or compiler proof.
`production_accepted` remains false. Admission-spec SHA-256:
`f5315fce5623e6d0bc9c7f1234c5433ad74d4be50e70dfff2b02452377f2d876`.

Both new cohorts are under `harness/runs/validation/visual-v1/`:

| Cohort | Embedded protocol SHA-256 | Protocol file SHA-256 | Snapshot |
| --- | --- | --- | --- |
| `matrix-main-d1c18b8-20261011` | `ccbbb3379639b39af98eb4941139ec3bdb25c312db90641b03e62c1b54680010` | `1d8b42799d7cdf4171a86f6070197d9b3662f84d80b7eee6f234eaa24f922e8f` | 18 Sol finished; 18 Luna planned |
| `fullgame-main-d1c18b8-20261011` | `7bcba8d7391bb42db40012888c6153425e2afb9ffe12700560e03b84143df9ec` | `9129cfc04d9173b77acfced1a35fcab5053384767b6ddb4ce04f6a7758e708b6` | Pilot defeat excluded; Sol/image verified defeat; Sol/hybrid running; two Luna planned |

All 18 Sol challenge trials are finished and independently reviewed: image 5/9,
hybrid 6/9 task successes, all 18 eligible, zero exclusions and seven preserved
budget failures. Luna's 18 cells remain planned; both comparison qualification
flags remain false. These finite outcomes establish no population or model ranking.

| Mode / challenge | Task successes | Eligible | Calls / PNGs | Latency (seconds) |
| --- | --- | --- | --- | --- |
| Image / combat | 1/3 | 3/3 | 112 / 118 | 2,013.810 |
| Image / fire | 2/3 | 3/3 | 22 / 28 | 354.355 |
| Image / repair/charge/escape | 2/3 | 3/3 | 22 / 28 | 309.484 |
| Hybrid / combat | 2/3 | 3/3 | 64 / 70 | 1,225.414 |
| Hybrid / fire | 3/3 | 3/3 | 11 / 17 | 196.808 |
| Hybrid / repair/charge/escape | 1/3 | 3/3 | 28 / 34 | 400.066 |

The seven budget failures followed three enemy escapes (image combat 01/02,
hybrid combat 02), one incomplete crew heal (image fire 02), and three departures
before full engine repair (image repair 02, hybrid repair 02/03). The repair
attempts made real fuel-consuming arrivals, but charged engines at 1/2 health
did not satisfy the full-repair requirement. Saved control/evidence checks passed;
the model failures remain in the totals.

All 259 calls report usage and latency: 295 audited PNGs, input 4,869,278
(cached subset 3,149,440; cache-write 0), output 67,474 (reasoning subset 23,739),
and latency 4,499.937 seconds, including failed tasks. No reconnect calls or
notices occurred. Requested model is Sol; resolved backend identity is unreported.
The exclusive checkpoint is `d1c18b8-sol-18-checkpoint-20261011T1305Z/`:
summary SHA-256 `31191d737b693cb59ebf9fb1d89b64463ac56ffc0ede93dd6255d1d834793159`,
comparison `74dab40c444baa9bec354fff60ffb29f7d24b3459c2636f1714aa17c2bc4532d`,
ledger `ca1b88a5ee46676793d244eefc09d62e5b412f38e31fb8fd8fe6ea07c6771bd9`.
The summary binds all 18 independent review hashes and per-group token totals.

Current cleanup passed at 13:04:56 UTC, before the next diagnostic: exact seven
original saves, prior bridge, six runtime files, source pins and no FTL process.
Receipt `d1c18b8-sol-boundary-current-cleanup-review.json` SHA-256:
`00f84686968ad21d761a5bc4568b4c6493f463205300b25c06826c471fb7adaa`.

### Current-stack cooperative interruption

The separate `fullgame-stop-d1c18b8-20261011T1305Z` diagnostic passed scoped
in-flight cancellation. The same CLI process was observed before and after the
official validation stop request at 13:07:41 UTC. Six decisions had been delivered;
call seven completed normally and its proposed click was retained, then cancelled
at `after_actor_before_dispatch` at 13:07:48 UTC. No further inputs, simulation
advance or screenshot capture were dispatched; absent after-image and actual-frame
fields remain null, rather than being relabelled as measured zero. All four later
cells remain planned. Seven calls report usage and latency, separately from the
18 scored challenges; this diagnostic contributes no full-game ending.

Recorded admission, actor joins and seven-save restoration passed. Independent
current cleanup at 13:08:49 UTC verified the seven originals, prior Lua, six runtime
files, source pins and no FTL. The rendered dashboard at 13:10 UTC shows an
interrupted pilot, the retained response, restored saves and zero native endings.
The uncaught `CooperativeStop` exception produces child exit `3221225786` on this
Windows host; the controller exits `1` to refuse interrupted continuation. This
nonzero exit is a documented stopping limitation, not a successful controller run.
No process was killed and the diagnostic will not be resumed or retried.

Local receipts in `dist/store-warp-diagnosis-20261011/`:
`d1c18b8-inflight-stop-final-review.json` (SHA-256
`fb9652352cfc92639dc5b89500e4e4d381b8a61970cbc9d0d403874d39a2bd06`),
`d1c18b8-post-stop-current-cleanup-review.json` (SHA-256
`4c574c7e47da12314beb1f02514c742abe1da24cc6552376ad249bc266af9530`),
and `d1c18b8-post-stop-rendered-ui-review.json` with its screenshot.

### Preserved nine-image subset

Canonical initial native gameplay matches across all six starts per challenge
(image and hybrid), checked in `d1c18b8-sol-initial-signature-scope-review.json`. Matching
starts do not establish deterministic later trajectories or pixel-identical
observations. The initial repair PNG differences were confined to CHARGING and
PAUSED label/caption intensity (under 0.9% of pixels); animation/glow phase is
plausible, not instrumented proof. See
`d1c18b8-repair-initial-observation-variation-review.json`.

All nine independent saved reviews exist under `dist/store-warp-diagnosis-20261011/`,
named `d1c18b8-sol-image-{combat,fire,repair}-{01,02,03}-final-review.json`.
The two combat budget failures followed enemy escapes. Fire repeat 02 left one
crew member at 76.48/100 health while the model claimed everyone was healed.
Repair repeat 02 made a connected jump with fuel use, but engines remained at
1/2 health: its sole unmet gate was `repaired_powered_full_drive_observed`.
The model prematurely declared completion and idled. Repeat 03 observed 2/2
engine health, power and full charge before a connected jump, fuel 16 to 15,
hull 30 and all crew at 100. Its independent review arrived at 12:24:33 UTC
(SHA-256 `cb627a00700a01cb8e6e6908f8e27c01833c58f849e16e5205a147ac34a18e57`).
The preserved nine-image subset and all nine review hashes are in
`d1c18b8-sol-image-nine-summary.json` (SHA-256
`826c27daf97f738714269a9b380fdd3040d6088ede4533690fdc7e28e39aa5f5`). It binds an exact copy of the
subsequent live rollup; that copy also contains newer trials outside this subset.

The first trial's current-cleanup/UI reviews at 11:42:58 / 11:43:42 UTC checked
seven original saves, prior bridge, six runtime files, no FTL and the eligible
budget outcome. Later saved reviews check recorded restoration, not current
live cleanup while the supervisor runs. Admission/negative/freeze receipts remain
`d1c18b8-admission-cleanup-review.json`, `d1c18b8-independent-eight-probe-review-result.json`
and `d1c18b8-cohort-freeze-review.json`. One current hybrid request passed ten checks
in `d1c18b8-first-hybrid-observation-review.json`: exact actor PNG supports fuel 15,
scrap 30, missiles 8 and drone parts 2; provenance and public prompt match, with
no native fallback and hull omitted. `paused=true` is a separate control invariant.
That earlier receipt covers one request; the 18-Sol checkpoint above now binds
the nine completed hybrid trials, without qualifying the full comparison.

### Full-game milestone (2026-10-11 14:24 UTC)

The main pilot finished at 13:38:53 UTC with audited native defeat after 62 calls;
it remains excluded from full-game totals. Its reported input is 1,175,359 tokens
(cached subset 770,048), output 18,849 (reasoning subset 7,523), latency 1,281.388
seconds (median 21.099), with no reconnects. Saved review at 13:41:26 UTC:
`d1c18b8-sol-pilot-final-review.json`, SHA-256
`5ac66fc073487a43a41a7a6d77c0755a9f79f2a5e78c21f6fdf677f0b867d0e4`.

Sol/image full game finished at 14:17:38 UTC with `native_game_over`: all crew
lost, hull 26/30, oxygen 0%, score 81 from `native_live_v1`. It made two jumps,
remained in sector 0 and recorded one observed enemy defeat. The native ending,
78 calls / 79 PNGs, input/action/frame/history joins and child admission passed
independent review; seven original saves were restored. All 78 calls report
input 1,470,354 (cached subset 968,320), output 21,920 (reasoning subset 8,100),
latency 1,558.339 seconds (median 19.016), and no reconnects. Resolved model
identity remains unreported. This is **1/4 verified full-game endings**, not a win
or a population/model ranking; full comparison and general determinism remain unproven.

Independent current cleanup at 14:18:23 UTC checked the seven originals, prior
bridge, six runtime files, source pins and no FTL before hybrid launched. The
rendered final UI passed at 14:19:34 UTC. Saved final review at 14:21:55 UTC and
native-fields addendum at 14:22:15 UTC remain separate: the addendum corrects
initial null oxygen/health projections to `oxygen_pct` / `health_current`, without
changing the verdict or original artifacts. Exact local receipts:

| Receipt | SHA-256 |
| --- | --- |
| `d1c18b8-sol-image-fullgame-final-review.json` | `c15e76d6a612e59131b3636abacd212f1ba3323334c42895c791915398d1de87` |
| `d1c18b8-sol-image-fullgame-final-review-native-fields-addendum.json` | `56d2f1a4162ce4f0a9ee36d5e80d5b73088b5fd0a1e63745291dae4b026325d5` |
| `d1c18b8-sol-image-fullgame-current-cleanup-review.json` | `fc686c477a5fdd00e5c6fa9d57edcc3d350fc4c4260af1da0f17677b94ff6fd5` |
| `d1c18b8-sol-image-fullgame-final-ui-review.json` | `25cb602ae985ef20be8c286861d40234caaba21e8cabbd6d17864eee177fef8b` |
| `d1c18b8-sol-hybrid-fullgame-startup-review.json` | `74028e2ab1793895f56be276ab089eebf56c210f662552f1adc6a0b46f648b57` |

Sol/hybrid started at 14:23:06 UTC and is running at this snapshot; two Luna
full games remain planned. Its bounded startup review at 14:24:09 UTC confirms
canonical initial gameplay matches Sol/image while PNG bytes differ. Exact PNG
pixels support fuel 16, scrap 30, missiles 8 and drone parts 2; hull is omitted,
and `paused=true` is a control invariant. This prefix review claims no ending
or current live cleanup for the active trial.

The 18-Sol challenge checkpoint remains 11 successes, seven budget failures and
18 eligible trials; Luna's 18 challenge cells are planned. The strict challenge
supervisor finished its declared cells through official `--limit 1` calls.
The full comparison, remaining three native endings and actual clean-build/setup
reproduction remain WIP; older failures remain separate without retries or pooling.
Official FTLMan v0.7.3 archive/executable verification receipts are now in setup
`dist/clean-setup-inputs-20261011/ftlman-v0.7.3/`, dated 14:22 UTC. Acquisition and
local hashing only, with no execution, do not establish clean build or installation.

## Preserved `463c340` admission (10:47 UTC snapshot)

Commit `463c340069df9ab1c7786bf6cc0c7b07ab1e8017` passed all five jobs in
[CI run 38132428078](https://github.com/ogabrielluiz/ftl_bench/actions/runs/38132428078).
Fresh collection `main-admission-cli-recovery-20261011T103548Z` passed startup's
eight checks, all nine timing equality probes and protected cleanup, followed by
eight actually executed independent negative review cases. Controller admission
joins 78 executable sources and 565 evidence files. All 31 original native-build
and authenticated source-proof inputs were reused unchanged; original timestamps
and identities remain intact, with reuse disclosed. This is not a new native build
or compiler proof. `production_accepted` remains false.

Admission-spec SHA-256:
`a107aa8d76e92c81d804f0b6bac3adcd7a13922da33c908857efd43b91076885`.
Both new cohorts are under `harness/runs/validation/visual-v1/`:

| Cohort | Embedded protocol SHA-256 | Protocol file SHA-256 | Snapshot |
| --- | --- | --- | --- |
| `matrix-main-463c340-20261011` | `8ff0aeb34e8bc69a5738dff9129cfb749fd793126b530cbb9786b628035d30bd` | `1e8889fea6fb7b580bc902af87673a48f5c57135a4e381f741a1f1be586a209f` | All 36 planned |
| `fullgame-main-463c340-20261011` | `818ffe2ff97bd0f610fdae4d6a7de7c545cdf5a38ae3a5d336f61879ac4d4b46` | `19fd8ed08f5460418e719473d45d319a681029761cc0272a622965cfbc74c877` | Pilot plus four conditions planned |

No model calls have run in these cohorts at this snapshot, and fixture-free
native-ending completion remains **0/4**. Their source-bound [recovery policy](cli-recovery.md)
does not retry or reinterpret any old failed cell. Next: review frozen archives
and rendered planned UI, then run the first Sol cell prospectively. Keep cohorts
separate; report completed-turn usage separately from unknown aborted internal
sampling usage. Clean-build/setup reproduction and full comparative/native-ending
requirements remain unfinished.

### First trial and saved-audit repair

At 10:53:51 UTC, the first Sol/image combat cell completed with
`fixture_goal_observed`: 13 decisions, 15 audited PNGs, hull 27/30, all three crew alive,
and the native combat goal achieved. The visible kill dialog and settled reward
show 18 scrap, three fuel and one missile received. Current exact seven-save
inventory, prior Lua bridge, six runtime files and no-game-process checks passed.
The matrix now retains one finished cell and 35 planned; the five full-game/pilot
entries remain planned. This challenge success does not complete a full game.

The original comparison records zero eligible and one excluded trial because the
new reporter incorrectly treats absent top-level trajectory actor metadata as a
legacy-policy declaration. The challenge producer writes that header before actor
construction; its manifest, frozen experiment and all actual model records carry
the correct modern policy. The first false rejection causes the subsequent history
mismatches. This is a reporting defect, not thirteen independent actor failures.

The prospective fix uses the manifest policy and checks every present declaration,
without requiring optional carriers absent from real challenge or standalone runs.
All-missing historical policies still use strict legacy behavior. It preserves
provisional auditing before a final report exists. The focused suite passed 301
tests, including challenge-shaped multi-step history and conflicting declarations;
the actual saved 13-decision trace passes a separate read-only re-audit. Original
run/report/comparison bytes and their exclusion remain unchanged. Changed reporting
sources require fresh admission and new freezes before further model calls.

All 13 calls report usage: input 245,915 (cached subset 164,736), output 3,916
(reasoning subset 1,599); recorded latency totals 231.364 seconds, median 18.728.
No reconnect notice occurred. Local evidence is under
`dist/store-warp-diagnosis-20261011/`: `463c340-sol-image-combat-01-final-review.json`,
`463c340-sol-image-combat-01-current-cleanup-review.json`, and
`463c340-sol-image-combat-01-completed-ui-review.json`. The first receipt preserves
the original failed audit; the UI correctly exposes its exclusion.
The separate `463c340-sol-image-combat-01-derived-audit-review.json` reanalysis
binds the prospective reporter, verifies all 13 decisions and 15 PNGs, and
derives eligibility and task success with no saved child-admission issues.
Its eight original artifact guards remain byte-identical; it does not replace
the saved comparison or authorize further trials on changed sources.

## Preserved `2174cc9` results (10:19 UTC snapshot)

At the 09:25 UTC challenge boundary, the admitted `2174cc9` matrix has all 18
Sol cells finished and 18 Luna cells remaining: **17 eligible, 12 task successes, five budget failures and one
preserved technical exclusion**. All five full-game/pilot entries were planned
at this boundary; fixture-free native-ending completion remains **0/4**.
At 2026-10-11 09:50 UTC, the Sol/image sector pilot has completed in native
defeat in sector index 0: 53 decisions, 54 PNGs and score 20. Saved integrity,
admission, recorded restoration, current cleanup and rendered UI reviews passed.
The pilot contributes zero full-game completions; all four full-game conditions
remain planned and native-ending completion remains **0/4**.
At 10:08 UTC, Sol/image full-game attempt one ended with `visual_model_error`
after 46 decisions. Call 47 recovered inside Codex CLI and exited zero, but the
frozen parser rejected its preceding reconnect notification. This is a preserved
technical interruption, not a native ending; full-game continuation is held by
the controller and three later conditions remain planned. See the
[recovery policy and evidence](cli-recovery.md). Fresh admission/new cohorts
are required for the changed actor and reporter; no old trial is retried or
retroactively accepted.
Challenge usage covers 198/199 calls, so complete token totals remain unknown. The
comparison is incomplete and unqualified; the retained image/fire repeat-one
exclusion also prevents that four-condition pair from qualifying after Luna
finishes. The static admission recheck passed after the frozen-source bytecode
incident below, and the nine hybrid cells finished without a new technical error.

The preserved `078a5e2` cohort remains separate: nine Sol/image cells finished,
with six task successes, two idle-budget failures and one technical exclusion;
eight have eligible evidence. Failed-call usage remains unknown. All saved
cleanup checks passed, including the last live check for that batch. Its pause
led to the prospective CLI evidence fix and fresh admission below, without
silent retries, relabelling or pooling. Older stopped full-game and diagnostic
runs remain historical; see the [store-arrival diagnosis](native-store-arrival.md).

## Implemented and verified scope

| Area | Evidence and limits |
| --- | --- |
| Visual play | Authenticated Codex CLI receives archived native PNGs and returns bounded mouse/key inputs. Native protocol 5, visual clock 2 and `fresh-start-seed-v3` are integrated. |
| Observation modes | Image-only play and hybrid HUD numerals extracted from the same PNG; no hidden native-state fallback. The comparative model trials remain incomplete. |
| Repeatable setup | Nine no-model fixture-6 probes passed measured starting-state and step equality across three wall delays. This covers the tested inputs, not every hidden RNG stream or full-game determinism. |
| Protected lifecycle | Save backups, exact restoration, runtime identities and terminal evidence are recorded. Cooperative-stop probes passed before the actor and during one real CLI request; the returned cancelled response was retained and its actions discarded. |
| Challenges | Frozen 36-cell controller, versioned public tasks, outcome audits, retained failures and exact replays. The dated `2174cc9` cohort has all 18 Sol cells finished; separate historical nine-cell results are below. |
| Full-game support | Fixture-free startup and the five-cell controller are implemented. Startup preserves the opening choice. The historical pilot ended in audited native defeat after 78 decisions; its subsequent Sol/image full-game attempt was interrupted by a confirmed harness store-arrival defect. The dated `2174cc9` pilot completed in audited native defeat after 53 decisions. The Sol/image full-game attempt then stopped with a preserved CLI protocol error after 46 decisions; three later conditions remain planned, and native-ending full games remain 0/4. |
| Dashboard | Saved challenge/full-game overviews, exact screenshots and inputs, outcome reasons, task identities and saved cleanup receipts. The dashboard is read-only. |

The visual track is `visual-v1`; historical structured runs retain runner/ruleset
v7 and their own contracts. Do not pool their scores or treat a diagnostic fixture
ending as a fixture-free full game.

## Preserved admitted cohorts (`2174cc9`)

Commit `2174cc9704343f91e7d527a6a9f6961eb741be81` passed all five jobs in
[CI run 38121156672](https://github.com/ogabrielluiz/ftl_bench/actions/runs/38121156672).
Fresh collection `main-admission-cli-evidence-20261011T072857Z` passed scoped
fixture-free startup, all nine timing probes, eight independent negative review
cases and controller admission joining 78 executable sources and 565 evidence
files. Independent review verified both source archives, all ten cleanup
inventories, current seven original saves, restored bridge and six-file runtime,
with no FTL process remaining at the check. The original native build and source
proof were reused unchanged, with their original identities and reuse disclosed;
this is not a new native build or compiler proof. `production_accepted` remains
false. Local cleanup receipt:
`dist/store-warp-diagnosis-20261011/CLI-evidence-admission-cleanup-review.json`.
Admission-spec SHA-256:
`1cf47ca6c7bc6de2bf8cfcb122b117219dc3f67c4e9c7df08f3f50d212124192`.

Both frozen cohorts are under `harness/runs/validation/visual-v1/`. Embedded
protocol identities and hashes of the complete `protocol.json` bytes differ:

| Cohort | Embedded protocol SHA-256 | Protocol file SHA-256 | Snapshot |
| --- | --- | --- | --- |
| `matrix-main-2174cc9-20261011` | `14b187e91c25d675f3f9e1c532f4dfa6ec75d137334dc62e122f9a254118b613` | `b04b9dab9e7f85b24c092f9b53117238506dd5cc5a75f66e4b8368a94ac2910e` | 18 finished, 18 Luna remaining |
| `fullgame-main-2174cc9-20261011` | `0714ba2975bc1b1fa37ff09a0be85087fda35037e237cc3a15ca4631b590935d` | `53b5b6cac94aef5b9177381b1a103abc14b6b991e656bebe296a71ceeb4288ac` | Pilot native defeat; Sol/image technical interruption; three conditions planned |

### Preserved results and retained failure

At the 09:25 UTC boundary, each row has three attempted repeats per mode:

| Challenge | Sol/image: success / budget / excluded | Sol/hybrid: success / budget / excluded |
| --- | --- | --- |
| Combat | 2 / 1 / 0 | 3 / 0 / 0 |
| Fire recovery | 1 / 1 / 1 | 1 / 2 / 0 |
| Repair-charge-escape | 3 / 0 / 0 | 2 / 1 / 0 |

All nine hybrid trials are eligible. All 79 actual hybrid model rows have
non-null visible-summary provenance, with saved PNG/HUD derivations verified.
Fire failures retain injured firefighters after premature full-health claims;
repair repeat two jumped with one engine bar still damaged. Native task gates
withheld success despite otherwise genuine recovery or arrival. Independent
ending-PNG, input/frame, native-outcome and seven recorded-save restoration
checks passed for every closed hybrid trial. These are saved-only checks, not
current live-state verification or proof of backend model weights.

Independent boundary cleanup passed at 09:26:01 UTC, followed by the actual
browser UI review. Their local receipts are
`dist/store-warp-diagnosis-20261011/2174-main-sol-challenges-current-cleanup-review.json`
and `dist/store-warp-diagnosis-20261011/2174-main-sol-challenges-ui-review.json`.
These dated reviews precede the separately completed pilot.

The saved comparison file SHA-256 is
`d99b098399ce91e4450b2c4c276710f0b6fe333e6315b89b0bd892c47ce9c243`,
separate from the embedded protocol identity above. Compact local receipt:
`dist/store-warp-diagnosis-20261011/2174-main-sol-18-saved-boundary-review.json`.
Sol/image and Sol/hybrid have eight eligible descriptive mode pairs out of nine;
none of the nine declared four-condition pairs is yet qualified because Luna
is unstarted. Fire repeat one additionally retains its technical exclusion.
These fixed-seed samples establish no model ranking or general hybrid advantage.

All 199 Sol calls have recorded latency, totalling 3,152.904 seconds. Usage is
reported for 198 calls: observed input 3,720,079 (cached subset 2,423,040), output
50,386 (reasoning subset 18,237). The excluded image/fire call has unknown usage,
so these observed sums are not complete totals. Hybrid alone has complete usage
for 79 calls: input 1,476,793 (cached 1,006,976), output 16,756 (reasoning 5,133),
and 1,130.195 seconds recorded latency. Cached and reasoning counts are subsets.

All three Sol/image combat repeats are eligible with no exclusions: repeat one
reached the 60-decision budget without task success; repeats two and three
succeeded after 11 and 16 decisions. Fire repeat one completed three decisions
before its fourth CLI subprocess exited 1 (`visual_backend_error`,
`infrastructure_failure`). Its bounded retained stdout records workspace routing
discovery failure and `turn.failed`. The failed call dispatched no actions.
Its usage is unavailable, so complete fire token totals are unknown rather than
zero. This evidence does not establish a general outage or quota failure.

Saved per-cell reviews are `2174-main-combat-01-final-review.json`,
`2174-main-combat-02-final-review.json`, `2174-main-combat-03-final-review.json`,
and `2174-main-fire-01-final-review.json`; exact retained failure-stream review is
`2174-main-fire-01-cli-evidence-review.json`, all under
`dist/store-warp-diagnosis-20261011/`. The current cleanup review
`2174-main-fire-01-error-cleanup-review.json` passed at 08:26:44 UTC: all four
started cells' backups/restoration matched the seven original saves; current
saves, prior bridge and six runtime files matched baseline, with no FTL process.
Both protocols and their 78-source/565-evidence archives remained unchanged.
This is a dated check; continuation was held at the 08:31 snapshot.

A separate text-only connectivity diagnostic succeeded at 08:31:50 UTC using
the frozen CLI, Sol and medium reasoning (11.071 seconds, strict audited JSON
with no tools). It remains outside the benchmark. Following review, only
unstarted cells continued; fire repeat one was not retried. Its exclusion and
unknown failed-call usage remain preserved. Sol/image fire finished with one
success, one idle-budget failure and that technical exclusion; repair finished
with three successes. Saved batch/UI receipts include
`2174-main-sol-image-ui-review.json` and `2174-main-sol-hybrid-01-ui-review.json`
under `dist/store-warp-diagnosis-20261011/`.

Sol/hybrid combat repeats one, two and three succeeded after 10, 10 and 13
decisions respectively. The first trial's rendered first input
summary shows fuel 15, scrap 30, missiles 8 and drone parts 2, with hull explicitly
omitted because its HUD anchor was unrecognized or occluded. The summary displays
the same PNG hash as the replay. All seven recorded combat outcome checks passed;
the UI displays saved originals restored and verified. These are saved evidence
checks, not a claim of current live cleanup.

At 08:53:51 UTC, an audit import created one `.pyc` in frozen-source. At 08:57:16,
the next controller rejected the extra archive file before game/model launch or
a new ledger trial. All 78 pinned executable files remained unchanged. Root
preserved the extra file, original rejection and before-inventory; the bytecode
preservation/restoration receipt is
`dist/store-warp-diagnosis-20261011/frozen-source-cache-incident-20261011T085716Z/restoration-receipt.json`.
The static recheck passed at 08:59:14 UTC: both original admissions matched
exactly, each with 78 sources and 565 evidence files; protocol hashes were
unchanged. Combat repeat two remained planned with no output before the fresh
launch. Root resumed the reviewed helper for eight unstarted Sol/hybrid cells.
All eight resumed cells subsequently finished: five task successes and three
idle-budget failures, with no new technical exclusion. Together with the first
hybrid combat trial, this completes the nine-cell Sol/hybrid boundary.

Frozen executable files must remain unchanged. Later actor source changes require
another fresh diagnostic collection, independent review and new admission/cohorts.

## Current pilot and prospective setup recipe

The later full-game technical interruption retained 47 PNGs and 47 call records,
including 46 accepted decisions. Last native state: sector index 0, three jumps,
four beacons, hull 28/30, three crew, score 91, no victory and no game over.
Independent saved image/input/frame/admission/restoration checks passed. Current
seven-save inventory, previous Lua bridge, six runtime files and no-game-process
check also passed. The rendered UI confirms zero native full-game completions,
one incomplete full-game attempt, the separate pilot defeat and three planned
conditions. Local receipts are `2174-main-fullgame-sol-image-final-review.json`,
`2174-main-fullgame-sol-image-current-cleanup-review.json`,
`2174-main-fullgame-sol-image-cli-failure-review.json` and
`2174-main-fullgame-sol-image-ui-review.json` under
`dist/store-warp-diagnosis-20261011/`.

Stored usage covers 46/47 calls: input 862,951 (cached subset 612,224), output
10,009 (reasoning subset 2,654). Raw call-47 completion separately reports input
20,030, cached 19,968, output 239 and reasoning 82. These are diagnostic retained
counts, not a replacement for the frozen report's missing usage. Usage from the
CLI's aborted internal requests is unknown. All 47 request latencies total
691.097 seconds; elapsed trial time was 821.622 seconds.

The Sol/image sector pilot in `fullgame-main-2174cc9-20261011` completed with
`native_game_over`: native defeat, sector index 0, score 20, 53 decisions and
54 PNGs. Independent saved outcome/admission/input/frame and seven recorded
restoration checks passed at 09:48:01 UTC. Current cleanup passed at 09:48:17:
seven original saves, prior bridge and six-file runtime matched, with no FTL
process remaining. The rendered dashboard review at 09:49:40 confirms the
GAME OVER / SCORE: 20 image, pilot exclusion, one finished entry and four planned
full-game conditions. This pilot is not one of the required four native endings.
The replay's generic fallback label now reads "Visual trial" instead of
"Full-game trial"; cohort classification was already correct. All 18 dashboard
tests and its build passed for that display change, outside the 78 frozen pins.

Usage is complete for 53/53 pilot calls: input 1,000,280 (cached subset 686,080),
output 17,131 (reasoning subset 8,640). Recorded model latency totals 1,058.864
seconds, median 20.509. Requested Sol/medium is retained; resolved backend weights
remain unavailable. Exact local receipts under `dist/store-warp-diagnosis-20261011/`:
`2174-main-pilot-final-review.json`, `2174-main-pilot-current-cleanup-review.json`
and `2174-main-pilot-ui-review.json`.

The [Windows/WSL setup recipe](../site/src/content/docs/install/pc.md) now creates
`dist/ftl_bench_bridge.ftl` deterministically from runtime data and mod
metadata; the external Lua is still deployed separately. It uses the caller's
selected checkout (or explicit `FTLB_ROOT`) without an implicit pull, honors an
explicit game path, and passes the Windows observation path to the printed
verification command. Data patching requires a supplied Linux FTLMan executable
and matching SHA-256, checks FTL is closed, and retains unique patch-input receipts;
it does not download a mutable latest patcher.

Before a native build, setup exclusively archives the original patched source
inputs. After the build, unchanged-source/provenance/DLL joins retain original
records and emit fresh build-origin references under the same evidence root.
It does not infer compiler identity or manufacture independent review. Offline
setup checks passed: 67 passed and five Windows symlink-creation skips (45 new
helper/input checks plus 22 staging checks), real `bash -n`, and two byte-identical
bridge CLI packages with all five exact loader/metadata members. Packaging receipt:
`dist/setup-package-check-20261011T094805465729Z/receipt.json` in the isolated setup
checkout. The current 78 frozen executable source pins remained unchanged.
The first setup publication passed all four Windows/Linux harness CI jobs but
failed the unpacked-source smoke: three new test modules assumed repository
siblings instead of the shipped `_bundled/` tree. Those tests now use the CLI's
existing source/package resolver. The full source-release smoke remains the
validation gate for this packaging correction.
No fresh native Docker build, installation or full clean-install validation has
run, and no new runtime was installed. Fresh source-bound diagnostics, independent
review and admission are still required for a newly built runtime.

## Preserved `078a5e2` cohorts and results

Executable sources at `078a5e2` passed all five CI jobs and fresh local
validation in `main-admission-dashboard-20261011T061245Z`: fixture-free startup,
all nine timing probes and eight independently executed evidence-rejection
checks. Independent review matched both 78-file source archives to current
sources and the commit, checked all ten cleanup inventories, and confirmed the
seven original saves, restored bridge, six-file runtime and no remaining game.
The local admission joins 565 evidence files and preserves
`production_accepted: false`. Admission-spec SHA-256:
`95f34f49d804852ac33f552f937319e5865dadd11576cea7f3019dfb033e6495`.

These preserved cohorts are under `harness/runs/validation/visual-v1/`:

| Cohort | Embedded protocol SHA-256 | Scope |
| --- | --- | --- |
| `matrix-main-078a5e2-20261011` | `412bcc6e687ebde35b6edb69331c9763673f0d2e5650bca45872004d4116b415` | 36 cells: 18 Sol, then 18 Luna; both modes and three repeats of each challenge |
| `fullgame-main-078a5e2-20261011` | `5351f3309a58bd0bc4fb7516e5b1759574efe68830e3e04e3528e4ddf4be8933` | Sol/image sector pilot, then four native-ending conditions |

Budgets remain 60 decisions / 1,800 seconds / eight idle decisions for challenges
and 300 / 14,400 / eight for full-game attempts, seed 1 and medium reasoning.
Independent freeze review records protocol IDs separately from file-byte hashes
in `dist/store-warp-diagnosis-20261011/main-078a5e2-cohort-review.json`. The
first Sol/image combat trial ended after 33 decisions at `idle_decision_budget`:
task success is false, evidence eligibility is true, and exclusions are empty.
Independent final review is retained locally as
`dist/store-warp-diagnosis-20261011/main-combat-01-final-review.json`. It records
33 model calls, 623,067 input tokens including 324,096 cached input tokens, and
8,901 output tokens including 3,117 reasoning output tokens. Total recorded model
latency is 512.978 seconds, with a 15.576-second median. Cached and reasoning
counts are subsets, not additional tokens. Repeat two also ended at the idle
budget after 27 decisions: task success false, evidence eligible, no exclusions.
Its saved audit passed with 29 PNGs and all seven saved restoration checks
verified; no live restoration check ran while repeat three was active. The enemy
fled at 7/9 hull without a reward; player hull was 25/30 and all three crew
survived. The receipt is `main-combat-02-final-review.json` in the same diagnosis
directory. Repeat three completed successfully after 12 decisions with 14 PNGs,
18 reward, one additional kill and the same beacon. Its independent saved and
current cleanup audit passed: seven original saves, bridge, six-file runtime,
frozen sources and evidence verified, with no FTL process remaining. Player hull
was 28/30 and all three crew survived. The receipt is
`main-combat-03-final-review.json` in the same diagnosis directory. This preserved
combat result is **1/3 task successes, 3/3 eligible trials**. These results are
not pooled with earlier cohorts, and fixture-free native-ending full games
remain **0/4**. All nine Sol/image cells are now finished:

| Challenge | Task successes | Idle-budget failures | Technical exclusions | Eligible evidence |
| --- | ---: | ---: | ---: | ---: |
| Combat | 1 | 2 | 0 | 3/3 |
| Fire/crew recovery | 3 | 0 | 0 | 3/3 |
| Repair/charge/escape | 2 | 0 | 1 | 2/3 |
| Total | 6 | 2 | 1 | 8/9 |

The bounded summary is `dist/store-warp-diagnosis-20261011/main-sol-image-summary.json`.
The nine cells completed 100 decisions and made 101 model calls. One failed call's
usage is unavailable, so complete token totals are unknown rather than zero.
All recorded cleanup receipts passed; the final repair batch audit at 07:10 UTC
also checked current seven-save inventory, restored bridge, runtime and source
pins, and no remaining FTL process. This is a dated check, not a continuing claim.

### Preserved pause and prospective CLI failure evidence

Repair repeat three retained `visual_model_error` / `protocol_failure` after five
completed decisions. The sixth CLI call exited zero but was rejected as
`CLI failed or emitted an unsupported event`. Only its event-stream hash was
saved, so the underlying event cannot be identified from that trial. Separately,
the model jumped with engines still at 1/2 health (one damaged bar and
`needs_repair: true`), although drive charge was 85/85 and native `can_jump` was
true. This partial repair correctly failed the full-repair task predicate before
any arrival modal; it is independent of the unknown CLI error. Exact rows and
image hashes are retained in `main-repair-03-task-attribution.json` in the diagnosis
directory. This trial establishes neither task success nor eligible gameplay evidence.
Keep its exclusion and original attempt intact. There is no silent retry.

The failure-only evidence change admitted at `2174cc9` retains:
bounded stdout (2 MiB) and stderr (64 KiB), raw-byte hashes, redacted retained
content with hashes and byte counts, truncation flags, and timeout partial-output
metadata. Successful decisions are unchanged. Unsupported/error/tool events still
fail closed; no retries, tools or fallback are enabled. The official
[Codex non-interactive contract](https://learn.chatgpt.com/docs/non-interactive-mode)
lists `error` and `turn.failed` in `--json` output and says `--ephemeral` does not
persist session rollouts, making retained failure output necessary for attribution.
Those documented events do not identify this particular unretained failure.

The old batch remains held and its frozen cohorts are preserved unchanged; the
new `2174cc9` cohorts above start prospectively rather than retrying its failed
cell. The CLI evidence fix passed 249 focused checks and independent review,
including a separate 67-test visual-agent suite, followed by all five green CI
jobs in run 38121156672. This acceptance does not recover the missing raw output
or unknown usage from the original failed call.

### Separate dashboard repair and rendered check (2026-10-11 06:55 UTC)

The dashboard initially returned HTTP 500 when latest-run ordering compared ISO
diagnostic `started_at` metadata with numeric model-run timestamps. The isolated
`ftl_bench-dashboard` viewer normalizes finite numeric and ISO timestamps to UTC
seconds and falls back to activity for invalid or unrepresentable values,
including oversized integers. Discovered raw metadata is preserved. The
evaluation checkout stays at documentation commit `e0a688e` with the admitted
`078a5e2` executable sources unchanged; the corrected viewer reads its existing
saved artifacts through the same absolute runs directory. No raw report was
rewritten and the existing built UI assets were reused.

The focused live/visual-live suites passed **74 tests with one skip**; an
independent 11-test timestamp subset and positive/negative oversized-integer
probes also passed. Actual Chrome inspection at port 8768 selected the current
cohort and completed repeat one: the unsuccessful task, eligible/unexcluded
evidence, restored-save status, exact before/after images, four delivered clicks
and 600 requested/600 simulated frames all matched the saved report and replay.
The comparison remained partial and unqualified. The original rendered HTTP-500
failure and the successful UI receipt/screenshots are preserved separately under
`dist/store-warp-diagnosis-20261011/dashboard-current-cohort-ui-review.*` and
`dashboard-current-cohort-ui-fixed-review.*`. These are viewer checks, not a new
admission or evidence of general determinism.

## First portable cohorts (preserved)

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

Sol/image combat repeat one started at 05:43:35 UTC and passed protected child
admission before the first Codex CLI call. It completed the task in ten decisions:
enemy defeat, 18 scrap collected, hull 30/30 and all three crew at full health.
Independent review checked 12 PNGs, all actions and frame counts, native outcome,
child admission and exact restoration of the seven saves and deployed bridge.
No FTL process remained. Recorded model latency totals 152.755 seconds, median
15.5975 seconds. CLI usage reports 186,628 input tokens (118,784 cached, included
in that total), 2,684 output tokens and 967 reasoning output tokens. The backend's
resolved model identity is unavailable; `gpt-6.1-sol` is the requested CLI model.

The saved rollup nevertheless marks this trial ineligible, solely with
`native_acceptance:native acceptance receipts missing`. The aggregator
unconditionally required v1 receipts, while v2 deliberately uses an empty legacy
receipt map plus portable admission. The dashboard accurately displayed that
saved exclusion. This is a reporting defect, not a failed gameplay task.

The prospective fix selects v2's admitted runtime and requires an explicit saved
child-audit result. It retains runtime, bridge and fixture checks, rejects absent
or malformed audit entries and unknown contracts, and preserves legacy receipt
checks. The real aggregator regression passed within 186 focused checks, with
one skip; independent review passed 22 targeted cases and additional rejection
probes. Separate reanalysis of the actual retained trial removes the false
exclusion. All 40 original run artifacts remain byte-identical, and the original
saved rollup is not overwritten or retroactively promoted.

Local receipts are under `dist/store-warp-diagnosis-20261011/`:
`first-portable-model-review.json`, `portable-report-exclusion-before.json` and
`portable-report-exclusion-after.json`. The latter is diagnostic reanalysis only.
The port-8768 dashboard shows one finished challenge, 35 planned challenges and
all five full-game-controller cells planned. These frozen cohorts remain preserved;
new reporter source bytes require fresh diagnostic admission and new cohorts
before further model trials. No complete comparison or full-game ending is claimed.

## Saved full-game admission projection

A separate review found that the v2 dashboard could keep showing verified
full-game completion after the saved child admission receipt was deleted or
rejected. Controller auditing already rejected those cases. The dashboard now
checks the saved receipt, manifest digest, protocol and recorded runtime before
projecting verified completion. Missing, changed, rejected, mismatched or oversized
evidence withholds completion and totals. This reads bounded local evidence; it
does not rerun live admission. Synthetic regression fixtures establish the
reporting behavior, not a played full game. The shared saved auditor requires
the exact admission contract, controller admission `true` and production
acceptance `false`, including their boolean types. Focused runner, saved-audit,
dashboard and controller checks passed (363 passed, one explicit skip); related
reporting and controller checks also passed (231). Independent review reproduced
the original omission, then confirmed rejection of altered admission states
even when their enclosing fixture hashes were updated. The retained real Sol
combat trial still passes its saved admission audit without changing its report.

The `main-admission-reportfix-20261011T060114Z` collection passed startup and
all nine timing probes at commit `31f589f`. Independent review matched its 78
archived source files to that commit, recomputed scoped validation using its
archived verifier and confirmed all ten cleanup inventories, the seven original
saves and absence of an FTL process. This collection remains diagnostic-only:
the subsequent dashboard change requires its own prospective admission.

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

1. Collect fresh startup/timing diagnostics, independent review and admission for
   the changed CLI recovery sources. Freeze new challenge and full-game cohorts;
   preserve the original failed Sol/image attempt and all old cohort outcomes.
2. Run the new cohort's Sol challenges, pilot and two full-game conditions first,
   followed by Luna's challenges and two full-game conditions, sequentially.
   Retain every attempted outcome; stop for technical failures or ambiguous cleanup.
   Keep pilots and budget outcomes distinct from the four required native endings.
3. Report matched conditions with denominators, exclusions, outcome reasons,
   latency and available usage. A fresh 36-cell challenge cohort can supply the
   declared three repeats per condition; never pool it with the preserved cohorts
   or silently retry failed cells to fill a comparison gap.
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
