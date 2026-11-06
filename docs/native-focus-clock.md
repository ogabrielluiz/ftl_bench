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
