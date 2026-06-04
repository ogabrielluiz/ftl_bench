# ftl_bench — AI Agent Interface for Playing FTL: Design Spec

**Date:** 2026-06-03
**Status:** Draft (design phase)
**Goal:** A reproducible agent-evaluation benchmark that lets LLM coding agents play *FTL: Faster Than Light* through an intent-level interface built on the FTL-Hyperspace Lua API.

> **Grounding note:** §5–§7 have been reconciled against a file-by-file deepdive of the cloned Hyperspace source (`~/Projects/FTL-Hyperspace`, v1.22.2). Full findings: [`docs/deepdive/hyperspace-lua-surface.md`](../deepdive/hyperspace-lua-surface.md) — authoritative on conflict. Key corrections folded in below: (1) **transport is the hard blocker** — the Lua sandbox disables `io`/`os`/sockets, so the harness link needs a new C++ binding + a JSON binding; (2) **jump is a gap**, not an exposed action; (3) **seed-setting needs a binding** (reading works today).

---

## 1. Objective & scope

Build an environment + interface so that a coding agent (e.g. Claude) can play FTL and have its decision-making *measured*. The benchmark optimizes for, in priority order:

1. **Reproducibility** — pinned seed + version + mod bundle ⇒ replayable, cross-agent-comparable runs.
2. **Clean perception/action** — the agent reasons over structured JSON and issues *intent-level* actions, not pixels or clicks.
3. **Fidelity** — the agent plays the actual game, not a reimplementation.

**In scope:** state extraction, intent-level action space, real-time→turn-based gating, episode/seed/scoring/logging, the Hyperspace extensions needed to close action gaps, and an agent-facing tool adapter.

**Out of scope (for v1 of the spec):** training RL policies, multiplayer, non-Hyperspace builds, modded content beyond base FTL Advanced Edition.

## 2. Target build

**FTL (Advanced Edition) + FTL-Hyperspace.** Hyperspace gives us:
- Lua read access to live engine objects (`Hyperspace.ships.player`/`.enemy`, crew, systems, weapons, map).
- Lua control over much of the sim (crew movement, power, jump, special systems).
- **Seeded runs** with the seed exposed to Lua (~v1.6.0+) — the reproducibility backbone.
- An **open-source C++/SWIG layer** we can extend for the few unbound actions.

Pinned for the benchmark: exact FTL version, exact Hyperspace (or `ftl_bench`-extended Hyperspace) build hash, Advanced Edition ON, and the mod bundle hash. Seeds only reproduce when all of these match.

## 3. Architecture

Four layers, each independently testable:

1. **`mod/ftl_bench_bridge` — in-game Lua bridge (inside FTL via Hyperspace).**
   - A per-frame Lua hook **gates the simulation** (auto-pause at decision points).
   - Serializes an `Observation` to JSON.
   - Receives an `Action` (or action batch) and applies it via the Lua API.
   - Talks to the harness over a **transport** (file-polling default; socket if the Lua sandbox allows).

2. **`harness/` — environment server (external process, Python).**
   - Gym-like API: `reset(seed, scenario) → Observation`, `observe() → Observation`, `step(action) → (Observation, reward, done, info)`.
   - Owns episode lifecycle, seed management, termination, scoring, and **full trajectory logging**.
   - Exchanges with the Lua bridge over the transport.

3. **`adapter/` — agent tool surface.**
   - Exposes the env to a coding agent as **MCP / function-calling tools** (`observe`, `act`, `legal_actions`, `end_turn`).
   - Translates the constrained action schema ↔ harness calls.

4. **`scenarios/` — benchmark content.**
   - Scenario defs (full run, or cheap micro-encounters: a single combat, an escape decision, a store-allocation puzzle) each with a pinned seed and success/score criteria.

## 4. The real-time → turn-based control model

FTL is real-time-with-pause; an LLM decides in seconds. The bridge keeps the sim **paused by default** and unpauses in controlled increments under harness policy. Mechanism (no new C++ required for the basic loop): freeze with `Hyperspace.FPS.SpeedFactor = 0` (the same trick Hyperspace uses during loading) or `App.gui.bPaused = true`, gate inside the `ON_TICK` internal-event hook, and resume by restoring `SpeedFactor = 1`. A dedicated `CFPS:StepFrames(n)` binding is a likely robustness add if Lua-side toggling races pending animations (tracked spike).

- **Event-driven gating (default).** Run until the next *significant event*, then re-pause and request an action. Significant events are drawn from Hyperspace's callback taxonomy (combat start, enemy weapon charged/about-to-fire, projectile incoming, system damaged, crew low-health/death, jump arrival, event/store screen shown, hull damage). Mirrors expert human micro-pausing.
- **Fixed-tick gating (option).** Unpause for *N* frames, re-pause. Cheaper, simpler; risks missing reaction windows.
- **Reaction-window handling** is the central design risk: some events demand sub-second response (incoming missile vs. a powered defense drone). The gating policy must surface these as decision points *before* the window closes. Tuning this is a tracked spike.

The harness controls pause/unpause; **pause is not an agent action**. The agent acts within a paused decision point and signals "resume" via `end_turn`.

## 5. Observation space

Structured JSON emitted at each decision point. Sketch (final field list pinned by `docs/deepdive/`):

```jsonc
{
  "context": "combat" | "event" | "store" | "map" | "menu",
  "tick": 12843,
  "player_ship": {
    "hull": [21, 30], "reactor": {"total": 18, "available": 4},
    "resources": {"scrap": 64, "fuel": 11, "missiles": 7, "drone_parts": 3},
    "oxygen_pct": 100,
    "systems": [{"id": "weapons", "power": 3, "max": 4, "damage": 0, "ion": 0, "level": 2}],
    "crew": [{"id": 0, "name": "...", "race": "human", "room": 3, "x": .., "y": ..,
              "health": [100,100], "skills": {...}, "mind_controlled": false}],
    "weapons": [{"slot": 0, "id": "LASER_BURST_1", "powered": true,
                 "charge_pct": 100, "cooldown": 0, "target_room": null}],
    "drones": [...], "augments": ["..."]
  },
  "enemy_ship": { /* visible subset of the same shape, null if none */ },
  "combat": {"incoming_projectiles": [{"type":"missile","eta_frames": 40, "target_room": 2}]},
  "map": {"sector": 3, "current_beacon": 7, "rebel_fleet_advance": 0.4,
          "beacons": [{"id": 9, "explored": false, "hazard": null, "type": "store"}]},
  "event": {"text": "...", "choices": [{"index":0,"text":"...","requires":null}]},
  "legal_actions": [ /* what's valid in this context, see §6 */ ],
  "seed": 1234567890
}
```

`legal_actions` is computed by the bridge for the current context so the agent never has to guess what's valid — and so we can measure illegal-action rate.

## 6. Action space (intent-level)

The agent issues *intents*, not clicks. Each maps to one or more Lua calls in the bridge.

| Action | Params | Backing |
|---|---|---|
| `set_system_power` | system, level | `ShipSystem:IncreasePower/DecreasePower/SetPowerCap` (exposed) |
| `move_crew` | crew_id, room_id | `CrewMember:MoveToRoom` (exposed) |
| `assign_crew_task` | crew_id, task | `CrewMember:SetTask/SetCurrentSystem` (exposed) |
| `target_weapon` | weapon_slot, enemy_room | **gap — extend Hyperspace** (WeaponControl/CombatControl binding) |
| `fire_weapons` | slots[] / autofire | partly exposed; firing path may need a binding |
| `activate_system` | cloak / hacking / mind-control / battery / teleport | mostly exposed via system objects |
| `jump` | beacon_id | **gap — extend Hyperspace** (`StarMap` has no `Jump()` binding; add `StarMap_Extend:InitiateJump(Location*)`) |
| `choose_event` | choice_index | **gap — extend Hyperspace** (`ChoiceBox.selectedChoice` is read-only; add `:ConfirmChoice(index)`) |
| `store_transaction` | buy/sell, item | **gap — extend Hyperspace** (`Store`/`StoreBox` unbound; highest-effort gap, deferrable from v1) |
| `end_turn` | — | harness resumes the sim (`FPS.SpeedFactor = 1`) |

**Extend, don't hack.** The gaps are closed by adding first-class SWIG/Lua bindings in an extended Hyperspace fork (the open-source C++ layer is built for this), **not** by OS-level input synthesis. The blocking new bindings cluster in four UI-driven actions — **weapon-target-and-fire, event-choice-confirm, jump-trigger, store** — of which the first three are low/medium effort and store is the only high-effort item (deferrable from a v1 that skips shops). Input synthesis is never part of the shipped benchmark. The full file-level extension task list (P0/P1/P2) is in the deepdive §10.

## 7. Feasibility assessment

| Area | Rating | Basis (deepdive-confirmed) |
|---|---|---|
| State extraction | **HIGH** | Rich read surface live today (`ShipManager` player+enemy, crew, systems, weapons, map). Needs a JSON binding to serialize (none bundled). |
| Power / crew / teleport control | **HIGH** | Exposed: `IncreasePower`/`SetPowerCap`, `MoveToRoom`/`SetTask`, `TeleportSystem:InitiateTeleport`, cloak/battery toggles |
| Weapon-targeting, event-choice, jump | **MEDIUM** | Not bound today; thin C++ wrappers over existing logic — low/med effort, low risk |
| Store transactions | **LOW→MED** | `Store`/`StoreBox` fully unbound; highest-effort gap. **Deferrable from v1.** |
| Turn-gating a real-time game | **MEDIUM** | Pause works via `FPS.SpeedFactor=0` + `ON_TICK` hook, no new C++; `StepFrames` may be needed for animation races (spike) |
| Determinism / seeding | **HIGH** | Seeded runs real; seed *readable* in Lua. *Setting* needs a `SetRunSeed` binding (low effort). Pin mods+version+AE+difficulty. |
| Transport (Lua ↔ harness) | **MEDIUM** | ⚠️ **Hard blocker.** Lua sandbox disables `io`/`os`/`package`/sockets (`lua/linit.c`). Requires a new C++ binding: file bridge (`Hyperspace.Benchmark.write/read`) or AF_UNIX/named-pipe socket. |

**Overall: FEASIBLE.** Critical path, in order: **(1) transport binding + JSON** (the structural root — everything depends on it), **(2) the four UI-action bindings** (weapon-target-and-fire, event-choice-confirm, jump, store), **(3) deterministic frame-step + seed-setter**. All bounded engineering over an existing SWIG layer, not open research. See deepdive §10 for the prioritized file-level work list and §11 for the spikes.

## 8. Benchmark layer

- **Seeding.** Harness sets the run seed via the bridge before `reset`; records it in the trajectory. Reproducibility manifest = {FTL version, Hyperspace/extended build hash, mod bundle hash, AE flag, seed}.
- **Scenarios.** Full-run (sector 1 → flagship) for headline scores; curated micro-encounters for cheap, high-signal eval of specific skills (combat micro, resource allocation, event risk).
- **Metrics.** Sectors cleared, flagship attempts/kills, final score, survival time, scrap efficiency, decision count & latency, **illegal-action rate**, and per-scenario success.
- **Trajectory logging.** Every `(observation, legal_actions, action, reward, info)` tuple persisted for replay, debugging, and offline analysis.

## 9. Risks & open spikes

Resolved by the deepdive: Lua sandbox IO (✗ disabled — transport needs C++) and action-gap locations (mapped to files in deepdive §10). Remaining spikes (full list in deepdive §11):

1. **Pause/step race (highest priority)** — does the `SpeedFactor=0`/`bPaused` toggle cleanly freeze mid-combat, or do animations slip a frame? Decides whether the simple polling loop suffices or `CFPS:StepFrames(n)` is mandatory.
2. **Transport latency budget** — measure file-bridge vs. socket round-trip; picks the transport and whether real-time-ish play is viable vs. strictly turn-based.
3. **Choice-confirm execution path** — verify a new `ChoiceBox:ConfirmChoice()` actually runs the event's consequences, not just a UI highlight.
4. **Internal-event firing order** — document when `PROJECTILE_FIRE`/`DAMAGE_*`/cooldown updates fire relative to damage resolution (pre- vs post-damage state at re-pause).
5. **Weapon target-room round-trip** — confirm `SetWeaponTargetRoom` → `Fire()` hits the intended enemy room end-to-end.
6. **Seed completeness** — with fixed seed + identical mods/version, do map/events/boss-fleet reproduce bit-for-bit? Is mid-run `mt19937` checkpointing needed, or is run-start seeding enough?
7. **Headless / throughput** — can FTL+Hyperspace run fast/headless enough for many eval episodes?

## 10. Build sequence (informs the implementation plan)

1. ✅ **Deepdive** the Hyperspace Lua surface → [`docs/deepdive/hyperspace-lua-surface.md`](../deepdive/hyperspace-lua-surface.md).
2. **Transport + JSON bindings** (deepdive P0 #1–#2): the structural root. C++ file-bridge or AF_UNIX socket + JSON encode/decode. Nothing else can be exercised end-to-end until this exists.
3. **State-read prototype**: Lua bridge serializes `Observation` JSON through the transport; harness reads it.
4. **Gating prototype**: `ON_TICK` + `SpeedFactor` pause; event-driven decision points. Run the pause-race spike (deepdive §11.1).
5. **Exposed-action prototype**: power/crew/teleport via existing bindings — end-to-end agent loop on a micro-scenario.
6. **Action-gap bindings** (deepdive P0 #3–#5,7): weapon-target-and-fire, event-choice-confirm, jump-trigger, seed-setter. (Store deferred — P2 #16.)
7. **Harness + adapter**: gym API, MCP tools, episode/seed/scoring/logging.
8. **Scenario library + metrics**; first benchmark report.

---

*Next: source-grounded deepdive findings land in `docs/deepdive/`, then this spec's §5–§7 are reconciled and an implementation plan is written.*
