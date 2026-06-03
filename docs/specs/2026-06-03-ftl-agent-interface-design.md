# ftl_bench — AI Agent Interface for Playing FTL: Design Spec

**Date:** 2026-06-03
**Status:** Draft (design phase)
**Goal:** A reproducible agent-evaluation benchmark that lets LLM coding agents play *FTL: Faster Than Light* through an intent-level interface built on the FTL-Hyperspace Lua API.

> **Grounding note:** The action/state-surface claims in §5–§7 are being verified file-by-file against the cloned Hyperspace source (`~/Projects/FTL-Hyperspace`, v1.22.2). The source-level findings live in `docs/deepdive/` and supersede any web-derived claim here on conflict.

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

FTL is real-time-with-pause; an LLM decides in seconds. The bridge keeps the sim **paused by default** and unpauses in controlled increments under harness policy.

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
| `jump` | beacon_id | StarMap / `TeleportSystem:InitiateTeleport` (exposed) |
| `choose_event` | choice_index | **gap — extend Hyperspace** (ChoiceBox/EventButtons binding) |
| `store_transaction` | buy/sell, item | **gap — extend Hyperspace** (Store_Extend binding) |
| `end_turn` | — | harness resumes the sim |

**Extend, don't hack.** The three gaps are closed by adding first-class SWIG/Lua bindings in an extended Hyperspace fork (the open-source C++ layer is built for this), **not** by OS-level input synthesis. Input synthesis is permitted only as a throwaway stopgap to unblock harness development before the bindings land, and is never part of the shipped benchmark.

## 7. Feasibility assessment

| Area | Rating | Basis |
|---|---|---|
| State extraction | **HIGH** | Rich Lua read surface; FTLAV proves savefile extraction as fallback |
| Power / crew / jump control | **HIGH** | Bindings exist (`MoveToRoom`, `IncreasePower`, jump/teleport) |
| Weapon-targeting + UI actions (event/store) | **MEDIUM → HIGH** | Not cleanly bound today; closed by extending Hyperspace SWIG layer |
| Turn-gating a real-time game | **MEDIUM** | Pause exists + per-frame hook; reaction-window policy is real work |
| Determinism / seeding | **HIGH** | Seeded runs; seed exposed to Lua (~v1.6.0); caveat: pin mods+version+AE |
| Transport (Lua ↔ harness) | **HIGH** | File-polling is robust; socket if sandbox allows |

**Overall: FEASIBLE.** Critical path = (a) the Hyperspace action-binding extensions for targeting/events/store, and (b) the event-driven gating policy. Both are bounded engineering, not open research.

## 8. Benchmark layer

- **Seeding.** Harness sets the run seed via the bridge before `reset`; records it in the trajectory. Reproducibility manifest = {FTL version, Hyperspace/extended build hash, mod bundle hash, AE flag, seed}.
- **Scenarios.** Full-run (sector 1 → flagship) for headline scores; curated micro-encounters for cheap, high-signal eval of specific skills (combat micro, resource allocation, event risk).
- **Metrics.** Sectors cleared, flagship attempts/kills, final score, survival time, scrap efficiency, decision count & latency, **illegal-action rate**, and per-scenario success.
- **Trajectory logging.** Every `(observation, legal_actions, action, reward, info)` tuple persisted for replay, debugging, and offline analysis.

## 9. Risks & open spikes

1. **Reaction-window gating** — can event-driven pausing reliably surface sub-second decisions? *Spike: instrument a combat encounter.*
2. **Lua sandbox IO** — does Hyperspace's Lua expose `io`/sockets, or must transport be a Hyperspace-provided helper / file polling? *Spike: inspect `lua/` runtime setup.* (→ deepdive)
3. **Action-gap reverse engineering** — locating the right C++ functions to hook for weapon targeting / event choice / store. *Spike: deepdive + a prototype binding.*
4. **Seed scope** — confirm exactly what the seed determinizes (map, events, combat RNG) and any non-determinism that leaks. *Spike.*
5. **Headless / throughput** — can FTL+Hyperspace run fast/headless enough for many eval episodes? *Spike.*

## 10. Build sequence (informs the implementation plan)

1. **Deepdive** the Hyperspace Lua surface → `docs/deepdive/` (in progress).
2. **State-read prototype**: Lua bridge emits `Observation` JSON over file transport; harness reads it. (HIGH-confidence, no extensions.)
3. **Gating prototype**: per-frame hook + pause; event-driven decision points.
4. **Exposed-action prototype**: power/crew/jump via existing bindings, end-to-end agent loop on a micro-scenario.
5. **Hyperspace extensions**: SWIG bindings for targeting, event-choice, store.
6. **Harness + adapter**: gym API, MCP tools, episode/seed/scoring/logging.
7. **Scenario library + metrics**; first benchmark report.

---

*Next: source-grounded deepdive findings land in `docs/deepdive/`, then this spec's §5–§7 are reconciled and an implementation plan is written.*
