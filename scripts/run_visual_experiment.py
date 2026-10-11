"""Freeze and run the local visual challenge matrix, one protected game at a time.

The ledger preserves failed attempts. Resuming never repeats a started cell or
assumes that an observation timeout means the game process has stopped.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapter"))

from visual_cancellation import StopControl, request_stop, wait_for_protected_child

MODELS = ("gpt-6.1-sol", "gpt-6-luna")
MODES = ("image", "hybrid")
CHALLENGES = ("combat", "fire-crew-recovery", "repair-charge-escape")
CONTRACT = "ftl-visual-challenge-matrix-v1"
FRESH_CONTRACT = {"fresh_start_seed": True, "fresh_seed_contract_version": 3,
                  "fresh_seed_contract": "fresh-start-seed-v3"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def fresh_start_evidence(receipt, root=ROOT):
    """Read immutable acceptance origins; the staging document is only a byte map."""
    evidence = receipt.get("fresh_start_evidence") or {}
    if evidence.get("contract") != "fresh-start-v3-nine-probes-v1":
        raise RuntimeError("Fresh-start v3 needs explicit nine-probe acceptance evidence")
    pins = {}

    def load(reference):
        if not isinstance(reference, dict):
            raise RuntimeError("Fresh-start evidence reference is missing")
        relative, expected = reference.get("path"), reference.get("sha256")
        if (not isinstance(relative, str) or not relative
                or not isinstance(expected, str) or len(expected) != 64
                or any(character not in "0123456789abcdef" for character in expected)):
            raise RuntimeError("Fresh-start evidence reference is malformed")
        relative = Path(relative.replace("\\", "/"))
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise RuntimeError("Fresh-start evidence must remain inside the benchmark directory")
        path = root / relative
        if (not path.resolve().is_relative_to(root.resolve())
                or any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent)):
            raise RuntimeError("Fresh-start evidence path is unsafe")
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise RuntimeError("Fresh-start evidence hash mismatch: " + relative.as_posix())
            document = json.loads(raw)
        except (OSError, ValueError) as error:
            raise RuntimeError("Fresh-start evidence is unreadable: " + relative.as_posix()) from error
        if not isinstance(document, dict):
            raise RuntimeError("Fresh-start evidence must be a JSON object")
        pins[relative.as_posix()] = expected
        return document

    acceptance = load(evidence.get("acceptance"))
    return {"acceptance": acceptance, "integration": load(evidence.get("integration")),
            "verification": load(acceptance.get("evidence")),
            "review": load(acceptance.get("independent_review")),
            "build": load(acceptance.get("build_manifest"))}, pins


def source_identity(root=ROOT):
    """Freeze executable experiment sources, including pixel-reader assets."""
    paths = set()
    for directory in ("adapter", "harness/src/ftl_bench", "prompts", "native", "mod"):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (path.is_file() and not any(p in {"__pycache__", "_bundled", "build", "dist"} for p in relative.parts)
                    and path.suffix in {".py", ".json", ".md", ".lua", ".patch", ".h", ".inc", ".png"}):
                paths.add(path)
    paths.update((root / "scripts").glob("*visual*.py"))
    paths.update(root / name for name in ("dist/Hyperspace.visual-v1.dll", "dist/native-build.visual-v1.json",
                                        "dist/native-validation.visual-v1.json", "dist/native-validation.visual-v1.live.md"))
    receipt = root / "dist/native-validation.visual-v1.json"
    if receipt.is_file() and read_json(receipt).get("fresh_start_evidence"):
        _, evidence = fresh_start_evidence(read_json(receipt), root)
        paths.update(root / relative for relative in evidence)
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def plan_cells():
    # All Sol conditions precede Luna; ordering is declared, not randomized.
    return [{"id": f"{model}/{mode}/{challenge}/repeat-{repeat:02d}",
             "model": model, "mode": mode, "challenge": challenge, "repetition": repeat,
             "status": "planned"}
            for model in MODELS for mode in MODES for challenge in CHALLENGES
            for repeat in range(1, 4)]


def accepted_native_runtime(source, root=ROOT):
    receipt = read_json(root / "dist/native-validation.visual-v1.json")
    artifacts = receipt.get("artifacts") or {}
    expected = {"dll_sha256": source["dist/Hyperspace.visual-v1.dll"],
                "patch_sha256": source["native/patches/0003-visual-io.patch"],
                "lua_sha256": source["mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"],
                "dll_build_provenance_sha256": source["dist/native-build.visual-v1.json"],
                "manifest_sha256": source["native/manifest.json"]}
    if (any(artifacts.get(key) != value for key, value in expected.items())
            or (receipt.get("live_acceptance") or {}).get("claimed") is not True):
        raise RuntimeError("Current native artifacts do not have matching recorded live acceptance")
    timing = {"visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60}
    acceptance = receipt.get("live_acceptance") or {}
    cases = acceptance.get("fixed_step_case_ids")
    if (any(type(artifacts.get(key)) is not int or artifacts[key] != value
            for key, value in timing.items())
            or acceptance.get("fixed_step_verified") is not True
            or not isinstance(cases, list) or not cases
            or any(not isinstance(case, str) or not case for case in cases)):
        raise RuntimeError("Fixed-step clock v2 needs recorded live repeatability acceptance")
    documents, evidence_pins = fresh_start_evidence(receipt, root)
    manifest = read_json(root / "native/manifest.json")
    provenance = read_json(root / "dist/native-build.visual-v1.json")
    accepted, verification, review, build, integration = (
        documents[name] for name in ("acceptance", "verification", "review", "build", "integration"))

    def require(condition, message):
        if not condition:
            raise RuntimeError("Fresh-start v3 acceptance: " + message)

    for name, payload in (("artifacts", artifacts), ("manifest", manifest),
                          ("provenance", provenance), ("tested build", build)):
        require(all(type(payload.get(key)) is type(value) and payload[key] == value
                    for key, value in {**timing, **FRESH_CONTRACT}.items()),
                name + " lacks the exact fresh-start/clock contract")
    require(all(source.get(path) == value for path, value in evidence_pins.items()),
            "evidence was not frozen with the experiment sources")
    require(accepted.get("status") == "accepted_for_production_integration"
            and accepted.get("acceptance_kind") == "fresh-start-v3-nine-challenge-probes"
            and accepted.get("fresh_seed_contract") == FRESH_CONTRACT["fresh_seed_contract"]
            and type(accepted.get("fixture_version")) is int and accepted["fixture_version"] == 6
            and type(accepted.get("trial_count")) is int and accepted["trial_count"] == 9
            and type(accepted.get("model_calls")) is int and accepted["model_calls"] == 0
            and accepted.get("full_game_determinism_claimed") is False
            and accepted.get("model_evaluation_performed") is False,
            "unsupported acceptance kind or scope")
    require(verification.get("passed") is True and verification.get("checks")
            and all(value is True for value in verification["checks"].values())
            and verification.get("full_game_determinism_claimed") is False
            and verification.get("internal_rng_stream_equality_measured") is False
            and type(verification.get("model_calls")) is int and verification["model_calls"] == 0,
            "nine-probe verification is incomplete or overstates its scope")
    collections = verification.get("collections") or []
    require(len(collections) == 3 and {row.get("challenge") for row in collections} == set(CHALLENGES)
            and all(len(row.get("trials", [])) == 3 and all(
                trial.get("rederived_checks") and all(value is True for value in trial["rederived_checks"].values())
                for trial in row["trials"]) for row in collections), "nine verified trials are required")
    require(review.get("verification_receipt_sha256") == accepted["evidence"]["sha256"]
            and review.get("verifier_sha256") == verification.get("verifier_sha256")
            and review.get("actual_nine_trials_passed") is True
            and review.get("all_mutations_rejected") is True
            and len(review.get("mutations") or []) >= 8
            and all(row.get("rejected") is True for row in review["mutations"]),
            "independent review does not bind the accepted verification")
    require(all(payload.get("dll_sha256") == expected["dll_sha256"]
                for payload in (accepted, verification, build, provenance))
            and integration.get("candidate_dll_sha256") == expected["dll_sha256"],
            "tested DLL differs from the promoted DLL")
    require(verification.get("build_manifest_sha256") == accepted["build_manifest"]["sha256"]
            == review.get("build_manifest_sha256"), "tested build origin differs")
    require(provenance.get("built_at") == build.get("built_at") and bool(build.get("built_at"))
            and provenance.get("source_commit") == build.get("base_commit") == manifest.get("base_commit"),
            "original build time or source commit differs")
    staged = {path.replace("\\", "/"): value for path, value in (integration.get("staged_sha256") or {}).items()}
    native_sources = {path.removeprefix("native-source/"): value for path, value in staged.items()
                      if path.startswith("native-source/")}
    require(integration.get("contract") == "native-production-integration-plan-v1"
            and integration.get("complete_patch_reconstructed_exact_base") is True
            and integration.get("reconstructed_source_hashes_match_tested_build") is True
            and len(native_sources) == 12 and sorted(native_sources) == sorted(integration.get("complete_patch_paths") or [])
            and provenance.get("source_files_sha256") == native_sources
            and bool(build.get("candidate_source_sha256"))
            and all(native_sources.get(path) == value for path, value in build["candidate_source_sha256"].items()),
            "promoted source files differ from the tested integration byte map")
    require(integration.get("staged_complete_patch_sha256") == expected["patch_sha256"]
            == manifest.get("patch_sha256") == provenance.get("patch_sha256")
            and staged.get("repo/native/manifest.json") == expected["manifest_sha256"]
            and staged.get("repo/mod/ftl_bench_bridge/dev/ftl_bench_dev.lua") == expected["lua_sha256"],
            "promoted patch, manifest or bridge differs from the tested integration")
    return {"dll_sha256": expected["dll_sha256"], "patch_sha256": expected["patch_sha256"],
            "production_bridge_sha256": expected["lua_sha256"], **timing, **FRESH_CONTRACT}


def freeze(directory: Path):
    from run_visual import codex_runtime_identity
    from visual_agent import CONTRACT as action_contract, MAX_ACTIONS, MAX_ADVANCE_FRAMES, MAX_HISTORY, MAX_MEMORY_CHARS
    directory.mkdir(parents=True, exist_ok=False)
    source = source_identity()
    accepted = accepted_native_runtime(source)
    _, acceptance_origins = fresh_start_evidence(read_json(ROOT / "dist/native-validation.visual-v1.json"))
    from validate_visual_challenges import TASK_VERSIONS, task_identity
    protocol = {"task_versions": dict(TASK_VERSIONS),
                "tasks": {challenge: task_identity(challenge) for challenge in CHALLENGES},
                "contract": CONTRACT, "created_at": stamp(), "models": list(MODELS),
                "modes": list(MODES), "challenges": list(CHALLENGES), "repetitions": 3,
                "seed": 1, "ship": "PLAYER_SHIP_HARD", "difficulty": 0,
                "reasoning_effort": "medium", "budgets": {"decisions": 60, "wall_seconds": 1800,
                    "idle_decisions": 8}, "action_contract": action_contract,
                "max_actions": MAX_ACTIONS, "max_advance_frames": MAX_ADVANCE_FRAMES,
                "time_contract": {"visual_clock_version": 2, "fixed_step_numerator": 1,
                                  "fixed_step_denominator": 60},
                "history_length": MAX_HISTORY, "memory_chars": MAX_MEMORY_CHARS,
                "execution_order": "model, mode, challenge, repetition; Sol before Luna",
                "source_files": source, "source_sha256": digest(source),
                "codex_cli": codex_runtime_identity(),
                "hud_extractor_identity": {p: h for p, h in source.items() if "visible_hud" in p},
                "native_acceptance": {
                    "receipts": {p: h for p, h in source.items()
                                 if "native-validation.visual-v1" in p or p in acceptance_origins},
                    "runtime": accepted},
                "scope": "Repeated diagnostic challenges; not full-game scores or a population ranking."}
    protocol["protocol_sha256"] = digest(protocol)
    write_json(directory / "protocol.json", protocol)
    write_json(directory / "ledger.json", {"protocol_sha256": protocol["protocol_sha256"], "cells": plan_cells()})
    return protocol


def verify_protocol(protocol, root=ROOT):
    original = dict(protocol)
    recorded = original.pop("protocol_sha256", None)
    if recorded != digest(original):
        raise RuntimeError("Experiment protocol changed; preserve it and freeze a new experiment")
    current = source_identity(root)
    if current != protocol["source_files"]:
        changed = sorted(k for k in current.keys() | protocol["source_files"].keys()
                         if current.get(k) != protocol["source_files"].get(k))
        raise RuntimeError("Frozen experiment source changed: " + ", ".join(changed))
    from validate_visual_challenges import TASK_VERSIONS, task_identity
    if (protocol.get("task_versions") != TASK_VERSIONS
            or protocol.get("tasks") != {challenge: task_identity(challenge) for challenge in CHALLENGES}):
        raise RuntimeError("Frozen task identity changed; freeze a new experiment")
    from run_visual import codex_runtime_identity
    if codex_runtime_identity() != protocol["codex_cli"]:
        raise RuntimeError("Codex CLI changed after the experiment was frozen")


def trial_command(directory, cell, protocol):
    return [sys.executable, "-u", str(ROOT / "scripts/validate_visual_challenges.py"),
            "--challenge", cell["challenge"], "--model", cell["model"], "--mode", cell["mode"],
            "--seed", str(protocol["seed"]), "--reasoning-effort", protocol["reasoning_effort"],
            "--repeats", "1", "--repeat-index", str(cell["repetition"]),
            "--max-decisions", str(protocol["budgets"]["decisions"]),
            "--max-wall-seconds", str(protocol["budgets"]["wall_seconds"]),
            "--max-idle-decisions", str(protocol["budgets"]["idle_decisions"]),
            "--experiment-file", str(directory / "protocol.json"),
            "--output", str(directory / "trials" / cell["id"])]


def validate_ledger(ledger, protocol):
    if ledger.get("protocol_sha256") != protocol["protocol_sha256"]:
        raise RuntimeError("Ledger belongs to a different protocol")
    cells, expected = ledger.get("cells"), plan_cells()
    if not isinstance(cells, list) or len(cells) != len(expected):
        raise RuntimeError("Ledger no longer contains the complete declared matrix")
    for cell, original in zip(cells, expected):
        if (not isinstance(cell, dict)
                or any(cell.get(key) != original[key] for key in original if key != "status")
                or cell.get("status") not in {"planned", "running", "finished", "interrupted_unknown"}):
            raise RuntimeError("Ledger cells changed identity or order")


def process_identity(pid):
    """Read the live Windows handle and creation time; a PID alone is not identity."""
    if os.name != "nt":
        raise RuntimeError("Protected matrix execution currently requires Windows")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: PID no longer exists
            return None
        raise OSError(error, "Cannot determine whether recorded benchmark process is alive")
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if code.value != 259:  # STILL_ACTIVE
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"pid": int(pid), "creation_filetime": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime}
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def controller_lock(directory):
    import msvcrt
    path = directory / "controller.lock"
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("Another experiment controller is still running") from error
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def saved_trial(directory, cell):
    return directory / "trials" / cell["id"] / "repetition-01" / cell["challenge"]


def reconcile(directory, cell):
    if cell["status"] != "running":
        return
    identity = cell.get("process")
    if not identity:
        raise RuntimeError("Started cell has no verified process identity; inspect it before resuming")
    if process_identity(identity["pid"]) == identity:
        raise RuntimeError(f"Trial {cell['id']} is still running; resumption will not duplicate it")
    path = saved_trial(directory, cell) / "run.json"
    run = read_json(path) if path.is_file() else {}
    cell.update(status="finished" if run.get("status") in {"completed", "error", "interrupted"}
                else "interrupted_unknown", recovered_at=stamp(),
                result_status=run.get("status"), result_reason=run.get("reason"))


def require_restoration(directory, cell):
    """A prior failed cleanup stays blocking across controller restarts."""
    receipt = saved_trial(directory, cell) / "save-backup/restoration.json"
    manifest = receipt.with_name("manifest.json")
    try:
        run = read_json(saved_trial(directory, cell) / "run.json")
        restoration, originals = read_json(receipt), read_json(manifest)
        files = originals.get("files")
        if (run.get("save_restoration") != "verified" or run.get("production_source_unchanged") is not True
                or run.get("status") not in {"completed", "error", "interrupted"}
                or restoration.get("verified") is not True or not isinstance(files, dict) or not files
                or restoration.get("files") != {name: True for name in files}):
            raise ValueError("incomplete restoration receipt")
    except (OSError, ValueError, TypeError) as error:
        raise RuntimeError(f"Save restoration is not verified for {cell['id']}; inspect before continuing") from error


def refresh_summary(directory, ledger):
    from visual_reporting import aggregate_visual_runs
    protocol = read_json(directory / "protocol.json")
    validate_ledger(ledger, protocol)
    paths = [saved_trial(directory, cell) for cell in ledger["cells"]
             if (saved_trial(directory, cell) / "trajectory.jsonl").is_file()]
    report = aggregate_visual_runs(paths, protocol=protocol)
    write_json(directory / "comparison.json", report)


def run(directory, limit):
    control = StopControl(directory / "stop-request.json", str(directory.resolve()))
    protocol = read_json(directory / "protocol.json")
    verify_protocol(protocol)
    with controller_lock(directory):
        ledger = read_json(directory / "ledger.json")
        validate_ledger(ledger, protocol)
        for cell in ledger["cells"]:
            reconcile(directory, cell)
            if cell["status"] in {"finished", "interrupted_unknown"}:
                require_restoration(directory, cell)
        write_json(directory / "ledger.json", ledger)
        done = 0
        for cell in ledger["cells"]:
            if control.pending():
                ledger["stop_requested"] = True
                write_json(directory / "ledger.json", ledger)
                break
            if cell["status"] != "planned" or done >= limit:
                continue
            verify_protocol(protocol)
            if control.pending():
                ledger["stop_requested"] = True
                write_json(directory / "ledger.json", ledger)
                break
            if (directory / "trials" / cell["id"]).exists():
                raise RuntimeError("Planned output already exists; inspect it rather than overwriting an attempt")
            logs = directory / "logs"
            logs.mkdir(exist_ok=True)
            log = logs / (cell["id"].replace("/", "__") + ".log")
            command = trial_command(directory, cell, protocol)
            command += ["--stop-file", str(control.path), "--stop-scope", control.scope]
            if control.pending():
                break
            cell.update(status="running", started_at=stamp(), command=command, log=str(log.relative_to(directory)))
            # Write intent before launching; an ambiguous controller crash fails closed.
            write_json(directory / "ledger.json", ledger)
            print(json.dumps({"starting": cell["id"], "log": str(log)}), flush=True)
            with log.open("xb") as output:
                child = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                cell["process"] = process_identity(child.pid)
                write_json(directory / "ledger.json", ledger)
                code = wait_for_protected_child(child, control)
            cell.update(status="finished", finished_at=stamp(), exit_code=code)
            path = saved_trial(directory, cell) / "run.json"
            result = read_json(path) if path.is_file() else {}
            cell.update(result_status=result.get("status"), result_reason=result.get("reason"))
            write_json(directory / "ledger.json", ledger)
            refresh_summary(directory, ledger)
            print(json.dumps({"finished": cell["id"], "exit_code": code, "reason": result.get("reason")}), flush=True)
            done += 1
            # A cleanup failure is not permission to start another game.
            require_restoration(directory, cell)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "run", "report", "stop"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=1, help="Maximum new cells to run this invocation (default: 1)")
    parser.add_argument("--initiator", default="operator", help="Identity of stop requester")
    parser.add_argument("--reason", default="operator_requested")
    args = parser.parse_args(argv)
    directory = args.output.resolve()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.operation == "stop":
        request_stop(directory / "stop-request.json", str(directory), args.initiator, args.reason)
    elif args.operation == "freeze":
        freeze(directory)
    elif args.operation == "run":
        run(directory, args.limit)
    else:
        refresh_summary(directory, read_json(directory / "ledger.json"))
    print(directory)


if __name__ == "__main__":
    main()
