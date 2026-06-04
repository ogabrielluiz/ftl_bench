"""Trajectory recording for ftl_bench runs.

Each step the harness takes is appended as one JSON line: the action(s) issued and
the resulting (raw) observation. Trajectories are replayable and scoreable, the
basis for benchmark evaluation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable


class TrajectoryRecorder:
    """Appends (kind, actions, resulting observation) records to a JSONL file."""

    def __init__(self, path: Path | str, meta: dict[str, Any] | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.n = 0
        # Start fresh; first line is a meta header.
        header = {"i": -1, "t": round(time.time(), 3), "kind": "meta",
                  "meta": meta or {}}
        self.path.write_text(json.dumps(header) + "\n", encoding="utf-8")

    def record(self, kind: str, actions: Iterable[dict[str, Any]] | None, obs) -> None:
        rec = {
            "i": self.n,
            "t": round(time.time(), 3),
            "kind": kind,
            "actions": list(actions) if actions else [],
            "obs": getattr(obs, "raw", None),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self.n += 1


def load_trajectory(path: Path | str) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]
