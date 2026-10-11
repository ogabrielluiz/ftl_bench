"""Protected fixture-free startup and first-image diagnostic; never calls a model.

Run with --output NEW_DIRECTORY [--seed UINT32]. This launches the configured
Windows game and restores the original saves automatically. Its receipt covers
startup admission only, not gameplay, full-game completion, or model comparison.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from ftl_bench.cli import _bench_root

ROOT = _bench_root()
sys.path.insert(0, str(ROOT / "adapter"))
from ftl_bench.fullgame_setup import FullGameSetupSession, declared_seed
from ftl_bench.installation import runtime_fingerprint
from ftl_bench.native_acceptance import source_identity, CAPABILITIES
from ftl_bench import visual_evidence as evidence
from ftl_bench.protected_game import ProtectedGame, _processes
from ftl_bench.session import ftl_user_folder
from ftl_bench.trajectory import TrajectoryRecorder
from ftl_bench.visual_session import VisualSession
from run_visual import run_loop

CONTRACT = "visual-startup-validation-v1"
SCOPE = "Fixture-free startup admission and first capture only; no gameplay or full-game completion."


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(protected):
    return evidence.inventory(protected)


def snapshot_sources(output, reference_root=None):
    """Archive executable/protocol source bytes without requiring dated dist receipts."""
    return evidence.snapshot_sources(ROOT, output, reference_root)


class NoModel:
    def decide(self, observation):
        raise AssertionError("Startup validation must never call an actor")


def restore_bridge_absence(protected, deployed_sha):
    """Restore an absent original only after owned-game cleanup has finished."""
    if _processes():
        raise RuntimeError("FTL still exists; refusing absent-bridge restoration")
    target = protected.save / "ftl_bench_dev.lua"
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise RuntimeError("Unsafe deployed bridge path during absent-bridge restoration")
    if target.exists():
        if digest(target) != deployed_sha:
            raise RuntimeError("Deployed bridge changed; refusing absent-bridge restoration")
        target.unlink()


def finalize(output, meta, checks, sources, status, reference_root=None):
    write(output / "run.json", meta)
    references = {}
    for name in ("run.json", "trajectory.jsonl", "visual-report.json", "runtime-fingerprint.json",
                 "source-snapshot.json", "fresh-setup/admission.json", "fresh-setup/setup-session.json",
                 "portable-cleanup.json", "startup-evidence.json",
                 "installed-runtime.json", "prelaunch-runtime-fingerprint.json",
                 "before-inventory.json", "after-inventory.json", "setup-verification.json",
                 "save-backup/manifest.json", "save-backup/restoration.json"):
        if (output / name).is_file():
            ref = evidence.reference(reference_root or output, output / name)
            references[ref["path"]] = ref["sha256"]
    for path in sorted((output / "screens").glob("*.png")):
        ref = evidence.reference(reference_root or output, path)
        references[ref["path"]] = ref["sha256"]
    write(output / "validation.json", {"contract": CONTRACT, "status": status,
        "checked_at": stamp(), "classification": "diagnostic_only", "seed": meta["seed"],
        "valid_for_model_comparison": False, "valid_for_full_game_comparison": False,
        "model_calls": 0, "checks": checks, "scope": SCOPE,
        "error": meta["error"], "cleanup_error": meta["cleanup_error"],
        "source_files": sources, "artifact_sha256": references})


def validate(output: Path, seed: int = 1, evidence_root: Path | None = None):
    seed = declared_seed(seed)
    output = Path(output).absolute()
    reference_root = evidence.evidence_root(output, evidence_root)
    output.mkdir(parents=True, exist_ok=False)
    meta = {"track": "visual-v1", "observation_mode": "image", "run_id": output.name,
        "classification": "diagnostic_only", "valid_for_model_comparison": False,
        "valid_for_full_game_comparison": False, "provider": "none", "model": None,
        "fixture_free_startup": True, "startup_contract": "fresh-start-seed-v3",
        "status": "running", "started_at": stamp(), "seed": seed, "scope": SCOPE}
    write(output / "run.json", meta)
    recorder = None
    checks, primary_error, cleanup_error = {}, None, None
    sources, before = {}, None
    protected = None
    entered = False
    try:
        sources = snapshot_sources(output, reference_root)
        meta["source_files_sha256"] = hashlib.sha256(json.dumps(sources, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        write(output / "run.json", meta)
        recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
        fingerprint = runtime_fingerprint(ROOT)
        write(output / "prelaunch-runtime-fingerprint.json", fingerprint)
        build = fingerprint.get("native_build") or {}
        if (build.get("matches_installed_dll") is not True or build.get("fresh_start_seed") is not True
                or build.get("fresh_seed_contract") != "fresh-start-seed-v3"
                or type(build.get("fresh_seed_contract_version")) is not int
                or build["fresh_seed_contract_version"] != 3):
            raise RuntimeError("Installed native runtime must match its fresh-start seed v3 provenance")
        protected = ProtectedGame(ftl_user_folder(), output / "save-backup",
            ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua")
        runtime_files = {name: {"path": str(protected.game / name), "sha256": digest(protected.game / name)}
            for name in ("FTLGame.exe", "ftl.dat", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll", "ftlbench-native.json")}
        write(output / "installed-runtime.json", {"contract": "visual-startup-installed-runtime-v1",
            "captured_at": stamp(), "files": runtime_files})
        before = inventory(protected)
        write(output / "before-inventory.json", {"checked_at": stamp(), "files_sha256": before})
        live_bridge = protected.save / "ftl_bench_dev.lua"
        if live_bridge.is_symlink() or (live_bridge.exists() and not live_bridge.is_file()):
            raise RuntimeError("Unsafe original bridge path")
        bridge_was_absent = not live_bridge.exists()
        try:
            with protected.protected():
                entered = True
                try:
                    protected.launch()
                    fingerprint = runtime_fingerprint(ROOT)
                    write(output / "runtime-fingerprint.json", fingerprint)
                    deployed = fingerprint.get("bridge_lua") or {}
                    native = fingerprint.get("native_build") or {}
                    if (deployed.get("sha256") != sources["mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"]
                            or native.get("matches_installed_dll") is not True
                            or (fingerprint.get("native_dll") or {}).get("sha256") != runtime_files["Hyperspace.dll"]["sha256"]
                            or any(type(native.get(k)) is not type(v) or native[k] != v
                                   for k, v in CAPABILITIES.items())):
                        raise RuntimeError("Deployed bridge or native runtime differs from archived startup identity")
                    session = FullGameSetupSession(ftl_user_folder(), setup_output=output / "fresh-setup",
                        seed=seed, step_timeout=20)
                    session.reset_episode(seed=seed)
                    session.reset()
                    report = run_loop(VisualSession(session, output), NoModel(), recorder,
                        max_decisions=0, expected_seed=seed, initial_frame_validator=session.verify_first_capture)
                    admission = json.loads((output / "fresh-setup/admission.json").read_text(encoding="utf-8"))
                    raw = admission["first_observation"]
                    visual, evaluator = raw["visual"], raw["visual_evaluator"]
                    checks.update(fixture_free_v3_admission=admission.get("passed") is True and session.admitted,
                        first_image_verified=admission.get("first_image_verified") is True,
                        opening_choices_untouched=evaluator.get("choice_window_open") is True
                            and evaluator.get("blocked_reason") == "choice_open",
                        zero_input_and_updates=type(visual.get("requested_frames")) is int
                            and visual["requested_frames"] == 0 and type(visual.get("actual_frames")) is int
                            and visual["actual_frames"] == 0 and visual.get("input_feedback") == []
                            and visual.get("world_updates") == visual.get("simulated_updates") == "0",
                        no_actor_decisions=report.get("decisions") == 0,
                        source_snapshot_unchanged=source_identity(ROOT) == sources)
                    if not all(checks.values()):
                        raise RuntimeError("Startup admission checks failed: " + str(checks))
                except BaseException as error:
                    primary_error = error
                    raise
        except BaseException as error:
            if entered and error is not primary_error:
                cleanup_error = error
            raise
        finally:
            if bridge_was_absent:
                try:
                    restore_bridge_absence(protected, sources["mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"])
                except BaseException as bridge_error:
                    if primary_error is None and cleanup_error is None:
                        cleanup_error = bridge_error
                        raise
                    prior = cleanup_error or primary_error
                    cleanup_error = bridge_error
                    raise BaseExceptionGroup("Startup lifecycle and absent-bridge restoration failed", [prior, bridge_error])
        restoration = json.loads((protected.backup / "restoration.json").read_text(encoding="utf-8"))
        checks["save_restoration"] = restoration.get("verified") is True
        if not checks["save_restoration"]:
            raise RuntimeError("Protected save restoration did not verify")
        processes = _processes()
        if processes:
            raise RuntimeError("FTL still exists after protected cleanup; independent inventory withheld")
        after = inventory(protected)
        write(output / "after-inventory.json", {"checked_at": stamp(), "files_sha256": after,
            "no_game_process": True, "processes": processes,
            "scope": "Point-in-time file inventory after this protected startup diagnostic."})
        checks["original_inventory_restored"] = before == after
        checks["source_snapshot_unchanged"] = source_identity(ROOT) == sources
        if not checks["original_inventory_restored"] or not checks["source_snapshot_unchanged"]:
            raise RuntimeError("Original inventory or snapshotted sources changed during startup validation")
        evidence.cleanup_attestation(reference_root, output, protected, before, after, processes,
                                     session="fresh-setup/setup-session.json")
        write(output / "startup-evidence.json", {"contract": "visual-startup-evidence-v1",
            "evidence_root": str(reference_root),
            "source_snapshot": evidence.reference(reference_root, output / "source-snapshot.json"),
            "startup": evidence.trial_descriptor(reference_root, output, session="fresh-setup/setup-session.json",
                                                admission="fresh-setup/admission.json")})
    except BaseException as error:
        if primary_error is None:
            primary_error = error
        if recorder is None:
            recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
        recorder.finish(status="error", reason="startup_probe_failed", error=str(error))
        raise
    finally:
        status = "error" if primary_error is not None or cleanup_error is not None else "passed"
        meta.update(status="error" if status == "error" else "completed", finished_at=stamp(),
            reason="startup_probe_failed" if status == "error" else "decision_budget",
            diagnostic_reason="startup_probe_failed" if status == "error" else "startup_admission_verified",
            error=str(primary_error) if primary_error is not None else None,
            cleanup_error=str(cleanup_error) if cleanup_error is not None else None)
        try:
            finalize(output, meta, checks, sources, status, reference_root)
        except BaseException as finalization_error:
            errors = list(dict.fromkeys(error for error in (primary_error, cleanup_error, finalization_error)
                                        if error is not None))
            if len(errors) > 1:
                raise BaseExceptionGroup("Startup and receipt finalization failed", errors)
            raise
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--evidence-root", type=Path, help="Common parent for all nested portable evidence references")
    args = parser.parse_args(argv)
    print(validate(args.output, args.seed, args.evidence_root))


if __name__ == "__main__":
    main()
