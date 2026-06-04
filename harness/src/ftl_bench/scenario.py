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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "type": self.type, "seed": self.seed,
            "goal": [vars(o) for o in self.goal],
            "budget_jumps": self.budget_jumps, "ship": self.ship,
            "difficulty": self.difficulty, "tier": self.tier,
            "min_distinct_beacons": self.min_distinct_beacons,
            "params": self.params, "notes": self.notes,
        }


def _scenario_from_dict(d: dict[str, Any]) -> Scenario:
    goal = [SubObjective(**o) for o in d["goal"]]
    return Scenario(
        id=d["id"], type=d["type"], seed=int(d["seed"]), goal=goal,
        budget_jumps=int(d.get("budget_jumps", 8)), ship=d.get("ship", "kestrel"),
        difficulty=d.get("difficulty", "easy"), tier=d.get("tier", "public"),
        min_distinct_beacons=d.get("min_distinct_beacons"),
        params=d.get("params", {}), notes=d.get("notes", ""),
    )


def load_suite(path: Path | str) -> list[Scenario]:
    """Load a scenario suite from a JSON file ({"scenarios": [...]} or a bare list)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["scenarios"] if isinstance(data, dict) else data
    return [_scenario_from_dict(d) for d in items]
