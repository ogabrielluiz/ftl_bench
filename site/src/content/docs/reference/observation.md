---
title: Observation schema
description: Preserved compact game facts, setup identity, optional probes and authoritative victory.
---

The agent sees `play_cli.compact()` JSON. The bridge emits bound game facts; optional fields are omitted when unavailable. Absence means unknown. See the repository's `docs/observation_coverage_audit.md` for evidence levels and remaining probes.

## Top level

| Field | Meaning |
|---|---|
| `game_started`, `paused` | Lifecycle and pause flags |
| `sector`, `hull` | Zero-based sector; hull string current/max |
| `oxygen_pct`, `fuel`, `missiles`, `drone_parts`, `scrap` | Ship resources |
| `reactor_free/total`, `reactor_usable_free/total` | Allocation and effective storm/ion cap |
| `ship`, `difficulty` | Actual native setup identity |
| `capabilities` | Bridge/native protocol features |
| `victory` | Explicit authoritative native boolean |
| `game_status` | Absent while alive; DESTROYED/GAME_OVER/VICTORY |
| `interrupted_by` | Early advance interruption |
| `ftl_score` | Native score when available |
| `economy` | Native upgrade prices/caps/legality and fuel-recovery state |
| `action_feedback` | Applied/rejected crew, event, upgrade and recovery requests |

## Ship and combat

Systems preserve id/name, power current/max, room, damage, repair/fire/broken state and `ion`, `ioned`, `hacked`. Crew preserve position, species, health and task; fires/intruders identify crisis rooms.

Player `crew` contains owned crew with health/death facts and original native `id`, `player_owned`, `owner_ship_id`, `current_ship_id` and `controllable`. Survival counts only living crew. Own boarders remain owned; hostile boarders appear separately in `intruders`. Mind-controlled friendly crew remain owned but cannot be moved. `action_feedback` identifies applied/rejected movement commands. The runner requires Lua ownership/control capabilities under `owned-player-crew-v1`.

Rooms preserve available oxygen/fire/breach/rectangle facts. Doors include inner doors **and outer airlocks**, with unique display index, engine id, room endpoints, open/locked/forced/hacked state and `airlock`. Endpoint -1 is space.

Weapons preserve type, power, charge/max, damage/piercing, ready and pending manual fire. Each fire/beam queues one release; a charging beam retains both endpoints. A held charged weapon does not automatically fire.

Enemy hull, shields, systems/rooms/weapons, crew positions/tasks and drones are exposed when available. Active false means depowered weapons; targetable false means unavailable native target. Neither proves victory. `enemy_ship.destroyed` reports the authoritative native destruction boolean when bound; a lingering wreck object can coexist with legal travel, and hull alone is not used to infer destruction.

Shot telemetry reports observed fired/hit/shield-blocked/missed/damage outcomes. Special-system blocks include cloak, battery, hacking, drones, teleporter and mind control readiness/occupants where bound.

## Map and screens

Map includes actual current position/sector, connected beacons, jump charge, exit, hazard and known route metadata. Travel scoring requires changed observed map identity. `economy.sector_navigation_version: 1` and capability `sector_navigation: true` prove the repaired native neighbor-index interface under `native-sector-neighbors-v1`; protocol 5 alone is insufficient. `economy.beacon_navigation_version: 1` and `beacon_navigation: true` add the `native-beacon-readiness-v1` gate. `economy.navigation` exposes `can_jump`, `enemy_defeat_pending`, native `drive_current`/`drive_max` and optional `reason`. `can_jump` combines native button/full-timer/system/fuel/context readiness. Pending defeat is guidance only; it never independently forbids a charged legal jump. A null reason can be omitted by the Lua codec.

Events preserve full text and original indices, `native_type`, availability, native `open_time` and `dialog_keys`. Type 1 is disabled. Applied feedback confirms queued selection; disabled, delayed, refused and already pending requests are distinct. Unverified blue/cost markers and hidden rewards are not inferred. Stores contain visible indexed transactions. Sector-choice and flagship surge/super-shield facts remain optional.

`economy` preserves native `upgrade_available`, `systems` with original `system_id`, `current_max_power`, `max_level`, `next_upgrade_cost` and `can_upgrade`, plus equivalent reactor facts. Native nullable costs/reactor may be omitted in Lua JSON; missing cost is unknown/unavailable, never free. Costs can stay visible when combat/modal state blocks buying.

`native-enemy-hostility-v1` requires Lua `enemy_hostility: true`. A surrendered ship can retain positive hull, weapons and a native ship pointer; combat and targeting use the native `_targetable.hostile` flag. Non-hostile, destroyed, jumping or unknown-state enemy targets reject enemy-directed weapon requests and clear queued enemy fire. Dispatch feedback records `enemy_hostile`, `enemy_targetable` and accepted queue state. `targetable` and compact `active` never become true from hull or equipment alone. Friendly ships do not independently block a charged native-legal sector exit.

`economy.fuel_recovery` contains `out_of_fuel`, `distress_on`, `can_wait` and `waiting`. Native Wait is a recovery turn resolved by frame progression, with normal encounter/fleet consequences; waiting frames alone do not create fuel. Runner/ruleset v7 requires `native-economy-and-fuel-recovery-v1` and valid upgrade/recovery capabilities.

Raw boss stage/phase counters do not establish completed phases or a win. The current native victory getter confirms the final win; intermediate completed phases remain unreported.

See [actions](/reference/actions/) and [protocol](/introduction/protocol/).
