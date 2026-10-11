"""Dashboard snapshots use recorded lifecycle and scenarios without a running game."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import ftl_live as live  # noqa: E402


def test_visual_trial_receipts_keep_setup_separate_from_model_outcome(bench):
    directory = bench / "fixture"
    directory.mkdir()
    (directory / "run.json").write_text(json.dumps({"track": "visual-v1", "challenge": "combat",
        "setup_only": True, "save_restoration": "verified"}), encoding="utf-8")
    (directory / "validation.json").write_text(json.dumps({"outcome_category": "setup_verified",
        "setup": {"checks": {"active_enemy": True}}, "outcome": {"checks": {"enemy_destroyed": False}}}), encoding="utf-8")
    result = live.visual_trial_report(str(directory / "trajectory.jsonl"))
    assert result["setup_only"] is True
    assert result["setup_checks"] == {"active_enemy": True}
    assert result["outcome_checks"] == {"enemy_destroyed": False}
    assert result["model"] is None
    assert result["save_restoration"] == "verified"


def test_no_observation_does_not_claim_crew_loss_or_no_fires():
    summary = live.summarize_obs(None)
    assert summary["crew"] is None
    assert summary["fires"] is None
    assert live.summarize_obs({"player_ship": {"crew": [], "fires": []}})["crew"] == 0


def test_visual_trial_receipts_handle_partial_or_invalid_files(bench):
    (bench / "run.json").write_text(json.dumps({"track": "visual-v1", "limitations": "bad"}), encoding="utf-8")
    (bench / "visual-report.json").write_text('{"unfinished":', encoding="utf-8")
    (bench / "validation.json").write_text(json.dumps({"setup": [], "outcome": {"checks": {"fake": 1, "real": False}}}), encoding="utf-8")
    result = live.visual_trial_report(str(bench / "trajectory.jsonl"))
    assert result["outcome_checks"] == {"real": False}
    assert result["setup_checks"] == {}
    assert result["limitations"] == []
    assert result["save_restoration"] is None
    assert live.visual_trial_report(str(bench.parent / "outside/trajectory.jsonl")) is None


def test_setup_capture_is_replayable_without_fabricating_model_decisions(bench):
    directory = run(bench, status="error")
    path = directory / "trajectory.jsonl"
    frame = {"path": "screens/setup.png", "frame_id": "setup-frame", "width": 1280, "height": 720}
    rows = [{"kind": "meta", "meta": {"run_id": directory.name}},
            {"kind": "fixture_setup", "i": 0, "visual": {"before": frame, "after": frame}},
            {"kind": "end", "status": "error", "reason": "challenge_setup_error"}]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    snapshot = live.build(live.name_of(path))
    assert snapshot["header"]["steps"] == 0
    assert snapshot["header"]["visual_steps"] == 1
    replay = live.replay_snapshot(live.name_of(path))
    assert replay["item"]["model"] is None
    assert "record=1" in replay["item"]["visual"]["before"]["url"]
    rows.insert(2, {"kind": "step", "i": 1, "model": {"model": "sol"}, "visual": {"before": frame}})
    assert [row[1]["kind"] for row in live.visual_replay_rows(rows)] == ["step"]


def scenario(sid="custom", target=1):
    return {"id": sid, "type": "reach_sector", "seed": 7,
            "goal": [{"key": "sector", "target": target, "kind": "threshold", "weight": 1}]}


@pytest.fixture
def bench(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "BENCH", tmp_path)
    monkeypatch.setattr(live, "SCENARIOS", {})
    monkeypatch.setattr(live, "process_status", lambda: {"known": True, "alive": True, "label": "alive"})
    live._snapshot_cache.clear()
    live._score_cache.clear()
    live._discovery_cache.clear()
    return tmp_path


def test_discovery_excludes_real_native_trace_sidecars_and_preserves_generic_legacy_run(bench):
    directory = run(bench)
    generic = attempt(directory, "generic", suffix=".a2")
    trace = directory / "native-random-traces" / "ftl_random_trace_capture-4.jsonl"
    trace.parent.mkdir()
    # The actual targeting-v2 trace header and numeric native record schema.
    header = {"protocol": "benchmark-random-trace-targeting-v2", "capture_id": "capture-4",
        "action_seq": 10, "tick": 893, "requested_frames": 0, "actual_frames": 0,
        "world_updates": "0", "draws": "0", "native_draws": "0", "seeds": "1",
        "last_seed": 1, "dropped": "0", "records": 12}
    draw = {"serial": "50", "updates": "0", "render_frame": "1034", "kind": 5,
        "stage": 2, "mask": 4, "flags": 1, "object": "33",
        "words": [1097859072, 0, 0, 0, 0, 0, 0, 0, 30, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}
    trace.write_text(json.dumps(header) + "\n" + json.dumps(draw) + "\n")
    sidecar = directory / "rng-state-probe.jsonl"
    sidecar.write_text(json.dumps({"capture_id": "capture-4", "world_updates": "0",
        "draws": "0", "state_sha256": "abc", "state_words": [1, 2, 3]}) + "\n")
    assert live.all_files() == [str(generic)]
    state = live.build("live")
    assert len(state["instances"]) == 1
    assert state["instances"][0]["name"].endswith("generic.a2")
    with pytest.raises(ValueError, match="trajectory not found"):
        live.selected_trajectory(live.name_of(trace))


def test_discovery_accepts_headerless_recording_and_does_not_filter_by_sidecar_filename(bench):
    path = bench / "rng-state-legitimate-legacy-name.jsonl"
    path.write_text(json.dumps({"kind": "step", "actions": [], "obs": {"game_started": True}}) + "\n")
    assert live.all_files() == [str(path)]


def test_discovery_rechecks_cached_partial_header_after_live_append(bench):
    path = bench / "generic.jsonl"
    path.write_text('{"kind":"meta","meta":')
    assert live.all_files() == []
    path.write_text(json.dumps({"kind": "meta", "meta": {"run_id": "generic"}}) + "\n")
    assert live.all_files() == [str(path)]


def test_discovery_prefix_is_bounded_for_unrelated_large_jsonl(bench):
    path = bench / "trace.jsonl"
    path.write_text(json.dumps({"payload": "x" * 70000}) + "\n")
    assert live.all_files() == []


def run(bench, name="run-1", *, status="completed", started=100, ids=None):
    directory = bench / name
    directory.mkdir(exist_ok=True)
    manifest = {"run_id": name, "agent": "test", "started_at": started, "status": status,
                "scenario_ids": ids if ids is not None else ["custom"], "suite": "custom-suite.json"}
    (directory / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def attempt(directory, sid="custom", *, score=100, sector=1, status="completed", reason="agent_returned", suffix="", definition=None):
    path = directory / f"{sid}{suffix}.jsonl"
    records = [
        {"kind": "meta", "t": 100, "meta": {"run_id": directory.name, "agent": "test",
          "scenario_id": sid, "scenario": definition or scenario(sid), "seed": 7}},
        {"kind": "step", "i": 0, "actions": [], "obs": {"game_started": True,
          "ftl_score": score, "render_count": 10, "player_ship": {"hull": {"current": 25, "max": 30},
          "crew": [{"health_current": 100}], "oxygen_pct": 100}, "map": {"sector": sector}}},
    ]
    if status:
        records.append({"kind": "end", "status": status, "reason": reason, "obs": None,
                        "error": "backend failed" if status == "error" else None})
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def test_completed_single_instance_scores_last_attempt_even_with_ftl_alive(bench):
    directory = run(bench)
    attempt(directory)
    state = live.build("live")
    assert state["process"]["alive"] is True
    assert state["header"]["live"] is False
    assert state["header"]["status"] == "completed"
    assert state["header"]["hull"] == 25
    assert state["header"]["steps"] == 1
    assert state["selected_score"]["score"] == 100
    assert state["selected_score"]["solved"] is True
    assert state["agg"]["done"] == state["agg"]["total"] == 1
    assert state["agg"]["mean"] == 100
    assert state["run"]["active_instance"] is None


@pytest.mark.parametrize("observation", [None, {}, {"game_started": False, "ftl_score": 0}])
def test_attempt_without_recorded_gameplay_has_no_phantom_zero_score(bench, observation):
    directory = run(bench, status="error")
    path = attempt(directory, status="error", reason="startup_failed")
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[1:2] = [] if observation is None else [{"kind": "reset", "obs": observation}]
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    assert live.score_for(path) is None
    snapshot = live.build("live")
    assert snapshot["selected_score"] is None
    assert snapshot["instances"][0]["score"] is None
    assert snapshot["agg"]["scored"] == 0 and snapshot["agg"]["mean"] is None
    assert snapshot["header"]["status"] == "error"


def test_recorded_in_game_zero_score_is_preserved(bench):
    directory = run(bench, status="error")
    path = attempt(directory, score=0, sector=0, status="error")
    assert live.score_for(path)["score"] == 0
    snapshot = live.build("live")
    assert snapshot["selected_score"]["score"] == 0
    assert snapshot["agg"]["scored"] == 1 and snapshot["agg"]["mean"] == 0


@pytest.mark.parametrize("hostile", [True, False, None, 1])
def test_live_snapshot_retains_friendly_ship_facts_without_claiming_hostility(bench, hostile):
    directory = run(bench, status="running")
    path = attempt(directory, status=None)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    enemy = {"hull": {"current": 4, "max": 15}, "targetable": False,
             "drones": [{"deployed": True, "name": "Combat Drone", "firing": True}]}
    if hostile is not None:
        enemy["hostile"] = hostile
    records[1]["obs"]["enemy_ship"] = enemy
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    snapshot = live.build("live")
    assert snapshot["header"]["enemy_present"] is True
    assert snapshot["header"]["enemy"] == "4/15"
    assert snapshot["header"]["enemy_hostile"] is (hostile if isinstance(hostile, bool) else None)
    assert snapshot["feed"][0]["state"]["enemy_hostile"] is snapshot["header"]["enemy_hostile"]


def test_active_attempt_is_not_final_score_and_finished_scenario_still_counts(bench):
    directory = run(bench, status="running", ids=["first", "second"])
    old = attempt(directory, "first", score=80)
    active = attempt(directory, "second", score=150, status=None)
    # Pin order independently of filesystem timestamp resolution.
    import os
    os.utime(old, (100, 100))
    os.utime(active, (200, 200))
    state = live.build("live")
    assert state["header"]["live"] is True
    assert state["header"]["ftl_score"] == 150
    assert state["selected_score"] is None
    assert state["run"]["active_instance"] == "run-1/second"
    assert state["agg"]["done"] == 1
    assert state["agg"]["total"] == 2
    assert state["agg"]["mean"] == 80


def test_retry_aggregate_prefers_solved_attempt_and_excludes_live_retry(bench):
    directory = run(bench, status="running")
    attempt(directory, score=200, sector=0, suffix=".a1")
    attempt(directory, score=100, sector=1, suffix=".a2")
    attempt(directory, score=999, status=None, suffix=".a3")
    state = live.build("live")
    assert state["agg"]["done"] == 1
    assert state["agg"]["solved"] == 1
    assert state["agg"]["mean"] == 100
    assert state["agg"]["attempt_files"] == 2


def test_identical_scenario_names_remain_selectable_across_runs(bench):
    first = run(bench, "older", started=100)
    second = run(bench, "newer", started=200)
    attempt(first, score=60)
    attempt(second, score=120)
    state = live.build("older/custom")
    assert len({item["name"] for item in state["instances"]}) == 2
    assert state["selected_score"]["score"] == 60
    assert state["agg"]["mean"] == 60
    assert state["run"]["run_id"] == "older"
    assert state["latest_run"]["run_id"] == "newer"
    assert state["following_live"] is False
    assert live.build("live")["selected_score"]["score"] == 120


def test_new_run_manifest_is_visible_before_any_trajectory(bench):
    attempt(run(bench, "older", started=100))
    run(bench, "preparing", status="running", started=200, ids=["one", "two"])
    state = live.build("live")
    assert state["selected"] is None
    assert state["run"]["run_id"] == "preparing"
    assert state["run"]["status"] == "running"
    assert state["agg"]["done"] == 0
    assert state["agg"]["total"] == 2
    assert state["agg"]["mean"] is None


def test_partial_end_record_is_pending_then_refreshes_when_completed(bench):
    directory = run(bench)
    path = attempt(directory, status=None)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"kind":"end","status":"completed"')
    pending = live.build("live")
    assert pending["header"]["partial"] is True
    assert pending["header"]["status"] == "incomplete"
    assert pending["selected_score"] is None
    assert pending["agg"]["done"] == 0
    with path.open("a", encoding="utf-8") as fh:
        fh.write(',"reason":"agent_returned"}\n')
    completed = live.build("live")
    assert completed["header"]["partial"] is False
    assert completed["selected_score"]["score"] == 100
    assert completed["agg"]["done"] == 1


def test_error_attempt_preserves_state_and_partial_score_but_is_unsolved(bench):
    directory = run(bench, status="error")
    attempt(directory, status="error", reason="agent_error")
    state = live.build("live")
    assert state["header"]["status"] == "error"
    assert state["header"]["reason"] == "agent_error"
    assert state["header"]["error"] == "backend failed"
    assert state["header"]["hull"] == 25
    assert state["selected_score"]["score"] == 100
    assert state["selected_score"]["solved"] is False
    assert state["agg"]["done"] == 1
    assert state["agg"]["failed"] == 1
    assert state["agg"]["solved"] == 0


def test_recorded_scenario_definition_overrides_configured_suite(bench, monkeypatch):
    directory = run(bench)
    attempt(directory, definition=scenario(target=2))
    monkeypatch.setattr(live, "SCENARIOS", {"custom": live.Scenario.from_dict(scenario(target=1))})
    assert live.build("live")["selected_score"]["solved"] is False


def test_missing_and_invalid_files_do_not_break_snapshot(bench, monkeypatch):
    missing = bench / "gone.jsonl"
    malformed = bench / "broken.jsonl"
    malformed.write_text('null\n{"kind":\n', encoding="utf-8")
    monkeypatch.setattr(live, "all_files", lambda: [str(missing), str(malformed)])
    state = live.build("live")
    assert len(state["instances"]) == 2
    assert all(item["score"] is None for item in state["instances"])
    assert all(item["live"] is False for item in state["instances"])


def test_legacy_file_has_provisional_score_without_claiming_live(bench):
    path = attempt(bench, status=None)
    state = live.build(live.name_of(path))
    assert state["header"]["status"] == "unknown"
    assert state["header"]["live"] is False
    assert state["selected_score"]["score"] == 100
    assert state["agg"]["done"] == 0
    assert state["agg"]["total_known"] is False


def test_collapsed_feed_retains_action_counts():
    feed = live.compact_feed([
        {"i": i, "actions": [{"kind": "power", "label": "power engines=2"}], "state": {}, "elapsed_seconds": 20}
        for i in range(3)
    ])
    assert feed[0]["actions"][0]["count"] == 3
    assert feed[0]["elapsed_seconds"] == 60


def test_elapsed_timing_never_uses_paused_render_frames(bench):
    directory = run(bench)
    path = attempt(directory)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    step = next(record for record in records if record.get("kind") == "step")
    step.update(t=100, i=0)
    step["obs"].update(render_count=10, paused=True)
    following = {**step, "i": 1, "t": 132.603, "obs": {**step["obs"], "render_count": 1963},
                 "model": {"latency_seconds": 31.570}}
    records.insert(records.index(step) + 1, following)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    feed = live.build(live.name_of(path))["feed"]
    assert feed[0]["elapsed_seconds"] is None
    assert feed[1]["elapsed_seconds"] == 32.603
    assert all("advance" not in item for item in feed)


def test_collapsed_elapsed_time_is_unknown_if_any_interval_is_missing():
    feed = live.compact_feed([{"i": i, "state": {}, "actions": [], "elapsed_seconds": value}
                              for i, value in enumerate([None, 20, 30])])
    assert feed[0]["elapsed_seconds"] is None


def test_timeout_decisions_without_observation_are_visible_and_not_collapsed(bench):
    directory = run(bench, status="error")
    records = [{"kind": "meta", "meta": {"scenario_id": "custom", "scenario": scenario(), "run_id": directory.name}}]
    records.extend({"kind": "step_timeout", "i": index, "actions": [{"type": "set_system_power", "system_id": 1, "level": 2}],
                    "obs": None, "model": {"model": "test-model", "request_id": f"timeout-{index}"}} for index in range(3))
    records.extend([{"kind": "final_observation", "obs": {"game_started": True, "ftl_score": 50}},
                    {"kind": "end", "status": "error", "reason": "action_timeout", "obs": None}])
    (directory / "custom.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    snapshot = live.build("live")
    assert snapshot["header"]["steps"] == 3
    assert snapshot["instances"][0]["steps"] == 3
    assert snapshot["header"]["ftl_score"] == 50
    assert len(snapshot["feed"]) == 3
    assert all(item["ack_timeout"] and not item.get("collapsed") for item in snapshot["feed"])
    assert snapshot["feed"][0]["model"]["request_id"] == "timeout-0"
    assert snapshot["feed"][0]["actions"][0]["kind"] == "power"


def test_zero_health_crew_are_not_alive_before_native_dead_flag_updates():
    summary = live.summarize_obs({"game_started": True, "game_over": True, "player_ship": {"crew": [
        {"health_current": 0, "dead": False}, {"health_current": -1, "dead": False},
        {"health_current": 100, "dead": True}, {"health_current": 25, "dead": False}]}})
    assert summary["crew"] == 1
    assert summary["crew_min"] == 25
    assert summary["crew_low"] == 1
    transition = live.summarize_obs({"player_ship": {"crew": [{"health_current": 0, "dead": False}]}})
    assert transition["crew"] == 0
    assert transition["crew_min"] is None


def test_boarders_cannot_inflate_surviving_player_crew_or_lower_their_health(bench):
    directory = run(bench)
    path = attempt(directory)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[1]["obs"]["player_ship"].update(crew=[
        {"id": 0, "health_current": 80},  # Legacy friendly crew retains its meaning.
        {"id": 3, "health_current": 5, "intruder": True},
        {"id": 4, "health_current": 100, "player_owned": False, "intruder": False},
        {"id": 5, "health_current": 1, "owner_ship_id": 1},
    ], intruders=[{"id": 3}, {"id": 4}, {"id": 5}])
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    snapshot = live.build("live")
    assert snapshot["header"]["crew"] == 1
    assert snapshot["header"]["crew_min"] == 80
    assert snapshot["header"]["crew_low"] == 0
    assert snapshot["header"]["intruders"] == 3
    assert snapshot["feed"][0]["state"]["crew_min"] == 80


def test_hostile_survivors_do_not_hide_player_crew_loss():
    summary = live.summarize_obs({"player_ship": {"crew": [
        {"health_current": 0, "dead": False, "player_owned": True},
        {"health_current": 100, "dead": False, "intruder": True},
        {"health_current": 100, "dead": False, "player_owned": False},
    ]}})
    assert summary["crew"] == 0
    assert summary["crew_min"] is None
    assert summary["crew_low"] == 0


@pytest.mark.parametrize("ownership", [
    {"player_owned": True, "intruder": True, "on_enemy_ship": True},
    {"owner_ship_id": 0, "intruder": True, "on_enemy_ship": True},
    {"intruder": True, "on_enemy_ship": True},
    {"player_owned": True, "controllable": False},
    {},
])
def test_our_boarders_and_temporarily_uncontrolled_crew_still_count_as_survivors(ownership):
    summary = live.summarize_obs({"player_ship": {"crew": [{"health_current": 25, **ownership}]}})
    assert summary["crew"] == 1
    assert summary["crew_min"] == 25
    assert summary["crew_low"] == 1


def test_all_retry_failures_are_visible_beside_successful_best_attempt(bench):
    directory = run(bench)
    attempt(directory, score=200, status="error", suffix=".a0", reason="model_error")
    attempt(directory, score=100, status="completed", suffix=".a1", reason="game_over")
    snapshot = live.build("live")
    assert snapshot["agg"]["attempt_files"] == 2
    assert snapshot["agg"]["failed"] == 0
    assert snapshot["agg"]["attempt_failures"] == 1
    assert snapshot["agg"]["attempt_interrupted"] == 0
    assert snapshot["agg"]["mean"] == 100
    from ftl_bench.reporting import load_run_report
    report = load_run_report(directory)
    assert report["aggregate"]["failed"] == snapshot["agg"]["failed"]
    assert report["aggregate"]["attempt_failures"] == snapshot["agg"]["attempt_failures"]


def test_diagnostic_failures_remain_recorded_when_excluded_from_comparison(bench):
    directory = run(bench, status="error")
    manifest_path = directory / "run.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(validation_status="diagnostic_only", validation_limitations=["Invalid control boundary."])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    attempt(directory, score=50, status="error", reason="invalid_control_boundary")
    snapshot = live.build("live")
    assert snapshot["header"]["status"] == "error"
    assert snapshot["selected_score"]["score"] == 50
    assert snapshot["agg"]["done"] == snapshot["agg"]["total"] == 1
    assert snapshot["agg"]["failed"] == 0
    assert snapshot["agg"]["attempt_failures"] == 1
    assert snapshot["agg"]["recorded_mean"] == 50 and snapshot["agg"]["mean"] is None
    from ftl_bench.reporting import load_run_report
    report = load_run_report(directory)
    assert report["coverage"]["complete"] is True
    assert report["aggregate"]["failed"] == 0
    assert report["recorded_aggregate"]["failed"] == 1
    assert report["recorded_aggregate"]["attempt_failures"] == snapshot["agg"]["attempt_failures"]


@pytest.mark.parametrize("iso,numeric,expected", [
    ("2026-10-11T06:00:00Z", 1791698460, "numeric-model"),
    ("2026-10-11T03:02:00-03:00", 1791698460, "iso-startup"),
])
def test_state_api_orders_mixed_iso_and_numeric_start_times(bench, iso, numeric, expected):
    from test_visual_comparison import asgi_request
    startup = run(bench, "iso-startup", started=iso)
    model = run(bench, "numeric-model", started=numeric)
    attempt(startup)
    attempt(model)
    app = live.create_app()
    if app is None: pytest.skip("dashboard dependency unavailable")
    status, state = asgi_request(app, "/api/state")
    assert status == 200 and state["run"]["run_id"] == expected
    runs, _ = live.discover_runs(live.all_files())
    assert runs[str(startup.resolve())]["started_at"] == iso
    assert runs[str(model.resolve())]["started_at"] == numeric


@pytest.mark.parametrize("started", [None, "invalid-date", {}, True, float("nan"), float("inf"), 10**500, -(10**500)])
def test_invalid_start_time_falls_back_to_activity(bench, monkeypatch, started):
    valid = run(bench, "valid", started=100)
    fallback = run(bench, "fallback", started=started)
    attempt(valid)
    attempt(fallback)
    monkeypatch.setattr(live, "_mtime", lambda path: 200 if "fallback" in str(path) else 10)
    assert live.build("live")["run"]["run_id"] == "fallback"


def test_equivalent_iso_and_numeric_start_times_use_activity_tiebreaker(bench, monkeypatch):
    iso = run(bench, "iso", started="2026-10-11T06:00:00+00:00")
    numeric = run(bench, "numeric", started=1791698400)
    attempt(iso)
    attempt(numeric)
    monkeypatch.setattr(live, "_mtime", lambda path: 200 if "numeric" in str(path) else 100)
    assert live.build("live")["run"]["run_id"] == "numeric"
