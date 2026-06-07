"""Tests for the retry protocol: the Attempt record handed to agents (ftl_bench.retry) and the
retry-aware aggregation (the solve@k learning curve + median) in ftl_bench.aggregate."""
from ftl_bench import Attempt, summarize_attempt
from ftl_bench.aggregate import aggregate
from ftl_bench.retry import _render_action


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _step(actions, *, hull, sector, enemy=False):
    return {
        "kind": "step",
        "actions": actions,
        "obs": {
            "player_ship": {"hull": {"current": hull, "max": 30}},
            "map": {"sector": sector},
            "enemy_ship": {"hull": {"current": 5}} if enemy else None,
        },
    }


def _result(*, ftl_score, solved, sector, hull, jumps, alive=1, budget=8, breakdown=None):
    return {
        "ftl_score": ftl_score,
        "solved": solved,
        "breakdown": breakdown or {"jumps": 0.5},
        "budget_jumps": budget,
        "achieved": {
            "sector": sector, "final_hull": hull, "jumps": jumps, "final_scrap": 10,
            "final_fuel": 4, "crew_alive": 2, "oxygen_pct": 80, "alive": alive,
            "ftl_score": ftl_score,
        },
    }


class _Scn:
    def __init__(self, sid, tier="public"):
        self.id = sid
        self.tier = tier


# --------------------------------------------------------------------------- #
# _render_action
# --------------------------------------------------------------------------- #
def test_render_action_known_types():
    assert _render_action({"type": "jump", "beacon_index": 3}) == "jump->b3"
    assert _render_action({"type": "fire_weapon", "weapon_slot": 0, "target_room_id": 1}) == "fire w0->r1"
    assert _render_action({"type": "set_system_power", "system_id": 3, "level": 2}) == "power s3=2"
    assert _render_action({"type": "choose_event", "choice_index": 0}) == "event->0"
    assert _render_action({"type": "leave_sector"}) == "leave"
    assert _render_action({"type": "move_crew", "crew_id": 1, "room_id": 5}) == "crew 1->r5"


def test_render_action_unknown_falls_back_to_type():
    assert _render_action({"type": "cloak"}) == "cloak"
    assert _render_action({}) == "?"


# --------------------------------------------------------------------------- #
# summarize_attempt
# --------------------------------------------------------------------------- #
def test_summarize_attempt_fields_and_transcript():
    records = [
        {"kind": "meta", "meta": {}},
        _step([{"type": "jump", "beacon_index": 3}], hull=28, sector=0),
        _step([{"type": "fire_weapon", "weapon_slot": 0, "target_room_id": 1}], hull=25, sector=1, enemy=True),
    ]
    res = _result(ftl_score=67, solved=False, sector=1, hull=25, jumps=2)
    att = summarize_attempt(records, res, index=0)

    assert isinstance(att, Attempt)
    assert att.index == 0
    assert att.ftl_score == 67
    assert att.solved is False
    assert att.final["sector"] == 1 and att.final["hull"] == 25 and att.final["jumps"] == 2
    assert att.breakdown == {"jumps": 0.5}
    # the meta header is skipped; two step lines, action-rendered with resulting state
    assert len(att.transcript) == 2
    assert att.transcript[0] == "step 0: jump->b3 -> sector 0 hull 28"
    assert att.transcript[1] == "step 1: fire w0->r1 -> sector 1 hull 25 enemy"


def test_summarize_attempt_outcomes():
    base = [{"kind": "meta"}, _step([], hull=0, sector=0)]
    destroyed = summarize_attempt(base, _result(ftl_score=10, solved=False, sector=0, hull=0, jumps=1, alive=0), 0)
    assert "destroyed" in destroyed.outcome.lower()

    survived = summarize_attempt(base, _result(ftl_score=40, solved=False, sector=2, hull=20, jumps=5), 0)
    assert "did not win" in survived.outcome

    won = summarize_attempt(base, _result(ftl_score=99, solved=True, sector=3, hull=30, jumps=8), 0)
    assert "met the scenario goal" in won.outcome

    # Regression: the outcome headline must be framed in GAME terms, never "jumps" — surfacing
    # the jump counter is what made reflections conclude "the goal is jumps".
    assert "jump" not in survived.outcome.lower()
    assert "jump" not in destroyed.outcome.lower()


def test_summarize_attempt_empty_action_is_wait():
    records = [{"kind": "meta"}, _step([], hull=30, sector=0)]
    att = summarize_attempt(records, _result(ftl_score=5, solved=False, sector=0, hull=30, jumps=0), 0)
    assert att.transcript == ["step 0: wait -> sector 0 hull 30"]


# --------------------------------------------------------------------------- #
# Attempt.digest
# --------------------------------------------------------------------------- #
def test_digest_includes_header_and_steps():
    att = Attempt(index=0, ftl_score=67, score=62.5, solved=False, outcome="ship destroyed",
                  breakdown={"jumps": 0.5}, final={"sector": 1, "hull": 0},
                  transcript=["step 0: jump->b3 -> sector 0 hull 28"])
    d = att.digest()
    assert "Attempt 1" in d and "ship destroyed" in d
    assert "ftl_score=67" in d and "solved=False" in d
    assert "step 0: jump->b3" in d
    # the score is kept but demoted to a labeled measurement; the {'jumps': ...} breakdown that
    # leaked "the goal is jumps" is no longer surfaced in the headline
    assert "measure" in d.lower()
    assert "Sub-objective credit" not in d and "0.5" not in d


def test_digest_truncates_long_transcripts():
    att = Attempt(index=1, ftl_score=10, score=5.0, solved=False, outcome="lost",
                  breakdown={}, final={}, transcript=[f"step {i}: wait -> s0" for i in range(100)])
    d = att.digest(max_steps=40)
    assert "60 earlier steps omitted" in d
    assert "step 99: wait -> s0" in d        # the tail is kept
    assert "step 0: wait -> s0" not in d.split("omitted")[1]  # the head is dropped


# --------------------------------------------------------------------------- #
# aggregate — retry mode (learning curve + median)
# --------------------------------------------------------------------------- #
def _retry_result(scenario, ftl_best, solved_best, attempt_scores, attempt_solved, jumps=5):
    return {
        "scenario": scenario, "type": "survive_n_jumps", "seed": 1,
        "ftl_score": ftl_best, "solved": solved_best, "jumps_used": jumps,
        "attempt_ftl_scores": attempt_scores, "attempt_solved": attempt_solved,
    }


def test_aggregate_retry_curve_and_solve_at():
    # A: never solves, improves 10 -> 50 across two tries.  B: solves on try 1 (score 30), stops.
    results = [
        _retry_result("a", 50, False, [10, 50], [False, False]),
        _retry_result("b", 30, True, [30], [True]),
    ]
    scenarios = [_Scn("a"), _Scn("b")]
    agg = aggregate(results, scenarios)

    assert agg["retries"] is True
    assert agg["max_attempts"] == 2
    # best-of-N headline: mean of best scores (50, 30) = 40, 1 of 2 solved
    assert agg["ftl_score_mean"] == 40.0
    assert agg["ftl_score_median"] == 40.0
    assert agg["solve_pct"] == 50.0
    assert "best of up to 2 tries" in agg["headline"]
    assert agg["solve_at"] == {"@1": "1/2", "@2": "1/2"}

    curve = agg["retry_curve"]
    assert [c["k"] for c in curve] == [1, 2]
    # @1: A=10, B=30 -> mean 20; one solved (B)
    assert curve[0]["ftl_score_mean"] == 20.0 and curve[0]["solved"] == 1
    # @2: A=max(10,50)=50, B clamps to its single attempt (30) -> mean 40; still one solved
    assert curve[1]["ftl_score_mean"] == 40.0 and curve[1]["solved"] == 1


def test_aggregate_non_retry_has_no_curve_but_has_median():
    results = [
        {"scenario": "a", "type": "t", "seed": 1, "ftl_score": 100, "solved": True, "jumps_used": 4},
        {"scenario": "b", "type": "t", "seed": 2, "ftl_score": 20, "solved": False, "jumps_used": 6},
    ]
    agg = aggregate(results, [_Scn("a"), _Scn("b")])
    assert "retries" not in agg
    assert "retry_curve" not in agg
    assert agg["ftl_score_median"] == 60.0          # median of (100, 20)
    assert agg["headline"].endswith("Solve 1/2")    # base headline format unchanged
