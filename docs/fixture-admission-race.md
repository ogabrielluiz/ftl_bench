# Fixture admission race and repeatability audit

Evidence reviewed after the 2026-10-10 fixture5 timing run completed. The
fixture4 first-capture race is fixed in the recorded fixture5 runs. The corrected
combat path still fails repeated identical-input outcome equality, so fixture5
with clock2 is **not accepted overall**. No game or model was launched for this
audit; historical evidence was preserved.

## The fixture4 failure

The authoritative boundary trace is
[`diagnostic-capture-boundaries.jsonl`](../harness/runs/validation/visual-v1/stale-capture-probe-before-20261010/repetition-02/combat/diagnostic-capture-boundaries.jsonl).
Python received capture `96628-134361180946387692-778-1` with fixture
`applied=false`, drive charge `1.426`, and enemy weapon charges
`0.98708683252335` / `0.98708671331406`. Before the next input packet, the native
observation had become capture `96628-134361180946387692-779-2`, with
`applied=true` and those charges zero. Both observations have action sequence 7,
world updates `"0"`, and pause enabled. A second capture appeared without a new
admitted input packet; the stale-screenshot guard correctly refused dispatch.

The archived [fixture4 wrapper](../harness/runs/validation/visual-v1/stale-capture-probe-before-20261010/repetition-01/combat/fixture-bridge.lua)
checked visual mode before calling the production visual tick. On the first
visual packet, the state still held the previous observation mode. The tick
admitted that packet and the render produced the unapplied fixture image. The
next wrapper tick applied the fixture and cleared `obs_fresh`; the production
tick refreshed the cached observation for the same action sequence, producing
the unsolicited replacement image. This ordering explains the recorded race;
it was not a model decision or gameplay loss.

The old matrix's third combat trial failed during setup with
`Stale screenshot: no inputs were dispatched`, before any actor-start capture:
[`validation.json`](../harness/runs/validation/visual-v1/matrix-clock2-20261010/trials/gpt-6.1-sol/image/combat/repeat-03/repetition-01/combat/validation.json).
Earlier successful trials and the old
[clock2 timing report](../harness/runs/validation/visual-v1/timing-clock2-all-20261010/fixed-step-report.json)
remain historical evidence. Their setup used later capture suffixes and cannot
establish correctness of first-capture admission.

## Fixture5 admission evidence

Fixture5 first calls the production visual tick to admit the packet, then applies
the one-time fixture while that first zero-frame capture is pending, before a
capture exists. The guard requires visual mode, no request error, zero requested
frames and frame budget, a live game, and no choice modal. It records
`applied_before_first_capture=true` and `admission_action_seq`. The driver rejects
an unapplied first capture instead of retrying setup. The archived
[fixture5 driver](../harness/runs/validation/visual-v1/timing-clock2-fixture5-all-20261010/combat/repetition-01/combat/fixture-driver.py)
and [bridge](../harness/runs/validation/visual-v1/timing-clock2-fixture5-all-20261010/combat/repetition-01/combat/fixture-bridge.lua)
preserve the exact implementation used.

All three
[post-fix diagnostic setups](../harness/runs/validation/visual-v1/stale-capture-probe-after-fixture5-20261010/)
and all nine completed
[timing trials](../harness/runs/validation/visual-v1/timing-clock2-fixture5-all-20261010/)
start with capture suffix 1 and the fixture already applied before capture.
The initial capture's action sequence equals its recorded admission sequence.
Combat diagnostic starts all use action sequence 7 and world updates zero.

Across the timing trajectories, capture suffixes and action sequences are
consecutive: 1–27 for each combat/fire trial and 1–13 for each repair trial.
There are no unsolicited captures within these recorded acknowledged
intervals. The first reference equals `actor-start.json`'s `first_image`; every
referenced PNG hash and every stored gameplay signature hash was independently
checked. This is evidence about the recorded intervals, not an assertion about
unobserved native behavior.

The first fire image visibly contains oxygen-room fires and an injured crew
health bar. The first repair image visibly shows the engines-critical warning
and damaged engine indicator. Both show the paused ship unobscured by a store
or event modal. Native setup predicates, rather than pixel estimates, establish
the exact fire counts, injury and health bars.

## Fixed time passes; combat outcomes do not repeat

The final [fixed-step report](../harness/runs/validation/visual-v1/timing-clock2-fixture5-all-20261010/fixed-step-report.json)
contains nine completed no-model trials with delays 0, 0.35 and 1.2 seconds.
All trials pass their clock contract, explicit-input sequence, native update
deltas, fresh zero-frame idle-freeze checks and progression checks. Captures
declare clock version 2, a 1/60 step, and `simulated_updates == world_updates`.
Combat/fire each advance 1,440 updates (24 nominal seconds); repair advances
360 (6 nominal seconds). The aggregate explicitly records
`fixed_step_acceptance.claimed=false` because combat step equality fails.

Initial gameplay fingerprints match all repetitions and the corresponding old
fixture4 timing starts exactly; values are compared without rounding:

| Challenge | Initial gameplay SHA-256 | All repeated steps equal |
| --- | --- | --- |
| combat | `1759586db7dc376c6513220994a1e2e6e25b6fefa42c488cb5927b9481e36850` | No |
| fire-crew-recovery | `a18e37907ca908c310df8850474916fb2687c18f581d55b94a3c4eb354aa60c6` | Yes |
| repair-charge-escape | `26fbc52a6d4cb1a9bc36d96511604a18355ec56fc665d976439122f33ba9abd1` | Yes |

Fire and repair trajectories also match their old fixture4 timing trajectories.
Combat repetition 1 matches the old trajectory, while repetitions 2 and 3
match each other and diverge from repetition 1 at `fixed-advance-6` (720 updates,
12 nominal seconds). At this first divergence, repetition 1 has engine health
2, crew 1 health 100 and no room-14 fire; repetition 2 has engine health 1,
crew 1 health `82.304351806641`, and a room-14 fire. Final hull is 28 versus 26,
with further engine, crew, shield and fire differences. This is material native
impact/outcome divergence, not a timestamp or screenshot difference. The exact
endpoints are retained in the combat
[repetition-01 trajectory](../harness/runs/validation/visual-v1/timing-clock2-fixture5-all-20261010/combat/repetition-01/combat/trajectory.jsonl)
and [repetition-02 trajectory](../harness/runs/validation/visual-v1/timing-clock2-fixture5-all-20261010/combat/repetition-02/combat/trajectory.jsonl).

The fixture seeds native RNG once and normalizes initial charges once. The
internal random draw stream is not measured. Shared RNG consumers during idle
rendering are a plausible remaining cause, supported by the source limits in
[the seeding review](full-game-seeding-review.md), but this audit does not prove
the cause. Equal initial state and fixed elapsed simulation time do not prove
equal later combat outcomes. Quiet-scenario equality is scoped to these tested
paths; full-game determinism and matched combat comparison remain unproven.

## Preservation and audit boundary

All nine trials report original-save restoration and unchanged production
source. After the parent confirmed the game had stopped, an independent
[save audit](../harness/runs/validation/visual-v1/timing-clock2-fixture5-all-20261010/independent-save-audit.json)
found no FTL process before or after reading and verified all seven live
original save files against the first trial's protected backup SHA-256 manifest.
The audit made no runtime, installed-file, save, model, or trajectory changes.
It added this note and the independent read-only save-verification receipt.
