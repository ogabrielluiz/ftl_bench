"""Run the separately versioned visual benchmark with Codex CLI and protected saves."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from uuid import uuid4

from ftl_bench.installation import runtime_fingerprint
from ftl_bench.fullgame_setup import FullGameSetupSession
from ftl_bench.protected_game import ProtectedGame
from ftl_bench.scoring import achieved_metrics
from ftl_bench.scenario import Scenario, SubObjective
from ftl_bench.session import ftl_user_folder
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory
from ftl_bench.visual_session import (ExternalInputInterference, VisualFrame, VisualSession, validate_visual_clock,
                                      VISUAL_CLOCK_VERSION, FIXED_STEP_NUMERATOR, FIXED_STEP_DENOMINATOR)
from visual_agent import CodexVisualAgent, VisualObservation, VisualProtocolError, VisualBackendError, _codex_executable
from visible_hud import extract_visible_hud, extractor_identity
from visual_cancellation import StopControl, CooperativeStop
from visual_reporting import canonical_sha256, outcome_category, summarize_model_calls


ROOT = Path(__file__).resolve().parent.parent
TRACK = "visual-v1"


def codex_runtime_identity(explicit: str | Path | None = None) -> dict:
    """Resolve and hash the pinned CLI once per run, without executing it."""
    executable = Path(_codex_executable(explicit))
    with executable.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"path": str(executable), "sha256": digest, "bytes": executable.stat().st_size}


def save_restoration_status(backup: Path) -> str:
    try:
        receipt = json.loads((backup / "restoration.json").read_text(encoding="utf-8"))
        if isinstance(receipt, dict) and receipt.get("verified") is True:
            return "verified"
    except (OSError, ValueError):
        pass
    return "see_save_backup_receipt"


def verify_visual_setup(frame: VisualFrame, seed: int) -> dict:
    """Verify the real start and evaluator signals without semantic controls."""
    obs = frame.observation
    raw = obs.raw or {}
    actual = {"seed": obs.seed, "blueprint": (obs.player_ship or {}).get("blueprint"),
              "difficulty": raw.get("difficulty")}
    if (obs.game_started is not True or type(actual["seed"]) is not int or type(actual["difficulty"]) is not int
            or actual != {"seed": seed, "blueprint": "PLAYER_SHIP_HARD", "difficulty": 0}):
        raise RuntimeError(f"Cannot verify seeded Kestrel A/easy setup; observed {actual}")
    capabilities = raw.get("capabilities") or {}
    if any(capabilities.get(name) is not True for name in ("live_score", "victory", "external_input_guard")):
        raise RuntimeError("Native live-score, victory, and external-input guard capabilities are required")
    validate_visual_clock(obs, synchronized=True)
    score, protocol = raw.get("ftl_score"), capabilities.get("native_protocol")
    if (type(protocol) is not int or protocol < 5 or type(raw.get("victory")) is not bool
            or type(score) not in (int, float) or not math.isfinite(score) or score < 0):
        raise RuntimeError("Native score, victory, or protocol evidence is unavailable")
    return {**actual, "live_score": True, "victory": True, "native_protocol": protocol,
            "external_input_guard": True, "visual_clock_version": VISUAL_CLOCK_VERSION,
            "fixed_step_numerator": FIXED_STEP_NUMERATOR, "fixed_step_denominator": FIXED_STEP_DENOMINATOR,
            "simulated_updates": raw["visual"]["simulated_updates"], "world_updates": raw["visual"]["world_updates"]}


def visible_hud(frame: VisualFrame) -> dict:
    return {**extract_visible_hud(frame.image_path)["values"], "paused": True}


def evaluator_outcome(before: VisualFrame, after: VisualFrame) -> dict:
    previous, current = before.observation, after.observation
    messages = []
    for name in ("fuel", "scrap", "missiles", "drone_parts"):
        old = ((previous.player_ship or {}).get("resources") or {}).get(name)
        new = ((current.player_ship or {}).get("resources") or {}).get(name)
        if type(old) is int and type(new) is int and old != new:
            messages.append(f"{name}: {old} → {new}")
    if ((previous.map or {}).get("current_pos") != (current.map or {}).get("current_pos")
            or (previous.map or {}).get("sector") != (current.map or {}).get("sector")):
        messages.append("Native location changed")
    if (current.raw or {}).get("victory") is True:
        messages.append("Native victory")
    elif current.game_over:
        messages.append("Native game over")
    return {"status": "observed" if messages else "unknown",
            "summary": "; ".join(messages) if messages else "No evaluated gameplay change; inspect the images."}


def advance_evidence(native: dict, requested: int, actual: int | None) -> dict:
    evidence = {"requested_frames": requested, "actual_frames": actual}
    if (native.get("visual_clock_version") == VISUAL_CLOCK_VERSION
            and native.get("fixed_step_numerator") == FIXED_STEP_NUMERATOR
            and native.get("fixed_step_denominator") == FIXED_STEP_DENOMINATOR):
        evidence.update(visual_clock_version=VISUAL_CLOCK_VERSION,
                        fixed_step_numerator=FIXED_STEP_NUMERATOR, fixed_step_denominator=FIXED_STEP_DENOMINATOR,
                        simulated_seconds=actual / FIXED_STEP_DENOMINATOR if type(actual) is int else None)
    return evidence


def visual_record(mode: str, before: VisualFrame, after: VisualFrame | None,
                  actions: list[dict], requested: int, *, hud: dict | None = None,
                  hud_provenance: dict | None = None) -> dict:
    native = (after.observation.raw or {}).get("visual", {}) if after else {}
    feedback = native.get("input_feedback", [])
    inputs = []
    for index, action in enumerate(actions):
        item = {**action}
        ack = feedback[index] if index < len(feedback) else {}
        # Missing acknowledgement is unknown, never retried as an assumed no-op.
        item["delivery"] = ack.get("status", "unknown")
        if ack.get("reason"):
            item["reason"] = ack["reason"]
        inputs.append(item)
    return {"observation_mode": mode, "before": before.reference,
            "after": after.reference if after else None, "inputs": inputs,
            "advance": advance_evidence(native, requested, native.get("actual_frames")),
            "outcome": evaluator_outcome(before, after) if after else
                       {"status": "unknown", "summary": "No synchronized after-image was received."},
            **({"visible_summary": hud if hud is not None else visible_hud(before),
                "visible_summary_provenance": hud_provenance} if mode == "hybrid" else {})}


def visual_report_metrics(records: list[dict]) -> tuple[dict, dict[str, str]]:
    """Keep unavailable visual counters distinct from observed zero values."""
    observations = []
    for row in records:
        if row.get("kind") in ("reset", "reset_episode", "start_game"):
            observations = []
        obs = row.get("obs")
        if isinstance(obs, dict) and obs.get("game_started") is True:
            observations.append(obs)
    if not observations:
        metrics = {key: None for key in achieved_metrics([])}
        return metrics, {key: "no_recorded_game_observations" for key in metrics}
    metrics = achieved_metrics(records)
    # The existing counter counts structured choose_event actions. Visual clicks
    # and keys cannot establish an event count, and there is no native count field.
    metrics["events"] = None
    unavailable = {"events": "native_event_count_unavailable_for_visual_actions"}
    phases = []
    for obs in observations:
        flagship = obs.get("flagship")
        value = flagship.get("phases_completed") if isinstance(flagship, dict) else None
        if type(value) is int and 0 <= value <= 3:
            phases.append(value)
    if any(obs.get("victory") is True for obs in observations):
        metrics["flagship_phases_completed"] = 3
    elif phases:
        metrics["flagship_phases_completed"] = max(phases)
    else:
        metrics["flagship_phases_completed"] = None
        unavailable["flagship_phases_completed"] = "native_flagship_phase_count_unavailable"
    return metrics, unavailable


def run_loop(transport: VisualSession, agent: CodexVisualAgent, recorder: TrajectoryRecorder,
             *, mode: str = "image", max_decisions: int = 300,
             max_wall_seconds: float = 14400, max_idle_decisions: int = 8,
             stop_when=None, expected_seed: int | None = None,
             experiment: dict | None = None, stop_reason: str = "fixture_goal_observed",
             initial_frame_validator=None, stop_control=None) -> dict:
    """Evaluator callbacks stay outside actor input; validators must raise to reject.
    Initial admission runs after the canonical reset record and before actor calls.
    """
    if type(max_idle_decisions) is not int or max_idle_decisions < 1:
        raise ValueError("max_idle_decisions must be a positive integer")
    # Freeze a caller-owned mapping before any actor call or stopping callback.
    experiment = json.loads(json.dumps(experiment, allow_nan=False)) if experiment is not None else None
    stop_control = stop_control or StopControl()
    start = time.monotonic()
    history, memory = [], ""
    completed = 0
    idle_decisions = 0
    budgets = {"decisions": max_decisions, "wall_seconds": max_wall_seconds,
               "idle_decisions": max_idle_decisions}
    reason = "decision_budget"
    try:
        stop_control.check("before_capture")
        frame = transport.capture()
        initial = frame
        recorder.record("reset", [], frame.observation, visual={
            "observation_mode": mode, "before": frame.reference, "after": frame.reference,
            "inputs": [], "advance": advance_evidence((frame.observation.raw or {}).get("visual") or {}, 0, 0),
            "outcome": {"status": "unknown", "summary": "Initial paused decision screenshot"}})
        if initial_frame_validator is not None:
            initial_frame_validator(frame)
        if expected_seed is not None:
            setup = verify_visual_setup(frame, expected_seed)
            (recorder.path.parent / "setup-verification.json").write_text(json.dumps(setup, indent=2), encoding="utf-8")
        while completed < max_decisions:
            stop_control.check("before_actor")
            if frame.observation.game_over or (frame.observation.raw or {}).get("victory") is True:
                reason = "native_victory" if (frame.observation.raw or {}).get("victory") else "native_game_over"
                break
            if stop_when is not None and stop_when(initial, frame):
                reason = stop_reason
                break
            if idle_decisions >= max_idle_decisions:
                reason = "idle_decision_budget"
                break
            if time.monotonic() - start >= max_wall_seconds:
                reason = "wall_clock_budget"
                break
            hud, hud_provenance = {}, None
            if mode == "hybrid":
                extraction = extract_visible_hud(frame.image_path)
                hud = {**extraction["values"], "paused": True}
                hud_provenance = extraction["provenance"]
                if hud_provenance.get("image_sha256") != frame.reference["sha256"]:
                    raise RuntimeError("Visible HUD reader image differs from the archived decision image")
            observation = VisualObservation(frame.image_path, frame.reference["frame_id"], mode=mode,
                                            visible_hud=hud,
                                            history=history[-8:], memory=memory)
            try:
                decision = agent.decide(observation)
            except (VisualProtocolError, VisualBackendError) as error:
                recorder.record("model_error", [], frame.observation, model=error.metadata,
                                visual=visual_record(mode, frame, None, [], 0, hud=hud, hud_provenance=hud_provenance))
                stop_control.check("after_actor_error")
                raise
            if stop_control.pending():
                recorder.record("model_cancelled", [], frame.observation, model=decision.metadata,
                                thought=decision.intent, visual=visual_record(mode, frame, None, [], 0,
                                    hud=hud, hud_provenance=hud_provenance))
                stop_control.check("after_actor_before_dispatch")
            after, interference = None, None
            try:
                after = transport.step(frame, decision.actions, decision.advance_frames)
            except ExternalInputInterference as error:
                interference = error
                replay = visual_record(mode, frame, None,
                    decision.actions if error.dispatched else [], decision.advance_frames,
                    hud=hud, hud_provenance=hud_provenance)
                replay["external_input_guard"] = error.evidence
                replay["planned_inputs"] = decision.actions
                replay["outcome"] = {"status": "unknown", "summary":
                    "External input interrupted the trial after packet dispatch; inspect native rejection evidence."
                    if error.dispatched else "External input interrupted the trial before dispatch; no planned inputs were sent."}
                recorder.record("external_interference", decision.actions if error.dispatched else [],
                                error.observation, thought=decision.intent, model=decision.metadata,
                                pre_obs=frame.observation, visual=replay)
                raise
            finally:
                if interference is None:
                    recorder.record("step" if after else "step_unacknowledged", decision.actions,
                                    after.observation if after else None, thought=decision.intent,
                                    model=decision.metadata, pre_obs=frame.observation,
                                    visual=visual_record(mode, frame, after, decision.actions, decision.advance_frames,
                                                         hud=hud, hud_provenance=hud_provenance))
            native = after.observation.raw["visual"]
            feedback = native["input_feedback"]
            delivery = "rejected" if any(i["status"] == "rejected" for i in feedback) else "delivered"
            history.append({"actions": decision.actions, "advance_frames": decision.advance_frames,
                            "actual_advance_frames": native["actual_frames"], "intent": decision.intent,
                            "delivery": delivery})
            history = history[-8:]
            frame, memory = after, decision.memory
            completed += 1
            stop_control.check("after_action_acknowledgement")
            idle_decisions = idle_decisions + 1 if decision.actions == [] and decision.advance_frames == 0 else 0
            print(json.dumps({"decision": completed, "intent": decision.intent,
                              "latency_seconds": decision.metadata.get("latency_seconds"),
                              "frames": native["actual_frames"], "delivery": delivery}), flush=True)
        else:
            if frame.observation.game_over or (frame.observation.raw or {}).get("victory") is True:
                reason = "native_victory" if (frame.observation.raw or {}).get("victory") else "native_game_over"
            elif stop_when is not None and stop_when(initial, frame):
                reason = stop_reason
            elif idle_decisions >= max_idle_decisions:
                reason = "idle_decision_budget"
        recorder.finish(status="completed", reason=reason, decisions=completed,
                        budgets=budgets, consecutive_idle_decisions=idle_decisions)
    except BaseException as error:
        recorder.finish(status="interrupted" if isinstance(error, (KeyboardInterrupt, ExternalInputInterference)) else "error",
                        reason="cooperative_stop_requested" if isinstance(error, CooperativeStop) else
                               "user_interrupted" if isinstance(error, KeyboardInterrupt) else
                               "external_interference" if isinstance(error, ExternalInputInterference) else
                               "visual_backend_error" if isinstance(error, VisualBackendError) else
                               "visual_model_error" if isinstance(error, VisualProtocolError) else "visual_infrastructure_error",
                        error=str(error), decisions=completed, budgets=budgets,
                        **({"stop_request": error.evidence} if isinstance(error, CooperativeStop) else {}),
                        consecutive_idle_decisions=idle_decisions,
                        **({"external_input_guard": error.evidence} if isinstance(error, ExternalInputInterference) else {}))
        raise
    finally:
        records = load_trajectory(recorder.path)
        terminal = next((r for r in reversed(records) if r.get("kind") == "end"), {})
        game_observations = sum(isinstance(r.get("obs"), dict) and r["obs"].get("game_started") is True
                                for r in records)
        metrics, unavailable = visual_report_metrics(records)
        report = {"track": TRACK, "observation_mode": mode, "classification": "diagnostic_only",
                  "valid_for_model_comparison": False,
                  "comparison_exclusion_reason": "external_interference" if terminal.get("reason") == "external_interference"
                                                   else "visual_control_validation_in_progress",
                  "status": terminal.get("status"), "reason": terminal.get("reason"),
                  "stop_request": terminal.get("stop_request"),
                  "outcome_category": outcome_category(terminal.get("reason"), terminal.get("status")),
                  "model_calls": summarize_model_calls(records),
                  "experiment": experiment,
                  "experiment_sha256": canonical_sha256(experiment) if experiment is not None else None,
                  "decisions": completed, "elapsed_seconds": round(time.monotonic() - start, 3),
                  "budgets": budgets, "consecutive_idle_decisions": idle_decisions,
                  "recorded_game_observations": game_observations,
                  "metrics_status": "partially_available" if game_observations else "unavailable_no_observations",
                  "metric_unavailable_reasons": unavailable,
                  "metrics": metrics}
        (recorder.path.parent / "visual-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--mode", choices=("image", "hybrid"), default="image")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--stop-after-sector", type=int,
                        help="Stop when native map.sector reaches this positive target; separate from a full-game trial")
    parser.add_argument("--max-decisions", type=int, default=300)
    parser.add_argument("--max-idle-decisions", type=int, default=8,
                        help="Stop after this many consecutive empty, zero-frame decisions (default: 8)")
    parser.add_argument("--max-wall-seconds", type=float, default=14400)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--stop-scope")
    args = parser.parse_args(argv)
    if args.stop_scope is not None and args.stop_file is None:
        parser.error("--stop-scope requires --stop-file")
    control = StopControl(args.stop_file, args.stop_scope)
    if (args.max_decisions < 1 or args.max_idle_decisions < 1
            or not math.isfinite(args.max_wall_seconds) or args.max_wall_seconds < 1):
        parser.error("Budgets must be finite and positive")
    if not 0 <= args.seed <= 0xFFFFFFFF:
        parser.error("Seed must be an unsigned 32-bit integer")
    if args.stop_after_sector is not None and args.stop_after_sector < 1:
        parser.error("--stop-after-sector must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    client = codex_runtime_identity()
    directory = (args.output or ROOT / "harness/runs/visual" / stamp).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    agent = CodexVisualAgent(model=args.model, reasoning_effort=args.reasoning_effort, codex_bin=client["path"])
    actor_identity = agent.instruction_identity()
    bridge = ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
    protected = ProtectedGame(ftl_user_folder(), directory / "save-backup", bridge)
    scenario = Scenario(id=f"VISUAL-s{args.seed}" + (f"-sector-{args.stop_after_sector}" if args.stop_after_sector else ""),
                        type="reach_sector" if args.stop_after_sector else "full_run", seed=args.seed,
                        goal=[SubObjective("sector", args.stop_after_sector)] if args.stop_after_sector else
                             [SubObjective("victory", 1, kind="boolean")], budget_jumps=40)
    meta = {"track": TRACK, "observation_mode": args.mode, "model": args.model,
            "agent": f"codex-{args.model}-{TRACK}", "run_id": directory.name,
            "scenario_id": scenario.id, "scenario": scenario.to_dict(),
            "provider": "codex", "reasoning_effort": args.reasoning_effort,
            "codex_cli": client,
            "seed": args.seed, "classification": "diagnostic_only",
            "valid_for_model_comparison": False, "started_at": datetime.now(timezone.utc).isoformat(),
            "budgets": {"decisions": args.max_decisions, "wall_seconds": args.max_wall_seconds,
                        "idle_decisions": args.max_idle_decisions},
            "prompt_sha256": actor_identity["manual_sha256"], "prompt_version": actor_identity["prompt_version"],
            "hybrid_hud": extractor_identity(), "actor_identity": actor_identity,
            "trial_scope": "sector_progress" if args.stop_after_sector else "full_game",
            "stop_after_sector": args.stop_after_sector,
            "startup_contract": "fresh-start-seed-v3", "fixture_free_startup": True}
    meta["external_input_guard_required"] = True
    meta.update(visual_clock_version=VISUAL_CLOCK_VERSION,
                fixed_step_numerator=FIXED_STEP_NUMERATOR, fixed_step_denominator=FIXED_STEP_DENOMINATOR)
    recorder = TrajectoryRecorder(directory / "trajectory.jsonl", meta)
    manifest = {**meta, "started_at": time.time(), "status": "running", "scenario_ids": [scenario.id],
                "validation_status": "diagnostic_only",
                "validation_limitations": ["Visual control acceptance matrix is incomplete."]}

    def write_manifest(**updates):
        manifest.update(updates)
        (directory / "run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    write_manifest()
    execution_error = None
    try:
        control.check("before_protected_startup")
        with protected.protected(), control.record_on_stop(recorder):
            control.check("before_game_launch")
            protected.launch()
            control.check("after_game_launch")
            fingerprint = runtime_fingerprint(ROOT)
            fingerprint["codex_cli"] = client
            (directory / "runtime-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
            if not (fingerprint.get("native_build") or {}).get("matches_installed_dll"):
                raise RuntimeError("Installed native DLL does not match its build provenance")
            native_build = fingerprint["native_build"]
            if (native_build.get("fresh_start_seed") is not True
                    or type(native_build.get("fresh_seed_contract_version")) is not int
                    or native_build["fresh_seed_contract_version"] != 3
                    or native_build.get("fresh_seed_contract") != "fresh-start-seed-v3"):
                raise RuntimeError("Visual trials require installed fresh-start seed contract v3")
            session = FullGameSetupSession(ftl_user_folder(), setup_output=directory / "fresh-setup",
                                           seed=args.seed, step_timeout=20)
            control.check("before_seed_setup")
            session.reset_episode(seed=args.seed)
            session.reset()
            control.check("after_seed_setup")
            try:
                report = run_loop(VisualSession(session, directory), agent, recorder, mode=args.mode,
                                  max_decisions=args.max_decisions, max_wall_seconds=args.max_wall_seconds,
                                  max_idle_decisions=args.max_idle_decisions, expected_seed=args.seed,
                                  initial_frame_validator=session.verify_first_capture, stop_control=control,
                                  **({"stop_when": lambda initial, frame:
                                      type((frame.observation.map or {}).get("sector")) is int
                                      and frame.observation.map["sector"] >= args.stop_after_sector,
                                      "stop_reason": "sector_target_observed"} if args.stop_after_sector else {}))
            except BaseException as error:
                execution_error = error
                raise
        # The run is finalized only after the protected context restores saves.
        write_manifest(status="completed", reason=report["reason"], finished_at=time.time(),
                       save_restoration="verified")
    except BaseException as error:
        status = "interrupted" if isinstance(error, (KeyboardInterrupt, ExternalInputInterference)) else "error"
        failure_reason = ("cooperative_stop_requested" if isinstance(error, CooperativeStop) else
                          "external_interference" if isinstance(error, ExternalInputInterference) else
                          "user_interrupted" if isinstance(error, KeyboardInterrupt) else "protected_run_failed")
        if error is execution_error:
            terminal = next((r for r in reversed(load_trajectory(recorder.path)) if r.get("kind") == "end"), {})
            status = terminal.get("status", status)
            failure_reason = terminal.get("reason", failure_reason)
        recorder.finish(status=status,
                        reason=failure_reason, error=str(error),
                        **({"stop_request": error.evidence} if isinstance(error, CooperativeStop) else {}))
        write_manifest(status=status, reason=failure_reason, error=str(error), finished_at=time.time(),
                       save_restoration=save_restoration_status(protected.backup),
                       **({"stop_request": error.evidence} if isinstance(error, CooperativeStop) else {}),
                       **({"external_input_guard": error.evidence,
                           "comparison_exclusion_reason": "external_interference"}
                          if isinstance(error, ExternalInputInterference) else {}))
        raise
    print(f"Visual run and save-restoration receipt: {directory}")


if __name__ == "__main__":
    main()
