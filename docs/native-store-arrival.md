# Hidden store arrival diagnosis

Status: both source repairs passed the protected natural arrival regression at
2026-10-11 05:28 UTC. Broader runtime admission and new model cohorts remain
pending. This is a harness defect, not a model gameplay failure.

## Retained failure

The Sol/image full-game cell in `fullgame-stop-v1-20261011` ran with the original
`ba06c25` sources and DLL SHA-256
`a33b9984caa9bd3a654816a62988a7da657f91ed39fcbc79a2dffda0d94f93bc`.
Decision 151 jumped toward a store, spent one fuel and advanced 122 of 600
requested frames. Native state then reported `store_open: true`,
`player_jumping: true`, and `blocked_reason: store_open`. The 04:50 UTC audit
found decisions 152–268 requested another 46,621 frames but advanced zero;
`world_updates` remained 24,032. Archived PNGs show an empty starfield with the
HUD and no usable store dialog or player ship.

The operator requested the controller's cooperative stop. The child stopped
after decision 276, retained its cancelled response, discarded unexecuted inputs,
and completed protected cleanup at 04:52:10 UTC. The controller refused to start
hybrid. An independent post-exit audit verified all seven original saves and
their inventory, all 15 baseline paths, and absence of FTL. This is an interrupted
attempt, with zero native full-game completions. Preserve its original results.

Local evidence in the integration checkout:

- `dist/active-fullgame-review-20261011T045001Z/receipt.json` and `findings.json`.
- `dist/store-warp-diagnosis-20261011/interrupted-cleanup.json`.
- `dist/store-warp-diagnosis-20261011/render-analysis.json`.
- `dist/store-warp-diagnosis-20261011/repro-before.json` and `regression-before.json`.
- `dist/store-warp-diagnosis-20261011/regression-after.json`.

Raw runs and diagnostic artifacts are intentionally excluded from Git.

## Cause and repair

`visual_blocked_reason` exempted staged choice/focus windows during jumping but
unconditionally blocked an open store. The Lua controller immediately cancelled
its remaining frame budget. Clock ownership then suppressed world/GUI updates
and the jump animation needed to make that store visible.

Read-only disassembly of the exact cohort FTL executable (SHA-256
`32f1459c22d5f268d323c5cc6ede0a8a704bc13b3a20d0c08b6da097a29c2daf`)
confirms the renderer skips focus windows when `GetIsJumping` returns true. The
constructor registers `storeScreens` in that vector. The retained receipt lists
the executable addresses and field joins; this is static visibility evidence,
not a live arrival replay.

The repair applies the same jumping guard to the store blocker. A visible store
still stops simulation after arrival; menus, errors and terminal states retain
their existing guards. The fix does not close the store, set jump flags, alter
fuel, reset timers, or give the actor hidden state. The include, cumulative patch
and manifest hash change together, so the old runtime cannot be silently reused
for a repaired cohort.

A second boundary occurs after warp. The ordinary Continue click queues a choice
for `WorldManager::PauseLoop`; it does not resolve the event inside the input
handler. A staged store must therefore also permit that queued choice through
both the explicit store check and the generic focus-window check. Once the choice
closes, the ordinary store blocker applies again. Unselected or out-of-range
choices cannot bypass it, and unrelated modal/error guards remain in force.

The first candidate DLL (`5280405c...`) completed the natural arrival in 243
frames, then exposed this second defect: Continue selected choice 0 but consumed
zero of its requested update, leaving both the choice and store open. That
candidate and its rejection remain preserved; it has no controller admission.

## Short live reproduction

`scripts/validate_store_arrival.py` reaches the natural first seed-one destination
at `(49, 231)` using ordinary deterministic setup, drive charge and a connected
jump. It deploys the production bridge unchanged. There is no injected encounter,
model call, direct jump/store flag write or timer override.

```powershell
uv run --directory harness python ../scripts/validate_store_arrival.py --output runs/validation/visual-v1/store-arrival-unique-name
```

The old DLL reproduced the stall with advances of 122, 0 and 0 frames, one fuel
spent and jumping still true. The probe preserves source/runtime identities,
native packets and receipts, exact PNGs, frame accounting, failure reasons, and
post-cleanup save/bridge/runtime inventories. The retained old-runtime run is
`harness/runs/validation/visual-v1/store-arrival-natural-old-20261011T051109Z`.

The passing path finishes arrival, acknowledges the screenshot-verified single
Continue choice through ordinary input, stops simulation at the visible store,
and closes it through the native CLOSE button. Unknown choices
produce `review_required` rather than guessed inputs or acceptance. A driver
error and an earlier attempt whose injection never executed remain in separate
output directories; neither is relabelled as this natural reproduction.

## Protected result and build identity

The final candidate was built from `c599189` using the pinned toolchain image.
Its DLL SHA-256 is
`7a695b9681deef16c791b28aa4be3d48721060410a4f71acda54875380844a22`;
the original provenance SHA-256 is
`a58f46456794b15ee870f6217c13916f3e8c1647a10630656fe2fc837bcc4960`.
The cumulative patch SHA-256 is
`33debd9d17ee0f3361fc355f258f58bbe0e864d066642572780299113d595aff`.

An independent build review reconstructed all 12 patched files from the exact
native base and matched their bytes before compilation, after compilation and
in provenance. It checked Clang 12, the successful target link, staged DLL identity
and the dependency-only cache copy. Actual source bytes, generated build settings
and logs are retained under
`dist/store-warp-diagnosis-20261011/build-attempt-05/`.

The live run is
`harness/runs/validation/visual-v1/store-arrival-natural-final-20261011T052742Z`.
It finished at 05:28:00 UTC with no model calls and this observed sequence:

| Operation | Requested frames | Actual frames | Observed result |
| --- | ---: | ---: | --- |
| Natural arrival | 600 | 243 | Warp finished at `(49, 231)`, one fuel spent, Continue visible |
| Fresh capture after input debounce | 0 | 0 | Same single Continue choice |
| Ordinary Continue click | 1 | 1 | Choice closed and store rendered |
| Advance with store visible | 600 | 0 | Native `store_open` blocker retained |
| Ordinary CLOSE click | 0 | 0 | Store closed |

The archived PNGs were inspected for the arrival, store and closed-store states.
Independent live-run review recomputed all 110 artifact hashes, joined all ten
sequence packets to the trajectory and checked input acknowledgments and update
counters. All seven original saves, the deployed bridge, source bytes and current
runtime matched their before/after inventories, with no FTL process remaining.
The receipt is
`dist/store-warp-diagnosis-20261011/store-final-independent-review.json`.
This is finite diagnostic evidence; its controller and production acceptance
flags remain false.

## Regression scope and remaining validation

The C++ test extracts the actual shipped predicate and uses the actual frame
clock. A small, explicitly simulated arrival loop reproduces the old failure:
eight requested updates produce zero while the store is hidden. It requires
bounded progress until arrival, then zero updates with the visible store, and
checks zero-frame idle, queued travel, missing ship pointers, focus registration,
and other blocking windows. Native renderer timing is not simulated acceptance.

The focused Python checks passed 51 tests, with seven host-compiler skips.
Five separately compiled WSL executables passed: the blocker/clock regression,
clock hooks, map/input wrappers, external input guard, and tooltip handling.
The regression changed from zero updates with jumping still true to three
simulated arrival updates followed by the visible store blocker.

Run the native visual pytest checks with a host C++ compiler. On Windows without
one, the compiled cases are skipped; execute their generated sources under WSL
and report those results separately. Standalone CMake targets do not include
these extracted hook tests.

The final combined change passed 35 focused Python checks with seven explicit
host-compiler skips; the queued-choice regression also passed under WSL. Its
ordinary Continue case changed from zero actual updates to one, followed by the
store blocker.

Before another model cohort, refresh the required startup/timing acceptance
against the new runtime and complete portable controller admission. Independent
review, archived evidence and new frozen cohort identities remain required.
Finite store-arrival checks do not establish general full-game determinism.
