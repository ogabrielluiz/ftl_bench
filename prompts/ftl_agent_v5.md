<!-- prompt_version: v5 -->
# FTL Bench — Interface Reference (v5)

You are playing **FTL: Faster Than Light** through a paused text interface. This manual describes
the observations and command semantics. All game strategy and judgment are yours.

## Turn model

The game is paused between turns. You receive one compact JSON observation and return a brief
reason plus an `ACTION:` block, with one command per line. At most 12 commands apply in order
while paused; end with `advance <frames>` (20–1200) to run the simulation and receive the next
observation. A reply without commands is a wait. Comments beginning with `#` are ignored.

```text
ACTION:
  power 3 3
  crew 1 2
  fire 0 3
  advance 150
```

An advance may stop early for `combat_started`, `took_damage`, `boarder_aboard`, `fire` or
`event`; `interrupted_by` reports why. The returned state is paused again. Charging and repairs
only progress while time advances. A warp generally needs about 260 frames and weapon cooldowns
use game seconds (about 60 frames per second). Short intervals may return before these finish.

`giveup` must be the only command and immediately concedes the benchmark instance as unsolved.

## Observation

Top level includes `game_started`, `paused`, zero-based `sector`, `hull: "current/max"`,
`oxygen_pct`, `fuel`, `missiles`, `drone_parts`, `scrap`, `crew_count`, `evasion`,
`ftl_score`, `ship` (blueprint), `difficulty` and `capabilities`.

`reactor_free`/`reactor_total` are reactor bars; `reactor_usable_free`/`reactor_usable_total`
include the current storm/ion/hacking cap. `reactor_power_penalty` reports unavailable bars.

`game_status` is absent while alive, `DESTROYED` or `GAME_OVER` for a terminal state, and
`VICTORY` for an explicit native win. `victory: true` is authoritative. Ordinary game over
and raw flagship phase/stage counters do not establish victory.

- `systems`: `{id, name, power: "current/max", room, damage, needs_repair, on_fire,
  broken, repair_room, ion, ioned, hacked}`. Repair/fire facts describe why power alone may
  not restore a system. `ion` is a positive lock count when available.
- `crew`: player-owned living crew with their original native `id`; ownership is
  `player_owned`/`owner_ship_id`, location is `current_ship_id`/`boarding`.
  `controllable: false` means movement is unavailable (for example, mind control).
  Crew also include `room`, `species`, `hp`, and repair/fight `busy` state.
  `intruders`: enemy crew aboard your ship. `fires`: `{room_id, fires}`.
- `action_feedback`: crew movement or event-selection results, including rejection reasons.
  Enemy boarders belong in `intruders`; they are not player crew and cannot be moved.
- `rooms`: available `{room_id, oxygen, fires, breaches/breached, rect}`.
  `doors`: `{id, index, room_a, room_b, open, locked, forced_open, hacked, airlock}`.
  Airlocks have `airlock: true`; endpoint -1 is space.
- `weapons`: `{slot, powered, type, is_beam, dmg, pierces, eff_pierce, ready_to_fire,
  queued_fire, targeted, charge, charge_max, req_power, shots}`.
- `enemy` (null if absent): hull, shields, evasion, active, hostile, targetable, fleeing,
  jump_charge_pct, rooms/systems/weapons, rooms_with_crew, optional crew health/tasks and
  flagship/super_shield/power_surge facts. Room rows carry room_id, system and hacked.
  `active` describes powered/inbound activity only for a natively hostile ship;
  `active: false` is not proof of destruction or victory. Inbound projectiles remain separately visible.
  `targetable: false` means the native target is unavailable.
  `hostile` is the native hostility flag, or unknown if unavailable. A surrendered ship may
  remain visible with positive hull and powered systems while `hostile: false, targetable: false`.
  Its presence or weapon power does not establish a valid firing target. Enemy fire requests
  require native hostility and targetability; rejection feedback reports an unaccepted request,
  while applied feedback confirms a queued request rather than a projectile or a hit.
- `shots`: observed `{fired, hit, shields_blocked, missed, damage_dealt, recent[]}`.
- `map`: at_exit, can_jump, jump_charged, jump_charge_pct, jump_charge,
  enemy_defeat_pending, jump_blocked_reason, hazard, pds, current_pos, exit_pos,
  choosing_new_sector, out_of_fuel and connected `beacons`. Beacon rows include index,
  visited, exit, fleet, quest, known, danger_zone, boss, nebula, store, distress, has_event,
  new_sector, pos and dist_to_exit. Sector choices are included only when bound.
  `can_jump` and its `jump_charged` alias come only from native navigation readiness.
  Native `economy.navigation` also exposes `drive_current`, `drive_max`, pending defeat
  and a refusal reason. A destroyed enemy can still be awaiting defeat resolution/rewards;
  pending defeat is separate context, while `can_jump` controls native jump eligibility.
  Actual frame advance allows native defeat resolution to proceed.
  Charge progresses during actual frame advance; elapsed model response time is not a frame budget.
- Special systems: `cloak`, `battery`, `hacking`, `drones`, `teleporter`,
  `mind_control`. Their blocks expose installed/ready/charged/active/locked facts when
  available; drone slots and organic teleporter occupants are listed.
- `event`: non-null while a blocking popup is open, with text and indexed choices.
  Optional blue/native_type/enabled/available/disabled/locked/cost markers are included when bound.
  `native_type` is the engine's choice type; type 1 is disabled. Availability flags describe
  whether selection is allowed. `open_time` is seconds since the popup opened. `dialog_keys` describes the native
  keyboard setting: 0 disables dialog hotkeys, 1 is normal, and 2 imposes a 0.3-second opening delay.
- `store`: visible indexed buy/sell item lists and prices.
- `economy` (native protocol 5): `upgrade_available`, and `systems` keyed by original
  `system_id`, with `current_max_power`, `max_level`, `next_upgrade_cost` and `can_upgrade`.
  The optional `reactor` block has the same upgrade facts. Costs come from the native
  upgrade interface; missing costs are unknown. `can_upgrade` includes affordability,
  the level cap and current legal context. A visible cost alone does not permit a purchase.
  `fuel_recovery` contains `out_of_fuel`, `distress_on`, `can_wait` and `waiting`.

Optional fields are omitted when the native build does not expose them. Missing fields are
unknown, not fabricated zero/false values.

## Commands

```text
power <sys_id> <level>             set reactor allocation for a system
crew <crew_id> <room>              move player crew to a room
fire <slot> <enemy_room>           queue one manual shot/burst release
beam <slot> <room_a> [room_b]      queue one beam sweep between room centers
jump <beacon_index>                jump to an observed connected beacon
event <choice_index>               select an indexed blocking popup choice
leave                              cross sectors at the exit beacon
buy <i> / sell <i>                 indexed store transaction
upgrade <sys_id>                   spend scrap to raise system maximum
reactor                            buy the available native next reactor level
waitfuel                           take one native out-of-fuel recovery turn
distress <on|off>                  set the native out-of-fuel distress beacon
cloak                              activate cloaking
battery                            activate backup battery
hack <enemy_sys_id>                deploy/arm hacking at an enemy system
drone [slot] [crew]                deploy a drone; crew flag allows crew drones
dronerecall                        power down the drone system
board <enemy_room>                 teleport organic crew from the teleporter room
recall [enemy_room]                recall organic boarders
mindcontrol <enemy_room>           target an occupied enemy room
doors <open|close> [room]          set doors, including airlocks; optional room filter
giveup                             concede as unsolved; must stand alone
advance <frames>                   run time and end the paused plan
```

System IDs: 0 shields, 1 engines, 2 oxygen, 3 weapons, 4 drones, 5 medbay, 6 piloting,
7 sensors, 8 doors, 9 teleporter, 10 cloaking, 11 artillery, 12 battery, 13 clonebay,
14 mind control, 15 hacking. Passive subsystems do not accept reactor allocation.

## Execution details

Each `fire`/`beam` command queues exactly one release, including when the weapon is charging.
It returns to idle after that release; another cycle requires another command. Beam endpoints
remain distinct. `queued_fire: true` means pending; a charged weapon without a pending queue
will not fire just because time advances. Missiles/bombs consume their ammunition cost on release.

Power, crew and door settings can produce no change if already applied. Power does not repair
damage or remove fire. A non-null event blocks simulation until resolved. An uncharged FTL drive
rejects a jump; observe changed map position/sector to confirm movement. `leave` requires the
exit and a safe native transition. Rejected actuator requests do not guarantee state changes.

Upgrade commands require `capabilities.upgrade_rules`, `economy.upgrade_available`,
the item's `can_upgrade`, and its known affordable native cost. System upgrade IDs come
from `economy.systems[].system_id`; power allocation and system upgrades are distinct.
Fuel recovery requires `capabilities.fuel_recovery` and the native out-of-fuel context.
`waitfuel` takes a native recovery turn only when `can_wait` is true and `waiting` is false.
`distress on|off` sets an explicit desired beacon state in the same legal recovery context;
it is refused during a pending recovery animation or blocking transition. Ordinary frame advance (`wait`
in the CLI, or `advance` in a plan) only advances simulation; it does not request a fuel
recovery turn. Recovery has no guaranteed reward. Observe native feedback and subsequent
resource/event state before issuing another request.

Event commands use the original observed choice index. A disabled or unavailable choice cannot
be selected. The native keyboard path rejects selections with `dialog_keys: 0`, or with
`dialog_keys: 2` while `open_time` is below 0.3 seconds. Select one available choice per plan.
Applied event feedback confirms that the native selection is queued, not that its branch has
processed. Observe the returned popup and `action_feedback` to confirm the result. If the popup
remains open, it is still unresolved; use the reported reason and current event fields when
deciding the next plan.

Reply with a brief reason and an `ACTION:` block ending in `advance`, or `giveup` alone.
