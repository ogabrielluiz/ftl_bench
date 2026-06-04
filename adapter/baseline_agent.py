"""ftl_bench baseline agent — a simple scripted heuristic player (no LLM).

Plays a handful of jumps: powers shields/weapons/engines, resolves events by
picking a choice, and fights enemies by targeting their weapons room and firing
until they're destroyed. Useful as an end-to-end smoke test and a scoring baseline.

Run:  cd harness && uv run python ../adapter/baseline_agent.py --jumps 5 [--new]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness" / "src"))

from ftl_bench import AgentSession, set_system_power  # noqa: E402

# system ids
SHIELDS, ENGINES, OXYGEN, WEAPONS = 0, 1, 2, 3


def systems(o):
    return {s["id"]: s for s in (o.player_ship or {}).get("systems", [])}


def enemy_hull(o):
    return (o.enemy_ship or {}).get("hull", {}).get("current")


def player_hull(o):
    return (o.player_ship or {}).get("hull", {}).get("current")


def power_core(sess, o):
    """Allocate power to shields, then weapons, then engines (best-effort)."""
    sys = systems(o)
    for sid in (SHIELDS, WEAPONS, ENGINES):
        s = sys.get(sid)
        if s and s.get("power_max"):
            o = sess.step([set_system_power(sid, s["power_max"])], advance_frames=15)
    return o


def fight(sess, o, log):
    """Target the enemy's weapons room (or room 0) and fire until it's destroyed
    or we take too much damage."""
    o = power_core(sess, o)
    rooms = (o.enemy_ship or {}).get("rooms", [])
    # prefer the enemy weapons room, else shields, else first room
    target = None
    for want in (WEAPONS, SHIELDS):
        target = next((r["room_id"] for r in rooms if r.get("system_id") == want), None)
        if target is not None:
            break
    if target is None and rooms:
        target = rooms[0]["room_id"]
    if target is None:
        return o
    log(f"  combat: target enemy room {target}, enemy hull {enemy_hull(o)}")
    # aim each powered weapon at the room (persistent target + autofire)
    for w in (o.player_ship or {}).get("weapons", []):
        if w.get("powered"):
            o = sess.fire_weapon(w["slot"], target, advance_frames=30)
    # let it play out
    for _ in range(20):
        if not o.enemy_ship or (enemy_hull(o) or 0) <= 0:
            log(f"  enemy destroyed (player hull {player_hull(o)})")
            return o
        if (player_hull(o) or 0) <= 6:
            log(f"  hull critical ({player_hull(o)}) — disengaging")
            return o
        o = sess.step([], advance_frames=200)
        log(f"    ...enemy hull {enemy_hull(o)}, player hull {player_hull(o)}")
    return o


def play(sess, jumps, log):
    o = sess.observe()
    if not o.game_started:
        log("not in a run; resetting")
        o = sess.start_game("continue")
    stats = {"jumps": 0, "events": 0, "combats": 0, "kills": 0}
    o = power_core(sess, o)

    for _ in range(jumps):
        o = sess.observe()
        if o.choice_box_open and (o.event or {}).get("choices"):
            choices = o.event["choices"]
            txt = (o.event.get("text") or "").replace("\n", " ")[:70]
            log(f"event: {txt!r} -> choosing 0/{len(choices)}")
            o = sess.choose_event(0, advance_frames=90)
            stats["events"] += 1
            continue
        if o.enemy_ship and (enemy_hull(o) or 0) > 0:
            o = fight(sess, o, log)
            stats["combats"] += 1
            eh = enemy_hull(o)
            if not o.enemy_ship or (eh is not None and eh <= 0):
                stats["kills"] += 1
            continue
        beacons = (o.map or {}).get("connected_beacons", [])
        if not beacons:
            log("no beacons to jump to; stopping")
            break
        tgt = next((b["index"] for b in beacons if b.get("visited") == 0),
                   beacons[0]["index"])
        log(f"jump -> beacon {tgt} (fuel {(o.player_ship or {}).get('resources',{}).get('fuel')})")
        try:
            o = sess.jump(tgt, advance_frames=260)
            stats["jumps"] += 1
        except Exception as e:  # noqa: BLE001
            log(f"jump failed: {e}; stopping")
            break

    o = sess.observe()
    log(f"\n== run summary == hull {player_hull(o)}/30  "
        f"sector {(o.map or {}).get('sector')}  {stats}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jumps", type=int, default=5)
    ap.add_argument("--new", action="store_true", help="start a fresh run first")
    args = ap.parse_args()
    sess = AgentSession()
    if args.new:
        sess.start_game("new")

    def log(msg):
        print(msg, flush=True)

    play(sess, args.jumps, log)


if __name__ == "__main__":
    main()
