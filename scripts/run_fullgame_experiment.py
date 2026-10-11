"""Frozen sector pilot and four descriptive full-game conditions, run sequentially.

Uses the mandatory fresh-start-v3 visual CLI. Existing run artifacts are never
overwritten or retried. Only native victory/defeat completes a full game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "adapter"))
from visual_cancellation import StopControl, request_stop, wait_for_protected_child

import run_visual_experiment as shared
from run_visual import codex_runtime_identity
from visual_agent import CodexVisualAgent, decision_schema
from visual_reporting import audit_visual_run
from ftl_bench.fullgame_setup import packet_proof, receipt_proof
from ftl_bench.installation import runtime_fingerprint
from ftl_bench.protected_game import _processes as game_processes
from ftl_bench import experiment_admission as portable
from ftl_bench.visual_admission import audit_trial_admission

CONTRACT = "ftl-fullgame-experiment-v1"
BUDGETS = {"decisions": 300, "wall_seconds": 14400, "idle_decisions": 8}
RUNTIME_FILES = ("FTLGame.exe", "ftl.dat", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll")
read, write, digest, stamp = shared.read_json, shared.write_json, shared.digest, shared.stamp


def plan_cells():
    return [{"id": "pilot/gpt-6.1-sol/image/sector-1", "model": "gpt-6.1-sol", "mode": "image",
             "scope": "sector_pilot", "stop_after_sector": 1, "status": "planned"}] + [
        {"id": f"fullgame/{model}/{mode}", "model": model, "mode": mode,
         "scope": "full_game", "stop_after_sector": None, "status": "planned"}
        for model in shared.MODELS for mode in shared.MODES]


def source_identity(root=ROOT):
    sources = shared.source_identity(root)
    _, baseline = accepted_runtime_baseline(root)
    sources[baseline["path"]] = baseline["sha256"]
    path = root / "scripts/run_fullgame_experiment.py"
    sources[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return sources


def accepted_runtime_baseline(root=ROOT):
    receipt = read(root / "dist/native-validation.visual-v1.json")
    reference = receipt.get("baseline")
    if receipt.get("contract") != "fresh-start-v3-production-acceptance-v1" or not isinstance(reference, dict):
        raise RuntimeError("Accepted runtime baseline is missing")
    name, expected = reference.get("path"), reference.get("sha256")
    if (not isinstance(name, str) or not name or not isinstance(expected, str)
            or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected)):
        raise RuntimeError("Accepted runtime baseline reference is malformed")
    relative = Path(name.replace("\\", "/"))
    path = root / relative
    if (relative.is_absolute() or relative.drive or ".." in relative.parts
            or not path.resolve().is_relative_to(root.resolve())
            or any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                   for p in (path, *path.parents) if p != root.parent)):
        raise RuntimeError("Accepted runtime baseline path is unsafe")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("Accepted runtime baseline hash changed")
    baseline = json.loads(raw)
    if not isinstance(baseline, dict):
        raise RuntimeError("Accepted runtime baseline must be a file hash map")
    files = {}
    for filename in RUNTIME_FILES:
        matches = [value for key, value in baseline.items() if PureWindowsPath(key).name == filename]
        if (len(matches) != 1 or not isinstance(matches[0], str) or len(matches[0]) != 64
                or any(c not in "0123456789abcdef" for c in matches[0])):
            raise RuntimeError("Accepted runtime baseline is missing or ambiguous: " + filename)
        files[filename] = matches[0]
    return files, {"path": relative.as_posix(), "sha256": expected}


def require_tested_runtime(installed, root=ROOT):
    files, reference = accepted_runtime_baseline(root)
    if installed.get("files_sha256") != files:
        raise RuntimeError("Installed game/data/loader/runtime bytes differ from the accepted tested baseline")
    return {"files_sha256": files, "baseline": reference}


def installed_identity(root=ROOT):
    """Pin installed content; deployed Lua is replaced by the protected runner."""
    fingerprint = runtime_fingerprint(root)
    build = fingerprint.get("native_build") or {}
    if build.get("matches_installed_dll") is not True:
        raise RuntimeError("Installed native DLL does not match provenance")
    if any(type(build.get(k)) is not type(v) or build[k] != v for k, v in shared.FRESH_CONTRACT.items()):
        raise RuntimeError("Installed runtime does not provide fresh-start v3")
    game = Path(fingerprint["native_dll"]["path"]).parent
    files = {name: hashlib.sha256((game / name).read_bytes()).hexdigest()
             for name in RUNTIME_FILES}
    return {"files_sha256": files, "native_build": build,
            "deployed_bridge_sha256": (fingerprint.get("bridge_lua") or {}).get("sha256")}


def archive_sources(directory, sources):
    for name, expected in sources.items():
        data = (ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("Source changed while freezing: " + name)
        target = directory / "frozen-source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(data)


def freeze(directory, *, native_evidence=None, evidence_root=None):
    if (native_evidence is None) != (evidence_root is None):
        raise ValueError("--native-evidence and --evidence-root must be provided together")
    if directory.exists():
        raise RuntimeError("Experiment output already exists")
    selector = None
    if native_evidence is not None:
        directory.mkdir(parents=True, exist_ok=False)
        selector = portable.freeze_admission(directory, native_evidence, source_root=ROOT, evidence_root=evidence_root)
        sources = selector["source_files"]
        accepted = selector["admission"]["runtime"]
        installed = portable.installed_runtime(ROOT)
        portable.require_installed(selector["admission"], installed)
        tested = {"files_sha256": installed["files_sha256"]}
    else:
        sources = source_identity()
        accepted = shared.accepted_native_runtime(sources, ROOT)
        installed = installed_identity()
        tested = require_tested_runtime(installed)
    if installed["files_sha256"]["Hyperspace.dll"] != accepted["dll_sha256"]:
        raise RuntimeError("Installed DLL differs from accepted native runtime")
    actor = CodexVisualAgent(model="gpt-6.1-sol").instruction_identity()
    protocol = {"contract": portable.FULLGAME_CONTRACT if selector else CONTRACT, "created_at": stamp(), "seed": 1,
        "reasoning_effort": "medium", "budgets": dict(BUDGETS), "cells": plan_cells(),
        "source_files": sources, "source_sha256": digest(sources), "codex_cli": codex_runtime_identity(),
        "installed_runtime": installed, "tested_runtime": tested,
        "native_acceptance": accepted, "actor_identity": actor,
        "schema_sha256": digest(decision_schema(1280, 720)),
        "scope": "One sector pilot followed by four matched single-seed full-game attempts; descriptive results, not a population ranking.",
        "pilot_admission": "Finished audited attempt with verified cleanup; sector success is reported separately.",
        "fullgame_completion": "Native victory or native defeat only; budget and interrupted attempts remain incomplete."}
    if selector:
        protocol["admission_selector"] = selector
    protocol["protocol_sha256"] = digest(protocol)
    if selector is None:
        directory.mkdir(parents=True, exist_ok=False)
        archive_sources(directory, sources)
    write(directory / "protocol.json", protocol)
    write(directory / "ledger.json", {"protocol_sha256": protocol["protocol_sha256"], "cells": plan_cells()})
    return protocol


def verify_protocol(protocol, *, directory=None, verify_installed=True):
    unsigned = dict(protocol)
    expected = unsigned.pop("protocol_sha256", None)
    if expected != digest(unsigned) or protocol.get("contract") not in (CONTRACT, portable.FULLGAME_CONTRACT):
        raise RuntimeError("Full-game protocol changed")
    if (protocol.get("seed") != 1 or protocol.get("budgets") != BUDGETS
            or protocol.get("reasoning_effort") != "medium" or protocol.get("cells") != plan_cells()):
        raise RuntimeError("Declared full-game conditions changed")
    if protocol["contract"] == portable.FULLGAME_CONTRACT:
        if directory is None:
            raise RuntimeError("Portable experiment verification requires its cohort directory")
        admission = portable.verify_admission(directory, protocol.get("admission_selector"), source_root=ROOT)
        sources = admission["source_files"]
        if (sources != protocol["source_files"] or digest(sources) != protocol.get("source_sha256")
                or admission["runtime"] != protocol["native_acceptance"]
                or protocol.get("tested_runtime") != {"files_sha256": admission["runtime_files"]}):
            raise RuntimeError("Portable full-game admission changed")
        if verify_installed:
            installed = portable.installed_runtime(ROOT)
            portable.require_installed(admission, installed)
            if installed != protocol["installed_runtime"]:
                raise RuntimeError("Installed runtime changed")
        if codex_runtime_identity() != protocol["codex_cli"]:
            raise RuntimeError("Authenticated Codex CLI identity changed")
        return
    sources = source_identity()
    if sources != protocol["source_files"] or digest(sources) != protocol.get("source_sha256"):
        raise RuntimeError("Frozen full-game source or acceptance evidence changed")
    if shared.accepted_native_runtime(sources, ROOT) != protocol["native_acceptance"]:
        raise RuntimeError("Native acceptance changed")
    installed = installed_identity()
    if require_tested_runtime(installed) != protocol.get("tested_runtime"):
        raise RuntimeError("Accepted runtime baseline changed")
    if installed != protocol["installed_runtime"] or codex_runtime_identity() != protocol["codex_cli"]:
        raise RuntimeError("Installed runtime or authenticated Codex CLI identity changed")


def validate_ledger(ledger, protocol):
    cells = ledger.get("cells")
    if ledger.get("protocol_sha256") != protocol["protocol_sha256"] or not isinstance(cells, list) or len(cells) != 5:
        raise RuntimeError("Full-game ledger is incomplete or belongs to another protocol")
    for cell, original in zip(cells, plan_cells()):
        if (any(cell.get(k) != v for k, v in original.items() if k != "status")
                or cell.get("status") not in ("planned", "running", "finished", "interrupted_unknown")):
            raise RuntimeError("Full-game cells changed identity, order or status")


def trial_directory(directory, cell):
    return directory / "trials" / cell["id"]


def trial_command(directory, cell, protocol):
    command = [sys.executable, "-u", str(ROOT / "adapter/run_visual.py"),
        "--model", cell["model"], "--mode", cell["mode"], "--seed", str(protocol["seed"]),
        "--reasoning-effort", protocol["reasoning_effort"], "--max-decisions", str(protocol["budgets"]["decisions"]),
        "--max-wall-seconds", str(protocol["budgets"]["wall_seconds"]),
        "--max-idle-decisions", str(protocol["budgets"]["idle_decisions"]),
        "--output", str(trial_directory(directory, cell))]
    if cell["stop_after_sector"] is not None:
        command += ["--stop-after-sector", str(cell["stop_after_sector"])]
    if protocol.get("contract") == portable.FULLGAME_CONTRACT:
        command += ["--experiment-file", str(directory / "protocol.json")]
    return command


def classify_outcome(cell, terminal, last_observation):
    """Completion is native telemetry, never inferred from score or budget."""
    reason = terminal.get("reason")
    native = None
    if terminal.get("status") == "completed":
        if reason == "native_victory" and last_observation.get("victory") is True:
            native = "victory"
        elif reason == "native_game_over" and last_observation.get("game_over") is True and last_observation.get("victory") is not True:
            native = "defeat"
    if cell["scope"] == "sector_pilot":
        sector = (last_observation.get("map") or {}).get("sector")
        reached = terminal.get("status") == "completed" and reason == "sector_target_observed" and type(sector) is int and sector >= 1
        return {"fullgame_complete": False, "native_outcome": native,
                "category": "pilot_sector_reached" if reached else "pilot_" + (native or "incomplete")}
    return {"fullgame_complete": native is not None, "native_outcome": native,
            "category": native or "incomplete"}


def audit_trial(directory, cell, protocol, *, verify_live_saves=False):
    path = trial_directory(directory, cell)
    audit = audit_visual_run(path, require_terminal=True, verify_live_saves=verify_live_saves)
    issues = list(audit.get("issues") or [])
    issues.extend(audit_trial_admission(path, protocol, protocol_file=directory / "protocol.json"))
    manifest, report, terminal, last = {}, {}, {}, {}
    def check(condition, message):
        if not condition:
            issues.append(message)
    try:
        manifest, report = read(path / "run.json"), read(path / "visual-report.json")
        rows = [json.loads(line) for line in (path / "trajectory.jsonl").read_text().splitlines()]
        terminal = next(row for row in reversed(rows) if row.get("kind") == "end")
        last = next(row["obs"] for row in reversed(rows) if isinstance(row.get("obs"), dict))
        first = next(row for row in rows if row.get("kind") == "reset")
        metadata = next(row["meta"] for row in rows if row.get("kind") == "meta")
        fingerprint = read(path / "runtime-fingerprint.json")
        setup = read(path / "fresh-setup/setup-session.json")
        admission = read(path / "fresh-setup/admission.json")
        check(manifest.get("model") == cell["model"] and manifest.get("observation_mode") == cell["mode"], "requested condition differs")
        check(manifest.get("seed") == protocol["seed"] and manifest.get("budgets") == protocol["budgets"]
              and manifest.get("reasoning_effort") == protocol["reasoning_effort"], "seed/budget/reasoning differs")
        check(metadata.get("seed") == protocol["seed"] and metadata.get("budgets") == protocol["budgets"]
              and metadata.get("reasoning_effort") == protocol["reasoning_effort"], "recorded actor metadata differs")
        check(terminal.get("budgets") == protocol["budgets"] and report.get("budgets") == protocol["budgets"],
              "effective terminal/report budgets differ")
        calls = [row["model"] for row in rows if isinstance(row.get("model"), dict) and row["model"]]
        check(all(call.get("reasoning_effort") == protocol["reasoning_effort"]
                  and call.get("requested_model", call.get("model")) == cell["model"]
                  and call.get("model") == cell["model"] for call in calls), "actual requested model/reasoning differs")
        check(manifest.get("stop_after_sector") == cell["stop_after_sector"]
              and manifest.get("trial_scope") == ("sector_progress" if cell["scope"] == "sector_pilot" else "full_game"), "scope differs")
        check(manifest.get("actor_identity") == protocol["actor_identity"], "actor instructions differ")
        check(fingerprint.get("codex_cli") == protocol["codex_cli"] == manifest.get("codex_cli"), "Codex CLI differs")
        check(fingerprint.get("native_build") == protocol["installed_runtime"]["native_build"], "native provenance differs")
        check((fingerprint.get("native_dll") or {}).get("sha256") == protocol["native_acceptance"]["dll_sha256"]
              and (fingerprint.get("bridge_lua") or {}).get("sha256") == protocol["native_acceptance"]["production_bridge_sha256"], "DLL or bridge differs")
        check(admission.get("passed") is True and setup.get("admitted") is True
              and admission.get("first_observation") == first["obs"]
              and admission.get("first_image") == first["visual"]["before"], "fresh admission does not join first screenshot")
        check(receipt_proof(first["obs"], protocol["seed"])["passed"]
              and packet_proof(first["obs"], setup["packets"], protocol["seed"])["passed"], "fresh native/packet proof failed")
        if audit["model_calls"]["calls"]:
            identity = protocol["actor_identity"]
            check(audit.get("manual_sha256") == [identity["manual_sha256"]]
                  and audit.get("instruction_sha256") == [identity["instructions_sha256"]]
                  and audit.get("schema_sha256") == [protocol["schema_sha256"]]
                  and audit.get("tasks") == [identity["task"]], "actual actor input boundary differs")
        # The audit verifies every original in this run's backup inventory.
        # Save counts vary by installation, including an initially empty profile.
        check(audit.get("terminal_cleanup", {}).get("complete") is True,
              "original save inventory was not verified")
    except (OSError, ValueError, KeyError, StopIteration, TypeError) as error:
        issues.append("missing_or_invalid_trial_evidence: " + str(error))
    outcome = classify_outcome(cell, terminal, last)
    integrity = audit.get("complete") is True and not issues
    return {"id": cell["id"], "scope": cell["scope"], "requested_model": cell["model"], "mode": cell["mode"],
        "directory": str(path), "status": manifest.get("status"), "reason": manifest.get("reason"),
        "integrity_passed": integrity, "issues": issues, "audit": audit,
        **outcome, "verified_fullgame_complete": integrity and outcome["fullgame_complete"],
        "metrics": report.get("metrics"), "metric_unavailable_reasons": report.get("metric_unavailable_reasons"),
        "elapsed_seconds": report.get("elapsed_seconds"), "model_calls": audit.get("model_calls")}


def refresh_summary(directory, ledger, protocol):
    validate_ledger(ledger, protocol)
    trials = [audit_trial(directory, cell, protocol) for cell in ledger["cells"]
              if cell["status"] in ("finished", "interrupted_unknown")]
    full = [row for row in trials if row["scope"] == "full_game"]
    result = {"contract": protocol["contract"], "protocol_sha256": protocol["protocol_sha256"], "updated_at": stamp(),
        "scope": protocol["scope"], "ranking_claimed": False, "pilot_excluded_from_fullgame_totals": True,
        "counts": {"planned": sum(c["status"] == "planned" for c in ledger["cells"]),
            "running": sum(c["status"] == "running" for c in ledger["cells"]), "finished_attempts": len(trials),
            "fullgame_attempts": len(full), "verified_fullgame_completions": sum(r["verified_fullgame_complete"] for r in full),
            "victories": sum(r["verified_fullgame_complete"] and r["native_outcome"] == "victory" for r in full),
            "defeats": sum(r["verified_fullgame_complete"] and r["native_outcome"] == "defeat" for r in full),
            "incomplete_fullgames": sum(not r["verified_fullgame_complete"] for r in full)}, "trials": trials,
        "limitations": ["One declared seed per condition does not establish a model ranking or general full-game determinism.",
            "Requested CLI model identity and reported response identity are shown separately in each audit.",
            "Budgets, interruptions and failed audits preserve attempts and never count as completed full games."]}
    write(directory / "comparison.json", result)
    return result


def reconcile(directory, cell):
    if cell["status"] != "running":
        return
    identity = cell.get("process")
    if not identity:
        raise RuntimeError("Started cell lacks verified process identity; inspect before resuming")
    if shared.process_identity(identity["pid"]) == identity:
        raise RuntimeError("Recorded full-game child is still running")
    path = trial_directory(directory, cell) / "run.json"
    result = read(path) if path.exists() else {}
    cell.update(status="finished" if result.get("status") in ("completed", "error", "interrupted") else "interrupted_unknown",
                recovered_at=stamp(), result_status=result.get("status"), result_reason=result.get("reason"))


def require_audited_cleanup(directory, cell, protocol):
    result = audit_trial(directory, cell, protocol, verify_live_saves=True)
    if not result["integrity_passed"]:
        raise RuntimeError("Prior trial failed integrity/cleanup audit; preserve it and inspect before continuing: " + cell["id"])
    allowed = {"decision_budget", "wall_clock_budget", "idle_decision_budget", "native_victory", "native_game_over"}
    if cell["scope"] == "sector_pilot":
        allowed.add("sector_target_observed")
    recovered = ("exit_code" not in cell and cell.get("recovered_at")
                 and cell.get("result_status") == "completed" and cell.get("result_reason") == result["reason"])
    if (cell["status"] != "finished" or result["status"] != "completed" or result["reason"] not in allowed
            or (cell.get("exit_code") != 0 and not recovered)):
        raise RuntimeError("Prior trial has a technical, interrupted or unknown child outcome; inspect before continuing")
    if result["reason"] in ("native_victory", "native_game_over") and result["native_outcome"] is None:
        raise RuntimeError("Native terminal outcome is not supported by final telemetry")
    processes = game_processes()
    if processes:
        raise RuntimeError("FTL process remains live; next trial is blocked")
    trial = trial_directory(directory, cell)
    backup = read(trial / "save-backup/manifest.json")
    live_paths = list(Path(backup["save_directory"]).glob("*.sav"))
    observed = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in live_paths}
    if observed != backup["files"]:
        raise RuntimeError("Live save inventory differs from the protected baseline")
    checked_at = stamp()
    receipt = {"contract": "fullgame-live-cleanup-check-v1", "checked_at": checked_at,
        "protocol_sha256": protocol["protocol_sha256"], "cell_id": cell["id"],
        "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "passed": True, "live_save_audit": result["audit"]["terminal_cleanup"],
        "trajectory_snapshot": result["audit"]["trajectory_snapshot"],
        "live_save_inventory_sha256": observed, "expected_save_inventory_sha256": backup["files"],
        "observed_game_processes": processes, "no_game_process": True,
        "child": {key: cell.get(key) for key in ("status", "exit_code", "process", "recovered_at", "result_status", "result_reason")},
        "child_verification": "recovered_completed_terminal_exit_code_unavailable" if recovered else "recorded_zero_exit",
        "status": result["status"], "reason": result["reason"],
        "artifact_sha256": {name: hashlib.sha256((trial / name).read_bytes()).hexdigest()
            for name in ("run.json", "visual-report.json", "trajectory.jsonl", "save-backup/manifest.json", "save-backup/restoration.json")},
        "scope": "Point-in-time post-child cleanup check; does not assert future file/process state or full-game completion."}
    target = directory / "cleanup-checks" / cell["id"] / (checked_at.replace(":", "-") + "-" + uuid4().hex + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
    with target.open("xb") as output:
        output.write(data)
    return {"path": target.relative_to(directory).as_posix(), "sha256": hashlib.sha256(data).hexdigest()}


def run(directory, limit):
    control = StopControl(directory / "stop-request.json", str(directory.resolve()))
    protocol, ledger = read(directory / "protocol.json"), read(directory / "ledger.json")
    verify_protocol(protocol, directory=directory)
    with shared.controller_lock(directory):
        validate_ledger(ledger, protocol)
        for cell in ledger["cells"]:
            reconcile(directory, cell)
        write(directory / "ledger.json", ledger)
        refresh_summary(directory, ledger, protocol)
        for cell in ledger["cells"]:
            if cell["status"] in ("finished", "interrupted_unknown"):
                check = require_audited_cleanup(directory, cell, protocol)
                if check:
                    cell.setdefault("cleanup_checks", []).append(check)
                    write(directory / "ledger.json", ledger)
        done = 0
        for cell in ledger["cells"]:
            if control.pending():
                ledger["stop_requested"] = True
                write(directory / "ledger.json", ledger)
                break
            if cell["status"] != "planned" or done >= limit:
                continue
            verify_protocol(protocol, directory=directory)
            if control.pending():
                ledger["stop_requested"] = True
                write(directory / "ledger.json", ledger)
                break
            if trial_directory(directory, cell).exists():
                raise RuntimeError("Planned trial output already exists; it will not be overwritten")
            logs = directory / "logs"
            logs.mkdir(exist_ok=True)
            log = logs / (cell["id"].replace("/", "__") + ".log")
            command = trial_command(directory, cell, protocol)
            command += ["--stop-file", str(control.path), "--stop-scope", control.scope]
            if control.pending():
                break
            cell.update(status="running", started_at=stamp(), command=command, log=str(log.relative_to(directory)))
            write(directory / "ledger.json", ledger)
            with log.open("xb") as output:
                child = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                cell["process"] = shared.process_identity(child.pid)
                write(directory / "ledger.json", ledger)
                code = wait_for_protected_child(child, control)
            cell.update(status="finished", finished_at=stamp(), exit_code=code)
            write(directory / "ledger.json", ledger)
            refresh_summary(directory, ledger, protocol)
            check = require_audited_cleanup(directory, cell, protocol)
            if check:
                cell.setdefault("cleanup_checks", []).append(check)
                write(directory / "ledger.json", ledger)
            verify_protocol(protocol, directory=directory)
            done += 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "run", "report", "stop"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--initiator", default="operator", help="Identity of stop requester")
    parser.add_argument("--reason", default="operator_requested")
    parser.add_argument("--native-evidence", type=Path, help="Portable admission spec (freeze only)")
    parser.add_argument("--evidence-root", type=Path, help="Portable evidence root (freeze only)")
    args = parser.parse_args(argv)
    if (args.native_evidence is None) != (args.evidence_root is None):
        parser.error("--native-evidence and --evidence-root must be provided together")
    if args.operation != "freeze" and args.native_evidence is not None:
        parser.error("Portable evidence options are freeze-only")
    if args.limit < 1:
        parser.error("--limit must be positive")
    directory = args.output.resolve()
    if args.operation == "stop":
        request_stop(directory / "stop-request.json", str(directory), args.initiator, args.reason)
    elif args.operation == "freeze":
        freeze(directory, native_evidence=args.native_evidence, evidence_root=args.evidence_root)
    elif args.operation == "run":
        run(directory, args.limit)
    else:
        refresh_summary(directory, read(directory / "ledger.json"), read(directory / "protocol.json"))
    print(directory)


if __name__ == "__main__":
    main()
