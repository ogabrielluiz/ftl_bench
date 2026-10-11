"""Read-only projections of saved matrix reports; no scoring or live control."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_MATRICES = 32
FULLGAME_CONTRACT = "ftl-fullgame-experiment-v1"
MATRIX_CONTRACTS = ("ftl-visual-challenge-matrix-v1", "ftl-visual-challenge-matrix-v2")
FULLGAME_CONTRACTS = (FULLGAME_CONTRACT, "ftl-fullgame-experiment-v2")
PORTABLE_CONTRACTS = (MATRIX_CONTRACTS[1], FULLGAME_CONTRACTS[1])
FULLGAME_ARTIFACTS = ("run.json", "visual-report.json", "trajectory.jsonl",
                      "save-backup/manifest.json", "save-backup/restoration.json")


def stored_admission(protocol: dict) -> dict | None:
    """Expose frozen protocol metadata, never recompute or claim fresh admission."""
    if protocol.get("contract") not in PORTABLE_CONTRACTS:
        return None
    selector = protocol.get("admission_selector")
    if (not isinstance(selector, dict)
            or selector.get("contract") != "portable-visual-controller-admission-v1"
            or not isinstance(selector.get("admission"), dict)):
        raise ValueError("portable protocol stored admission metadata missing")
    admission = selector["admission"]
    fields = ("candidate", "build_origin", "review", "reviewer", "runtime", "runtime_files")
    if (not isinstance(selector.get("spec"), dict)
            or any(not isinstance(admission.get(name), dict) for name in fields)
            or not isinstance(selector.get("evidence_files"), dict)):
        raise ValueError("portable protocol stored admission metadata malformed")
    return {"source": "Stored protocol admission metadata only; the dashboard does not rerun admission or a live runtime audit.",
            "spec": selector["spec"], **{name: admission[name] for name in fields},
            "evidence_files": selector["evidence_files"]}


def safe_path(root: Path, path: Path) -> Path:
    lexical_root = root.absolute()
    root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("outside benchmark directory")
    current = path.absolute()
    while current != root and current != lexical_root:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError("linked artifacts are not served")
        if current.parent == current:
            raise ValueError("artifact path has no benchmark ancestor")
        current = current.parent
    return resolved


def read_json(root: Path, path: Path) -> tuple[dict, str]:
    path = safe_path(root, path)
    with path.open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("artifact exceeds size limit")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("artifact is not an object")
    return value, hashlib.sha256(data).hexdigest()


def trial_kind(run: dict) -> str:
    if run.get("setup_only") is True or run.get("provider") == "none":
        return "scripted_probe" if run.get("reason") == "timing_probe_completed" else "setup_check"
    if run.get("fixture_only") is True and not run.get("model"):
        return "scripted_probe"
    return "model_trial" if run.get("model") else "recorded_run"


def trial_label(run: dict, fallback: str) -> str:
    kind = trial_kind(run)
    if run.get("track") != "visual-v1":
        return fallback
    parts = [run.get("challenge") or run.get("scenario_id") or fallback]
    if kind == "model_trial":
        parts.extend([run["model"], run.get("observation_mode")])
    else:
        parts.append({"scripted_probe": "Scripted probe", "setup_check": "Setup check"}.get(kind, "Recorded run"))
    if run.get("repetition") is not None:
        parts.append(f"Repeat {run['repetition']}")
    return " · ".join(str(part) for part in parts if part)


def replay_link(root: Path, directory: Path) -> tuple[str | None, str | None]:
    try:
        trajectory = safe_path(root, directory / "trajectory.jsonl")
        if not trajectory.is_file():
            return None, None
        selection = trajectory.relative_to(root.resolve()).with_suffix("").as_posix()
        return selection, "/?" + urlencode({"sel": selection})
    except (OSError, ValueError):
        return None, None


def fullgame_terminal_evidence(root: Path, directory: Path, saved: dict, receipt: dict) -> None:
    """Join the cleanup snapshot to fixed artifact paths and the raw native ending."""
    hashes = receipt.get("artifact_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(FULLGAME_ARTIFACTS):
        raise ValueError("cleanup artifact snapshot is incomplete")
    terminal, last_observation, final_kind = None, None, None
    for name in FULLGAME_ARTIFACTS:
        digest = hashlib.sha256()
        path = safe_path(root, directory / name)
        with path.open("rb") as stream:
            if name == "trajectory.jsonl":
                for line in iter(lambda: stream.readline(MAX_JSON_BYTES + 1), b""):
                    if len(line) > MAX_JSON_BYTES:
                        raise ValueError("trajectory record exceeds size limit")
                    digest.update(line)
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("invalid trajectory record")
                    final_kind = row.get("kind")
                    if final_kind == "end":
                        if terminal is not None:
                            raise ValueError("multiple trajectory endings")
                        terminal = row
                    elif terminal is not None:
                        raise ValueError("trajectory continues after ending")
                    if isinstance(row.get("obs"), dict):
                        last_observation = row["obs"]
            else:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        if digest.hexdigest() != hashes[name]:
            raise ValueError("cleanup artifact bytes changed: " + name)
    if final_kind != "end" or terminal is None or last_observation is None:
        raise ValueError("raw terminal/native observation missing")
    for value in (terminal, receipt, read_json(root, directory / "run.json")[0],
                  read_json(root, directory / "visual-report.json")[0]):
        if (value.get("status"), value.get("reason")) != (saved.get("status"), saved.get("reason")):
            raise ValueError("raw lifecycle disagrees with saved outcome")
    native = ("victory" if terminal.get("status") == "completed" and terminal.get("reason") == "native_victory"
              and last_observation.get("victory") is True else
              "defeat" if terminal.get("status") == "completed" and terminal.get("reason") == "native_game_over"
              and last_observation.get("game_over") is True and last_observation.get("victory") is not True else None)
    if native != saved.get("native_outcome"):
        raise ValueError("raw native ending disagrees with saved outcome")


def fullgame_view(root, directory, key, protocol, ledger, protocol_hash, ledger_hash):
    """Project saved full-game audits; never infer endings from budgets or scores."""
    declared = protocol.get("cells")
    cells = ledger["cells"]
    if not isinstance(declared, list) or len(declared) != 5 or len(cells) != 5:
        raise ValueError("full-game protocol must declare all five cells")
    immutable = ("id", "model", "mode", "scope", "stop_after_sector")
    ids = set()
    for index, (cell, expected) in enumerate(zip(cells, declared)):
        if not isinstance(expected, dict) or any(cell.get(k) != expected.get(k) for k in immutable):
            raise ValueError("full-game ledger cell differs from protocol")
        name = cell.get("id")
        if (not isinstance(name, str) or not name or name == "." or Path(name).is_absolute()
                or ".." in Path(name).parts or name in ids):
            raise ValueError("invalid full-game cell identity")
        ids.add(name)
        if (cell.get("mode") not in ("image", "hybrid") or not isinstance(cell.get("model"), str)
                or cell.get("status") not in ("planned", "running", "finished", "interrupted_unknown")):
            raise ValueError("invalid full-game condition")
        if index == 0:
            if (cell.get("scope") != "sector_pilot" or cell.get("mode") != "image"
                    or type(cell.get("stop_after_sector")) is not int or cell["stop_after_sector"] != 1):
                raise ValueError("invalid sector pilot")
        elif cell.get("scope") != "full_game" or cell.get("stop_after_sector") is not None:
            raise ValueError("invalid full-game scope")
    models = list(dict.fromkeys(c["model"] for c in cells[1:]))
    if (len(models) != 2 or cells[0]["model"] != models[0]
            or [(c["model"], c["mode"]) for c in cells[1:]] != [(m, mode) for m in models for mode in ("image", "hybrid")]):
        raise ValueError("invalid full-game condition order")
    identity = protocol["protocol_sha256"]
    issues, report, report_hash = [], {}, None
    try:
        report, report_hash = read_json(root, directory / "comparison.json")
        if (report.get("contract") != protocol["contract"] or report.get("protocol_sha256") != identity
                or report.get("pilot_excluded_from_fullgame_totals") is not True):
            raise ValueError("full-game comparison identity mismatch")
    except (OSError, ValueError, UnicodeError) as error:
        report = {}
        issues.append("Saved full-game report unavailable or updating: " + str(error))
    trials = report.get("trials", [])
    if (not isinstance(trials, list) or len(trials) > 5 or any(not isinstance(t, dict) for t in trials)
            or not isinstance(report.get("limitations", []), list)
            or any(not isinstance(item, str) for item in report.get("limitations", []))):
        raise ValueError("invalid full-game report collections")
    for trial in trials:
        if (not isinstance(trial.get("issues", []), list) or any(not isinstance(x, str) for x in trial.get("issues", []))
                or trial.get("metrics") is not None and not isinstance(trial["metrics"], dict)
                or trial.get("model_calls") is not None and not isinstance(trial["model_calls"], dict)):
            raise ValueError("invalid full-game trial fields")
    counts = {s: sum(c["status"] == s for c in cells) for s in ("planned", "running", "finished")}
    counts.update(total=5, unknown=sum(c["status"] == "interrupted_unknown" for c in cells))
    rows, used = [], set()
    for cell in cells:
        name = cell["id"]
        trial_directory = safe_path(root, directory / "trials" / name)
        candidates = [(i, t) for i, t in enumerate(trials) if t.get("id") == name]
        saved = {}
        if len(candidates) == 1:
            index, candidate = candidates[0]
            try:
                if (candidate.get("scope") != cell["scope"] or candidate.get("requested_model") != cell["model"]
                        or candidate.get("mode") != cell["mode"] or not isinstance(candidate.get("directory"), str)
                        or safe_path(root, Path(candidate["directory"])) != trial_directory
                        or cell["status"] not in ("finished", "interrupted_unknown")):
                    raise ValueError("saved trial does not match its cell")
                saved = candidate
                used.add(index)
            except (OSError, ValueError):
                issues.append("Saved full-game identity disagrees with cell " + name)
        elif len(candidates) > 1:
            issues.append("Multiple saved full-game trials for " + name)
        native = saved.get("native_outcome")
        terminal_native = (saved.get("status") == "completed" and
            ((native == "victory" and saved.get("reason") == "native_victory")
             or (native == "defeat" and saved.get("reason") == "native_game_over")))
        complete = cell["scope"] == "full_game" and terminal_native
        verified = complete and saved.get("integrity_passed") is True
        consistent = (bool(saved) and type(saved.get("integrity_passed")) is bool
            and native in (None, "victory", "defeat") and (native is None or terminal_native)
            and saved.get("fullgame_complete") is complete and saved.get("verified_fullgame_complete") is verified)
        if saved and not consistent:
            issues.append("Saved completion flags are inconsistent for " + name)
        cleanup, terminal_verified = [], False
        checks = cell.get("cleanup_checks", [])
        if not isinstance(checks, list):
            raise ValueError("invalid cleanup evidence list")
        for check in checks:
            try:
                if (not isinstance(check, dict) or not isinstance(check.get("path"), str)
                        or Path(check["path"]).is_absolute() or ".." in Path(check["path"]).parts):
                    raise ValueError("invalid cleanup reference")
                path = safe_path(root, directory / check["path"])
                if not path.is_relative_to(directory / "cleanup-checks" / name):
                    raise ValueError("cleanup belongs to another cell")
                receipt, digest = read_json(root, path)
                if (digest != check.get("sha256") or receipt.get("contract") != "fullgame-live-cleanup-check-v1"
                        or receipt.get("protocol_sha256") != identity or receipt.get("cell_id") != name
                        or receipt.get("passed") is not True or receipt.get("no_game_process") is not True
                        or not isinstance(receipt.get("checked_at"), str) or not receipt["checked_at"]):
                    raise ValueError("cleanup receipt identity mismatch")
                if saved:
                    fullgame_terminal_evidence(root, trial_directory, saved, receipt)
                    terminal_verified = True
                cleanup.append({"path": check["path"], "sha256": digest, "checked_at": receipt.get("checked_at")})
            except (OSError, ValueError, UnicodeError) as error:
                issues.append("Saved cleanup evidence unavailable for " + name + ": " + str(error))
        audit = saved.get("audit")
        if verified and (not terminal_verified or not isinstance(audit, dict)
                         or audit.get("complete") is not True or audit.get("issues") != []
                         or saved.get("issues") != []):
            consistent = False
            issues.append("Native ending verification is pending or inconsistent for " + name)
        if verified and protocol["contract"] == FULLGAME_CONTRACTS[1]:
            try:
                # Confine and bound each saved input before the reusable audit.
                for filename in ("controller-admission.json", "run.json", "runtime-fingerprint.json"):
                    read_json(root, trial_directory / filename)
                read_json(root, directory / "protocol.json")
                from ftl_bench.visual_admission import audit_trial_admission
                admission_issues = audit_trial_admission(
                    trial_directory, protocol, protocol_file=directory / "protocol.json")
                if admission_issues:
                    raise ValueError("; ".join(admission_issues))
            except (OSError, ValueError, UnicodeError) as error:
                consistent = False
                issues.append("Saved full-game admission unavailable for " + name + ": " + str(error))
        selection, url = replay_link(root, trial_directory)
        rows.append({"id": name, "model": cell["model"], "mode": cell["mode"], "scope": cell["scope"],
            "status": cell["status"], "kind": "model_trial", "reason": saved.get("reason", cell.get("result_reason")),
            "outcome_category": saved.get("category"), "native_outcome": native,
            "integrity_passed": saved.get("integrity_passed"),
            "verified_fullgame_complete": verified if consistent else None,
            "exclusions": saved.get("issues", []), "metrics": saved.get("metrics"),
            "model_calls": saved.get("model_calls"), "selection": selection, "replay_url": url,
            "cleanup_evidence": cleanup})
    expected_trials = sum(c["status"] in ("finished", "interrupted_unknown") for c in cells)
    if len(used) != len(trials) or len(used) != expected_trials:
        issues.append("Saved full-game results and ledger are at different refresh boundaries.")
    full = [r for r in rows if r["scope"] == "full_game" and r["status"] in ("finished", "interrupted_unknown")]
    verified = [r for r in full if r["verified_fullgame_complete"] is True]
    expected_counts = {"planned": counts["planned"], "running": counts["running"], "finished_attempts": expected_trials,
        "fullgame_attempts": len(full), "verified_fullgame_completions": len(verified),
        "victories": sum(r["native_outcome"] == "victory" for r in verified),
        "defeats": sum(r["native_outcome"] == "defeat" for r in verified), "incomplete_fullgames": len(full) - len(verified)}
    saved_counts = report.get("counts")
    typed_counts = (isinstance(saved_counts, dict) and set(saved_counts) == set(expected_counts)
                    and all(type(n) is int and n >= 0 for n in saved_counts.values()))
    # The controller writes planned -> running to the ledger before launching
    # the protected child, and refreshes comparison.json only after it exits.
    # Allow that execution-only lag; every saved terminal total must still join
    # the audited rows above. Never excuse a finished/unknown result mismatch.
    live_progress = (typed_counts and not issues
        and 0 < saved_counts["planned"] - expected_counts["planned"]
            == expected_counts["running"] - saved_counts["running"]
        and all(saved_counts[k] == v for k, v in expected_counts.items() if k not in ("planned", "running")))
    if report and (not typed_counts or saved_counts != expected_counts) and not live_progress:
        issues.append("Saved full-game totals disagree with joined trial evidence.")
    refresh = "unavailable" if not report else "inconsistent" if issues else "live_progress" if live_progress else "current"
    return {"key": key, "name": directory.name, "experiment_kind": "full_game", "protocol_sha256": identity,
        "contract": protocol["contract"], "stored_admission": stored_admission(protocol),
        "scope": report.get("scope", protocol.get("scope")), "partial": counts["finished"] < 5 or bool(issues),
        "qualified_scoped_comparison": False, "valid_for_full_game_comparison": False,
        "counts": counts, "reported_trials": len(trials), "requested_models": models,
        "budgets": protocol.get("budgets"), "seed": protocol.get("seed"), "conditions": [], "trials": rows,
        "fullgame_summary": expected_counts if report and not issues else None,
        "summary_refresh": refresh,
        "limitations": report.get("limitations", []), "issues": issues,
        "source": "Execution progress comes from the ledger; terminal totals come from saved run_fullgame_experiment comparison.json and hash-joined cleanup receipts. Running progress is provisional; no live audit or scoring by the dashboard.",
        "artifact_sha256": {"protocol.json": protocol_hash, "ledger.json": ledger_hash, "comparison.json": report_hash}}


def comparison_view(bench: Path, key: str) -> dict:
    root = bench.resolve()
    if not isinstance(key, str) or Path(key).is_absolute() or ".." in Path(key).parts:
        raise ValueError("invalid comparison key")
    directory = safe_path(root, root / key)
    protocol, protocol_file_hash = read_json(root, directory / "protocol.json")
    if protocol.get("contract") not in (*MATRIX_CONTRACTS, *FULLGAME_CONTRACTS):
        raise ValueError("not a visual matrix")
    identity = protocol.get("protocol_sha256")
    unhashed = {k: v for k, v in protocol.items() if k != "protocol_sha256"}
    if identity != hashlib.sha256(json.dumps(unhashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest():
        raise ValueError("protocol digest mismatch")
    ledger, ledger_hash = read_json(root, directory / "ledger.json")
    if ledger.get("protocol_sha256") != identity or not isinstance(ledger.get("cells"), list):
        raise ValueError("ledger protocol mismatch")
    cells = ledger["cells"]
    if len(cells) > 5000 or any(not isinstance(c, dict) for c in cells):
        raise ValueError("invalid ledger cells")
    if protocol.get("contract") in FULLGAME_CONTRACTS:
        return fullgame_view(root, directory, key, protocol, ledger, protocol_file_hash, ledger_hash)
    issues = []
    report, report_hash = {}, None
    try:
        report, report_hash = read_json(root, directory / "comparison.json")
        # Legacy aggregate reports predate the explicit contract field. Only
        # their absent field is tolerated; v2 requires exact protocol semantics.
        report_contract = report.get("contract", MATRIX_CONTRACTS[0])
        if (report.get("protocol_sha256") != identity or report.get("report_version") != "visual-comparison-v1"
                or report_contract != protocol["contract"]):
            raise ValueError("comparison protocol mismatch")
    except (OSError, ValueError, UnicodeError) as exc:
        report = {}
        issues.append("Saved comparison report unavailable or updating: " + str(exc))
    conditions = report.get("conditions", [])
    trials = report.get("trials", [])
    if (not isinstance(conditions, list) or not isinstance(trials, list)
            or any(not isinstance(row, dict) for row in conditions + trials)
            or not isinstance(report.get("limitations", []), list)):
        raise ValueError("invalid report collections")
    counts = {status: sum(c.get("status") == status for c in cells) for status in ("planned", "running", "finished")}
    counts.update(total=len(cells), unknown=sum(c.get("status") not in counts for c in cells))
    rows, matched = [], []
    cell_ids = set()
    for cell in cells:
        cell_id = cell.get("id")
        if not isinstance(cell_id, str) or Path(cell_id).is_absolute() or ".." in Path(cell_id).parts:
            raise ValueError("invalid cell path")
        if cell_id in cell_ids:
            raise ValueError("duplicate ledger cell")
        cell_ids.add(cell_id)
        cell_directory = safe_path(root, directory / "trials" / cell_id)
        recorded = []
        for index, saved in enumerate(trials):
            identity_matches = (saved.get("model"), saved.get("mode"), saved.get("scenario"), saved.get("repetition")) == (
                cell.get("model"), cell.get("mode"), cell.get("challenge"), cell.get("repetition"))
            directory_matches = False
            if isinstance(saved.get("directory"), str):
                try:
                    directory_matches = safe_path(root, Path(saved["directory"])).is_relative_to(cell_directory)
                except (OSError, ValueError):
                    pass
            # An unreadable run still has an authoritative directory/exclusion,
            # even when the aggregator could not read its model identity.
            if identity_matches or directory_matches:
                recorded.append(saved)
                matched.append((index, cell_id, cell.get("status")))
                if directory_matches and any(key in saved for key in ("model", "mode", "scenario", "repetition")) and not identity_matches:
                    issues.append(f"Saved trial identity disagrees with its cell {cell_id}.")
        if len(recorded) > 1:
            issues.append(f"Multiple saved trials for {cell_id}; no result selected.")
        trial = recorded[0] if len(recorded) == 1 else {}
        selection, url = None, None
        run = {}
        if isinstance(trial.get("directory"), str):
            trial_directory = Path(trial["directory"])
        else:
            parent = safe_path(root, directory / "trials" / cell_id)
            candidates = list(parent.glob("repetition-*/*/trajectory.jsonl")) if parent.exists() else []
            trial_directory = candidates[0].parent if len(candidates) == 1 else None
        if trial_directory is not None:
            try:
                resolved = safe_path(root, trial_directory)
                if not resolved.is_relative_to(cell_directory):
                    raise ValueError("trial belongs to another cell")
                run, _ = read_json(root, resolved / "run.json")
                selection, url = replay_link(root, resolved)
            except (OSError, ValueError, UnicodeError):
                issues.append(f"Trial replay unavailable for {cell_id}.")
        rows.append({"id": cell_id, "model": cell.get("model"), "mode": cell.get("mode"),
            "challenge": cell.get("challenge"), "repetition": cell.get("repetition"),
            "status": cell.get("status", "unknown"), "kind": trial_kind(run) if run else "model_trial",
            "outcome_category": trial.get("outcome_category"), "reason": trial.get("reason", cell.get("result_reason")),
            "task_success": trial.get("task_success"), "eligible": trial.get("eligible"),
            "exclusions": trial.get("exclusions", []), "decisions": trial.get("decisions"),
            "model_calls": trial.get("model_calls"), "selection": selection, "replay_url": url})
    recorded = len(trials)
    matched_indices = [index for index, _, _ in matched]
    lagging = (counts["finished"] != recorded or len(matched_indices) != recorded
               or len(set(matched_indices)) != recorded
               or any(status != "finished" for _, _, status in matched))
    if lagging:
        issues.append("Saved results and the execution ledger are at different refresh boundaries.")
    return {"key": key, "name": directory.name, "experiment_kind": "challenge", "protocol_sha256": identity,
        "contract": protocol["contract"], "stored_admission": stored_admission(protocol),
        "scope": report.get("scope", "paired_diagnostic_challenges"),
        "qualified_scoped_comparison": report.get("qualified_scoped_comparison") is True and not issues
            and counts["finished"] == counts["total"],
        "valid_for_full_game_comparison": False, "partial": counts["finished"] < counts["total"] or lagging or bool(issues),
        "counts": counts, "reported_trials": recorded, "requested_models": protocol.get("models", []),
        "budgets": protocol.get("budgets"), "seed": protocol.get("seed"),
        "conditions": conditions, "trials": rows, "limitations": report.get("limitations", []), "issues": issues,
        "source": "Saved aggregate_visual_runs comparison.json; outcomes and scoring are not recomputed by the dashboard.",
        "artifact_sha256": {"protocol.json": protocol_file_hash, "ledger.json": ledger_hash, "comparison.json": report_hash}}


def comparison_catalog(bench: Path) -> dict:
    root = bench.resolve()
    candidates = sorted(root.rglob("protocol.json"), key=lambda p: p.as_posix(), reverse=True)
    items, issues = [], []
    for path in candidates:
        if len(items) >= MAX_MATRICES:
            break
        try:
            view = comparison_view(root, path.parent.relative_to(root).as_posix())
            items.append({k: view[k] for k in ("key", "name", "counts", "partial", "protocol_sha256", "experiment_kind")})
        except (OSError, ValueError, UnicodeError):
            # A concurrent or unrelated protocol is not a scored matrix.
            continue
    return {"comparisons": items, "issues": issues}
