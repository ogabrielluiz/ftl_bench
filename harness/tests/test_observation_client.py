import json
from pathlib import Path

import pytest

from ftl_bench.observation import (
    ObservationClient,
    Observation,
    ObservationValidationError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "observation_sample.json"


def test_read_latest_returns_observation():
    client = ObservationClient(FIXTURE)
    obs = client.read_latest()
    assert isinstance(obs, Observation)
    assert obs.tick == 120
    assert obs.seed == 1234567
    assert obs.game_started is True


def test_player_ship_hull_parsed():
    obs = ObservationClient(FIXTURE).read_latest()
    assert obs.player_ship["hull"]["current"] == 30
    assert obs.player_ship["hull"]["max"] == 30


def test_enemy_ship_is_none_when_null():
    obs = ObservationClient(FIXTURE).read_latest()
    assert obs.enemy_ship is None


def test_missing_file_raises():
    client = ObservationClient(Path("/nonexistent/observation.json"))
    with pytest.raises(FileNotFoundError):
        client.read_latest()


def test_schema_version_mismatch_raises(tmp_path):
    bad = tmp_path / "obs.json"
    bad.write_text(json.dumps({"schema_version": 999, "tick": 1, "seed": 0,
                               "game_started": False}))
    client = ObservationClient(bad)
    with pytest.raises(ObservationValidationError):
        client.read_latest()


def test_missing_required_field_raises(tmp_path):
    bad = tmp_path / "obs.json"
    bad.write_text(json.dumps({"schema_version": 1, "tick": 1}))
    client = ObservationClient(bad)
    with pytest.raises(ObservationValidationError):
        client.read_latest()


def test_changing_state_detected(tmp_path):
    p = tmp_path / "obs.json"
    p.write_text(json.dumps({"schema_version": 1, "tick": 10, "seed": 1,
                             "game_started": True}))
    client = ObservationClient(p)
    first = client.read_latest()
    p.write_text(json.dumps({"schema_version": 1, "tick": 20, "seed": 1,
                             "game_started": True}))
    second = client.read_latest()
    assert first.tick == 10
    assert second.tick == 20
