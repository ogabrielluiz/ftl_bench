"""Offline protected-child gates and saved admission joins, without game access."""
import copy
import json
from types import SimpleNamespace

import pytest

from ftl_bench import visual_admission as a
from ftl_bench.controller_admission import AdmissionError
from ftl_bench.experiment_admission import FULLGAME_CONTRACT, MATRIX_CONTRACT
from ftl_bench.native_acceptance import CAPABILITIES, RUNTIME_FILES, digest


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


@pytest.fixture(params=[FULLGAME_CONTRACT, MATRIX_CONTRACT])
def trial(tmp_path, monkeypatch, request):
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    files = {name: digest(name.encode()) for name in RUNTIME_FILES}
    production = digest(b"production Lua")
    build = {**CAPABILITIES, "dll_sha256": files["Hyperspace.dll"],
             "patch_sha256": digest(b"patch"), "matches_installed_dll": True}
    admission = {"contract": "portable-visual-controller-admission-v1",
                 "controller_admission": True, "production_accepted": False, "runtime_files": files,
                 "runtime": {"dll_sha256": build["dll_sha256"], "patch_sha256": build["patch_sha256"],
                             "production_bridge_sha256": production}}
    installed = {"files_sha256": files, "native_build": build}
    cli = {"path": "synthetic-cli", "sha256": digest(b"CLI")}
    common = {"seed": 1, "reasoning_effort": "medium",
              "budgets": {"decisions": 60, "wall_seconds": 1800, "idle_decisions": 8}}
    configuration = {**common, "model": "test-model", "mode": "image"}
    protocol = {"contract": request.param, **common, "codex_cli": cli,
                "admission_selector": {"spec": {"path": "spec.json", "sha256": digest(b"spec")},
                                       "admission": admission}}
    if request.param == FULLGAME_CONTRACT:
        configuration.update(scope="full_game", stop_after_sector=None)
        cell = {"id": "full-image", **{key: configuration[key] for key in
                                     ("model", "mode", "scope", "stop_after_sector")}}
        protocol["cells"] = [cell]
        output = cohort / "trials/full-image"
        deployed = production
    else:
        configuration.update(challenge="combat", repetition=1, setup_only=False)
        protocol.update(models=["test-model"], modes=["image"], challenges=["combat"], repetitions=3)
        output = cohort / "trials/test-model/image/combat/repeat-01/repetition-01/combat"
        deployed = digest(b"regenerated fixture Lua")
    output.mkdir(parents=True)
    fingerprint = {"native_build": copy.deepcopy(build), "bridge_lua": {"sha256": deployed}}
    experiment_file = cohort / "protocol.json"
    write(experiment_file, protocol)
    calls = []

    def verify(value, *, directory, verify_installed):
        calls.append((value, directory, verify_installed))

    monkeypatch.setattr(a, "installed_runtime", lambda root: copy.deepcopy(installed))
    kwargs = {"experiment_file": experiment_file, "output": output, "source_root": tmp_path,
              "fingerprint": fingerprint, "cli_identity": cli, "production_hash": production,
              "deployed_hash": deployed, "verify_protocol": verify, "configuration": configuration,
              "experiment": protocol}
    return locals()


def test_accepts_frozen_cell_and_records_runtime(trial):
    t = trial
    receipt = a.admit_trial(**t["kwargs"])
    assert receipt["accepted"] is True
    assert receipt["contract"] == a.TRIAL_CONTRACT
    assert receipt["protocol_sha256"] == digest(t["experiment_file"].read_bytes())
    assert receipt["selector_spec_sha256"] == t["protocol"]["admission_selector"]["spec"]["sha256"]
    assert receipt["admission"] == t["admission"]
    assert receipt["installed_runtime"] == t["installed"]
    assert receipt["deployed_bridge_sha256"] == t["deployed"]
    assert receipt["configuration"] == t["configuration"]
    assert t["calls"] == [(t["protocol"], t["cohort"], False)]
    assert json.loads((t["output"] / "controller-admission.json").read_bytes()) == receipt


@pytest.mark.parametrize("change", ["baseline", "runtime", "patch", "capability", "fingerprint", "cli", "production", "deployed", "configuration", "output", "protocol", "contract"])
def test_gate_rejects_and_retains_reason(trial, monkeypatch, change):
    t = trial
    kwargs = t["kwargs"]
    if change == "baseline":
        def reject(*args, **kw):
            raise AdmissionError("synthetic baseline rejected")
        kwargs["verify_protocol"] = reject
    elif change in ("runtime", "patch", "capability"):
        installed = copy.deepcopy(t["installed"])
        if change == "runtime":
            installed["files_sha256"]["ftl.dat"] = digest(b"substitute")
        elif change == "patch":
            installed["native_build"]["patch_sha256"] = digest(b"other patch")
        else:
            installed["native_build"]["fresh_start_seed"] = False
        monkeypatch.setattr(a, "installed_runtime", lambda root: installed)
    elif change == "fingerprint":
        kwargs["fingerprint"]["native_build"]["dll_sha256"] = digest(b"other DLL")
    elif change == "cli":
        kwargs["cli_identity"] = {"sha256": digest(b"other CLI")}
    elif change == "production":
        kwargs["production_hash"] = digest(b"other production")
    elif change == "deployed":
        kwargs["deployed_hash"] = digest(b"other deployment")
    elif change == "configuration":
        kwargs["configuration"]["budgets"] = {"decisions": 999, "wall_seconds": 1800, "idle_decisions": 8}
    elif change == "output":
        kwargs["output"] = t["cohort"] / "outside-cell"
        kwargs["output"].mkdir()
    elif change == "protocol":
        kwargs["experiment"] = {**t["protocol"], "unfrozen": True}
    else:
        protocol = {**t["protocol"], "contract": "unknown-experiment-v2"}
        write(t["experiment_file"], protocol)
        kwargs["experiment"] = protocol
    with pytest.raises(AdmissionError):
        a.admit_trial(**kwargs)
    receipt = json.loads((kwargs["output"] / "controller-admission.json").read_bytes())
    assert receipt["accepted"] is False
    assert receipt["error"]


def test_admission_record_is_exclusive(trial):
    t = trial
    a.admit_trial(**t["kwargs"])
    path = t["output"] / "controller-admission.json"
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        a.admit_trial(**t["kwargs"])
    assert path.read_bytes() == original


def test_prior_rejection_is_preserved(trial):
    t = trial
    t["kwargs"]["cli_identity"] = {}
    with pytest.raises(AdmissionError):
        a.admit_trial(**t["kwargs"])
    path = t["output"] / "controller-admission.json"
    original = path.read_bytes()
    t["kwargs"]["cli_identity"] = t["cli"]
    with pytest.raises(FileExistsError):
        a.admit_trial(**t["kwargs"])
    assert path.read_bytes() == original


@pytest.mark.parametrize("field,value", [("model", "outside-model"), ("mode", "hybrid"),
    ("seed", 2), ("reasoning_effort", "high"), ("scope", "sector_pilot"),
    ("stop_after_sector", 1), ("challenge", "outside-challenge"), ("repetition", 0),
    ("repetition", 4), ("repetition", True), ("setup_only", True)])
def test_configuration_cannot_leave_frozen_cell(trial, field, value):
    trial["kwargs"]["configuration"][field] = value
    with pytest.raises(AdmissionError):
        a.admit_trial(**trial["kwargs"])
    receipt = json.loads((trial["output"] / "controller-admission.json").read_bytes())
    assert receipt["accepted"] is False and receipt["error"]


def test_alternate_declared_pilot_or_repeat_accepts(trial):
    if trial["protocol"]["contract"] == FULLGAME_CONTRACT:
        trial["protocol"]["cells"][0].update(scope="sector_pilot", stop_after_sector=1)
        trial["configuration"].update(scope="sector_pilot", stop_after_sector=1)
    else:
        trial["configuration"]["repetition"] = 2
        output = trial["cohort"] / "trials/test-model/image/combat/repeat-02/repetition-01/combat"
        output.mkdir(parents=True)
        trial["kwargs"]["output"] = output
    write(trial["experiment_file"], trial["protocol"])
    assert a.admit_trial(**trial["kwargs"])["accepted"] is True


def test_output_requires_one_exact_declared_cell(trial):
    if trial["protocol"]["contract"] == FULLGAME_CONTRACT:
        trial["protocol"]["cells"].append(copy.deepcopy(trial["protocol"]["cells"][0]))
    else:
        trial["configuration"]["repetition"] = 2
    write(trial["experiment_file"], trial["protocol"])
    with pytest.raises(AdmissionError):
        a.admit_trial(**trial["kwargs"])


def saved_trial(t):
    receipt = a.admit_trial(**t["kwargs"])
    manifest = {"model": t["configuration"]["model"], "observation_mode": t["configuration"]["mode"],
                **{key: t["configuration"][key] for key in ("seed", "reasoning_effort", "budgets")},
                "controller_admission_sha256": digest((t["output"] / "controller-admission.json").read_bytes())}
    write(t["output"] / "run.json", manifest)
    write(t["output"] / "runtime-fingerprint.json", t["fingerprint"])
    return receipt, manifest


def test_saved_audit_accepts_without_live_access(trial, monkeypatch):
    saved_trial(trial)
    monkeypatch.setattr(a, "installed_runtime", lambda root: pytest.fail("audit accessed live runtime"))
    assert a.audit_trial_admission(trial["output"], trial["protocol"], protocol_file=trial["experiment_file"]) == []


@pytest.mark.parametrize("change", ["receipt", "receipt_hash", "protocol_hash", "spec", "admission", "runtime", "fingerprint", "bridge", "config", "manifest", "missing"])
def test_saved_audit_rejects_tampering(trial, change):
    t = trial
    receipt, manifest = saved_trial(t)
    path = t["output"] / "controller-admission.json"
    if change == "receipt":
        receipt["accepted"] = False
    elif change == "receipt_hash":
        manifest["controller_admission_sha256"] = digest(b"other receipt")
    elif change == "protocol_hash":
        t["experiment_file"].write_bytes(t["experiment_file"].read_bytes() + b"\n")
    elif change == "spec":
        receipt["selector_spec_sha256"] = digest(b"other spec")
    elif change == "admission":
        receipt["admission"]["runtime"]["patch_sha256"] = digest(b"other admission")
    elif change == "runtime":
        receipt["installed_runtime"]["files_sha256"]["ftl.dat"] = digest(b"other runtime")
    elif change == "fingerprint":
        fingerprint = copy.deepcopy(t["fingerprint"])
        fingerprint["native_build"]["patch_sha256"] = digest(b"other fingerprint")
        write(t["output"] / "runtime-fingerprint.json", fingerprint)
    elif change == "bridge":
        fingerprint = copy.deepcopy(t["fingerprint"])
        fingerprint["bridge_lua"]["sha256"] = digest(b"other bridge")
        write(t["output"] / "runtime-fingerprint.json", fingerprint)
    elif change == "config":
        receipt["configuration"]["mode"] = "hybrid"
    elif change == "manifest":
        manifest["seed"] = 2
    else:
        (t["output"] / "runtime-fingerprint.json").unlink()
    if change not in ("receipt_hash", "protocol_hash", "fingerprint", "bridge", "manifest", "missing"):
        # Re-pin changed receipt to ensure semantic joins, not only its hash, reject it.
        write(path, receipt)
        manifest["controller_admission_sha256"] = digest(path.read_bytes())
    write(t["output"] / "run.json", manifest)
    issues = a.audit_trial_admission(t["output"], t["protocol"], protocol_file=t["experiment_file"])
    assert issues and all(issue.startswith("Controller admission:") for issue in issues)


def test_configuration_builds_fullgame_pilot_and_challenge():
    args = SimpleNamespace(model="test-model", mode="image", seed=1, reasoning_effort="medium",
                           max_decisions=60, max_wall_seconds=1800, max_idle_decisions=8,
                           stop_after_sector=None, setup_only=False)
    full = a.trial_configuration(args)
    assert full["scope"] == "full_game" and full["stop_after_sector"] is None
    args.stop_after_sector = 1
    pilot = a.trial_configuration(args)
    assert pilot["scope"] == "sector_pilot" and pilot["stop_after_sector"] == 1
    challenge = a.trial_configuration(args, challenge="combat", repetition=2)
    assert challenge["challenge"] == "combat" and challenge["repetition"] == 2
    assert challenge["setup_only"] is False and "scope" not in challenge


def test_legacy_saved_audit_does_not_require_portable_receipt(tmp_path):
    assert a.audit_trial_admission(tmp_path, {"contract": "ftl-fullgame-experiment-v1"},
                                   protocol_file=tmp_path / "missing.json") == []


@pytest.mark.parametrize("field,value", [("controller_admission", False), ("controller_admission", None),
    ("controller_admission", 1), ("production_accepted", True), ("production_accepted", None),
    ("production_accepted", 0), ("contract", "wrong-contract"), ("contract", None)])
def test_saved_audit_rejects_repinned_invalid_admission_state(trial, field, value):
    receipt, manifest = saved_trial(trial)
    admitted = trial["protocol"]["admission_selector"]["admission"]
    if value is None: admitted.pop(field)
    else: admitted[field] = value
    write(trial["experiment_file"], trial["protocol"])
    receipt["admission"] = admitted
    receipt["protocol_sha256"] = digest(trial["experiment_file"].read_bytes())
    path = trial["output"] / "controller-admission.json"
    write(path, receipt)
    manifest["controller_admission_sha256"] = digest(path.read_bytes())
    write(trial["output"] / "run.json", manifest)
    issues = a.audit_trial_admission(trial["output"], trial["protocol"], protocol_file=trial["experiment_file"])
    assert issues == ["Controller admission: Saved controller admission state is invalid"]
