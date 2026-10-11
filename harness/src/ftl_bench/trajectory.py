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
        self.closed = False
        # Start fresh; first line is a meta header.
        header = {"i": -1, "t": round(time.time(), 3), "kind": "meta",
                  "meta": meta or {}}
        self.path.write_text(json.dumps(header) + "\n", encoding="utf-8")

    def record(self, kind: str, actions: Iterable[dict[str, Any]] | None, obs,
               thought: str | None = None, model: dict[str, Any] | None = None, *,
               pre_obs=None, decision_obs=None, visual: dict[str, Any] | None = None) -> None:
        if self.closed:
            raise RuntimeError("cannot append to a finished trajectory")
        rec = {
            "i": self.n,
            "t": round(time.time(), 3),
            "kind": kind,
            "actions": list(actions) if actions else [],
            "obs": getattr(obs, "raw", None),
        }
        # `thought` (the agent's reasoning for this step) is OPTIONAL and additive: only written
        # when present, so old trajectories and non-LLM agents (no thought) stay byte-identical and
        # every consumer that reads records via .get() is unaffected.
        if thought:
            rec["thought"] = thought
        if model:
            rec["model"] = model
        if visual is not None:
            rec["visual"] = visual
        # Optional provenance snapshots are additive. The resulting observation remains `obs`,
        # so scoring and older consumers keep their existing behavior.
        for name, snapshot in (("pre_obs", pre_obs), ("decision_obs", decision_obs)):
            if snapshot is not None:
                rec[name] = snapshot if isinstance(snapshot, dict) else getattr(snapshot, "raw", None)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self.n += 1

    def finish(self, *, status: str = "completed", reason: str = "agent_returned",
               error: str | None = None, **details: Any) -> None:
        """Append one terminal lifecycle marker, without replacing the final game state."""
        if self.closed:
            return
        if status not in ("completed", "error", "interrupted"):
            raise ValueError(f"unsupported trajectory status: {status}")
        rec = {**details, "i": self.n, "t": round(time.time(), 3), "kind": "end", "obs": None,
               "actions": [], "status": status, "reason": reason}
        if error:
            rec["error"] = error
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self.n += 1
        self.closed = True


def load_trajectory(path: Path | str) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]
