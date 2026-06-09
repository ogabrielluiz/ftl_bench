"""Retry protocol for ftl_bench — learning from failure across attempts.

When the suite is run with retries, the benchmark gives an agent more than one try at the SAME
seeded instance, and between tries it hands the agent a record of what happened on its previous
attempt(s): the actions it took, how the run ended, and the score. The agent decides what to do
with that (reflect on its mistakes, change strategy) — the benchmark only provides the loop and
the prior-attempt context. This makes "learn from your mistake and try again" a first-class part
of the agent contract, not something each agent has to wire up itself.

The contract: in retry mode the runner calls

    agent_fn(sess, scenario, log, attempts=(<Attempt>, ...))

where `attempts` holds the prior same-seed `Attempt`s, oldest first (empty on the first try). An
agent that doesn't accept `attempts` is simply called the old way, so existing agents keep working.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Attempt:
    """One completed try at a seeded instance, handed back to the agent for its next try."""

    index: int                      # 0-based attempt number
    ftl_score: float                # FTL's native run score for this attempt
    score: float                    # goal-conditioned score in [0, 100]
    solved: bool                    # did this attempt fully meet the goal?
    outcome: str                    # short human-readable end state (e.g. "ship destroyed")
    breakdown: dict[str, float]     # per-sub-objective credit (which goals were/weren't met)
    final: dict[str, Any]           # final state: sector, hull, jumps, scrap, fuel, crew_alive
    transcript: list[str]           # per-step "action -> resulting state" summary of this attempt

    def digest(self, max_steps: int = 40) -> str:
        """A compact text digest of this attempt, suitable for putting in a prompt.

        Leads with the GAME outcome and end state; the FTL run score is shown last and explicitly
        labeled a measurement (not the objective). The per-sub-objective `breakdown` — literally
        `{'jumps': ...}` for a survive_n_jumps scenario — is intentionally kept OUT of the headline:
        surfacing it made reflections treat "use more jumps" as the goal instead of "win the game".
        """
        f = self.final
        head = (
            f"Attempt {self.index + 1}: {self.outcome}.\n"
            f"  End state: sector {f.get('sector')}, hull {f.get('hull')}, "
            f"crew_alive {f.get('crew_alive')}, oxygen {f.get('oxygen_pct')}%, "
            f"scrap {f.get('scrap')}, fuel {f.get('fuel')}.\n"
            f"  (FTL run score for reference: ftl_score={self.ftl_score}, solved={self.solved} "
            f"— these MEASURE how well you played, not the objective.)"
        )
        steps = self.transcript[-max_steps:]
        omitted = len(self.transcript) - len(steps)
        lines = ([f"  ...({omitted} earlier steps omitted)"] if omitted > 0 else []) + \
                [f"  {s}" for s in steps]
        label = f" (last {len(steps)} of {len(self.transcript)} steps)" if omitted > 0 else ""
        return head + f"\nWhat you did{label}:\n" + "\n".join(lines)


def _render_action(a: dict[str, Any]) -> str:
    """Compactly render one applied action dict for a transcript line."""
    t = a.get("type", "?")
    if t == "set_system_power":
        return f"power s{a.get('system_id')}={a.get('level')}"
    if t == "move_crew":
        return f"crew {a.get('crew_id')}->r{a.get('room_id')}"
    if t == "jump":
        return f"jump->b{a.get('beacon_index')}"
    if t == "choose_event":
        return f"event->{a.get('choice_index')}"
    if t == "fire_weapon":
        return f"fire w{a.get('weapon_slot')}->r{a.get('target_room_id')}"
    if t == "fire_beam":
        return f"beam w{a.get('weapon_slot')}->r{a.get('room_a')}-r{a.get('room_b')}"
    if t == "leave_sector":
        return "leave"
    if t in ("store_buy", "store_sell"):
        return f"{t.split('_')[1]} #{a.get('index')}"
    if t == "upgrade_system":
        return f"upgrade s{a.get('system_id')}"
    if t == "start_game":
        return f"start({a.get('mode')})"
    return t


def summarize_attempt(records: list[dict[str, Any]], result: dict[str, Any], index: int) -> Attempt:
    """Build an `Attempt` from a recorded trajectory + its `score_instance` result."""
    ach = result.get("achieved") or {}
    # Lead with the game-outcome fields (sector/hull/crew); the jump counter is last and is NOT
    # in the outcome headline — describing an attempt in jumps-used terms is what made past
    # reflections conclude "the goal is jumps" (it isn't; the goal is to win the game).
    final = {
        "sector": ach.get("sector"),
        "hull": ach.get("final_hull"),
        "crew_alive": ach.get("crew_alive"),
        "oxygen_pct": ach.get("oxygen_pct"),
        "scrap": ach.get("final_scrap"),
        "fuel": ach.get("final_fuel"),
        "jumps": ach.get("jumps"),
    }
    sector = ach.get("sector", 0)
    kills = ach.get("kills", 0)
    crew = ach.get("crew_alive")
    o2 = ach.get("oxygen_pct")
    hull = ach.get("final_hull")
    if result.get("solved"):
        outcome = "met the scenario goal"
    elif ach.get("alive", 1) == 0:
        clauses = [f"killed {kills} enemies", f"crew alive {crew}"]
        if o2 is not None:
            clauses.append(f"O2 was {o2}%")
        outcome = (f"LOST: ship destroyed in sector-{sector} combat "
                   f"({'; '.join(clauses)})")
    else:
        outcome = (f"survived but did not win: reached sector {sector} with hull {hull}, "
                   f"crew alive {crew}, O2 {o2}%, {kills} enemies killed; "
                   f"the run ended without beating the flagship")

    transcript: list[str] = []
    step = 0
    for r in records:
        if r.get("kind") == "meta":
            continue
        acts = r.get("actions") or []
        obs = r.get("obs") or {}
        a_str = ", ".join(_render_action(a) for a in acts) or "wait"
        ps = obs.get("player_ship") or {}
        hull = (ps.get("hull") or {}).get("current")
        sector = (obs.get("map") or {}).get("sector")
        enemy = " enemy" if obs.get("enemy_ship") else ""
        # Carry the agent's recorded reasoning for this step into the transcript so the reflection
        # can learn from WHY each move was made, not just the move + outcome. Single-line (it was
        # collapsed at capture); omitted for old/non-LLM records that have no thought.
        thought = (r.get("thought") or "").strip().replace("\n", " ")
        line = f"step {step}: {a_str} -> sector {sector} hull {hull}{enemy}"
        if thought:
            line += f" [thought: {thought}]"
        transcript.append(line)
        step += 1

    return Attempt(
        index=index,
        ftl_score=ach.get("ftl_score", result.get("ftl_score", 0)),
        score=result.get("score", 0),
        solved=bool(result.get("solved")),
        outcome=outcome,
        breakdown=dict(result.get("breakdown") or {}),
        final=final,
        transcript=transcript,
    )
