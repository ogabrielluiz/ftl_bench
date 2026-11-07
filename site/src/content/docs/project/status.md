---
title: Validation and baselines
description: Current protocol, retained diagnostic evidence and comparable reporting.
---

## Visual benchmark status — November 7, 2026 UTC

The Sol/hybrid full-game attempt stopped cooperatively after a stale store
price charged 6 scrap for eight hull repairs. Its artifacts and verified
save restoration are preserved. The rebuilt Release runtime from `47db7f6`
passed the same protected zero-frame store path, quoting and charging 16 scrap
at hull 22. Both probes restored the original saves and prior Lua. Independent
review verified 123 artifacts and 85 source pins per run.

The probe covers the visible vanilla buy tab and made no model calls. The
rebuilt runtime has scoped controller admission after eight protected startup
checks, nine timing probes and eight independent rejection checks. A new
36-cell challenge matrix and a separate sector pilot plus four full-game
conditions are frozen. At the 02:42 UTC checkpoint, all 18 Sol challenge cells
were complete and eligible, with 3/9 image-only successes and 7/9 hybrid
successes. Combat was 0/3 image-only and 3/3 hybrid, fire and crew recovery
was 3/3 in both modes, and repair, charge and escape was 0/3 image-only
and 1/3 hybrid. The 18 Luna challenge cells and all five full-game entries
were planned at this boundary. The Sol pilot and two full games were next.
These results describe one seed and fixed situations. Resolved backend model
identity and monetary cost are
unavailable. Rendered dashboard inspection is deferred while the operator
is away. See the
[store refresh evidence](https://github.com/ogabrielluiz/ftl_bench/blob/main/docs/native-store-refresh.md).

At the 03:11 UTC checkpoint, the Sol/image pilot had ended in native crew-loss
defeat after 117 decisions, four settled jumps and five visited beacons in
native sector 0. The terminal screenshot and native state agreed on score
160, hull 3 and oxygen 30%. Input and restoration audits passed. The pilot
contributes zero full-game completions, leaving all four full-game conditions
planned at this boundary. Sol/image full game was next, then Sol/hybrid and
the Luna trials.

At the 04:13 UTC checkpoint, Sol/image had ended in native crew-loss defeat
after 286 decisions in native sector 2 (the third sector). The final screenshot
and native state agreed on score 462, hull 11 and oxygen 84%. Input and
restoration audits passed. One of four full-game conditions was complete,
with zero victories and the pilot excluded. Sol/hybrid was next at this
boundary, followed by the Luna trials.

The visual benchmark remains an alpha with partial live validation. Codex CLI
is the default. Decisions and Jev now have separate typed visual adapters and
an archived-image decision command; offline integration and packaging checks
passed, while live provider compatibility remains unverified. Typed visual
runs are diagnostic and do not enter the frozen Codex comparison cohorts.
See the [backend contracts](https://github.com/ogabrielluiz/ftl_bench/blob/main/docs/typed-decision-backends.md).

Separate protected game diagnostics reproduced a focus-related clock defect:
paused updates could count toward a gameplay advance, and refocusing could
advance the timer during a frozen hold. The rebuilt fix passed protected
startup, all nine timing probes and eight independent evidence-rejection
checks. A pre-capture focus test also verified that native refocus leaves the
world and timer frozen even when the UI becomes unpaused. The preserved Sol/Luna
cohorts had scoped local admission for that focus-fix runtime. All 18 Sol
challenge trials are complete and eligible, with verified cleanup. Image-only
succeeded in 6/9 and hybrid in 4/9. Each task has three repetitions per mode with matching
starting gameplay states. The eight idle-budget endings remain recorded,
with the unmet native requirements reported separately. There are no technical
exclusions or recorded reconnects. The 217 audited turns reported 4,094,609
input tokens, 46,938 output tokens and 2,184.411 seconds of CLI latency.
Independent audits reproduced all 135 hybrid prompts and same-PNG HUD
extraction, including omissions under warning, cursor and reward overlays.
This fixed-situation sample does not establish a general ranking. The Sol/image
pilot ended in native crew-loss defeat after 89 decisions, four jumps
and five visited beacons in sector one. Its input and restoration audits passed;
the pilot contributes zero full-game completions. Sol/image then reached an
audited full-game defeat after 42 decisions at the second beacon, with native
score 59 and all crew dead. Cleanup and the saved dashboard projection passed.
The preserved cohort has one verified full-game ending out of four. The
Sol/hybrid attempt is incomplete. Both Luna full games and all 18 Luna challenge
cells remain planned in the preserved cohorts.
Historical failures remain preserved. See
[current work](https://github.com/ogabrielluiz/ftl_bench/blob/main/docs/NEXT.md).

## Structured protocol validation history

Current runs use native protocol 5 and runner/ruleset v7, retaining `owned-player-crew-v1` and requiring `native-economy-and-fuel-recovery-v1`, `native-sector-neighbors-v1`, `native-beacon-readiness-v1` and `native-enemy-hostility-v1`. Native protocol 5 remains the API version, while `economy.sector_navigation_version: 1` and Lua `sector_navigation: true` identify verified neighbor-index routing. `economy.beacon_navigation_version: 1` and Lua `beacon_navigation: true` additionally identify strict native travel readiness and pending-defeat guidance. They verify Kestrel A/easy setup, confirmed navigation and explicit native victory. Exact native upgrades, event availability/pending feedback and native fuel recovery replace the incomplete older interface.

The Windows x86 protocol-5 DLL is built from source `d85d6df9626c13343d28b60f43b37d6eadcc7f1d` plus the complete checked patch. Current artifacts are `dist/Hyperspace.protocol5.dll` and `dist/native-build.protocol5.json`; provenance records actual source/diff, every patched file, patch, toolchain/container and DLL hashes. The v7 source suite has 731 passing tests; current release packaging checks are recorded separately.  GCC Release native routing/readiness regressions passed and the DLL compiled with Clang 12/MinGW. Native upgrade/recovery validation remains under `harness/runs/validation/native-protocol5/`. The prior sector-only seven-transition fixture is retained under `harness/runs/validation/native-sector-routing-v5/`, excluded from comparisons; it did not test the subsequently found ordinary-jump charge defect. V7 retains native button/full-timer/system/fuel/context readiness for both jumps and sector exit. Pending defeat is guidance and does not independently forbid a charged legal jump. Release evidence is recorded separately in `dist/package-validation.json`; tests and private fixtures do not establish a full-game win.

The retained v6 live fixtures passed: `harness/runs/validation/native-beacon-readiness/` verifies partial-charge refusal, normal enemy death/reward credit, modal-free post-reward charging refusal and a charged one-fuel escape. `harness/runs/validation/native-sector-routing/` verifies all seven sector transitions from index 0 through 7, full native charge before each departure, exact one-fuel charges and off-exit refusal. These fixtures are comparison-excluded; the sector fixture supplies the exit-location prerequisite and is not a full-game run.

The current v7 hostility fixture passed on the exact recorded DLL and Lua: `harness/runs/validation/native-enemy-hostility/` verifies normal hostile fire and native kill/reward credit, a natural surrender with its bribe reward, a retained friendly ship marked `hostile: false, targetable: false`, and rejected weapon requests without ammunition loss even after 720 native frames. A fully charged friendly sector exit advanced index 0 to 1 and consumed one fuel. Combat/surrender checks used no state injection; sector departure supplied only the exit-location prerequisite. The fixture is excluded from model comparisons, and all six original save hashes were restored.

## Historical diagnostics

The v6 trial was stopped after an accepted surrender left a friendly ship serialized as targetable for repeated turns. Its final native score was 81, with two confirmed jumps and hull 28; there was no real game over or victory. V6 artifacts and release checks are preserved at `dist/releases/protocol5-before-target-validity/` and superseded for comparison. V7 adds `native-enemy-hostility-v1`, using the native hostility flag for combat, targeting, queued weapons and the sector enemy restriction. The native API and bindings remain protocol 5.

The owned-crew v3 GPT-6.1-Sol trial completed 89 turns and 21 confirmed jumps, then conceded at fuel 0 with hull 19 and three owned living crew. Native score was 329: 69 scrap + two kills + 22 explored beacons. There was no native game over or victory. Its validation checked 93 observations, 91 scores and archived runtime Lua/DLL/prompt hashes. It is `diagnostic_only` because event availability, upgrade pricing and recovery were incomplete. This is not a model ranking.

That run is retained at `harness/runs/validation/gpt-6.1-sol-codex-v3/20261002T180050Z-ed0317356b`, with `validation.json`, `recomputed.json`, runtime artifacts and save-restoration evidence. An earlier pre-v3 trial moved a hostile boarder and was stopped as an invalid control trial. The owned-crew guard repairs that boundary and remains required.

Historical Jev v2 validation remains at `harness/runs/validation/final/20261002T133446Z-865cd6722e`. It retains a model-error attempt scoring 20 and a retry reaching native crew-loss game over at score 59, hull 21: 19 scrap + one kill + two beacons. The probability-tolerance error was subsequently fixed. Its native formula matched 35 scored snapshots and fresh retries began at score 10. This supports score/reset behavior, not a current comparison row.

The archived protocol-4 DLL/patch/manifests remain available for those traces. The old v3 package passed 390 checkout/source-release tests and installed CLI/UI/native-patch smoke checks; current protocol-5 release checks are recorded separately.

## Current comparison rows

The preceding v5 trial was stopped after ordinary jumps bypassed native charging and enemy-death rewards. Its exact d443 DLL/Lua6f/packages and prior release evidence remain archived and diagnostic.

The preceding v4 trial exposed a sector type/index mismatch at sector exit and was stopped as a diagnostic; its exact runtime artifacts remain archived. The repair selects an actual neighboring-sector vector index and retains native acceptance/refusal feedback.

**Pre-v7 rows are noncomparable.** Diagnostic attempts retain score/progress and terminal evidence but do not enter model-ranking metrics. Fresh public baselines and models, held-out full games and human references remain to be established. No retained full-game win is claimed here.

Jev's independent actuator choices are labeled `jev-actuator-choice-v1`.
OpenAI Responses and the Decisions actuator adapter are implemented. The
November Decisions integration has offline coverage; current provider
compatibility still requires live validation. Compare the same suite, tier,
mode, prompt, control/economy/routing/beacon/hostility contracts, native
artifacts, backend/action-selection contract and retries.

## Platform and evidence limits

Native Windows through Steam is the validation target; WSL can access its save folder. macOS needs an equivalent patched build and live validation. Optional sector-choice, flagship surge, breach and special-system facts need representative retained traces.

Report runner/ruleset, all five contracts, actual setup, prompt/suite identity, native hashes/provenance, backend/model/decision contract, retries and outcome artifacts. Failed and interrupted attempts stay visible.

See [protocol](/introduction/protocol/) and the repository's `docs/NEXT.md` for retained evidence.
