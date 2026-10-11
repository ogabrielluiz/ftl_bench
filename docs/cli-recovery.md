# Audited Codex CLI recovery

Status at 2026-10-11 11:44 UTC (08:44 in São Paulo): the implemented recovery policy and saved-report
repair are freshly admitted at executable commit `d1c18b8` in
`matrix-main-d1c18b8-20261011` and `fullgame-main-d1c18b8-20261011`.
The first Sol/image combat trial reached the 60-decision budget without task
success; its evidence is eligible with no exclusions, and all 60 decisions/62
PNGs passed saved auditing. No reconnect occurred, so this trial does not prove
live recovery handling. One challenge cell is finished, 35 remain planned, and
all five pilot/full-game cells remain planned. Independent final saved-trace,
current-cleanup and rendered UI reviews passed at their dated boundaries.
See [exact admission, cohort identities and receipts](NEXT.md).

Fresh collection `main-admission-policy-audit-20261011T110830Z` passed eight startup
checks, nine timing equality probes, protected cleanup and eight executed negative
review cases, binding 78 sources and 565 evidence files. The 31 original native
inputs remain unchanged with reuse disclosed; `production_accepted` remains false.

The preserved `463c340` trial achieved its combat goal after 13 decisions, but its
original comparison falsely excluded it because challenge trajectory metadata
precedes actor construction. The repaired reporter uses the manifest policy and
checks every present declaration, without inventing a conflict for absent optional
metadata. Unknown, conflicting or undeclared modern policies still reject; strict
historical behavior remains. Original reports and failures were not regenerated,
retried or retroactively accepted. The fresh `d1c18b8` cohort now binds this repair.

## Observed failure

In `fullgame-main-2174cc9-20261011`, Sol/image call 47 exited zero after 29.258
seconds. Its retained stream contained `thread.started`, `turn.started`, a
reconnect `error` notification, one completed agent message and `turn.completed`.
The original parser rejected event index 2 before reaching the completion.
The final-answer file and screenshot checks were therefore never reached. No
call-47 input or simulated advance was delivered; the game was still alive.

The notification reported a server-closed WebSocket before completion; stderr
also retained a Windows connection-reset diagnostic and two internal sampling
retries. This does not establish whether the underlying cause was local routing
or a provider incident. It differs from the earlier matrix fire call's nonzero
exit and `turn.failed` workspace-routing failure. Both failed attempts remain
preserved and excluded under their original contracts.

The [official non-interactive CLI documentation](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable)
lists completion, failure and error events in JSONL output. The precise recovery
allowlist below is this benchmark's deliberately narrower policy, based on the
retained stream; the documentation does not certify arbitrary errors as safe.

## Prospective policy

`ftl-codex-cli-reconnect-v1` is recorded in actor identity and each request.
It accepts only full notifications matching `Reconnecting... N/5`, with N in
1..5, strictly increasing indices, at most five notices, and either the observed
server-closed WebSocket reason or the observed Windows error 10054 reason.
The exact event must contain only its type and message. A notice must occur
after one thread and turn start and before any agent-message activity.

Acceptance still requires CLI exit zero, exactly one completed agent message,
one completed turn, valid usage when supplied, no tools or unknown activity,
an unchanged attached PNG, an output file matching the audited final message,
and a valid bounded action schema. Unknown errors, failed or incomplete turns,
duplicate threads/turns, notices after completion, and notices after a partial
agent message fail closed. The harness never issues a replacement CLI call or
changes model, transport settings, prompt, actions or budgets to recover.

The explicit historical policy `ftl-codex-cli-strict-v1`, also selected when a
saved record has no policy, retains the original reject-all-errors behavior.
Saved auditing binds the request policy to the trajectory and manifest, checks
recovery notices against the event stream, and verifies the retained diagnostic
bytes. It never turns a recorded `model_error` into a delivered decision.

## Evidence and usage

Recovered requests retain the complete audited event list and its original
stream hash. `cli_recovery` additionally keeps bounded, credential-redacted
stdout and stderr, original/retained hashes, byte counts, redaction/truncation
metadata, notices and `completed_turn_only` usage scope. Rejected requests keep
their existing `cli_failure` evidence. The dashboard exposes both in expandable
request details; raw diagnostic completion usage never replaces frozen totals.
Auditing rehashes retained bytes. When redaction or truncation removed original
bytes, their original digest remains a producer-recorded claim; the audit does
not reconstruct or certify the removed content.

`observed_totals` retain reported counts and `completed_turn_totals` require
coverage of every harness call. When a call recovered internally,
`complete_totals` remain unavailable because aborted sampling usage was not
reported. Both trial and condition summaries carry recovery counts and this
limitation. Cached and reasoning tokens remain subsets, not added totals.

This change requires a new executable-source freeze and admission. Preserve the
old cohorts, inputs, failures and receipts; do not patch their ledgers, retry
started cells or combine results across contracts. Native ending, cleanup,
task success and fair-pair requirements remain unchanged.

## Validation at 2026-10-11 10:24 UTC

The actor, saved reporting, runner, full-game/controller and independent recovery
checks passed: 468 tests, with one explicitly opt-in native source reconstruction
test skipped because no local proof/repository was supplied to that invocation.
The 22 dashboard tests and TypeScript/Vite build passed. Independent review
reproduced and closed missing manifest-policy and redaction-metadata joins.

An offline counterfactual fed the original 1,097-byte call-47 stream to both
policies: the new parser accepted its completed response and the old parser
rejected it. This did not replay the game, recreate the original temporary final
file, or change its failure status. Synthetic process tests separately cover
the final-file, screenshot, schema, terminal and no-tool checks.

The actual rendered viewer exposes the retained reconnect/completion stream and
diagnostic token counts while leaving the failed call undelivered and full-game
completions at zero. Local evidence includes
`dist/cli-recovery-call47-counterfactual-review.json` in the isolated setup
checkout and `2174-main-fullgame-sol-image-expanded-diagnostics-ui-review.json`
under the evaluation checkout's `dist/store-warp-diagnosis-20261011/`.
Fresh source-bound collection `main-admission-cli-recovery-20261011T103548Z`
subsequently passed eight startup checks, nine timing equality probes, protected
cleanup and eight executed independent negative probes. Admission binds 78 sources
and 565 evidence files, reusing 31 unchanged original native inputs; it retains
`production_accepted: false`. All five [CI jobs at `463c340`](https://github.com/ogabrielluiz/ftl_bench/actions/runs/38132428078)
passed. No live model benchmark has yet used the new policy at the 10:47 UTC
snapshot. Admission does not establish completed games or the Sol/Luna comparison.
