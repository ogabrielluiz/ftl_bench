---
title: Action set
description: The intent-level commands an agent can issue, one per turn.
---

The agent issues exactly **one** command per turn. The same dispatcher (`apply_command`) is used by
the CLI and the LLM track, so semantics are identical however you drive the game.

## Commands

```
power <sys_id> <level>           set a system's power (needs enough free reactor)
fire <slot> <enemy_room>         aim a weapon at an enemy room (sets target + autofire)
beam <slot> <room_a> [room_b]    fire a BEAM weapon, sweeping room_a -> room_b
jump <beacon_index>              jump to a connected beacon (see map.beacons[].index)
event <choice_index>             resolve a blocking event / popup
leave                            cross into the next sector (only at the exit beacon: at_exit=true)
wait [frames]                    let time pass (e.g. wait, wait 20, wait 600)
crew <crew_id> <room>            move a crew member to a room (repair / fight fire / fight boarders)
buy <i> / sell <i>               store transactions
upgrade <sys_id>                 raise a system's max power (store)
cloak | battery                  activate cloak / backup battery
hack <enemy_sys> | drone | dronerecall
board <enemy_room> | recall | mindcontrol <enemy_room> | doors <open|close> [room]
```

## System ids

`0` shields, `1` engines, `2` oxygen, `3` weapons, `4` drones, `5` medbay, `6` piloting,
`7` sensors, `8` doors, `9` teleporter, `10` cloaking, `12` battery, `14` mind control,
`15` hacking.

## Interface quirks

These differ from clicking in the real game, and are the few things an agent needs to be told:

- **Commands are one-time sets, not continuous actions.** `power`, `fire`, and `crew` each set a
  state once. Re-issuing the same one when it is already in effect does nothing (the result says
  `NO EFFECT`). Read the current state and pick the next thing to do.
- **Powering a weapon does not fire it.** Use `fire <slot> <enemy_room>` to set its target and
  enable autofire. `targeted: false` means it will never shoot, however long you wait.
- **A broken module is not a power problem.** A system with `damage > 0` or `on_fire: true` is
  broken and works poorly no matter how much power it has. Send a crew member to its room to repair
  or extinguish it. That is different from a system at 0 power with no damage, which just needs
  `power`.
- **You move between beacons with `jump`; you advance to the next sector with `leave`,** only when
  `at_exit` is true. `jump_charged: false` means the FTL drive is still recharging.
- **A non-null `event` freezes the sim** until you resolve it with `event <choice_index>`.

After firing, read `shots` to see whether your shots are landing, getting shield-blocked, or
missing, rather than guessing from the enemy's hull alone.
