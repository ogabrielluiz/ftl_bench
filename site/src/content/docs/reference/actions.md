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
upgrade <sys_id>                 buy one level at the native system price
reactor                          buy one level at the native reactor price
waitfuel                         request a native out-of-fuel recovery turn
distress <on|off>                toggle the native out-of-fuel distress beacon
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

- **Crew ownership is checked before movement.** `crew` commands address original native
  IDs for owned, living, controllable player crew. Hostile boarders cannot be moved;
  mind-controlled friendly crew are temporarily uncontrollable. Own boarders remain
  player-owned. `action_feedback` reports applied/rejected moves and reasons.
- **Most commands are one-time sets.** Repeating `power`, `crew`, `doors`, or a
  setting that is already in effect usually does nothing. Read the
  observation and choose the next useful change.
- **Power does not repair damage.** A system with `damage > 0`,
  `needs_repair: true`, or `on_fire: true` is broken. Send crew to that
  system's `room`; do not keep adding power.
- **Powering a weapon does not fire it.** Use `fire <slot> <enemy_room>` or
  `beam <slot> ...` to queue one release. A charging weapon keeps the request pending;
  another cycle needs another command. Beam endpoints remain distinct.
- **Events preserve native choice IDs and delay.** Type 1 choices are disabled.
  Feedback distinguishes disabled choices, keyboard delay/settings, refused
  selection and a pending selection. Applied means queued native selection;
  advance to resolve it before requesting another branch.
- **Upgrades use native rules.** Read `economy` costs and `can_upgrade`.
  Missing cost is unknown/unavailable, never free. Native actions refuse illegal,
  capped or unaffordable upgrades and charge only a successful level increase.
- **Fuel recovery is a game turn.** `waitfuel` activates native Wait when legal;
  `distress on|off` uses its toggle. Advance resolves normal encounters and fleet
  movement. Ordinary `wait`/`advance` passes frames and does not guarantee fuel.
- **Jump and leave are different.** `jump` moves between beacons. `leave`
  crosses to the next sector and only works when `map.at_exit` is true. Native
  routing chooses an actual neighboring-sector vector index, with explicit
  acceptance/refusal feedback; a sector type is not a route index.
- **Travel readiness is native.** Early jump/leave requests are rejected when
  native travel readiness is incomplete. A retained
  destroyed flag alone does not prove travel is legal; charged combat fleeing
  remains available under normal native rules.
- **Targetability matters.** If `enemy.targetable` is false, the enemy is gone or
  warping out; firing will not help.
- **Shot feedback is diagnostic.** Use `shots.missed` and
  `shots.shields_blocked` to tell evasion problems from shield problems.
- **Give-up is terminal.** `giveup` records a concession and ends the benchmark
  instance as unsolved with the current state and FTL score.

See [Observation schema](/reference/observation/) for the state fields these
commands depend on.
