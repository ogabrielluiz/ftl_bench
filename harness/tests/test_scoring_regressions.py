"""Benchmark outcomes must follow observed game changes, not acknowledged intentions."""
from ftl_bench import (Observation, Scenario, SubObjective, achieved_metrics, load_suite,
                       score_instance, score_observation)
from ftl_bench.cli import _bench_root


REPO = _bench_root()


def state(sector=0, x=0, *, hull=30, **extra):
    return {
        "game_started": True,
        "map": {"sector": sector, "current_pos": {"x": x, "y": 0}},
        "player_ship": {"hull": {"current": hull}, "crew": [{"dead": False}]},
        **extra,
    }


def record(obs, action=None, kind="step"):
    return {"kind": kind, "obs": obs, "actions": [action] if action else []}


def test_score_uses_current_episode_final_value_and_ignores_menu_snapshots():
    records = [record(state(ftl_score=900)), record(state(ftl_score=59, game_over=True)),
               record({"game_started": False, "ftl_score": 1200}, kind="cleanup")]
    assert achieved_metrics(records)["ftl_score"] == 59


def test_refused_jumps_cannot_solve_the_public_survival_probe():
    scenario = load_suite(REPO / "scenarios" / "suite_v1.json")[0]
    records = [record(state(x=i)) for i in range(4)]
    records += [record(state(x=3), {"type": "jump"}) for _ in range(8)]
    result = score_instance(records, scenario)
    assert result["achieved"]["distinct_beacons"] == 4
    assert result["jumps_used"] == 3
    assert result["solved"] is False


def test_sector_pumping_counts_one_crossing_and_one_jump():
    records = [record(state(), kind="reset_episode")]
    records += [record(state(), {"type": "leave_sector"}) for _ in range(5)]
    records.append(record(state(sector=1), {"type": "leave_sector"}))
    metrics = achieved_metrics(records)
    assert metrics["sectors_crossed"] == 1
    assert metrics["jumps"] == 1
    assert metrics["distinct_beacons"] == 2  # identical coordinates in different sectors


def test_missing_map_fields_never_fall_back_to_action_credit():
    records = [record({"game_started": True}, {"type": "jump"}) for _ in range(10)]
    metrics = achieved_metrics(records)
    assert metrics["jumps"] == metrics["distinct_beacons"] == 0


def test_a_warp_snapshot_does_not_double_count_its_settled_arrival():
    records = [record(state(), kind="reset_episode"),
               record({**state(sector=1), "map": {"sector": 1}}),
               record(state(sector=1, x=10))]
    assert achieved_metrics(records)["jumps"] == 1


def test_unsupported_flagship_phase_guess_and_gameover_are_not_victory():
    scenario = load_suite(REPO / "scenarios" / "full_game.json")[0]
    records = [record(state(sector=7, x=i)) for i in range(6)]
    records.append(record(state(sector=7, x=5, game_over=True,
                                flagship={"phase": 3, "stage": 3})))
    result = score_instance(records, scenario)
    assert result["achieved"]["progress"] == 8
    assert result["solved"] is False


def test_verified_victory_scores_all_eight_sectors_and_three_phases():
    scenario = load_suite(REPO / "scenarios" / "full_game.json")[0]
    records = [record(state(sector=7, x=i)) for i in range(6)]
    records.append(record(state(sector=7, x=5, game_over=True, victory=True)))
    result = score_instance(records, scenario)
    assert result["achieved"]["progress"] == 11
    assert result["solved"] is True


def test_concession_keeps_native_score_but_cannot_solve_an_achieved_goal():
    scenario = Scenario("probe", "reach_sector", 1, [SubObjective("sector", 1)])
    records = [record(state(sector=1, ftl_score=123), {"type": "give_up"})]
    result = score_instance(records, scenario)
    assert result["ftl_score"] == 123
    assert result["solved"] is False


def test_failed_or_stalled_attempt_cannot_solve_an_achieved_goal():
    scenario = Scenario("probe", "reach_sector", 1, [SubObjective("sector", 1)])
    for terminal in ({"status": "error", "reason": "agent_error", "error": "oops"},
                     {"status": "completed", "reason": "stalled"}):
        result = score_instance([record(state(sector=1)), {"kind": "end", **terminal}], scenario)
        assert result["solved"] is False
        assert result["reason"] == terminal["reason"]


def test_survival_probe_does_not_award_a_dead_ship():
    scenario = Scenario("survive", "survive_n_jumps", 1, [SubObjective("jumps", 2)])
    records = [record(state(x=0), kind="reset_episode"), record(state(x=1)),
               record(state(x=2, hull=0, game_over=True))]
    assert score_instance(records, scenario)["solved"] is False


def test_menu_cleanup_and_lifecycle_records_preserve_the_last_run_state():
    records = [record(state(sector=2, hull=21)),
               record({"game_started": False}, {"type": "confirm_menu"}),
               {"kind": "end", "status": "completed", "reason": "budget", "obs": None}]
    metrics = achieved_metrics(records)
    assert metrics["final_hull"] == 21
    assert metrics["crew_alive"] == 1


def test_zero_health_crew_is_dead_before_native_death_flag_updates():
    scenario = Scenario("survive", "survive_n_jumps", 1, [SubObjective("jumps", 2)])
    final = state(x=2, hull=21)
    final["player_ship"]["crew"] = [{"dead": False, "health_current": 0}]
    records = [record(state(x=0), kind="reset_episode"), record(state(x=1)), record(final)]
    result = score_instance(records, scenario)
    assert result["achieved"]["crew_alive"] == 0
    assert result["achieved"]["alive"] == 0
    assert result["solved"] is False
    observation = Observation.from_dict({"schema_version": 3, "tick": 1, "seed": 1, **final})
    assert score_observation(observation)["alive"] is False


def test_crew_loss_gameover_with_positive_hull_is_not_alive_in_snapshot():
    final = state(hull=21, game_over=True)
    observation = Observation.from_dict({"schema_version": 3, "tick": 1, "seed": 1, **final})
    assert score_observation(observation)["alive"] is False


def test_hostile_boarder_cannot_count_as_surviving_player_crew():
    final = state(hull=21)
    final["player_ship"]["crew"] = [
        {"player_owned": True, "health_current": 0},
        {"intruder": True, "health_current": 100},
        {"player_owned": False, "health_current": 100, "on_enemy_ship": True},
    ]
    metrics = achieved_metrics([record(final)])
    assert metrics["crew_alive"] == 0
    assert metrics["alive"] == 0


def test_owned_boarders_and_mind_controlled_friendlies_remain_player_crew():
    final = state()
    final["player_ship"]["crew"] = [
        {"player_owned": True, "intruder": True, "on_enemy_ship": True, "health_current": 40},
        {"owner_ship_id": 0, "controllable": False, "mind_controlled": True, "health_current": 50},
        {"intruder": True, "on_enemy_ship": True, "health_current": 60},
    ]
    assert achieved_metrics([record(final)])["crew_alive"] == 3
