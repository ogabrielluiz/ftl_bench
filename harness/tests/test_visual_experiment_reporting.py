"""Integration of controller paths and the child fixture's saved evidence schema."""
from copy import deepcopy
import json

import visual_reporting as reporting
from test_visual_experiment import experiment as controller
from test_visual_reporting import protocol, saved_run, save_rows, write


def challenge_evidence(directory, *, model, mode):
    rows = saved_run(directory, model=model, mode=mode)
    health = [{"system_id": 1, "health_current": 1, "health_max": 2}]
    for row in rows:
        for field in ("obs", "pre_obs"):
            if isinstance(row.get(field), dict):
                row[field]["visual_challenge_system_health"] = health
    prelude = deepcopy(rows[1])
    prelude["kind"] = "fixture_setup"
    rows.insert(1, prelude)
    save_rows(directory, rows)
    start = json.loads((directory / "actor-start.json").read_text())
    start["initial_observation"] = rows[2]["obs"]
    start["gameplay_signature"]["native_system_health"] = health
    start["gameplay_signature_sha256"] = reporting.canonical_sha256(start["gameplay_signature"])
    write(directory / "actor-start.json", start)
    for name in ("run.json", "visual-report.json"):
        value = json.loads((directory / name).read_text())
        value["experiment"]["initial_gameplay_sha256"] = start["gameplay_signature_sha256"]
        value["experiment_sha256"] = reporting.canonical_sha256(value["experiment"])
        write(directory / name, value)
    return rows


def test_controller_saved_paths_accept_actual_fixture_prelude_and_native_health_alias(tmp_path):
    paths = []
    for cell in controller.plan_cells():
        if cell["challenge"] != "combat" or cell["repetition"] != 1:
            continue
        directory = controller.saved_trial(tmp_path, cell)
        challenge_evidence(directory, model=cell["model"], mode=cell["mode"])
        paths.append(directory)
    result = reporting.aggregate_visual_runs(paths, protocol())
    assert result["qualified_scoped_comparison"], [t["exclusions"] for t in result["trials"]]
    assert all(t["audit"]["complete"] for t in result["trials"])


def test_fixture_prelude_cannot_hide_mid_actor_setup_or_simulation(tmp_path):
    directory = tmp_path / "bad"
    rows = challenge_evidence(directory, model="gpt-6.1-sol", mode="image")
    prelude = rows.pop(1)
    rows.insert(-1, prelude)
    save_rows(directory, rows)
    result = reporting.audit_visual_run(directory)
    assert not result["complete"]
    assert any(issue["scope"] == "fixture_setup" for issue in result["issues"])
