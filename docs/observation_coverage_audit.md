# Observation coverage audit

This is an interface audit, not an agent strategy guide.

The benchmark prompt should not teach FTL strategy. It should expose the facts a competent player
can see in the game UI, plus exact command semantics, so the agent can apply its own game knowledge.

## Sources checked

- Steam guide: "How to Avoid losing to Luck" - https://steamcommunity.com/sharedfiles/filedetails/?id=170276164
- Steam guide: "How to reliably beat the Flagship, FTL (Advanced Edition)" - https://steamcommunity.com/sharedfiles/filedetails/?id=2462125559
- Cross-check: "Practical FTL" - https://steamcommunity.com/sharedfiles/filedetails/?id=266502670
- Cross-check: "Get Your First Win in FTL Hard Difficulty" - https://steamcommunity.com/sharedfiles/filedetails/?id=373609260

## Coverage matrix

| Player-visible requirement | Current status | Notes |
|---|---|---|
| Own hull, oxygen, fuel, missiles, drone parts, scrap | Covered | Top-level compact fields. |
| Reactor allocation and true storm-capped usable power | Covered | `reactor_free`, `reactor_total`, `reactor_usable_*`, `reactor_power_penalty`. |
| Own systems: power, room, damage, ion, repair-needed state | Covered | `needs_repair` was previously lost when `damage == 0`; now preserved. Compact also emits `broken` and `repair_room` so damaged/repair-needed/fire-blocked modules are not mistaken for merely unpowered modules. |
| Crew state for repair/fighting/manning | Mostly covered | Crew id, room, species, hp, busy, boarding are exposed. Detailed skills are still raw-only. |
| Fires and intruders | Covered | `fires` and `intruders` identify crisis rooms. |
| Door/vent execution | Improved | Compact now exposes player `rooms` with oxygen/fire/breach fields when bound, plus `doors` with room endpoints and open/locked/forced/hacked state. |
| Player weapons: type, charge, power, damage, piercing, shots, ready, queued | Covered | Enough for volley timing and shield-pierce reasoning. |
| Shot outcomes: hit, shield-blocked, missed, damage | Covered | `shots` tells whether attacks are missing, blocked, or landing. |
| Enemy weapons and incoming projectiles | Covered | Enemy weapon type/charge/damage/pierce and `incoming_fire` are exposed. |
| Enemy systems and target rooms | Covered | Enemy rooms and powered systems are exposed. Hacked rooms are now preserved. |
| Enemy drones | Covered | Deployed enemy drones are exposed and counted as active threats. |
| Enemy crew positions | Improved | `rooms_with_crew` is forwarded and now carries optional member details; compact also exposes `enemy.crew` when the bridge can read health/species/task fields. |
| Boarding / teleporter readiness | Newly covered | Raw `teleporter` block is now forwarded into compact observations. |
| Mind control readiness and legal target rooms | Newly covered | Raw `mind_control` and enemy `rooms_with_crew` are now forwarded. |
| Cloak, battery, hacking, drone readiness | Newly covered | Raw special-system blocks are now forwarded. |
| Current beacon hazard | Covered | `map.hazard` and `pds` are exposed. |
| Connected beacon route metadata | Improved | Compact now preserves `known`, `danger_zone`, `boss`, `nebula`, `store`, `distress`, `has_event`, `new_sector`, `fleet`, `quest`, positions, and distance to exit. |
| Stores at current beacon | Covered | Store buy/sell lists are exposed when standing at a store. |
| Store locations before arrival | Not covered | Only available if the game exposes them through known beacon data; no compact field yet. |
| Event text and choices | Improved | Choices now include explicit `index`, full text, and optional metadata (`blue`, `enabled`, `available`, `disabled`, `locked`, `cost`) when bound. |
| Blue/disabled event choice metadata | Best-effort covered | The bridge probes known scalar fields and compact preserves them. If Hyperspace does not bind a marker, no field is invented. |
| Flagship phase-specific state | Best-effort improved | Current boss beacon is exposed through map-derived `flagship.present`; phase, super-shield, and power-surge fields are preserved when the bound objects expose scalar values. |
| Sector-choice screen | Best-effort improved | Compact exposes `choosing_new_sector` and preserves `sector_choices` if `StarMap.sectors` exposes scalar choice fields. |
| Terminal concession | Covered | `giveup` records an explicit unsolved concession with current state/FTL score; this prevents irrecoverable runs from turning into no-op loops without rewarding the concession. |

## Highest-priority non-strategy gaps

1. Runtime-verify which optional Lua probes actually populate on the current Hyperspace build:
   event blue/disabled fields, sector choice fields, flagship phase/surge fields, and room breach fields.
2. Add C++/SWIG bindings for any player-visible flagship or sector-choice fields that remain absent
   after live verification.
3. Consider compacting room/door topology further if token pressure rises in long runs.

The rule for adding fields should be: if the game UI or existing raw bridge state makes the fact
available to a human player, compact should preserve it unless it is unsafe or too noisy.
