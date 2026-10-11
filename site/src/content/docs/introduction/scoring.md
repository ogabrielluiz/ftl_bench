---
title: How scoring works
description: Native score, strict verified wins, confirmed movement and retained outcomes.
---

The runner reports FTL's native run score plus scenario progress and strict solve rate. The scorer reads recorded observations and terminal outcomes; it does not execute a game policy.

## Native score and goal progress

`ftl_score` is the latest authoritative current-run score observed during the attempt, tagged `ftl_score_source: native_live_v1`. Aggregate reports include its mean, median and seed standard error.

The pure native getter matches FTL 1.6.9: `(scrap collected + 20 × ships destroyed + 10 × beacons explored) × difficulty multiplier`, truncated to an integer. Multipliers are 1.0 easy, 1.25 normal and 1.5 hard. The only automatic benchmark setup currently supported is easy. Components are recorded in raw observations.

The saved `TopScore.currentScore` snapshot can retain a previous run until FTL saves; it is not accepted as live score evidence. Missing or legacy score sources remain unverified.

Mixed scenarios have weighted goals such as surviving confirmed jumps or reaching a sector with enough hull. Full-run progress has target 11: eight sectors plus three completed flagship phases. Native sector indices are zero-based, so index 7 gives eight sectors of progress.

The current native getter reports a verified final win. No completed intermediate phases are guessed from raw flagship stage counters; a verified win supplies all three completed phases.

## Strict solve

A full-run solve requires explicit `victory: true` (or a future verified completed-phases field). Game over alone also occurs on losses and cannot establish a win. Survival requires the player still alive at the end.

Player survival counts living player-owned crew, including own boarders; hostile intruders never count as surviving player crew. Observed zero health is excluded even if a native death flag lags. The v3 control contract also rejects hostile or uncontrollable movement before the engine call.

Travel is counted from changed observed map identity, not jump commands. Resets, rejected moves and repeated commands at the same beacon earn no travel credit. Minimum distinct-beacon requirements continue to gate applicable scenarios.

Concession, stall, error or interruption is unsolved. Partial progress and native score remain recorded; they do not turn a failed attempt into a solve.

## Lifecycle and retries

Each attempt ends with a terminal record containing status, reason and optional error. A real loss is a completed game outcome; a model/transport failure is an error. The dashboard and reports retain both.

`--retries N` allows up to N extra same-seed attempts and reports best-of-k results plus solve@k. Compare these only with equally labeled retry rows.

**Ruleset v7 requires `owned-player-crew-v1` and `native-economy-and-fuel-recovery-v1`. Pre-v7 rows are not comparable.** The v3 Sol concession at score 329 and v2 Jev score 59 remain diagnostic/historical evidence. Diagnostic runs preserve results but are excluded from model comparison metrics. Compare the same suite, tier, mode, prompt, native artifacts, all five contracts, action-selection contract and retry count.

Implementation: `harness/src/ftl_bench/scoring.py` and `aggregate.py`.
