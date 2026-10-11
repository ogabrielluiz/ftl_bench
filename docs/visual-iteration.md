# Visual iteration

The visual track lets an agent play through FTL's rendered interface. Each decision pairs the exact image supplied to the model with ordinary mouse/keyboard inputs and an image of the resulting game window. Native observations remain available to the evaluator for scoring and diagnosing failures.

This is an additional track. Existing structured trajectories remain readable, and historical diagnostic runs remain excluded from model-comparison totals. A recorded native score is not evidence that a run is eligible for comparison.

**WIP:** the current challenge comparison is partial and fixture-free full-game
four-condition completion remains unfinished. At the 2026-10-11 14:24 UTC snapshot,
Sol/image has an audited native crew-loss defeat (1/4 endings); Sol/hybrid is running.
The historical `2174cc9` sector pilot ended in audited native defeat
and is excluded from full-game totals. Read [current validation and remaining work](NEXT.md) before treating
any historical result below as current acceptance. Native binaries, raw runs
and local acceptance evidence are not included in Git; a fresh checkout still
needs the matching runtime and evidence described in the
[experiment protocol](visual-experiment-protocol.md#freezing-and-resumption).

## CLI input isolation

Each request uses a fresh temporary working directory containing the exact PNG
and response schema, with the explicit frozen manual/task prompt, bounded public
history and actor memory supplied on stdin. Accepted calls undergo a per-call
no-tool event audit. The saved d1c18b8 review checked twelve hybrid requests:
public prompts and recorded events contain no native telemetry or evaluator
content. Actual generated argv and temporary cwd were not retained per call;
those details are source-derived, not independently observed process metadata.

The inspected Codex CLI 0.160.0 help defines `read-only` as a shell-command sandbox,
not blanket filesystem-read denial or tool disabling; `--ephemeral` means no
session-file persistence, and `--ignore-user-config` skips `config.toml` only.
It does not establish suppression of instruction discovery or provider/system
context. The dated 2026-10-11 12:52 UTC existence check found no `AGENTS.md` or
`AGENTS.override.md` at the named global and relevant ancestor paths, including
`CODEX_HOME` and the temporary-directory parent. Provider/system context remains
unverified; these checks establish neither leakage nor expanded acceptance.
See the official [instruction-discovery documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
Local receipts are `d1c18b8-cli-input-isolation-review.json`,
`d1c18b8-cli-input-isolation-semantics-review.json` and
`d1c18b8-cli-instruction-existence-review.json` under
`dist/store-warp-diagnosis-20261011/`.

## Running a local visual attempt

The [versioned CLI recovery policy](cli-recovery.md) handles only recognized
connection notices followed by a fully validated completed response. It does not
retry a benchmark call. Historical strict-policy failures remain failures, and
new executable sources require fresh admission before frozen experiments.

Close FTL first. From the harness environment, start a protected run in a new output directory:

```powershell
ftlbench visual --model gpt-6.1-sol --mode image --seed 1 --max-decisions 300 --max-wall-seconds 14400 --reasoning-effort medium --output runs/visual/sol-image-001
ftlbench visual --model gpt-6-luna --mode hybrid --seed 1 --max-decisions 300 --max-wall-seconds 14400 --reasoning-effort medium --output runs/visual/luna-hybrid-001
```

Image mode is the default. Visual runs use the locally authenticated Codex CLI; the declared experiment models are `gpt-6.1-sol` and `gpt-6-luna`. The executable resolves through `CODEX_BIN`, the command path, or the installed Codex desktop executable. From a checkout, prefix the commands with `uv run --directory harness`. Each output directory must be new. The examples declare model, observation mode, seed, reasoning effort and budgets; they do not establish a model comparison by themselves.

### Pending-launch recovery

A Steam launch can remain queued behind cloud/sign-in prompts after readiness
times out. New protected runs claim `ftl_bench_pending_launch.json` in the explicit
save folder before backup/launch. An unresolved pending timeout blocks verified
restoration-success and new protected runs; an empty FTL process list does not
prove Steam cancelled the request. First cancel the pending Steam launch manually
and close FTL. Read `ownership_id` and the backup path from that named marker,
then run from the source checkout:

```powershell
uv run --directory harness ftlbench recover-protected --backup <save-backup-path> --ownership-id <ownership_id> --confirm-pending-launch-cancelled
```

If backup was interrupted before its manifest was complete, also pass the marker's
explicit `--save-dir <save-folder>`; recovery does not discover save folders.
Recovery verifies marker/backup identity, absence of FTL and applicable backup
hashes, retaining a separate `recovery-restoration.json` before releasing the
guard. It never rewrites the failed trial or its original restoration receipt.
Cancellation acknowledgement is operator testimony, not automatic queue proof.
The fix passes 240 focused offline checks after the final recovery fixes. The
broader harness suite passed 2,583 tests with 17 skips before those fixes; final
CI and live validation remain pending, with no new admission or cohort. It does not retrofit
the historical bb6014b Steam failure: that request still awaits operator action,
has no new-code marker, and must not be passed to recovery without one created
by the new code. Keep further game runs stopped until cancellation is confirmed.

For reproducible settings and durable cooperative stopping, prefer the full-game
experiment controller. The standalone examples above do not configure a stop
file; controller children do. From the checkout root, with the harness environment
configured and the tested visual runtime/acceptance baseline available:

```powershell
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py freeze --output harness/runs/visual/fullgame-sol-luna-001
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py run --output harness/runs/visual/fullgame-sol-luna-001 --limit 1
```

Only when stopping an active run, use a second terminal at the repository root:

```powershell
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py stop --output harness/runs/visual/fullgame-sol-luna-001 --initiator operator --reason operator_requested
```

Inspect saved attempts after the controller finishes:

```powershell
harness/.venv/Scripts/python.exe scripts/run_fullgame_experiment.py report --output harness/runs/visual/fullgame-sol-luna-001
```

Choose a new directory for `freeze`; subsequent commands use that same directory.
Run only one game/controller at a time. Each `run --limit 1` admits at most one
new cell after source/runtime and prior cleanup checks. The declared order is
Sol image sector-one pilot, then Sol image/hybrid and Luna image/hybrid full-game
attempts. A stop request is durable and records its initiator. A response already
in flight may finish, but its actions are discarded before dispatch when the
request is observed; keep the runner alive until protected cleanup completes.
Stopped attempts remain recorded as interrupted; use a fresh output directory
for a new experiment after a stop request.
Do not use execution-session termination as a substitute. See the
[experiment protocol](visual-experiment-protocol.md#cooperative-stopping-and-task-identity)
for stop evidence, budgets, exclusions and native-ending completion rules. This
workflow does not claim that a full game or matrix has already completed.

Every production `ftlbench visual` run now requires native protocol 5, fixed clock 2 at 1/60 second, and `fresh-start-seed-v3`. This is mandatory startup behavior, with no extra user flag. Inside the protected save lifecycle, the runner sends one explicit native setup opt-in, initializes the native and DLL C-runtime generators once before ship construction, and freezes the completed startup before ordinary gameplay. It verifies the actual seed, Kestrel A/easy setup, score/victory signals and exact construction/clock receipts before any model decision. The structured `ftlbench run` track retains its existing startup contract.

Full-game startup is fixture-free: no injected damage, fires, resource changes, initial charge adjustment, event choice or backstage gameplay occurs. The first archived image retains the opening intro choices for the actor to handle through ordinary visual input. The same image becomes the canonical trajectory reset and the first actor image; the admission validator runs after that reset is recorded. Hidden setup receipts stay outside actor prompts and history.

The runner stores `fresh-setup/setup-session.json` with the fresh request and native observations, and `fresh-setup/admission.json` with first-image, packet and receipt proofs. Admission failure stops before any model call, preserves the available evidence and first image when captured, and follows protected cleanup without retrying or bypassing the native refusal. `run.json`, `trajectory.jsonl`, `runtime-fingerprint.json` and `save-backup/restoration.json` retain terminal cause and restoration status; a later cleanup failure remains a separate failure. Windows runs back up current saves and the external bridge, then restore them on exit. Individual visual reports remain diagnostic until the experiment audit establishes comparison eligibility.

Nine no-model fixture-6 probes passed measured initial and per-step gameplay equality under three wall delays for combat, fire and repair scenarios. The production startup-only check `fullgame-startup-v3-production-20261011-v3` also passed fixture-free admission, verified the first image and retained opening choices, with zero model calls and verified cleanup. These checks establish their recorded startup and finite progression scope. They do not establish an uninterrupted full-game ending, a new model result, equality of every internal RNG stream, or general full-game reproducibility. Earlier failed probes remain archived.

The runner also stops after eight consecutive decisions with no inputs and zero requested frames, recorded as `idle_decision_budget`. Set `--max-idle-decisions` to a positive integer to change this declared budget. The harness does not invent an action or advance time to rescue a stalled model.

To inspect its artifacts with the existing dashboard:

```powershell
ftlbench dashboard --runs runs/visual --port 8765
```

Open `http://127.0.0.1:8765/` and select the attempt. The dashboard is read-only and does not send game inputs.

## Decision boundary

The session pauses simulation before capturing a decision image. The model responds while simulation remains paused. The session then delivers the bounded input sequence, advances the requested amount of game time, and captures the next paused observation. Screenshot coordinates always refer to the original captured image dimensions.

The active runtime requires `visual_clock_version: 2`, a fixed step of `1/60` second, and the external-input guard. The clock gates native world and transition updates, including jump animation updates that normally continue during FTL's pause. Each screenshot carries cumulative decimal-string `world_updates` and matching `simulated_updates`; their change must equal the acknowledged frame count. Permitted frames use FTL's base `SpeedFactor` of `16/60`, retaining existing gameplay multipliers. Queued event choices and travel need an explicit bounded advance to complete. Interface drawing and dialog input-delay timers remain active. Clock-v1 runs established bounded update counts, not fixed duration; their historical evidence is not eligible for the new fair comparison. Scoped live v2 control and repeated-timing checks have passed; see the [experiment protocol](visual-experiment-protocol.md). Full-game and model-comparison acceptance remain separate.

The paused map UI refreshes its fuel mode and hover controls under the world gate. Opening the map or choosing a destination does not consume simulation time; pending travel and waiting without fuel progress only through explicit frame budgets.

Outside input received by the game latches the native guard and invalidates the trial, including input received while the model is thinking. The Python transport checks the guard when the model response returns, before dispatching its planned action; this does not cancel an in-flight model request immediately. Input arriving between that check and native dispatch is also rejected by the native guard. The runner records `external_interference`, ends the trial, and restores protected saves without retrying the action. A refusal before dispatch records the proposed inputs separately from sent inputs; an interruption after packet dispatch preserves unknown delivery.

The observation modes are `image` and `hybrid`. Image mode supplies the screenshot and recent input history. Hybrid adds only resource numerals recognized directly in that same PNG. The reader has no native-state or sidecar fallback: unsupported images, obscured fields, partial glyphs, and uncertain layouts omit the affected values. The exact supplied summary and image/crop provenance are retained as `visual.visible_summary` and `visual.visible_summary_provenance`. Full native observations, hidden state, and evaluator assessments never enter the actor input. The older paused-flag-only hybrid condition remains historical.

An input acknowledgement means the input was delivered, not that the intended game action succeeded. The evaluator's assessment is recorded separately. Missing actual frame counts, usage, or latency remain unknown; elapsed wall time is never converted into simulated frames.

Visual reports leave event counts unknown (`null`) because the native telemetry does not provide an event counter; primitive clicks and keys cannot establish that count. Flagship phases completed are also unknown unless a valid explicit native phase count is present, or native terminal victory establishes all three phases. Each unavailable metric includes a reason. These reporting rules do not change structured-track scoring.

## Historical clock-v1 acceptance evidence

The following historical artifacts are local diagnostic runs under `harness/runs/validation/visual-v1/`. Their final clock-v1 native DLL has SHA-256 prefix `75c71eb6`, built from patch `2c657fdd`, and its Lua bridge has prefix `89406693`. That build corrects the same-batch tooltip cache while retaining the paused-map fuel-mode/hover refresh and native world gate. Its Lua bridge fixes the startup action-packet double read. Earlier build `8cd1573b` passed the Sol store task but failed the fuel-wait path before the map refresh correction. Complete runtime and prompt provenance is stored with each run; results on earlier builds retain their original scope.

| Run | Observed result | Scope |
| --- | --- | --- |
| `tooltip-final-20261009T0504` | All 14 automated clock/input checks passed. Independent direct inspection of all 13 PNG cases confirmed stale tooltip removal, correct delayed Open/Close text, empty-space clearing, and menu/key/click behavior. Menu dismissal shows the normal brief dark fade; the settled capture restores the correct tooltip. | Targeted visual/native regression on `75c71eb6`; `manual-image-review-part-a.json` and `manual-image-review-part-b.json` preserve the observations. No model. Seven original saves restored and verified. |
| `controls-final-20261009T0507` | All nine ordinary-control checks passed again, including paused/zero-frame world freezing, oxygen keys and modifiers, crew drag to the medbay, and the unselected pilot remaining in the cockpit. | Native control regression on `75c71eb6`, without a model. Seven original saves restored and verified. |
| `startup-final-20261009T0428` | All six checks passed: direct startup produced a fresh acknowledged image, retained the opening dialog through an idle hold, and kept the native world-update counter at zero. | Startup regression with Lua `89406693`, without a model. Seven original saves restored and verified. |
| `wait-final-20261009T0415` | All 11 check groups passed, including idle and zero-frame freezes before/after selection. An explicit 120 actual updates completed normal waiting and opened a refugee recovery event offering four fuel. The choice was not selected, so fuel remained zero. | Native fixture on `607776a6` with an injected zero-fuel prerequisite; no model. Establishes the Wait path and event boundary, not receipt of the offered fuel. Seven original saves restored and verified. |
| `sector-final-20261009T0416` | All 11 check groups passed. The queued transition stayed frozen without a budget; 241 actual updates completed arrival in sector 1 from sector 0 and changed fuel 16→15. | Native fixture on `607776a6` with an injected exit-beacon prerequisite; no model. Seven original saves restored and verified. |
| `transition-final-20261009T0417` | All four checks passed again: queued and mid-jump states remained frozen through idle waits and zero-frame input, and bounded advancement completed arrival with exactly one fuel spent. | Native jump regression on `607776a6`, without a model. Seven original saves restored and verified. |
| `sol-store-final-20261009T0347` | GPT-6.1 Sol passed all 11 store-to-arrival checks in four image decisions: one fuel purchase changed fuel 15→16 and scrap 30→27; CLOSE at (854,572) plus 600 frames reached full charge; the model opened the map and selected a connected beacon. The last request allowed 600 frames, stopped at the arrival dialog after 241 actual updates, and left fuel 15. | DLL `8cd1573b`, revised prompt `2b15a30d`. Seven original saves restored and verified. Three archived images were reviewed manually; `manual-image-review.json` confirms the CLOSE target and visible arrival. Diagnostic fixture, not a full game or model comparison. |
| `sol-store-final-20261009T0340` | The earlier Sol run advanced 180 frames into warp, then returned 40 empty zero-frame decisions. Its world counter stayed at 780 and the ship remained in transit. The 45-decision budget ended with store-to-arrival acceptance incomplete. | DLL `512d4a2a`, earlier prompt `309227e9`. `model-stall-review.json` preserves the failure and its interpretation. Seven original saves restored and verified. |
| `transition-final-20261009T0337` | All four transition checks passed: queued and started jumps stayed frozen through idle waits and zero-frame input; bounded advancement completed the selected jump in 241 actual world updates and spent exactly one fuel. | Native clock and travel fixture on `512d4a2a`, without a model. Seven original saves restored and verified. |
| `controls-final-20261009T0339` | All nine capture/control checks passed, covering readable capture, ordinary mouse input, keys/modifiers, calibrated crew drag, paused waiting, and frame accounting. | Native control fixture on `512d4a2a`, without a model. Seven original saves restored and verified. |
| `interference-final-20261009T0339` | All nine checks passed after one addressed `WM_MOUSEMOVE`: input generation changed from 0 to 1, the next planned key was refused before packet dispatch, the guard stayed latched, and action sequence, gameplay, and cumulative world updates remained unchanged. | Native input-guard fixture on `512d4a2a`, without a model. Seven original saves restored and verified. |
| `capture-20261009T0242` | Historical capture/pause checks passed for that run, including readable images, oxygen power/drain, a paused hold, and a zero-frame cursor move. | Predates the final clock fix; not current runtime acceptance. |
| `sol-store-20261009T0242` | Historical GPT-6.1 Sol image run purchased one fuel, closed the store, handled onboard fires, reached full charge, opened the map, and initiated a jump. Its 30-decision budget ended before observed arrival. | Predates the final clock fix. Incomplete store-to-destination acceptance; no completed benchmark game. |

The store encounter was supplied as a fixture prerequisite. Native purchase, closure, charge, travel, and outcome checks remain evaluator evidence. Final acceptance is recomputed from the complete trajectory; a requested jump or changing travel state does not by itself prove arrival. The passing Sol run establishes the short store-to-arrival task on `8cd1573b`; each subsequent native fixture establishes its stated path on the recorded DLL.

The image-only Sol full-game attempt `sol-fullgame-20261009T0420` failed during startup, before its first model decision, when a Lua action packet was read twice and its acknowledgement timed out. Its trajectory contains only metadata and a terminal error, so it has no recorded gameplay score. All seven original saves were restored and verified. The startup regression above validates the fix; the failed attempt remains a harness failure, not a model gameplay result.

The retry `sol-fullgame-20261009T0429` used GPT-6.1 Sol through Codex CLI in image mode, with budgets of 120 decisions, 3,600 seconds, and eight consecutive idle decisions. The root agent intentionally stopped this diagnostic after 53 decisions to investigate a confirmed tooltip display defect. Observed progress was two jumps, three explored beacons, one destroyed enemy ship, 31 collected scrap, and native score 81. The final recorded state had hull 27, fuel 16, three crew, and no victory. All seven original saves were restored and verified. This is an incomplete diagnostic trial, excluded from comparisons.

The raw Ctrl+C lifecycle reason remains `user_interrupted`. Here it records the root agent's intentional diagnostic stop, not a human request to stop or a model concession. The saved trajectory and read-only audit preserve the original evidence.

The display defect occurred within a zero-frame batch containing multiple inputs: a tooltip associated with an earlier button could remain visible at the final cursor position. Input-delivery and world-counter checks passed. This was a tooltip-cache display defect within one batch, not simulation advancing across model decisions. The current build passes the targeted tooltip and ordinary-control regressions above; the older trial retains its original limitation and diagnostic stop.

The bounded Sol image pilot `sol-pilot-final-20261009T0508` completed normally through Codex CLI on the current frozen build: 24 decisions in 542.959 seconds, ending at `decision_budget`. It made one jump, visited two beacons, and ended with native score 20, hull 17, fuel 15, scrap 30, three living crew, and no kills or victory. The final independent audit passed for all 24 decisions and 25 PNGs, exact image-only actor inputs, no tool use, runtime identities, input/clock accounting, consistent terminal reports, and all seven restored live save hashes. FTL closed cleanly. Event count and intermediate flagship phases are explicitly unavailable. This is a completed bounded integration pilot, not a completed full game or evidence of better model performance; screenshot fidelity is covered separately by the thirteen-image tooltip acceptance.

The rebuilt wheel and source packages pass validation on the final tooltip and truthful-metric reporting source: 1,114 tests passed and eight skipped in both the checkout and an independently extracted source package. Seven skipped compiler-dependent cases passed separately as WSL native executable checks; one Windows symlink test requires an unavailable privilege. Installed-wheel CLI, all three public validators, clock/provenance guards, and dashboard assets/API pass. All 86 wheel and 130 source-package source files match the checkout. Exact artifact hashes and the detailed receipt are in `dist/package-validation.visual-v1-python.json` and `dist/SHA256SUMS.visual-v1-python.txt`. The fixtures use canonical trajectory replay. Packaging and integration checks do not replace gameplay acceptance.

The prompt changed between the stalled and passing Sol runs: it now explicitly identifies the small ship against a star field as a travel animation and tells the actor to request bounded time until normal ship view or an arrival event appears. The DLL and declared idle budget also changed. These runs show the outcome of an implementation/prompt revision; they are not a controlled model-performance comparison. There is no image-versus-hybrid comparison result yet.

The standalone interference diagnostic uses `scripts/validate_visual_interference.py` with a new `--output` directory and the same protected-save lifecycle. It never sends global desktop input or changes focus. Its Windows client coordinates are independent of rendered screenshot pixels: the earlier passing `interference-20261009T0331` run measured an 853×480 Windows client and a 1280×720 render. Both coordinate spaces are recorded in `proof.json`; no screenshot-to-Windows scaling is inferred for this harmless movement.

## Resource-summary visibility review

The implemented `ftl-visible-hud-pixels-v1` reader recognizes current hull, fuel,
scrap, missiles, and drone parts from exact raster glyphs in supported 1280x720
PNGs. It checks PNG integrity, numeral alignment, anchor colors, and overlap.
Single-digit hull is deliberately omitted because its layout cannot be accepted
with the same conservative evidence. Twelve manually transcribed archived image
cases and focused malformed/occlusion tests exercise the reader. A visible glyph
changed into another valid aligned glyph cannot be distinguished from a real
value change using pixels alone. This is a limited HUD transcription aid, not a
general screenshot-understanding system.

The following earlier review motivated the observation boundary:

| Screen inspected | Readable resource evidence |
| --- | --- |
| Intro event and unobscured ship view | Current hull, fuel, scrap, missiles, and drone parts are visible above the dialog or ship. The intro example is one event layout, not evidence for every event dialog. |
| Store purchase and closure | The top HUD remains visible. In the store fixture, one purchase changed fuel from 16 to 17 and scrap from 49 to 46; current hull 28, missiles 6, and drone parts 3 remained visible. The purchase image also contains floating `+1`/`-3` labels. |
| Beacon map | The late store-fixture map image visibly shows current hull 27, fuel 17, scrap 46, missiles 6, and drone parts 3. The map and jump tooltip in this example do not cover these numerals. |
| Menu, options, controls, hangar, upgrades, equipment, crew, sector selection, and terminal screens | No visibility acceptance yet. These states must not receive a resource summary based on retained native data. |

Do not expose `hull_max` yet: these examples print current hull and a segmented bar, not a separate maximum numeral. Exact crew health, room oxygen, drive charge, and hidden upgrade prices are also outside this proposed summary.

The implemented resource contract uses the captured pixels themselves rather than a native visibility flag. Missing, stale, or unknown visual evidence omits the affected field; it never reuses a prior value. Maximum hull, exact crew health, room oxygen, drive charge, and hidden prices remain outside this summary.

The existing `visual_evaluator` store/map/choice flags are insufficient for a visibility gate. `menu_buttons` is populated even when the menu is closed, and store inventory remains available after its window closes. Neither is a visibility indicator, and neither is used by the pixel reader.

The exact admitted summary must match `visual.visible_summary`. Additional image cases may reveal layouts requiring stricter omission; preserve those failures and version the extractor before any new comparison cohort.

## Additive trajectory contract

Visual decisions retain the existing `kind: "step"` record, lifecycle, `obs`, `thought`, and `model` fields. `model.latency_seconds` keeps its existing meaning. The new `visual` object is additive:

```json
{
  "observation_mode": "hybrid",
  "before": {
    "path": "screens/0001-before.png",
    "width": 1280,
    "height": 720,
    "frame_id": "decision-0001-before",
    "sha256": "<sha256 of the exact PNG supplied to the model>"
  },
  "after": {
    "path": "screens/0001-after.png",
    "width": 1280,
    "height": 720,
    "frame_id": "decision-0001-after",
    "sha256": "<sha256 of the resulting PNG>"
  },
  "inputs": [
    {"type": "click", "x": 1150, "y": 620, "button": "left", "modifiers": [], "delivery": "delivered"}
  ],
  "advance": {"requested_frames": 60, "actual_frames": 12,
    "visual_clock_version": 2, "fixed_step_numerator": 1,
    "fixed_step_denominator": 60, "simulated_seconds": 0.2},
  "outcome": {"status": "unknown", "summary": "Input delivered; intended game action unverified."},
  "visible_summary": {"fuel": 16, "scrap": 30}
}
```

Image paths use forward slashes and are relative to the trajectory file's directory. Images are immutable after recording. `frame_id` is an identity string, not an elapsed frame count. Inputs support `click`, `move`, `drag`, and `key`; drags add `to_x`/`to_y`, key inputs may add `modifiers`, and rejected inputs carry a `reason`. Outcome status is `observed` or `unknown`; the summary describes evaluator evidence rather than silently declaring success from delivery.

Actual capture references additionally carry `capture_id`, `action_seq`, `visual_clock_version`, decimal-string `world_updates`, and decimal-string `external_input_generation`. These bind the archived image to its native acknowledgement and guarded world state. An `external_interference` record retains the before-image, `visual.planned_inputs`, and `visual.external_input_guard` evidence, including whether a packet was dispatched. It must not fabricate an after-image or actual frame count.

## Dashboard replay

Run the existing local dashboard against the output directory, then select the visual trajectory by run name. The **What the model saw** panel opens the latest recorded model decision. Native-only fixtures use **Recorded game view**, since no model received their images. Previous/Next and the decision slider can inspect the complete history, including decisions older than the live feed's 120-record tail. **Before** shows the decision image; **After** shows the resulting window. Requested input markers can be hidden, and the original image can be opened at full resolution. Images are not enlarged beyond their original dimensions.

Markers use an SVG view box matching the original screenshot dimensions, so they remain aligned when the browser resizes. They appear only on the before image. Rejected inputs use a distinct marker style. The panel separately displays input delivery, requested/actual simulation frames, model response time, and the evaluator's assessment.

Outside-input interruptions remain in replay and the decision feed. A refusal before dispatch labels the proposed inputs **not sent** and draws no planned click markers. An interruption after a packet was sent retains unverified delivery. The replay includes the expected/observed input generation and action sequence, and does not claim that an absent after-image shows the resulting game state.

Attempts with no recorded in-game observation have no score. Metadata, a terminal error, or a menu-only observation cannot produce a zero-score gameplay result; a genuine recorded in-game score of zero remains valid.

The read-only API has two additive endpoints:

- `/api/replay?sel=<trajectory-key>&index=<visual-decision-index>` returns one visual decision; omitting `index` selects the latest. Its index counts visual decisions, not lines or frames.
- `/api/artifact?sel=<trajectory-key>&record=<record-ordinal>&phase=before|after` serves the image referenced by that exact record slot. Clients never supply an arbitrary image path.

Image serving is restricted to the selected trajectory's own directory inside the configured run root. Absolute paths, traversal, Windows drive/UNC/alternate-stream paths, and resolved symlink escapes are rejected. The server checks image content, a 20 MiB maximum, and the recorded SHA-256 when present. Changed or missing artifacts produce an explicit unavailable-image state.

## Acceptance sequence and remaining work

1. Admit the exact runtime and source identities before running a cohort. The
   current clock-2/fresh-start-v3 acceptance covers scoped controls, transitions,
   interference and nine repeatability probes. Older clock-1 DLL hashes in the
   historical sections above are not current runtime requirements.
2. Finish the frozen 36-cell challenge matrix. All nine Sol/image cells are
   complete at the latest snapshot; Sol/hybrid and both Luna modes remain.
   Preserve setup, model, budget and native-loss outcomes with their exact images.
3. Run the separately declared fixture-free sector pilot and four full-game
   conditions when experiments resume. Require audited native victory or defeat
   for complete games. Neither earlier budget-limited pilots nor the challenge
   crew-loss screen establishes this requirement.
4. Compare image and hybrid only under matched conditions. The conservative
   same-PNG reader is implemented; a performance benefit is not established.
   Report every exclusion, available usage and latency without inferring cost
   or resolved backend weights from a requested model name.
5. Complete portable native acceptance/evidence setup, validate the merged
   headless runtime, and rebuild/test release packages. Passing unit
   tests and an installed-wheel smoke do not replace live gameplay evidence.

The [experiment protocol](visual-experiment-protocol.md) defines the commands,
budgets and acceptance rules; [NEXT.md](NEXT.md) records current progress.
Store demonstrations and historical fixture captures remain diagnostic evidence.
Save backup, cooperative stopping and verified restoration remain mandatory
around live validation.
