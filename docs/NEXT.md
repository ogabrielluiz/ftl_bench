# ftl_bench — next steps

## CURRENT DIRECTION (2026-06-05) — play the game, no sub-goals
The benchmark was REFRAMED (user's call): the agent should just PLAY FTL toward its real goal —
beat the rebel flagship — using its own intelligence; we measure how far it gets (`progress`
milestone: 8 sectors + 3 flagship phases = win). NO artificial scenario types / sub-goals are
given to the agent. `scenarios/full_game.json` (seeds only, progress-scored); `build_system_prompt`
appends a constant "WIN THE GAME" objective, not `_goal_text(scenario)`. The T1–T5 typed suite
(`suite_v1.json`) + its scripted-70.2/random-5.2 numbers are now LEGACY (they scored sub-goals).

**Agent prompt = INTERFACE ONLY** (`prompts/ftl_agent_v3.md`): name the game + the controls + the
obs schema + the few quirks that differ from clicking the real game (commands are one-time SETS;
power≠fire; broken `damage`/`on_fire` module needs crew repair not power; `leave` to cross sectors;
the hybrid pause + `wait <N>`). ZERO strategy — the model already knows FTL from training; teaching
strategy backfired (v2's "no time pressure/patch up" made it dawdle). v1=as-measured 35.7, v2=+repair
coaching (bad), v3=lean interface (right design).

**Interface VALIDATED — it discriminates by capability.** Opus 4.8 played the full game (seed 1)
WELL through this interface (smart targeting/power/repair, no no-op loops, cleared sector 0 at 30/30,
one jump from sector 1) where zero-shot Sonnet DAWDLED at sector 0 (power/wait no-op loops, 3-4
jumps). Opus credited the session's interface fixes (called `shots` "the single most helpful field").
So the benchmark works; the ceiling is the AGENT, not interface friction.

**REMAINING FRONTIERS (not the interface):**
1. **Engine reliability** — Opus's winning run ended on a Rosetta jump/sector-transition FREEZE
   (`FROZEN_KILLED`, ship was 30/30 alive). This caps full-length runs + a real progress number.
   Root-cause the jump-time freeze (RepairDrone SIGBUS class / warp teardown) so games can run to 8
   sectors. THE key blocker now.
2. **Play-to-game baselines** — re-baseline `scripted`/`random` on `full_game.json` (progress-scored)
   so agent results have floors (code agents, no API credit needed). IN PROGRESS.
3. **Billing** — Anthropic API + headless `claude -p` are credit-exhausted (account-wide) after this
   session; harness-scored LLM runs need a top-up. In-session Agent-tool subagent (runs as Opus 4.8)
   is the working fallback for a strong agent but isn't auto-scored.

---

**Benchmark v1 shipped (2026-06-04):** the env is now a goal-conditioned scenario
benchmark (ARC-AGI/WebShop/BALROG-inspired). `harness/src/ftl_bench/{scenario,scoring.
score_instance,aggregate}.py`, `scenarios/suite_v1.json` (T1–T5, public + held-out),
`adapter/run_benchmark.py` (runner → headline **GCS@1** + Solve Rate). The agent decides
in-game; only goal achievement is scored. Reliability: the jump/arrival freeze is fixed
(rebuild obs only on state change + guard volatile collection reads against the warp).

**Combat now actually works (2026-06-04) — Burst Laser firing fixed.** Root cause: a
multi-shot weapon needs `ProjectileFactory::NumTargetsRequired()` aim points to fire, but
`fire_weapon` supplied only one — so the 3-shot Burst Laser II stayed fully charged +
`fire_when_ready` yet never released (the Artemis missile, 1 shot, worked). Fix (live, pure
Lua in `apply_fire_weapon`): top up `pf.targets` to `NumTargetsRequired()` copies of the
target-room center; the first fire copies them to `lastTargets` so autofire keeps firing all
3 bolts. C++ `hs_benchmark_fire_weapon` also corrected for the next rebuild. The obs now
exposes per-weapon `num_shots`/`targets_required`/`n_targets`. Two combat facts this exposed:
(1) FTL gates `World::OnLoop` on `bPaused || event_pause || menu_pause || bAutoPaused`, so an
unresolved (often **chained**) event/flee dialog freezes the *whole* combat sim — clear the
choice box (loop `choose_event` until `choice_box_open=false`) to resume; (2) a damaged enemy
pops a "trying to escape!/Continue…" dialog that re-pauses combat — the baseline `fight()` now
dismisses it to finish the kill. Verified: scripted agent lands real kills in the suite
(`enemy destroyed`, scrap reward) — shielded fights are winnable now that the burst fires.

**First real-LLM playtest (2026-06-05) — the agent-facing CLI was starving the agent.**
Dispatched a real frontier LLM (a subagent, no scripted policy) to play instance
T3-healthy1-s1 (seed 1) turn-by-turn through `play_cli.py` and write a benchmark report. It
**died at hull 0 in sector 0 (score ~0/4)** and its report was the missing signal: its three
biggest complaints — "can't navigate to the exit", "enemy weapons invisible", "weapon identity
unknown" — were **all data the raw obs already had but `compact()` discarded**. Verified field-
by-field against `ftl_agent_observation.json`: the raw obs carries `map.exit_pos`/`current_pos`
+ per-beacon `pos_x/pos_y`, `enemy_ship.weapons`/`systems`, and per-weapon `weapon_type`/
`is_beam` — none of which reached the agent. **Fix (pure Python, no rebuild, `play_cli.py
compact()`):** forward `current_pos`/`exit_pos` + per-beacon `pos` and a derived `dist_to_exit`
(the data; the agent still decides which beacon — no "best" flag); add player weapon `type`/
`is_beam`; forward `enemy.weapons` (count + charge + `about_to_fire`) and `enemy.systems`
(powered); split the ambiguous `reactor "3/8"` into numeric `reactor_free`/`reactor_total`
(a real agent misread which number was free); flag `game_status: DESTROYED` at hull<=0 (the
formal `game_over` flag only flips at the menu, leaving a hull-0 window that read as a live-
but-stuck state — verified the fix on the prior run's corpse); and a `power_result` that says
WHY a `power` command didn't apply (damaged/ion/no-free-reactor — a silent power no-op cost the
first agent its main weapon). **A/B VALIDATED:** identical prompt, fresh agent, enriched obs →
**Run #2 crossed to sector 1, hull 23/30, 3 crew, 4/4** (vs Run #1's ~0/4). The obs compaction
WAS the bottleneck. **Second-tier fixes (surfaced only once the agent got far enough), both
verified live:** (1) **`leave` silent no-op → reliable** — `benchmark_leave_sector` only SETS the
StarMap transition flags and `StarMap::OnLoop` commits them a later tick, so a fixed frame-advance
could re-pause mid-transition (Run #2 needed ~5 retries to cross). `session.leave_sector` now
PUMPS until the sector increments (re-issue is a safe no-op mid-warp); `play_cli` emits
`leave_result` (committed/refused/pending). Verified: a single `s.leave_sector()` committed sector
0→1 in 6.3s. (2) **weapon stats null until combat** — the dev-lua enrichment gated the PLAYER's
own `weapon_type`/`is_beam`/`num_shots` on an enemy being present; dropped that. Verified:
`type:MISSILES/LASER` shows with `enemy:None`. **Third-tier — the items I'd called "deferred"
are now DONE (2026-06-05), all pure-Lua-hot-reload + `compact()`, NO rebuild.** A 4-lane
research→adversarial-verify Workflow confirmed every `%rename`-bound symbol against the SWIG master
+ the compiled wrapper (the deferral premise was wrong — enemy-weapon enrichment mirrors the player
loop in the hot-reload `ftl_bench_dev.lua`, and `ShipManager::jump_timer` was bound all along, just
never read into the obs). The verifier caught a real bug (the draft's enemy-weapon loop would be
clobbered by the existing `obs.enemy_ship.weapons = ew` replacement — fixed by EXTENDING that loop +
adding its missing jump/destroy guard). All 4 live-verified in combat: (1) **weapon damage+type+
shield-piercing for BOTH ships** (`dmg`/`pierces`/`eff_pierce`/`fire`/`ion`; player Artemis dmg2
pierce5, enemy MISSILES dmg1 pierce5 vs LASER dmg1 pierce0 — the exact missile-vs-laser threat ID the
dead agent lacked); (2) **`jump_charge_pct`** (`ShipManager::jump_timer` pair; 0 idle, 0.044→climbing
in combat, + `jump_charge {current,max}`); (3) **evasion** both ships (`GetDodgeFactor()`; player 20,
enemy 15); (4) **`map.hazard`** (SpaceManager `bStorm`/`pulsarLevel`/`sunLevel`/`bNebula`/asteroids +
`pds`) + **reactor power-truth** (`PowerManager::GetMaxPower()` → `reactor_usable_total`/
`reactor_usable_free`/`reactor_power_penalty`, so a storm-capped reactor stops lying; no-hazard case
verified usable==raw, penalty 0). Only a non-`"none"` hazard value is unobserved (RNG-gated on hitting
a storm/nebula beacon); the flags are confirmed bound and the `"none"` path works.

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
2. ~~**Store transactions**~~ ✅ DONE — `hs_benchmark_store_read()` (serializes the active
   store's `vStoreBoxes`/`vItemBoxes`: name from `desc.title`, `desc.cost`, `count`),
   `hs_benchmark_store_buy(i)`/`hs_benchmark_store_sell(i)` (call the box's virtual
   `Purchase()`, which deducts scrap + adds the item). Obs exposes `store={buy:[...],sell:
   [...]}` at a store beacon; actions `store_buy`/`store_sell`/`upgrade_system` (the last
   spends scrap via `ModifyScrapCount` to raise a system's max power). CLI: `buy`/`sell`/
   `upgrade`. Verified: bought FTL Fuel, scrap 10→7. Active store = `world->baseLocationEvent->pStore`.
3. ~~**Beam weapon targeting** (two-point)~~ ✅ DONE — see #4.
4. ~~**Activate special systems** as first-class actions~~ ✅ ALL 8 WIRED (2026-06-05). Two
   research+adversarial-verify workflows (one per system) produced paste-ready impls with a full
   binding audit (every Hyperspace symbol confirmed `%rename`-bound) + a per-system Rosetta
   crash verdict re-derived from the teardown source. All 8 came back SHIP-WITH-FIXES; the fixes
   are folded in. **Lua-only (hot-reload):** `cloak` (10), `set_doors` (8), `mind_control` (14),
   `deploy_drone`/`recall_drones` (4). **Needed the C++ rebuild (3 new bindings, done + loaded +
   verified callable):** `battery` (12, +`BatterySystem::timer` rename, then Lua), `fire_beam`
   (`hs_benchmark_fire_beam`, two distinct sweep points), `hack_system` (`hs_benchmark_hack_system`),
   `teleport_crew` (`hs_benchmark_teleport_crew`, send/recall). Obs exposes each system's state
   (`battery`/`hacking`/`drones`/`teleporter`/`cloak`/`mind_control` blocks + per-weapon
   `is_beam`/`weapon_type`/`beam_length`). Harness builders + `__init__` exports + `play_cli`
   cmds (`battery`/`beam`/`hack`/`drone`/`dronerecall`/`board`/`recall`).
   **Rosetta crash-safety (verified from source):** HackingDrone is a `SpaceDrone` (not a
   CrewDrone) → outside the SIGBUS class; combat/defense drones likewise. `deploy_drone`
   DEFAULT-REFUSES crew-drone types (2 repair,3 battle,4 boarder,5 ship-repair) unless
   `allow_crew_drone` (slot-order-safe so it can't deploy a refused slot first). `teleport_crew`
   only ever sends `IsDrone()==false` organic crew (organic death frees via uncorrupted
   `~CrewAnimation`; only RepairDrone's RepairAnimation vtable SIGBUSes). hack dedups the
   space.drones push by pointer-scan (not the unreliable `drone.deployed` flag).
   **Verified at runtime (new build):** all 3 bindings register as callable Lua functions; all 7
   new actions dispatch clean (no crash, FTL alive) when the system is absent (no-op); obs blocks
   run clean. **Not yet runtime-demonstrated:** the in-combat EFFECT of a *bought* special system
   (a beam sweep / hack landing / boarders teleporting / cloak engaging) — gated on reaching a
   store that stocks a special SYSTEM (RNG; a 14-jump run hit a store with weapons only). The
   buy→power→activate loop + obs-confirms is the recommended next validation.

## No rebuild needed (pure Lua hot-reload / Python)

5. **Scenario library** (`scenarios/`): curated `{seed, sector, goal}` micro-encounters
   (a single combat, an escape, a store-allocation) + a runner that scores each.
6. ~~**A real LLM agent** over the adapter~~ ✅ DONE (2026-06-05) — **`--agent llm` track in
   `run_benchmark.py`** (`adapter/llm_agent.py`). A real frontier model plays the whole suite
   over the SAME intent-level surface the baselines use: per turn it gets the decision-complete
   `compact()` obs + the scenario goal + a short action history and replies with one command
   (`ACTION: <cmd>`), dispatched through a SHARED `apply_command()` refactored out of
   `play_cli.py` so the LLM and CLI have identical action semantics. No scripted policy. Two
   pluggable backends: `--backend anthropic` (canonical; Anthropic Messages API over urllib, no
   SDK dep; needs `ANTHROPIC_API_KEY`) and `--backend claude-cli` (shells out to local
   `claude -p`; no key — used to validate end-to-end). Scored identically (trajectory →
   `score_instance` → `aggregate` → GCS@1/solve), manifest records `{model, backend}`, summary
   filename namespaced per agent label. **Validated live** (claude-cli, seed 1): the model made
   real decisions (`jump 3` → `event 0` → `jump 5`), jumps counted, budget enforced, scored.
   **Versioned prompt manual (2026-06-05):** the agent's rules/instructions are a first-class,
   version-controlled artifact — `prompts/ftl_agent_v1.md` (a full operating manual: turn loop,
   obs schema field-by-field, core mechanics, how-to-play). The diagnosis that prompted it: a
   real run showed the model `power`s weapons then `wait`s forever because **power ≠ fire — you
   must `fire <slot> <room>` to set a target** (`targeted:false`); the obs now surfaces
   `targeted` and the manual teaches the mechanic. `--prompt-version` selects the manual;
   `prompt_version` is recorded in the manifest + agent label (a different manual = a different,
   non-comparable agent). Remaining: a FULL public/suite pass for the first real GCS@1 row.
7. **Richer observation** (mostly ✅): incoming projectiles, weapon charge/ETA, per-system
   ion/hack, exit beacon + positions, rebel fleet, sector-choice flag are done. **Crew
   management (2026-06-05):** `move_crew(crew_id, room_id)` is the universal tasking action
   (repair a damaged system = send to its room; fight a fire/intruder = send to that room; man
   a station). Obs now exposes what that needs (pure Lua, all `%rename`-bound, no rebuild):
   player system→`room_id` (where to send a repairer; `damage>0` = needs it), per-crew
   `species`/`skills`(0-5)/`repairing`/`fighting`/`on_enemy_ship`, `player_ship.intruders`
   (enemy boarders aboard our ship: room/health/species — "find invaders"), and
   `player_ship.fires` (burning rooms via `GetFireCount`). CLI `compact` surfaces `crew`,
   system `room`, `intruders`, `fires`. **Shot-outcome feed (2026-06-05):** Hyperspace event
   hooks (`PROJECTILE_FIRE`/`DAMAGE_AREA_HIT`/`SHIELD_COLLISION`, ourShots only) give the agent
   `player_ship.shots = {fired, hit, shields_blocked, missed, damage_dealt, recent[]}` so it can
   tell a whiff (evasion → target engines/flee) from a shield-block (→ drop shields/pierce) from
   a hit, instead of dumping ammo blindly. Verified live via `fight()`: fired=32/hit=8/blocked=17/
   missed=7 (chain-event callbacks return nil so damage still applies). Remaining: reactor
   breakdown detail, hull breaches, augments.
8. **Better baseline agent** (partly ✅): exit navigation, flee on O2/weapon/crew danger,
   event-choice escalation, stalemate-flee, and sector crossing are done. Remaining:
   active **crew repair** (move crew to a destroyed O2/weapons room instead of fleeing),
   FTL-charge-aware combat fleeing, buy at stores once #2 lands.
9. **Combat-time sector flee**: `leave_sector` currently refuses with a live enemy (the
   transition SIGBUS guard). Root-cause the crash (likely a projectile/teardown race) so
   the agent can also flee a sector mid-combat.

## Reliability — drone bugs FIXED + autonomous recovery (2026-06-04)

A single **macOS/Rosetta** bug (`translated:True`, SIGBUS) caused every "freeze"/crash:
Rosetta corrupts the **`RepairAnimation` vtable**, so **`RepairDrone::~RepairDrone()` SIGBUSes
whenever an enemy repair drone is FREED** — at a jump (`ClearLocation → RemoveExcessCrew`) and
at new-game init (`ShipBuilder::Open → CrewMemberFactory::Restart`). Found by `sample`-ing the
live process (the deepest `Hook_NNNN::wrapper` frame is a fn *called by* the symbol above it,
so guess-and-rebuild kept missing). You CANNOT refuse the drone's creation — that infinite-
loops `ShipGenerator::CreateShip → AddDrone`. **FIX (env-gated `FTL_BENCH_STABILIZE_DRONES=1`,
StatBoost.cpp):** hook `CrewMemberFactory::{Restart,RemoveExcessCrew}` and `std::remove_if` the
`IsDrone()` members out of `crewMembers`+`lostMembers` before `super()`, so the corrupt
RepairDrone is LEAKED (a few small objects/instance, bounded) instead of freed. Non-drone crew
free normally. Verified: `--new seed 3` (both crash sites) plays 10 jumps, 3 kills, crosses to
sector 1, hull 28/30, **0 crashes at full speed**.

**Defense in depth (kept as belt-and-suspenders):** the launcher exports
`HYPERSPACE_FORCE_EXIT_ON_FREEZE=1` so Hyperspace's `FreezeWatchdog` SIGKILLs any future spin
in ~5s (no human dialog) and `com.apple.CrashReporter DialogType none` silences crash popups;
the runner detects a dead game via `pgrep`, relaunches eagerly, and the agent bails on a
non-advancing obs `tick`. So even an unforeseen hang self-heals: kill → relaunch → continue.
`adapter/play_cli.py` reports `game_status: FROZEN_KILLED` so a live agent knows the episode ended.

**Agent-plays harness:** `adapter/play_cli.py` is a thin turn-based CLI (`obs/power/fire/jump/
event/leave/wait/start`, one action per call → compact JSON). It's the tool surface a code-mode
LLM agent uses to actually PLAY (vs the scripted baseline) — used to validate the burst-laser
fix and surface the freeze above with a real agent in the loop.

**Screenshot (on-demand vision, additive, 2026-06-05):** `adapter/capture.py` +
`play_cli.py screenshot [path]` lets a vision-capable agent SEE the game when JSON isn't enough.
It captures FTL's OWN window buffer via `screencapture -l <CGWindowID>` (occlusion-proof — works
even when another window covers FTL; the naive `-R region` grabs whatever is on top instead).
The CGWindowID comes from Quartz (optional `screenshot` extra: `pyobjc-framework-Quartz`,
macOS-only, lazy-imported so it never affects the rest of the CLI); falls back to an
AppleScript-bounds region grab (and SAYS SO) if Quartz is missing. Purely additive — does NOT
change the JSON obs; the turn-based pause makes each frame a stable, decision-relevant moment.
Verified end-to-end (window_buffer, occlusion_proof=True).

**GAME OVER detection (2026-06-05).** A crew-death game-over is neither a process crash (so the
pgrep recovery doesn't fire — FTL is alive at the menu) NOR `hull<=0` (crew death leaves the
hull intact), and the obs had no signal for it — so an agent/driver would spin no-op actions at
the GAME OVER screen until an iteration cap. Fixed: bound `CommandGui::gameover` (one-line
`%rename`, rebuild) → obs carries `game_over`; the baseline `play()` loop + CLI (`game_status:
GAME_OVER`) treat it as terminal, and the runner resets to a fresh episode. Verified end-to-end:
the obs flag flips and a driver caught it and reset (`GAME OVER detected -> reset to new game`).

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
