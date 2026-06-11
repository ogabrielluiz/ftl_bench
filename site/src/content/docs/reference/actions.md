---
title: Action set
description: The intent-level commands an agent can issue through the paused FTL interface.
---

The agent controls FTL through intent-level text commands. In the current v5 LLM
interface, a turn is one `ACTION:` block: several paused commands followed by
`advance <frames>`. The exception is `giveup`, which is sent alone and ends the
instance as an unsolved concession. The lower-level CLI can also send one
command at a time.

Example v5 turn:

```text
ACTION:
  power 3 3
  crew 0 8
  doors close 8
  fire 1 3
  advance 150
```

Commands before `advance` are applied while the game is paused. `advance` then
lets the simulation run and re-pauses at the next decision point or frame limit.

## Commands

```text
power <sys_id> <level>           set a system's power
fire <slot> <enemy_room>         aim a weapon at an enemy room
beam <slot> <room_a> [room_b]    fire a beam weapon, sweeping room_a -> room_b
jump <beacon_index>              jump to a connected beacon
event <choice_index>             resolve a blocking event or popup
leave                            cross into the next sector at the exit beacon
crew <crew_id> <room>            move crew to repair, fight fires, or fight boarders
buy <i> / sell <i>               store transactions
upgrade <sys_id>                 raise a system's max power at a store
cloak                            activate cloak
battery                          activate backup battery
hack <enemy_sys>                 launch hacking at an enemy system
drone / dronerecall              deploy or recall drones
board <enemy_room> / recall      teleport boarders or recall them
mindcontrol <enemy_room>         activate mind control
doors <open|close> [room]        open or close doors
giveup                           concede this benchmark instance as unsolved
advance <frames>                 plan terminator: let time pass
wait [frames]                    CLI-compatible wait command
```

## System ids

| id | System |
|---:|---|
| 0 | shields |
| 1 | engines |
| 2 | oxygen |
| 3 | weapons |
| 4 | drones |
| 5 | medbay |
| 6 | piloting |
| 7 | sensors |
| 8 | doors |
| 9 | teleporter |
| 10 | cloaking |
| 12 | battery |
| 14 | mind control |
| 15 | hacking |

## Interface quirks

- **Most commands are one-time sets.** Repeating `power`, `crew`, `doors`, or a
  weapon target that is already in effect usually does nothing. Read the
  observation and choose the next useful change.
- **Power does not repair damage.** A system with `damage > 0`,
  `needs_repair: true`, or `on_fire: true` is broken. Send crew to that
  system's `room`; do not keep adding power.
- **Powering a weapon does not fire it.** Use `fire <slot> <enemy_room>` or
  `beam <slot> ...` to set a target.
- **Events freeze the simulation.** If `event` is non-null, resolve it with
  `event <choice_index>` before expecting combat, repairs, or jumps to continue.
- **Jump and leave are different.** `jump` moves between beacons. `leave`
  crosses to the next sector and only works when `map.at_exit` is true.
- **Targetability matters.** If `enemy.targetable` is false, the enemy is gone or
  warping out; firing will not help.
- **Shot feedback is diagnostic.** Use `shots.missed` and
  `shots.shields_blocked` to tell evasion problems from shield problems.
- **Give-up is terminal.** `giveup` records a concession and ends the benchmark
  instance as unsolved with the current state and FTL score.

See [Observation schema](/reference/observation/) for the state fields these
commands depend on.
