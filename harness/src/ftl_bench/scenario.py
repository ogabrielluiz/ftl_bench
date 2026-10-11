"""ftl_bench scenario / task schema.

A benchmark INSTANCE is a fully-specified, seeded scenario = (seed, ship, difficulty,
goal). Inspired by ARC-AGI (a suite of held-out tasks) and WebShop (instruction-
conditioned goals with weighted sub-objectives): the agent decides everything in-game;
the harness only checks GOAL achievement against the recorded observation stream. No
"how to play" is encoded here — only what counts as success.

A `Scenario.goal` is a list of `SubObjective`s, each scored to partial credit and
combined by a weighted intersection (see scoring.score_instance).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ObjKind = Literal["threshold", "boolean", "milestone"]


@dataclass(frozen=True)
class SubObjective:
    """One scored component of a scenario goal.

    key:    the achieved-metric key produced by scoring (e.g. 'jumps', 'sector',
            'final_hull', 'final_scrap', 'crew_alive', 'enemy_defeated', 'progress').
    target: the value that earns full credit.
    kind:   'threshold' -> credit = clip(achieved/target, 0, 1);
            'boolean'   -> credit = 1.0 if achieved truthy else 0.0;
            'milestone' -> credit = clip(achieved/target, 0, 1) (already a progress count).
    weight: relative importance in the weighted-intersection reward.
    """
    key: str
    target: float
    kind: ObjKind = "threshold"
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key or self.kind not in ("threshold", "boolean", "milestone"):
            raise ValueError("a goal needs a metric key and a supported objective kind")
        if (not isinstance(self.target, (int, float)) or isinstance(self.target, bool)
                or not math.isfinite(self.target) or self.target < 0):
            raise ValueError("objective target must be a finite non-negative number")
        if (not isinstance(self.weight, (int, float)) or isinstance(self.weight, bool)
                or not math.isfinite(self.weight) or self.weight <= 0):
            raise ValueError("objective weight must be finite and greater than zero")


@dataclass(frozen=True)
class Scenario:
    """A single reproducible benchmark instance."""
    id: str
    type: str                       # scenario TYPE (T1..T12 family), e.g. 'reach_sector'
    seed: int                       # pins map + events via reset_episode(seed)
    goal: list[SubObjective]
    budget_jumps: int = 8           # the agent's jump/turn budget for this instance
    ship: str = "kestrel"
    difficulty: str = "easy"
    tier: str = "public"            # public | dev | semi_private | private
    # Legitimacy gate: the run must show genuine engagement, not metric-gaming.
    # min_distinct_beacons guards "jump in place" loops (None = no check).
    min_distinct_beacons: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.id):
            raise ValueError("scenario id must contain only letters, numbers, dots, underscores or hyphens")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or not 0 <= self.seed <= 0xFFFFFFFF:
            raise ValueError("scenario seed must be an unsigned 32-bit integer")
        if not isinstance(self.budget_jumps, int) or isinstance(self.budget_jumps, bool) or self.budget_jumps <= 0:
            raise ValueError("scenario budget_jumps must be greater than zero")
        if self.min_distinct_beacons is not None and (
            not isinstance(self.min_distinct_beacons, int) or isinstance(self.min_distinct_beacons, bool)
            or self.min_distinct_beacons < 0
        ):
            raise ValueError("min_distinct_beacons must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "type": self.type, "seed": self.seed,
            "goal": [vars(o) for o in self.goal],
            "budget_jumps": self.budget_jumps, "ship": self.ship,
            "difficulty": self.difficulty, "tier": self.tier,
            "min_distinct_beacons": self.min_distinct_beacons,
            "params": self.params, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        return _scenario_from_dict(data)


def _scenario_from_dict(d: dict[str, Any]) -> Scenario:
    goal = [SubObjective(**o) for o in d["goal"]]
    return Scenario(
        id=d["id"], type=d["type"], seed=d["seed"], goal=goal,
        budget_jumps=d.get("budget_jumps", 8), ship=d.get("ship", "kestrel"),
        difficulty=d.get("difficulty", "easy"), tier=d.get("tier", "public"),
        min_distinct_beacons=d.get("min_distinct_beacons"),
        params=d.get("params", {}), notes=d.get("notes", ""),
    )


def load_suite(path: Path | str) -> list[Scenario]:
    """Load a scenario suite from a JSON file ({"scenarios": [...]} or a bare list)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["scenarios"] if isinstance(data, dict) else data
    scenarios = [_scenario_from_dict(d) for d in items]
    if len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("scenario ids must be unique within a suite")
    return scenarios
