"""Tests for trajectory scoring against synthetic records."""
from ftl_bench import score_trajectory
from ftl_bench.scoring import score_observation
from ftl_bench.observation import Observation


def _rec(actions=None, enemy_hull=None, phull=30, sector=0, scrap=0, started=True):
    enemy = None
    if enemy_hull is not None:
        enemy = {"hull": {"current": enemy_hull, "max": 10}}
    return {
        "i": 0, "kind": "step", "actions": actions or [],
        "obs": {
            "game_started": started,
            "player_ship": {"hull": {"current": phull, "max": 30},
                            "resources": {"scrap": scrap}},
            "enemy_ship": enemy,
            "map": {"sector": sector},
        },
    }


def test_counts_jumps_and_events():
    recs = [
        {"kind": "meta", "meta": {}},
        _rec(actions=[{"type": "jump", "beacon_index": 0}]),
        _rec(actions=[{"type": "choose_event", "choice_index": 1}]),
        _rec(actions=[{"type": "jump", "beacon_index": 2}]),
    ]
    s = score_trajectory(recs)
    assert s["decisions"] == 3  # meta excluded
    assert s["jumps"] == 2
    assert s["events"] == 1


def test_counts_kill_on_hull_to_zero():
    recs = [
        _rec(enemy_hull=8),   # enemy alive
        _rec(enemy_hull=3),   # still alive
        _rec(enemy_hull=0),   # destroyed -> kill
        _rec(enemy_hull=None),  # gone, no double-count
    ]
    assert score_trajectory(recs)["kills"] == 1


def test_counts_kill_on_enemy_gone():
    recs = [_rec(enemy_hull=5), _rec(enemy_hull=None)]
    assert score_trajectory(recs)["kills"] == 1


def test_no_kill_without_prior_enemy():
    recs = [_rec(enemy_hull=None), _rec(enemy_hull=None)]
    assert score_trajectory(recs)["kills"] == 0


def test_final_fields_and_survival():
    recs = [_rec(phull=20, scrap=15, sector=2)]
    s = score_trajectory(recs)
    assert s["final_hull"] == 20
    assert s["final_scrap"] == 15
    assert s["final_sector"] == 2
    assert s["alive"] is True


def test_score_observation():
    obs = Observation.from_dict({
        "schema_version": 3, "tick": 1, "seed": 0, "game_started": True,
        "player_ship": {"hull": {"current": 25, "max": 30},
                        "resources": {"scrap": 9, "fuel": 7}},
        "map": {"sector": 1},
        "enemy_ship": {"hull": {"current": 4}},
    })
    s = score_observation(obs)
    assert s["hull"] == 25 and s["scrap"] == 9 and s["alive"] is True
    assert s["in_combat"] is True and s["sector"] == 1
