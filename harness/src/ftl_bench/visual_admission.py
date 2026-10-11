"""Record a portable controller gate inside a protected visual child."""
from __future__ import annotations

import json
from pathlib import Path

from ftl_bench.controller_admission import AdmissionError
from ftl_bench.experiment_admission import FULLGAME_CONTRACT, PORTABLE_CONTRACTS, installed_runtime, require_installed
from ftl_bench.native_acceptance import digest, read_json

TRIAL_CONTRACT = "portable-visual-trial-admission-v1"


def trial_configuration(args, *, challenge=None, repetition=None):
    result = {"model": args.model, "mode": args.mode, "seed": args.seed,
              "reasoning_effort": args.reasoning_effort,
              "budgets": {"decisions": args.max_decisions, "wall_seconds": args.max_wall_seconds,
                          "idle_decisions": args.max_idle_decisions}}
    if challenge is None:
        result.update(scope="sector_pilot" if args.stop_after_sector is not None else "full_game",
                      stop_after_sector=args.stop_after_sector)
    else:
        result.update(challenge=challenge, repetition=repetition, setup_only=args.setup_only)
    return result


def _require_configuration(protocol, configuration, output, cohort):
    """Bind actual arguments and output to one declared cell before quota use."""
    common = {key: protocol[key] for key in ("seed", "reasoning_effort", "budgets")}
    if protocol["contract"] == FULLGAME_CONTRACT:
        matches = [cell for cell in protocol["cells"]
                   if (cohort / "trials" / cell["id"]).resolve() == Path(output).resolve()]
        if len(matches) != 1:
            raise AdmissionError("Trial output does not identify one frozen full-game cell")
        expected = {**common, **{key: matches[0][key] for key in
                               ("model", "mode", "scope", "stop_after_sector")}}
    else:
        model, mode, challenge, repeat = (configuration.get(k) for k in
                                        ("model", "mode", "challenge", "repetition"))
        if (model not in protocol["models"] or mode not in protocol["modes"]
                or challenge not in protocol["challenges"] or type(repeat) is not int
                or not 1 <= repeat <= protocol["repetitions"]):
            raise AdmissionError("Trial configuration is outside the frozen challenge matrix")
        expected_output = (cohort / "trials" / model / mode / challenge / f"repeat-{repeat:02}"
                           / "repetition-01" / challenge)
        if expected_output.resolve() != Path(output).resolve():
            raise AdmissionError("Trial output differs from its frozen challenge cell")
        expected = {**common, "model": model, "mode": mode, "challenge": challenge,
                    "repetition": repeat, "setup_only": False}
    if configuration != expected:
        raise AdmissionError("Actual child configuration differs from the frozen cell")


def admit_trial(*, experiment_file, output, source_root, fingerprint, cli_identity,
                production_hash, deployed_hash, verify_protocol, configuration, experiment=None):
    """Fail before model calls and retain both acceptance and rejection evidence.

    Call only after protected deployment. The caller owns teardown on failure.
    The verifier checks the frozen source/evidence chain; this gate separately
    checks actual installed bytes and the production or regenerated fixture Lua.
    """
    receipt = {"contract": TRIAL_CONTRACT, "accepted": False}
    target = Path(output) / "controller-admission.json"
    # Never replace a previous decision, including an earlier rejection.
    with target.open("x", encoding="utf-8") as handle:
        try:
            path = Path(experiment_file)
            raw = path.read_bytes()
            receipt["protocol_sha256"] = digest(raw)
            protocol = read_json(raw)
            if not isinstance(protocol, dict) or protocol.get("contract") not in PORTABLE_CONTRACTS:
                raise AdmissionError("A portable trial requires an exact v2 experiment contract")
            if experiment is not None and protocol != experiment:
                raise AdmissionError("Child protocol differs from the archived experiment file")
            receipt["selector_spec_sha256"] = protocol["admission_selector"]["spec"]["sha256"]
            verify_protocol(protocol, directory=path.parent, verify_installed=False)
            receipt["configuration"] = configuration
            _require_configuration(protocol, configuration, output, path.parent)
            admission = protocol["admission_selector"]["admission"]
            actual = installed_runtime(source_root)
            receipt.update(admission=admission, installed_runtime=actual,
                           deployed_bridge_sha256=(fingerprint.get("bridge_lua") or {}).get("sha256"))
            require_installed(admission, actual)
            if fingerprint.get("native_build") != actual["native_build"]:
                raise AdmissionError("Native runtime changed between deployment and admission")
            if cli_identity != protocol.get("codex_cli"):
                raise AdmissionError("Actual Codex CLI differs from frozen protocol")
            if production_hash != admission["runtime"]["production_bridge_sha256"]:
                raise AdmissionError("Production bridge differs from admitted source")
            if receipt["deployed_bridge_sha256"] != deployed_hash:
                raise AdmissionError("Deployed bridge differs from expected trial Lua")
            receipt["accepted"] = True
        except Exception as error:
            receipt["error"] = str(error)
            json.dump(receipt, handle, indent=2, allow_nan=False)
            raise
        json.dump(receipt, handle, indent=2, allow_nan=False)
    return receipt


def audit_trial_admission(output, protocol, *, protocol_file):
    """Join a saved child gate to its protocol and runtime, without live access."""
    if protocol.get("contract") not in PORTABLE_CONTRACTS:
        return []
    try:
        output = Path(output)
        paths = [output / name for name in
                 ("controller-admission.json", "run.json", "runtime-fingerprint.json")]
        if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in paths):
            raise AdmissionError("Linked trial admission artifact")
        raw = paths[0].read_bytes()
        receipt, manifest, fingerprint = (read_json(p.read_bytes()) for p in paths)
        selector = protocol["admission_selector"]
        admitted = selector["admission"]
        if (admitted.get("contract") != "portable-visual-controller-admission-v1"
                or admitted.get("controller_admission") is not True
                or admitted.get("production_accepted") is not False):
            raise AdmissionError("Saved controller admission state is invalid")
        _require_configuration(protocol, receipt["configuration"], output, Path(protocol_file).parent)
        common = {"model": manifest.get("model"), "mode": manifest.get("observation_mode"),
                  "seed": manifest.get("seed"), "reasoning_effort": manifest.get("reasoning_effort"),
                  "budgets": manifest.get("budgets")}
        if any(receipt["configuration"].get(k) != value for k, value in common.items()):
            raise AdmissionError("Saved child configuration differs from its manifest")
        if (receipt.get("contract") != TRIAL_CONTRACT or receipt.get("accepted") is not True
                or receipt.get("error") or manifest.get("controller_admission_sha256") != digest(raw)
                or receipt.get("protocol_sha256") != digest(Path(protocol_file).read_bytes())
                or receipt.get("selector_spec_sha256") != selector["spec"]["sha256"]
                or receipt.get("admission") != selector["admission"]):
            raise AdmissionError("Saved child admission does not match its frozen protocol")
        actual = receipt["installed_runtime"]
        require_installed(selector["admission"], actual)
        if (fingerprint.get("native_build") != actual["native_build"]
                or receipt.get("deployed_bridge_sha256") != (fingerprint.get("bridge_lua") or {}).get("sha256")
                or not receipt.get("deployed_bridge_sha256")):
            raise AdmissionError("Saved child admission does not match its recorded runtime")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return ["Controller admission: " + str(error)]
    return []
