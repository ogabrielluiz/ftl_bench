"""Scoring / metrics for ftl_bench runs.

`score_observation` summarizes a single state; `score_trajectory` aggregates a
recorded run (raw stats). `score_instance` is the BENCHMARK scorer: goal-conditioned,
partial-credit, reading only recorded observation fields (no env access, no policy) —
the WebShop-style weighted intersection of achieved vs. requested sub-objectives, with
a legitimacy gate against metric-gaming. r in [0,1], Score = 100*r.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ftl_bench.scenario import Scenario


def _hull(ps: dict[str, Any] | None):
    return (ps or {}).get("hull", {}).get("current")


def score_observation(obs) -> dict[str, Any]:
    """Snapshot metrics from a single Observation."""
    ps = obs.player_ship or {}
    hull = _hull(ps)
    return {
        "game_started": obs.game_started,
        "alive": (hull or 0) > 0 if obs.game_started else None,
        "hull": hull,
        "scrap": (ps.get("resources") or {}).get("scrap"),
        "fuel": (ps.get("resources") or {}).get("fuel"),
        "sector": (obs.map or {}).get("sector"),
        "in_combat": bool(obs.enemy_ship),
    }


def score_trajectory(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate metrics over a recorded run (list of trajectory records)."""
    jumps = events = kills = 0
    prev_alive = False
    final_obs: dict[str, Any] = {}

    for r in records:
        if r.get("kind") == "meta":
            continue
        obs = r.get("obs") or {}
        if obs:
            final_obs = obs
        for a in r.get("actions", []):
            t = a.get("type")
            if t == "jump":
                jumps += 1
            elif t == "choose_event":
                events += 1
        enemy = obs.get("enemy_ship")
        ehull = enemy.get("hull", {}).get("current") if enemy else None
        alive = enemy is not None and (ehull or 0) > 0
        # kill = an enemy that was alive is now destroyed (hull <= 0 in-obs, or gone)
        if prev_alive and (enemy is None or (ehull is not None and ehull <= 0)):
            kills += 1
        prev_alive = alive

    ps = final_obs.get("player_ship") or {}
    hull = _hull(ps)
    return {
        "decisions": sum(1 for r in records if r.get("kind") != "meta"),
        "jumps": jumps,
        "events": events,
        "kills": kills,
        "final_hull": hull,
        "final_scrap": (ps.get("resources") or {}).get("scrap"),
        "final_sector": (final_obs.get("map") or {}).get("sector"),
        "alive": (hull or 0) > 0 if final_obs.get("game_started") else None,
    }


# --- Benchmark scoring: goal-conditioned, partial-credit (score_instance) -----------

def achieved_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Outcome metrics an agent's run achieved, read ONLY from recorded observations.
    These are the values scenario sub-objectives are scored against. No env access."""
    jumps = sectors = events = kills = 0
    max_sector = 0
    positions: set = set()
    prev_alive = False
    final_obs: dict[str, Any] = {}
    for r in records:
        if r.get("kind") == "meta":
            continue
        obs = r.get("obs") or {}
        if obs:
            final_obs = obs
        m = obs.get("map") or {}
        sec = m.get("sector")
        if isinstance(sec, int):
            max_sector = max(max_sector, sec)
        cp = m.get("current_pos")
        if cp and cp.get("x") is not None:
            positions.add((cp.get("x"), cp.get("y")))
        for a in r.get("actions", []):
            t = a.get("type")
            if t == "jump":
                jumps += 1
            elif t == "leave_sector":
                sectors += 1
            elif t == "choose_event":
                events += 1
        enemy = obs.get("enemy_ship")
        ehull = (enemy or {}).get("hull", {}).get("current") if enemy else None
        alive = enemy is not None and (ehull or 0) > 0
        if prev_alive and (enemy is None or (ehull is not None and ehull <= 0)):
            kills += 1
        prev_alive = alive

    ps = final_obs.get("player_ship") or {}
    res = ps.get("resources") or {}
    final_hull = _hull(ps) or 0
    crew_alive = sum(1 for c in (ps.get("crew") or []) if not c.get("dead"))
    return {
        "jumps": jumps + sectors,          # sector crossings are jumps too
        "sectors_crossed": sectors,
        "sector": max_sector,
        "progress": max_sector,            # milestone progress (sectors); flagship later
        "kills": kills,
        "events": events,
        "enemy_defeated": 1 if kills > 0 else 0,
        "final_hull": final_hull,
        "final_scrap": res.get("scrap") or 0,
        "final_fuel": res.get("fuel") or 0,
        "crew_alive": crew_alive,
        "alive": 1 if final_hull > 0 else 0,
        "distinct_beacons": len(positions) if positions else (jumps + sectors),
        "oxygen_pct": ps.get("oxygen_pct"),
    }


def _credit(obj, achieved: dict[str, Any]) -> float:
    """Per-sub-objective credit in [0,1]."""
    a = achieved.get(obj.key, 0) or 0
    if obj.kind == "boolean":
        return 1.0 if a else 0.0
    t = obj.target or 1
    return max(0.0, min(1.0, a / t))            # threshold / milestone


def _legitimacy_gate(achieved: dict[str, Any], scenario: "Scenario") -> int:
    """1 if the run shows genuine engagement, 0 to collapse the reward (anti-gaming).
    Currently: reject 'jump in place' loops that don't visit enough distinct beacons."""
    mdb = getattr(scenario, "min_distinct_beacons", None)
    if mdb is not None and achieved.get("distinct_beacons", 0) < mdb:
        return 0
    return 1


def score_instance(records: list[dict[str, Any]], scenario: "Scenario") -> dict[str, Any]:
    """Goal-conditioned partial-credit score for one benchmark instance.

    r = legitimacy_gate * (Σ w_i * credit_i / Σ w_i)  (WebShop weighted intersection).
    Score = 100*r; solved = (r==1 and legit). Reads only recorded observations.
    """
    achieved = achieved_metrics(records)
    total_w = sum(o.weight for o in scenario.goal) or 1.0
    breakdown: dict[str, float] = {}
    raw = 0.0
    for o in scenario.goal:
        c = _credit(o, achieved)
        breakdown[o.key] = round(c, 3)
        raw += o.weight * c
    raw /= total_w
    legit = _legitimacy_gate(achieved, scenario)
    r = legit * raw
    return {
        "scenario": scenario.id,
        "type": scenario.type,
        "seed": scenario.seed,
        "r": round(r, 4),
        "score": round(100 * r, 1),
        "solved": bool(r >= 1.0 - 1e-9 and legit == 1),
        "legitimacy_gate": legit,
        "breakdown": breakdown,
        "jumps_used": achieved["jumps"],
        "budget_jumps": scenario.budget_jumps,
        "achieved": achieved,
    }
