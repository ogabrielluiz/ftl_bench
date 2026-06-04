"""ftl_bench baseline agent — a simple scripted heuristic player (no LLM).

Plays a handful of jumps: powers shields/weapons/engines, resolves events by
picking a choice, and fights enemies by targeting their weapons room and firing
until they're destroyed. Useful as an end-to-end smoke test and a scoring baseline.

Run:  cd harness && uv run python ../adapter/baseline_agent.py --jumps 5 [--new]
"""
from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness" / "src"))

from ftl_bench import (  # noqa: E402
    AgentSession,
    TrajectoryRecorder,
    load_trajectory,
    score_trajectory,
    set_system_power,
)

# system ids
SHIELDS, ENGINES, OXYGEN, WEAPONS = 0, 1, 2, 3


def systems(o):
    return {s["id"]: s for s in (o.player_ship or {}).get("systems", [])}


def enemy_hull(o):
    return (o.enemy_ship or {}).get("hull", {}).get("current")


def player_hull(o):
    return (o.player_ship or {}).get("hull", {}).get("current")


def player_oxygen(o):
    return (o.player_ship or {}).get("oxygen_pct")


def operational_weapons(o):
    """Player weapons that are powered (can actually deal damage)."""
    return [w for w in (o.player_ship or {}).get("weapons", []) if w.get("powered")]


def min_crew_health(o):
    alive = [c for c in (o.player_ship or {}).get("crew", []) if not c.get("dead")]
    hp = [c.get("health_current", 100) for c in alive]
    return min(hp) if hp else 0


def flee_reason(o, hull_floor):
    """Why we should bail out of this fight, or None to keep fighting. Watches more
    than hull: a destroyed oxygen system suffocates a full-hull ship, and a fight you
    can't deal damage in is unwinnable (the seed-7 death: hull 21, O2 gone, no weapons)."""
    hull = player_hull(o) or 0
    if hull <= hull_floor:
        return f"hull {hull}"
    o2 = player_oxygen(o)
    if o2 is not None and o2 <= 25:
        return f"oxygen {o2}%"
    if min_crew_health(o) <= 25:
        return f"crew health {min_crew_health(o):.0f}"
    return None


def power_core(sess, o):
    """Allocate power to shields, then weapons, then engines (best-effort).
    Skips silently if an action ack lags (don't crash the run on a transient)."""
    sys = systems(o)
    for sid in (SHIELDS, WEAPONS, ENGINES):
        s = sys.get(sid)
        if s and s.get("power_max"):
            try:
                o = sess.step([set_system_power(sid, s["power_max"])], advance_frames=15)
            except TimeoutError:
                pass
    return o


def _flee(sess, o, log):
    """Jump away from combat, heading toward the sector exit (FTL flee)."""
    tgt = _pick_beacon(o)
    if tgt is None:
        return o, "stuck"
    try:
        o = sess.jump(tgt, advance_frames=260)
        log(f"  fled to beacon {tgt} (hull {player_hull(o)})")
        return o, "flee"
    except Exception:  # noqa: BLE001
        return o, "low"


def fight(sess, o, log, flee_below=8):
    """Target the enemy's weapons room (then shields, then any) and fire until it's
    destroyed; bail out (flee) on hull/oxygen/crew danger or if we have no powered
    weapons to win with. Returns (obs, outcome)."""
    o = power_core(sess, o)
    # Can't deal damage with no powered weapons — sitting here just suffocates/burns
    # us down (the seed-7 death). Leave instead of looping in an unwinnable fight.
    if not operational_weapons(o):
        log("  no operational weapons — can't win, fleeing")
        return _flee(sess, o, log)
    why = flee_reason(o, flee_below)
    if why:
        log(f"  unsafe ({why}) — fleeing before engaging")
        return _flee(sess, o, log)
    rooms = (o.enemy_ship or {}).get("rooms", [])
    target = None
    for want in (WEAPONS, SHIELDS):
        target = next((r["room_id"] for r in rooms if r.get("system_id") == want), None)
        if target is not None:
            break
    if target is None and rooms:
        target = rooms[0]["room_id"]
    if target is None:
        log("  enemy has no targetable rooms — fleeing")
        return _flee(sess, o, log)
    log(f"  combat: target enemy room {target}, enemy hull {enemy_hull(o)}")
    for w in operational_weapons(o):
        o = sess.fire_weapon(w["slot"], target, advance_frames=30)
    prev_eh, stall = enemy_hull(o), 0
    for _ in range(15):
        eh = enemy_hull(o)
        if not o.enemy_ship or (eh or 0) <= 0:
            log(f"  enemy destroyed (player hull {player_hull(o)})")
            return o, "kill"
        why = flee_reason(o, flee_below)
        if why:
            log(f"  unsafe ({why}) — fleeing")
            return _flee(sess, o, log)
        if not operational_weapons(o):  # weapons knocked out mid-fight
            log("  weapons knocked out — fleeing")
            return _flee(sess, o, log)
        # Stalemate: enemy hull isn't dropping (shields we can't break). Not dangerous,
        # but unwinnable -- leave instead of looping here forever (the x=238 stall).
        stall = stall + 1 if (eh is not None and prev_eh is not None and eh >= prev_eh) else 0
        prev_eh = eh
        if stall >= 5:
            log(f"  no progress vs enemy (hull stuck at {eh}) — fleeing")
            return _flee(sess, o, log)
        o = sess.step([], advance_frames=200)
    log("  fight inconclusive — fleeing")
    return _flee(sess, o, log)


def _pick_beacon(o):
    """Navigate toward the sector exit (FTL maps run left->right, exit on the right),
    grabbing nearby unvisited beacons for loot/events en route. Never jump into the
    rebel fleet. Falls back to plain unvisited/any when positions are unavailable."""
    m = o.map or {}
    beac = m.get("connected_beacons", [])
    if not beac:
        return None
    pool = [b for b in beac if not b.get("fleet")] or beac  # avoid the pursuit fleet
    # a neighbor that IS the exit beacon advances the sector — take it
    for b in pool:
        if b.get("exit_beacon"):
            return b["index"]
    exit_pos = m.get("exit_pos")
    if exit_pos and all(b.get("pos_x") is not None for b in pool):
        def dist_to_exit(b):
            return ((b["pos_x"] - exit_pos["x"]) ** 2 + (b["pos_y"] - exit_pos["y"]) ** 2) ** 0.5
        ranked = sorted(pool, key=dist_to_exit)            # nearest the exit first
        near_unvisited = [b for b in ranked[:2] if b.get("visited") == 0]
        return (near_unvisited[0] if near_unvisited else ranked[0])["index"]
    # no positions: prefer unvisited non-danger, then unvisited, then any
    for pred in (lambda b: b.get("visited") == 0 and not b.get("danger_zone"),
                 lambda b: b.get("visited") == 0,
                 lambda b: True):
        cand = [b for b in pool if pred(b)]
        if cand:
            return cand[0]["index"]
    return None


def play(sess, jumps, log):
    """Play until `jumps` FTL jumps are made (not iterations), the ship dies, or we
    get stuck. Resolves events, fights (fleeing when low), and navigates."""
    o = sess.observe()
    if not o.game_started:
        log("not in a run; resetting")
        o = sess.start_game("continue")
    stats = {"jumps": 0, "events": 0, "combats": 0, "kills": 0, "fled": 0, "sectors": 0}
    o = power_core(sess, o)

    # Event resolution escalates through choices: if a choice doesn't close the box
    # (e.g. an unaffordable "Hire for N scrap" option is greyed out -> the hotkey is a
    # no-op), try the next. Order: choice 0 (usual reward), then the LAST choice (almost
    # always a safe "leave/continue"), then the middle ones -- this avoids walking into a
    # "Fight the ship" option that sits before the leave choice.
    ev = {"text": None, "order": [], "step": 0}
    iters, timeouts, combat_streak, leave_tries = 0, 0, 0, 0
    while stats["jumps"] < jumps and iters < jumps * 8:
        iters += 1
        try:
            o = sess.observe()
        except Exception:  # noqa: BLE001
            time.sleep(0.2); continue
        if (player_hull(o) or 0) <= 0:
            log("ship destroyed"); break
        try:
            if o.choice_box_open and (o.event or {}).get("choices"):
                n = len(o.event["choices"])
                txt = (o.event.get("text") or "").replace("\n", " ")[:60]
                if txt != ev["text"]:                # new event: build the escalation order
                    order = [0, n - 1] + list(range(1, n - 1))
                    ev["text"] = txt
                    ev["order"] = list(dict.fromkeys(i for i in order if 0 <= i < n))
                    ev["step"] = 0
                else:
                    ev["step"] += 1                  # box still open -> previous choice was a no-op
                if ev["step"] >= len(ev["order"]):
                    log(f"event won't resolve ({txt!r}); stopping"); break
                idx = ev["order"][ev["step"]]
                sess.choose_event(idx, advance_frames=90)
                stats["events"] += 1
                combat_streak = 0
                log(f"event: {txt!r} -> chose {idx}")
            elif o.enemy_ship and (enemy_hull(o) or 0) > 0:
                combat_streak += 1
                if combat_streak > 6:       # can't kill and can't escape (FTL not charging?)
                    log("stuck in combat, can't win or escape; stopping"); break
                _, outcome = fight(sess, o, log)
                stats["combats"] += 1
                if outcome == "kill":
                    stats["kills"] += 1
                    combat_streak = 0
                elif outcome == "flee":
                    stats["fled"] += 1
                    stats["jumps"] += 1  # fleeing is an FTL jump
            elif (o.map or {}).get("at_exit"):
                # On the exit beacon -> cross into the next sector. The binding refuses
                # while a live enemy lingers (combat-time transition = SIGBUS), so retry
                # across iterations until combat clears; give up after a cap.
                sec_before = (o.map or {}).get("sector")
                o = sess.leave_sector()
                sec_after = (o.map or {}).get("sector")
                if sec_after is not None and sec_after != sec_before:
                    stats["sectors"] += 1
                    stats["jumps"] += 1
                    leave_tries = 0
                    ev["text"] = None
                    combat_streak = 0
                    log(f">>> crossed to sector {sec_after} (hull {player_hull(o)})")
                    power_core(sess, o)
                else:
                    leave_tries += 1
                    log(f"at exit beacon, waiting to leave [{leave_tries}] (combat/fuel?)")
                    if leave_tries >= 8:
                        log("can't leave the exit beacon; stopping"); break
            else:
                tgt = _pick_beacon(o)
                if tgt is None:
                    log("no beacons to jump to; stopping"); break
                fuel = (o.player_ship or {}).get("resources", {}).get("fuel")
                log(f"jump -> beacon {tgt} (fuel {fuel})")
                o = sess.jump(tgt, advance_frames=260)
                stats["jumps"] += 1
                ev["text"] = None           # new beacon -> fresh event, start at choice 0
                combat_streak = leave_tries = 0
                power_core(sess, o)
            timeouts = 0
        except TimeoutError:
            # An ack can lag transiently (long warp/arrival), but persistent timeouts
            # mean the game-side loop is actually wedged (Hyperspace's freeze watchdog
            # fires) -- the harness can't unstick that, so bail promptly rather than
            # hammer a frozen game.
            timeouts += 1
            log(f"action ack timed out [{timeouts}]")
            if timeouts >= 4:
                log("too many consecutive timeouts (game may be frozen); stopping"); break

    o = sess.observe()
    log(f"\n== run summary == hull {player_hull(o)}/30  "
        f"sector {(o.map or {}).get('sector')}  {stats}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jumps", type=int, default=5)
    ap.add_argument("--new", action="store_true", help="start a fresh run first")
    ap.add_argument("--seed", type=int, default=None, help="seed for --new")
    ap.add_argument("--record", default=None, help="path to write a trajectory JSONL")
    args = ap.parse_args()

    recorder = None
    if args.record:
        recorder = TrajectoryRecorder(
            args.record, meta={"agent": "baseline", "seed": args.seed, "jumps": args.jumps})
    sess = AgentSession(recorder=recorder)
    if args.new:
        sess.reset_episode(seed=args.seed)   # clean fresh run, even from in-game

    def log(msg):
        print(msg, flush=True)

    play(sess, args.jumps, log)

    if args.record:
        score = score_trajectory(load_trajectory(args.record))
        log(f"\n== score == {score}")
        log(f"trajectory: {args.record}")


if __name__ == "__main__":
    main()
