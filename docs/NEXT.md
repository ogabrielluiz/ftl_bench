# ftl_bench — next steps

Status as of this session: **M1–M6 working end-to-end and live-verified** (see README),
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

- **Reproducible game freeze (seed 11, beacon 3).** Hyperspace's own freeze watchdog
  fires: the game loop hangs when the agent jumps to a specific destination (connected
  beacon index 3 on seed 11, after a flee). Confirmed real with a 15s obs-staleness
  watchdog (`$CLAUDE_JOB_DIR/tmp/freeze_watchdog.sh`); NOT a watchdog false-positive
  (a 4s threshold *does* false-fire on normal multi-second warps — keep any watchdog
  >12s). The mid-warp re-trigger guard (apply_jump/leave_sector skip while `bJumping`)
  does NOT fix it, so the hang is tied to that destination's event/encounter, not the
  harness retrying. Next step: attach `lldb` to the frozen FTL pid and dump the hung
  main-thread stack to see whether it's in the game engine, a Hyperspace hook, or the
  bridge's per-tick Lua. The autonomous restart recovers (force-quit + clean relaunch),
  so a run can resume — but the episode is lost. Run the harness with an external
  freeze-watchdog until root-caused, so a hang can't leave a blocking Hyperspace dialog.

## Operating notes

- Keep FTL un-napped: `defaults write com.example.FTL NSAppSleepDisabled -bool YES`
  (done) — FTL then ticks in the background and the harness drives it unattended.
- Iterate Lua with `scripts/deploy_dev.sh` (hot-reload, no relaunch). Only C++ changes
  need a rebuild+relaunch (and the one mic click).
- `scripts/restart_ftl.sh [continue|new|none]` = autonomous restart to a run/the menu.
