"""Tests for ftl_bench.scoring — the core benchmark scoring math.

Covers the four public scorers exported from the package:

* ``score_observation``  — snapshot metrics from one Observation object.
* ``score_trajectory``   — raw aggregate stats over a recorded run.
* ``achieved_metrics``   — outcome metrics the scenario goal is scored against.
* ``score_instance``     — the goal-conditioned, partial-credit benchmark score,
  including the weighted intersection of sub-objectives and the anti-gaming
  legitimacy gate.

All inputs are built by hand (no game, no subprocess, no env access) — the
scorers read only recorded observation fields, so these tests pin the contract
exactly as the source defines it.
"""
import math

from ftl_bench import (
    Observation,
    Scenario,
    SubObjective,
    achieved_metrics,
    score_instance,
    score_observation,
    score_trajectory,
)


# --------------------------------------------------------------------------- #
# Builders                                                                     #
# --------------------------------------------------------------------------- #
def make_obs(**overrides) -> Observation:
    """Build a valid Observation, overriding any field."""
    data = {
        "schema_version": 2,
        "tick": 1,
        "seed": 0,
        "game_started": True,
    }
    data.update(overrides)
    return Observation.from_dict(data)


def obs_dict(**overrides) -> dict:
    """Raw observation dict as stored inside a trajectory record's 'obs'."""
    return make_obs(**overrides).raw


def player_ship(*, hull=30, scrap=10, fuel=5, crew=None, oxygen_pct=None):
    ps = {
        "hull": {"current": hull, "max": 30},
        "resources": {"scrap": scrap, "fuel": fuel},
    }
    if crew is not None:
        ps["crew"] = crew
    if oxygen_pct is not None:
        ps["oxygen_pct"] = oxygen_pct
    return ps


def rec(obs=None, actions=None, kind=None):
    """A single trajectory record (the dict shape the aggregators consume)."""
    r = {}
    if kind is not None:
        r["kind"] = kind
    if obs is not None:
        r["obs"] = obs
    if actions is not None:
        r["actions"] = actions
    return r


def sub(key, target, kind="threshold", weight=1.0):
    return SubObjective(key=key, target=target, kind=kind, weight=weight)


def scenario(goal, **overrides):
    data = dict(
        id="s1",
        type="reach_sector",
        seed=7,
        goal=goal,
    )
    data.update(overrides)
    return Scenario(**data)


# =========================================================================== #
# score_observation                                                           #
# =========================================================================== #
def test_score_observation_basic_fields():
    obs = make_obs(
        player_ship=player_ship(hull=22, scrap=14, fuel=3),
        map={"sector": 4},
        enemy_ship={"hull": {"current": 8}},
    )
    s = score_observation(obs)
    assert s == {
        "game_started": True,
        "alive": True,
        "hull": 22,
        "scrap": 14,
        "fuel": 3,
        "sector": 4,
        "in_combat": True,
    }


def test_score_observation_alive_is_none_before_game_started():
    # Even with a positive hull, alive is None until the game has started.
    obs = make_obs(game_started=False, player_ship=player_ship(hull=30))
    s = score_observation(obs)
    assert s["game_started"] is False
    assert s["alive"] is None


def test_score_observation_dead_at_zero_hull():
    obs = make_obs(player_ship=player_ship(hull=0))
    assert score_observation(obs)["alive"] is False


def test_score_observation_missing_hull_is_not_alive():
    # No player ship at all -> hull is None -> treated as not alive (not an error).
    obs = make_obs(player_ship=None)
    s = score_observation(obs)
    assert s["hull"] is None
    assert s["alive"] is False
    assert s["scrap"] is None and s["fuel"] is None


def test_score_observation_not_in_combat_when_no_enemy():
    obs = make_obs(player_ship=player_ship(), enemy_ship=None)
    assert score_observation(obs)["in_combat"] is False


def test_score_observation_sector_none_when_no_map():
    obs = make_obs(player_ship=player_ship(), map=None)
    assert score_observation(obs)["sector"] is None


# =========================================================================== #
# score_trajectory                                                            #
# =========================================================================== #
def test_score_trajectory_empty_records():
    s = score_trajectory([])
    assert s["decisions"] == 0
    assert s["jumps"] == 0
    assert s["events"] == 0
    assert s["kills"] == 0
    assert s["gave_up"] == 0
    assert s["final_hull"] is None
    assert s["final_scrap"] is None
    assert s["final_sector"] is None
    # No final obs -> game not started -> alive is None.
    assert s["alive"] is None


def test_score_trajectory_counts_jumps_and_events_and_decisions():
    records = [
        rec(obs=obs_dict(), actions=[{"type": "jump"}]),
        rec(obs=obs_dict(), actions=[{"type": "choose_event"}, {"type": "jump"}]),
        rec(obs=obs_dict(), actions=[{"type": "set_system_power"}]),
    ]
    s = score_trajectory(records)
    assert s["decisions"] == 3
    assert s["jumps"] == 2
    assert s["events"] == 1


def test_score_trajectory_and_achieved_metrics_record_give_up():
    records = [rec(obs=obs_dict(player_ship=player_ship()), actions=[{"type": "give_up"}])]

    assert score_trajectory(records)["gave_up"] == 1
    assert achieved_metrics(records)["gave_up"] == 1


def test_score_trajectory_skips_meta_records():
    records = [
        rec(kind="meta", actions=[{"type": "jump"}]),  # ignored entirely
        rec(obs=obs_dict(), actions=[{"type": "jump"}]),
    ]
    s = score_trajectory(records)
    # meta record contributes neither a decision nor its jump action.
    assert s["decisions"] == 1
    assert s["jumps"] == 1


def test_score_trajectory_final_obs_is_last_with_obs():
    records = [
        rec(obs=obs_dict(player_ship=player_ship(hull=30, scrap=1), map={"sector": 1})),
        rec(obs=obs_dict(player_ship=player_ship(hull=12, scrap=9), map={"sector": 3})),
    ]
    s = score_trajectory(records)
    assert s["final_hull"] == 12
    assert s["final_scrap"] == 9
    assert s["final_sector"] == 3
    assert s["alive"] is True


def test_score_trajectory_kill_when_enemy_disappears():
    records = [
        rec(obs=obs_dict(enemy_ship={"hull": {"current": 5}})),
        rec(obs=obs_dict(enemy_ship=None)),  # enemy gone -> 1 kill
    ]
    assert score_trajectory(records)["kills"] == 1


def test_score_trajectory_kill_when_enemy_hull_drops_to_zero():
    records = [
        rec(obs=obs_dict(enemy_ship={"hull": {"current": 3}})),
        rec(obs=obs_dict(enemy_ship={"hull": {"current": 0}})),
    ]
    assert score_trajectory(records)["kills"] == 1


def test_score_trajectory_no_double_count_after_kill():
    records = [
        rec(obs=obs_dict(enemy_ship={"hull": {"current": 8}})),  # alive
        rec(obs=obs_dict(enemy_ship={"hull": {"current": 0}})),  # destroyed -> kill
        rec(obs=obs_dict(enemy_ship=None)),                       # gone, no double-count
    ]
    assert score_trajectory(records)["kills"] == 1


def test_score_trajectory_no_kill_if_enemy_never_seen_alive():
    # Enemy is absent the whole run -> nothing to kill.
    records = [
        rec(obs=obs_dict(enemy_ship=None)),
        rec(obs=obs_dict(enemy_ship=None)),
    ]
    assert score_trajectory(records)["kills"] == 0


def test_score_trajectory_alive_none_when_final_obs_not_started():
    records = [rec(obs=obs_dict(game_started=False, player_ship=player_ship(hull=30)))]
    assert score_trajectory(records)["alive"] is None


# =========================================================================== #
# achieved_metrics                                                            #
# =========================================================================== #
def test_achieved_metrics_empty():
    a = achieved_metrics([])
    assert a["jumps"] == 0
    assert a["sectors_crossed"] == 0
    assert a["sector"] == 0
    assert a["progress"] == 0
    assert a["kills"] == 0
    assert a["enemy_defeated"] == 0
    assert a["final_hull"] == 0
    assert a["final_scrap"] == 0
    assert a["final_fuel"] == 0
    assert a["crew_alive"] == 0
    assert a["alive"] == 0
    assert a["gave_up"] == 0
    assert a["ftl_score"] == 0
    assert a["oxygen_pct"] is None
    # No positions recorded -> distinct_beacons falls back to jumps+sectors (0).
    assert a["distinct_beacons"] == 0


def test_achieved_metrics_jumps_include_leave_sector():
    records = [
        rec(obs=obs_dict(), actions=[{"type": "jump"}, {"type": "leave_sector"}]),
        rec(obs=obs_dict(), actions=[{"type": "jump"}]),
    ]
    a = achieved_metrics(records)
    assert a["sectors_crossed"] == 1
    assert a["jumps"] == 3  # two jumps + one leave_sector counted as a jump


def test_achieved_metrics_events_counted():
    records = [rec(obs=obs_dict(), actions=[{"type": "choose_event"}] * 2)]
    assert achieved_metrics(records)["events"] == 2


def test_achieved_metrics_max_sector_progress():
    records = [
        rec(obs=obs_dict(map={"sector": 2})),
        rec(obs=obs_dict(map={"sector": 5})),
        rec(obs=obs_dict(map={"sector": 4})),  # regression doesn't lower max
    ]
    a = achieved_metrics(records)
    assert a["sector"] == 5
    assert a["progress"] == 5


def test_achieved_metrics_non_int_sector_ignored():
    # A non-int sector value must not crash and must not raise max_sector.
    records = [rec(obs=obs_dict(map={"sector": "boss"}))]
    assert achieved_metrics(records)["sector"] == 0


def test_achieved_metrics_ftl_score_is_max_seen():
    records = [
        rec(obs=obs_dict(ftl_score=120)),
        rec(obs=obs_dict(ftl_score=340)),
        rec(obs=obs_dict(ftl_score=300)),  # never decreases the tracked max
    ]
    assert achieved_metrics(records)["ftl_score"] == 340


def test_achieved_metrics_ftl_score_ignores_non_numeric():
    records = [rec(obs=obs_dict(ftl_score="n/a"))]
    assert achieved_metrics(records)["ftl_score"] == 0


def test_achieved_metrics_distinct_beacons_from_positions():
    records = [
        rec(obs=obs_dict(map={"current_pos": {"x": 1, "y": 1}})),
        rec(obs=obs_dict(map={"current_pos": {"x": 2, "y": 3}})),
        rec(obs=obs_dict(map={"current_pos": {"x": 1, "y": 1}})),  # revisit
    ]
    # Two distinct (x, y) beacons visited.
    assert achieved_metrics(records)["distinct_beacons"] == 2


def test_achieved_metrics_distinct_beacons_ignores_missing_x():
    records = [rec(obs=obs_dict(map={"current_pos": {"x": None, "y": 1}}))]
    # x is None -> position not recorded -> fall back to jumps+sectors (0).
    assert achieved_metrics(records)["distinct_beacons"] == 0


def test_achieved_metrics_crew_alive_excludes_dead():
    crew = [{"dead": False}, {"dead": True}, {}]  # missing 'dead' counts as alive
    records = [rec(obs=obs_dict(player_ship=player_ship(crew=crew)))]
    assert achieved_metrics(records)["crew_alive"] == 2


def test_achieved_metrics_final_resources_and_alive():
    records = [
        rec(obs=obs_dict(player_ship=player_ship(hull=30, scrap=1, fuel=9))),
        rec(obs=obs_dict(player_ship=player_ship(hull=18, scrap=42, fuel=7))),
    ]
    a = achieved_metrics(records)
    assert a["final_hull"] == 18
    assert a["final_scrap"] == 42
    assert a["final_fuel"] == 7
    assert a["alive"] == 1


def test_achieved_metrics_alive_zero_when_hull_zero():
    records = [rec(obs=obs_dict(player_ship=player_ship(hull=0)))]
    a = achieved_metrics(records)
    assert a["final_hull"] == 0
    assert a["alive"] == 0


def test_achieved_metrics_enemy_defeated_flag():
    records = [
        rec(obs=obs_dict(enemy_ship={"hull": {"current": 7}})),
        rec(obs=obs_dict(enemy_ship=None)),
    ]
    a = achieved_metrics(records)
    assert a["kills"] == 1
    assert a["enemy_defeated"] == 1


def test_achieved_metrics_skips_meta():
    records = [
        rec(kind="meta", obs=obs_dict(map={"sector": 9}), actions=[{"type": "jump"}]),
        rec(obs=obs_dict(map={"sector": 2}), actions=[{"type": "jump"}]),
    ]
    a = achieved_metrics(records)
    # meta record's sector and action are both ignored.
    assert a["sector"] == 2
    assert a["jumps"] == 1


def test_achieved_metrics_oxygen_pct_from_final_obs():
    records = [rec(obs=obs_dict(player_ship=player_ship(oxygen_pct=88)))]
    assert achieved_metrics(records)["oxygen_pct"] == 88


# =========================================================================== #
# score_instance — partial credit, weighting, solved, legitimacy gate         #
# =========================================================================== #
def test_score_instance_all_achieved_is_solved():
    # Single threshold objective fully met -> r == 1, solved True, score 100.
    records = [rec(obs=obs_dict(map={"sector": 5}))]
    sc = scenario([sub("sector", target=5, kind="threshold")])
    res = score_instance(records, sc)
    assert res["r"] == 1.0
    assert res["score"] == 100.0
    assert res["solved"] is True
    assert res["legitimacy_gate"] == 1
    assert res["breakdown"] == {"sector": 1.0}
    assert res["scenario"] == sc.id
    assert res["type"] == sc.type
    assert res["seed"] == sc.seed


def test_score_instance_none_achieved_is_zero():
    records = [rec(obs=obs_dict(map={"sector": 0}))]
    sc = scenario([sub("sector", target=5, kind="threshold")])
    res = score_instance(records, sc)
    assert res["r"] == 0.0
    assert res["score"] == 0.0
    assert res["solved"] is False
    assert res["breakdown"] == {"sector": 0.0}


def test_score_instance_partial_threshold_credit():
    # sector 2 of target 8 -> 0.25 credit.
    records = [rec(obs=obs_dict(map={"sector": 2}))]
    sc = scenario([sub("sector", target=8, kind="threshold")])
    res = score_instance(records, sc)
    assert res["breakdown"]["sector"] == 0.25
    assert res["r"] == 0.25
    assert res["score"] == 25.0
    assert res["solved"] is False


def test_score_instance_threshold_credit_clipped_to_one():
    # Overshooting the target never exceeds full credit.
    records = [rec(obs=obs_dict(map={"sector": 20}))]
    sc = scenario([sub("sector", target=5, kind="threshold")])
    res = score_instance(records, sc)
    assert res["breakdown"]["sector"] == 1.0
    assert res["r"] == 1.0
    assert res["solved"] is True


def test_score_instance_boolean_objective_truthy():
    records = [
        rec(obs=obs_dict(enemy_ship={"hull": {"current": 4}})),
        rec(obs=obs_dict(enemy_ship=None)),
    ]
    sc = scenario([sub("enemy_defeated", target=1, kind="boolean")])
    res = score_instance(records, sc)
    assert res["breakdown"]["enemy_defeated"] == 1.0
    assert res["solved"] is True


def test_score_instance_boolean_objective_falsy():
    records = [rec(obs=obs_dict(enemy_ship=None))]
    sc = scenario([sub("enemy_defeated", target=1, kind="boolean")])
    res = score_instance(records, sc)
    assert res["breakdown"]["enemy_defeated"] == 0.0
    assert res["r"] == 0.0


def test_score_instance_weighted_intersection():
    # sector met (credit 1, weight 3), enemy not defeated (credit 0, weight 1).
    # r = (3*1 + 1*0) / (3 + 1) = 0.75
    records = [rec(obs=obs_dict(map={"sector": 5}, enemy_ship=None))]
    sc = scenario(
        [
            sub("sector", target=5, kind="threshold", weight=3.0),
            sub("enemy_defeated", target=1, kind="boolean", weight=1.0),
        ]
    )
    res = score_instance(records, sc)
    assert res["breakdown"] == {"sector": 1.0, "enemy_defeated": 0.0}
    assert res["r"] == 0.75
    assert res["score"] == 75.0
    assert res["solved"] is False  # not every sub-objective achieved


def test_score_instance_weighting_actually_matters():
    # Same credits as above but the heavier weight on the *unmet* objective
    # should pull the score DOWN, proving weights are applied, not ignored.
    records = [rec(obs=obs_dict(map={"sector": 5}, enemy_ship=None))]
    sc = scenario(
        [
            sub("sector", target=5, kind="threshold", weight=1.0),
            sub("enemy_defeated", target=1, kind="boolean", weight=3.0),
        ]
    )
    res = score_instance(records, sc)
    # r = (1*1 + 3*0) / (1 + 3) = 0.25
    assert res["r"] == 0.25


def test_score_instance_milestone_partial_credit():
    records = [
        rec(obs=obs_dict(), actions=[{"type": "jump"}, {"type": "jump"}]),
    ]
    sc = scenario([sub("jumps", target=4, kind="milestone")])
    res = score_instance(records, sc)
    assert res["breakdown"]["jumps"] == 0.5
    assert res["r"] == 0.5


def test_score_instance_zero_target_does_not_divide_by_zero():
    # target 0 with threshold math: source guards via `obj.target or 1`.
    records = [rec(obs=obs_dict(map={"sector": 3}))]
    sc = scenario([sub("sector", target=0, kind="threshold")])
    res = score_instance(records, sc)
    # achieved 3 / fallback target 1 -> clipped to 1.0; no ZeroDivisionError.
    assert res["breakdown"]["sector"] == 1.0


def test_score_instance_reports_ftl_score_and_jump_budget():
    records = [
        rec(obs=obs_dict(ftl_score=512, map={"sector": 1}), actions=[{"type": "jump"}]),
    ]
    sc = scenario([sub("sector", target=1, kind="threshold")], budget_jumps=6)
    res = score_instance(records, sc)
    assert res["ftl_score"] == 512
    assert res["jumps_used"] == 1
    assert res["budget_jumps"] == 6
    assert res["achieved"]["ftl_score"] == 512


def test_score_instance_multi_objective_all_met_is_solved():
    records = [
        rec(
            obs=obs_dict(
                map={"sector": 8},
                player_ship=player_ship(hull=20),
                enemy_ship={"hull": {"current": 5}},
            )
        ),
        rec(obs=obs_dict(map={"sector": 8}, enemy_ship=None)),  # kill registered
    ]
    sc = scenario(
        [
            sub("sector", target=8, kind="threshold", weight=2.0),
            sub("enemy_defeated", target=1, kind="boolean", weight=1.0),
        ]
    )
    res = score_instance(records, sc)
    assert res["breakdown"] == {"sector": 1.0, "enemy_defeated": 1.0}
    assert res["r"] == 1.0
    assert res["solved"] is True


# --- Legitimacy gate (anti metric-gaming) ---------------------------------- #
def test_legitimacy_gate_collapses_jump_in_place():
    # The agent jumps repeatedly but stays on the SAME beacon: distinct_beacons == 1,
    # below the scenario's min_distinct_beacons -> reward collapses to 0 despite the
    # sub-objective (many jumps) being fully met.
    records = [
        rec(
            obs=obs_dict(map={"current_pos": {"x": 4, "y": 4}}),
            actions=[{"type": "jump"}],
        )
        for _ in range(8)
    ]
    sc = scenario(
        [sub("jumps", target=8, kind="milestone")],
        min_distinct_beacons=3,
    )
    res = score_instance(records, sc)
    # raw credit would be 1.0, but the gate zeroes it.
    assert res["breakdown"]["jumps"] == 1.0
    assert res["legitimacy_gate"] == 0
    assert res["r"] == 0.0
    assert res["score"] == 0.0
    assert res["solved"] is False
    assert res["achieved"]["distinct_beacons"] == 1


def test_legitimacy_gate_passes_with_enough_distinct_beacons():
    records = [
        rec(
            obs=obs_dict(map={"current_pos": {"x": i, "y": 0}}),
            actions=[{"type": "jump"}],
        )
        for i in range(4)
    ]
    sc = scenario(
        [sub("jumps", target=4, kind="milestone")],
        min_distinct_beacons=3,
    )
    res = score_instance(records, sc)
    assert res["achieved"]["distinct_beacons"] == 4
    assert res["legitimacy_gate"] == 1
    assert res["r"] == 1.0
    assert res["solved"] is True


def test_legitimacy_gate_disabled_when_unset():
    # min_distinct_beacons is None -> the gate never fires, even on a one-beacon run.
    records = [
        rec(obs=obs_dict(map={"current_pos": {"x": 0, "y": 0}}), actions=[{"type": "jump"}])
    ]
    sc = scenario([sub("jumps", target=1, kind="milestone")], min_distinct_beacons=None)
    res = score_instance(records, sc)
    assert res["legitimacy_gate"] == 1
    assert res["solved"] is True


def test_legitimacy_gate_boundary_exactly_at_minimum_passes():
    # distinct_beacons == min_distinct_beacons is NOT below the threshold -> gate passes.
    records = [
        rec(obs=obs_dict(map={"current_pos": {"x": i, "y": 0}}), actions=[{"type": "jump"}])
        for i in range(3)
    ]
    sc = scenario([sub("jumps", target=3, kind="milestone")], min_distinct_beacons=3)
    res = score_instance(records, sc)
    assert res["achieved"]["distinct_beacons"] == 3
    assert res["legitimacy_gate"] == 1


def test_legitimacy_gate_one_below_minimum_fails():
    records = [
        rec(obs=obs_dict(map={"current_pos": {"x": i, "y": 0}}), actions=[{"type": "jump"}])
        for i in range(2)
    ]
    sc = scenario([sub("jumps", target=2, kind="milestone")], min_distinct_beacons=3)
    res = score_instance(records, sc)
    assert res["achieved"]["distinct_beacons"] == 2
    assert res["legitimacy_gate"] == 0
    assert res["r"] == 0.0


# --- Edge cases ------------------------------------------------------------ #
def test_score_instance_empty_goal_uses_unit_denominator():
    # Empty goal -> sum of weights is 0, source falls back to 1.0 denominator.
    # raw stays 0 -> score 0, but no crash and not "solved".
    records = [rec(obs=obs_dict(map={"sector": 3}))]
    sc = scenario([])
    res = score_instance(records, sc)
    assert res["r"] == 0.0
    assert res["breakdown"] == {}
    assert res["solved"] is False


def test_score_instance_empty_trajectory():
    sc = scenario([sub("sector", target=5, kind="threshold")])
    res = score_instance([], sc)
    assert res["r"] == 0.0
    assert res["solved"] is False
    assert res["achieved"]["sector"] == 0


def test_score_instance_short_trajectory_single_record():
    records = [rec(obs=obs_dict(map={"sector": 1}))]
    sc = scenario([sub("sector", target=1, kind="threshold")])
    res = score_instance(records, sc)
    assert res["solved"] is True
    assert math.isclose(res["score"], 100.0)


def test_score_instance_breakdown_rounded_to_three_places():
    # sector 1 of 3 -> 0.333... must be rounded to 3 dp in the breakdown.
    records = [rec(obs=obs_dict(map={"sector": 1}))]
    sc = scenario([sub("sector", target=3, kind="threshold")])
    res = score_instance(records, sc)
    assert res["breakdown"]["sector"] == 0.333


def test_score_instance_r_and_score_rounding():
    # 1 of 3 sectors -> r ~= 0.3333 rounded to 4dp, score to 1dp.
    records = [rec(obs=obs_dict(map={"sector": 1}))]
    sc = scenario([sub("sector", target=3, kind="threshold")])
    res = score_instance(records, sc)
    assert res["r"] == 0.3333
    assert res["score"] == 33.3


def test_score_instance_solved_requires_full_credit_not_just_high():
    # 0.999... credit must NOT count as solved (solved needs r >= 1 - 1e-9).
    records = [rec(obs=obs_dict(map={"sector": 999}))]
    sc = scenario([sub("sector", target=1000, kind="threshold")])
    res = score_instance(records, sc)
    assert res["r"] < 1.0
    assert res["solved"] is False
