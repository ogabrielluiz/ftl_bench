# Current validation and next work

**WIP / alpha. Current status as of 2026-11-07 UTC. Historical snapshots retain their original dates.**

## Scoped controller admission and new cohorts (2026-11-07 UTC)

The protected `47db7f6` collection passed all eight startup checks and all nine
fixed-step timing probes, with exact frame equality within each case. The
independent review passed eight targeted rejection checks. Scoped admission
binds 85 executable source files and 579 evidence files. The final receipt
records `controller_admission: true` and `production_accepted: false`.

Local admission files are under
`harness/runs/validation/visual-v1/store-admission-47db7f6-20261107/`.

| File | SHA-256 |
| --- | --- |
| `startup/validation.json` | `b4afc802acb5bacbca7119eb61c5af148d42333476a5324de86b09bfabb58f2c` |
| `timing/fixed-step-report.json` | `d072ba364275c3406458f7452aa6a666b10fd9c92ae4e62bd359f84a48f9296d` |
| `review/review.json` | `c9eba6413fcf90a7e3342e906bf94378339590f717b69ae8a5df49dbd103b565` |
| `controller-admission-spec.json` | `86d284bf02808508e10faf15523bfd4e711f86b86200c4d7db9799f81a687e83` |
| `controller-admission.json` | `fa2e9a45332038088afa49e69d581e0063ce62c4d7c1c72a3e5c09a9f7f0c82c` |

Both cohorts are frozen under `harness/runs/visual/` with Codex CLI `0.162.1`.
Budgets are listed as decisions, wall seconds and idle decisions.

| Cohort | Embedded protocol SHA-256 | Conditions | Budgets |
| --- | --- | --- | --- |
| `matrix-store-47db7f6-20261107` | `0c6bdfe7fbb03dd1c314ca8062d318be34cb9ed6c083e48dbbf39f187fbac942` | 36 challenge cells | 60 / 1,800 / 8 |
| `fullgame-store-47db7f6-20261107` | `a4f81ad3fb081bda9a891c3d45855e137470ca26527ceb40eb04bcbfe9eb0b54` | Sol/image sector-one pilot, then four full-game cells | 1,500 / 86,400 / 8 |

### Sol/image challenge checkpoint (02:00:58 UTC)

All nine Sol/image cells finished and are eligible. Three met their native
task criteria, and six stopped at their budgets. There were zero technical
exclusions. The results describe this image-only condition and fixed seed.
The remaining 27 challenge cells and all five full-game entries are planned.

| Challenge | Successes | Decisions by repeat | Native result |
| --- | --- | --- | --- |
| Combat | 0/3 | 33 / 60 / 20 | Two scout escapes without rewards and one native kill with an original crew loss. |
| Fire and crew recovery | 3/3 | 5 / 5 / 3 | All fires extinguished, crew at full health, oxygen recovered and ship stayed at the original beacon. |
| Repair, charge and escape | 0/3 | 12 / 11 / 12 | All three spent one fuel and arrived at a connected beacon with all crew alive. The charged drive was ready, but engines remained at 1/2 before departure. |

All three fire trials together acknowledged 4,020 native updates. They reported
244,949 input tokens (198,144 cached), 3,624 output tokens (1,471 reasoning)
and 139.009 seconds of CLI latency across 13 completed turns.
Across all nine cells, 161 completed turns reported 3,045,189 input tokens
(2,306,048 cached) and 37,692 output tokens (13,900 reasoning). Total CLI
latency was 1,602.486 seconds, with a pooled median of 9.085 seconds and no
recorded reconnects. Native acknowledgements covered 30,790 of 32,133
requested updates.

Independent review matched 161 actor inputs and 170 PNGs, with input-guard
generation zero at every acknowledgement. Canonical gameplay starts matched
within each scenario. Dashboard HTTP matched all nine completed cells and
the final trial's first and last replay image pairs. The live boundary
verified 15 inventory roles, seven original saves, 85 source pins, FTL
closed and no pending-launch marker.

The nine Sol/hybrid challenges come next. Then run the Sol/image sector-one
pilot and both Sol full-game modes before the 18 Luna challenges and two Luna
full games. Rendered dashboard verification is deferred while the operator
is away.

Local receipts under `dist/store-admission-47db7f6-20261107/`

| File | SHA-256 |
| --- | --- |
| `store-matrix-sol-image-fire-crew-recovery-repeat03-independent-review.json` | `6301f32a30dd71b466bdc8bd248044790c6f72e2ad36570dd11a89df60feb2a2` |
| `store-matrix-sol-image-repair-charge-escape-repeat01-independent-review.json` | `41ef7c083e0b60c1f5d4c217a93c5e1a5b852f58e534e9bb900761f7316c2635` |
| `store-matrix-sol-image-repair-charge-escape-repeat03-independent-review.json` | `273a5c71f5b6a74711555576d2738b846474f411541e70b59d21fce9672896cf` |
| `store-live-boundary-20261107T020058310835Z.json` | `5876a391e0754b4fc6460faba5cdb180852239fd35684092e1d4f7496f2ba3f4` |

The independent input aggregate is
`dist/store-ui-build/matrix-store-sol-image-nine-cell-actor-input-independent-audit-20261107.json`,
SHA-256 `9c683a06120cbcdc909409583bc54191aa11352a7003103b2669ca447336a6ee`.
It joins the nine individual receipts, exact prompts, event streams and images.

### Sol/image combat batch (01:37 UTC)

At this boundary, three of 36 challenge cells had finished and 33 remained
planned. All three combat repeats were eligible, with zero task successes
and zero technical exclusions. The comparison, visual reports and dashboard
API classify all three terminations as `budget_exhausted`. The native goal checks distinguish
the reasons each attempt missed the task.

| Repeat | Decisions | Budget that ended the run | Native outcome |
| --- | --- | --- | --- |
| 1 | 33 | Idle decisions | Scout escaped at 6 hull with no reward. |
| 2 | 60 | Total decisions | Scout escaped at 1 hull with no reward. |
| 3 | 20 | Idle decisions | Native kill and reward of 18 scrap, three fuel and one missile. Initial crew ID 2 died before the reward. |

The third trial's fixture `validation.json` and `run.json` classify the crew
loss as `failed_native_loss`. Its final hull was 25 and its native score was
58. All repeats shared canonical gameplay-start SHA-256
`1759586db7dc376c6513220994a1e2e6e25b6fefa42c488cb5927b9481e36850`.
Independent input review matched 113 exact prompts and 116 PNGs. The native
clock acknowledged 23,641 of 23,913 requested updates. Input-guard generation
remained zero. The CLI recorded no tool calls or reconnects and reported no
resolved backend model identity.

The 113 completed turns reported 2,144,248 input tokens (1,638,144 cached) and
29,215 output tokens (11,559 reasoning). Total CLI latency was 1,205.630
seconds, with a pooled median of 10.478 seconds. Dashboard HTTP checks matched
the saved comparison and replay PNGs. The 01:37 UTC live boundary verified 15
inventory roles, all seven original saves, 85 source pins, FTL closed and no
pending-launch marker. Local receipts under `dist/store-admission-47db7f6-20261107/`
include the [independent review and live boundary hashes](#combat-batch-receipts).

Fire and crew recovery was the next planned group at this boundary. The
full-game ledger had five planned entries.

#### Combat batch receipts

| File | SHA-256 |
| --- | --- |
| `store-matrix-sol-image-combat-repeat03-independent-review.json` | `4f917ac7acc470d0855f8ac7b4ad835bd0beab72921e0e2e316e466c400af04d` |
| `store-live-boundary-20261107T013706803412Z.json` | `0552317c61ba04878229b34f2cc41052b3e21c841c107127bb117876db0476f3` |

## Protected store refresh passed (2026-11-07, 00:46 UTC)

The isolated `store-ui-refresh` checkout built executable commit `47db7f6`.
The Windows Release DLL linked under the pinned Clang 12 toolchain, and the
build completed at 00:42 UTC. The preliminary Debug dependency build failed
in vcpkg's Boost.Filesystem port. The retained log records that failure and the
subsequent successful Release compile and link.

The Release DLL was independently verified and installed at 00:45 UTC.
Its SHA-256 is
`e8cd1f3d8df3dff115f8c6bb20096b4748bc5da8aa77ff0ebffef2dcadf10923`,
and its provenance SHA-256 is
`7f0abe4c5a2372f81e685c72d95989ac01ca7fe181a38fa3558fc26b9770c2a8`.
The installer replaced the DLL and provenance. Installed `ftl.dat` matched the
verified baseline, and both rebuilt mod archives matched the prior member
bytes. The original runtime pair remains in the installation backup.

The same protected probe ran on the prior and replacement DLLs. It reached the
store through a normal jump and Continue, then supplied two controlled hull
changes in a disposable session. Both runs quoted 6 scrap at hull 27. After
closing the store and reducing hull to 22, the prior DLL still quoted and
charged 6. The replacement quoted and charged 16. The reopen and Fix All clicks
each admitted zero frames, with the world counter and native timer unchanged.
Both runs repaired to hull 30, preserved the hidden arrival and visible store
gates, and restored all seven original saves and the prior Lua bridge.

Independent review rehashed 123 declared artifacts and 85 executable source
pins per run, joined all twelve steps to their PNGs and native records, and
verified the final live inventory with FTL closed and no pending-launch
marker. This is a fixture-only result with zero model calls. The refresh
covers the visible vanilla buy tab. Custom stores remain outside its scope.

See [the store refresh evidence](native-store-refresh.md) and
[the admission workflow](native-acceptance.md#prospective-portable-controller-admission).

Local receipts in the isolated checkout:

| Receipt | SHA-256 |
| --- | --- |
| `dist/store-ui-build/operator-evidence/build.log` | `74ad582dd67c5dc0463c090ba492d09e0154710d295e2f369f897cd80004b4fa` |
| `dist/store-ui-build/installation-20261107T004525896415Z-8e1fb814/independent-build-review.json` | `73dee5ada7ea74dd5341bbb8b50c9d5f32a26881426f2f3dc6e599c0c082fbb7` |
| `dist/store-ui-build/installation-20261107T004525896415Z-8e1fb814/result.json` | `dc8df2b6268ab8577245b837d1cece59b964e4e6919577bd0bb933eb586637af` |
| `dist/store-ui-build/store-refresh-red-green-independent-audit-20261107.json` | `67a8db8c8d5115250262f654cf012ed07be0701615574668d1216f1e6a011036` |

## Confirmed store price defect and cooperative stop (2026-11-07, 00:15 UTC)

The Sol/hybrid full-game attempt exposed a native GUI cache defect in the
benchmark's zero-frame decision path. At the first store, the repair-all price
was initialized with 27 hull: three missing hull at two scrap each, or six scrap.
After the store closed, fire damage reduced hull to 22. Reopening and purchasing
with zero requested frames kept the old quote. The screenshot showed current
hull 22, unit repair price 2 and repair-all price 6; the purchase restored hull
to 30 while charging six scrap instead of the current cost of sixteen.

Static inspection of the exact installed FTL executable and pinned native hook
establishes the mechanism. `RepairStoreBox::OnLoop` recomputes the cached total;
rendering and purchasing read it, while repair-all applies the current hull
deficit. Native `Store::Open` only opens the window. Ordinary paused GUI ticks
refresh its boxes, but the benchmark skips `CommandGui::OnLoop` while frozen
and refreshes only map UI. The cache therefore persists across separate
zero-frame decisions. A later store is a useful positive control: one admitted
frame refreshed its quote, and repairing 12 to 30 hull correctly cost 36 scrap.
The causal receipt retains exact PE byte spans, hashes, source and screenshot
references. It does not claim an unperformed native replay or general prevalence.

The assistant operator requested the official cooperative stop at
00:15:14.206678 UTC, with reason
`confirmed_stale_store_repair_price_during_zero_frame_decisions`. The game had
286 dispatched decisions. The 287th completed model response was retained as
cancelled before dispatch, with no dispatched actions, acknowledged frames or after-image.
The prior observation and world counter remained unchanged. This is an
operator interruption due to a confirmed harness defect, not a model concession,
native defeat or full-game completion.

The controller subsequently refused continuation because the saved child was
interrupted; its nonzero parent exit is that guard, not failed save restoration.
The live boundary audit at 00:15:57 UTC verified all seven original saves, all
15 file roles and 84 frozen executable source pins, with FTL absent at both
checks and no pending-launch marker. Dashboard HTTP showed one completed
Sol/image defeat and one incomplete hybrid attempt, with the pilot excluded.
The raw reports and their integrity verdicts remain unchanged; mechanical
input integrity does not establish correct store pricing.

At interruption the run was in native sector index 1, with 24 hull, four living
crew and score 438. These are diagnostic observations, not qualified comparative
performance. The cohort has two unstarted Luna full games; the challenge matrix
retains all eighteen Sol results and eighteen unstarted Luna cells. Do not resume
either cohort after changing executable sources or silently retry the hybrid cell.

The terminal input audit reconstructed all 287 exact hybrid prompts and PNGs,
including the cancelled response's input. All 92 distinct crop states have
direct or exact prior pixel witnesses. There were 51 turns with conservative
omissions, covering 79 numeric field slots. Reported completed-turn usage,
including the cancelled turn, was 5,418,781 input tokens (4,161,280 cached) and
59,115 output tokens (16,807 reasoning), with 2,707.964 seconds of CLI latency.
Cached and reasoning tokens are subsets; no reconnect was recorded. These
mechanical input and usage checks do not validate the store-price behavior.

The subsequent rebuild and protected store probe ran in
`ftl_bench-store-ui-20261107`. Their results are recorded above. The preserved
attempt and its original runtime remain the evidence for this interruption.

Local receipts under `dist/resume-20261106/`:

| Receipt | SHA-256 |
| --- | --- |
| `focus-fullgame-sol-hybrid-stale-store-price-20261107T001714Z.json` | `4a82a980ec4db64ad52ad5ffd3278b09dd2d0268640fe5bce1440f750ea2833b` |
| `focus-fullgame-sol-hybrid-stale-store-native-dispatch-20261107T003117Z.json` | `316c06c40ca9890fd822855e5110a7e8b214a795920a10e03e1fb36b78bda458` |
| `fullgame-live-cleanup-20261107T001557277146Z.json` | `8a2010e5d4dd0c7644170bcd28b68471ab29286a52df593d2d42ef8e3444b51a` |
| `focus-fullgame-sol-hybrid-dashboard-http-20261107T001825Z.json` | `0039a56596fcd0791f8acd4d68095f6239d6d61f4fb5cd8b9b1f434b2a4a0c64` |
| `fullgame-sol-hybrid-terminal-input-audit-20261106.json` | `30d596697b5edb352394012878bc25198153ffab3617a257cb32bdd32d6e1dcc` |
| `fullgame-focus-sol-hybrid-interrupted-independent-review-verified-20261107.json` | `1dac062f1e97080a359bc150984fada7f3940782ad9f4d1fc9c9fc74828f01e6` |

## Sol image full game: first native ending (2026-11-06, 23:12 UTC)

The Sol/image full-game cell in `fullgame-focus-5155dab-20261106` ended in
audited native defeat after 42 decisions and 43 archived screenshots. The final
native state and screenshot agree that all crew died at the second beacon in
the starting sector. Final hull was 18, oxygen 85%, scrap 49, fuel 16 and native
score 59. Twenty fires remained across nine rooms. Before defeat, the ship made
one connected jump and collected 19 scrap and one fuel after destroying the
first enemy. These observations do not isolate every crew member's death mechanism.

This is the first verified full-game ending in the current cohort: **1/4**,
with one defeat and no victories. The earlier pilot remains excluded. Both
trials retain their original outcomes and artifacts. Sol/hybrid is next, then
Luna's eighteen challenge cells and both Luna full-game conditions. A native
defeat completes a declared full-game attempt; it does not establish strong
gameplay, later-sector coverage or a model ranking.
The Sol/hybrid full-game cell started at 23:13:43 UTC under the same frozen
protocol. Its ongoing activity is separate from the settled image result.

The independent saved review reproduced the exact two-trial comparison and
verified child admission, all 42 tool-free CLI turns, 6,633 acknowledged updates
within 7,083 requested updates, and no reconnects or input interference. The
canonical fresh gameplay state matched the pilot's seed-1 start; each run's
different opening PNG was authenticated separately. All exact image-only
prompts, attachments, permitted acknowledgements/history and actor memory
reconstructed, with no native gameplay summaries or evaluator fields.

The CLI reported 795,593 input tokens, including 581,888 cached, and 12,237
output tokens, including 5,268 reasoning. Total CLI latency was 523.036 seconds,
median 12.1755 seconds. Cached and reasoning counts are subsets. The requested
model was `gpt-6.1-sol`; resolved backend identity remained unreported.

The controller exited zero. Saved restoration matched all seven original
saves and prior Lua. A live boundary check at 23:12:49 UTC matched the exact
seven-save inventory, all 15 original file roles and 84 executable source pins,
with no FTL process or pending-launch marker. The dashboard's actual HTTP
response showed one verified defeat and kept the pilot excluded; its opening
and final replay images matched saved hashes. Rendered browser inspection
remains deferred. Earlier cleanup checks remain point-in-time evidence.

Local receipts under `dist/resume-20261106/`:

| Receipt | SHA-256 |
| --- | --- |
| `fullgame-focus-sol-image-independent-review-20261106.json` | `4b469fe2582105161fc04121c5cb06e5a5f16df64c8ec7c6d4092b090e1f5ea8` |
| `fullgame-sol-image-terminal-input-audit-20261106.json` | `912373b656573b0834f96f573c5a6e5b5684c6f896b992016363c3b79b39f0ca` |
| `fullgame-live-cleanup-20261106T231249426964Z.json` | `6bfe96556ea072317d9528fc539a8495958954f0c8f71096759d1871d091af21` |
| `focus-fullgame-sol-image-dashboard-http-20261106T231248Z.json` | `516bc3e890f1c10769b8f0e81b5065b9471ca807ea6d9070367a4cee46abe4ec` |

## Sol image pilot: native defeat (2026-11-06, 22:59 UTC)

The sector-one pilot in `fullgame-focus-5155dab-20261106` finished with
`native_game_over` after 89 decisions and 90 archived screenshots. It made four
connected jumps and reached five beacons, but did not leave the starting sector
(native index 0). The final native state and game-over screenshot agree that all
crew died. Final hull was 7, oxygen 0%, fuel 14, scrap 36 and native score 101.
The observed crew-loss ending does not by itself isolate each death's mechanism.

This is an audited pilot defeat, not a technical exclusion or a completed
full-game condition. The pilot's sector target was unmet. All four full-game
attempts were still planned at this checkpoint; verified full-game endings
remain 0/4 in this cohort. The controller's frozen pilot admission rule accepts
a finished, audited attempt with verified cleanup, independently of sector
success. Next are Sol/image and Sol/hybrid full games, then Luna's eighteen
challenge cells and both Luna full games. Each launched attempt is retained.
The Sol/image full-game attempt started at 23:00:53 UTC under the same frozen
protocol; its live progress does not establish a result or restored saves.

The saved review reproduced the exact comparison and verified fixture-free
Kestrel A/Easy/seed-1 startup, portable child admission and all 89 tool-free
CLI turns. No reconnect or external-input generation change was recorded.
The 13,327 acknowledged updates remained within 15,486 requested updates;
modal and terminal stops can end an advance early. All exact image-only
prompts, PNG attachments, permitted input/acknowledgement history and actor
memory reconstructed. The earlier 20-turn input prefix remained byte-identical.
No evaluator, native gameplay summary or pilot target entered the explicit
actor prompts. The final game-over after-image was not sent back to the actor.

Reported CLI latency totaled 1,108.487 seconds, with a median of 11.719 seconds.
The 89 turns reported 1,685,270 input tokens, including 1,235,200 cached, and
26,195 output tokens, including 11,544 reasoning. These subsets are not additive.
The requested model was `gpt-6.1-sol`; resolved backend identity was unreported.

The controller exited zero after protected cleanup. Saved restoration evidence
matched all seven original saves and the prior deployed Lua. The independent
live boundary audit at 22:59:32 UTC matched all 15 original inventory roles and
84 executable source pins, with FTL absent at both checks and no pending-launch
marker. This is a dated boundary check, not a claim about later live runs.

The actual dashboard HTTP audit showed a completed pilot defeat, clean integrity,
89 replay decisions, verified restoration and zero full-game attempts/endings.
Opening and final replay images matched saved bytes; the opening image also
joined fresh admission. Rendered browser verification remains deferred while
local browser control is disabled and the operator is away.

Local receipts under `dist/resume-20261106/`:

| Receipt | SHA-256 |
| --- | --- |
| `fullgame-focus-sector-pilot-independent-review-20261106.json` | `00dac6463f46436294f80feadb3a26612da9e3d1bc8456341e0d9c21bea7079d` |
| `fullgame-sol-image-sector-pilot-terminal-input-audit-20261106.json` | `8cbc27671ad9d09184cc2330f6a5cc5e1dadb2c43770681cfd8d5934cc2de452` |
| `fullgame-live-cleanup-20261106T225932041028Z.json` | `a4251c6c403bcd8454f1ab6f0711ac62a2c14c0537142ca6d08a7cb9d40124b8` |
| `focus-fullgame-sol-image-pilot-dashboard-http-20261106T225935Z.json` | `7d4aa4d0afc36016a06fa726b2ada0fef1f2ede4c6537e043aad81a3171b7052` |

## Sol challenge block complete (2026-11-06, 22:26 UTC)

All eighteen Sol cells in `matrix-focus-5155dab-20261106` completed and remain
eligible, with ten task successes and eight idle-budget stops. No technical
exclusions or CLI reconnects were recorded. All eighteen attempts remain
recorded in this cohort.

| Challenge | Image task successes | Hybrid task successes | Image decisions by repeat | Hybrid decisions by repeat |
| --- | ---: | ---: | --- | --- |
| Combat | 2/3 | 1/3 | 13, 9, 21 | 43, 25, 18 |
| Fire and crew recovery | 2/3 | 1/3 | 5, 11, 3 | 12, 11, 5 |
| Repair, charge and departure | 2/3 | 2/3 | 12, 4, 4 | 4, 6, 11 |
| Total | 6/9 | 4/9 | 82 | 135 |

The eight unsuccessful trials ended at the idle limit. Two scouts escaped
without rewards, three trials left crew injured, two departed before full
engine repair, and one lost a crew member despite collecting the reward.
The native outcome and terminal reason remain separate. Scores alone do not
establish task success.

All eighteen canonical reset states were recomputed: every hybrid trial matches
its image counterpart, and repeats match within each task. The task, seed,
instructions, controls and budgets remain frozen. Full PNGs can differ; the
audits bind each actual actor capture independently. These are descriptive
results for three fixed situations, with three repetitions per mode. Luna has
not started, so the declared four-condition matched groups remain incomplete.
No general model ranking or hybrid performance benefit is established.

| Mode | Audited CLI turns | Reported input tokens | Cached subset | Reported output tokens | Reasoning subset | Reported CLI latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Image | 82 | 1,548,076 | 398,080 | 18,439 | 6,892 | 855.210 s |
| Hybrid | 135 | 2,546,533 | 1,671,680 | 28,499 | 9,201 | 1,329.201 s |
| Total | 217 | 4,094,609 | 2,069,760 | 46,938 | 16,093 | 2,184.411 s |

Every recorded turn was tool-free with one harness attempt. Latency covers
reported CLI calls, not total elapsed trial or audit time. Cached tokens are
a subset of input; reasoning tokens are a subset of output. The requested
model is `gpt-6.1-sol`; resolved backend identity remains unreported. The
aggregate review retains every trial's hull, crew health, native score and
components, latency, wall time, usage, terminal reason and native goal checks.

The nine hybrid input audits reconstructed all 135 exact prompts and PNG
attachments, permitted input/acknowledgement history and actor memory. Every
reported HUD value and its full crop/anchor provenance reproduced from that
same PNG. Previously inspected exact crop bytes were reused as visual witnesses;
new states were inspected directly. Hull was supplied on 132/135 turns, drone
parts on all 135, and fuel, scrap and missiles on 127 each. The omissions were
three hull-anchor rejections under a warning or cursor, and eight turns with
reward overlays across the other three fields. This measures reporting coverage
in the observed sample, not general OCR accuracy. `paused: true` remains the
public decision-interface flag, separate from the five PNG-derived numbers.

In fire repeat one, the image and hybrid opening screenshots showed the same
hull-anchor occlusion. The final hybrid repair trial also supplied actual
settled arrival screenshots to the actor; the earlier successful hybrid repair
repeats ended at arrival and supplied only the pre-jump map to their final
decisions. No evaluator or hidden gameplay fields were present in the explicit
prompts.

The saved review reproduced the full eighteen-member comparison and verified
the prior seventeen trials' referenced artifacts unchanged. All original save
backups and restorations passed. At 22:26:21 UTC, the live boundary check matched
all seven saves, prior Lua, six runtime files and 84 executable source pins,
with no FTL process at either process check and no pending-launch marker.

Local receipts under `dist/resume-20261106/`:

| Receipt | SHA-256 |
| --- | --- |
| `matrix-sol-18-cell-block-independent-review-20261106.json` | `0cd8ada62b0e00c7cf068ff591acb0652504c59cfa8f09ddb26fd0e12d074d12` |
| `matrix-sol-hybrid-input-audit-aggregate-20261106.json` | `1adaab1a59214700f03fe764fc174678bd80a526df42765584492966124c1400` |
| `matrix-live-cleanup-20261106T222621845413Z.json` | `914037279a5770a4f41df3986c71c021db0d83d8f0288ffd708279f72e11bba4` |
| `focus-matrix-sol-eighteen-cell-dashboard-http-20261106T222654Z.json` | `d287b75d5ab31353f5d48ce6590dca65a4878324892603b262b1dac48c77031d` |

The final actual HTTP audit matched every Sol row, per-task/mode counts and the
last repair trial's native failure, eligibility and exact replay PNG/HUD data.
Rendered-page verification still awaits enabled local browser control.

Next is the Sol/image sector-one pilot in `fullgame-focus-5155dab-20261106`,
then both Sol full games. Read-only preflight matched its frozen sources and
evidence, Codex CLI and six installed runtime files; protected child admission
runs again before model calls. All five full-game cohort cells are still planned
at this checkpoint. After both Sol full-game attempts, run Luna's eighteen
challenge cells and both Luna full games. Only audited native victory or defeat
in a full-game cell counts toward the four required endings; pilots, challenge
results and budget stops remain separate.

## Sol hybrid combat and input audit (2026-11-06, 22:00 UTC)

The first three hybrid cells completed in `matrix-focus-5155dab-20261106`.
All are eligible, with one task success and two idle-budget stops. The full
twelve-cell checkpoint has seven successes, five idle-budget stops and zero
technical exclusions. Every attempted outcome remains recorded.

| Repeat | Gameplay outcome | Decisions | Final hull | Crew alive | Native score | Median CLI latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Scout escaped; no reward | 43 | 22 | 3 | 40 | 10.115 s |
| 2 | Enemy destroyed, 18 scrap collected, one crew lost | 25 | 27 | 2 | 58 | 9.071 s |
| 3 | Enemy destroyed, 18 scrap collected, all crew survived | 18 | 25 | 3 | 58 | 11.816 s |

Repeat two is a native `failed_native_loss` because the public task requires
all crew to survive. Its comparison category is `budget_exhausted`, describing
the later idle-budget stop. The reward and score do not establish task success.
Repeat one's raw enemy-destruction counter changed on escape without a reward;
the archived screenshot and strict evaluator preserve that distinction.

Canonical starting gameplay signatures match all three image combat controls.
Image-only combat achieved 2/3 and hybrid 1/3 for this fixed encounter. These
three repetitions describe this local sample. Luna is still unstarted, and
no complete four-condition matched group or general model ranking is claimed.

Independent input audits reconstructed all 86 hybrid prompts and exact PNG
attachments, actor memory and permitted action/acknowledgement history. The
frozen reader reproduced every numeric summary and its crop/anchor provenance;
distinct reported crop states were visually inspected or joined to exact
previously inspected crop bytes. Only the five allowed numeric HUD fields
come from the PNG; `paused: true` is the public decision-interface guarantee.
No native evaluator fields were present in the explicit actor prompts.

The first repeat omitted hull once under a flashing red warning and restored
it when readable. The second omitted fuel, scrap and missiles during eight
turns with reward pop-ups obscuring those fields. The third supplied all five
readings on every turn. These observed omissions used no hidden-state fallback.
This is finite live coverage of the frozen reader, not every possible layout.

Hybrid combat totals are 86 audited tool-free turns, 1,629,947 input tokens
(1,042,432 cached), 19,891 output tokens (6,775 reasoning) and 896.159 seconds
of reported CLI latency. Across all twelve cells: 168 turns, 3,178,023 input
(1,440,512 cached), 38,330 output (13,667 reasoning) and 1,751.369 seconds.
Cached tokens are a subset of input and reasoning tokens a subset of output.
There were no recorded reconnects;
the requested model is Sol, while resolved backend identity remains unreported.

The saved outcome review rederived the full twelve-member comparison and
verified the prior eleven trials' referenced artifacts and outcomes unchanged.
All saved restorations passed. The separate live boundary check at 22:00:08 UTC
matched all seven saves, prior Lua, six runtime files and 84 source pins, with no FTL process
at either process check and no pending-launch marker.

Local receipts under `dist/resume-20261106/`:

| Receipt | SHA-256 |
| --- | --- |
| `matrix-sol-hybrid-combat-repeats-independent-review-20261106.json` | `580eae02802be151c1cd2dceb9e125bee5b33b11266bb9248cac64b8f639814f` |
| `matrix-sol-hybrid-combat-repeat01-actor-input-pixel-audit-20261106.json` | `f67a4a1e2227c92174113b87e605e5758e2cb37c2aecfa01d3c54abf3976daa9` |
| `matrix-sol-hybrid-combat-repeat02-actor-input-pixel-audit-20261106.json` | `48095245aabba840be7efdb471a0487d367f10757808f7b792b7d642c83ffcb4` |
| `matrix-sol-hybrid-combat-repeat03-actor-input-pixel-audit-20261106.json` | `0d8dec6010dd7585120a85dc7c0ff30322666581e4014a2634576e32c33bfdfc` |
| `matrix-live-cleanup-20261106T220008048320Z.json` | `ebd3c2ecbcc8ca8ff5c6e4f2014cdbdb414aa1662f87f66128a015e8bb6877de` |

The QA HTTP audit verified the first hybrid trial's running-to-terminal
projection, task failure versus eligibility, restored saves, exact before/after
PNG bytes and HUD provenance returned by the replay API. Its receipt is
`focus-matrix-sol-hybrid-combat-dashboard-http-20261106T214718Z.json`, SHA-256
`deb371479cb7d1bc55cc8c645b38a1c05d6ab8464f2bcb6a3a0c499e1aca3e83`.
The final HTTP review matched all twelve rows, the third hybrid trial's success
and replay images, and the second trial's separate native crew-loss outcome.
`focus-matrix-twelve-cell-dashboard-http-20261106T220144Z.json` has SHA-256
`09728a5ed6042d33f5c02d9beba902067501ffe710e39d910faad4f2dc022866`.
Rendered-page verification remains pending while browser control is disabled.

Next are the six Sol hybrid fire/recovery and repair/departure cells, followed
by the Sol sector pilot and both full games, then Luna's eighteen challenge
cells and both full games. Twenty-four matrix cells and all five full-game
cohort attempts remain unstarted at this checkpoint. Continue one cell per
invocation with independent outcome/input review and live cleanup checks.

## Sol image challenge block complete (2026-11-06, 21:31 UTC)

All nine Sol image-only cells in `matrix-focus-5155dab-20261106` are complete
and eligible. Each challenge produced two task successes and one idle-budget
failure. There are no technical exclusions or recorded CLI reconnects.
The canonical starting gameplay state matches across the three repetitions
of each challenge. This finite fixture evidence does not establish general
game determinism.

| Challenge | Task successes | Decisions by repeat | Unsuccessful outcome |
| --- | ---: | --- | --- |
| Combat | 2/3 | 13, 9, 21 | Scout escaped without a reward; idle limit followed |
| Fire and crew recovery | 2/3 | 5, 11, 3 | Fire extinguished, but one crew member remained at 76.48% health |
| Repair, charge and departure | 2/3 | 12, 4, 4 | Reached another beacon with one engine bar still damaged |

The fire failure ended after eight empty zero-frame decisions with no world
updates or change in observed gameplay state. The repair failure reached full
charge and spent one fuel on a confirmed arrival, but did not fully repair the
engines before departure.
The two successful repair repeats established full repair, power and charge
at the origin before their confirmed arrivals. The two missed objectives
are recorded as gameplay failures. All nine retained the ship and
three living crew; the combat hull and score details appear in the earlier
checkpoint below. The fire and repair runs finished at full hull.

Across 82 tool-free, audited Codex turns, reported usage totals are 1,548,076
input tokens (398,080 cached, a subset of input) and 18,439 output tokens
(6,892 reasoning, a subset of output). Recorded CLI latency totals 855.210
seconds. Each delivered decision has one harness attempt and exact image and
dispatch bindings. `gpt-6.1-sol` was requested; Codex did not report a resolved
backend model identity. Hybrid and Luna results are still absent, so there
are no complete matched comparison groups or model/observation rankings.

Independent reviews rederived the saved outcomes, child admission, original
backups and exact restoration, and reproduced the nine-cell comparison.
A separate live boundary audit at 21:31:01 UTC verified the seven original
saves, prior Lua, six runtime files and all 84 executable source pins. FTL
was absent at both process checks and no pending-launch marker was present.
These are timestamped checks, not a claim about later runtime state.

Local receipts under `dist/resume-20261106/`:

| Receipt | SHA-256 |
| --- | --- |
| `matrix-fire-recovery-repeats-independent-review-20261106.json` | `ff1f5d9aa73227dab64fa93a86bd2a9d9fa279156ff2ed3b8f32a45ba9e5aa50` |
| `matrix-repair-charge-escape-repeats-independent-review-verified-20261106.json` | `94fa06b0ef46c55f4acba0e21d486d5f48df780fa334869749a02bdba87ef902` |
| `matrix-live-cleanup-20261106T213101578037Z.json` | `58cc390c8969b5e960f10908862c6b4381862a48c8e97ac8db62728bf2044e98` |

The final repair review retains and supersedes its first derived audit attempt:
comparing a repair-only subset introduced extra pair annotations. Rebuilding
the comparison from all nine saved members matched exactly. No trial artifact
or outcome was changed.

The QA viewer's actual HTTP checks covered running-to-terminal transitions
for the first fire and repair trials, including their distinct task outcomes,
eligibility, restoration and byte-matched before/after replay PNGs. Receipts:
`focus-matrix-sol-image-fire-dashboard-http-20261106T211902Z.json`
(`7ed30d5dd75aacf93bf2d2c6e62dffd933dd2f88e8538ffe896b41088fd7c174`)
and `focus-matrix-sol-image-repair-dashboard-http-20261106T212616Z.json`
(`2d3e2e5e246e18b62dd708cc048ee7c7af1889c71bcce2819d73a18e395e04a0`).
Rendered-page verification remains pending because local browser control is
disabled and the operator is away.

Next: the nine Sol hybrid cells, then the Sol sector pilot and both Sol full
games, followed by Luna's 18 challenge cells and both Luna full games. All 27
remaining matrix cells and all five full-game cohort attempts are unstarted
at this checkpoint. Continue one matrix cell per invocation, with terminal
outcome, eligibility and live cleanup reviewed before the next. Keep every
attempt and stop on technical failure or ambiguous cleanup.

## New Sol image combat results (2026-11-06, 21:08 UTC)

The first three cells of `matrix-focus-5155dab-20261106` completed through the
authenticated Codex CLI with `gpt-6.1-sol` requested. All three are eligible:
two task successes and one gameplay budget failure, with zero technical
exclusions. Initial gameplay states matched. These are three repetitions of
one model/mode/challenge condition, not a matched Sol/Luna or image/hybrid
comparison.

| Repeat | Outcome | Decisions | Final hull | Crew alive | Native score | Median call latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Enemy destroyed, 18 scrap collected | 13 | 24 | 3 | 58 | 13.093 s |
| 2 | Enemy destroyed, 18 scrap collected | 9 | 30 | 3 | 58 | 9.117 s |
| 3 | Scout escaped; idle decision budget exhausted | 21 | 27 | 3 | 40 | 9.214 s |

The third run's archived screenshot explicitly records the scout jumping away.
Its raw native destroyed flag and destruction counter still changed, but it
received no reward. The declared evaluator correctly withheld task success.
This reproduces the documented escape-counter caveat; those raw fields and the
native score do not independently prove a kill. All attempted outcomes remain.

Independent audit verified 43 tool-free decisions with one harness attempt each,
exact actor PNG/dispatch joins, saved child admission and cleanup. Completed
turn usage totals were 814,188 input tokens (131,328 cached, a subset of input)
and 11,264 output tokens (4,492 reasoning, a subset of output). No reconnect
was recorded. Codex reported the requested model but not a resolved backend
model identity. All seven original saves and the prior Lua were restored.
A separate live audit at 21:09:35 UTC verified all six runtime files, the
profile and 84 source pins, with no FTL process or pending launch marker.

Local evidence under `dist/resume-20261106/`:

- `matrix-combat-repeats-independent-review-20261106.json`, SHA-256
  `8bc434bfd47f129fbed6a1ab43be19d9df5cc5936ed83ce4e68b51ae5b4dbe9d`.
- `matrix-combat-live-cleanup-20261106T210935Z.json`, SHA-256
  `a02e83971b87927bf3da986587300c2994c0e20e051e060e04a0f1b54dd1e135`.

A separate detached viewer checkout at `6665357`, `ftl_bench-qa-20261106`,
serves the existing absolute runs directory read-only on `127.0.0.1:8766`.
Its 25 frontend tests and build passed. Actual HTTP checks matched the served
HTML/JS/CSS to built bytes and joined the first completed row and replay PNGs
to saved evidence. The older frozen viewer checkout remains unchanged; port
8765 was offline. Browser rendering remains unverified because local browser
control was disabled in Work settings. The HTTP receipt is
`focus-matrix-sol-image-dashboard-http-20261106T210132Z.json`, SHA-256
`17e2e1914376ba6fba63f0ae3facbadaff3c6350f5e54cd0eacfaa68a1be89e7`.

At that snapshot, thirty-three matrix cells and all five new full-game cohort
attempts were unstarted. The next steps were Sol image fire/crew recovery,
then repair/escape, then Sol
hybrid. Run one matrix cell per invocation and audit its terminal outcome,
eligibility and cleanup before the next: the bare matrix controller only
automatically stops for restoration failure. Preserve any technical failure
and resolve its cause before continuing. After all Sol matrix cells, run the
sector pilot and both Sol full games, then Luna's matrix cells and full games.
The pilot and budget stops do not count toward the four required native endings.

## Typed decision backends (2026-11-06)

The structured runner exposes `openai-decisions` alongside its Jev and
Responses backends. Standalone visual runs can select `jev` or
`openai-decisions` in addition to the default Codex CLI. The
`ftlbench visual-decide` command accepts one archived PNG and saves a
replayable decision without a game launch. Mocked responses exercise the
request and audit paths. Live provider validation remains pending, and no
FTL game was launched for this integration. Typed visual runs are diagnostic
and require their own comparison protocol. The frozen Codex cohorts use a
separate actor contract. See [typed decision backends](typed-decision-backends.md).

Final offline validation passed 2,808 checkout tests (20 skips), 25 headless
contract tests and 25 dashboard tests, plus dashboard and documentation builds.
The installed wheel passed isolated CLI, bundled-source and dashboard checks.
The unpacked source release passed 2,755 tests (73 skips); its additional skips
cover checkout-bound native admission proofs. Windows symlink privileges and
the missing host C++ compiler account for the other skipped checks. These
results establish offline integration and packaging, not provider compatibility
or gameplay acceptance.

The tested local wheel SHA-256 is
`a96f654f23b637651e677c79cc5d648341ce4256e00c09f6e53441a2870337a8`;
the tested source release is
`c29f0d0b4c1d7cb84b3b4aaa7f90de9f10742b2b37d66e76385d3b91df46f5e2`.
Both are under `harness/dist/`; generated distributions remain outside Git.

## Native focus guard repair (2026-11-06)

A protected foreground/focus-switch pair reproduced a native accounting defect:
both runs reported 600 updates, but the focus-switch run executed only 16
gameplay updates and 584 paused updates without recording interference.
Refocusing during a frozen hold also advanced the native timer by one frame.
Both runs restored the exact original saves, deployed Lua and runtime files.
They made no model calls. The October fire mismatch remains unexplained.

The repair observes native focus transitions, freezes an
interrupted owned advance, gates the independent unpaused timer, and makes
deterministic setup fail immediately on sticky interference. All 2,810 harness
tests pass with 22 explicit skips, including all 108 deterministic setup Lua
checks. Extracted native hook regressions ran separately under WSL and passed;
installed-executable binding checks and exact native source reconstruction also
passed. A fresh DLL was built and installed with the previous DLL/provenance
retained for rollback. The packaged data payload is unchanged. Protected
startup passed all eight checks, and all nine timing probes matched exactly
across three wall delays for combat, fire recovery and repair/escape. All
original saves and the prior deployed Lua were restored after each run. See
[native focus and simulation clock](native-focus-clock.md) for the mechanism,
evidence and validation boundary.

The post-capture focus probe stopped after 27 updates and remained frozen,
but pointer movement prevented isolating its first guard trigger. A separate
pre-capture probe made no visual requests or captures: focus loss stopped its
600-frame structured interval after 22 updates and immediately failed setup.
Refocusing produced 879 unpaused native trace rows with no world-counter or
timer growth. The foreground controls consumed exactly 600 updates. These
diagnostics retain their intentional interrupted/failed trial classifications.
They establish these observed paths, not general full-game determinism or the
cause of the October mismatch.

The current DLL SHA-256 is
`16eba4465270311bc480f9a91c4c3adc36c8ff33d1e6dc79c11ef950173023ec`;
provenance is `c0b40e0d32cdedf8b2f8fa085b883957e25f4f3f160a25bc83af61afb719b539`.
The original successful build is retained under
`dist/native-build-evidence/build-cached-20261106T201844280131920Z/`.
Earlier pull, dependency-download and Ninja-regeneration failures remain
separate; the successful fresh build does not explain the transient Ninja failure.

The new collection is
`harness/runs/validation/visual-v1/focus-admission-5155dab-20261106/`.
Its independent reviewer reran the positive verifier and executed all eight
meaningful rejection probes. The resulting local controller admission binds
84 executable sources and 577 evidence files while retaining
`production_accepted: false`. The admission spec SHA-256 is
`ce04665a3efa7a5766ae643e614a3fb77605439b027901c41a6732f56fe7528d`;
the review SHA-256 is
`b1d83835d710d2168cdc1743dc261da185fe4d032c000148b60fb12a64d56d18`.

New cohorts are frozen under `harness/runs/visual/`:

- `matrix-focus-5155dab-20261106`: 36 Sol/Luna image/hybrid challenge cells,
  three repetitions, 60 decisions / 1,800 seconds / eight idle decisions.
- `fullgame-focus-5155dab-20261106`: the Sol/image sector pilot and four
  native-ending conditions, retaining the matched 1,500 decisions /
  86,400 seconds / eight idle decisions budgets.

All model cells were unstarted at the freeze checkpoint; the later combat
results above update that state. Continue Sol first through the frozen
controllers, preserve failures, then run Luna.
Typed Decisions/Jev live provider checks still await an explicitly selected
credential file and remain separate from these Codex cohorts.
The independent archive review is
`dist/resume-20261106/focus-cohorts-independent-freeze-review-20261106.json`,
SHA-256 `35dfd3bfb39b78f39ef1f0072fc549ee565b48cc23dfbdde418242c029a2c9df`.

The joint independent pre-fix review is
`dist/resume-20261106/focus-clock-v2-independent-comparison-20261106T195520Z.json`,
SHA-256 `47e73362723b5eb658b9460c82db816d9af3fde3eff315485464ff0ce11aca9a`.
Its current cleanup/source snapshot was recorded at 19:55:20 UTC; it is not a
claim about a subsequently modified working tree or installed runtime.

## Attempt-three installation and timing (2026-10-14)

After the isolated rehearsal below, the attempt-three DLL, provenance and
patched data were installed in the real game with verified rollback bytes.
The local installation evidence is under
`dist/live-installation-attempt3-20261014T132339Z-94ecea82/`. A saved independent
review verified eight protected startup checks, including the untouched
opening image and restored saves.

The aggregate timing comparison rejected fire repeatability. Repetition two
first differed in room oxygen at `fixed-advance-8` despite matching requested
and actual frames and update counter deltas. The saved differential bounds
the first sampled change to that interval. Independent cleanup verified the
original saves and prior bridge. This collection stopped before admission. The
[November 6 focus collection](#native-focus-guard-repair-2026-11-06) later passed
all nine timing probes, independent review and scoped controller admission.

| Local receipt under `dist/resume-20261014/` | SHA-256 |
| --- | --- |
| `attempt3-startup-saved-independent-review.json` | `b04daa86c5ef59fea653d45582fe0beebd2ff39431f4701edcea42e7042cca0b` |
| `attempt3-failed-repeatability-current-cleanup-review.json` | `491dde0158cf0729b4b033f7171aceb46b5a223e5ccd8b584571afdfb85c6c72` |
| `attempt3-fire-timing-differential-20261014T133653Z.json` | `8350cc8831cc6bbf24470b5d3afd1e6091429538e6166e2da00dd86b63fac11b` |

## Isolated installation rehearsal (2026-10-14)

The new attempt-three native build has passed a file-only installation rehearsal.
The actual setup wrapper ran `locate install patch verify`, including Windows
FLIPS downgrade, loader installation, verified DLL/provenance installation and
Linux FTLMan v0.7.3 data patching, with exit 0 at 12:54:12 UTC. The isolated game
layout was reconstructed from the retained original 1.6.14 executable and vanilla
data; this is not a fresh Steam download or live acceptance. No model or game
was launched and the dummy profile remained empty. The real six runtime files,
seven saves and prior Lua remained byte-identical.

The successful rehearsal is retained under
`dist/installation-rehearsal-20261014T125317Z-8608b467/`. Its `operator-source.json`
pins the exact source snapshot over base commit `7960321`; native Git objects
were reused locally solely to authenticate the complete release inventory.
`installed-game/` retains the installed result, while `game/` was restored to
its exact seven-file baseline. `restoration.json` records this explicit operator
restoration, not automatic rollback of the entire setup. Loader backups and
receipts are copied under `loader-evidence/`; all original receipts are preserved.
Independent review at 12:59:37 UTC rederived the file, payload and restoration
checks. `independent-installation-review.json` has SHA-256
`1b8179b328ddc54f1a0a4913a387b0662474cd5a9f2311d430f9672fc845c236`.

The installed executable matches the known 1.6.9 target SHA-256
`32f1459c22d5f268d323c5cc6ede0a8a704bc13b3a20d0c08b6da097a29c2daf`.
DLL/provenance match attempt three, and the patched data SHA-256 is
`b83610ab6440f8a2adc234c58a327d8e4f5daacaec770e68d7b43d1340432d13`.
The patched archive was extracted: 305 direct mod payloads matched exact bytes,
one XML file matched after canonicalization, the Hyperspace version remained,
and all three bridge scripts were registered in order. FTLMan reported a locale
warning and an ignored Korean-text append with no base file. This validates
these file contents, not every append's gameplay behavior. The initial local
verifier expected byte equality for an XML file whose declaration FTLMan removes;
its original driver is retained alongside the corrected XML comparison.

The first rehearsal at `dist/installation-rehearsal-20261014T123105Z-580d6f7c/`
stopped before installation: the operator's prepared release copy omitted
`patch/patch.bps`, and the exact inventory gate rejected it. Its source, logs and
unchanged baseline remain separate. The second rehearsal used all three native
BPS files. No started experiment cell was retried or changed.

Confirmed setup defects fixed in this change include unchecked copy/backup
bytes, incomplete rollback after one restore fails, failed process queries
treated as absence, missing Python reported as PowerShell success, and explicit
game paths bypassing save-path resolution. The loader now requires expected
input hashes derived from the declared native Git base, including an exact BPS
inventory. Both native installation and data patching reject pending launches.
File-only mode requires explicit paths, disables elevation and permits only the
four rehearsal stages. Stage backups are separate; a later patch failure does
not undo an earlier successful installation, and process-crash atomicity is not
claimed. Independent review found no remaining blockers in this scope.

The local harness run passed **2,686 tests with 19 explicit skips**; the newly
added Git-input pinning suite separately passed all 15 checks. The unpacked source
release passed **2,648 tests with 72 explicit skips**, including the new helper
tests. Installed-wheel CLI/dashboard checks and the documentation build passed.
These changes include `installation.py` and `session.py`, so they invalidate
the executable pins used by the earlier admission. Fresh startup/timing
collection, independent admission and new cohorts are required before further
model calls. The external-input investigation, new-runtime live acceptance,
matched model comparison and native-ending full games remain unfinished.

## Resumed validation and build attempt (2026-10-14)

The operator confirmed the pending launch was cancelled, Steam signed in and
FTL closed. Current inventory matched seven original saves, the prior bridge
and six runtime files, with no pending guard. Fresh collection
`main-admission-d430d0e-20261014T111200Z` passed eight startup checks and all nine
timing probes, including exact native-step equality across the declared delays
and protected restoration. Independent review executed all eight negative probes;
78 source and 565 consumed evidence identities passed. The original 31 native
build/source inputs were copied with unchanged hashes and timestamps, explicitly
disclosed as reuse. Local controller admission is true; `production_accepted`
remains false. No new native build is claimed by this admission.

New full-game cohort `fullgame-main-d430d0e-20261014` freezes seed 1, medium
reasoning and matched 1,500 / 86,400 / 8 budgets. Embedded protocol SHA-256:
`fe8ae4d78bdf079352d4dd9eb5579899635696aa43d085f7c233d5bea2d94065`.
The Sol/image sector pilot ran from 11:24:35 to 11:57:50 UTC and stopped on
external input: 85 decisions were delivered, while the 86th completed model
response was rejected before dispatch. The guard changed from generation 0 to
13; no final action packet or simulation advance was sent. Evidence integrity
passed with 86 completed calls and 86 PNGs, but the attempt remains interrupted,
not a native ending. All four full-game conditions remain planned, with Sol
before Luna. This cohort cannot continue past its technical pilot outcome. The old
300-decision hybrid attempt and all historical results remain unchanged.

Independent cleanup at 12:01:20 UTC matched all seven original saves, prior Lua,
six runtime files and 78 executable sources, with no FTL process or pending
launch marker. The last delivered state had hull 16/30, oxygen 94%, three living
crew, sector index 0 and native score 142; the game had not ended. Recorded usage
is 1,627,197 input tokens (446,592 cached), 25,189 output tokens (9,101 reasoning),
1,750.667 seconds total model latency and zero reconnects. Review receipt
`dist/resume-20261014/d430d0e-sol-image-pilot-final-review.json` has SHA-256
`540cba1fd766dfdc47b4c9c92c902de235f595b96656259bc96e77e98600f53d`.

The operator reports using the computer but not FTL. The native guard counts
changed mouse positions and other delivered input events without a foreground
check; saved evidence does not record event types or foreground identity.
Background movement is a hypothesis, not an established cause. A separate
no-model passive diagnostic ran from 12:14:56 to 12:15:56 UTC. All 299 samples
retained generation 0, the same gameplay signature, action sequence 4 and zero
world updates. FTL was the foreground process while the pointer was outside
its window in every sample. This is a quiet baseline, not a test of active
other-app use; PID snapshots do not attribute individual events or establish
continuous focus. The bridge publishes changed generations even while idle,
so an unchanged observation tick alone is not evidence of a stalled monitor.
The protected receipt records exact restoration, with no model calls or
sampling-phase inputs. Artifacts are under
`dist/resume-20261014/passive-input-20261014T121444Z-d3775b21/`.

The rendered dashboard shows the interrupted pilot, verified save restoration,
the final archived screenshot and four planned inputs explicitly marked unsent.
The remaining diagnostic is controlled movement/typing in another app and
focus transitions. Do not merely stop counting events that still reach FTL:
the current guard forwards them, and the native chain has scroll callbacks
before downstream dispatch plus a separate physical-key polling path. Any
input-isolation change needs native cursor/UI/world invariance and synthetic
control checks, fresh admission and new cohorts. No guard behavior or frozen
sources changed. Preserve the interrupted run and do not treat its technical
exclusion as a model loss or silently retry it.

Docker startup reproduced its inaccessible inference-socket error. With Docker
closed, the two stale runtime sockets were preserved by renaming their parent
`run` directory; a fresh directory allowed Docker 28.3.2 to respond. Storage was
not reset. The host WSL configuration also contained `processors=32[wsl2]`,
exactly reproduced by the old bootstrap's append to a file lacking a final
newline. A byte-preserving backup precedes the narrow host repair. The source
fix now inserts into a unique section atomically, preserves explicit settings,
and refuses malformed/linked targets. No WSL shutdown was performed.

A fresh detached benchmark/native source build actually ran from 11:15:19 to
11:19:29 UTC under the pinned image, 3 GiB memory and one CPU. The image pulled
and dependencies built, but five compiler commands were killed by the container
memory limit; Docker OOM events and retained kernel lines identify that exact
container. Exit was 1, with no new staged DLL or installation. The entire failed
attempt remains at
`/home/ogabrielluiz/projects/ftl_bench-clean-builds/20261014T111013Z-prepare-4eec1485`.
Optional `FTLB_BUILD_JOBS` now caps direct Ninja jobs and vcpkg concurrency;
numeric validation and a real nested-Bash forwarding probe passed. Memory caps
alone do not limit parallel compiler jobs or the whole WSL VM.
The combined focused setup suite passed 86 tests with one Windows symlink
permission skip. Independent review also checked the wrapper's provenance
quoting and the pinned upstream chain's bare `ninja -C` invocation. All 78
admitted executable sources remain byte-identical after these setup-only edits.

The second fresh source build, benchmark commit `7b8462e`, ran from 11:34:04 to
11:38:08 UTC with one compiler job, one CPU and 3 GiB. Actual container settings
confirmed those limits. All 136 native compilation/link steps finished, and
the wrapper archived original build evidence and staged a verified DLL/provenance
pair. Independent review matched all twelve native source files across the
preparation archive, current tree, provenance and authenticated reconstruction.
The DLL SHA-256 is
`86c3af96b0c4cf80cb9ebae85a54e9bc8a1ebecff7c4655b1fe50eaa2e91e898`;
provenance SHA-256 is
`8d9e7ce980550c8c9e388894ae32aa4b5461c33159f306c66636847e2dc74795`.
This establishes a native build, not byte-for-byte reproduction of the installed
historical DLL or acceptance of the new runtime. The pinned Docker image/layers
were reused, while native source/output trees were fresh.

The overall second wrapper attempt exited 1: its subsequent `datamod` stage
could not write into Docker's root-owned native build directory. Its retained
root is
`/home/ogabrielluiz/projects/ftl_bench-clean-builds/20261014T113329Z-attempt2-624f7856`.
`independent-build-review.json` there has SHA-256
`bb934c2d7ff43a4aa74c82103f82f914795f793583a1eacb2025be053ff25589`.
The prospective fix packages `Hyperspace.ftl` atomically into caller-owned
benchmark `dist/` and makes the patch stage consume that path. It preserves
native outputs and any prior packaged mod on failure. Focused setup-input tests
passed (42 passed, one Windows symlink skip); independent review passed 64 focused
tests and a partial-ZIP failure probe with spaces in the paths.

The third fresh build at `90eeec8` completed `repos build datamod` with exit 0,
from 11:43:23 to 11:47:34 UTC, using the same one-job / one-CPU / 3 GiB recipe.
Its retained root is
`/home/ogabrielluiz/projects/ftl_bench-clean-builds/20261014T114250Z-attempt3-04e4cc04`.
Independent review joined all twelve native source identities and successful
link evidence, checked all 324 Hyperspace ZIP payload files against `Mod Files/`,
and matched the bridge archive to a fresh deterministic repackage. Actual
container settings and retained CMake records identify Clang 12.0.0 at
`/usr/local/bin/clang++`; tool observations also record CMake 3.26.4 and Ninja
1.10.0. The independent receipt there is `independent-build-review.json`, SHA-256
`576638ec6f90253c0ac025ee23ba3f6c87bd22dd4aca1fcc97a56c4fd2dc4f65`.

| Attempt-three output | SHA-256 |
| --- | --- |
| Native DLL | `7921bea2d589ee39b4dc9fb0528e98a7c3218ce296d14d0cd6a30d67f3c32e06` |
| Native provenance | `0dde1b46381c2025258cae5a25f0bb58dd22ad5c036c2575e44def03eed44be2` |
| Hyperspace data package | `f4bd9ecd4efeecabc0a46c588326fb938579ee68dbd9690171791c02af14d6c1` |
| Bridge data package | `a5336111a32d7392a1b983316330bdc8bb19a7e5aa6c9e37a71e583fd7155b8a` |

The source build and data packaging are now exercised end to end. The pinned
image and its toolchain dependencies were reused. DLL bytes differ from attempt
two, so byte-identical reproduction is not established. Installation and timing
validation took place separately as recorded above. The preserved pilot and
frozen model cohorts use their original admitted runtime.

The packaged-release CI check exposed a separate test-client defect with newer
Starlette dependencies: three synthetic ASGI clients returned an immediately
ready request forever, starving the file-response task while it waited for
disconnect. A retained isolated source release reproduced the hang. The
test-only fix sends one complete request and awaits disconnect after the final
response body, preserving all routing, image, outcome and read-only assertions.
The targeted reproducer passed, followed by 2,581 tests with 71 explicit skips
in the counterfactually patched Windows source release. This diagnoses the fix;
fresh CI on commit `8bc2b66` subsequently passed all five jobs. That exact commit
was fast-forwarded to remote `main`; main CI and documentation deployment also
passed. The two superseded stalled runs were cancelled and their logs retained.
Runtime source pins are unchanged. Local CI metadata receipt
`dist/ci-sdist-asgi-diagnosis-20261014/ci-results.json` has SHA-256
`c50ec7d8766746575bf21b63f2d1a4c9c9f83cd762cbdbd82ad7b8118a667b7c`.

Local receipts under `dist/resume-20261014/` include:

| Receipt | SHA-256 |
| --- | --- |
| `initial-inventory.json` | `b2cdb4a0c0643c1d658cc0e0f034634762f6b2f5510813d3c515cbf3da7058cf` |
| `d430d0e-static-native-input-reuse.json` | `510350479919a916f1632c091cf49c906a1624fa0d5ec0c076946712b10e33e5` |
| `d430d0e-independent-admission-cleanup-review.json` | `f18810963f0ffbd0d24fab8137a98ab8d5ba40a8073d88bee44b45aa18bca9aa` |
| `docker-recovery.json` | `25b3c0323773a85eaead0d92b7922ec8d43aa74a12af734b600b9b5f92f447da` |
| `wslconfig-repair.json` | `4ca93c47d4b524e0d8c2190715ac3a34de355e9ab9f2c9863fdf5e2b876c5ae7` |
| `native-build-attempt-01-oom.json` | `3d98fe69e0caa3f3bed7c291d39313c7a8bf23b72228f8d20446cb18625d0201` |
| `native-build-attempt-02-container.json` | `9df3ff23415bde3bbf222cd3dce9ce215cef14357a65173c4408e46816494888` |
| `native-build-attempt-02-packaging-failure.json` | `df16d5d69c65d455a27d4d6f3df0b6a5c04b22eaefa658d2bf5666d0f066c3c8` |
| `native-build-attempt-03-container.json` | `f29ccce6c31d0f0a4cc02c19d981042a55f065e893848d3afe44f19353722001` |
| `native-build-attempt-03-completed.json` | `12d389db7d01b95b6df3d0a515634f884bfbdff7db59d0af3ea20f05b0c6abb7` |

Controller-spec SHA-256 is
`7248180d61a072b0dc0514580d565e13d90a960286413532f04879cfa057967e`;
independent-review SHA-256 is
`a028522e67ee9b3535199872e95200e921f986935f90fbb3645996373d834469`.
These local artifacts are not shipped in Git. Fresh full-game outcomes, the
remaining Luna challenges, clean installation and runtime acceptance remain WIP.

## Native-build preflight and resource limits

Historical snapshot from 2026-10-11; the resumed state is recorded above.

The Windows/WSL build wrapper now accepts optional `FTLB_BUILD_MEMORY` (a
positive integer with lowercase `m`/`g`) and `FTLB_BUILD_CPUS` (a positive
integer). Memory sets equal Docker memory and memory-plus-swap limits; CPU sets
a quota. Unset variables preserve the existing command. Invalid values fail
before build-stage patching, image pulls or archive creation; earlier selected
bootstrap stages may already have run. The actual build command, including caps,
is retained in provenance. These caps do not constrain the whole WSL VM or
Ninja's job count. All 54 focused staging/setup-input checks passed, including
shell syntax, unchanged defaults and rejection before build-stage mutations.

The isolated-build preparation acquired Ubuntu Noble's `zip` 3.0-13ubuntu0.2
package and verified both package and extracted executable hashes, without a
privileged installation. Its local receipt is
`/home/ogabrielluiz/projects/ftl_bench-clean-builds/20261011T165000Z/tools/zip-acquisition.json`
(SHA-256 `2b69da72547e36ed66c68906b19a0df59b0aa00b66fbcfc0a92f5ca5007b87f4`).
This is tool acquisition only, not a clean-build result.

Docker Desktop's backend crashed at 16:48:32 UTC while initializing its inference
service because its local `run/dockerInference` file could not be accessed.
Compilation never started; there is no new DLL, installation or runtime admission.
The bounded, redacted preflight note is
`dist/store-warp-diagnosis-20261011/docker-preflight-20261011T164832Z.json`
(SHA-256 `082bd56d256f546d0a7b5470afac60e62db0e3c2f2a781d455a00601278b1c24`).
The local receipts are generated artifacts and are not shipped in Git.
The 3 GiB / one-CPU example remains unvalidated for a complete build.
Docker recovery and sufficient available host memory are required before the
next attempt. No factory reset or Docker-storage deletion was performed.

Steam's pending-launch cancellation remains a separate prerequisite for game
diagnostics below. No game or model run was started during build preparation.
The existing `main` checkpoint `c74aed4` passed all five
[CI jobs](https://github.com/ogabrielluiz/ftl_bench/actions/runs/38156659096),
including package and documentation builds. Offline validation does not supply
the missing live acceptance or complete-game results.

## Prospective configurable full-game budgets

The controller now accepts freeze-only positive-integer `--max-decisions`,
`--max-wall-seconds` and `--max-idle-decisions`. Defaults remain 300 / 14,400 / 8;
one frozen budget applies to the pilot and all four model/mode conditions.
Runtime overrides and malformed or unrepresentable values are rejected.
The focused controller suite passes 169 tests, covering custom/default freezes,
all five child commands, validation before side effects and tamper rejection.

Main `bb6014b146c8105ab917c4b65308f2c36e8a2058` passed all five CI jobs
in run `38151646134`, but is not yet admitted for model measurements. Collection
`main-admission-bb6014b-20261011T153250Z` passed eight startup checks and four of
nine timing probes. Fire repeat 02 then retained `protected_launch_error` before
game launch, with zero model calls and all seven saves restored. Independent
cleanup at 16:15:38 UTC verified the originals, bridge, six runtime files and no
FTL; receipt `bb6014b-failed-timing-current-cleanup-review.json` SHA-256
`1a63b78270656a68b4183fb4b173bb7652b2cb059207dd2a75aa44f1c59d5462`.

Steam reported cloud-sync failure and `login=false` at 16:07:33 UTC (13:07:33
local). The operator was asked to refresh sign-in, cancel the pending FTL
launch and leave FTL closed; confirmation arrived on 2026-10-14 as recorded above. New code implements
a durable pending-launch guard and explicit recovery: 240 focused offline checks
pass after the final recovery fixes. The broader harness suite passed 2,583 tests
with 17 skips before those final fixes. All five
[CI jobs for implementation `552377c`](https://github.com/ogabrielluiz/ftl_bench/actions/runs/38156148686)
passed, including both Windows and Linux Python versions and the package checks.
Live validation and fresh admission remain pending.
An unresolved guarded timeout blocks restoration-success and new protected runs.
The harness still cannot cancel Steam's queued request, and the fix does not
retrofit this historical bb failure, which has no guard. Do not run recovery for
that attempt without a marker created by the new code. Verified historical save
restoration and no process do not prove cancellation; further game runs stayed
stopped until that confirmation. See [recovery instructions](visual-iteration.md#pending-launch-recovery).
Bounded, redacted Steam
log excerpts are retained at
`dist/store-warp-diagnosis-20261011/steam-launch-failure-20261011T160733Z/`;
receipt SHA-256
`cac012d57dd2bb6b0122530d0f4b3326ff6b6e86c6b32183fe1ae65062b738de`.
This partial collection has no controller admission or new cohort. The separate
2026-10-14 collection above supplies fresh startup/timing evidence and review for
the new 1,500 / 86,400 / 8 cohort. That budget does not guarantee native endings.
Preserve the failed collection and all old
attempts without retries or pooling; all new Sol conditions precede Luna. The
original d1 challenge checkout remains pinned for its 18 unstarted Luna cells.

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
| `fullgame-main-d1c18b8-20261011` | `7bcba8d7391bb42db40012888c6153425e2afb9ffe12700560e03b84143df9ec` | `9129cfc04d9173b77acfced1a35fcab5053384767b6ddb4ce04f6a7758e708b6` | Pilot defeat excluded; Sol/image verified defeat; Sol/hybrid budget; two Luna planned |

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

### Closed Sol full-game checkpoint (2026-10-11 16:02:58 UTC)

Both main Sol attempts are finished and independently audited: image has native
crew-loss defeat (78 calls / 79 PNGs); hybrid has `decision_budget` (300 / 301),
with two living human crew, sector index 2, hull 21 and oxygen about 3%. Hybrid
has no native ending. The pilot remains separate and excluded; completion is
still **1/4 native endings**, with two Luna full games and 18 Luna challenges
untouched and planned. Main Sol totals are 378 calls / 380 PNGs, 6,418.143 seconds,
input 7,111,345 (cached subset 4,888,832; cache-write 0), output 88,032 (reasoning
subset 24,676), with all calls reporting usage and zero reconnects. No model
ranking or general determinism follows from these two attempts.

Exclusive saved checkpoint `d1c18b8-sol-fullgames-checkpoint-20261011T160258Z/`
binds exact comparison/ledger/protocol bytes, the pilot, both final reviews and
the image native-fields addendum. Summary SHA-256:
`02c65eb85d7a935c5f598cc5e54f844147f973d0a1cacf5507402aa1ad422258`.
Hybrid final review SHA-256:
`782342f49c24d2a1df98408e02b33c0d94400a462ceb00dc0d0337cb47cbf61f`;
independent cleanup SHA-256:
`0a32963671e0c43802ba91442c3dd1233f785ad9f950a23784e14ece3240f2b8`.
Final UI also passed. These dated saved/cleanup findings are not a current
live-state claim. The earlier milestone below is preserved as historical.

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

1. Continue the admitted November 6 matrix and full-game cohorts using their
   frozen source and evidence archives. Audit each terminal outcome, child
   admission and save restoration before the next cell.
2. Finish the remaining Sol challenge cells, then run the Sol pilot and two
   full-game conditions, followed by Luna's challenges and two full-game conditions.
   Retain every attempted outcome; stop for technical failures or ambiguous cleanup.
   Keep pilots and budget outcomes distinct from the four required native endings.
3. Report matched conditions from the frozen 36-cell matrix with denominators,
   exclusions, outcome reasons, latency and available usage. Keep previous
   cohorts and every attempted outcome separate.
4. Make native acceptance/evidence setup reproducible from a fresh checkout,
   validate the merged headless runtime, and revalidate any
   changed implementation and rebuild packages before release.
5. Once the operator selects a credential file, exercise each typed visual
   provider against an archived PNG and replay its saved stages. Use a separate
   admitted protocol for any live provider comparison.

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
