"""Real startup/capture/runner/restore lifecycle with fake native I/O only."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

import validate_visual_startup as probe
import ftl_bench.protected_game as protection
from ftl_bench.session import AgentSession
from ftl_bench.observation import Observation, ObservationClient
from ftl_bench.trajectory import load_trajectory
from test_fullgame_setup import immediate
from test_visual_session import observed, png
from ftl_bench import native_acceptance


@pytest.fixture
def native(tmp_path, monkeypatch):
    root, save, game = (tmp_path / name for name in ("repo", "save", "game"))
    for path in (root, save, game): path.mkdir()
    bridge = root / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
    bridge.parent.mkdir(parents=True); bridge.write_text("new bridge")
    (root / "adapter").mkdir(); (root / "adapter/start.py").write_text("source")
    package = root / "harness/src/ftl_bench"; package.mkdir(parents=True)
    (package / "native_acceptance.py").write_bytes(Path(native_acceptance.__file__).read_bytes())
    (save / "original.sav").write_bytes(b"original save")
    (save / "ftl_bench_dev.lua").write_bytes(b"original bridge")
    (save / "capture.png").write_bytes(png(1280, 720))
    (root / "scripts").mkdir()
    for name in ("run_fullgame_experiment.py", "validate_native_acceptance.py", "write_native_provenance.py",
                 "collect_native_source_evidence.py"):
        (root / "scripts" / name).write_text("source")
    for name in ("FTLGame.exe", "ftl.dat", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll", "ftlbench-native.json"):
        (game / name).write_bytes(name.encode())
    state = {"raw": {"schema_version": 3, "tick": 0, "seed": 0, "game_started": False, "paused": False, "last_action_seq": 0},
             "packets": [], "launches": 0, "fault": None}
    monkeypatch.setattr(probe, "ROOT", root)
    monkeypatch.setattr(probe, "ftl_user_folder", lambda: save)
    monkeypatch.setattr(protection, "game_directory", lambda directory=None: game)
    monkeypatch.setattr(protection, "_processes", lambda: [])
    monkeypatch.setattr(protection, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(probe, "_processes", lambda: [])
    monkeypatch.setattr(probe, "runtime_fingerprint", lambda root: {
        "bridge_lua": {"path": str(save / "ftl_bench_dev.lua"), "sha256": probe.digest(save / "ftl_bench_dev.lua")
                       if (save / "ftl_bench_dev.lua").is_file() else None},
        "native_dll": {"sha256": probe.digest(game / "Hyperspace.dll")}, "native_build": {
        **native_acceptance.CAPABILITIES, "dll_sha256": probe.digest(game / "Hyperspace.dll"),
        "matches_installed_dll": True, "fresh_start_seed": True,
        "fresh_seed_contract": "fresh-start-seed-v3", "fresh_seed_contract_version": 3}})
    def launch(self):
        state["launches"] += 1
        if (save / "ftl_bench_dev.lua").exists():
            shutil.copy2(save / "ftl_bench_dev.lua", self.backup / "ftl_bench_dev.lua")
        shutil.copy2(self.bridge, save / "ftl_bench_dev.lua")
        (save / "original.sav").write_bytes(b"changed by native")
        (save / "generated.sav").write_bytes(b"native generated")
        if state["fault"] == "launch": raise RuntimeError("launch failed")
    monkeypatch.setattr(protection.ProtectedGame, "launch", launch)
    monkeypatch.setattr(ObservationClient, "read_latest", lambda self: Observation.from_dict(copy.deepcopy(state["raw"])))
    def dispatch(self, packet):
        state["packets"].append(copy.deepcopy(packet))
        if packet["actions"]:
            assert packet["actions"] == [{"type": "start_game", "mode": "new", "seed": packet["actions"][0]["seed"]}]
            assert packet["advance_frames"] == 0
            seed = packet["actions"][0]["seed"]
            raw = immediate(seed)
            raw.update(schema_version=3, tick=1, seed=seed, paused=True, difficulty=0, ftl_score=0, victory=False,
                       player_ship={"blueprint": "PLAYER_SHIP_HARD"}, last_action_seq=1)
            raw["deterministic_setup"]["phase"] = "ready"
            raw["capabilities"].update(external_input_guard=True, live_score=True, victory=True, native_protocol=5)
            raw.pop("visual")
            state["raw"] = raw
        else:
            assert packet == {"seq": 2, "advance_frames": 0, "actions": [], "observation_mode": "visual-v1"}
            raw = state["raw"]
            raw["last_action_seq"] = 2
            raw["deterministic_setup"]["phase"] = "visual"
            raw["visual"] = observed(2, width=1280, height=720, external_input_guard=True).raw["visual"]
            raw["visual_evaluator"] = {"choice_window_open": True, "blocked_reason": "choice_open"}
            if state["fault"] == "admission": raw["deterministic_setup"]["native_seed"]["seed"] += 1
            if state["fault"] == "opening": raw["visual_evaluator"]["choice_window_open"] = False
    monkeypatch.setattr(AgentSession, "_write_action_atomic", dispatch)
    monkeypatch.setattr(probe.NoModel, "decide", lambda *args: pytest.fail("Actor called"))
    return root, save, state


def test_startup_uses_real_zero_decision_capture_and_restores_originals(native, tmp_path):
    root, save, state = native
    output = probe.validate(tmp_path / "result", seed=23)
    assert len(state["packets"]) == 2 and state["launches"] == 1
    assert (save / "original.sav").read_bytes() == b"original save"
    assert (save / "ftl_bench_dev.lua").read_bytes() == b"original bridge"
    assert not (save / "generated.sav").exists()
    assert (output / "save-backup/benchmark-generated/generated.sav").read_bytes() == b"native generated"
    rows = load_trajectory(output / "trajectory.jsonl")
    assert [row["kind"] for row in rows] == ["meta", "reset", "end"]
    assert rows[1]["actions"] == [] and rows[1]["visual"]["inputs"] == []
    assert rows[-1]["reason"] == "decision_budget"
    admission = json.loads((output / "fresh-setup/admission.json").read_text())
    assert admission["passed"] and admission["first_observation"]["seed"] == 23
    image = output / admission["first_image"]["path"]
    assert image.read_bytes() == (save / "capture.png").read_bytes()
    receipt = json.loads((output / "validation.json").read_text())
    assert receipt["status"] == "passed" and all(receipt["checks"].values())
    assert all(probe.digest(output / name) == sha for name, sha in receipt["artifact_sha256"].items())
    assert (output / "sources/adapter/start.py").read_bytes() == (root / "adapter/start.py").read_bytes()
    before = json.loads((output / "prelaunch-runtime-fingerprint.json").read_text())["bridge_lua"]["sha256"]
    deployed = json.loads((output / "runtime-fingerprint.json").read_text())["bridge_lua"]["sha256"]
    assert before != deployed == probe.digest(root / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua")
    assert json.loads((output / "run.json").read_text())["reason"] == rows[-1]["reason"] == "decision_budget"
    descriptor = json.loads((output / "startup-evidence.json").read_text())
    assert rows[0]["meta"]["source_files_sha256"] == hashlib.sha256(json.dumps(
        receipt["source_files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    accepted = native_acceptance._startup(native_acceptance.Reader(output), descriptor["startup"],
        probe.digest(Path(json.loads((output / "installed-runtime.json").read_text())["files"]["Hyperspace.dll"]["path"])), deployed,
        expected_source_digest=rows[0]["meta"]["source_files_sha256"],
        provenance_sha=probe.digest(Path(json.loads((output / "installed-runtime.json").read_text())["files"]["ftlbench-native.json"]["path"])))
    assert accepted["seed"] == 23 and accepted["cleanup"]["save_paths"] == 1


@pytest.mark.parametrize("fault", ["launch", "admission", "opening"])
def test_failure_preserves_raw_evidence_and_restores_saves(native, tmp_path, fault):
    _, save, state = native
    state["fault"] = fault
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError): probe.validate(output)
    assert (save / "original.sav").read_bytes() == b"original save"
    assert not (save / "generated.sav").exists()
    receipt = json.loads((output / "validation.json").read_text())
    assert receipt["status"] == "error" and receipt["error"]
    assert json.loads((output / "save-backup/restoration.json").read_text())["verified"]
    assert load_trajectory(output / "trajectory.jsonl")[-1]["kind"] == "end"
    assert len(state["packets"]) <= 2
    if fault == "opening": assert (output / "fresh-setup/admission.json").exists()


@pytest.mark.parametrize("primary", [False, True])
def test_cleanup_error_is_raised_and_recorded_even_after_capture(native, tmp_path, monkeypatch, primary):
    _, save, state = native
    if primary: state["fault"] = "opening"
    def fail_restore(self): raise RuntimeError("restore refused")
    monkeypatch.setattr(protection.ProtectedGame, "restore_saves", fail_restore)
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="restore refused"): probe.validate(output)
    receipt = json.loads((output / "validation.json").read_text())
    assert receipt["status"] == "error" and receipt["cleanup_error"] == "restore refused"
    if primary: assert "Startup admission checks failed" in receipt["error"]
    assert (output / "save-backup/original.sav").read_bytes() == b"original save"
    assert (save / "original.sav").read_bytes() == b"changed by native"


def test_existing_output_and_invalid_seed_never_launch(native, tmp_path):
    _, _, state = native
    output = tmp_path / "existing"; output.mkdir(); (output / "keep").write_text("untouched")
    with pytest.raises(FileExistsError): probe.validate(output)
    with pytest.raises(ValueError): probe.validate(tmp_path / "invalid", True)
    assert (output / "keep").read_text() == "untouched"
    assert not (tmp_path / "invalid").exists() and state["launches"] == 0


def test_unproven_runtime_retains_snapshot_without_launch(native, tmp_path, monkeypatch):
    _, save, state = native
    monkeypatch.setattr(probe, "runtime_fingerprint", lambda root: {"native_build": None})
    output = tmp_path / "refused"
    with pytest.raises(RuntimeError, match="provenance"): probe.validate(output)
    assert state["launches"] == 0 and state["packets"] == []
    assert (save / "original.sav").read_bytes() == b"original save"
    assert (output / "source-snapshot.json").exists()
    assert json.loads((output / "validation.json").read_text())["status"] == "error"
    assert load_trajectory(output / "trajectory.jsonl")[-1]["status"] == "error"


def test_receipt_write_failure_propagates_after_verified_cleanup(native, tmp_path, monkeypatch):
    _, save, _ = native
    original_write = probe.write
    def write(path, value):
        if Path(path).name == "validation.json": raise OSError("receipt unavailable")
        return original_write(path, value)
    monkeypatch.setattr(probe, "write", write)
    output = tmp_path / "unfinalized"
    with pytest.raises(OSError, match="receipt unavailable"): probe.validate(output)
    assert (save / "original.sav").read_bytes() == b"original save"
    assert json.loads((output / "save-backup/restoration.json").read_text())["verified"]
    assert (output / "fresh-setup/admission.json").exists()
    assert not (output / "validation.json").exists()


def test_finalization_error_cannot_replace_cleanup_error(native, tmp_path, monkeypatch):
    original_write = probe.write
    def write(path, value):
        if Path(path).name == "validation.json": raise OSError("receipt unavailable")
        original_write(path, value)
    def fail_restore(self): raise RuntimeError("restore refused")
    monkeypatch.setattr(probe, "write", write)
    monkeypatch.setattr(protection.ProtectedGame, "restore_saves", fail_restore)
    with pytest.raises(ExceptionGroup) as errors: probe.validate(tmp_path / "failed")
    assert [str(error) for error in errors.value.exceptions] == ["restore refused", "receipt unavailable"]


def test_common_evidence_root_resolves_all_nested_startup_refs(native, tmp_path):
    root, _, _ = native
    common = tmp_path / "candidate"
    output = probe.validate(common / "startup", evidence_root=common)
    descriptor = json.loads((output / "startup-evidence.json").read_text())
    reader = native_acceptance.Reader(common)
    snapshot = reader.json(descriptor["source_snapshot"], "snapshot")
    for name, ref in snapshot["archived_files"].items():
        assert ref["path"].startswith("startup/sources/")
        assert reader.bytes(ref, "source") == (root / name).read_bytes()
    manifest = json.loads((output / "run.json").read_text())
    accepted = native_acceptance._startup(reader, descriptor["startup"],
        probe.digest(native[0].parent / "game/Hyperspace.dll"),
        probe.digest(root / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"),
        expected_source_digest=manifest["source_files_sha256"],
        provenance_sha=probe.digest(native[0].parent / "game/ftlbench-native.json"))
    assert accepted["cleanup"]["save_paths"] == 1


def test_outside_common_evidence_root_refused_before_output_or_launch(native, tmp_path):
    _, _, state = native
    with pytest.raises(ValueError, match="evidence root"):
        probe.validate(tmp_path / "outside", evidence_root=tmp_path / "candidate")
    assert not (tmp_path / "outside").exists() and state["launches"] == 0


def test_added_source_during_startup_invalidates_receipt_after_restore(native, tmp_path, monkeypatch):
    root, save, _ = native
    launch = protection.ProtectedGame.launch
    def drift(self):
        launch(self)
        (root / "adapter/added.py").write_text("new source after snapshot")
    monkeypatch.setattr(protection.ProtectedGame, "launch", drift)
    output = tmp_path / "drift"
    with pytest.raises(RuntimeError, match="admission checks failed"): probe.validate(output)
    assert (save / "original.sav").read_bytes() == b"original save"
    assert not (output / "portable-cleanup.json").exists()
    assert json.loads((output / "validation.json").read_text())["status"] == "error"


@pytest.mark.parametrize("fault", [None, "launch", "admission", "opening"])
def test_originally_absent_bridge_is_restored_on_success_and_startup_failures(native, tmp_path, fault):
    _, save, state = native
    (save / "ftl_bench_dev.lua").unlink()
    state["fault"] = fault
    output = tmp_path / "absent"
    if fault:
        with pytest.raises(RuntimeError): probe.validate(output)
    else:
        probe.validate(output)
        cleanup = json.loads((output / "portable-cleanup.json").read_text())
        assert cleanup["before"]["save/ftl_bench_dev.lua"] is None
        assert cleanup["before"] == cleanup["after"]
        descriptor = json.loads((output / "startup-evidence.json").read_text())["startup"]
        assert cleanup["trajectory"] == descriptor["trajectory"]
        assert cleanup["session"] == descriptor["session"]
    assert not (save / "ftl_bench_dev.lua").exists()
    assert (save / "original.sav").read_bytes() == b"original save"
    assert json.loads((output / "save-backup/restoration.json").read_text())["verified"]


@pytest.mark.parametrize("unsafe", ["changed", "directory", "game_process"])
def test_absent_bridge_cleanup_refuses_unowned_content_or_surviving_game(native, tmp_path, monkeypatch, unsafe):
    _, save, _ = native
    target = save / "ftl_bench_dev.lua"
    target.unlink()
    launch = protection.ProtectedGame.launch
    def interfere(self):
        launch(self)
        if unsafe == "changed": target.write_text("unexpected bridge")
        elif unsafe == "directory": target.unlink(); target.mkdir()
        else: monkeypatch.setattr(probe, "_processes", lambda: [{"id": 999}])
    monkeypatch.setattr(protection.ProtectedGame, "launch", interfere)
    output = tmp_path / "refused"
    with pytest.raises((RuntimeError, ExceptionGroup)): probe.validate(output)
    assert target.exists()
    receipt = json.loads((output / "validation.json").read_text())
    assert receipt["status"] == "error" and receipt["cleanup_error"]
    assert not (output / "portable-cleanup.json").exists()
    assert (save / "original.sav").read_bytes() == b"original save"
