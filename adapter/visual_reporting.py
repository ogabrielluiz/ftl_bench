"""Read-only evidence checks and scoped comparisons for recorded visual trials.

This module never starts a game, model, or process and never changes run evidence.
An intact transcript establishes input/protocol integrity, not screenshot fidelity
or model competence. Native control acceptance and challenge prerequisites remain
separate evidence required by the frozen experiment protocol.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import zlib


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _reported_models(call) -> list[str]:
    models = _object(call.get("response_model_identity")).get("models")
    return [m for m in models if isinstance(m, str)] if isinstance(models, list) else []


def outcome_category(reason: str | None, status: str | None = None) -> str:
    return {"native_victory": "game_victory", "native_game_over": "game_loss",
            "fixture_goal_observed": "task_success", "sector_target_observed": "sector_target",
            "decision_budget": "budget_exhausted", "wall_clock_budget": "budget_exhausted",
            "idle_decision_budget": "budget_exhausted", "user_interrupted": "operator_interruption",
            "cooperative_stop_requested": "operator_interruption",
            "external_interference": "external_interference", "visual_model_error": "protocol_failure",
            "visual_protocol_error": "protocol_failure", "visual_backend_error": "infrastructure_failure",
            "visual_infrastructure_error": "infrastructure_failure",
            "protected_run_failed": "infrastructure_failure"}.get(
                reason, "infrastructure_failure" if status == "error" else "unknown")


def summarize_model_calls(records: list[dict]) -> dict:
    """Preserve usage coverage: an absent provider count is never a zero count."""
    calls = [r["model"] for r in records if isinstance(r.get("model"), dict) and r["model"]]
    keys = {k for call in calls for k in _object(call.get("usage")) if isinstance(k, str)}
    keys.update(("input_tokens", "cached_input_tokens", "output_tokens"))
    counts, totals = {}, {}
    for key in sorted(keys):
        values = [c["usage"][key] for c in calls if isinstance(c.get("usage"), dict)
                  and type(c["usage"].get(key)) is int and c["usage"][key] >= 0]
        counts[key] = len(values)
        totals[key] = sum(values) if values else None
    latencies = [c["latency_seconds"] for c in calls
                 if type(c.get("latency_seconds")) in (int, float)
                 and math.isfinite(c["latency_seconds"]) and c["latency_seconds"] >= 0]
    reported = sorted({model for c in calls for model in _reported_models(c)})
    return {"calls": len(calls), "usage": {
        "source": "codex_turn_completed", "observed_totals": totals, "reported_calls": counts,
        "complete_totals": {k: v if counts[k] == len(calls) and calls else None for k, v in totals.items()},
        "missing_means": "unavailable, not zero; cached tokens are a subset of input tokens"},
        "latency_seconds": {"reported_calls": len(latencies),
            "observed_total": round(sum(latencies), 3) if latencies else None,
            "total": round(sum(latencies), 3) if calls and len(latencies) == len(calls) else None,
            "median": statistics.median(latencies) if latencies else None},
        "requested_models": sorted({c.get("requested_model", c.get("model")) for c in calls
                                    if isinstance(c.get("requested_model", c.get("model")), str)}),
        "response_model_identity": {"reported_models": reported,
            "reported_calls": sum(bool(_reported_models(c)) for c in calls),
            "status": "reported" if reported else "not_reported",
            "limitation": "Requested CLI model is not proof of the backend's resolved model or weights."}}


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "expected JSON object: " + path.name)
    return value


def _combine_call_summaries(summaries: list[dict]) -> dict:
    calls = sum(s["calls"] for s in summaries)
    keys = {k for s in summaries for k in s["usage"]["observed_totals"]}
    counts = {k: sum(s["usage"]["reported_calls"].get(k, 0) for s in summaries) for k in keys}
    observed = {k: sum(s["usage"]["observed_totals"].get(k) or 0 for s in summaries) if counts[k] else None for k in keys}
    latency_count = sum(s["latency_seconds"]["reported_calls"] for s in summaries)
    latency = sum(s["latency_seconds"]["observed_total"] or 0 for s in summaries)
    return {"calls": calls, "usage": {"observed_totals": observed, "reported_calls": counts,
            "complete_totals": {k: v if calls and counts[k] == calls else None for k, v in observed.items()}},
            "latency_seconds": {"reported_calls": latency_count,
                "observed_total": round(latency, 3) if latency_count else None,
                "total": round(latency, 3) if calls and latency_count == calls else None,
                "mean_per_reported_call": latency / latency_count if latency_count else None}}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _decimal(value):
    _require(isinstance(value, str) and value.isascii() and value.isdecimal(), "invalid native decimal counter")
    return int(value)


def runtime_identity(runtime: dict) -> dict:
    """Stable content identities; installation paths are not experimental factors."""
    build = _object(runtime.get("native_build"))
    return {"native_dll": _object(runtime.get("native_dll")).get("sha256"),
            "bridge_lua": _object(runtime.get("bridge_lua")).get("sha256"),
            "codex_cli": _object(runtime.get("codex_cli")).get("sha256"),
            "patch": build.get("patch_sha256"), "source_commit": build.get("source_commit"),
            "native_protocol": build.get("native_protocol"),
            "visual_clock_version": build.get("visual_clock_version"),
            "fixed_step_numerator": build.get("fixed_step_numerator"),
            "fixed_step_denominator": build.get("fixed_step_denominator"),
            "visual_io_version": build.get("visual_io_version")}


def _verify_png_pixels(data: bytes, info: dict) -> None:
    """Check the native RGB(A) raster, including compressed row completeness."""
    offset, compressed, header = 8, bytearray(), None
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        tag, payload = data[offset + 4:offset + 8], data[offset + 8:offset + 8 + length]
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif tag == b"IDAT":
            compressed.extend(payload)
        offset += length + 12
    width, height, depth, color, compression, filtering, interlace = header
    _require(depth == 8 and color in (2, 6) and compression == filtering == interlace == 0,
             "unsupported native PNG pixel format")
    stride = 1 + width * (3 if color == 2 else 4)
    expected = stride * height
    _require(expected <= 128 * 1024 * 1024, "native PNG raster is too large")
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, expected + 1)
    _require(len(raw) == expected and decoder.eof and not decoder.unused_data,
             "PNG raster length or compressed stream mismatch")
    _require(all(raw[row * stride] <= 4 for row in range(height)), "invalid PNG row filter")


def audit_visual_run(directory: str | Path, *, require_terminal: bool = True,
                     verify_live_saves: bool = False) -> dict:
    """Audit immutable saved inputs, response events, dispatch and cleanup evidence.

    Live saves are optional: after another run starts they need not equal an older
    run's originals. Backup hashes and the recorded restoration receipt are always
    required for a final audit. Missing or corrupt artifacts fail closed.
    """
    from visual_agent import (CONTRACT, _visible_hud, audit_codex_events, decision_schema,
                              parse_decision, read_screenshot)
    from visible_hud import extract_visible_hud
    directory = Path(directory).resolve()
    issues, pictures, identities, checked = [], {}, set(), []
    rows, meta, manifest, runtime, report, terminal = [], {}, {}, {}, {}, {}
    instruction_hashes, schema_hashes, manual_hashes, tasks = set(), set(), set(), set()
    clock_versions = set()
    history, memory, prior_after, prior_obs = [], "", None, None

    def problem(scope, error, **extra):
        issues.append({"scope": scope, "error": str(error), **extra})

    def picture(ref):
        _require(isinstance(ref, dict), "missing image reference")
        path = (directory / ref["path"]).resolve()
        _require(path.is_relative_to(directory / "screens"), "image path escaped screens directory")
        if str(path) not in pictures:
            pixels, pictures[str(path)] = read_screenshot(path)
            _verify_png_pixels(pixels, pictures[str(path)])
        info = pictures[str(path)]
        _require(all(ref.get(k) == info[k] for k in ("sha256", "width", "height")), "PNG/reference mismatch")
        return info

    def synchronized(obs, ref):
        visual, caps = obs.get("visual") or {}, obs.get("capabilities") or {}
        _require(obs.get("paused") is True and visual.get("paused") is True, "snapshot is not paused")
        _require(type(visual.get("visual_io_version")) is int
                 and visual["visual_io_version"] == caps.get("visual_io_version") == 1, "missing visual IO version")
        version = visual.get("visual_clock_version")
        _require(type(version) is int and version in (1, 2) and version == caps.get("visual_clock_version"),
                 "unsupported visual clock version")
        clock_versions.add(version)
        _require(len(clock_versions) == 1, "visual clock version changed during run")
        _require(_object(runtime.get("native_build")).get("visual_clock_version") == version,
                 "native clock differs from recorded runtime provenance")
        if version == 2:
            for clock in (visual, caps):
                _require(type(clock.get("fixed_step_numerator")) is int and clock["fixed_step_numerator"] == 1
                         and type(clock.get("fixed_step_denominator")) is int and clock["fixed_step_denominator"] == 60,
                         "fixed simulation step is not 1/60 second")
                _require(_decimal(clock.get("simulated_updates")) == _decimal(clock.get("world_updates"))
                         and clock["simulated_updates"] == clock["world_updates"], "simulated-update counter mismatch")
            for name in ("fixed_step_numerator", "fixed_step_denominator", "simulated_updates"):
                _require(ref.get(name) == visual[name], "native/reference time contract mismatch: " + name)
        _require(caps.get("external_input_guard") is True and visual.get("external_input_detected") is False,
                 "external input detected or guard absent")
        _require(_decimal(caps.get("world_updates")) == _decimal(visual.get("world_updates")), "snapshot/live clock mismatch")
        _require(obs.get("last_action_seq") == visual.get("action_seq"), "observation sequence mismatch")
        for name in ("capture_id", "frame_id", "width", "height", "action_seq", "coordinate_space",
                     "external_input_generation", "visual_clock_version", "world_updates"):
            _require(ref.get(name) == visual.get(name), "native/reference mismatch: " + name)
        return visual

    snapshot = {}
    try:
        data = (directory / "trajectory.jsonl").read_bytes()
        lines = data.splitlines()
        partial = False
        for index, line in enumerate(lines):
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                if not require_terminal and index == len(lines) - 1 and not data.endswith(b"\n"):
                    partial = True
                    continue
                else:
                    raise
            _require(isinstance(row, dict), "trajectory row is not an object")
            rows.append(row)
        snapshot = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "rows": len(rows),
                    "partial_trailing_record_ignored": partial}
        _require(rows and rows[0].get("kind") == "meta", "missing trajectory metadata")
        _require(isinstance(rows[0].get("meta"), dict), "invalid trajectory metadata")
        meta = rows[0]["meta"]
        manifest, runtime = _read(directory / "run.json"), _read(directory / "runtime-fingerprint.json")
        _require(meta.get("observation_mode") in ("image", "hybrid"), "invalid observation mode")
        for key in ("model", "observation_mode", "codex_cli"):
            _require(meta.get(key) == manifest.get(key), "manifest/trajectory mismatch: " + key)
        _require(runtime.get("codex_cli") == meta.get("codex_cli"), "CLI runtime identity mismatch")
        _require((runtime.get("native_build") or {}).get("matches_installed_dll") is True,
                 "installed DLL provenance was not verified")
        identity = runtime_identity(runtime)
        _require(all(value for key, value in identity.items() if key not in ("fixed_step_numerator", "fixed_step_denominator")),
                 "incomplete native/runtime identities")
        if identity["visual_clock_version"] == 2:
            _require(identity["fixed_step_numerator"] == 1 and identity["fixed_step_denominator"] == 60,
                     "fixed-step runtime provenance is missing")
    except Exception as error:
        problem("metadata", error)

    for row in rows:
        kind = row.get("kind")
        if kind == "fixture_setup":
            try:
                _require(prior_obs is None and not checked and not row.get("model") and not row.get("actions"),
                         "fixture setup evidence appeared after actor initialization or contains actor inputs")
                reference = row["visual"]["before"]
                picture(reference)
                synchronized(row["obs"], reference)
                _require(reference == row["visual"]["after"], "fixture setup capture references differ")
            except Exception as error:
                problem("fixture_setup", error)
            continue
        if kind == "reset":
            prior_obs = row.get("obs")
            if row.get("visual"):
                try:
                    prior_after = row["visual"]["before"]
                    picture(prior_after)
                    synchronized(prior_obs, prior_after)
                    _require(prior_after == row["visual"]["after"], "initial capture references differ")
                except Exception as error:
                    problem("initial_capture", error)
        if kind not in ("step", "step_unacknowledged", "model_error", "model_cancelled", "external_interference"):
            if kind not in ("meta", "reset", "end"):
                problem("trajectory", "unsupported record kind: " + str(kind))
            continue
        check = {"record": row.get("i"), "passed": False, "kind": kind}
        try:
            replay, model = row["visual"], row["model"]
            before = replay["before"]
            image = picture(before)
            _require(model.get("frame_id") == before["frame_id"], "actor received wrong frame")
            _require(all(model["image"].get(k) == image[k] for k in ("sha256", "bytes", "width", "height")),
                     "actor attachment differs from archived image")
            _require(model.get("model") == meta.get("model") and model.get("provider") == "codex", "actor model provenance mismatch")
            _require(model.get("reasoning_effort") == meta.get("reasoning_effort"), "actor reasoning effort mismatch")
            declared_prompt_version = meta.get("prompt_version") or _object(meta.get("actor_identity")).get("prompt_version")
            _require(declared_prompt_version is None or model.get("prompt_version") == declared_prompt_version,
                     "actor prompt version mismatch")
            _require(model.get("contract") == CONTRACT and model.get("attempts") == 1, "contract mismatch or hidden model retry")
            _require(model.get("mode") == replay.get("observation_mode") == meta.get("observation_mode"), "mode mismatch")
            prompt = model["prompt"]
            _require(hashlib.sha256(prompt.encode()).hexdigest() == model["prompt_sha256"], "prompt hash mismatch")
            instructions, encoded = prompt.rsplit("\n\nDECISION INPUT\n", 1)
            manual, task = instructions.rsplit("\n\nCURRENT TASK\n", 1)
            _require(hashlib.sha256(manual.encode()).hexdigest() == model["manual_sha256"], "manual hash mismatch")
            instruction_hashes.add(hashlib.sha256(instructions.encode()).hexdigest())
            manual_hashes.add(model["manual_sha256"])
            tasks.add(task)
            expected = {"frame_id": before["frame_id"], "image": {k: image[k] for k in ("sha256", "width", "height")},
                        "mode": meta["observation_mode"], "recent_inputs": history[-8:], "your_memory": memory}
            if meta["observation_mode"] == "hybrid":
                expected["visible_hud"] = _visible_hud(replay["visible_summary"])
                provenance = replay.get("visible_summary_provenance")
                if provenance is not None:
                    _require(provenance.get("image_sha256") == image["sha256"], "HUD reader used wrong image")
                    extracted = extract_visible_hud(directory / before["path"])
                    _require(provenance == extracted["provenance"]
                             and expected["visible_hud"] == {**extracted["values"], "paused": True},
                             "HUD summary or provenance cannot be reproduced from the archived pixels")
            else:
                _require("visible_summary" not in replay, "image mode received HUD")
            _require(json.loads(encoded) == expected, "actor input differs from allowed image/history/memory/HUD")
            _require(model["schema"] == decision_schema(image["width"], image["height"]), "decision schema differs from action contract")
            schema_hashes.add(canonical_sha256(model["schema"]))
            _require(len(instruction_hashes) == len(manual_hashes) == len(schema_hashes) == 1,
                     "instructions or schema changed during run")
            for key, actual in (("instructions_sha256", next(iter(instruction_hashes))),
                                ("schema_sha256", next(iter(schema_hashes))),
                                ("task_sha256", hashlib.sha256(task.encode()).hexdigest()), ("task", task)):
                _require(key not in model or model[key] == actual, "actor identity mismatch: " + key)
                declared = meta.get("actor_identity") or {}
                _require(key not in declared or declared[key] == actual, "declared actor identity mismatch: " + key)
            _require(not meta.get("prompt_sha256") or meta["prompt_sha256"] == model["manual_sha256"], "run manual identity mismatch")
            if kind == "model_error":
                # The recorded failure remains ineligible for comparison even when
                # its input envelope is intact; do not pretend it was a decision.
                check.update(passed=True, response_audited=False)
                checked.append(check)
                continue
            audit = audit_codex_events("\n".join(json.dumps(e) for e in model["events"]))
            _require(model.get("tool_use") is False and model.get("cli_exit_code") == 0, "CLI audit did not succeed")
            _require(model.get("usage") == audit["usage"], "recorded usage differs from native CLI event")
            if "response_model_identity" in model:
                _require(model["response_model_identity"] == audit["response_model_identity"], "reported model evidence mismatch")
            answer = parse_decision(audit["last_message"], image["width"], image["height"])
            _require(answer.intent == (row.get("thought") or ""), "recorded intent differs from response")
            if kind == "model_cancelled":
                _require(row.get("actions") == [] and replay.get("inputs") == []
                         and replay.get("after") is None
                         and _object(replay.get("advance")).get("requested_frames") == 0,
                         "cancelled model result contains dispatched input or after capture")
                _require(before == prior_after and row.get("obs") == prior_obs,
                         "cancelled model capture continuity mismatch")
                ends = [entry for entry in rows if entry.get("kind") == "end"]
                _require(len(ends) == 1 and rows[-1] == ends[0], "cancelled model has no unique terminal")
                end = ends[0]
                evidence = _object(end.get("stop_request"))
                request = _object(evidence.get("request"))
                _require(end.get("status") == "interrupted"
                         and end.get("reason") == "cooperative_stop_requested"
                         and evidence.get("observed_boundary") == "after_actor_before_dispatch"
                         and isinstance(evidence.get("observed_at"), str) and bool(evidence["observed_at"])
                         and request.get("contract") == "visual-cooperative-stop-v1"
                         and all(isinstance(request.get(key), str) and bool(request[key])
                                 for key in ("request_id", "scope", "initiator", "reason", "requested_at"))
                         and type(request.get("requester_pid")) is int and request["requester_pid"] > 0,
                         "cancelled model lacks bound cooperative stop evidence")
            if kind != "step":
                check.update(passed=True, response_audited=True, dispatch_acknowledged=False)
                checked.append(check)
                continue
            after = replay["after"]
            picture(after)
            synchronized(row["pre_obs"], before)
            native = synchronized(row["obs"], after)
            _require(row["pre_obs"] == prior_obs and (prior_after is None or before == prior_after), "capture continuity mismatch")
            _require(after["capture_id"] != before["capture_id"] and after["frame_id"] != before["frame_id"]
                     and after["capture_id"] not in identities, "capture identity reused")
            identities.add(after["capture_id"])
            _require(after["action_seq"] == before["action_seq"] + 1, "action sequence did not advance exactly once")
            _require(before["external_input_generation"] == after["external_input_generation"], "external generation changed")
            actual, requested = native["actual_frames"], native["requested_frames"]
            _require(type(actual) is int and type(requested) is int and 0 <= actual <= requested <= 600, "invalid native frame budget")
            _require(_decimal(after["world_updates"]) - _decimal(before["world_updates"]) == actual, "world counter delta differs from actual frames")
            expected_advance = {"requested_frames": requested, "actual_frames": actual}
            if native["visual_clock_version"] == 2:
                expected_advance.update(visual_clock_version=2, fixed_step_numerator=1,
                                        fixed_step_denominator=60, simulated_seconds=actual / 60)
            _require(replay["advance"] == expected_advance, "replay accounting mismatch")
            _require(answer.actions == row["actions"] and answer.advance_frames == requested, "dispatched actions differ from model response")
            feedback = native["input_feedback"]
            _require(len(feedback) == len(answer.actions), "feedback length mismatch")
            expected_inputs = []
            for index, (action, item) in enumerate(zip(answer.actions, feedback)):
                _require(item.get("index") == index and item.get("type") == action["type"]
                         and item.get("status") in ("delivered", "rejected"), "input feedback mismatch")
                expected_inputs.append({**action, "delivery": item["status"],
                                        **({"reason": item["reason"]} if item.get("reason") else {})})
            _require(replay["inputs"] == expected_inputs, "replay inputs differ from native feedback")
            history.append({"actions": answer.actions, "advance_frames": requested, "actual_advance_frames": actual,
                            "intent": answer.intent, "delivery": "rejected" if any(i["status"] == "rejected" for i in feedback) else "delivered"})
            memory, prior_after, prior_obs = answer.memory, after, row["obs"]
            check.update(passed=True, actual_frames=actual, requested_frames=requested,
                         before_sha256=before["sha256"], after_sha256=after["sha256"], response_audited=True)
        except Exception as error:
            check["error"] = str(error)
            problem("decision", error, record=row.get("i"))
        checked.append(check)

    cleanup = {"complete": False, "live_saves_checked": verify_live_saves}
    if require_terminal:
        try:
            ends = [r for r in rows if r.get("kind") == "end"]
            _require(len(ends) == 1 and rows[-1] == ends[0], "missing unique final terminal record")
            terminal = ends[0]
            report = _read(directory / "visual-report.json")
            for key in ("status", "reason"):
                _require(terminal.get(key) == report.get(key) == manifest.get(key), "terminal/report/manifest mismatch: " + key)
            if terminal.get("reason") == "cooperative_stop_requested":
                _require(terminal.get("stop_request") == report.get("stop_request") == manifest.get("stop_request"),
                         "cooperative stop evidence differs between terminal/report/manifest")
            steps = sum(r.get("kind") == "step" for r in rows)
            _require(terminal.get("decisions") == report.get("decisions") == steps, "completed decision count mismatch")
            _require(manifest.get("status") != "running" and manifest.get("finished_at"), "cleanup not finalized")
            _require(manifest.get("save_restoration") == "verified", "manifest does not verify save restoration")
            backup = _read(directory / "save-backup/manifest.json")
            receipt = _read(directory / "save-backup/restoration.json")
            _require(receipt.get("verified") is True and set(receipt["files"]) == set(backup["files"])
                     and all(v is True for v in receipt["files"].values()), "save restoration receipt incomplete")
            for name, digest in backup["files"].items():
                _require(Path(name).name == name and name.endswith(".sav"), "unsafe save name")
                _require(hashlib.sha256((directory / "save-backup" / name).read_bytes()).hexdigest() == digest, "save backup hash mismatch")
                if verify_live_saves:
                    _require(hashlib.sha256((Path(backup["save_directory"]) / name).read_bytes()).hexdigest() == digest,
                             "restored live save differs; use historical receipt after later runs")
            cleanup.update(complete=True, restored_files=len(backup["files"]))
        except Exception as error:
            problem("terminal_cleanup", error)
    return {"audit_version": "visual-run-audit-v1", "run_id": directory.name,
            "status": "failed" if issues else "passed" if cleanup["complete"] else "provisional",
            "complete": cleanup["complete"] and not issues, "issues": issues,
            "checked_decisions": len(checked), "checked_unique_pngs": len(pictures), "decisions": checked,
            "trajectory_snapshot": snapshot, "terminal_cleanup": cleanup,
            "runtime_identity": runtime_identity(runtime), "instruction_sha256": sorted(instruction_hashes),
            "simulation_timing": {"clock_versions": sorted(clock_versions),
                "fixed_step_verified": clock_versions == {2},
                "classification": "fixed_step_1_over_60_second" if clock_versions == {2}
                    else "historical_update_count_without_fixed_duration" if clock_versions == {1} else "unavailable",
                "declared_elapsed_seconds": {"numerator": prior_after["simulated_updates"], "denominator": 60}
                    if clock_versions == {2} and prior_after is not None else None},
            "manual_sha256": sorted(manual_hashes), "schema_sha256": sorted(schema_hashes), "tasks": sorted(tasks),
            "model_calls": summarize_model_calls(rows),
            "outcome_category": outcome_category(terminal.get("reason"), terminal.get("status")),
            "limitations": ["Audits recorded event objects; original CLI stdout and staged attachments are not retained.",
                            "Pixel identity does not establish UI fidelity; independent native acceptance is required.",
                            "Historical save restoration relies on the recorded receipt and original backup hashes."]}


def aggregate_visual_runs(directories, protocol: dict | None = None, *, admission_issues=None) -> dict:
    """Compare only intact paired challenge trials under one frozen protocol.

    Game losses and budget stops remain outcomes. Technical failures are reported
    separately and never converted into a zero score or successful gameplay trial.
    """
    trials, groups, pairs = [], defaultdict(list), defaultdict(list)
    protocol = protocol or {}
    frozen_protocol = {k: v for k, v in protocol.items() if k != "protocol_sha256"}
    protocol_intact = bool(protocol) and canonical_sha256(frozen_protocol) == protocol.get("protocol_sha256")
    for supplied in directories:
        directory = Path(supplied)
        audit = audit_visual_run(directory)
        problems = list((admission_issues or {}).get(str(directory), []))
        try:
            manifest, report = _read(directory / "run.json"), _read(directory / "visual-report.json")
            experiment = report.get("experiment") or manifest.get("experiment") or {}
            validated_success = False
            identity = {key: experiment.get(key) for key in ("protocol", "scenario", "seed", "task_version", "task_sha256",
                        "fixture_sha256", "fixture_version", "budgets", "protocol_sha256", "hud_extractor_identity",
                        "initial_gameplay_sha256")}
            identity.update(runtime=audit["runtime_identity"], manual=audit["manual_sha256"],
                            instructions=audit["instruction_sha256"], schema=audit["schema_sha256"],
                            reasoning_effort=manifest.get("reasoning_effort"))
            required = ("protocol", "scenario", "seed", "task_sha256", "fixture_sha256", "fixture_version", "budgets",
                        "initial_gameplay_sha256")
            if any(identity.get(k) is None for k in required):
                problems.append("missing_frozen_experiment_identity")
            if not audit["complete"]:
                problems.append("protocol_or_cleanup_audit_failed")
            if audit["runtime_identity"]["visual_clock_version"] != 2 or not audit["simulation_timing"]["fixed_step_verified"]:
                problems.append("fixed_step_visual_clock_v2_required")
            category = outcome_category(report.get("reason"), report.get("status"))
            if category not in {"task_success", "game_victory", "game_loss", "budget_exhausted"}:
                problems.append("non_gameplay_outcome:" + category)
            if experiment.get("prerequisites_verified") is not True:
                problems.append("challenge_prerequisites_not_verified")
            try:
                actor_start = _read(directory / "actor-start.json")
                rows = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
                reset = next(row for row in rows if row.get("kind") == "reset")
                _require(actor_start.get("canonical_actor_reset") is True
                         and actor_start.get("initial_observation") == reset.get("obs")
                         and actor_start.get("first_image") == (reset.get("visual") or {}).get("before"),
                         "actor-start differs from canonical first decision snapshot")
                signature = actor_start["gameplay_signature"]
                digest = hashlib.sha256(json.dumps(signature, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                _require(digest == actor_start.get("gameplay_signature_sha256") == identity["initial_gameplay_sha256"],
                         "initial gameplay signature identity mismatch")
                raw = reset["obs"]
                for field, value in signature.items():
                    if field == "player_ship":
                        _require(all((raw.get("player_ship") or {}).get(k) == v for k, v in value.items()),
                                 "initial ship signature differs from native snapshot")
                    elif field == "navigation":
                        _require((raw.get("economy") or {}).get("navigation", {}) == value,
                                 "initial navigation signature differs from native snapshot")
                    elif field == "native_system_health":
                        _require(raw.get("visual_challenge_system_health") == value,
                                 "initial native system health differs from native snapshot")
                    elif field == "visual_time_contract":
                        _require({key: _object(raw.get("visual")).get(key) for key in
                                  ("visual_clock_version", "fixed_step_numerator", "fixed_step_denominator")} == value,
                                 "initial visual time contract differs from native snapshot")
                    elif field == "initial_rng_seed":
                        _require(_object(raw.get("visual_challenge_fixture")).get("initial_rng_seed") == value,
                                 "initial fixture RNG seed differs from native snapshot")
                    else:
                        _require(raw.get(field) == value, "initial signature differs from native snapshot: " + field)
                proof = actor_start.get("setup_proof") or {}
                _require(proof.get("passed") is True and proof.get("checks")
                         and all(v is True for v in proof["checks"].values()), "challenge prerequisites lack complete proof")
                validation = _read(directory / "validation.json")
                _require(validation.get("protocol") == experiment.get("protocol")
                         and validation.get("challenge") == experiment.get("scenario")
                         and validation.get("repetition") == experiment.get("repetition"),
                         "native challenge validation has a different trial identity")
                _require(validation.get("termination") == report.get("reason")
                         and validation.get("setup") == proof, "challenge validation disagrees with lifecycle or setup")
                _require(validation.get("save_restoration_verified") is True
                         and validation.get("production_source_unchanged") is True
                         and validation.get("cli_image_decisions_audited") is True
                         and validation.get("error") is None and validation.get("failure_type") is None,
                         "challenge validation records technical failure or incomplete cleanup")
                goal = _object(validation.get("outcome"))
                checks = _object(goal.get("checks"))
                _require(bool(checks) and all(type(v) is bool for v in checks.values())
                         and type(goal.get("achieved")) is bool
                         and goal["achieved"] == all(checks.values()), "native goal proof is incomplete or inconsistent")
                validated_success = goal["achieved"]
                _require(report.get("reason") != "fixture_goal_observed" or validated_success,
                         "challenge success lacks a positive native goal proof")
                _require(not validated_success or report.get("reason") in ("fixture_goal_observed", "native_victory"),
                         "positive native goal proof disagrees with termination")
            except Exception as error:
                problems.append("challenge_evidence:" + str(error))
            if report.get("experiment_sha256") != canonical_sha256(experiment):
                problems.append("experiment_identity_hash_mismatch")
            if manifest.get("experiment") != experiment:
                problems.append("manifest_experiment_mismatch")
            if experiment.get("budgets") != report.get("budgets"):
                problems.append("budget_mismatch")
            if audit["tasks"] != [experiment.get("task")]:
                problems.append("actor_task_mismatch")
            if experiment.get("task_sha256") != hashlib.sha256(str(experiment.get("task", "")).encode()).hexdigest():
                problems.append("task_hash_mismatch")
            if protocol:
                if "tasks" in protocol or "task_versions" in protocol:
                    try:
                        versions, task_map = protocol.get("task_versions"), protocol.get("tasks")
                        challenges = protocol.get("challenges")
                        _require(isinstance(challenges, list) and bool(challenges)
                                 and isinstance(versions, dict) and isinstance(task_map, dict)
                                 and set(versions) == set(task_map) == set(challenges),
                                 "prospective task maps are incomplete")
                        for challenge in challenges:
                            frozen_task = _object(task_map[challenge])
                            _require(isinstance(versions[challenge], str) and bool(versions[challenge])
                                     and frozen_task.get("task_version") == versions[challenge]
                                     and isinstance(frozen_task.get("task"), str) and bool(frozen_task["task"])
                                     and frozen_task.get("task_sha256") == hashlib.sha256(frozen_task["task"].encode()).hexdigest(),
                                     "prospective frozen task identity is malformed")
                        scenario = experiment.get("scenario")
                        frozen_task = task_map[scenario]
                        version = versions[scenario]
                        trajectory_meta = next(row["meta"] for row in rows if row.get("kind") == "meta")
                        _require(manifest.get("task_version") == experiment.get("task_version")
                                 == _object(manifest.get("actor_identity")).get("task_version")
                                 == trajectory_meta.get("task_version") == version,
                                 "prospective task versions disagree")
                        _require(all(experiment.get(key) == frozen_task.get(key)
                                     for key in ("task", "task_sha256", "task_version")),
                                 "prospective trial differs from frozen task")
                    except Exception as error:
                        problems.append("task_version:" + str(error))
                if not protocol_intact:
                    problems.append("frozen_protocol_hash_mismatch")
                if experiment.get("protocol_sha256") != protocol.get("protocol_sha256"):
                    problems.append("different_frozen_protocol")
                if identity["hud_extractor_identity"] != protocol.get("hud_extractor_identity"):
                    problems.append("different_hud_extractor_identity")
                if manifest.get("reasoning_effort") != protocol.get("reasoning_effort"):
                    problems.append("different_reasoning_effort")
                if experiment.get("seed") != protocol.get("seed", experiment.get("seed")):
                    problems.append("different_seed")
                if experiment.get("budgets") != protocol.get("budgets", experiment.get("budgets")):
                    problems.append("different_frozen_budgets")
                if experiment.get("runtime_identity") is not None and runtime_identity(experiment["runtime_identity"]) != audit["runtime_identity"]:
                    problems.append("experiment_runtime_mismatch")
                try:
                    acceptance = protocol["native_acceptance"]
                    accepted = acceptance["runtime"]
                    _require(bool(acceptance["receipts"]), "native acceptance receipts missing")
                    for receipt, digest in acceptance["receipts"].items():
                        _require(protocol.get("source_files", {}).get(receipt) == digest,
                                 "native receipt was not frozen with sources")
                    _require(accepted["dll_sha256"] == audit["runtime_identity"]["native_dll"]
                             and accepted["patch_sha256"] == audit["runtime_identity"]["patch"],
                             "accepted DLL or patch differs from trial")
                    _require(accepted.get("visual_clock_version") == 2
                             and accepted.get("fixed_step_numerator") == 1 and accepted.get("fixed_step_denominator") == 60,
                             "native acceptance does not establish fixed-step clock v2")
                    production = (directory / "production-bridge.lua").read_bytes()
                    fixture = (directory / "fixture-bridge.lua").read_bytes()
                    _require(hashlib.sha256(production).hexdigest() == accepted["production_bridge_sha256"]
                             == manifest.get("production_bridge_sha256") and fixture.startswith(production),
                             "fixture did not append to accepted production bridge bytes")
                    _require(hashlib.sha256(fixture).hexdigest() == experiment["fixture_sha256"]
                             == audit["runtime_identity"]["bridge_lua"], "installed fixture bridge identity mismatch")
                except Exception as error:
                    problems.append("native_acceptance:" + str(error))
            key = canonical_sha256(identity)
            condition = (manifest.get("model"), manifest.get("observation_mode"))
            repetition = experiment.get("repetition")
            if type(repetition) is not int or repetition < 1:
                problems.append("invalid_repetition")
            trial = {"directory": str(directory), "scenario": experiment.get("scenario"),
                     "model": condition[0], "mode": condition[1], "repetition": repetition,
                     "identity_sha256": key, "identity": identity, "status": report.get("status"),
                     "reason": report.get("reason"), "outcome_category": category,
                     "task_success": validated_success,
                     "eligible": not problems, "exclusions": problems, "audit": audit,
                     "decisions": report.get("decisions"), "elapsed_seconds": report.get("elapsed_seconds"),
                     "model_calls": audit["model_calls"]}
            trials.append(trial)
            groups[(experiment.get("scenario"), *condition)].append(trial)
            pairs[(experiment.get("scenario"), repetition)].append(trial)
        except Exception as error:
            trials.append({"directory": str(directory), "eligible": False,
                           "exclusions": ["unreadable_run:" + str(error)], "audit": audit})
    conditions = {(model, mode) for model in protocol.get("models", []) for mode in protocol.get("modes", [])}
    if not conditions:
        conditions = {(t.get("model"), t.get("mode")) for t in trials if t.get("model") and t.get("mode")}
    paired = []
    expected_pairs = {(s, r) for s in protocol.get("challenges", [])
                      for r in range(1, protocol.get("repetitions", 0) + 1)} or set(pairs)
    for scenario, repetition in sorted(expected_pairs):
        members = pairs.get((scenario, repetition), [])
        counts = Counter((t["model"], t["mode"]) for t in members)
        reasons = []
        if set(counts) != conditions or any(n != 1 for n in counts.values()):
            reasons.append("missing_or_duplicate_conditions")
        if any(not t["eligible"] for t in members):
            reasons.append("ineligible_trial")
        if len({t["identity_sha256"] for t in members}) != 1:
            reasons.append("unmatched_trial_identity")
        paired.append({"scenario": scenario, "repetition": repetition, "qualified": not reasons,
                       "exclusions": reasons})
    summaries = []
    matched_pairs = {(p["scenario"], p["repetition"]) for p in paired if p["qualified"]}
    for (scenario, model, mode), members in sorted(groups.items()):
        valid = [t for t in members if t["eligible"]]
        paired_members = [t for t in valid if (scenario, t["repetition"]) in matched_pairs]
        counts = Counter(t["outcome_category"] for t in valid)
        summaries.append({"scenario": scenario, "model": model, "mode": mode, "attempts": len(members),
                          "eligible_trials": len(valid), "excluded_trials": len(members) - len(valid),
                          "outcomes": dict(counts),
                          "model_calls_all_attempts": _combine_call_summaries([t["model_calls"] for t in members]),
                          "matched_pair_trials": len(paired_members),
                          "paired_task_success_rate": sum(t["task_success"] for t in paired_members) / len(paired_members)
                              if paired_members else None,
                          "task_success_rate": sum(t["task_success"] for t in valid) / len(valid) if valid else None})
    qualified = bool(protocol_intact and paired and trials) and all(p["qualified"] for p in paired)
    qualified = qualified and set(pairs) == expected_pairs
    return {"report_version": "visual-comparison-v1", "scope": "paired_diagnostic_challenges",
            "valid_for_full_game_comparison": False, "qualified_scoped_comparison": qualified,
            "protocol_sha256": protocol.get("protocol_sha256"), "trials": trials,
            "conditions": summaries, "pairs": paired,
            "limitations": ["Seed repeats measure repeatability of these fixtures, not a population ranking.",
                            "Challenge outcomes are not full-game scores; technical failures remain separate.",
                            "Requested model identifiers do not establish resolved backend weights."]}
