# ftl_bench — next steps

**Benchmark v1 shipped (2026-06-04):** the env is now a goal-conditioned scenario
benchmark (ARC-AGI/WebShop/BALROG-inspired). `harness/src/ftl_bench/{scenario,scoring.
score_instance,aggregate}.py`, `scenarios/suite_v1.json` (T1–T5, public + held-out),
`adapter/run_benchmark.py` (runner → headline **GCS@1** + Solve Rate). The agent decides
in-game; only goal achievement is scored. Reliability: the jump/arrival freeze is fixed
(rebuild obs only on state change + guard volatile collection reads against the warp).

### Benchmark — remaining to make it canonical
1. **Micro-encounter scenarios (T6–T9)** — `win_this_combat`, `escape_a_crisis`,
   `event_risk_choice`, `resource_goal`. Highest signal-per-token. Needs a new Lua
   `scenario_setup` binding to pin a frozen mid-run state (player loadout + enemy +
   systems), plus hand-authored, human-validated snapshots. Pure Lua hot-reload.
2. **Flagship + store tiers (T10–T12)** — gated on the action-gap bindings below
   (flagship reachability, store buy/sell). The apex skill probes + the full-run ceiling.
3. **Baseline ladder + references** — run `random` and `scripted` for the floor (done by
   run_benchmark.py); add a **human reference** (≥2 clears/instance via MCP/code-mode) to
   anchor the efficiency axis and validate each instance is human-achievable & not
   random-achievable; add a **frontier-LLM** track (zero-shot + code-mode).
4. **Reproducibility hardening** — capture ftl/hyperspace build hashes in the manifest;
   an acceptance test that re-running an instance reproduces the same milestone outcome.
5. **Efficiency reference** — per-seed human/best jump counts for the T4 efficiency term.

Status of the env it runs on: **M1–M6 working end-to-end and live-verified** (see README),
**plus sector progression, richer observation, and a smarter baseline.**
An agent can reset (continue/new, seeded), observe, and act (power, crew, jump,
event-choice, fire, leave-sector) through the harness, the MCP adapter, or the scripted
baseline agent; runs are recorded and scored. The baseline navigates a full sector to
the exit beacon and **crosses into the next sector** (`leave_sector`), fleeing on
oxygen/weapon/crew danger and escalating event choices.

Done this session (was rebuild-gated): **`leave_sector` binding** (exit beacon → next
sector; refuses during combat to dodge a transition SIGBUS), **exit-beacon + position +
rebel-fleet + sector-choice observation**, **crash-flag-aware restart** (recovers from a
crashed/killed FTL), **launch via `Hyperspace.command` directly** (no `open` → vanilla
bridge-less hang; no `osascript activate` → duplicate instance).

## Needs a Hyperspace C++ rebuild (do when present — a rebuild re-triggers the mic dialog)

Rebuild = edit `Benchmark_Extend.{h,cpp}` / `hyperspace.i`, then
`ninja -C ~/Projects/FTL-Hyperspace/build-darwin-1.6.13-release`, copy the dylib
into `FTL.app/Contents/MacOS/`, `codesign -f -s - --deep`, relaunch (Allow mic once).

1. ~~**Return-to-menu binding**~~ ✅ DONE — `AgentSession.reset_episode(seed)` abandons
   the current run back to the main menu and launches a fresh seeded game, from
   in-game, no process restart. (`return_to_menu()` finds the "Main Menu" button by
   label; the bridge drives return→confirm→new-game in Lua.)
2. **Store transactions** (M3 deferred, high effort): bind `Store`/`StoreBox`/`Purchase`
   so the agent can buy/sell at stores. See deepdive §10 P2 #16.
3. **Beam weapon targeting** (two-point): a `fire_beam(slot, room_a, room_b)` variant.
4. **Activate special systems** as first-class actions (cloak/hacking/mind-control/
   teleporter) — most are already Lua-exposed; wire dispatchers + a small binding where
   not (e.g. hacking `TargetSystem`).

## No rebuild needed (pure Lua hot-reload / Python)

5. **Scenario library** (`scenarios/`): curated `{seed, sector, goal}` micro-encounters
   (a single combat, an escape, a store-allocation) + a runner that scores each.
6. **A real LLM agent** over the MCP adapter (vs the scripted baseline) — and a small
   eval harness that runs N seeded episodes and aggregates `score_trajectory`.
7. **Richer observation** (mostly ✅): incoming projectiles, weapon charge/ETA, per-system
   ion/hack, exit beacon + positions, rebel fleet, sector-choice flag are done. Remaining:
   reactor breakdown detail, crew skills.
8. **Better baseline agent** (partly ✅): exit navigation, flee on O2/weapon/crew danger,
   event-choice escalation, stalemate-flee, and sector crossing are done. Remaining:
   active **crew repair** (move crew to a destroyed O2/weapons room instead of fleeing),
   FTL-charge-aware combat fleeing, buy at stores once #2 lands.
9. **Combat-time sector flee**: `leave_sector` currently refuses with a live enemy (the
   transition SIGBUS guard). Root-cause the crash (likely a projectile/teardown race) so
   the agent can also flee a sector mid-combat.

## Known issues

- ~~**Reproducible game freeze (seed 11, beacon 3).**~~ ✅ FIXED. Root-caused by
  `sample`-ing the hung process: the game-loop thread was spinning in FTL's
  `CommandGui::OnLoop()` because the bridge forced `starMap.readyToTravel` while the FTL
  drive was still recharging (the agent jumping right after a flee) — an inconsistent
  warp state the engine loops on forever. Fix (Lua, no rebuild): the bridge gates every
  jump/sector-leave on `jump_ready` (player ship present, not `bJumping`, and
  `jump_timer.first >= jump_timer.second`); the obs exposes `jump_charged` so the agent
  waits out the recharge for free instead of spending no-op jump attempts. Verified: the
  deterministic seed-11 case clears beacon 3 with no freeze; a healthy seed-7 run jumps
  normally (fuel decrements, no stalls). Diagnostic tooling kept in
  `$CLAUDE_JOB_DIR/tmp/freeze_sampler.sh` (sample-then-kill on a >12s obs-staleness hang;
  a watchdog threshold <12s false-fires on normal multi-second warps).
- **Baseline flee-loop on a crippled ship.** A badly damaged ship (engines/O2 down) can
  flee repeatedly and its FTL drive recharges too slowly to jump (the agent then stops
  with "drive won't charge here"). Not a freeze — a policy gap: the baseline should keep
  engines powered (faster FTL charge) and repair/leave instead of flee-looping.

## Operating notes

- Keep FTL un-napped: `defaults write com.example.FTL NSAppSleepDisabled -bool YES`
  (done) — FTL then ticks in the background and the harness drives it unattended.
- Iterate Lua with `scripts/deploy_dev.sh` (hot-reload, no relaunch). Only C++ changes
  need a rebuild+relaunch (and the one mic click).
- `scripts/restart_ftl.sh [continue|new|none]` = autonomous restart to a run/the menu.
