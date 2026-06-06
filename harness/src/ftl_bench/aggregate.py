"""Aggregate per-instance benchmark scores into the headline leaderboard metrics.

PRIMARY: FTL score = mean of FTL's own native run score over the suite. It is the game's holistic
measure (scrap, kills, sectors, flagship, times difficulty), non-saturating and gaming-resistant,
so it needs no coined metric. SECONDARY: Solve Rate = fraction of instances that achieve the
scenario goal (for full games, the win). Also reports a per-type and public-vs-held-out breakdown,
and a coarse efficiency axis.
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
        return {"ftl_score_mean": None, "solve_rate": "0/0", "instances": 0}
    ftl_scores = [r.get("ftl_score", 0) for r in results]
    solved = sum(1 for r in results if r["solved"])
    tier_by_id = {s.id: s.tier for s in scenarios}

    def group(key_fn):
        g: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            g.setdefault(key_fn(r), []).append(r)
        return {
            k: {
                "ftl_score": _mean([x.get("ftl_score", 0) for x in rs]),
                "solved": sum(1 for x in rs if x["solved"]),
                "n": len(rs),
            }
            for k, rs in sorted(g.items())
        }

    # efficiency: median state-changing jumps used per instance (lower = tighter)
    jumps_used = [r.get("jumps_used", 0) for r in results]
    fmean = _mean(ftl_scores)
    fse = _se(ftl_scores)
    return {
        "ftl_score_mean": fmean,                # the headline number (FTL's native run score)
        "ftl_score_SE": fse,
        "headline": f"FTL score {fmean} ± {fse}  |  Solve {solved}/{len(results)}",
        "solve_rate": f"{solved}/{len(results)}",
        "solve_pct": round(100 * solved / len(results), 1),
        "instances": len(results),
        "median_jumps_per_instance": round(statistics.median(jumps_used), 1) if jumps_used else None,
        "by_type": group(lambda r: r["type"]),
        "by_tier": group(lambda r: tier_by_id.get(r["scenario"], "?")),
    }
