"""Protected no-model STORE-on-arrival diagnostic; never benchmark gameplay.

Run only when no game/controller is active, with --output NEW_DIRECTORY.
Queues the natural first seed-one jump with the unchanged production bridge,
and archives actual visual frames and cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from ftl_bench.cli import _bench_root
from ftl_bench.challenge_setup import DeterministicSetupSession, packet_proof, receipt_proof
from ftl_bench.installation import runtime_fingerprint
from ftl_bench.native_acceptance import CAPABILITIES, source_identity
from ftl_bench.protected_game import ProtectedGame, _processes
from ftl_bench.session import ftl_user_folder, jump
from ftl_bench.trajectory import TrajectoryRecorder
from ftl_bench.visual_session import VisualSession
from ftl_bench import visual_evidence as evidence

ROOT = _bench_root()
sys.path.insert(0, str(ROOT / "adapter"))
from run_visual import visual_record

SCOPE = "Natural first seed-one beacon arrival at (49,231); no model or general determinism claim."


def write(path, value):
    evidence.write(path, value)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def position(raw):
    return (raw.get("map") or {}).get("current_pos")


def single_continue(raw):
    event = raw.get("event") or {}
    choices = event.get("choices") or []
    return (type(event.get("dialog_keys")) is int and event["dialog_keys"] == 1
            and event.get("selected_choice") == -1 and len(choices) == 1
            and type(choices[0].get("index")) is int and choices[0]["index"] == 0
            and choices[0].get("enabled") is True and choices[0].get("disabled") is False
            and choices[0].get("text") == "Continue...")


def prepare(session, output, recorder):
    """Ordinary clocked intro/charge and a zero-update real connected jump."""
    session.configure_setup(output)
    records = []
    def keep(label, obs, actions=(), frames=0):
        records.append({"label": label, "actions": list(actions), "requested_frames": frames, "obs": obs.raw})
        write(output / "setup.json", records)
        recorder.record("setup", actions, obs, thought=label)
        return obs
    keep("fresh-seed-one", session.reset_episode(seed=1))
    keep("reset-ack", session.reset())
    obs = keep("settle-intro", session.step([], 30), frames=30)
    for _ in range(20):
        if not obs.choice_box_open:
            break
        choices = [c for c in (obs.event or {}).get("choices", []) if c.get("enabled") is True]
        if not choices:
            raise RuntimeError("Intro has no enabled ordinary choice")
        index = choices[0]["index"]
        actions = [{"type": "choose_event", "choice_index": index}]
        obs = keep("intro-choice", session.choose_event(index, 60), actions, 60)
    else:
        raise RuntimeError("Intro did not settle")
    if position(obs.raw) != {"x": 88, "y": 152}:
        raise RuntimeError("Seed-one starting location differs")
    for _ in range(30):
        if (obs.raw.get("economy") or {}).get("navigation", {}).get("can_jump") is True:
            break
        obs = keep("ordinary-drive-charge", session.step([], 300), frames=300)
    else:
        raise RuntimeError("Ordinary drive charging did not enable navigation")
    beacon = next((b for b in (obs.raw.get("map") or {}).get("connected_beacons", []) if b.get("index") == 1), None)
    if not beacon or (beacon.get("pos_x"), beacon.get("pos_y")) != (49, 231):
        raise RuntimeError("Seed-one connected quiet destination differs")
    departure = position(obs.raw)
    target = {"x": beacon["pos_x"], "y": beacon["pos_y"]}
    fuel = (obs.raw.get("player_ship") or {}).get("resources", {}).get("fuel")
    if type(fuel) is not int or fuel < 1:
        raise RuntimeError("Native departure fuel evidence missing")
    actions = [jump(1)]
    obs = keep("queue-real-connected-jump", session.step(actions, 0), actions, 0)
    # The ready-phase receipt retains the native Start callback's snapshot.
    # The ordinary zero-update visual handoff refreshes that snapshot after
    # completion scope exits; it is the authoritative validation boundary.
    write(output / "pre-handoff-setup-proof.json", {
        "diagnostic_only": True, "authoritative": False,
        "receipt_proof": receipt_proof(obs.raw, require_visual=False)})
    feedback = obs.raw.get("action_feedback") or []
    write(output / "departure.json", {"position": departure, "target": target, "fuel": fuel,
          "queued_observation": obs.raw, "action_feedback": feedback})
    if not any(row.get("type") == "jump" and row.get("beacon_index") == 1
               and row.get("status") == "applied" for row in feedback):
        raise RuntimeError("Native connected jump was not acknowledged as applied")
    return departure, target, fuel


def run_probe(session, transport, recorder, output, departure, target, fuel):
    frame = transport.capture()
    setup_proof = receipt_proof(frame.observation.raw, require_visual=False)
    packets = packet_proof(frame.observation.raw, session.setup_packets)
    write(output / "handoff-setup-proof.json", {"authoritative": True,
          "receipt_proof": setup_proof, "packet_proof": packets})
    if not setup_proof["passed"]:
        raise RuntimeError("Clocked structured prerequisite receipt failed at visual handoff")
    if (frame.reference.get("width"), frame.reference.get("height")) != (1280, 720):
        raise RuntimeError("STORE CLOSE calibration requires a 1280x720 image")
    if not packets["passed"]:
        raise RuntimeError("Archived setup packets do not join native handoff")
    recorder.record("reset", [], frame.observation,
                    visual=visual_record("image", frame, frame, [], 0))
    steps = []
    def save(status, error=None):
        value = {"classification": "diagnostic_only", "fixture_only": False, "model_calls": 0,
                 "valid_for_model_comparison": False, "valid_for_full_game_comparison": False,
                 "status": status, "error": error, "scope": SCOPE, "steps": steps,
                 "departure": departure, "target": target}
        write(output / "store-arrival-proof.json", value)
        return value
    def step(actions, requested, label):
        nonlocal frame
        before = frame
        frame = transport.step(before, actions, requested)
        raw, previous = frame.observation.raw, before.observation.raw
        native = raw["visual"]
        delta = int(native["world_updates"]) - int(previous["visual"]["world_updates"])
        actual = native.get("actual_frames")
        feedback = native.get("input_feedback") or []
        delivered = len(feedback) == len(actions) and all(
            item.get("status") == "delivered" and item.get("index") == i
            and item.get("type") == action["type"] for i, (action, item) in enumerate(zip(actions, feedback)))
        row = {"label": label, "actions": actions, "requested_frames": requested,
               "actual_frames": actual, "native_counter_delta": delta, "inputs_delivered": delivered,
               "before_image": before.reference, "after_image": frame.reference,
               "visual_evaluator": raw.get("visual_evaluator"), "position": position(raw),
               "event": raw.get("event"),
               "fuel": (raw.get("player_ship") or {}).get("resources", {}).get("fuel")}
        steps.append(row)
        recorder.record("step", actions, frame.observation, thought=label, pre_obs=before.observation,
                        visual=visual_record("image", before, frame, actions, requested))
        save("running")
        if type(actual) is not int or not 0 <= actual <= requested or delta != actual or not delivered:
            raise RuntimeError("Visual input/update accounting failed: " + label)
        return raw
    save("running")
    hidden_zero = 0
    for index in range(8):
        raw = step([], 600, f"native-arrival-{index + 1}")
        evaluator = raw.get("visual_evaluator") or {}
        if evaluator.get("store_open") is True and evaluator.get("player_jumping") is True:
            if (raw.get("player_ship") or {}).get("resources", {}).get("fuel") != fuel - 1:
                raise RuntimeError("Hidden arrival did not consume exactly one fuel")
            hidden_zero = hidden_zero + 1 if steps[-1]["actual_frames"] == 0 else 0
            if hidden_zero >= 2:
                save("rejected", "Hidden native STORE blocks unfinished warp; two subsequent advances completed zero updates")
                raise RuntimeError("Hidden store arrival regression reproduced")
        else:
            hidden_zero = 0
        if evaluator.get("store_open") is True and evaluator.get("player_jumping") is False:
            break
    else:
        save("rejected", "Bounded native arrival did not reach a settled visible store")
        raise RuntimeError("Bounded STORE arrival did not settle")
    if position(raw) != target:
        raise RuntimeError("Settled STORE lacks the correct native arrival location")
    if (raw.get("player_ship") or {}).get("resources", {}).get("fuel") != fuel - 1:
        raise RuntimeError("Real jump did not consume exactly one fuel")
    if (raw.get("visual_evaluator") or {}).get("choice_window_open") is True:
        if not single_continue(raw):
            return save("review_required", "Unknown native arrival choice; archived without guessed input")
        # Native input debounce advances with rendered UI time, not world updates.
        time.sleep(0.35)
        raw = step([], 0, "arrival-choice-debounce-capture")
        if not single_continue(raw):
            return save("review_required", "Arrival Continue choice changed during debounce")
        raw = step([{"type": "click", "x": 405, "y": 317, "button": "left", "modifiers": []}],
                   1, "ordinary-arrival-continue")
        evaluator = raw.get("visual_evaluator") or {}
        if evaluator.get("choice_window_open") is not False or evaluator.get("store_open") is not True:
            save("rejected", "Ordinary arrival Continue did not close choice and retain visible STORE")
            raise RuntimeError("Ordinary arrival Continue transition failed")
    blocked = step([], 600, "settled-visible-store-blocks")
    evaluator = blocked.get("visual_evaluator") or {}
    if (steps[-1]["actual_frames"] != 0 or evaluator.get("blocked_reason") != "store_open"
            or evaluator.get("player_jumping") is not False):
        raise RuntimeError("Settled store did not block ordinary simulation")
    close = [{"type": "click", "x": 853, "y": 570, "button": "left", "modifiers": []}]
    closed = step(close, 0, "ordinary-store-close")
    if (closed.get("visual_evaluator") or {}).get("store_open") is not False:
        raise RuntimeError("Ordinary CLOSE input did not close the settled store")
    return save("passed")


def validate(output):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    meta = {"classification": "diagnostic_only", "fixture_only": False, "model_calls": 0,
            "provider": "none", "model": None, "seed": 1, "scope": SCOPE,
            "valid_for_model_comparison": False, "valid_for_full_game_comparison": False,
            "status": "running", "started_at": evidence.stamp()}
    recorder = None
    protected, before, sources = None, None, {}
    primary_error, cleanup_error, cleanup_verification_error = None, None, None
    checks = {}
    live_existed, live_sha = True, None
    deployed_sha = None
    try:
        sources = evidence.snapshot_sources(ROOT, output)
        driver = Path(__file__).read_bytes()
        (output / "probe-driver.py").write_bytes(driver)
        meta["probe_driver_sha256"] = hashlib.sha256(driver).hexdigest()
        source = ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
        production = source.read_bytes()
        (output / "production-bridge.lua").write_bytes(production)
        deployed_bridge = output / "production-bridge.lua"
        deployed_sha = digest(deployed_bridge)
        meta.update(production_bridge_sha256=hashlib.sha256(production).hexdigest(),
                    deployed_bridge_sha256=deployed_sha, source_files_sha256=evidence.source_digest(sources))
        recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
        protected = ProtectedGame(ftl_user_folder(), output / "save-backup", deployed_bridge)
        before = evidence.inventory(protected, source)
        write(output / "before-inventory.json", {"checked_at": evidence.stamp(), "files_sha256": before})
        live = protected.save / "ftl_bench_dev.lua"
        if live.is_symlink() or (live.exists() and not live.is_file()):
            raise RuntimeError("Unsafe original deployed bridge")
        live_existed = live.exists()
        live_sha = digest(live) if live_existed else None
        fingerprint = runtime_fingerprint(ROOT)
        write(output / "prelaunch-runtime-fingerprint.json", fingerprint)
        build = fingerprint.get("native_build") or {}
        if build.get("matches_installed_dll") is not True or any(
                type(build.get(k)) is not type(v) or build.get(k) != v for k, v in CAPABILITIES.items()):
            raise RuntimeError("Installed native provenance/capabilities do not match")
        runtime_files = {name: {"path": str(protected.game / name), "sha256": digest(protected.game / name)}
                         for name in evidence.RUNTIME_FILES}
        write(output / "installed-runtime.json", {"files": runtime_files})
        with protected.protected():
            try:
                protected.launch()
                fingerprint = runtime_fingerprint(ROOT)
                write(output / "runtime-fingerprint.json", fingerprint)
                if ((fingerprint.get("bridge_lua") or {}).get("sha256") != deployed_sha
                        or fingerprint.get("native_build") != build
                        or (fingerprint.get("native_dll") or {}).get("sha256") != runtime_files["Hyperspace.dll"]["sha256"]
                        or any(digest(protected.game / name) != value["sha256"] for name, value in runtime_files.items())):
                    raise RuntimeError("Deployed diagnostic bridge/native runtime differs from archived bytes")
                session = DeterministicSetupSession(ftl_user_folder(), step_timeout=30)
                departure, target, fuel = prepare(session, output, recorder)
                result = run_probe(session, VisualSession(session, output), recorder, output, departure, target, fuel)
                meta["probe_status"] = result["status"]
            except BaseException as error:
                primary_error = error
                raise
    except BaseException as error:
        if primary_error is None:
            primary_error = error
        else:
            if error is not primary_error:
                cleanup_error = error
    finally:
        if protected is not None and protected.manifest:
            try:
                processes = _processes()
                if processes:
                    raise RuntimeError("FTL remains active; post-cleanup verification withheld")
                live = protected.save / "ftl_bench_dev.lua"
                if not live_existed and live.exists():
                    if live.is_symlink() or not live.is_file() or digest(live) != deployed_sha:
                        raise RuntimeError("Changed/unsafe production bridge prevents absent-bridge restoration")
                    live.unlink()
                checks["bridge_restored"] = (digest(live) == live_sha) if live_existed else not live.exists()
                restoration = json.loads((protected.backup / "restoration.json").read_text(encoding="utf-8"))
                checks["save_restoration"] = restoration.get("verified") is True
                after = evidence.inventory(protected, ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua")
                write(output / "after-inventory.json", {"checked_at": evidence.stamp(), "files_sha256": after,
                      "no_game_process": True, "processes": processes})
                checks["original_inventory_restored"] = before == after
                checks["source_snapshot_unchanged"] = source_identity(ROOT) == sources
                checks["probe_driver_unchanged"] = digest(Path(__file__)) == meta["probe_driver_sha256"]
                if not all(checks.values()):
                    raise RuntimeError("Post-cleanup save/bridge/runtime/source verification failed")
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
                else:
                    cleanup_verification_error = error
        if recorder is None:
            recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
        failed = primary_error is not None or cleanup_error is not None or cleanup_verification_error is not None
        reason = "store_arrival_probe_failed" if failed else ("store_arrival_review_required" if meta.get("probe_status") == "review_required" else "store_arrival_verified")
        recorder.finish(status="error" if failed else "completed", reason=reason,
                        error=str(primary_error or cleanup_error) if failed else None, model_calls=0)
        meta.update(status="error" if failed else "completed", reason=reason, finished_at=evidence.stamp(),
                    error=str(primary_error) if primary_error else None,
                    cleanup_error=str(cleanup_error) if cleanup_error else None,
                    cleanup_verification_error=str(cleanup_verification_error) if cleanup_verification_error else None)
        write(output / "run.json", meta)
        artifacts = {path.relative_to(output).as_posix(): digest(path) for path in sorted(output.rglob("*"))
                     if path.is_file() and path.name != "validation.json"}
        write(output / "validation.json", {**meta, "checks": checks, "source_files": sources,
                                          "artifact_sha256": artifacts})
    errors = [error for error in (primary_error, cleanup_error, cleanup_verification_error) if error is not None]
    if len(errors) > 1:
        raise BaseExceptionGroup("STORE arrival and cleanup failed", errors)
    if errors:
        raise errors[0]
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(validate(args.output))


if __name__ == "__main__":
    main()
