"""play_cli — a thin, turn-based command line for an LLM agent to PLAY FTL.

Each invocation performs ONE action through the standard harness interface and prints a
compact JSON state for the agent to reason over. State lives in the running game (not this
process), so every call re-attaches to the live episode — perfect for an agent that thinks
between turns.

Usage (run from repo root):
  cd harness && uv run python ../adapter/play_cli.py <command> [args...]

Commands:
  reset <seed>            start a fresh seeded run (abandons the current one)
  obs                     just look (no action)
  power <sys_id> <level>  set a system's power (weapons=3, shields=0, engines=1, oxygen=2)
  fire <slot> <room>      fire weapon `slot` at enemy `room` (autofires until it dies/flees)
  jump <beacon_index>     jump to a connected beacon
  event <choice_index>    pick an event/dialog choice (resolve a popup)
  leave                   leave the sector from the exit beacon
  wait [frames]           let time pass (default 150 frames) — charge weapons, watch combat
  crew <crew_id> <room>   move a crew member to a room
  buy <index>             at a store: buy `store.buy[index]` (weapon/drone/system/fuel/...)
  sell <index>            at a store: sell `store.sell[index]` (your inventory) for scrap
  upgrade <sys_id>        spend scrap to raise a system's MAX power +1 (anytime; e.g.
                          `upgrade 0` = a 2nd shield layer). Needs enough scrap.

Special-system actions (each needs the system installed — buy at a store — and powered):
  cloak                   engage cloaking (id 10): evasion + untargetable for a timer
  doors <open|close> [room]  open/close doors to vent oxygen (fight fires / suffocate boarders)
  mindcontrol <enemy_room>   mind-control an enemy crew member (id 14)
  battery                 backup battery (id 12): temporary extra reactor power
  beam <slot> <room_a> [room_b]   fire a BEAM weapon, sweeping room_a->room_b across the hull
  hack <enemy_sys_id>     deploy+arm the hacking drone on an enemy system (id 15)
  drone [slot] [crew]     deploy a drone slot (id 4); space drones only unless `crew` is passed
  dronerecall             power the drone system down (recall space drones)
  board <enemy_room>      teleport organic boarders into an enemy room (id 9; -1 = random)
  recall [enemy_room]     bring boarders home (id 9; -1 auto-resolves the room they're in)
  screenshot [path]       capture the live FTL window to a PNG and print the path (vision aid)

System ids: 0 shields, 1 engines, 2 oxygen, 3 weapons, 4 drones, 5 medbay, 6 piloting,
            7 sensors, 8 doors, 9 teleporter, 10 cloaking, 12 battery, 14 mind, 15 hacking.
            Fire needs weapons (3) powered; a 2-power weapon needs 2 FREE reactor bars at
            once (lower another system first if reactor is full).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "harness" / "src"))

from ftl_bench import (  # noqa: E402
    AgentSession, set_system_power, move_crew, store_buy, store_sell, upgrade_system,
    cloak, set_doors, mind_control, battery, fire_beam, hack_system, deploy_drone,
    recall_drones, teleport_crew, fire_weapon, jump, choose_event, leave_sector,
)
from capture import capture_ftl  # noqa: E402  (adapter/ is on sys.path as cwd-adjacent)

SYS_NAMES = {0: "shields", 1: "engines", 2: "oxygen", 3: "weapons", 4: "drones",
             5: "medbay", 6: "piloting", 7: "sensors", 8: "doors", 9: "teleporter",
             10: "cloaking", 11: "artillery", 12: "battery", 13: "clonebay",
             14: "mind", 15: "hacking"}


def _pair(d, a="current", b="max"):
    if not isinstance(d, dict):
        return None
    return f"{d.get(a)}/{d.get(b)}"


def compact(o) -> dict:
    """A token-lean but decision-complete snapshot of the game."""
    ps = o.player_ship or {}
    res = ps.get("resources") or {}
    st = {
        "game_started": o.game_started,
        # game_over: the run ended (crew death / ship lost). This is NOT a crash and NOT
        # always hull<=0, so it's the only reliable "the episode is over" signal — without it
        # an agent spins no-op actions at the GAME OVER screen instead of stopping/resetting.
        **({"game_status": "GAME_OVER",
            "hint": "the run is over (crew dead / ship lost) — reset to a new game to continue"}
           if (o.raw or {}).get("game_over") else {}),
        "paused": o.paused,
        "sector": (o.map or {}).get("sector"),
        "hull": _pair(ps.get("hull")),
        "oxygen_pct": ps.get("oxygen_pct"),
        "fuel": res.get("fuel"),
        "missiles": res.get("missiles"),
        "scrap": res.get("scrap"),
        # reactor_free = bars available to assign right now; reactor_total = your reactor
        # size. To power a system you need (req_power) <= reactor_free — otherwise lower
        # another system first. (Was an ambiguous "free/total" string a real agent misread.)
        # BUT during an ion/plasma storm (or ion/hack on the reactor) the engine CAPS usable
        # power and these raw bars LIE — prefer reactor_usable_free, the honest GetMaxPower()
        # cap. reactor_power_penalty = bars stolen by the hazard (0 when none).
        "reactor_free": (ps.get("reactor") or {}).get("available"),
        "reactor_total": (ps.get("reactor") or {}).get("total"),
        "reactor_usable_total": (ps.get("reactor") or {}).get("usable_total"),
        "reactor_usable_free": (ps.get("reactor") or {}).get("usable_available"),
        "reactor_power_penalty": (ps.get("reactor") or {}).get("power_penalty"),
        # evasion (dodge %): chance an incoming shot MISSES this ship, from powered/manned
        # engines + piloting + cloak. High = shots whiff; raise engines/cloak to dodge more.
        "evasion": ps.get("evasion"),
        "crew_count": len(ps.get("crew", []) or []),
        # FTL's own run score (the game's native scoring: scrap, kills, sectors, flagship x
        # difficulty). The benchmark's headline metric for full games; absent until in a run.
        **({"ftl_score": (o.raw or {}).get("ftl_score")}
           if (o.raw or {}).get("ftl_score") is not None else {}),
    }
    # A destroyed ship leaves hull<=0 for the frames before FTL's formal GAME OVER screen
    # flips `game_over`; that window read as a live-but-stuck state to a real agent. Treat
    # hull<=0 as terminal so the episode is unambiguously over.
    _h = ps.get("hull") or {}
    if isinstance(_h, dict) and isinstance(_h.get("current"), (int, float)) and _h["current"] <= 0:
        st.setdefault("game_status", "DESTROYED")
        st.setdefault("hint", "player hull <= 0 — ship destroyed, run is over; reset to a new game")
    # interrupted_by: the hybrid pause ended your last advance EARLY because a crisis developed
    # mid-action (combat_started / took_damage / boarder_aboard / fire / event) — react now.
    if (o.raw or {}).get("interrupted_by"):
        st["interrupted_by"] = o.raw["interrupted_by"]
    # rooms currently on fire — a system in a burning room is being damaged and can't function
    # properly until the fire is out, no matter how much power it has. Surfaced per-system as
    # `on_fire` so a BROKEN module (needs crew repair) is distinguishable from a merely UNPOWERED
    # one (needs power).
    _burning = {f.get("room_id") for f in (ps.get("fires") or [])}
    st["systems"] = [
        {"id": s.get("id"), "name": SYS_NAMES.get(s.get("id"), str(s.get("id"))),
         "power": f"{s.get('power')}/{s.get('power_max')}",
         # room: where to send a crew member (`crew <id> <room>`) to repair/extinguish this system.
         **({"room": s.get("room_id")} if s.get("room_id") is not None else {}),
         # damage>0 = the module is BROKEN (reduced/zero function); on_fire = its room is burning.
         # Either way it needs a crew member in its room to REPAIR/EXTINGUISH — power will NOT fix it.
         **({"damage": s.get("damage")} if s.get("damage") else {}),
         **({"on_fire": True} if s.get("room_id") in _burning else {}),
         **({"ion": s.get("ion")} if s.get("ion") else {})}
        for s in ps.get("systems", []) if s.get("power_max")
    ]
    # Crew management: move a crew member with `crew <id> <room>` to REPAIR a damaged system
    # (send to its room), FIGHT an intruder (send to intruders[].room), or EXTINGUISH a fire.
    st["crew"] = [
        {"id": c.get("id"), "room": c.get("room"), "species": c.get("species"),
         "hp": f"{c.get('health_current')}/{c.get('health_max')}",
         **({"busy": "repair"} if c.get("repairing") else {}),
         **({"busy": "fight"} if c.get("fighting") else {}),
         **({"boarding": True} if c.get("on_enemy_ship") else {})}
        for c in ps.get("crew", []) if not c.get("dead")
    ]
    # intruders = enemy boarders aboard YOUR ship (send crew to .room to fight); fires = burning
    # rooms (send crew to extinguish). Both empty when none.
    if ps.get("intruders"):
        st["intruders"] = ps["intruders"]
    if ps.get("fires"):
        st["fires"] = ps["fires"]
    st["weapons"] = [
        {"slot": w.get("slot"), "powered": w.get("powered"),
         # type: MISSILES pierce shields (cost a missile); BEAM sweeps rooms (use `beam`,
         # blocked by shields equal to its damage); LASER/BURST bolts are each stopped by one
         # shield layer. is_beam flags which slot the `beam` command targets. A real agent had
         # to GUESS weapon identity from side effects — this was in the obs but dropped here.
         "type": w.get("weapon_type"), "is_beam": w.get("is_beam"),
         # DAMAGE PROFILE: dmg = hull damage per shot; pierces = shield layers ignored.
         # eff_pierce: does it effectively bypass shields? MISSILES/BOMB always do (missiles
         # ignore shields; bombs teleport past them) even when pierces reads 0.
         "dmg": w.get("damage"), "pierces": w.get("shield_piercing"),
         "eff_pierce": bool((w.get("shield_piercing") or 0) > 0
                            or w.get("weapon_type") in ("MISSILES", "BOMB")),
         **({"fire": w.get("fire_chance")} if w.get("fire_chance") else {}),
         **({"ion": w.get("ion_damage")} if w.get("ion_damage") else {}),
         # ready_to_fire: charged enough to release a volley THIS turn (clearer than the
         # raw `charge` float, which keeps climbing past the threshold). Autofire keeps the
         # weapon firing once targeted, so you don't need to re-`fire` every cycle.
         "ready_to_fire": bool(w.get("powered")
                               and (w.get("charge") or 0) >= (w.get("charge_max") or w.get("base_cooldown") or 1e9)),
         # targeted: armed + autofiring at a target. A powered weapon with targeted:false NEVER
         # fires no matter how long you wait — `fire <slot> <enemy_room>` to target it. Reads
         # autoFiring (reliable; set by the fire path) — NOT currentShipTarget, which the fire
         # path leaves nil so it false-flickered and induced fire-spam. Once targeted, just wait.
         "targeted": bool(w.get("autofiring") or w.get("has_target")),
         "charge": round(w.get("charge") or 0, 1),
         "charge_max": round(w.get("charge_max") or w.get("base_cooldown") or 0, 1),
         "req_power": w.get("required_power"),
         "shots": w.get("num_shots"), "targets_req": w.get("targets_required"),
         "n_targets": w.get("n_targets"), "fire_when_ready": w.get("fire_when_ready")}
        for w in ps.get("weapons", [])
    ]
    # incoming_fire = shots currently inbound at YOU (space.projectiles with targetId==0). This
    # counts ENEMY DRONE fire too: a combat drone is NOT in enemy.weapons, so a ship whose guns
    # are depowered can still be shooting you via a drone. Surfacing it (and folding it into
    # enemy.active below) stops the agent misreading a drone-armed enemy as "surrendered/inactive".
    _incoming = (o.raw or {}).get("incoming_projectiles") or 0
    if _incoming:
        st["incoming_fire"] = _incoming
    if o.enemy_ship:
        en = o.enemy_ship
        sh = en.get("shields") or {}
        # enemy "active" = still a LIVE THREAT: weapons powered OR something still inbound at you
        # (incoming_fire > 0, e.g. a combat drone). A truly forfeit enemy depowers its guns AND
        # stops firing; depowered guns alone is NOT enough — a drone keeps attacking after the
        # ship's weapons are gone, and reading that as "inactive" makes the agent stop defending.
        _ew = en.get("weapons") or []
        _wsys = next((s for s in (en.get("systems") or []) if s.get("id") == 3), None)
        # deployed enemy drones fly + attack independently of the ship's weapons, so a ship
        # with depowered guns is still a live threat if it has a drone out.
        _edrones = [d for d in (en.get("drones") or []) if d.get("deployed")]
        _enemy_active = bool((_wsys and (_wsys.get("power") or 0) > 0)
                             or any(w.get("powered") for w in _ew)
                             or _incoming > 0
                             or _edrones)
        st["enemy"] = {
            "hull": _pair(en.get("hull")),
            "shields": f"{sh.get('layers')}L charger={sh.get('charger')}" if sh else None,
            # still a LIVE THREAT (weapons powered, or incoming_fire>0 e.g. a drone) vs forfeit
            # (guns depowered AND nothing inbound). Don't stop defending just because guns are off.
            "active": _enemy_active,
            # enemy DEPLOYED drones (flying around): combat/beam drones damage your hull, defense
            # drones shoot down your missiles/drones -- all INDEPENDENT of enemy.weapons. type is
            # the drone's name (e.g. "Combat Drone Mark I"); firing = powered + deployed + alive.
            **({"drones": [{"type": (d.get("name")
                                     or {0: "defense", 1: "combat", 7: "shield"}.get(d.get("type"), d.get("type"))),
                            "firing": bool(d.get("firing"))} for d in _edrones]}
               if _edrones else {}),
            # targetable = you can actually aim a weapon at it now (false once it's warping out
            # or gone — firing then hits NOTHING, the agent's equivalent of "no targeting cursor").
            "targetable": en.get("targetable"),
            # fleeing = it has forfeit and is charging its FTL drive to escape (jump_charge_pct).
            **({"fleeing": True} if en.get("fleeing") else {}),
            **({"jump_charge_pct": round(en.get("jump_charge_pct"), 2)}
               if en.get("jump_charge_pct") else {}),
            # enemy evasion (dodge %): how often OUR shots miss them. High = beams/lasers/missiles
            # whiff — disable their engines (hack/ion/board) or expect misses before spending
            # limited missiles. This is why a run can waste missiles on an evasive auto-ship.
            "evasion": en.get("evasion"),
            "rooms": [{"room_id": r.get("room_id"),
                       "system": SYS_NAMES.get(r.get("system_id"), r.get("system_id"))}
                      for r in en.get("rooms", []) if r.get("system_id") is not None],
            # The incoming threat: each enemy weapon's TYPE + DAMAGE PROFILE + how close to firing.
            # type: MISSILES/BOMB bypass shields, BEAM sweeps, LASER/BURST are shield-blocked;
            # dmg/pierces/fire/ion say HOW bad a hit is; about_to_fire = charged this turn. A real
            # agent flew blind into a shield-piercer + fire-bomb because this was never surfaced.
            "weapons": [
                {"slot": w.get("slot"), "powered": w.get("powered"),
                 "type": w.get("weapon_type"), "is_beam": w.get("is_beam"),
                 "dmg": w.get("damage"), "pierces": w.get("shield_piercing"),
                 "eff_pierce": bool((w.get("shield_piercing") or 0) > 0
                                    or w.get("weapon_type") in ("MISSILES", "BOMB")),
                 **({"fire": w.get("fire_chance")} if w.get("fire_chance") else {}),
                 **({"ion": w.get("ion_damage")} if w.get("ion_damage") else {}),
                 "shots": w.get("num_shots"),
                 "charge": round(w.get("charge") or 0, 1),
                 "charge_max": round(w.get("charge_max") or w.get("base_cooldown") or 0, 1),
                 "about_to_fire": bool(w.get("powered")
                                       and (w.get("charge") or 0) >= (w.get("charge_max") or w.get("base_cooldown") or 1e9))}
                for w in (en.get("weapons") or [])
            ],
            # Which enemy systems are powered (e.g. is their cloak/shields/weapons up). Lets the
            # agent pick a disable target (fire/hack/board their weapons or shields room).
            "systems": [
                {"id": s.get("id"), "name": SYS_NAMES.get(s.get("id"), s.get("id")),
                 "power": f"{s.get('power')}/{s.get('power_max')}",
                 **({"damage": s.get("damage")} if s.get("damage") else {})}
                for s in (en.get("systems") or []) if s.get("power_max")
            ],
        }
    else:
        st["enemy"] = None
    # shots: OUR weapons' effectiveness THIS combat — fired / hit / shields_blocked / missed
    # (+ a recent-outcomes log). missed running high means the enemy is DODGING (evasion): target
    # its engines/piloting to cut evasion, or flee — don't keep dumping ammo. In-combat only.
    _shots = ps.get("shots")
    if _shots:
        st["shots"] = _shots
    m = o.map or {}
    # Navigation toward the exit beacon (the PRIMARY scored goal) needs POSITIONS — the obs
    # has them (map.exit_pos, map.current_pos, per-beacon pos_x/pos_y) but compact() dropped
    # them, so a real agent saw only `exit:false` booleans (the exit is rarely adjacent) and
    # could not steer toward it. Surface positions + a derived dist_to_exit per beacon (the
    # data; the agent decides which to take). Note `index` re-maps each jump (it's the slot in
    # the connected list) — use pos_x/pos_y as the stable reference, not index.
    _exit = m.get("exit_pos") or {}
    _ex, _ey = _exit.get("x"), _exit.get("y")

    def _dist_to_exit(bx, by):
        if None in (bx, by, _ex, _ey):
            return None
        return round(((bx - _ex) ** 2 + (by - _ey) ** 2) ** 0.5)

    st["map"] = {
        "at_exit": m.get("at_exit"),
        "jump_charged": o.raw.get("jump_charged") if o.raw else None,
        # jump_charge_pct/jump_charge: FTL-drive recharge in [0,1] + raw {current,max} seconds.
        # Meaningful as a progress bar IN COMBAT only; out of combat it reads ~0.0 while jumps are
        # still free. Authority on "can I jump now" remains jump_charged; None = unknown/mid-warp.
        "jump_charge_pct": o.raw.get("jump_charge_pct") if o.raw else None,
        "jump_charge": o.raw.get("jump_charge") if o.raw else None,
        # hazard: environmental hazard at this beacon — none | nebula | ion_storm (caps usable
        # reactor: trust reactor_usable_free, NOT reactor_free) | sun | pulsar | asteroids.
        # pds = an anti-ship defense turret is firing (independent of the hazard above).
        "hazard": m.get("hazard"),
        "pds": m.get("pds"),
        "current_pos": m.get("current_pos"),
        "exit_pos": m.get("exit_pos"),
        "beacons": [{"index": b.get("index"), "visited": b.get("visited"),
                     "exit": b.get("exit_beacon"), "fleet": b.get("fleet"),
                     "quest": b.get("quest"),
                     "pos": [b.get("pos_x"), b.get("pos_y")],
                     "dist_to_exit": _dist_to_exit(b.get("pos_x"), b.get("pos_y"))}
                    for b in m.get("connected_beacons", [])],
    }
    if o.choice_box_open and (o.event or {}).get("choices"):
        st["event"] = {
            "text": (o.event.get("text") or "").replace("\n", " ")[:300],
            "choices": [c.get("text") for c in o.event["choices"]],
        }
    else:
        st["event"] = None
    # store inventory when standing on a store beacon (else null). `buy <i>` / `sell <i>`
    # act on these indices; `upgrade <sys_id>` raises a system's max power (anytime).
    store = (o.raw or {}).get("store")
    st["store"] = store if store else None
    return st


def apply_command(s: AgentSession, cmd: str, args: list[str]):
    """Dispatch ONE play_cli command through the session and return the resulting Observation.

    Shared by the CLI (`main`) and the LLM agent track (`llm_agent.py`) so both drive the
    EXACT same action semantics (per-action frame budgets included). Raises ValueError on an
    unknown command. `screenshot` is CLI-only (it writes a PNG, not an Observation) and is
    handled in `main`, not here.
    """
    if cmd == "reset":
        return s.reset_episode(seed=int(args[0]) if args else None)
    elif cmd == "start":
        return s.start_game("new", seed=int(args[0]) if args else None, timeout=90.0)
    elif cmd == "obs":
        return s.observe()
    elif cmd == "power":
        return s.step([set_system_power(int(args[0]), int(args[1]))], advance_frames=20)
    elif cmd == "fire":
        return s.fire_weapon(int(args[0]), int(args[1]), advance_frames=int(args[2]) if len(args) > 2 else 150)
    elif cmd == "jump":
        return s.jump(int(args[0]), advance_frames=int(args[1]) if len(args) > 1 else 260)
    elif cmd == "event":
        return s.choose_event(int(args[0]), advance_frames=int(args[1]) if len(args) > 1 else 90)
    elif cmd == "leave":
        return s.leave_sector()
    elif cmd == "wait":
        return s.step([], advance_frames=int(args[0]) if args else 150)
    elif cmd == "crew":
        return s.step([move_crew(int(args[0]), int(args[1]))], advance_frames=30)
    elif cmd == "buy":
        return s.step([store_buy(int(args[0]))], advance_frames=30)
    elif cmd == "sell":
        return s.step([store_sell(int(args[0]))], advance_frames=30)
    elif cmd == "upgrade":
        return s.step([upgrade_system(int(args[0]))], advance_frames=20)
    elif cmd == "cloak":
        return s.step([cloak()], advance_frames=120)
    elif cmd == "doors":      # doors <open|close> [room_id]
        return s.step([set_doors(args[0] == "open",
                                 room_id=int(args[1]) if len(args) > 1 else None,
                                 include_airlocks=True)], advance_frames=60)
    elif cmd == "mindcontrol":  # mindcontrol <enemy_room_id>
        return s.step([mind_control(int(args[0]))], advance_frames=90)
    elif cmd == "battery":      # backup battery: temp reactor power (id 12)
        return s.step([battery()], advance_frames=60)
    elif cmd == "beam":         # beam <slot> <room_a> [room_b] [frames]
        _ra = int(args[1])
        _rb = int(args[2]) if len(args) > 2 else _ra
        return s.fire_beam(int(args[0]), _ra, _rb,
                           advance_frames=int(args[3]) if len(args) > 3 else 150)
    elif cmd == "hack":         # hack <enemy_system_id>  (0=shields,3=weapons,...)
        return s.hack_system(int(args[0]) if args else 0)
    elif cmd == "drone":        # drone [slot] [crew]
        _slot = int(args[0]) if args else None
        _allow = (len(args) > 1 and args[1] in ("1", "crew", "allowcrew", "true"))
        return s.step([deploy_drone(slot=_slot, allow_crew_drone=_allow)], advance_frames=120)
    elif cmd == "dronerecall":  # power the drone system down (recall space drones)
        return s.step([recall_drones()], advance_frames=30)
    elif cmd == "board":        # board <enemy_room_id>  (send organic boarders; -1 random)
        return s.step([teleport_crew(1, int(args[0]) if args else -1)], advance_frames=120)
    elif cmd == "recall":       # recall [enemy_room_id]  (bring boarders home; -1 auto-resolves)
        return s.step([teleport_crew(2, int(args[0]) if args else -1)], advance_frames=120)
    raise ValueError(f"unknown command {cmd!r}")


def command_to_action(cmd: str, args: list[str]) -> dict | None:
    """Convert ONE play_cli command into its env action dict WITHOUT dispatching it — so several
    commands can be batched into a single `sess.step([...], advance_frames=N)` (the multi-action
    'plan' turn). Mirrors apply_command's per-command mapping exactly; the bridge's dispatch_actions
    applies each act.type, so a batched list behaves like issuing them in order while paused. Returns
    None for `wait` (a pure time-advance, no action). Raises ValueError on an unknown verb."""
    if cmd == "wait":
        return None
    if cmd == "power":
        return set_system_power(int(args[0]), int(args[1]))
    if cmd == "fire":
        return fire_weapon(int(args[0]), int(args[1]))
    if cmd == "jump":
        return jump(int(args[0]))
    if cmd == "event":
        return choose_event(int(args[0]))
    if cmd == "leave":
        return leave_sector()
    if cmd == "crew":
        return move_crew(int(args[0]), int(args[1]))
    if cmd == "buy":
        return store_buy(int(args[0]))
    if cmd == "sell":
        return store_sell(int(args[0]))
    if cmd == "upgrade":
        return upgrade_system(int(args[0]))
    if cmd == "cloak":
        return cloak()
    if cmd == "doors":
        return set_doors(args[0] == "open",
                         room_id=int(args[1]) if len(args) > 1 else None,
                         include_airlocks=True)
    if cmd == "mindcontrol":
        return mind_control(int(args[0]))
    if cmd == "battery":
        return battery()
    if cmd == "beam":
        _ra = int(args[1])
        _rb = int(args[2]) if len(args) > 2 else _ra
        return fire_beam(int(args[0]), _ra, _rb)
    if cmd == "hack":
        return hack_system(int(args[0]) if args else 0)
    if cmd == "drone":
        _slot = int(args[0]) if args else None
        _allow = (len(args) > 1 and args[1] in ("1", "crew", "allowcrew", "true"))
        return deploy_drone(slot=_slot, allow_crew_drone=_allow)
    if cmd == "dronerecall":
        return recall_drones()
    if cmd == "board":
        return teleport_crew(1, int(args[0]) if args else -1)
    if cmd == "recall":
        return teleport_crew(2, int(args[0]) if args else -1)
    raise ValueError(f"unknown command {cmd!r}")


def _ftl_alive() -> bool:
    """Is the FTL game process running? Platform-aware: on Windows — native Python (os.name ==
    'nt') or WSL pointing at a /mnt drive — check the native FTLGame.exe via tasklist; macOS uses
    pgrep on the app binary. The old macOS-only pgrep falsely reported FROZEN_KILLED on Windows
    (it can't see a Windows process), mislabeling a perfectly live game."""
    import os
    import subprocess
    native_win = os.name == "nt"
    wsl_win = os.environ.get("FTL_SAVE_DIR", "").startswith("/mnt/")
    if native_win or wsl_win:
        tasklist = "tasklist" if native_win else "/mnt/c/Windows/System32/tasklist.exe"
        try:
            r = subprocess.run([tasklist, "/fi", "imagename eq FTLGame.exe"],
                               capture_output=True, text=True)
            return "FTLGame.exe" in r.stdout
        except Exception:  # noqa: BLE001
            return True  # can't tell -> don't cry freeze
    r = subprocess.run(["pgrep", "-f", "FTL Faster Than Light/FTL.app/Contents/MacOS/FTL"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no command", "usage": __doc__.splitlines()[0]}))
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]
    s = AgentSession()
    try:
        if cmd == "screenshot":   # CLI-only: writes a PNG, not an Observation
            dest = args[0] if args else str(REPO / "ftl_screenshot.png")
            print(json.dumps(capture_ftl(dest), indent=2))
            return
        # capture the pre-leave sector so we can report whether `leave` actually committed
        _bsec = (s.observe().map or {}).get("sector") if cmd == "leave" else None
        # capture a system's pre-action power so we can tell the agent when a `power` command had
        # NO EFFECT (the system was already at that level) — the no-op that drives power-spam loops.
        _prepow = None
        if cmd == "power" and len(args) >= 2:
            try:
                _ps = next((sy for sy in (s.observe().player_ship or {}).get("systems", [])
                            if sy.get("id") == int(args[0])), None)
                _prepow = _ps.get("power") if _ps else None
            except Exception:  # noqa: BLE001
                pass
        o = apply_command(s, cmd, args)
        out = compact(o)
        # Power-command feedback: a real agent repeatedly hit `power` silently not taking
        # effect (a damaged/ion'd system, or not enough free reactor) with NO explanation —
        # and lost the run fighting with an unpowered main weapon. Say why it didn't apply.
        if cmd == "power" and len(args) >= 2:
            try:
                _sid, _lvl = int(args[0]), int(args[1])
                _sys = next((s for s in (o.player_ship or {}).get("systems", [])
                             if s.get("id") == _sid), None)
                _cur = _sys.get("power") if _sys else None
                if _sys is not None and isinstance(_cur, int):
                    _pmax = _sys.get("power_max")
                    if _prepow == _cur and _cur >= _lvl:
                        # already at (or above) the requested level -> this command changed nothing
                        out["power_result"] = {
                            "system": SYS_NAMES.get(_sid, _sid), "requested": _lvl, "actual": _cur,
                            "reason": f"NO EFFECT — {SYS_NAMES.get(_sid, _sid)} was already at "
                                      f"{_cur}/{_pmax}. Setting a system to a power level it already "
                                      f"holds does nothing; re-issuing won't help — do something else."}
                    elif _cur < _lvl:
                        _dmg, _ion = _sys.get("damage") or 0, _sys.get("ion") or 0
                        _free = ((o.player_ship or {}).get("reactor") or {}).get("available")
                        if _dmg:
                            _why = f"system damaged — usable max is {(_pmax or 0) - _dmg} of {_pmax} until repaired"
                        elif _ion:
                            _why = "system is ion-locked (wait for ion to clear)"
                        elif isinstance(_free, int) and _free <= 0:
                            _why = "no free reactor bars — lower another system first, then retry"
                        else:
                            _why = "did not reach requested level (check reactor_free, damage, ion)"
                        out["power_result"] = {"system": SYS_NAMES.get(_sid, _sid),
                                               "requested": _lvl, "actual": _cur, "reason": _why}
            except Exception:  # noqa: BLE001 — feedback is best-effort, never break the action
                pass
        # leave_result: `leave` used to silently no-op when the sector transition didn't
        # commit within one advance — a correct action indistinguishable from a broken one.
        # session.leave_sector now pumps to commit; report committed / refused / pending so
        # the agent never has to guess whether its leave worked.
        if cmd == "leave":
            _asec = (o.map or {}).get("sector")
            if _bsec is not None and _asec is not None and _asec > _bsec:
                out["leave_result"] = f"committed — crossed into sector {_asec}"
            elif o.enemy_ship is not None:
                out["leave_result"] = "refused: enemy present — clear/kill it, then leave"
            elif not (o.map or {}).get("at_exit"):
                out["leave_result"] = "refused: not at the exit beacon — jump to the beacon with exit:true first"
            elif (o.raw or {}).get("jump_charged") is False:
                out["leave_result"] = "pending: FTL drive still charging — wait, then leave again"
            else:
                out["leave_result"] = "pending: transition did not commit — call leave again"
        # `obs` reads the last-written snapshot from disk, which is NOT refreshed once the
        # engine freezes and the watchdog SIGKILLs FTL — so a stale-but-valid-looking obs
        # could mislead the agent into thinking the game is live. Flag a dead process.
        if cmd == "obs":
            if not _ftl_alive():
                out["game_status"] = "FROZEN_KILLED"
                out["hint"] = "FTL is not running (froze and was killed); this snapshot is stale — the episode is over"
        print(json.dumps(out, indent=2))
    except Exception as e:  # noqa: BLE001
        out = {"error": f"{type(e).__name__}: {e}", "command": cmd, "args": args}
        # Distinguish a hard engine FREEZE from a transient hiccup: if the FTL process is
        # gone (the freeze watchdog SIGKILLs a spinning game) or unresponsive, say so
        # plainly so the caller restarts the episode instead of retrying a dead game.
        alive = _ftl_alive()
        if isinstance(e, TimeoutError):
            out["game_status"] = "ALIVE_BUT_UNRESPONSIVE" if alive else "FROZEN_KILLED"
            out["hint"] = ("the FTL engine hard-froze and the watchdog killed it; this "
                           "episode is over — restart with `start <seed>` after relaunch"
                           if not alive else
                           "the game did not ack in time; it may be mid-animation — retry, "
                           "or it may be freezing (check again)")
        print(json.dumps(out))


if __name__ == "__main__":
    main()
