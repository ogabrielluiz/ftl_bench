from __future__ import annotations

import json

import pytest

from ftl_bench.config import load_env_file
from ftl_bench import doctor


def test_env_values_are_literal_and_existing_environment_wins(tmp_path, monkeypatch):
    source = tmp_path / ".env.txt"
    source.write_text('TYPESAFE_API_KEY="fixture-secret" # local\nFTL_LITERAL=$(do-not-run)\n', encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "existing-secret")
    monkeypatch.delenv("FTL_LITERAL", raising=False)
    names = load_env_file(source)
    import os
    assert names == ["TYPESAFE_API_KEY", "FTL_LITERAL"]
    assert os.environ["TYPESAFE_API_KEY"] == "existing-secret"
    assert os.environ["FTL_LITERAL"] == "$(do-not-run)"


def test_invalid_env_does_not_print_or_partially_load_secrets(tmp_path, monkeypatch):
    source = tmp_path / ".env.txt"
    source.write_text('FTL_NEW_KEY=fixture-secret\nBAD="unclosed-secret\n', encoding="utf-8")
    monkeypatch.delenv("FTL_NEW_KEY", raising=False)
    with pytest.raises(ValueError) as error:
        load_env_file(source)
    import os
    assert "secret" not in str(error.value)
    assert "FTL_NEW_KEY" not in os.environ


def test_doctor_reports_corrupt_bridge_observations_without_modifying_them(tmp_path, monkeypatch):
    save, game = tmp_path / "save", tmp_path / "game"
    save.mkdir()
    game.mkdir()
    (save / "ftl_bench_dev.lua").write_text("-- bridge", encoding="utf-8")
    observation = save / "ftl_agent_observation.json"
    observation.write_bytes(b"\x00" * 20)
    for name in ("FTLGame.exe", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll"):
        (game / name).touch()
    monkeypatch.setattr(doctor, "ftl_process_alive", lambda: True)
    result = doctor.inspect_installation(user_folder=save, game_dir=game, live=True, full_game=True)
    assert result["ready"] is False
    assert any(c["name"] == "observation" and not c["ok"] for c in result["checks"])
    assert observation.read_bytes() == b"\x00" * 20


def test_doctor_does_not_reveal_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-secret")
    result = doctor.inspect_installation(user_folder=tmp_path, backend="jev")
    assert "fixture-secret" not in json.dumps(result)
    assert next(c for c in result["checks"] if c["name"] == "model_backend")["ok"]


@pytest.mark.parametrize("unavailable", ["native_protocol", "event_choice_state", "upgrade_rules", "fuel_recovery",
                                         "sector_navigation", "sector_navigation_version", "beacon_navigation",
                                         "beacon_navigation_version", "can_jump", "enemy_defeat_pending", "enemy_hostility"])
def test_doctor_identifies_incomplete_economy_and_recovery_controls(tmp_path, monkeypatch, unavailable):
    save, game = tmp_path / "save", tmp_path / "game"
    save.mkdir()
    game.mkdir()
    (save / "ftl_bench_dev.lua").write_text("-- current bridge")
    for name in ("FTLGame.exe", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll"):
        (game / name).touch()
    capabilities = {"native_protocol": 5, **dict.fromkeys(("manual_fire", "global_autofire_control",
                    "setup_identity", "live_score", "crew_control_guard", "crew_ownership",
                    "event_choice_state", "upgrade_rules", "fuel_recovery", "victory", "sector_navigation", "beacon_navigation", "enemy_hostility"), True)}
    economy = {"sector_navigation_version": 0 if unavailable == "sector_navigation_version" else 1,
               "beacon_navigation_version": 0 if unavailable == "beacon_navigation_version" else 1,
               "navigation": {"can_jump": True, "enemy_defeat_pending": False}}
    if unavailable in ("can_jump", "enemy_defeat_pending"):
        del economy["navigation"][unavailable]
    elif unavailable not in ("sector_navigation_version", "beacon_navigation_version"):
        capabilities[unavailable] = 4 if unavailable == "native_protocol" else False
    (save / "ftl_agent_observation.json").write_text(json.dumps({
        "schema_version": 3, "tick": 1, "seed": 1, "game_started": True,
        "capabilities": capabilities, "economy": economy}), encoding="utf-8")
    monkeypatch.setattr(doctor, "ftl_process_alive", lambda: True)
    result = doctor.inspect_installation(user_folder=save, game_dir=game, full_game=True)
    assert result["ready"] is False
    failed = [check["name"] for check in result["checks"] if not check["ok"]]
    assert failed == [f"navigation.{unavailable}" if unavailable in ("can_jump", "enemy_defeat_pending") else unavailable]
