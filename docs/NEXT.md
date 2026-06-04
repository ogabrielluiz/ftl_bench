# ftl_bench — next steps

Status as of this session: **M1–M6 working end-to-end and live-verified** (see README).
An agent can reset (continue/new, seeded), observe, and act (power, crew, jump,
event-choice, fire) through the harness, the MCP adapter, or the scripted baseline
agent; runs are recorded and scored.

## Needs a Hyperspace C++ rebuild (do when present — a rebuild re-triggers the mic dialog)

Rebuild = edit `Benchmark_Extend.{h,cpp}` / `hyperspace.i`, then
`ninja -C ~/Projects/FTL-Hyperspace/build-darwin-1.6.13-release`, copy the dylib
into `FTL.app/Contents/MacOS/`, `codesign -f -s - --deep`, relaunch (Allow mic once).

1. **Return-to-menu binding** (highest value). Lets the harness `reset()` to a fresh
   seeded run *from in-game* without a full FTL restart — needed for clean episodes.
   Add `hs_benchmark_return_to_menu()` that triggers the in-game menu's "Main Menu"
   action (look at `CApp`/`CommandGui` menu / `App.gui` quit-to-menu path), then
   `start_game('new', seed=…)`. Today `scripts/restart_ftl.sh` reaches the menu via a
   process restart, which works but is heavier.
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
7. **Richer observation**: incoming projectiles / weapon ETA, per-system ion/hack,
   reactor breakdown, crew skills — all readable from Lua, just add to `observation.lua`
   / the dev script.
8. **Better baseline agent**: smarter event choices (avoid combat when weak), flee when
   low hull (charge engines + jump), buy at stores once #2 lands.

## Operating notes

- Keep FTL un-napped: `defaults write com.example.FTL NSAppSleepDisabled -bool YES`
  (done) — FTL then ticks in the background and the harness drives it unattended.
- Iterate Lua with `scripts/deploy_dev.sh` (hot-reload, no relaunch). Only C++ changes
  need a rebuild+relaunch (and the one mic click).
- `scripts/restart_ftl.sh [continue|new|none]` = autonomous restart to a run/the menu.
