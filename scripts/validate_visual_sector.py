"""Protected, no-model sector/Wait clock diagnostic; never benchmark evidence.

Run without coordinates first to archive the visible map and stop safely. Supply
coordinates only after inspecting that image, then the sector picker image from
the next run. Every tested input uses VisualSession; hidden map actor data never
selects a click. Existing saves and deployed bridge are restored before exit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]

from ftl_bench.installation import runtime_fingerprint
from ftl_bench.protected_game import ProtectedGame
from ftl_bench.session import AgentSession, ftl_user_folder
from ftl_bench.trajectory import TrajectoryRecorder
from ftl_bench.visual_session import ExternalInputInterference, VisualSession


# This appended chunk shares the production chunk's local json binding. Setup
# waits for visual mode, after the ordinary disposable run and intro are ready.
# No queued choice, travel flag, sector, timer, or simulation counter is written.
FIXTURE_LUA = r'''
local visualFixture={fixture_only=true,valid_for_model_comparison=false,
 id=__FIXTURE_ID__,mode=__FIXTURE_MODE__,applied=false}
local visualFixtureTick=_G.ftl_bench_tick
local function fixtureProbe(out,key,fn)
 local ok,value=pcall(fn)
 if ok and value~=nil then out[key]=value end
end
local function visualFixtureSnapshot()
 local out={fixture_only=true,valid_for_model_comparison=false,
  id=visualFixture.id,mode=visualFixture.mode,applied=visualFixture.applied,
  setup_error=visualFixture.setup_error}
 local app=Hyperspace.App
 local map=app.world.starMap
 fixtureProbe(out,"world_level",function() return map.worldLevel end)
 fixtureProbe(out,"choosing_new_sector",function() return map.bChoosingNewSector end)
 fixtureProbe(out,"final_sector_choice",function() return map.finalSectorChoice end)
 fixtureProbe(out,"ready_to_travel",function() return map.readyToTravel end)
 fixtureProbe(out,"waited_last",function() return map.waitedLast end)
 fixtureProbe(out,"fuel_event_seed",function() return map.fuelEventSeed end)
 fixtureProbe(out,"danger_zone",function() return {x=map.dangerZone.x,y=map.dangerZone.y} end)
 fixtureProbe(out,"current_beacon",function() return map.currentLoc.beacon end)
 fixtureProbe(out,"fuel",function() return Hyperspace.ships.player.fuel_count end)
 fixtureProbe(out,"map_position",function() return {x=map.position.x,y=map.position.y} end)
 -- Optional public render geometry is evidence only. Missing SWIG fields are
 -- omitted; Python never substitutes hidden sector locations or guessed pixels.
 local geometry={coordinate_space="native-logical",used_for_clicks=false}
 fixtureProbe(geometry,"sector_map_offset",function()
  return {x=map.sectorMapOffset.x,y=map.sectorMapOffset.y} end)
 fixtureProbe(geometry,"end_button",function()
  local b=map.endButton
  return {x=b.hitbox.x,y=b.hitbox.y,w=b.hitbox.w,h=b.hitbox.h,active=b.bActive} end)
 fixtureProbe(geometry,"wait_button",function()
  local b=map.waitButton
  return {x=b.hitbox.x,y=b.hitbox.y,w=b.hitbox.w,h=b.hitbox.h,active=b.bActive} end)
 out.render_geometry=geometry
 return out
end
_G.ftl_bench_tick=function()
 local app=Hyperspace.App
 if not visualFixture.applied and not visualFixture.setup_error
  and _G.ftl_bench_state.observation_mode=="visual-v1"
  and app.world.bStartedGame and not app.gui.choiceBoxOpen then
  local ok,err=pcall(function()
   if visualFixture.mode=="wait" then
    Hyperspace.ships.player.fuel_count=0
   else
    assert(app.world.starMap.currentLoc,"current location unavailable")
    app.world.starMap.currentLoc.beacon=true
   end
  end)
  if ok then visualFixture.applied=true else visualFixture.setup_error=tostring(err) end
  _G.ftl_bench_state.obs_fresh=false
 end
 visualFixtureTick()
end
local visualFixtureWriter=Hyperspace.benchmark_write_visual_observation
Hyperspace.benchmark_write_visual_observation=function(payload,...)
 local obs=json.decode(payload)
 obs.visual_fixture=visualFixtureSnapshot()
 return visualFixtureWriter(json.encode(obs),...)
end
'''


def fixture_bridge(source: bytes, mode: str, fixture_id: str) -> bytes:
    if mode not in ("sector", "wait"):
        raise ValueError("Unknown fixture mode")
    chunk = FIXTURE_LUA.replace("__FIXTURE_MODE__", json.dumps(mode)).replace(
        "__FIXTURE_ID__", json.dumps(fixture_id))
    return source + chunk.encode("utf-8")


def _fixture(raw):
    return raw.get("visual_fixture") or {}


def _recovery(raw):
    return (raw.get("economy") or {}).get("fuel_recovery") or {}


def _fuel(raw):
    return ((raw.get("player_ship") or {}).get("resources") or {}).get("fuel")


def world_signature(raw):
    """Gameplay fields only; cursor, render count and capture identities may move."""
    player = raw.get("player_ship") or {}
    nav = (raw.get("economy") or {}).get("navigation") or {}
    game_map = raw.get("map") or {}
    return {"resources": player.get("resources"), "hull": player.get("hull"),
            "crew": player.get("crew"), "systems": player.get("systems"),
            "oxygen": player.get("oxygen_pct"),
            "location": {k: game_map.get(k) for k in ("sector", "current_pos")},
            "drive": {k: nav.get(k) for k in ("drive_current", "drive_max")},
            "score": raw.get("ftl_score_components"),
            "world_level": _fixture(raw).get("world_level"),
            "world_updates": (raw.get("visual") or {}).get("world_updates")}


def queue_signature(raw):
    return {"fixture": {k: _fixture(raw).get(k) for k in (
                "world_level", "choosing_new_sector", "final_sector_choice",
                "ready_to_travel", "waited_last", "fuel_event_seed", "danger_zone")},
            "fuel_recovery": _recovery(raw), "evaluator": raw.get("visual_evaluator"),
            "choice_box_open": raw.get("choice_box_open")}


def freeze_proof(before, after, *, queue=True):
    missing = []
    for label, raw in (("before", before), ("after", after)):
        if raw.get("paused") is not True:
            missing.append(f"{label}.paused")
        if type(_fixture(raw).get("world_level")) is not int:
            missing.append(f"{label}.world_level")
        if type(_fuel(raw)) is not int:
            missing.append(f"{label}.fuel")
        counter = (raw.get("visual") or {}).get("world_updates")
        if not isinstance(counter, str) or not counter.isdecimal():
            missing.append(f"{label}.world_updates")
    same_world = world_signature(before) == world_signature(after)
    same_queue = not queue or queue_signature(before) == queue_signature(after)
    return {"passed": not missing and same_world and same_queue,
            "missing": missing, "same_world": same_world, "same_queue": same_queue}


def click_action(point, frame, expected_size):
    if tuple(frame.reference[k] for k in ("width", "height")) != tuple(expected_size):
        raise RuntimeError("Calibration size does not match the archived screenshot")
    if (len(point) != 2 or any(type(v) is not int for v in point)
            or not 0 <= point[0] < expected_size[0] or not 0 <= point[1] < expected_size[1]):
        raise ValueError("Click must be an integer pixel inside the calibration screenshot")
    return {"type": "click", "x": point[0], "y": point[1],
            "button": "left", "modifiers": []}


def transition_proof(mode, queued, after, updates):
    """Require native state progress in addition to acknowledged frame accounting."""
    q, a = _fixture(queued), _fixture(after)
    levels = (q.get("world_level"), a.get("world_level"))
    valid_levels = all(type(v) is int for v in levels)
    if mode == "sector":
        fuel = (_fuel(queued), _fuel(after))
        checks = {"native_sector_plus_one": valid_levels and levels[1] == levels[0] + 1,
                  "native_fuel_minus_one": all(type(v) is int for v in fuel) and fuel[1] == fuel[0] - 1,
                  "arrival_finished": (after.get("visual_evaluator") or {}).get("player_jumping") is False
                       and (after.get("map") or {}).get("current_pos") is not None}
    else:
        checks = {"native_wait_started": _recovery(queued).get("waiting") is True,
                  "native_wait_finished": _recovery(after).get("waiting") is False,
                  "sector_unchanged": valid_levels and levels[0] == levels[1]}
    checks["explicit_world_updates"] = type(updates) is int and updates > 0
    return {"passed": all(checks.values()), "checks": checks, "actual_frames": updates}


def prepare(session, output):
    """Backstage prerequisite only: fresh seed 1, ordinary intro and drive charge."""
    records = []
    def keep(label, obs):
        records.append({"label": label, "obs": obs.raw})
        (output / "setup.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        return obs
    session.reset_episode(seed=1)
    session.reset()
    obs = keep("fresh-disposable-run", session.step([], 30))
    for _ in range(20):
        if not obs.choice_box_open:
            break
        choices = [c for c in (obs.event or {}).get("choices", []) if c.get("enabled") is True]
        if not choices:
            raise RuntimeError("Intro has no enabled normal choice")
        time.sleep(.35)
        obs = keep("normal-intro-choice", session.choose_event(choices[0]["index"], 60))
    if obs.choice_box_open:
        raise RuntimeError("Intro did not settle")
    for _ in range(30):
        if ((obs.raw.get("economy") or {}).get("navigation") or {}).get("can_jump") is True:
            return keep("normally-charged-drive", obs)
        obs = keep("normal-drive-charge", session.step([], 300))
    raise RuntimeError("Fresh run did not naturally charge its FTL drive")


def run_fixture(args, session, transport, recorder, output):
    evidence = []
    checks = {}
    def record(label, frame, before=None, actions=None, requested=0):
        evidence.append({"label": label, "capture": frame.reference,
                         "visual_fixture": _fixture(frame.observation.raw),
                         "visual_evaluator": frame.observation.raw.get("visual_evaluator")})
        (output / "captures.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        native = frame.observation.raw.get("visual") or {}
        feedback = native.get("input_feedback") or []
        inputs = []
        for index, action in enumerate(actions or []):
            ack = feedback[index] if index < len(feedback) else {}
            item = {**action, "delivery": ack.get("status", "unknown")}
            if ack.get("reason"):
                item["reason"] = ack["reason"]
            inputs.append(item)
        recorder.record("step" if before else "reset", actions or [], frame.observation,
                        thought=label, pre_obs=before.observation if before else None,
                        visual={"observation_mode": "image",
                                "before": before.reference if before else None,
                                "after": frame.reference, "inputs": inputs,
                                "advance": {"requested_frames": requested,
                                            "actual_frames": native.get("actual_frames")},
                                "outcome": {"status": "unknown", "summary": label}})
        print(json.dumps({"stage": label, "image": str(frame.image_path)}), flush=True)
        return frame
    def step(label, before, actions, frames):
        after = record(label, transport.step(before, actions, frames), before, actions, frames)
        feedback = (after.observation.raw.get("visual") or {}).get("input_feedback") or []
        if (len(feedback) != len(actions) or any(
                item.get("status") != "delivered" or type(item.get("index")) is not int
                or item["index"] != index or item.get("type") != action["type"]
                for index, (action, item) in enumerate(zip(actions, feedback)))):
            raise RuntimeError(f"Native input was rejected at {label}")
        return after
    def incomplete(stage):
        return {"status": "incomplete", "fixture_only": True,
                "valid_for_model_comparison": False, "reason": stage,
                "checks": checks, "calibration": evidence[-1]}
    def freeze(label, frame):
        time.sleep(args.idle_seconds)
        idle = session.observe()
        idle_check = freeze_proof(frame.observation.raw, idle.raw)
        fresh = step(label + "-fresh-zero", frame, [], 0)
        zero_check = freeze_proof(frame.observation.raw, fresh.observation.raw)
        checks[label + "-idle"] = idle_check
        checks[label + "-fresh-zero"] = zero_check
        (output / "freeze-proof.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        if not idle_check["passed"] or not zero_check["passed"]:
            raise RuntimeError(f"World or queued transition changed without a frame budget: {label}")
        return fresh
    frame = record("fixture-prerequisite-capture", transport.capture())
    # The one permitted setup write occurs once visual mode is entered. This
    # first refresh is setup evidence, deliberately outside the freeze checks.
    for _ in range(3):
        if _fixture(frame.observation.raw).get("applied") is True:
            break
        frame = step("fixture-prerequisite-refresh", frame, [], 0)
    fixture = _fixture(frame.observation.raw)
    if fixture.get("applied") is not True or fixture.get("setup_error"):
        raise RuntimeError("Temporary fixture prerequisite failed or its binding is unavailable")
    if args.mode == "sector" and fixture.get("current_beacon") is not True:
        raise RuntimeError("Disposable exit-beacon prerequisite was not observed")
    if args.mode == "wait" and _fuel(frame.observation.raw) != 0:
        raise RuntimeError("Disposable zero-fuel prerequisite was not observed")
    actions = ([click_action(args.map, frame, args.size)] if args.map else
               [{"type": "key", "key": "j", "modifiers": []}])
    before = frame
    frame = step("visible-map", frame, actions, 0)
    checks["open-map-zero-world"] = freeze_proof(before.observation.raw, frame.observation.raw, queue=False)
    if not checks["open-map-zero-world"]["passed"]:
        raise RuntimeError("Opening the map advanced gameplay")
    if (frame.observation.raw.get("visual_evaluator") or {}).get("map_open") is not True:
        return incomplete("map_not_open; inspect capture or supply --map X Y")
    frame = freeze("map-before-selection", frame)
    if args.mode == "sector":
        if args.end is None:
            return incomplete("calibrate --end X Y from visible-map screenshot")
        before = frame
        frame = step("visible-sector-picker", frame, [click_action(args.end, frame, args.size)], 0)
        if not freeze_proof(before.observation.raw, frame.observation.raw, queue=False)["passed"]:
            raise RuntimeError("Opening the sector picker advanced gameplay")
        if _fixture(frame.observation.raw).get("choosing_new_sector") is not True:
            return incomplete("sector_picker_not_open; inspect native control availability")
        if args.neighbor is None:
            return incomplete("calibrate --neighbor X Y from visible-sector-picker screenshot")
        point = args.neighbor
    else:
        if args.wait is None:
            return incomplete("calibrate --wait X Y from visible-map screenshot")
        point = args.wait
    before = frame
    frame = step("queued-native-selection", frame, [click_action(point, frame, args.size)], 0)
    checks["selection-zero-world"] = freeze_proof(before.observation.raw, frame.observation.raw, queue=False)
    if not checks["selection-zero-world"]["passed"]:
        raise RuntimeError("Zero-frame selection committed gameplay")
    if args.mode == "wait" and _recovery(frame.observation.raw).get("waiting") is not True:
        return incomplete("normal_Wait_not_started; inspect native button availability")
    if args.mode == "sector" and _fixture(frame.observation.raw).get("choosing_new_sector") is not True:
        return incomplete("sector_picker_not_visible_after_selection")
    queued = frame.observation.raw
    frame = freeze("queued-selection", frame)
    total = 0
    frame = step("explicit-first-frame", frame, [], 1)
    total += frame.observation.raw["visual"]["actual_frames"]
    frame = freeze("after-first-budget", frame)
    proof = transition_proof(args.mode, queued, frame.observation.raw, total)
    for _ in range(args.max_batches):
        if proof["passed"]:
            break
        frame = step("explicit-bounded-update", frame, [], args.frames)
        actual = frame.observation.raw["visual"]["actual_frames"]
        total += actual
        proof = transition_proof(args.mode, queued, frame.observation.raw, total)
        if actual == 0 and not proof["passed"]:
            break
    checks["native_transition"] = proof
    frame = freeze("final-boundary", frame)
    return {"status": "passed" if proof["passed"] else "failed", "fixture_only": True,
            "valid_for_model_comparison": False, "mode": args.mode, "checks": checks,
            "reason": "native_transition" if proof["passed"] else "bounded_updates_did_not_complete_transition"}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("sector", "wait"), default="sector")
    p.add_argument("--fuel-wait", action="store_true", help="Alias for --mode wait")
    for name, help_text in (("map", "Optional calibrated FTL/map button"),
                            ("end", "Calibrated NEXT SECTOR button in visible map"),
                            ("neighbor", "Calibrated visible connected sector in sector picker"),
                            ("wait", "Calibrated WAIT button in out-of-fuel map")):
        p.add_argument("--" + name, nargs=2, type=int, metavar=("X", "Y"), help=help_text)
    p.add_argument("--size", nargs=2, type=int, default=(1280, 720), metavar=("WIDTH", "HEIGHT"),
                   help="Exact dimensions of the screenshot used for calibration")
    p.add_argument("--frames", type=int, default=600, help="Explicit per-step frame budget, 1..600")
    p.add_argument("--max-batches", type=int, default=6, help="Maximum explicit bounded steps after the first frame")
    p.add_argument("--idle-seconds", type=float, default=2, help="Idle interval at each freeze boundary (1..30)")
    p.add_argument("--output", type=Path, help="Fresh artifact directory; must not exist")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.fuel_wait:
        args.mode = "wait"
    if not 1 <= args.frames <= 600 or not 1 <= args.max_batches <= 20 or not 1 <= args.idle_seconds <= 30:
        raise ValueError("Invalid bounded update/idle limits")
    if any(v < 1 or v > 8192 for v in args.size):
        raise ValueError("Invalid calibration dimensions")
    output = args.output or ROOT / "harness/runs/validation/visual-v1" / ("visual-" + args.mode + "-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
    original = source.read_bytes()
    source_hash = hashlib.sha256(original).hexdigest()
    temporary = output / "fixture-bridge.lua"
    temporary.write_bytes(fixture_bridge(original, args.mode, output.name))
    user = ftl_user_folder()
    live = user / "ftl_bench_dev.lua"
    if live.is_symlink() or (live.exists() and not live.is_file()):
        raise RuntimeError("Unsafe deployed bridge path")
    live_existed = live.exists()
    live_hash = hashlib.sha256(live.read_bytes()).hexdigest() if live_existed else None
    protected = ProtectedGame(user, output / "save-backup", temporary)
    meta = {"track": "visual-v1", "observation_mode": "image",
            "fixture_only": True, "valid_for_model_comparison": False, "provider": "none", "model": None,
            "mode": args.mode, "seed": 1, "run_id": output.name,
            "production_bridge_sha256": source_hash,
            "temporary_bridge_sha256": hashlib.sha256(temporary.read_bytes()).hexdigest(),
            "setup_override": "currentLoc.beacon=true" if args.mode == "sector" else "fresh_disposable_fuel=0",
            "coordinate_source": "explicit human calibration of archived native screenshots",
            "coordinates": {k: getattr(args, k) for k in ("map", "end", "neighbor", "wait")},
            "calibration_size": args.size, "status": "running"}
    recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
    def manifest(**updates):
        meta.update(updates)
        (output / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    manifest()
    error = None
    validation = None
    try:
        with protected.protected():
            protected.launch()
            fingerprint = runtime_fingerprint(ROOT)
            (output / "runtime-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
            if not (fingerprint.get("native_build") or {}).get("matches_installed_dll"):
                raise RuntimeError("Installed native DLL provenance mismatch")
            session = AgentSession(step_timeout=20)
            prepare(session, output)
            validation = run_fixture(args, session, VisualSession(session, output), recorder, output)
            (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    except BaseException as exc:
        error = exc
    finally:
        receipt_path = output / "save-backup/restoration.json"
        restored = receipt_path.is_file() and json.loads(receipt_path.read_text(encoding="utf-8")).get("verified") is True
        # ProtectedGame restores pre-existing deployed Lua. Also remove its
        # generated bridge when this profile originally had no deployed bridge.
        if restored:
            if live.is_symlink() or (live.exists() and not live.is_file()):
                restored = False
            elif not live_existed:
                live.unlink(missing_ok=True)
            else:
                restored = live.exists() and hashlib.sha256(live.read_bytes()).hexdigest() == live_hash
        source_unchanged = source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        status = "interrupted" if isinstance(error, (KeyboardInterrupt, ExternalInputInterference)) else "error" if error else "completed"
        if not restored or not source_unchanged:
            error = error or RuntimeError("Save/deployed bridge restoration or production source verification failed")
            status = "error"
        reason = "external_interference" if isinstance(error, ExternalInputInterference) else str(error) if error else validation["reason"]
        recorder.finish(status=status, reason=reason, error=str(error) if error else None)
        manifest(status=status, reason=reason, finished_at=time.time(), save_restoration="verified" if restored else "not_verified",
                 production_source_unchanged=source_unchanged,
                 fixture_acceptance=validation["status"] if validation else "not_run")
    print(f"Visual {args.mode} fixture artifacts: {output}", flush=True)
    if error:
        raise error
    return 0 if validation["status"] in ("passed", "incomplete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
