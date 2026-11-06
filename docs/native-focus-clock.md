# Native focus and simulation clock

The visual controller owns simulation time during setup and play. Native FTL
focus handling must retain its ordinary UI behavior, but a focus transition
during an owned advance invalidates that advance. After the first capture,
focus transitions also invalidate a frozen visual session. The external-input
generation is sticky evidence; it is never cleared to salvage a run.

## Reproduced behavior before the fix

Two protected, no-model fire-fixture diagnostics on 2026-11-06 used the same
installed attempt-three runtime and 600 requested updates. The foreground
baseline ran 600 gameplay updates. In the controlled run, switching to Steam
after native progress was observed left only 16 gameplay updates and 584 paused
updates, although the world counter still advanced by 600 and the external-input
generation remained zero. Native `RunningTime` advanced about 0.267 seconds,
compared with 10.000 seconds in the baseline. This is a clock-accounting defect,
not a model failure.

Refocusing during the subsequent frozen hold also advanced `RunningTime` by
about 0.0167 seconds while the world counter remained unchanged. The baseline
hold had no timer growth. Both probes restored the exact original saves,
deployed Lua and runtime files. They made no model calls and are diagnostics,
not controller admission or evidence of general determinism.

Local evidence is retained in these immutable run directories:

- `dist/resume-20261106/focus-clock-v2-foreground-20261106T1949/`
- `dist/resume-20261106/focus-clock-v2-controlled-20261106T1955/`

The foreground trace ring dropped its earliest 42 rows; the advance and hold
intervals are retained. Raw native readbacks, passive foreground samples,
command markers, sources, protected backups and cleanup receipts remain
available. The earlier attempt at
`dist/resume-20261106/focus-clock-transition-20261106T1935/` stopped on external
input before dispatching the requested advance and remains a separate failure.

These results establish a focus-related defect. They do not establish that
focus caused the October fire-repeatability mismatch.

## Fix boundary

Windows FTL 1.6.9 handles ordinary blur/refocus inline in `CApp::GenInputEvents`;
the keyboard/mouse `CEvent::OnEvent` guard does not receive that transition.
Observe the actual `inputFocus` value around the original input poll. For the
current application, an owned advance or an already-armed guard must latch
interference and revoke the frame permit before `CApp::OnLoop` can consume it.
Do not synthesize input or overwrite native pause flags.

`CFPS::OnLoopUnpaused` also runs outside the gated world loop. Gate that method
for the current FPS instance when an owned frame is not permitted, retaining
ordinary ambient FPS bookkeeping and UI animation. An executable-level test
requires the Windows binding to match exactly one function in the supported
FTL 1.6.9 image. ZHL itself uses its normal first-match signature resolver;
failure to resolve the binding aborts native startup rather than degrading to
an unguarded visual controller. The visual capability check also requires the
resolved address. Other instances and unowned operation on the supported
runtime retain native behavior.

Keep legitimate `WorldManager::PauseLoop` work, including accepted travel and
queued-choice commits. Rejecting all paused updates would deadlock those paths.
Deterministic setup must terminate and freeze its budget when native capabilities
report external interference, including before the first visual capture.

## Validation boundary

The fix preserves native protocol 5 and clock 2's wire fields and fixed 1/60
step. Its changed source, patch and DLL identities require a fresh build,
protected startup and timing evidence, independent review, controller admission
and newly frozen cohorts. Existing admissions and failed runs cannot be reused
or relabeled. Extracted-hook regressions establish scheduling behavior in a
native test fixture; only a rebuilt DLL and protected game probes can establish
the corresponding live behavior.

## Rebuilt runtime evidence (2026-11-06)

The rebuilt DLL `16eba4465270311bc480f9a91c4c3adc36c8ff33d1e6dc79c11ef950173023ec`
passed protected startup and all nine timing probes. Each challenge's recorded
states matched exactly under delays of 0, 0.35 and 1.2 seconds. All eight
independent evidence mutations were rejected before local controller admission.
The scoped report retains `production_accepted: false`; newly frozen cohorts
have not yet produced model results. See [current work](NEXT.md).

The repeated post-capture foreground probe consumed 600 gameplay updates and
about ten seconds of native time. The controlled switch stopped after 27
updates, then held the counter and timer constant through refocus. However,
switching windows also moved the physical pointer: that probe cannot identify
which guard fired first. Its independent comparison is
`dist/resume-20261106/focus-clock-v2-postfix-independent-comparison-20261106T203657Z.json`.

To isolate native focus handling, a separate protected driver added one ordinary
600-frame structured wait after fresh setup and before any visual capture.
It kept production control logic unchanged and did not clear interference or
arm the ordinary input guard. Its observer forwarded the native capture writer
unchanged and recorded zero writer calls, visual packets and capture artifacts. The source's
only ordinary guard-arm call is in that writer.

In the controlled run, focus loss latched generation 1 at world update 112
after 22 updates, and deterministic setup failed immediately. Returning to FTL
restored the native unpaused UI state. All 879 subsequent unpaused trace rows
kept world updates at 112 and `RunningTime` at 1.3499994277954. This exercises
the independent timer gate while the world is frozen. The foreground control
consumed 600 updates; its observer begins after the first update, so its timer
span covers 599 sample-to-sample steps rather than a measured full ten seconds.

These pre-capture diagnostics are retained separately:

- `dist/resume-20261106/focus-clock-prearm-foreground-20261106T2043/`
- `dist/resume-20261106/focus-clock-prearm-controlled-20261106T2045/`

Their independent comparison is
`dist/resume-20261106/focus-clock-prearm-independent-comparison-20261106T205003Z.json`,
SHA-256 `5b7bfcf8d3b178a8e84b6b7a7e5ec3291ce7944d5db9642187947d4aa0a883c5`.

Their trials deliberately terminate before capture and retain failed trial
classifications. Collection completion means the intended stop and evidence
were obtained with protected cleanup; it is not a gameplay pass. A supplemental
latest-observation copy in the controlled run hit a Windows file-access error;
the primary interval-end observation, full trace and cleanup evidence remain.
Original saves and prior Lua were restored. The current-runtime cleanup audit
at 20:44:55 UTC found no FTL process or pending launch marker. The cause of the
historical October fire mismatch remains unproven.
