"""Read-only replay of one recorded benchmark invocation.

Scenario definitions come from trajectory headers, never the current default suite.
Cached runner summaries are identified but are not trusted as recomputed results.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .aggregate import aggregate
from .scenario import Scenario, load_suite
from .scoring import score_instance

FINAL_STATUSES = {"completed", "error", "interrupted"}


def run_validation(manifest: dict, sidecar: dict | None = None) -> dict:
    """Normalize explicit validation restrictions without certifying unmarked runs."""
    sidecar = sidecar or {}
    statuses = (manifest.get("validation_status"), sidecar.get("validation_status"))
    status = "diagnostic_only" if "diagnostic_only" in statuses else next((item for item in statuses if item), None)
    comparable = manifest.get("valid_for_model_comparison")
    if comparable is None:
        comparable = sidecar.get("valid_for_model_comparison")
    excluded = status == "diagnostic_only" or any(
        source.get("valid_for_model_comparison") is False for source in (manifest, sidecar))
    limitations = []
    for source in (manifest.get("validation_limitations"), sidecar.get("limitations"),
                   sidecar.get("validation_limitations")):
        if isinstance(source, list):
            limitations.extend(item for item in source if isinstance(item, str) and item not in limitations)
    return {"status": status, "comparison_eligible": not excluded,
            "valid_for_model_comparison": False if excluded else comparable if isinstance(comparable, bool) else None,
            "limitations": limitations}


def validation_from_directory(directory: Path | str, manifest: dict) -> dict:
    sidecar = {}
    path = Path(directory) / "validation.json"
    if path.exists():
        try:
            sidecar = _read_object(path)
        except (OSError, ValueError, UnicodeError) as error:
            sidecar = {"valid_for_model_comparison": False,
                       "limitations": [f"validation.json could not be read: {error}"]}
    return run_validation(manifest, sidecar)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def summarize_model_usage(records: list[dict]) -> dict:
    """Sum recorded completions without inventing token prices or failed-call usage."""
    traces = [record["model"] for record in records if isinstance(record.get("model"), dict)]
    tokens = {"input_tokens": 0, "output_tokens": 0}
    known = {key: 0 for key in tokens}
    costs: list[float] = []
    latencies: list[float] = []
    requests = []
    for trace in traces:
        usage = trace.get("usage") or {}
        if isinstance(usage, dict):
            for key in tokens:
                value = usage.get(key)
                if _number(value):
                    tokens[key] += value
                    known[key] += 1
        cost = trace.get("cost_usd", trace.get("estimated_cost_usd"))
        if _number(cost):
            costs.append(cost)
        latency = trace.get("latency_seconds")
        if _number(latency):
            latencies.append(latency)
        requests.append({key: trace.get(key) for key in (
            "provider", "model", "request_id", "client_request_id", "latency_seconds",
            "usage", "action_selection", "decision_contract") if trace.get(key) is not None})
    return {
        "recorded_completions": len(traces),
        "models": sorted({str(trace["model"]) for trace in traces if trace.get("model")}),
        "providers": sorted({str(trace["provider"]) for trace in traces if trace.get("provider")}),
        **{key: tokens[key] if known[key] else None for key in tokens},
        "completions_with_input_usage": known["input_tokens"],
        "completions_with_output_usage": known["output_tokens"],
        "recorded_cost_usd": round(sum(costs), 8) if costs else None,
        "completions_with_cost": len(costs),
        "latency_seconds_total": round(sum(latencies), 3) if latencies else None,
        "latency_seconds_mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "completions_with_latency": len(latencies),
        "requests": requests,
        "scope": "Recorded completions only; usage and cost of failed or unrecorded requests are unknown.",
    }


def _read_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a JSON object")
    return data


def _read_records(path: Path) -> tuple[list[dict], list[str]]:
    records, errors = [], []
    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [], [f"{path.name}: cannot read trajectory: {error}"]
    for line_no, line in enumerate(contents.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("expected a JSON object")
            records.append(record)
        except (ValueError, TypeError) as error:
            errors.append(f"{path.name}:{line_no}: invalid trajectory record: {error}")
    return records, errors


def load_run_report(directory: Path | str, *, legacy_suite: Path | str | None = None) -> dict:
    """Recompute final attempts and best retries, exposing gaps in the planned denominator.

    ``legacy_suite`` is an explicit fallback for old files without an embedded scenario.
    It does not replace embedded definitions or repair invalid definitions silently.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"run directory does not exist: {directory}")
    paths = sorted(directory.glob("*.jsonl"), key=lambda path: path.name)
    if not paths and any(directory.glob("*/run.json")):
        raise ValueError("select one invocation's run directory, not its parent benchmark directory")
    warnings, errors = [], []
    manifest = {}
    if (directory / "run.json").exists():
        try:
            manifest = _read_object(directory / "run.json")
        except (OSError, ValueError, UnicodeError) as error:
            errors.append(f"run.json: invalid run manifest: {error}")
    else:
        warnings.append("No run.json manifest; the original selected suite and run lifecycle are unknown.")
    validation = validation_from_directory(directory, manifest)
    planned = manifest.get("scenario_ids")
    planned_known = (isinstance(planned, list) and all(isinstance(item, str) for item in planned)
                     and len(set(planned)) == len(planned))
    if not planned_known:
        if "scenario_ids" in manifest:
            errors.append("run.json: scenario_ids must be a list of unique scenario identifiers")
        planned = None
    fallback = {scenario.id: scenario for scenario in load_suite(legacy_suite)} if legacy_suite is not None else {}
    attempts, definitions, all_records = [], {}, []
    groups: dict[str, list[dict]] = {}
    for path in paths:
        records, problems = _read_records(path)
        all_records.extend(records)
        meta_records = [record for record in records if record.get("kind") == "meta"]
        meta = meta_records[0].get("meta") if meta_records else None
        meta = meta if isinstance(meta, dict) else {}
        if len(meta_records) != 1 or not records or records[0].get("kind") != "meta":
            problems.append(f"{path.name}: expected exactly one initial metadata header")
        end_records = [record for record in records if record.get("kind") == "end"]
        end = end_records[-1] if end_records else None
        if len(end_records) > 1 or (end is not None and records[-1] is not end):
            problems.append(f"{path.name}: terminal marker must occur exactly once at the end")
        status = end.get("status") if end else ("running" if manifest.get("status") == "running" else "incomplete")
        if end is not None and status not in FINAL_STATUSES:
            problems.append(f"{path.name}: unsupported terminal status {status!r}")
        scenario_id = meta.get("scenario_id")
        scenario = None
        source = "recorded"
        try:
            if "scenario" in meta:
                if not isinstance(meta["scenario"], dict):
                    raise ValueError("embedded scenario must be a JSON object")
                scenario = Scenario.from_dict(meta["scenario"])
            elif scenario_id in fallback:
                scenario = fallback[scenario_id]
                source = "explicit_legacy_suite"
                warnings.append(f"{path.name}: using explicit legacy suite; original scenario configuration was not recorded.")
            else:
                raise ValueError("no embedded scenario definition; use --legacy-suite explicitly for legacy files")
            if scenario_id != scenario.id:
                raise ValueError(f"metadata scenario_id {scenario_id!r} differs from embedded id {scenario.id!r}")
            if scenario_id in definitions and definitions[scenario_id].to_dict() != scenario.to_dict():
                raise ValueError("scenario definition differs between retry attempts")
            definitions[scenario_id] = scenario
        except (ValueError, KeyError, TypeError) as error:
            problems.append(f"{path.name}: cannot decode recorded scenario: {error}")
        if planned_known and scenario_id not in planned:
            problems.append(f"{path.name}: scenario {scenario_id!r} is outside run.json scenario_ids")
        result = None
        if end is not None and not problems and scenario is not None:
            try:
                result = score_instance(records, scenario)
                result["trajectory"] = str(path)
                groups.setdefault(scenario.id, []).append(result)
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                problems.append(f"{path.name}: cannot score recorded observations: {error}")
        match = re.search(r"\.a(\d+)$", path.stem)
        attempts.append({"file": path.name, "scenario": scenario_id,
                         "attempt": int(match.group(1)) if match else 0,
                         "status": "invalid" if problems else status,
                         "terminal_status": end.get("status") if end else None,
                         "reason": end.get("reason") if end else None,
                         "error": end.get("error") if end else None,
                         "finalized": end is not None and status in FINAL_STATUSES,
                         "scenario_source": source, "result": result,
                         "model_usage": summarize_model_usage(records), "errors": problems})
        errors.extend(problems)
    # Filename order is not numeric retry order (a10 precedes a2).
    attempts.sort(key=lambda attempt: (str(attempt["scenario"]), attempt["attempt"], attempt["file"]))
    groups = {}
    for attempt in attempts:
        if attempt["result"] is not None:
            groups.setdefault(attempt["scenario"], []).append(attempt["result"])
    instance_ids = planned if planned_known else sorted(groups)
    results = []
    for scenario_id in instance_ids:
        rows = groups.get(scenario_id, [])
        if not rows:
            continue
        best = dict(max(rows, key=lambda result: (result["solved"], result.get("ftl_score", 0))))
        if manifest.get("retries", 0) or len(rows) > 1 or any(
            attempt["scenario"] == scenario_id and re.search(r"\.a\d+\.jsonl$", attempt["file"])
            for attempt in attempts
        ):
            best.update(attempts_used=len(rows), attempt_ftl_scores=[row.get("ftl_score", 0) for row in rows],
                        attempt_solved=[row["solved"] for row in rows],
                        attempt_statuses=[row.get("status", "completed") for row in rows],
                        attempt_failures=sum(row.get("status") == "error" for row in rows))
        results.append(best)
    recorded_metrics = aggregate(results, list(definitions.values()))
    metrics = aggregate(results if validation["comparison_eligible"] else [], list(definitions.values()))
    for metric in (metrics, recorded_metrics):
        metric.update({"agent": manifest.get("agent"), "run_id": manifest.get("run_id"),
                       "status": manifest.get("status", "unknown")})
    seen = {attempt["scenario"] for attempt in attempts}
    missing = [scenario_id for scenario_id in (planned or []) if scenario_id not in seen]
    unscored = [scenario_id for scenario_id in (planned or []) if scenario_id not in groups]
    nonfinal = [attempt["file"] for attempt in attempts if not attempt["finalized"]]
    invalid = [attempt["file"] for attempt in attempts if attempt["errors"]]
    complete = bool(planned_known and manifest.get("status") in FINAL_STATUSES
                    and not unscored and not nonfinal and not errors)
    if unscored:
        warnings.append(f"{len(unscored)} planned scenario(s) have no finalized, scorable attempt; aggregate denominator is the scorable subset.")
    if nonfinal:
        warnings.append(f"{len(nonfinal)} attempt(s) lack a terminal marker and are excluded from finalized metrics.")
    if manifest.get("status") == "running":
        warnings.append("The run is still marked running; these are provisional finalized-attempt metrics.")
    if not validation["comparison_eligible"]:
        warnings.append("Diagnostic result: excluded from model-comparison aggregates; recorded scores and outcomes are retained.")
        warnings.extend(f"Validation limitation: {limitation}" for limitation in validation["limitations"])
    cached = sorted(path.name for path in directory.glob("summary_*.json"))
    return {
        "report_schema": 1, "recomputed": True, "directory": str(directory), "run": manifest,
        "validation": validation,
        "coverage": {"complete": complete, "planned_known": planned_known,
                     "planned_instances": len(planned) if planned_known else None,
                     "scored_instances": len(results), "attempt_files": len(attempts),
                     "finalized_attempts": sum(attempt["finalized"] for attempt in attempts),
                     "missing_scenarios": missing, "unscored_scenarios": unscored,
                     "nonfinal_attempts": nonfinal, "invalid_attempts": invalid,
                     "metric_scope": "finalized_scorable_scenarios"},
        "aggregate": metrics, "recorded_aggregate": recorded_metrics,
        "comparison": {"instances": len(results) if validation["comparison_eligible"] else 0,
                       "excluded_instances": 0 if validation["comparison_eligible"] else len(results),
                       "metric_scope": "model_comparison"},
        "instances": results, "attempts": attempts,
        "model_usage": summarize_model_usage(all_records),
        "cached_summary_files": cached, "warnings": warnings, "errors": errors,
    }


def render_run_report(report: dict, *, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    run, coverage, metrics, usage = (report[key] for key in ("run", "coverage", "aggregate", "model_usage"))
    planned = coverage["planned_instances"] if coverage["planned_known"] else "unknown"
    lines = [f"Run {run.get('run_id', Path(report['directory']).name)} ({run.get('status', 'unknown')})",
             f"Recomputed from recorded scenarios: {coverage['scored_instances']}/{planned} planned instances scorable.",
             f"{'Complete' if coverage['complete'] else 'Partial/provisional'} finalized-file coverage; coverage does not certify model comparability.",
             f"Model-comparison instances: {report['comparison']['instances']}; excluded diagnostic instances: {report['comparison']['excluded_instances']}.",
             "Model-comparison aggregate: " + metrics["headline"],
             f"Failed selected comparison attempts: {metrics['failed']}; interrupted: {metrics['interrupted']}; all recorded attempt failures: {report['recorded_aggregate']['attempt_failures']}.",
             f"Recorded model completions: {usage['recorded_completions']}; input tokens: {usage['input_tokens']}; output tokens: {usage['output_tokens']}; recorded cost USD: {usage['recorded_cost_usd']}.",
             usage["scope"]]
    if not report["validation"]["comparison_eligible"]:
        recorded = report["recorded_aggregate"]
        lines.extend(["DIAGNOSTIC ONLY: recorded outcomes do not enter model-comparison aggregates.",
                      "Recorded trajectory aggregate: " + recorded["headline"],
                      f"Recorded failed selected attempts: {recorded['failed']}; interrupted: {recorded['interrupted']}; all recorded attempt failures: {recorded['attempt_failures']}."])
    for result in report["instances"]:
        lines.append(f"  {result['scenario']}: FTL {result['ftl_score']}, solved={result['solved']}, {result.get('status')} / {result.get('reason')}")
    for label in ("warnings", "errors"):
        lines.extend(f"{label[:-1].upper()}: {message}" for message in report[label])
    if report["cached_summary_files"]:
        lines.append("Cached summaries were not used: " + ", ".join(report["cached_summary_files"]))
    return "\n".join(lines) + "\n"
