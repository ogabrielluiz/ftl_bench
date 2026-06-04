"""Scoring / metrics for ftl_bench runs.

`score_observation` summarizes a single state; `score_trajectory` aggregates a
recorded run (decisions, jumps, events, kills, final hull/scrap/sector, survival).
These are the headline benchmark metrics for an episode.
"""
from __future__ import annotations

from typing import Any


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
