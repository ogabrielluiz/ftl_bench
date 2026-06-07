"""Aggregate per-instance benchmark scores into the headline leaderboard metrics.

PRIMARY: FTL score = mean of FTL's own native run score over the suite. It is the game's holistic
measure (scrap, kills, sectors, flagship, times difficulty), non-saturating and gaming-resistant,
so it needs no coined metric. We report it as mean ± seed SE and as the median (the score is
right-skewed, so the median is the robust central tendency). SECONDARY: Solve Rate = fraction of
instances that achieve the scenario goal (for full games, the win). Also reports a per-type and
public-vs-held-out breakdown, and a coarse efficiency axis.

RETRY MODE: when the suite is run with retries, each instance's reported result is its BEST attempt
and also carries every attempt's score. The aggregate then adds a learning curve — the mean/median
best-so-far score and the solve rate AS A FUNCTION OF the number of attempts (solve@1 -> solve@k),
the standard way to show whether retrying-with-reflection actually helps. The headline number stays
best-of-N and is labeled as such, never conflated with the pass@1 (single-try) number.
"""
from __future__ import annotations

import statistics
from typing import Any


def _mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 2) if xs else None


def _median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 2) if xs else None


def _se(xs: list[float]) -> float:
    return round(statistics.stdev(xs) / (len(xs) ** 0.5), 2) if len(xs) > 1 else 0.0


def _retry_curve(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Learning curve over retries: for each attempt budget k = 1..maxk, the mean & median
    best-so-far FTL score and the cumulative solve rate (solved within k tries). Instances that
    solved early and stopped keep their solved value for all larger k (best-so-far is monotone)."""
    per = [(r.get("attempt_ftl_scores") or [r.get("ftl_score", 0)],
            r.get("attempt_solved") or [bool(r.get("solved"))]) for r in results]
    maxk = max(len(scores) for scores, _ in per)
    n = len(results)
    curve = []
    for k in range(1, maxk + 1):
        bests, solves = [], 0
        for scores, flags in per:
            kk = min(k, len(scores))               # early-stopped instances clamp to their last
            bests.append(max(scores[:kk]))
            solves += 1 if any(flags[:kk]) else 0
        curve.append({
            "k": k,
            "ftl_score_mean": _mean(bests),
            "ftl_score_median": _median(bests),
            "solved": solves,
            "solve_pct": round(100 * solves / n, 1),
        })
    return curve


def aggregate(results: list[dict[str, Any]], scenarios: list) -> dict[str, Any]:
    """results: list of score_instance() dicts (in retry mode, each is the BEST attempt and also
    carries `attempt_ftl_scores`/`attempt_solved`). scenarios: the Scenario objects (for tier)."""
    if not results:
        return {"ftl_score_mean": None, "ftl_score_median": None, "solve_rate": "0/0", "instances": 0}
    ftl_scores = [r.get("ftl_score", 0) for r in results]
    solved = sum(1 for r in results if r["solved"])
    n = len(results)
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
    fmean, fmed, fse = _mean(ftl_scores), _median(ftl_scores), _se(ftl_scores)
    out: dict[str, Any] = {
        "ftl_score_mean": fmean,                # the headline number (FTL's native run score)
        "ftl_score_median": fmed,               # robust central tendency (right-skewed score)
        "ftl_score_SE": fse,
        "headline": f"FTL score {fmean} ± {fse}  |  Solve {solved}/{n}",
        "solve_rate": f"{solved}/{n}",
        "solve_pct": round(100 * solved / n, 1),
        "instances": n,
        "median_jumps_per_instance": round(statistics.median(jumps_used), 1) if jumps_used else None,
        "by_type": group(lambda r: r["type"]),
        "by_tier": group(lambda r: tier_by_id.get(r["scenario"], "?")),
    }
    # Retry mode: the headline IS best-of-N — label it and add the learning curve.
    if any("attempt_ftl_scores" in r for r in results):
        curve = _retry_curve(results)
        out["retries"] = True
        out["max_attempts"] = len(curve)
        out["retry_curve"] = curve
        out["solve_at"] = {f"@{c['k']}": f"{c['solved']}/{n}" for c in curve}
        out["headline"] += f"  [best of up to {len(curve)} tries]"
    return out
