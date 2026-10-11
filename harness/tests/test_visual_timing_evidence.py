"""Opt-in timing evidence at the real challenge/protected lifecycle boundary."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ftl_bench import visual_evidence as evidence
import ftl_bench.protected_game as protection
from ftl_bench.trajectory import load_trajectory
from test_visual_startup import native
from test_visual_challenges import challenge, initial
from test_visual_timing import reports
from test_challenge_setup import first_frame, good_packets
import validate_visual_timing as timing


@pytest.fixture(params=[False, True], ids=["own-root", "common-root"])
def portable_trial(native, tmp_path, monkeypatch, request):
    root, save, state = native
    script = Path(timing.__file__).read_bytes()
    (root / "scripts/validate_visual_timing.py").write_bytes(script)
    collection = tmp_path / "collection"; collection.mkdir()
    driver = collection / "timing-driver.py"; driver.write_bytes(script)
    reference_root = tmp_path if request.param else collection
    files = evidence.snapshot_sources(root, collection, reference_root)
    trial = collection / "fire-crew-recovery/repetition-01/fire-crew-recovery"
    portable = evidence.TimingTrialEvidence(root, collection, files, "fire-crew-recovery", 1, .35, driver, reference_root)
    monkeypatch.setattr(challenge, "ROOT", root)
    monkeypatch.setattr(challenge, "ftl_user_folder", lambda: save)
    monkeypatch.setattr(challenge, "runtime_fingerprint", lambda root: {
        "native_build": {"matches_installed_dll": True}, "bridge_lua": {"sha256": evidence.digest(save / "ftl_bench_dev.lua")}})
    monkeypatch.setattr(challenge, "game_processes", lambda: [])
    session = SimpleNamespace(setup_packets=good_packets())
    monkeypatch.setattr(challenge, "AgentSession", lambda **kwargs: session)
    def prepare(session, kind, output, control):
        challenge.write_json(output / "deterministic-setup-session.json", {"packets": session.setup_packets})
    monkeypatch.setattr(challenge, "prepare", prepare)
    def capture():
        screens = trial / "screens"; screens.mkdir()
        frame = first_frame(screens)
        raw = initial("fire-crew-recovery")
        raw["visual"].update(frame.observation.raw["visual"])
        raw["last_action_seq"] = 4
        frame.observation.raw = raw
        frame.reference["path"] = "screens/first.png"
        return frame
    monkeypatch.setattr(challenge, "VisualSession", lambda *args: SimpleNamespace(capture=capture))
    monkeypatch.setattr(challenge, "verify_visual_setup", lambda *args: {"verified": True})
    monkeypatch.setattr(challenge, "CodexVisualAgent", lambda **kwargs: pytest.fail("No actor construction allowed"))
    launch = protection.ProtectedGame.launch
    def check_header_before_launch(self):
        header = load_trajectory(trial / "trajectory.jsonl")[0]["meta"]
        assert header["source_files_sha256"] == evidence.source_digest(files)
        assert header["probe_delay_seconds"] == .35
        assert header["timing_driver_sha256"] == evidence.digest(driver)
        assert (trial / "before-inventory.json").is_file()
        launch(self)
    monkeypatch.setattr(protection.ProtectedGame, "launch", check_header_before_launch)
    args = challenge.parser().parse_args(["--setup-only", "--challenge", "fire-crew-recovery"])
    args.probe_delay_seconds = .35
    return root, save, collection, trial, portable, args


def test_opt_in_trial_records_portable_evidence_and_restores_actual_save_copies(portable_trial):
    root, save, collection, trial, portable, args = portable_trial
    calls = []
    result = challenge.run_trial(args, "fire-crew-recovery", 1, trial, None, None,
        scripted_probe=lambda *args: calls.append("scripted"), portable_evidence=portable)
    assert calls == ["scripted"] and result["outcome_category"] == "setup_verified"
    assert (save / "original.sav").read_bytes() == b"original save"
    assert (save / "ftl_bench_dev.lua").read_bytes() == b"original bridge"
    assert not (save / "generated.sav").exists()
    assert [row["kind"] for row in load_trajectory(trial / "trajectory.jsonl")] == ["meta", "reset", "end"]
    descriptor = result["portable_evidence"]
    for key in ("trajectory", "session", "runtime", "cleanup", "timing_script", "admission"):
        assert evidence.digest(portable.reference_root / descriptor[key]["path"]) == descriptor[key]["sha256"]
    cleanup = json.loads((portable.reference_root / descriptor["cleanup"]["path"]).read_text())
    assert cleanup["trajectory"] == descriptor["trajectory"] and cleanup["session"] == descriptor["session"]
    before = json.loads((portable.reference_root / cleanup["raw_inventory_refs"]["before"]["path"]).read_text())["files_sha256"]
    assert {cleanup["inventory_ids"][name]: sha for name, sha in before.items()} == cleanup["before"] == cleanup["after"]
    assert len(cleanup["inventory_ids"]) == len(set(cleanup["inventory_ids"].values()))
    assert evidence.digest(portable.reference_root / cleanup["backups"]["original.sav"]["path"]) == cleanup["before"]["save/original.sav"]
    assert len(descriptor["images"]) == 1
    snapshot = json.loads((collection / "source-snapshot.json").read_text())
    for ref in snapshot["archived_files"].values():
        assert evidence.digest(portable.reference_root / ref["path"]) == ref["sha256"]


@pytest.mark.parametrize("fault", ["source_drift", "game_process"])
def test_failed_portable_cleanup_cannot_be_reported_as_setup_verified(portable_trial, monkeypatch, fault):
    root, save, _, trial, portable, args = portable_trial
    def probe(*unused):
        if fault == "source_drift": (root / "adapter/start.py").write_text("changed during probe")
        else: monkeypatch.setattr(challenge, "game_processes", lambda: [{"id": 123, "path": "recorded fake"}])
    result = challenge.run_trial(args, "fire-crew-recovery", 1, trial, None, None,
        scripted_probe=probe, portable_evidence=portable)
    assert result["outcome_category"] != "setup_verified" and result["status"] == "failed"
    assert result["portable_evidence"] is None and (trial / "portable-evidence-error.json").exists()
    assert not (trial / "portable-cleanup.json").exists()
    assert (save / "original.sav").read_bytes() == b"original save"
    assert (trial / "save-backup/original.sav").read_bytes() == b"original save"


def test_collection_source_drift_or_changed_driver_refuses_next_trial_before_launch(portable_trial):
    root, _, collection, _, portable, args = portable_trial
    (collection / "timing-driver.py").write_text("tampered archive")
    with pytest.raises(RuntimeError, match="driver"): portable.metadata()
    (root / "adapter/start.py").write_text("changed source")
    with pytest.raises(RuntimeError, match="source identity"): portable.metadata()


def test_metadata_delay_must_match_actual_scripted_args_before_output(portable_trial):
    _, _, _, trial, portable, args = portable_trial
    args.probe_delay_seconds = 0
    with pytest.raises(ValueError, match="actual scripted trial"):
        challenge.run_trial(args, "fire-crew-recovery", 1, trial, None, None,
            scripted_probe=lambda *args: pytest.fail("No probe admitted"), portable_evidence=portable)
    assert not trial.exists()


def test_portable_hook_is_rejected_for_model_trials_before_output_creation(tmp_path):
    args = challenge.parser().parse_args([])
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="no-model scripted"):
        challenge.run_trial(args, "combat", 1, output, None, None, portable_evidence=object())
    assert not output.exists()


@pytest.mark.parametrize("failed_trial", [None, 1, 3])
def test_collection_uses_declared_delays_and_stops_after_failed_evidence(native, tmp_path, monkeypatch, failed_trial):
    root, _, _ = native
    (root / "scripts/validate_visual_timing.py").write_bytes(Path(timing.__file__).read_bytes())
    monkeypatch.setattr(timing, "ROOT", root)
    calls = []
    def run_trial(args, kind, repetition, output, cli, experiment, *, scripted_probe, portable_evidence):
        calls.append(repetition)
        metadata = portable_evidence.metadata()
        assert metadata["probe_delay_seconds"] == timing.DELAYS[repetition - 1]
        assert args.probe_delay_seconds == metadata["probe_delay_seconds"]
        output.mkdir(parents=True)
        data = reports(kind)[repetition - 1]
        evidence.write(output / "timing-proof.json", data)
        passed = repetition != failed_trial
        if passed:
            portable_evidence.descriptor = {"challenge": kind, "repetition": repetition, "delay_seconds": args.probe_delay_seconds}
        return {"outcome_category": "setup_verified" if passed else "infrastructure_failure",
            "save_restoration_verified": True, "production_source_unchanged": True}
    monkeypatch.setattr(timing.challenges, "run_trial", run_trial)
    output = tmp_path / "timing"
    code = timing.main(["--output", str(output), "--challenge", "repair-charge-escape"])
    assert calls == list(range(1, (failed_trial or 3) + 1))
    report = json.loads((output / "fixed-step-report.json").read_text())
    assert report["fixed_step_acceptance"]["claimed"] is (failed_trial is None)
    assert code == (0 if failed_trial is None else 1)
    descriptor = json.loads((output / "timing-evidence.json").read_text())
    assert len(descriptor["probes"]) == len(calls) - (1 if failed_trial else 0)
    snapshot = json.loads((output / "source-snapshot.json").read_text())
    assert snapshot["source_files"] == evidence.source_identity(root)
    with pytest.raises(FileExistsError): timing.main(["--output", str(output)])
