"""Frozen full-game scheduling and truthful completion; no live processes/models."""
from contextlib import nullcontext
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from ftl_bench.cli import _bench_root
from test_fullgame_setup import immediate, packets
from test_visual_reporting import saved_run, save_rows

spec = importlib.util.spec_from_file_location("fullgame_experiment", _bench_root() / "scripts/run_fullgame_experiment.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def test_declared_pilot_and_four_fullgames_have_fixed_matched_conditions(tmp_path):
    cells = controller.plan_cells()
    assert len(cells) == 5 and cells[0]["scope"] == "sector_pilot"
    assert cells[0]["model"] == "gpt-6.1-sol" and cells[0]["mode"] == "image"
    assert {(c["model"], c["mode"]) for c in cells[1:]} == {
        (model, mode) for model in ("gpt-6.1-sol", "gpt-6-luna") for mode in ("image", "hybrid")}
    protocol = {"seed": 1, "budgets": controller.BUDGETS, "reasoning_effort": "medium"}
    for cell in cells:
        command = controller.trial_command(tmp_path, cell, protocol)
        assert command[2].endswith("run_visual.py")
        for flag, value in (("--seed", "1"), ("--max-decisions", "300"),
                            ("--max-wall-seconds", "14400"), ("--max-idle-decisions", "8")):
            assert command[command.index(flag) + 1] == value
        assert ("--stop-after-sector" in command) == (cell["scope"] == "sector_pilot")


@pytest.mark.parametrize("reason,raw,complete", [
    ("native_victory", {"victory": True}, True),
    ("native_game_over", {"game_over": True, "victory": False}, True),
    ("native_victory", {"victory": False}, False),
    ("native_game_over", {"game_over": False, "player_ship": {"hull": {"current": 0}}}, False),
    ("decision_budget", {"victory": True}, False),
    ("wall_clock_budget", {}, False), ("idle_decision_budget", {}, False),
    ("user_interrupted", {}, False), ("sector_target_observed", {"map": {"sector": 1}}, False),
])
def test_only_matching_native_terminal_completes_fullgame(reason, raw, complete):
    result = controller.classify_outcome(controller.plan_cells()[1], {"status": "completed", "reason": reason}, raw)
    assert result["fullgame_complete"] is complete
    if complete:
        assert not controller.classify_outcome(controller.plan_cells()[1], {"status": "error", "reason": reason}, raw)["fullgame_complete"]


def test_pilot_never_counts_as_completed_fullgame():
    pilot = controller.plan_cells()[0]
    result = controller.classify_outcome(pilot, {"status": "completed", "reason": "sector_target_observed"}, {"map": {"sector": 1}})
    assert result["category"] == "pilot_sector_reached" and not result["fullgame_complete"]
    result = controller.classify_outcome(pilot, {"status": "completed", "reason": "native_victory"}, {"victory": True})
    assert result["native_outcome"] == "victory" and not result["fullgame_complete"]


@pytest.mark.parametrize("mutation", ["drop", "reorder", "model", "protocol"])
def test_ledger_rejects_changed_declared_conditions(mutation):
    ledger = {"protocol_sha256": "hash", "cells": controller.plan_cells()}
    if mutation == "drop": ledger["cells"].pop()
    elif mutation == "reorder": ledger["cells"].reverse()
    elif mutation == "model": ledger["cells"][1]["model"] = "other"
    else: ledger["protocol_sha256"] = "other"
    with pytest.raises(RuntimeError):
        controller.validate_ledger(ledger, {"protocol_sha256": "hash"})


def test_self_source_is_explicitly_frozen_without_changing_challenge_glob(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    own = scripts / "run_fullgame_experiment.py"
    own.write_bytes(b"controller version one")
    monkeypatch.setattr(controller.shared, "source_identity", lambda root: {"adapter/run_visual.py": "a"})
    monkeypatch.setattr(controller, "accepted_runtime_baseline", lambda root: ({}, {"path": "baseline.json", "sha256": "b" * 64}))
    first = controller.source_identity(tmp_path)
    own.write_bytes(b"controller version two")
    assert first != controller.source_identity(tmp_path)
    assert "scripts/run_fullgame_experiment.py" in first


def test_source_archive_is_byte_exact_and_rejects_drift(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "script.py").write_bytes(b"frozen source")
    monkeypatch.setattr(controller, "ROOT", source)
    identity = {"script.py": hashlib.sha256(b"frozen source").hexdigest()}
    controller.archive_sources(tmp_path / "output", identity)
    assert (tmp_path / "output/frozen-source/script.py").read_bytes() == b"frozen source"
    (source / "script.py").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed while freezing"):
        controller.archive_sources(tmp_path / "another", identity)


@pytest.mark.parametrize("identity,blocked", [({"pid": 12, "creation_filetime": 3}, True),
                                             ({"pid": 12, "creation_filetime": 4}, False), (None, False)])
def test_live_child_blocks_resume_but_reused_pid_does_not(tmp_path, monkeypatch, identity, blocked):
    cell = controller.plan_cells()[0]
    cell.update(status="running", process={"pid": 12, "creation_filetime": 3})
    path = controller.trial_directory(tmp_path, cell)
    path.mkdir(parents=True)
    controller.write(path / "run.json", {"status": "completed", "reason": "decision_budget"})
    monkeypatch.setattr(controller.shared, "process_identity", lambda pid: identity)
    if blocked:
        with pytest.raises(RuntimeError, match="still running"):
            controller.reconcile(tmp_path, cell)
    else:
        controller.reconcile(tmp_path, cell)
        assert cell["status"] == "finished"


def test_missing_process_identity_and_missing_terminal_never_retry(tmp_path, monkeypatch):
    cell = controller.plan_cells()[0]
    cell["status"] = "running"
    with pytest.raises(RuntimeError, match="lacks verified"):
        controller.reconcile(tmp_path, cell)
    cell["process"] = {"pid": 1, "creation_filetime": 2}
    monkeypatch.setattr(controller.shared, "process_identity", lambda pid: None)
    controller.reconcile(tmp_path, cell)
    assert cell["status"] == "interrupted_unknown"


def trial_fixture(tmp_path, reason="native_game_over", *, save_count=7):
    cell = controller.plan_cells()[1]
    path = controller.trial_directory(tmp_path, cell)
    rows = saved_run(path, reason=reason)
    rows[0]["meta"].update(seed=1, budgets=dict(controller.BUDGETS))
    rows[-1]["budgets"] = dict(controller.BUDGETS)
    raw = immediate(1)
    rows[1]["obs"]["deterministic_setup"] = raw["deterministic_setup"]
    for row in rows:
        for key in ("obs", "pre_obs"):
            if key in row:
                row[key]["last_action_seq"] += 2
                row[key]["visual"]["action_seq"] += 2
        if "visual" in row:
            for key in ("before", "after"):
                row["visual"][key]["action_seq"] += 2
    rows[2]["obs"].update(game_over=reason == "native_game_over", victory=reason == "native_victory")
    # saved_run deep-copies the pre-observation; join its new deterministic receipt.
    rows[2]["pre_obs"] = rows[1]["obs"]
    save_rows(path, rows)
    report = controller.read(path / "visual-report.json")
    report["budgets"] = dict(controller.BUDGETS)
    controller.write(path / "visual-report.json", report)
    manifest = controller.read(path / "run.json")
    manifest.update(seed=1, budgets=dict(controller.BUDGETS), trial_scope="full_game", stop_after_sector=None)
    controller.write(path / "run.json", manifest)
    runtime = controller.read(path / "runtime-fingerprint.json")
    setup = path / "fresh-setup"
    setup.mkdir()
    controller.write(setup / "setup-session.json", {"admitted": True, "packets": packets(1)})
    controller.write(setup / "admission.json", {"passed": True, "first_observation": rows[1]["obs"],
        "first_image": rows[1]["visual"]["before"]})
    backup = controller.read(path / "save-backup/manifest.json")
    if save_count == 0:
        (path / "save-backup/original.sav").unlink()
        backup["files"] = {}
    for i in range(save_count - 1):
        name = f"other{i}.sav"
        data = name.encode()
        (path / "save-backup" / name).write_bytes(data)
        backup["files"][name] = hashlib.sha256(data).hexdigest()
    controller.write(path / "save-backup/manifest.json", backup)
    controller.write(path / "save-backup/restoration.json", {"verified": True, "files": {k: True for k in backup["files"]}})
    protocol = {"protocol_sha256": "frozen-protocol", "seed": 1, "budgets": dict(controller.BUDGETS), "reasoning_effort": "medium",
        "actor_identity": manifest["actor_identity"], "codex_cli": runtime["codex_cli"],
        "installed_runtime": {"native_build": runtime["native_build"]},
        "native_acceptance": {"dll_sha256": runtime["native_dll"]["sha256"], "production_bridge_sha256": runtime["bridge_lua"]["sha256"]},
        "schema_sha256": controller.digest(rows[2]["model"]["schema"])}
    return cell, protocol, path


def test_actual_saved_audit_native_loss_and_budget_attribution(tmp_path):
    cell, protocol, _ = trial_fixture(tmp_path)
    result = controller.audit_trial(tmp_path, cell, protocol)
    assert result["integrity_passed"], result["issues"]
    assert result["verified_fullgame_complete"] and result["native_outcome"] == "defeat"
    assert result["model_calls"]["calls"] == 1


@pytest.mark.parametrize("mutation", ["recorded_reasoning", "call_reasoning", "requested_model", "terminal_budget", "report_budget", "metadata_budget", "metadata_seed"])
def test_effective_actor_settings_and_budgets_must_match_protocol(tmp_path, mutation):
    cell, protocol, path = trial_fixture(tmp_path)
    rows = [json.loads(line) for line in (path / "trajectory.jsonl").read_text().splitlines()]
    if mutation == "recorded_reasoning":
        rows[0]["meta"]["reasoning_effort"] = "low"
        rows[2]["model"]["reasoning_effort"] = "low"
    elif mutation == "call_reasoning": rows[2]["model"]["reasoning_effort"] = "low"
    elif mutation == "requested_model": rows[2]["model"]["requested_model"] = "gpt-6-luna"
    elif mutation == "terminal_budget": rows[-1]["budgets"]["decisions"] = 900
    elif mutation == "metadata_budget": rows[0]["meta"]["budgets"]["decisions"] = 900
    elif mutation == "metadata_seed": rows[0]["meta"]["seed"] = 2
    save_rows(path, rows)
    if mutation in ("terminal_budget", "report_budget"):
        report = controller.read(path / "visual-report.json")
        report["budgets"]["decisions"] = 900
        controller.write(path / "visual-report.json", report)
    result = controller.audit_trial(tmp_path, cell, protocol)
    assert not result["integrity_passed"] and not result["verified_fullgame_complete"]


def baseline_fixture(tmp_path):
    (tmp_path / "dist").mkdir()
    files = {name: hashlib.sha256(name.encode()).hexdigest() for name in controller.RUNTIME_FILES}
    baseline = {"C:/tested-game/" + name: value for name, value in files.items()}
    path = tmp_path / "dist/baseline.json"
    controller.write(path, baseline)
    receipt = {"contract": "fresh-start-v3-production-acceptance-v1", "baseline": {
        "path": "dist/baseline.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
    controller.write(tmp_path / "dist/native-validation.visual-v1.json", receipt)
    return files, receipt, baseline


@pytest.mark.parametrize("filename", controller.RUNTIME_FILES)
def test_all_installed_runtime_files_join_the_accepted_baseline(tmp_path, filename):
    files, _, _ = baseline_fixture(tmp_path)
    installed = {"files_sha256": dict(files), "deployed_bridge_sha256": "separate-original-bridge"}
    assert controller.require_tested_runtime(installed, tmp_path)["files_sha256"] == files
    installed["files_sha256"][filename] = "0" * 64
    with pytest.raises(RuntimeError, match="accepted tested baseline"):
        controller.require_tested_runtime(installed, tmp_path)


@pytest.mark.parametrize("mutation", ["changed_bytes", "missing_file", "duplicate_file", "unsafe_path", "bad_hash"])
def test_baseline_reference_is_hash_checked_and_unambiguous(tmp_path, mutation):
    _, receipt, baseline = baseline_fixture(tmp_path)
    path = tmp_path / "dist/baseline.json"
    if mutation == "changed_bytes": path.write_bytes(path.read_bytes() + b" ")
    elif mutation in ("missing_file", "duplicate_file"):
        if mutation == "missing_file": baseline.pop("C:/tested-game/ftl.dat")
        else: baseline["C:/other/ftl.dat"] = "0" * 64
        controller.write(path, baseline)
        receipt["baseline"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation == "unsafe_path": receipt["baseline"]["path"] = "../baseline.json"
    else: receipt["baseline"]["sha256"] = "not-a-hash"
    controller.write(tmp_path / "dist/native-validation.visual-v1.json", receipt)
    with pytest.raises(RuntimeError):
        controller.accepted_runtime_baseline(tmp_path)


@pytest.mark.parametrize("mutation", ["budget", "model", "native_proof", "save"])
def test_changed_trial_evidence_blocks_completion_and_next_trial(tmp_path, mutation):
    cell, protocol, path = trial_fixture(tmp_path)
    if mutation in ("budget", "model"):
        run = controller.read(path / "run.json")
        if mutation == "budget": run["budgets"]["decisions"] = 900
        else: run["model"] = "gpt-6-luna"
        controller.write(path / "run.json", run)
    elif mutation == "native_proof":
        setup = controller.read(path / "fresh-setup/setup-session.json")
        setup["packets"][0]["packet"]["benchmark_setup"]["seed"] = 2
        controller.write(path / "fresh-setup/setup-session.json", setup)
    else:
        (path / "save-backup/original.sav").write_bytes(b"changed")
    result = controller.audit_trial(tmp_path, cell, protocol)
    assert not result["verified_fullgame_complete"] and not result["integrity_passed"]
    with pytest.raises(RuntimeError, match="failed integrity/cleanup"):
        controller.require_audited_cleanup(tmp_path, cell, protocol)


def progression_fixture(tmp_path, monkeypatch, reason="decision_budget", *, save_count=7):
    cell, protocol, path = trial_fixture(tmp_path, reason, save_count=save_count)
    cell.update(status="finished", exit_code=0)
    backup = controller.read(path / "save-backup/manifest.json")
    live = tmp_path / "live-saves"
    live.mkdir()
    for name in backup["files"]:
        (live / name).write_bytes((path / "save-backup" / name).read_bytes())
    backup["save_directory"] = str(live)
    controller.write(path / "save-backup/manifest.json", backup)
    monkeypatch.setattr(controller, "game_processes", lambda: [])
    return cell, protocol, path, live


@pytest.mark.parametrize("reason", ["native_game_over", "native_victory", "decision_budget", "idle_decision_budget", "wall_clock_budget"])
def test_clean_native_outcomes_and_budgets_allow_progression(tmp_path, monkeypatch, reason):
    cell, protocol, _, _ = progression_fixture(tmp_path, monkeypatch, reason)
    reference = controller.require_audited_cleanup(tmp_path, cell, protocol)
    data = (tmp_path / reference["path"]).read_bytes()
    receipt = json.loads(data)
    assert hashlib.sha256(data).hexdigest() == reference["sha256"]
    assert receipt["protocol_sha256"] == protocol["protocol_sha256"]
    assert receipt["live_save_audit"]["live_saves_checked"] and receipt["live_save_audit"]["complete"]
    assert receipt["no_game_process"] and receipt["observed_game_processes"] == []
    assert receipt["live_save_inventory_sha256"] == receipt["expected_save_inventory_sha256"]
    assert len(receipt["live_save_inventory_sha256"]) == 7
    assert receipt["child_verification"] == "recorded_zero_exit"
    assert receipt["controller_sha256"] == hashlib.sha256(Path(controller.__file__).read_bytes()).hexdigest()


@pytest.mark.parametrize("save_count", [0, 1, 3, 8])
def test_cleanup_accepts_exact_machine_specific_save_inventory(tmp_path, monkeypatch, save_count):
    cell, protocol, path, live = progression_fixture(tmp_path, monkeypatch, save_count=save_count)
    reference = controller.require_audited_cleanup(tmp_path, cell, protocol)
    receipt = controller.read(tmp_path / reference["path"])
    assert len(receipt["expected_save_inventory_sha256"]) == save_count
    assert receipt["expected_save_inventory_sha256"] == receipt["live_save_inventory_sha256"]
    assert receipt["live_save_audit"]["restored_files"] == save_count
    # Exact inventory still matters on an empty or small profile.
    (live / "unexpected.sav").write_bytes(b"unrestored generated save")
    with pytest.raises(RuntimeError, match="inventory differs"):
        controller.require_audited_cleanup(tmp_path, cell, protocol)


def test_cleanup_check_preserves_each_receipt_even_at_same_timestamp(tmp_path, monkeypatch):
    cell, protocol, _, _ = progression_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(controller, "stamp", lambda: "2026-10-11T00:00:00+00:00")
    first = controller.require_audited_cleanup(tmp_path, cell, protocol)
    original = (tmp_path / first["path"]).read_bytes()
    second = controller.require_audited_cleanup(tmp_path, cell, protocol)
    assert first["path"] != second["path"]
    assert (tmp_path / first["path"]).read_bytes() == original
    assert (tmp_path / second["path"]).is_file()


@pytest.mark.parametrize("mutation", ["live_bytes", "extra_save", "game_alive", "nonzero_exit", "missing_exit", "unknown_status", "technical_reason"])
def test_progression_checks_current_saves_process_and_child_outcome(tmp_path, monkeypatch, mutation):
    reason = "visual_infrastructure_error" if mutation == "technical_reason" else "decision_budget"
    cell, protocol, _, live = progression_fixture(tmp_path, monkeypatch, reason)
    if mutation == "live_bytes": (live / "original.sav").write_bytes(b"changed")
    elif mutation == "extra_save": (live / "generated.sav").write_bytes(b"new")
    elif mutation == "game_alive": monkeypatch.setattr(controller, "game_processes", lambda: [{"id": 123}])
    elif mutation == "nonzero_exit": cell["exit_code"] = 2
    elif mutation == "missing_exit": cell.pop("exit_code")
    elif mutation == "unknown_status": cell["status"] = "interrupted_unknown"
    with pytest.raises(RuntimeError):
        controller.require_audited_cleanup(tmp_path, cell, protocol)


def test_recovered_dead_child_requires_matching_completed_terminal(tmp_path, monkeypatch):
    cell, protocol, _, _ = progression_fixture(tmp_path, monkeypatch)
    cell.pop("exit_code")
    cell.update(recovered_at="now", result_status="completed", result_reason="decision_budget")
    reference = controller.require_audited_cleanup(tmp_path, cell, protocol)
    receipt = controller.read(tmp_path / reference["path"])
    assert receipt["child"]["exit_code"] is None
    assert receipt["child_verification"] == "recovered_completed_terminal_exit_code_unavailable"
    cell["result_status"] = "error"
    with pytest.raises(RuntimeError, match="technical, interrupted"):
        controller.require_audited_cleanup(tmp_path, cell, protocol)


def fake_controller(tmp_path, monkeypatch):
    protocol = {"protocol_sha256": "hash", "seed": 1, "budgets": controller.BUDGETS, "reasoning_effort": "medium"}
    controller.write(tmp_path / "protocol.json", protocol)
    controller.write(tmp_path / "ledger.json", {"protocol_sha256": "hash", "cells": controller.plan_cells()})
    monkeypatch.setattr(controller, "verify_protocol", lambda protocol: None)
    monkeypatch.setattr(controller.shared, "controller_lock", lambda directory: nullcontext())
    monkeypatch.setattr(controller, "refresh_summary", lambda *args: None)
    monkeypatch.setattr(controller, "require_audited_cleanup", lambda *args: None)


def test_single_invocation_does_not_start_second_cell(tmp_path, monkeypatch):
    fake_controller(tmp_path, monkeypatch)
    starts = []
    monkeypatch.setattr(controller.subprocess, "Popen", lambda command, **kwargs:
        starts.append(command) or SimpleNamespace(pid=123, wait=lambda timeout=None: 0))
    monkeypatch.setattr(controller.shared, "process_identity", lambda pid: {"pid": pid, "creation_filetime": 42})
    controller.run(tmp_path, 1)
    cells = controller.read(tmp_path / "ledger.json")["cells"]
    assert len(starts) == 1 and cells[0]["status"] == "finished"
    assert all(c["status"] == "planned" for c in cells[1:])


def test_existing_trial_output_is_preserved_without_launch(tmp_path, monkeypatch):
    fake_controller(tmp_path, monkeypatch)
    controller.trial_directory(tmp_path, controller.plan_cells()[0]).mkdir(parents=True)
    monkeypatch.setattr(controller.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(RuntimeError, match="will not be overwritten"):
        controller.run(tmp_path, 1)


def test_interruption_requests_cooperative_stop_waits_for_cleanup_and_does_not_start_next(tmp_path, monkeypatch):
    fake_controller(tmp_path, monkeypatch)
    waits = []
    def wait(timeout=None):
        waits.append(timeout)
        if len(waits) == 1:
            raise KeyboardInterrupt
        request = controller.read(tmp_path / "stop-request.json")
        assert request["initiator"] == "controller_keyboard_interrupt"
        return 130
    monkeypatch.setattr(controller.subprocess, "Popen", lambda *a, **k: SimpleNamespace(pid=123, wait=wait))
    monkeypatch.setattr(controller.shared, "process_identity", lambda pid: {"pid": pid, "creation_filetime": 42})
    controller.run(tmp_path, 5)
    cells = controller.read(tmp_path / "ledger.json")["cells"]
    assert cells[0]["status"] == "finished" and cells[0]["process"]["creation_filetime"] == 42
    assert all(c["status"] == "planned" for c in cells[1:]) and waits == [1, 1]
