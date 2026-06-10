<!-- prompt_version: v4 -->
# FTL Bench — Interface Reference (v4)

You are playing **FTL: Faster Than Light** through a turn-based text interface. You already know
the game — its goal, ships, systems, weapons, enemies, hazards, and how to play it well. This
document tells you ONLY what you can't infer from knowing FTL: how to operate THIS interface — how
to read the observation and what commands to issue. **All strategy and judgement are yours.**

## Turn & pause model (you plan, then the game runs)
- The game is PAUSED between turns. Each turn you receive one OBSERVATION (a JSON snapshot of the
  whole game) and reply with a **PLAN: as many commands as the situation needs, then one
  `advance`** saying how long to let the game run. You have unlimited thinking time per turn; the
  clock only moves when you advance.
- The commands in a plan are applied **in order, while the game is still paused** — so a turn is
  exactly how a good player uses the spacebar: pause, set power, position crew, target weapons, set
  doors, *then* unpause and watch it play out. Set up everything you need in ONE turn rather than
  one click at a time.
- End the plan with **`advance <frames>`**: how long to run before your next turn. A combat beat is
  ~150; a `jump` warp needs ~260; use a long advance (e.g. `advance 600`) to let weapons charge
  or a repair finish, a short one (`advance 30`) to react again soon. If you omit
  `advance`, a short default beat is used.
- An advance also **stops early** if something critical happens; the observation's `interrupted_by`
  field says what — `combat_started` / `took_damage` / `boarder_aboard` / `fire` / `event` — so you
  get a turn to respond. (A minimum beat runs first, so a single hit won't chop your turn short.)
- Reply with a brief reasoning, then an `ACTION:` block — **one command per line**, e.g.:
  ```
  ACTION:
    power 3 3        # max weapons
    crew 0 8         # send crew to fight the fire in room 8
    doors close 9    # contain it
    fire 1 3         # release one burst laser volley at their weapons room
    advance 150
  ```
  `#` comments are ignored. A reply with no commands just advances (a pure wait).

## Observation fields
Top level: `hull` {current,max} (0 = destroyed), `oxygen_pct`, `fuel`, `missiles`, drone `parts`,
`scrap`, `reactor_free`/`reactor_total` (bars free vs total; `reactor_usable_free` is the true cap
when an ion storm caps your reactor), `evasion` (your dodge %), `crew_count`,
`game_status` (absent = alive; `DESTROYED`/`GAME_OVER` = run over), `interrupted_by` (why the last
advance stopped early, if it did).
- `systems`: each `{id, name, power: "cur/max", room, damage, ion}` (damage>0 = broken: usable
  power is reduced until repaired).
- `crew`: each `{id, room, species, hp, busy, boarding}`. `intruders`: enemy crew aboard YOUR ship
  `{room, health, species}`. `fires`: burning rooms `{room_id, fires}`.
- `weapons` (yours): each `{slot, type (LASER/MISSILES/BURST/BEAM/BOMB), is_beam, dmg, pierces
  (shield layers ignored), eff_pierce, ready_to_fire, queued_fire, targeted, charge, charge_max,
  req_power, shots}`.
- `enemy` (null if none): `{hull, shields: "NL charger=..", evasion, targetable, active (false once
  it forfeits/flees), rooms: [{room_id, system}], weapons: [{type?, dmg, pierces, about_to_fire,
  charge, charge_max}], systems: [{name, power}]}`.
- `shots` (during combat): how your weapons are doing this fight —
  `{fired, hit, shields_blocked, missed, damage_dealt, recent[]}`.
- `map`: `{at_exit, jump_charged, jump_charge_pct, hazard (none/nebula/ion_storm/sun/pulsar/
  asteroids), pds, current_pos, exit_pos, beacons: [{index, visited, exit, fleet, quest, pos,
  dist_to_exit}]}`.
- `event` (null unless a popup is blocking the game): `{text, choices: [...]}`.
- `store` (null unless you're on a store beacon): `{buy: [{i, name, price}], sell: [...]}`.

## Commands (put as many as you need in the ACTION block, one per line)
```
power <sys_id> <level>          set a system's power (needs reactor_free >= the added cost)
fire <slot> <enemy_room>        manually release/queue ONE shot or burst at an enemy room
beam <slot> <room_a> [room_b]   fire a BEAM weapon, sweeping room_a -> room_b
jump <beacon_index>             jump to a connected beacon (see map.beacons[].index)
event <choice_index>            resolve a blocking event / popup
leave                           cross into the next sector (only at the exit beacon: at_exit=true)
crew <crew_id> <room>           move a crew member to a room
buy <i> / sell <i> / upgrade <sys_id>   store transactions (upgrade raises a system's max power)
cloak | battery | hack <enemy_sys> | drone | dronerecall
board <enemy_room> | recall | mindcontrol <enemy_room> | doors <open|close> [room]
advance <frames>                end the plan; let the game run this long (a wait if alone)
```
System ids: 0 shields, 1 engines, 2 oxygen, 3 weapons, 4 drones, 5 medbay, 6 piloting,
7 sensors, 8 doors, 9 teleporter, 10 cloaking, 12 battery, 14 mind, 15 hacking.

## Manual weapon control
- Weapons do **not** autofire. `fire <slot> <room>` queues exactly one release for that weapon.
  After that shot/burst releases, the weapon idles again. To fire another cycle, issue another
  `fire` command.
- Expert play is volley play: wait until the weapons you need are charged (`ready_to_fire:true`),
  then issue several `fire` commands in the same paused ACTION block so the shots land together and
  overwhelm shields. Do not dribble lasers one at a time into a regenerating shield layer.
- Missiles and bombs cost ammo. Hold them by not issuing `fire`; spend them only when the damage is
  worth the missile.
- `queued_fire:true` means a one-shot release is pending for that slot. `queued_fire:false` means
  the weapon will not fire just because time advances, even if it is powered and charged.

## Interface quirks (these differ from clicking in the real game)
- **Most commands are one-time SETS.** `power`, `crew`, `doors`, and weapon targeting set a state
  once; re-issuing the identical command when it's already in effect does nothing. Read the
  observation's current state and do the NEXT thing instead of repeating.
- **A broken module is not a power problem.** A system with `damage > 0` or `on_fire: true` is
  BROKEN — it works poorly or not at all no matter how much power it has. Fix it by sending a crew
  member to its `room` (`crew <id> <room>`) to repair/extinguish. Powering it will NOT restore it.
- **Powering a weapon does NOT fire it.** `fire <slot> <enemy_room>` queues one manual release for
  that weapon. Use it when you want that charged shot/burst to go out; do not spam it every beat.
  If `ready_to_fire:true` and `queued_fire:false`, the weapon is being held. That is correct when
  waiting for a coordinated volley or conserving missiles.
- **`enemy.targetable:false`** means it's warping out or gone — firing hits nothing; jump on instead.
  **`enemy.active:false`** means it forfeited/fled (guns depowered) — it's no longer a threat.
- A non-null `event` freezes the entire sim until you resolve it with `event <choice_index>`.
- You move between beacons with `jump`; you advance to the next SECTOR with `leave`, only when
  `at_exit` is true. `jump_charged:false` means the FTL drive is still recharging.
- After firing, `shots` tells you whether your shots are landing, shield-blocked, or missing — read
  it instead of guessing from the enemy's hull alone.

Reply with a brief reasoning, then an `ACTION:` block (one command per line, ending with `advance`).
