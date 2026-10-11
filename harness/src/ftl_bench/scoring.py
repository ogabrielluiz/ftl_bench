"""Scoring / metrics for ftl_bench runs.

`score_observation` summarizes a single state; `score_trajectory` aggregates a
recorded run (raw stats). `score_instance` is the BENCHMARK scorer. The headline metric is
FTL's own native run score (`ftl_score`, the game's holistic scrap/kills/sectors/flagship
measure). It also computes a goal-conditioned `solved` flag (did the run achieve the scenario
goal, e.g. the win) and a legitimacy gate against metric-gaming, all from recorded observation
fields only (no env access, no policy).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .observation import is_living_player_crew

if TYPE_CHECKING:
    from ftl_bench.scenario import Scenario


def _hull(ps: dict[str, Any] | None):
    return (ps or {}).get("hull", {}).get("current")


def _crew_alive(ps: dict[str, Any]) -> int:
    # The death flag can lag health by one native frame. Missing health remains
    # compatible with older recordings, but observed zero health is terminal.
    return sum(is_living_player_crew(member) for member in (ps.get("crew") or []))


def score_observation(obs) -> dict[str, Any]:
    """Snapshot metrics from a single Observation."""
    ps = obs.player_ship or {}
    hull = _hull(ps)
    return {
        "game_started": obs.game_started,
        "alive": ((hull or 0) > 0 and
                  (ps.get("crew") is None or _crew_alive(ps) > 0) and
                  (not obs.game_over or (obs.raw or {}).get("victory") is True))
                 if obs.game_started else None,
        "hull": hull,
        "scrap": (ps.get("resources") or {}).get("scrap"),
        "fuel": (ps.get("resources") or {}).get("fuel"),
        "sector": (obs.map or {}).get("sector"),
        "in_combat": bool(obs.enemy_ship),
    }


def score_trajectory(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate metrics over a recorded run (list of trajectory records)."""
    metrics = achieved_metrics(records)
    final_obs = _final_run_observation(records)
    ps = final_obs.get("player_ship") or {}
    hull = _hull(ps)
    return {
        "decisions": sum(1 for r in records if r.get("kind") not in ("meta", "end")),
        "jumps": metrics["jumps"],
        "events": metrics["events"],
        "kills": metrics["kills"],
        "final_hull": hull,
        "final_scrap": (ps.get("resources") or {}).get("scrap"),
        "final_sector": (final_obs.get("map") or {}).get("sector"),
        "alive": bool(metrics["alive"]) if final_obs.get("game_started") else None,
        "gave_up": metrics["gave_up"],
    }


# --- Benchmark scoring: goal-conditioned, partial-credit (score_instance) -----------

def _location(obs: dict[str, Any]) -> tuple | None:
    """A beacon identity includes its sector: coordinates are reused across sectors."""
    m = obs.get("map") or {}
    cp = m.get("current_pos") or {}
    x, y = cp.get("x"), cp.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    sector = m.get("sector")
    return (sector if isinstance(sector, int) else None, x, y)


def _final_run_observation(records: list[dict[str, Any]]) -> dict[str, Any]:
    observations = [r.get("obs") for r in records if r.get("kind") not in ("meta", "end")
                    and r.get("obs")]
    # Cleanup may record a menu after play has finished. It must not erase the outcome.
    return next((o for o in reversed(observations) if o.get("game_started")),
                observations[-1] if observations else {})


def achieved_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Outcome metrics an agent's run achieved, read ONLY from recorded observations.
    These are the values scenario sub-objectives are scored against. No env access."""
    jumps = sectors = events = kills = gave_up = 0
    max_sector = 0
    saw_sector = False
    positions: set = set()
    prev_alive = False
    prev_fleeing = False
    prev_location = None
    prev_sector = None
    final_obs: dict[str, Any] = {}
    ftl_score = 0
    victory = False
    phases_completed = 0
    for r in records:
        if r.get("kind") in ("meta", "end"):
            continue
        obs = r.get("obs") or {}
        if obs.get("game_started"):
            final_obs = obs
        if r.get("kind") in ("start_game", "reset_episode", "reset"):
            # A reset is an episode baseline, never a travel action. If a trajectory
            # contains several episodes, score the last one rather than pool their progress.
            jumps = sectors = events = kills = gave_up = max_sector = 0
            saw_sector = prev_alive = prev_fleeing = victory = False
            phases_completed = ftl_score = 0
            positions.clear()
            prev_location = prev_sector = None
        # Use the latest in-game score. Older TopScore snapshots may carry a previous
        # episode's value; taking their maximum would inflate a later, shorter run.
        _fs = obs.get("ftl_score")
        if obs.get("game_started") and isinstance(_fs, (int, float)) and not isinstance(_fs, bool):
            ftl_score = _fs
        # Only an explicit, verified win/completed-phase field is authoritative. The
        # engine's raw boss phase/stage counters and game_over also occur on losses.
        victory = victory or obs.get("victory") is True
        completed = (obs.get("flagship") or {}).get("phases_completed")
        if isinstance(completed, int) and not isinstance(completed, bool) and 0 <= completed <= 3:
            phases_completed = max(phases_completed, completed)
        if victory:
            phases_completed = 3
        m = obs.get("map") or {}
        sec = m.get("sector")
        sector_changed = False
        if isinstance(sec, int) and not isinstance(sec, bool) and sec >= 0:
            saw_sector = True
            max_sector = max(max_sector, sec)
            if prev_sector is not None and sec > prev_sector:
                crossings = sec - prev_sector
                sectors += crossings
                jumps += crossings
                sector_changed = True
            elif prev_sector is not None and sec < prev_sector:
                # A new run observed without an explicit reset cannot be a backwards jump.
                prev_location = None
            prev_sector = sec
        location = _location(obs)
        moved = False
        if location is not None:
            positions.add(location)
            moved = prev_location is not None and location != prev_location
            if moved and not sector_changed and location[0] == prev_location[0]:
                jumps += 1
            prev_location = location
        elif sector_changed:
            # The bridge omits coordinates during a warp. The first settled position
            # in the new sector is a baseline, not a second jump.
            prev_location = None
        for a in r.get("actions", []):
            t = a.get("type")
            if t == "choose_event":
                events += 1
            elif t == "give_up":
                gave_up = 1
        if not obs.get("game_started"):
            continue  # a menu/cleanup snapshot cannot defeat an enemy
        enemy = obs.get("enemy_ship")
        ehull = (enemy or {}).get("hull", {}).get("current") if enemy else None
        alive = enemy is not None and (ehull or 0) > 0
        if prev_alive and ((ehull is not None and ehull <= 0) or
                           (enemy is None and not moved and not sector_changed and not prev_fleeing)):
            kills += 1
        prev_alive = alive
        prev_fleeing = bool((enemy or {}).get("fleeing"))

    ps = final_obs.get("player_ship") or {}
    res = ps.get("resources") or {}
    final_hull = _hull(ps) or 0
    crew_alive = _crew_alive(ps)
    crew = ps.get("crew")
    alive = final_hull > 0 and (crew is None or crew_alive > 0)
    alive = alive and (not final_obs.get("game_over") or victory or phases_completed == 3)
    sector_progress = min(8, max_sector + 1) if saw_sector else 0
    if victory or phases_completed == 3:
        sector_progress = 8
    return {
        "jumps": jumps,                    # confirmed beacon/sector transitions only
        "sectors_crossed": sectors,
        "sector": max_sector,
        "progress": sector_progress + phases_completed,
        "victory": bool(victory or phases_completed == 3),
        "flagship_phases_completed": phases_completed,
        "kills": kills,
        "events": events,
        "enemy_defeated": 1 if kills > 0 else 0,
        "final_hull": final_hull,
        "final_scrap": res.get("scrap") or 0,
        "final_fuel": res.get("fuel") or 0,
        "crew_alive": crew_alive,
        "alive": int(alive),
        "gave_up": gave_up,
        "distinct_beacons": len(positions),
        "oxygen_pct": ps.get("oxygen_pct"),
        "ftl_score": ftl_score,            # FTL's native run score (headline for full games)
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
    terminal = next((rec for rec in reversed(records) if rec.get("kind") == "end"), {})
    status = terminal.get("status", "completed")
    reason = terminal.get("reason")
    outcome_allows_solve = (not achieved["gave_up"] and
                           status not in ("error", "failed", "interrupted") and
                           reason not in ("stalled", "gave_up", "give_up"))
    if scenario.type == "full_run":
        outcome_allows_solve = outcome_allows_solve and achieved["victory"]
    if scenario.type == "survive_n_jumps":
        outcome_allows_solve = outcome_allows_solve and achieved["alive"] == 1
    return {
        "scenario": scenario.id,
        "type": scenario.type,
        "seed": scenario.seed,
        "r": round(r, 4),
        "score": round(100 * r, 1),
        "ftl_score": achieved.get("ftl_score", 0),   # the game's native run score
        "solved": bool(r >= 1.0 - 1e-9 and legit == 1 and outcome_allows_solve),
        "status": status,
        "reason": reason,
        **({"error": terminal["error"]} if terminal.get("error") else {}),
        "legitimacy_gate": legit,
        "breakdown": breakdown,
        "jumps_used": achieved["jumps"],
        "budget_jumps": scenario.budget_jumps,
        "achieved": achieved,
    }
