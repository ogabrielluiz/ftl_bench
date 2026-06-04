"""Aggregate per-instance benchmark scores into the headline leaderboard metrics.

PRIMARY: GCS@1 (Goal Completion Score) = mean partial-credit Score over the suite
(WebShop "Score" / BALROG "Average Progress"). SECONDARY: Solve Rate = % of instances
fully achieving the goal (ARC "% solved" / WebShop "Success Rate"). Also reports a
per-type and public-vs-held-out breakdown, and a coarse efficiency axis.
"""
from __future__ import annotations

import statistics
from typing import Any


def _mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 2) if xs else None


def _se(xs: list[float]) -> float:
    return round(statistics.stdev(xs) / (len(xs) ** 0.5), 2) if len(xs) > 1 else 0.0


def aggregate(results: list[dict[str, Any]], scenarios: list) -> dict[str, Any]:
    """results: list of score_instance() dicts. scenarios: the Scenario objects (for tier)."""
    if not results:
        return {"GCS@1": None, "solve_rate": "0/0", "instances": 0}
    scores = [r["score"] for r in results]
    solved = sum(1 for r in results if r["solved"])
    tier_by_id = {s.id: s.tier for s in scenarios}

    def group(key_fn):
        g: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            g.setdefault(key_fn(r), []).append(r)
        return {
            k: {
                "GCS": _mean([x["score"] for x in rs]),
                "solved": sum(1 for x in rs if x["solved"]),
                "n": len(rs),
            }
            for k, rs in sorted(g.items())
        }

    # efficiency: median state-changing jumps used per instance (lower = tighter)
    jumps_used = [r.get("jumps_used", 0) for r in results]
    gcs = _mean(scores)
    se = _se(scores)
    return {
        "GCS@1": gcs,                           # the headline number (0-100)
        "GCS@1_SE": se,
        "headline": f"GCS@1 = {gcs} ± {se}  |  Solve {solved}/{len(results)}",
        "solve_rate": f"{solved}/{len(results)}",
        "solve_pct": round(100 * solved / len(results), 1),
        "instances": len(results),
        "median_jumps_per_instance": round(statistics.median(jumps_used), 1) if jumps_used else None,
        "by_type": group(lambda r: r["type"]),
        "by_tier": group(lambda r: tier_by_id.get(r["scenario"], "?")),
    }

