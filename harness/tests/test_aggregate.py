"""Tests for the HEADLINE leaderboard metric: ftl_bench.aggregate.aggregate().

aggregate() takes a list of score_instance()-shaped result dicts plus the Scenario
objects (used only for the per-tier breakdown) and returns the headline numbers:
the mean FTL native run score, its +/- standard error, the solve rate / pct / count,
the median jumps per instance, and the by_type / by_tier breakdowns.

These tests pin the ACTUAL contract of aggregate.py. The result dicts mirror the keys
score_instance() emits (scenario, type, solved, ftl_score, jumps_used, ...). Scenario
objects are the real package dataclass so the tier lookup is exercised faithfully.
"""
import math

from ftl_bench import Scenario, SubObjective
from ftl_bench.aggregate import aggregate


# --- helpers ---------------------------------------------------------------

def make_result(
    scenario="s0",
    type="reach_sector",
    *,
    ftl_score=0,
    solved=False,
    jumps_used=0,
):
    """A minimal result dict shaped like scoring.score_instance() output.

    aggregate() reads: ftl_score (via .get default 0), solved (direct key),
    jumps_used (via .get default 0), type (direct key), scenario (direct key).
    """
    return {
        "scenario": scenario,
        "type": type,
        "ftl_score": ftl_score,
        "solved": solved,
        "jumps_used": jumps_used,
    }


def make_scenario(id="s0", tier="public", type="reach_sector"):
    """Real package Scenario; aggregate() only reads .id and .tier off these."""
    return Scenario(
        id=id,
        type=type,
        seed=0,
        goal=[SubObjective(key="progress", target=1, kind="milestone")],
        tier=tier,
    )


# --- empty results ---------------------------------------------------------

def test_empty_results_returns_minimal_dict():
    out = aggregate([], [])
    assert out == {"ftl_score_mean": None, "ftl_score_median": None,
                   "solve_rate": "0/0", "instances": 0}


def test_empty_results_ignores_scenarios():
    # Scenarios present but no results -> still the minimal empty shape.
    out = aggregate([], [make_scenario("s0")])
    assert out["ftl_score_mean"] is None
    assert out["instances"] == 0
    # The rich keys are absent on the empty path.
    assert "headline" not in out
    assert "by_type" not in out


# --- mean FTL score --------------------------------------------------------

def test_ftl_score_mean_is_rounded_mean():
    results = [
        make_result("s0", ftl_score=10),
        make_result("s1", ftl_score=20),
        make_result("s2", ftl_score=30),
    ]
    scen = [make_scenario("s0"), make_scenario("s1"), make_scenario("s2")]
    out = aggregate(results, scen)
    assert out["ftl_score_mean"] == 20.0


def test_ftl_score_mean_rounds_to_two_decimals():
    # mean(10,20,21) = 17.0 exactly; use values that need rounding: (1,2) -> 1.5,
    # and (10, 11, 13) -> 11.333... -> 11.33
    results = [
        make_result("s0", ftl_score=10),
        make_result("s1", ftl_score=11),
        make_result("s2", ftl_score=13),
    ]
    scen = [make_scenario("s0"), make_scenario("s1"), make_scenario("s2")]
    out = aggregate(results, scen)
    assert out["ftl_score_mean"] == 11.33


def test_ftl_score_defaults_to_zero_when_missing():
    # A result without an ftl_score key contributes 0 (via .get default).
    r = {"scenario": "s0", "type": "t", "solved": False, "jumps_used": 0}
    out = aggregate([r], [make_scenario("s0")])
    assert out["ftl_score_mean"] == 0.0


# --- standard error --------------------------------------------------------

def test_standard_error_multiple_instances():
    results = [
        make_result("s0", ftl_score=10),
        make_result("s1", ftl_score=20),
        make_result("s2", ftl_score=30),
    ]
    scen = [make_scenario("s0"), make_scenario("s1"), make_scenario("s2")]
    out = aggregate(results, scen)
    # stdev([10,20,30]) = 10.0; SE = 10/sqrt(3) = 5.7735... -> 5.77
    assert out["ftl_score_SE"] == 5.77


def test_standard_error_two_instances():
    results = [make_result("s0", ftl_score=10), make_result("s1", ftl_score=20)]
    scen = [make_scenario("s0"), make_scenario("s1")]
    out = aggregate(results, scen)
    # stdev([10,20]) = 7.0710...; SE = /sqrt(2) = 5.0
    assert out["ftl_score_SE"] == 5.0


def test_single_instance_standard_error_is_zero():
    # n == 1: stdev is undefined, code short-circuits to 0.0 (no ValueError).
    out = aggregate([make_result("s0", ftl_score=42.5)], [make_scenario("s0")])
    assert out["ftl_score_SE"] == 0.0
    assert out["ftl_score_mean"] == 42.5


def test_standard_error_is_a_float():
    out = aggregate([make_result("s0", ftl_score=5)], [make_scenario("s0")])
    assert isinstance(out["ftl_score_SE"], float)


# --- headline string -------------------------------------------------------

def test_headline_string_format():
    results = [
        make_result("s0", ftl_score=10, solved=True),
        make_result("s1", ftl_score=20, solved=False),
        make_result("s2", ftl_score=30, solved=True),
    ]
    scen = [make_scenario("s0"), make_scenario("s1"), make_scenario("s2")]
    out = aggregate(results, scen)
    # statistics.mean over int scores with an exact-integer result returns an int,
    # so the headline renders "20" (not "20.0"); two spaces flank the pipe.
    assert out["headline"] == "FTL score 20 ± 5.77  |  Solve 2/3"


def test_headline_single_instance():
    out = aggregate([make_result("s0", ftl_score=7, solved=False)], [make_scenario("s0")])
    assert out["headline"] == "FTL score 7 ± 0.0  |  Solve 0/1"


def test_headline_renders_float_mean_with_decimal():
    # A non-integer mean keeps its decimal in the headline.
    results = [make_result("s0", ftl_score=10), make_result("s1", ftl_score=15)]
    scen = [make_scenario("s0"), make_scenario("s1")]
    out = aggregate(results, scen)
    assert out["headline"].startswith("FTL score 12.5 ± ")


# --- solve rate / pct / count ----------------------------------------------

def test_solve_rate_and_pct_and_count():
    results = [
        make_result("s0", solved=True),
        make_result("s1", solved=True),
        make_result("s2", solved=False),
        make_result("s3", solved=False),
    ]
    scen = [make_scenario(f"s{i}") for i in range(4)]
    out = aggregate(results, scen)
    assert out["solve_rate"] == "2/4"
    assert out["solve_pct"] == 50.0
    assert out["instances"] == 4


def test_solve_pct_rounds_to_one_decimal():
    # 1/3 solved -> 33.333... -> 33.3
    results = [
        make_result("s0", solved=True),
        make_result("s1", solved=False),
        make_result("s2", solved=False),
    ]
    scen = [make_scenario(f"s{i}") for i in range(3)]
    out = aggregate(results, scen)
    assert out["solve_pct"] == 33.3


def test_all_solved():
    results = [make_result("s0", solved=True), make_result("s1", solved=True)]
    scen = [make_scenario("s0"), make_scenario("s1")]
    out = aggregate(results, scen)
    assert out["solve_rate"] == "2/2"
    assert out["solve_pct"] == 100.0


def test_none_solved():
    results = [make_result("s0", solved=False), make_result("s1", solved=False)]
    scen = [make_scenario("s0"), make_scenario("s1")]
    out = aggregate(results, scen)
    assert out["solve_rate"] == "0/2"
    assert out["solve_pct"] == 0.0


# --- median jumps per instance ---------------------------------------------

def test_median_jumps_odd_count():
    results = [
        make_result("s0", jumps_used=1),
        make_result("s1", jumps_used=3),
        make_result("s2", jumps_used=9),
    ]
    scen = [make_scenario(f"s{i}") for i in range(3)]
    out = aggregate(results, scen)
    assert out["median_jumps_per_instance"] == 3.0


def test_median_jumps_even_count_averages_middle_two():
    results = [
        make_result("s0", jumps_used=2),
        make_result("s1", jumps_used=4),
        make_result("s2", jumps_used=6),
        make_result("s3", jumps_used=8),
    ]
    scen = [make_scenario(f"s{i}") for i in range(4)]
    out = aggregate(results, scen)
    # median of [2,4,6,8] = (4+6)/2 = 5.0
    assert out["median_jumps_per_instance"] == 5.0


def test_median_jumps_defaults_to_zero_when_missing():
    # Missing jumps_used -> 0 via .get default; median of [0] = 0.0
    r = {"scenario": "s0", "type": "t", "solved": False, "ftl_score": 0}
    out = aggregate([r], [make_scenario("s0")])
    assert out["median_jumps_per_instance"] == 0.0


def test_median_jumps_single_instance():
    out = aggregate([make_result("s0", jumps_used=7)], [make_scenario("s0")])
    assert out["median_jumps_per_instance"] == 7.0


# --- by_type breakdown -----------------------------------------------------

def test_by_type_groups_and_aggregates():
    results = [
        make_result("s0", type="reach_sector", ftl_score=10, solved=True, jumps_used=2),
        make_result("s1", type="reach_sector", ftl_score=30, solved=False, jumps_used=4),
        make_result("s2", type="defeat_enemy", ftl_score=50, solved=True, jumps_used=6),
    ]
    scen = [
        make_scenario("s0", type="reach_sector"),
        make_scenario("s1", type="reach_sector"),
        make_scenario("s2", type="defeat_enemy"),
    ]
    out = aggregate(results, scen)
    by_type = out["by_type"]
    assert set(by_type) == {"reach_sector", "defeat_enemy"}
    assert by_type["reach_sector"] == {"ftl_score": 20.0, "solved": 1, "n": 2}
    assert by_type["defeat_enemy"] == {"ftl_score": 50.0, "solved": 1, "n": 1}


def test_by_type_is_sorted_by_key():
    results = [
        make_result("s0", type="zeta"),
        make_result("s1", type="alpha"),
        make_result("s2", type="mike"),
    ]
    scen = [
        make_scenario("s0", type="zeta"),
        make_scenario("s1", type="alpha"),
        make_scenario("s2", type="mike"),
    ]
    out = aggregate(results, scen)
    assert list(out["by_type"]) == ["alpha", "mike", "zeta"]


def test_by_type_single_type():
    results = [
        make_result("s0", type="reach_sector", ftl_score=12, solved=True),
        make_result("s1", type="reach_sector", ftl_score=8, solved=False),
    ]
    scen = [make_scenario("s0", type="reach_sector"), make_scenario("s1", type="reach_sector")]
    out = aggregate(results, scen)
    assert out["by_type"] == {"reach_sector": {"ftl_score": 10.0, "solved": 1, "n": 2}}


# --- by_tier breakdown -----------------------------------------------------

def test_by_tier_groups_by_scenario_tier():
    results = [
        make_result("pub0", ftl_score=10, solved=True),
        make_result("pub1", ftl_score=20, solved=False),
        make_result("priv0", ftl_score=40, solved=True),
    ]
    scen = [
        make_scenario("pub0", tier="public"),
        make_scenario("pub1", tier="public"),
        make_scenario("priv0", tier="private"),
    ]
    out = aggregate(results, scen)
    by_tier = out["by_tier"]
    assert by_tier["public"] == {"ftl_score": 15.0, "solved": 1, "n": 2}
    assert by_tier["private"] == {"ftl_score": 40.0, "solved": 1, "n": 1}


def test_by_tier_unknown_scenario_falls_back_to_question_mark():
    # A result whose scenario id is not in the scenarios list -> tier "?".
    results = [make_result("ghost", ftl_score=5, solved=False)]
    out = aggregate(results, [make_scenario("known", tier="public")])
    assert "?" in out["by_tier"]
    assert out["by_tier"]["?"]["n"] == 1


def test_by_tier_is_sorted_by_key():
    results = [
        make_result("a", ftl_score=1),
        make_result("b", ftl_score=2),
        make_result("c", ftl_score=3),
    ]
    scen = [
        make_scenario("a", tier="semi_private"),
        make_scenario("b", tier="dev"),
        make_scenario("c", tier="public"),
    ]
    out = aggregate(results, scen)
    assert list(out["by_tier"]) == ["dev", "public", "semi_private"]


# --- structural / integration ----------------------------------------------

def test_full_result_keys_present():
    out = aggregate([make_result("s0", ftl_score=10, solved=True)], [make_scenario("s0")])
    expected_keys = {
        "ftl_score_mean",
        "ftl_score_SE",
        "headline",
        "solve_rate",
        "solve_pct",
        "instances",
        "median_jumps_per_instance",
        "by_type",
        "by_tier",
    }
    assert expected_keys <= set(out)


def test_breakdown_solved_counts_match_total():
    results = [
        make_result("s0", type="a", ftl_score=10, solved=True),
        make_result("s1", type="a", ftl_score=20, solved=False),
        make_result("s2", type="b", ftl_score=30, solved=True),
    ]
    scen = [
        make_scenario("s0", type="a", tier="public"),
        make_scenario("s1", type="a", tier="public"),
        make_scenario("s2", type="b", tier="private"),
    ]
    out = aggregate(results, scen)
    total_solved = sum(g["solved"] for g in out["by_type"].values())
    assert total_solved == 2
    total_n = sum(g["n"] for g in out["by_type"].values())
    assert total_n == out["instances"]
    # Same totals must hold across the tier breakdown.
    assert sum(g["n"] for g in out["by_tier"].values()) == out["instances"]
    assert sum(g["solved"] for g in out["by_tier"].values()) == total_solved


def test_negative_ftl_scores_handled():
    # FTL native score can dip (e.g. penalties); mean/SE must still compute.
    results = [
        make_result("s0", ftl_score=-10),
        make_result("s1", ftl_score=10),
    ]
    scen = [make_scenario("s0"), make_scenario("s1")]
    out = aggregate(results, scen)
    assert out["ftl_score_mean"] == 0.0
    # stdev([-10, 10]) = 14.142...; SE = /sqrt(2) = 10.0
    assert math.isclose(out["ftl_score_SE"], 10.0, abs_tol=0.01)
