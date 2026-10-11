"""Natural native STORE arrival and protected no-model diagnostic checks."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

import validate_store_arrival as probe
import ftl_bench.protected_game as protection
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory
from ftl_bench.visual_session import VisualFrame
from test_visual_session import observed, png
from test_challenge_setup import good_receipt


class ScriptedTransport:
    def __init__(self, output, *, old=False, fault=None):
        self.output, self.old, self.fault = output, old, fault
        self.ordinal, self.counter = 0, 0
        (output / "screens").mkdir()
        self.arrived = False
        self.continued = False
    def frame(self, actions, requested, actual, *, store=False, jumping=False):
        self.ordinal += 1
        self.counter += actual
        image = self.output / "screens" / f"{self.ordinal}.png"
        image.write_bytes(png(1280, 720))
        feedback = [{"index": i, "type": a["type"], "status": "delivered"} for i, a in enumerate(actions)]
        if self.fault == "ack" and actions: feedback = []
        counter = self.counter + (1 if self.fault == "delta" and requested else 0)
        obs = observed(self.ordinal, width=1280, height=720, world_updates=str(counter),
                       requested_frames=requested, actual_frames=actual, input_feedback=feedback)
        obs.raw.update(visual_evaluator={"store_open": store, "player_jumping": jumping,
                                         "choice_window_open": self.fault in ("choice", "continue", "continue-blocked") and not self.continued,
                                         "blocked_reason": "choice_box_open" if self.fault in ("choice", "continue", "continue-blocked") and not self.continued else ("store_open" if store else "")},
                       player_ship={"resources": {"fuel": 14 if self.fault == "fuel" else (15 if self.arrived else 16)}},
                       map={"current_pos": None if jumping else {"x": 49, "y": 231}})
        if self.fault in ("continue", "continue-blocked"):
            obs.raw["event"] = {"dialog_keys": 1, "selected_choice": -1,
                                "choices": [{"index": 0, "text": "Continue...", "enabled": True, "disabled": False}]}
        ref = {"path": image.relative_to(self.output).as_posix(), "sha256": probe.digest(image),
               "width": 1280, "height": 720, "capture_id": self.ordinal, "frame_id": str(self.ordinal)}
        return VisualFrame(obs, image, ref, self.ordinal)
    def capture(self): return self.frame([], 0, 0)
    def step(self, before, actions, requested):
        if not self.arrived:
            self.arrived = True
            return self.frame(actions, requested, 122, store=True, jumping=self.old)
        if actions:
            if actions[0].get("y") == 317:
                self.continued = self.fault != "continue-blocked"
                return self.frame(actions, requested, 0, store=True)
            return self.frame(actions, requested, 0, store=self.fault == "close")
        return self.frame(actions, requested, 0, store=True, jumping=self.old)


def execute_probe(tmp_path, monkeypatch, *, wait_log=None, **kwargs):
    monkeypatch.setattr(probe.time, "sleep", lambda seconds: wait_log.append(seconds) if wait_log is not None else None)
    monkeypatch.setattr(probe, "packet_proof", lambda *a: {"passed": True})
    monkeypatch.setattr(probe, "receipt_proof", lambda *a, **kw: {"passed": True})
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl", {"model_calls": 0})
    return probe.run_probe(SimpleNamespace(setup_packets=[]), ScriptedTransport(tmp_path, **kwargs),
                           recorder, tmp_path, {"x": 88, "y": 152}, {"x": 49, "y": 231}, 16)


def test_old_runtime_hidden_store_rejection_retains_repeated_zero_and_pngs(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="regression reproduced"):
        execute_probe(tmp_path, monkeypatch, old=True)
    proof = json.loads((tmp_path / "store-arrival-proof.json").read_text())
    assert proof["status"] == "rejected" and proof["model_calls"] == 0
    assert [step["actual_frames"] for step in proof["steps"]] == [122, 0, 0]
    assert all(step["fuel"] == 15 for step in proof["steps"])
    assert "fixture" not in proof
    assert all(step["visual_evaluator"]["store_open"] and step["visual_evaluator"]["player_jumping"]
               for step in proof["steps"])
    assert all(probe.digest(tmp_path / step["after_image"]["path"]) == step["after_image"]["sha256"]
               for step in proof["steps"])


def test_fixed_runtime_arrival_store_block_and_ordinary_close_are_archived(tmp_path, monkeypatch):
    proof = execute_probe(tmp_path, monkeypatch)
    assert proof["status"] == "passed" and proof["model_calls"] == 0
    assert [row["label"] for row in proof["steps"]] == ["native-arrival-1", "settled-visible-store-blocks", "ordinary-store-close"]
    assert proof["steps"][1]["actual_frames"] == 0
    assert proof["steps"][-1]["inputs_delivered"] and proof["steps"][-1]["actions"][0]["type"] == "click"
    assert not proof["steps"][-1]["visual_evaluator"]["store_open"]
    assert not any(row.get("model") for row in load_trajectory(tmp_path / "trajectory.jsonl"))


def test_natural_arrival_choice_precedence_archived_without_guessed_input(tmp_path, monkeypatch):
    proof = execute_probe(tmp_path, monkeypatch, fault="choice")
    assert proof["status"] == "review_required"
    assert len(proof["steps"]) == 1
    assert proof["steps"][0]["actions"] == []
    assert proof["steps"][0]["visual_evaluator"]["choice_window_open"] is True
    assert proof["steps"][0]["visual_evaluator"]["blocked_reason"] == "choice_box_open"
    assert (tmp_path / proof["steps"][0]["after_image"]["path"]).is_file()


@pytest.mark.parametrize("blocked", [False, True])
def test_exact_continue_uses_debounced_visual_click_and_retains_blocker(tmp_path, monkeypatch, blocked):
    waits = []
    if blocked:
        with pytest.raises(RuntimeError, match="Continue transition failed"):
            execute_probe(tmp_path, monkeypatch, fault="continue-blocked", wait_log=waits)
        proof = json.loads((tmp_path / "store-arrival-proof.json").read_text())
        assert proof["status"] == "rejected"
    else:
        proof = execute_probe(tmp_path, monkeypatch, fault="continue", wait_log=waits)
        assert proof["status"] == "passed"
    assert proof["steps"][1]["label"] == "arrival-choice-debounce-capture"
    assert proof["steps"][1]["requested_frames"] == 0
    click = proof["steps"][2]
    assert click["requested_frames"] == 1 and click["inputs_delivered"]
    assert click["actions"] == [{"type": "click", "x": 405, "y": 317, "button": "left", "modifiers": []}]
    assert click["visual_evaluator"]["choice_window_open"] is blocked
    assert waits == [0.35]


@pytest.mark.parametrize("change", [
    {"text": "Buy supplies"}, {"enabled": False}, {"disabled": True}, {"index": 1}, {"index": False}])
def test_continue_guard_rejects_other_choice_semantics(change):
    raw = {"event": {"dialog_keys": 1, "selected_choice": -1,
                     "choices": [{"index": 0, "text": "Continue...", "enabled": True, "disabled": False}]}}
    assert probe.single_continue(raw)
    raw["event"]["choices"][0].update(change)
    assert not probe.single_continue(raw)


@pytest.mark.parametrize("fault", ["delta", "ack", "fuel", "close"])
def test_accounting_fuel_and_control_mismatches_reject(tmp_path, monkeypatch, fault):
    with pytest.raises(RuntimeError): execute_probe(tmp_path, monkeypatch, fault=fault)


@pytest.fixture
def protected_native(tmp_path, monkeypatch):
    root, save, game = (tmp_path / name for name in ("repo", "save", "game"))
    for path in (root, save, game): path.mkdir()
    source = root / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"production bridge")
    package = root / "harness/src/ftl_bench"
    package.mkdir(parents=True)
    (package / "native_acceptance.py").write_bytes(b"verifier")
    (root / "scripts").mkdir()
    for name in ("run_fullgame_experiment.py", "validate_native_acceptance.py", "write_native_provenance.py", "collect_native_source_evidence.py"):
        (root / "scripts" / name).write_bytes(b"source")
    for name in probe.evidence.RUNTIME_FILES: (game / name).write_bytes(name.encode())
    (save / "original.sav").write_bytes(b"original save")
    (save / "ftl_bench_dev.lua").write_bytes(b"original bridge")
    monkeypatch.setattr(probe, "ROOT", root)
    monkeypatch.setattr(probe, "ftl_user_folder", lambda: save)
    monkeypatch.setattr(protection, "game_directory", lambda *a: game)
    monkeypatch.setattr(protection, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(protection, "_processes", lambda: [])
    monkeypatch.setattr(probe, "_processes", lambda: [])
    monkeypatch.setattr(probe, "runtime_fingerprint", lambda root: {
        "native_build": {**probe.CAPABILITIES, "matches_installed_dll": True},
        "native_dll": {"sha256": probe.digest(game / "Hyperspace.dll")},
        "bridge_lua": {"sha256": probe.digest(save / "ftl_bench_dev.lua") if (save / "ftl_bench_dev.lua").exists() else None}})
    def launch(self):
        if (save / "ftl_bench_dev.lua").exists(): shutil.copy2(save / "ftl_bench_dev.lua", self.backup / "ftl_bench_dev.lua")
        shutil.copy2(self.bridge, save / "ftl_bench_dev.lua")
        (save / "original.sav").write_bytes(b"changed by native")
        (save / "generated.sav").write_bytes(b"generated by native")
    monkeypatch.setattr(protection.ProtectedGame, "launch", launch)
    monkeypatch.setattr(probe, "prepare", lambda *a: ({"x": 88, "y": 152}, {"x": 49, "y": 231}, 16))
    monkeypatch.setattr(probe, "DeterministicSetupSession", lambda *a, **kw: SimpleNamespace())
    monkeypatch.setattr(probe, "VisualSession", lambda *a: SimpleNamespace())
    monkeypatch.setattr(probe, "run_probe", lambda *a: {"status": "passed"})
    return root, save, game


@pytest.mark.parametrize("failed,absent_bridge", [(False, False), (True, False), (False, True), (True, True)])
def test_protected_lifecycle_restores_saves_bridge_and_snapshots_after_failure(protected_native, tmp_path, monkeypatch, failed, absent_bridge):
    root, save, game = protected_native
    if absent_bridge: (save / "ftl_bench_dev.lua").unlink()
    if failed:
        monkeypatch.setattr(probe, "run_probe", lambda *a: (_ for _ in ()).throw(RuntimeError("arrival rejected")))
    output = tmp_path / "run"
    if failed:
        with pytest.raises(RuntimeError, match="arrival rejected"): probe.validate(output)
    else: probe.validate(output)
    assert (save / "original.sav").read_bytes() == b"original save"
    assert not (save / "generated.sav").exists()
    if absent_bridge: assert not (save / "ftl_bench_dev.lua").exists()
    else: assert (save / "ftl_bench_dev.lua").read_bytes() == b"original bridge"
    value = json.loads((output / "validation.json").read_text())
    assert all(value["checks"].values()) and value["model_calls"] == 0
    assert value["status"] == ("error" if failed else "completed")
    assert value["artifact_sha256"]["probe-driver.py"] == probe.digest(Path(probe.__file__))
    assert (output / "production-bridge.lua").read_bytes() == (root / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua").read_bytes()
    assert not (output / "fixture-bridge.lua").exists()
    assert json.loads((output / "save-backup/restoration.json").read_text())["verified"]
    assert load_trajectory(output / "trajectory.jsonl")[-1]["status"] == ("error" if failed else "completed")


def test_cleanup_failure_retains_primary_and_restoration_error(protected_native, tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "run_probe", lambda *a: (_ for _ in ()).throw(RuntimeError("arrival rejected")))
    monkeypatch.setattr(protection.ProtectedGame, "restore_saves", lambda self: (_ for _ in ()).throw(RuntimeError("restore failed")))
    with pytest.raises(BaseExceptionGroup): probe.validate(tmp_path / "failed")
    value = json.loads((tmp_path / "failed/validation.json").read_text())
    assert value["error"] == "arrival rejected" and value["cleanup_error"] == "restore failed"
    assert value["cleanup_verification_error"]


def test_existing_output_never_enters_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "ProtectedGame", lambda *a: pytest.fail("output reused"))
    with pytest.raises(FileExistsError): probe.validate(tmp_path)


@pytest.mark.parametrize("accepted", [True, False])
def test_prepare_uses_normal_charge_and_acknowledged_zero_update_jump(tmp_path, monkeypatch, accepted):
    calls = []
    class SetupSession:
        def configure_setup(self, output): calls.append(("configure", output))
        def obs(self, ready=False, feedback=None):
            raw = good_receipt()
            raw["deterministic_setup"].update(phase="ready", active=True)
            raw["deterministic_setup"]["native_seed"]["start_completion_scope_active"] = True
            raw.update({"map": {"current_pos": {"x": 88, "y": 152},
                       "connected_beacons": [{"index": 1, "pos_x": 49, "pos_y": 231}]},
                       "economy": {"navigation": {"can_jump": ready}},
                       "player_ship": {"resources": {"fuel": 16}}, "action_feedback": feedback or []})
            return SimpleNamespace(raw=raw, choice_box_open=False)
        def reset_episode(self, seed):
            calls.append(("fresh", seed)); return self.obs()
        def reset(self): calls.append(("reset",)); return self.obs()
        def step(self, actions, frames):
            calls.append(("step", actions, frames))
            if actions:
                return self.obs(ready=True, feedback=[{"type": "jump", "beacon_index": 1,
                    "status": "applied" if accepted else "rejected"}])
            return self.obs(ready=frames == 300)
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    if accepted:
        assert probe.prepare(SetupSession(), tmp_path, recorder) == ({"x": 88, "y": 152}, {"x": 49, "y": 231}, 16)
    else:
        with pytest.raises(RuntimeError, match="not acknowledged"): probe.prepare(SetupSession(), tmp_path, recorder)
    assert calls[1] == ("fresh", 1)
    assert calls[-2:] == [("step", [], 300), ("step", [{"type": "jump", "beacon_index": 1}], 0)]
    proof = json.loads((tmp_path / "pre-handoff-setup-proof.json").read_text())
    assert proof["authoritative"] is False
    assert proof["receipt_proof"]["passed"] is False
    assert [k for k, v in proof["receipt_proof"]["checks"].items() if not v] == ["start_boundary_measured"]


@pytest.mark.parametrize("scope_active", [False, True])
def test_handoff_validates_refreshed_native_scope_and_retains_false_proof(tmp_path, monkeypatch, scope_active):
    transport = ScriptedTransport(tmp_path)
    initial = transport.capture()
    initial.observation.raw.update(good_receipt())
    initial.observation.raw["deterministic_setup"]["native_seed"]["start_completion_scope_active"] = scope_active
    transport.counter = 90
    monkeypatch.setattr(transport, "capture", lambda: initial)
    monkeypatch.setattr(probe, "packet_proof", lambda *a: {"passed": True})
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl")
    args = (SimpleNamespace(setup_packets=[]), transport, recorder, tmp_path,
            {"x": 88, "y": 152}, {"x": 49, "y": 231}, 16)
    if scope_active:
        with pytest.raises(RuntimeError, match="receipt failed at visual handoff"):
            probe.run_probe(*args)
        assert transport.ordinal == 1  # No native travel requested after rejected setup.
    else:
        assert probe.run_probe(*args)["status"] == "passed"
    proof = json.loads((tmp_path / "handoff-setup-proof.json").read_text())
    assert proof["authoritative"] is True
    assert proof["receipt_proof"]["passed"] is (not scope_active)
    assert proof["receipt_proof"]["checks"]["start_boundary_measured"] is (not scope_active)
