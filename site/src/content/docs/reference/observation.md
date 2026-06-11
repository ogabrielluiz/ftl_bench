---
title: Observation schema
description: The decision-complete JSON the agent receives each turn.
---

Each turn the agent receives one JSON snapshot of the whole game (the `compact()` view). It is
decision-complete: everything needed to choose the next action is in it. Fields that do not apply
are omitted (for example, `enemy` is `null` out of combat; `store` appears only on a store beacon).

## Top level

| Field | Meaning |
|---|---|
| `game_started`, `paused` | lifecycle flags; at the menu `game_started` is false and `menu_buttons` is present |
| `sector` | current sector index |
| `hull` | `"cur/max"` (0 = destroyed) |
| `oxygen_pct`, `fuel`, `missiles`, `parts`, `scrap` | resources |
| `reactor_free` / `reactor_total` | power bars free vs total; `reactor_usable_free`/`_total` give the true cap under an ion-storm penalty |
| `evasion`, `crew_count` | your dodge %, crew alive |
| `interrupted_by` | why the last advance stopped early (`combat_started`, `took_damage`, `boarder_aboard`, `fire`, `event`) |
| `game_status` | absent while alive; `DESTROYED` / `GAME_OVER` when the run is over |

## Ship state

- `systems`: each `{id, name, power: "cur/max", room, damage, needs_repair, ion, on_fire, broken,
  repair_room}`. `broken` names why power alone will not fix it (`needs_repair`, `damaged`,
  `on_fire`, or a `+` combination).
- `crew`: each `{id, room, species, hp, busy, boarding}`.
- `fires`: burning rooms, each `{room_id, fires}` where `fires` is the number of fire blobs in that
  room (sum them for the total active fires).
- `rooms`: player ship room facts when available, including `{room_id, oxygen, fires,
  breaches/breached, rect}`.
- `doors`: door topology/state when available, including `{id/index, room_a, room_b, open, locked,
  forced_open, hacked}`.
- `intruders`: enemy crew aboard your ship, `{room, health, species}`.
- `weapons`: each `{slot, type, is_beam, dmg, pierces, eff_pierce, ready_to_fire, targeted, charge,
  charge_max, req_power, shots}`. `targeted: false` means the weapon has no target and will never
  fire until you `fire` it.

## Enemy (`null` if no combat)

`{hull, shields, evasion, rooms, rooms_with_crew, crew, weapons, systems, active, targetable,
fleeing, jump_charge_pct, flagship, super_shield, power_surge_timer}`.

- `active`: the enemy is still fighting (its weapons are powered). `false` means it has forfeit and
  depowered its guns.
- `targetable`: you can actually aim a weapon at it right now. `false` once it is warping out or
  gone, in which case firing hits nothing (the agent's equivalent of "no targeting cursor").
- `fleeing` / `jump_charge_pct`: it has given up and is charging its FTL drive to escape.
- `rooms_with_crew` and `crew`: enemy crew positions and optional health/species/task fields when
  the bridge can read them.
- `flagship`, `super_shield`, `power_surge_timer`: boss-specific facts when the current Hyperspace
  build exposes them.

## Combat feedback

- `shots`: how your weapons are doing this fight: `{fired, hit, shields_blocked, missed,
  damage_dealt, recent[]}`. A high `missed` count means the enemy is dodging (target its engines or
  expect misses); a high `shields_blocked` means you need to pierce or drop shields.

## Map and screens

- `map`: `{at_exit, jump_charged, jump_charge_pct, hazard (none/nebula/ion_storm/sun/pulsar/
  asteroids), pds, current_pos, exit_pos, beacons[]}`. Each beacon: `{index, visited, exit, fleet,
  quest, known, danger_zone, boss, nebula, store, distress, has_event, new_sector, pos,
  dist_to_exit}`. `sector_choices` appears when the sector picker exposes choices.
- `event`: non-null only when a popup is blocking the game: `{text, choices[]}`. Choices preserve
  `index`, `text`, and optional `blue`, `enabled`, `available`, `disabled`, `locked`, and `cost`
  fields when exposed. Resolve it with `event <choice_index>`.
- `store`: non-null only on a store beacon: `{buy[], sell[]}`.

See the [Action set](/reference/actions/) for what you can send in response.
