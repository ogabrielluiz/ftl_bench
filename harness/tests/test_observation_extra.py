"""Extra coverage for ftl_bench.observation.

Targets the gaps not covered by test_session.py: Observation.from_dict on
varied payloads, the ObservationValidationError paths (missing fields,
unsupported schema_version, invalid JSON, non-dict root), and the
ObservationClient.read_latest read-retry loop on transient
PermissionError/OSError before succeeding.
"""
import json
from pathlib import Path

import pytest

from ftl_bench import (
    Observation,
    ObservationClient,
    ObservationValidationError,
)
from ftl_bench.observation import (
    REQUIRED_FIELDS,
    SUPPORTED_SCHEMA_VERSIONS,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _minimal_payload(**overrides):
    """A valid observation dict containing only the required fields."""
    data = {
        "schema_version": 2,
        "tick": 0,
        "seed": 0,
        "game_started": False,
    }
    data.update(overrides)
    return data


def _write_obs_file(folder: Path, payload) -> Path:
    p = folder / "ftl_agent_observation.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# Observation.from_dict — happy paths / defaults
# --------------------------------------------------------------------------- #
def test_from_dict_minimal_applies_defaults():
    obs = Observation.from_dict(_minimal_payload())
    assert obs.schema_version == 2
    assert obs.tick == 0
    assert obs.seed == 0
    assert obs.game_started is False
    # Optional fields default to their declared values.
    assert obs.paused is False
    assert obs.choice_box_open is False
    assert obs.game_over is False
    assert obs.last_action_seq is None
    assert obs.player_ship is None
    assert obs.enemy_ship is None
    assert obs.map is None
    assert obs.event is None


def test_from_dict_reads_game_over_flag():
    # The bridge sets game_over when the run has ended (crew dead / ship lost / win); the harness
    # uses it to hard-restart instead of spinning the menu-return actions at the GAME OVER screen.
    assert Observation.from_dict(_minimal_payload(game_over=True)).game_over is True
    assert Observation.from_dict(_minimal_payload(game_over=False)).game_over is False


def test_from_dict_preserves_raw_payload():
    payload = _minimal_payload(extra_unmodeled_key={"nested": [1, 2, 3]})
    obs = Observation.from_dict(payload)
    # raw must be the exact dict passed in (identity), unmodeled keys survive.
    assert obs.raw is payload
    assert obs.raw["extra_unmodeled_key"] == {"nested": [1, 2, 3]}


def test_from_dict_full_payload_maps_every_field():
    player = {"hull": {"current": 30, "max": 30}}
    enemy = {"hull": {"current": 10, "max": 18}}
    game_map = {"nodes": [{"id": 0}], "current": 0}
    event = {"text": "A distress beacon", "choices": [{"text": "Investigate"}]}
    payload = _minimal_payload(
        schema_version=3,
        tick=42,
        seed=12345,
        game_started=True,
        paused=True,
        choice_box_open=True,
        last_action_seq=7,
        player_ship=player,
        enemy_ship=enemy,
        map=game_map,
        event=event,
    )
    obs = Observation.from_dict(payload)
    assert obs.schema_version == 3
    assert obs.tick == 42
    assert obs.seed == 12345
    assert obs.game_started is True
    assert obs.paused is True
    assert obs.choice_box_open is True
    assert obs.last_action_seq == 7
    assert obs.player_ship is player
    assert obs.enemy_ship is enemy
    assert obs.map is game_map
    assert obs.event is event


@pytest.mark.parametrize("version", SUPPORTED_SCHEMA_VERSIONS)
def test_from_dict_accepts_every_supported_schema_version(version):
    obs = Observation.from_dict(_minimal_payload(schema_version=version))
    assert obs.schema_version == version


def test_from_dict_last_action_seq_zero_is_preserved_not_coerced_to_none():
    # last_action_seq=0 is a real ack key and must not be lost via a truthiness bug.
    obs = Observation.from_dict(_minimal_payload(last_action_seq=0))
    assert obs.last_action_seq == 0


def test_from_dict_explicit_false_optionals_kept_false():
    obs = Observation.from_dict(
        _minimal_payload(paused=False, choice_box_open=False)
    )
    assert obs.paused is False
    assert obs.choice_box_open is False


# --------------------------------------------------------------------------- #
# Observation.from_dict — validation error paths
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("missing", REQUIRED_FIELDS)
def test_from_dict_missing_required_field_raises(missing):
    payload = _minimal_payload()
    del payload[missing]
    with pytest.raises(ObservationValidationError) as exc:
        Observation.from_dict(payload)
    assert "missing required field" in str(exc.value)
    assert repr(missing) in str(exc.value)


def test_from_dict_empty_dict_reports_first_missing_field():
    with pytest.raises(ObservationValidationError) as exc:
        Observation.from_dict({})
    # REQUIRED_FIELDS is checked in order; schema_version is first.
    assert repr(REQUIRED_FIELDS[0]) in str(exc.value)


@pytest.mark.parametrize("bad_version", [0, 4, 99, -1])
def test_from_dict_unsupported_schema_version_raises(bad_version):
    with pytest.raises(ObservationValidationError) as exc:
        Observation.from_dict(_minimal_payload(schema_version=bad_version))
    msg = str(exc.value)
    assert "unsupported schema_version" in msg
    assert str(bad_version) in msg


def test_validation_error_is_a_value_error_subclass():
    # Callers may catch the broader ValueError; lock in the hierarchy.
    assert issubclass(ObservationValidationError, ValueError)
    with pytest.raises(ValueError):
        Observation.from_dict(_minimal_payload(schema_version=999))


# --------------------------------------------------------------------------- #
# ObservationClient.read_latest — happy path & validation
# --------------------------------------------------------------------------- #
def test_read_latest_returns_observation(tmp_path):
    _write_obs_file(tmp_path, _minimal_payload(tick=5, game_started=True))
    client = ObservationClient(tmp_path / "ftl_agent_observation.json")
    obs = client.read_latest()
    assert isinstance(obs, Observation)
    assert obs.tick == 5
    assert obs.game_started is True


def test_client_accepts_str_path_and_stores_as_path(tmp_path):
    target = tmp_path / "ftl_agent_observation.json"
    _write_obs_file(tmp_path, _minimal_payload())
    client = ObservationClient(str(target))
    assert isinstance(client.path, Path)
    assert client.path == target
    assert isinstance(client.read_latest(), Observation)


def test_read_latest_missing_file_raises_filenotfound(tmp_path, monkeypatch):
    # A briefly-absent obs file (just after a restart) is retried and re-raised after the budget.
    import ftl_bench.observation as obs_mod
    monkeypatch.setattr(obs_mod.time, "sleep", lambda *_a, **_k: None)
    client = ObservationClient(tmp_path / "does_not_exist.json")
    with pytest.raises(FileNotFoundError):
        client.read_latest()


def test_read_latest_retries_after_missing_file_then_succeeds(tmp_path, monkeypatch):
    # The restart window: the file is briefly absent, then the bridge re-creates it. The same
    # retry loop that absorbs PermissionError now absorbs FileNotFoundError (an OSError subclass).
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("{}", encoding="utf-8")
    calls, _ = _patch_read_text_failing_then_ok(
        monkeypatch,
        [FileNotFoundError("absent"), FileNotFoundError("absent")],
        _minimal_payload(tick=7),
    )
    obs = ObservationClient(p).read_latest()
    assert obs.tick == 7
    assert calls["n"] == 3


def test_read_latest_invalid_json_raises_validation_error(tmp_path):
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("{not valid json", encoding="utf-8")
    client = ObservationClient(p)
    with pytest.raises(ObservationValidationError) as exc:
        client.read_latest()
    assert "invalid JSON" in str(exc.value)


def test_read_latest_empty_file_raises_validation_error(tmp_path):
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("", encoding="utf-8")
    client = ObservationClient(p)
    with pytest.raises(ObservationValidationError) as exc:
        client.read_latest()
    assert "invalid JSON" in str(exc.value)


@pytest.mark.parametrize(
    "json_text",
    ["[1, 2, 3]", '"a string"', "42", "true", "null"],
)
def test_read_latest_non_dict_root_raises_validation_error(tmp_path, json_text):
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text(json_text, encoding="utf-8")
    client = ObservationClient(p)
    with pytest.raises(ObservationValidationError) as exc:
        client.read_latest()
    assert "observation root must be a JSON object" in str(exc.value)


def test_read_latest_propagates_validation_error_from_from_dict(tmp_path):
    # A well-formed-but-invalid observation surfaces from_dict's error.
    _write_obs_file(tmp_path, _minimal_payload(schema_version=99))
    client = ObservationClient(tmp_path / "ftl_agent_observation.json")
    with pytest.raises(ObservationValidationError) as exc:
        client.read_latest()
    assert "unsupported schema_version" in str(exc.value)


# --------------------------------------------------------------------------- #
# ObservationClient.read_latest — transient read-retry loop
# --------------------------------------------------------------------------- #
def _patch_read_text_failing_then_ok(monkeypatch, exceptions, payload):
    """Make Path.read_text raise each item in `exceptions`, then return JSON.

    Returns a one-element list holding the call count, plus patches
    time.sleep (in the observation module) to a no-op so the test is fast.
    """
    calls = {"n": 0}
    good_text = json.dumps(payload)
    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        idx = calls["n"]
        calls["n"] += 1
        if idx < len(exceptions):
            raise exceptions[idx]
        return good_text

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    # Don't actually sleep between retries.
    import ftl_bench.observation as obs_mod

    monkeypatch.setattr(obs_mod.time, "sleep", lambda *_a, **_k: None)
    return calls, real_read_text


def test_read_latest_retries_after_permission_error_then_succeeds(
    tmp_path, monkeypatch
):
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("{}", encoding="utf-8")  # must exist for the exists() gate
    calls, _ = _patch_read_text_failing_then_ok(
        monkeypatch,
        [PermissionError("WinError 5"), PermissionError("WinError 5")],
        _minimal_payload(tick=9),
    )
    client = ObservationClient(p)
    obs = client.read_latest()
    assert obs.tick == 9
    # Two failures + one success.
    assert calls["n"] == 3


def test_read_latest_retries_after_oserror_then_succeeds(tmp_path, monkeypatch):
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("{}", encoding="utf-8")
    calls, _ = _patch_read_text_failing_then_ok(
        monkeypatch,
        [OSError("transient drvfs"), OSError("transient drvfs")],
        _minimal_payload(tick=3, game_started=True),
    )
    client = ObservationClient(p)
    obs = client.read_latest()
    assert obs.tick == 3
    assert obs.game_started is True
    assert calls["n"] == 3


def test_read_latest_succeeds_on_final_allowed_attempt(tmp_path, monkeypatch):
    # The loop runs for attempt in range(9): attempts 0..7 raise, attempt 8 succeeds.
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("{}", encoding="utf-8")
    eight_failures = [PermissionError("x") for _ in range(8)]
    calls, _ = _patch_read_text_failing_then_ok(
        monkeypatch, eight_failures, _minimal_payload(tick=1)
    )
    client = ObservationClient(p)
    obs = client.read_latest()
    assert obs.tick == 1
    assert calls["n"] == 9  # 8 failures + 1 success on the last attempt


def test_read_latest_reraises_after_exhausting_retries(tmp_path, monkeypatch):
    # Nine failures: every attempt (0..8) raises, so attempt 8 must re-raise.
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("{}", encoding="utf-8")
    sentinel = PermissionError("persistent sharing violation")
    nine_failures = [sentinel] + [PermissionError("x") for _ in range(8)]
    calls, _ = _patch_read_text_failing_then_ok(
        monkeypatch, nine_failures, _minimal_payload()
    )
    client = ObservationClient(p)
    with pytest.raises(PermissionError):
        client.read_latest()
    # range(9) => exactly 9 read attempts before giving up.
    assert calls["n"] == 9


def test_read_latest_reraises_oserror_after_exhausting_retries(
    tmp_path, monkeypatch
):
    p = tmp_path / "ftl_agent_observation.json"
    p.write_text("{}", encoding="utf-8")
    nine_failures = [OSError("persistent") for _ in range(9)]
    calls, _ = _patch_read_text_failing_then_ok(
        monkeypatch, nine_failures, _minimal_payload()
    )
    client = ObservationClient(p)
    with pytest.raises(OSError):
        client.read_latest()
    assert calls["n"] == 9


def test_read_latest_does_not_sleep_on_first_successful_read(
    tmp_path, monkeypatch
):
    p = tmp_path / "ftl_agent_observation.json"
    _write_obs_file(tmp_path, _minimal_payload())
    slept = {"n": 0}
    import ftl_bench.observation as obs_mod

    monkeypatch.setattr(
        obs_mod.time, "sleep", lambda *_a, **_k: slept.__setitem__("n", slept["n"] + 1)
    )
    ObservationClient(p).read_latest()
    assert slept["n"] == 0
