# Hidden store arrival diagnosis

Status: source repair implemented; new native build and protected live validation
remain pending. This is a harness defect, not a model gameplay failure.

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

Before another model cohort, build a new DLL from the patched source, retain its
build provenance, run a protected no-model store-arrival regression, and re-run
the required startup/timing acceptance against the new runtime. Independent
review, archived evidence and new frozen cohort identities remain required.
Finite store-arrival checks do not establish general full-game determinism.
