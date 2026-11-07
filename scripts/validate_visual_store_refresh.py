"""Protected native repair quote diagnostic at the first seed-one store.

Requires a new output directory and the ordinary 1280x720 seed-one layout.
Use only at an operator-approved game boundary. No actor or model is invoked.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

from ftl_bench import visual_evidence as evidence
from ftl_bench.challenge_setup import DeterministicSetupSession, packet_proof, receipt_proof
from ftl_bench.installation import runtime_fingerprint
from ftl_bench.native_acceptance import CAPABILITIES, source_identity
from ftl_bench.protected_game import ProtectedGame, _processes
from ftl_bench.session import ftl_user_folder
from ftl_bench.trajectory import TrajectoryRecorder
from ftl_bench.visual_session import ExternalInputInterference, VisualSession

import validate_store_arrival as arrival
from validate_store_arrival import position, prepare, single_continue, visual_record


SCOPE = {"classification": "diagnostic_only", "fixture_only": True, "model_calls": 0,
         "valid_for_model_comparison": False, "valid_for_full_game_comparison": False}
ROOT = Path(__file__).resolve().parents[1]
HULL_EDITS = ((30, 27), (27, 22))
QUOTES = {"one": "Repair Partial Hull", "all": "Repair Entire Hull"}
COORDINATES = {"continue": (405, 317), "close": (853, 570), "open": (752, 48),
               "repair-all": (428, 453)}

# This diagnostic-only append has no influence until an explicitly armed,
# acknowledged-capture-bound zero-input packet arrives while already frozen.
# Its only gameplay writes set the disposable hull pair's current value.
FIXTURE_LUA = r'''
do
 local fixture={phase=0}
 local originalReader=Hyperspace.read_json_action
 local originalWriter=Hyperspace.benchmark_write_visual_observation
 local function applyFixture(packet)
  if fixture.phase>=2 or fixture.error or S.observation_mode~="visual-v1"
   or S.frame_budget~=0 or not S.visual_capture then return end
  if type(packet)~="table" or packet.store_refresh_fixture_phase~=fixture.phase+1
   or packet.observation_mode~="visual-v1" or type(packet.seq)~="number"
   or packet.seq~=S.last_applied_seq+1 or packet.advance_frames~=0
   or type(packet.actions)~="table" or next(packet.actions)
   or packet.expected_capture_id~=S.visual_capture.capture_id
   or packet.expected_external_input_generation~=S.visual_capture.external_input_generation then return end
  local ok,err=pcall(function()
   local caps=visual_capabilities()
   assert(caps and caps.external_input_guard==true and caps.external_input_detected==false
    and caps.external_input_generation==packet.expected_external_input_generation
    and caps.width==S.visual_capture.width and caps.height==S.visual_capture.height
    and caps.world_updates==S.visual_capture.world_updates,"guard, dimensions, or world changed")
   assert(not DeterministicSetup.owns() and not DeterministicSetup.failed(),"setup has not handed off")
   assert(Hyperspace.App.gui.bPaused and not visual_blocked(),"fixture requires a quiet closed store")
   local store=Hyperspace.benchmark_store_read()
   local hull=Hyperspace.ships.player.ship.hullIntegrity
   local before=fixture.phase==0 and 30 or 27
   local after=fixture.phase==0 and 27 or 22
   assert(type(store)=="string","native store read unavailable")
   assert((fixture.phase==0 and store=="") or (fixture.phase==1 and store~=""),"unexpected store location")
   assert(hull.first==before and hull.second==30,"unexpected disposable hull")
   hull.first=after
   assert(hull.first==after,"native hull write unavailable")
   fixture.phase=fixture.phase+1
   fixture.last_edit={seq=packet.seq,before=before,after=after}
  end)
  if not ok then fixture.error=tostring(err) end
 end
 Hyperspace.read_json_action=function(...)
  local payload=originalReader(...)
  if type(payload)=="string" and string.find(payload,'"store_refresh_fixture_phase"',1,true) then
   local ok,packet=pcall(json.decode,payload)
   if ok then applyFixture(packet) end
  end
  return payload
 end
 Hyperspace.benchmark_write_visual_observation=function(payload,...)
  local obs=json.decode(payload)
  obs.store_refresh_fixture={phase=fixture.phase,error=fixture.error,last_edit=fixture.last_edit,
   running_time=Hyperspace.FPS.RunningTime}
  return originalWriter(json.encode(obs),...)
 end
end
'''


def fixture_bridge(production: bytes) -> bytes:
    return production + FIXTURE_LUA.encode()


class StoreSetupSession(DeterministicSetupSession):
    fixture_phase = None

    def arm_fixture(self, phase):
        require(self.fixture_phase is None and phase in (1, 2), "Fixture phase already armed or invalid")
        self.fixture_phase = phase

    def _write_action_atomic(self, payload):
        if self.fixture_phase is not None:
            require(payload.get("observation_mode") == "visual-v1" and payload.get("actions") == []
                    and payload.get("advance_frames") == 0 and payload.get("expected_capture_id") is not None
                    and isinstance(payload.get("expected_external_input_generation"), str),
                    "Fixture edit requires a capture-bound zero-input packet")
            payload = {**payload, "store_refresh_fixture_phase": self.fixture_phase}
            self.fixture_phase = None
        return super()._write_action_atomic(payload)


def repair_quotes(raw):
    boxes = (raw.get("store") or {}).get("buy") or []
    result = {}
    for key, title in QUOTES.items():
        matches = [box for box in boxes if box.get("name") == title]
        if (len(matches) != 1 or type(matches[0].get("price")) is not int
                or matches[0]["price"] < 0 or type(matches[0].get("i")) is not int
                or type(matches[0].get("count")) is not int):
            raise RuntimeError(f"Missing or ambiguous native repair box {title}")
        result[key] = {name: matches[0][name] for name in ("i", "price", "count")}
    require(result["one"]["i"] != result["all"]["i"], "Native repair boxes share an index")
    return result


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def readback(frame):
    raw = frame.observation.raw
    ship = raw["player_ship"]
    return {
        "capture": frame.reference, "seq": frame.observation.last_action_seq, "paused": raw["paused"],
        "clock": raw["visual"], "fixture": raw["store_refresh_fixture"],
        "evaluator": raw["visual_evaluator"], "location": position(raw),
        "hull": ship["hull"], "resources": ship["resources"], "store": raw.get("store"),
    }


def account(before, after, actions, requested):
    clock, previous = after["clock"], before["clock"]
    actual = clock["actual_frames"]
    require(type(actual) is int and 0 <= actual <= requested and clock["requested_frames"] == requested
            and int(clock["world_updates"]) - int(previous["world_updates"]) == actual
            and clock["world_updates"] == clock["simulated_updates"],
            "Native world/frame accounting differs")
    generation = previous["external_input_generation"]
    require(isinstance(generation, str) and clock["external_input_generation"] == generation
            and previous["external_input_detected"] is False and clock["external_input_detected"] is False,
            "Native external-input guard changed")
    expected = [{"index": i, "type": action["type"], "status": "delivered"}
                for i, action in enumerate(actions)]
    require(clock["input_feedback"] == expected, "Native input acknowledgements differ")
    require(after["seq"] == before["seq"] + 1 and after["paused"] is True,
            "Native capture sequence or pause differs")
    old_time, new_time = (row["fixture"]["running_time"] for row in (before, after))
    require(all(type(t) in (int, float) and math.isfinite(t) for t in (old_time, new_time))
            and new_time >= old_time and (actual > 0 or new_time == old_time),
            "Native unpaused timer changed without a world update")


class StoreProbe:
    def __init__(self, session, transport, recorder, output, frame):
        self.session, self.transport, self.recorder, self.output = session, transport, recorder, output
        self.frame = frame
        self.proof = {**SCOPE, "status": "running", "coordinates": COORDINATES,
                      "initial": readback(frame), "steps": []}
        recorder.record("reset", [], frame.observation, visual=visual_record("image", frame, frame, [], 0))
        self.save()

    def save(self, **fields):
        self.proof.update(fields)
        evidence.write(self.output / "store-refresh-proof.json", self.proof)
        return self.proof

    def step(self, label, frames=0, *, click=None):
        actions = []
        if click:
            x, y = COORDINATES[click]
            actions.append({"type": "click", "x": x, "y": y, "button": "left", "modifiers": []})
        before = self.frame
        row = {"label": label, "actions": actions, "requested_frames": frames,
               "before_image": before.reference}
        self.proof["steps"].append(row)
        self.save()
        self.frame = self.transport.step(before, actions, frames)
        after = readback(self.frame)
        row["after"] = after
        self.recorder.record("step", actions, self.frame.observation, thought=label, pre_obs=before.observation,
                             visual=visual_record("image", before, self.frame, actions, frames))
        self.save()
        account(readback(before), after, actions, frames)
        require(not after["fixture"].get("error"), f"Disposable fixture error at {label}")
        return after

    def edit_hull(self, phase):
        before = readback(self.frame)
        start, end = HULL_EDITS[phase - 1]
        seq = before["seq"] + 1
        require(before["evaluator"]["store_open"] is False
                and before["hull"] == {"current": start, "max": 30}
                and before["fixture"]["phase"] == phase - 1,
                "Closed-store disposable hull prerequisite differs")
        self.session.arm_fixture(phase)
        after = self.step(f"closed-hull-{start}-to-{end}")
        require(after["fixture"].get("phase") == phase
                and after["fixture"].get("last_edit") == {"seq": seq, "before": start, "after": end}
                and after["evaluator"]["store_open"] is False and after["location"] == before["location"]
                and after["resources"] == before["resources"] and after["store"] == before["store"]
                and after["hull"] == {"current": end, "max": 30},
                "Native fixture did not change only the intended closed-store hull")
        return after


def run_probe(session, transport, recorder, output, departure, target, fuel):
    frame = transport.capture()
    handoff = {"receipt": receipt_proof(frame.observation.raw, require_visual=False),
               "packets": packet_proof(frame.observation.raw, session.setup_packets)}
    evidence.write(output / "handoff-setup-proof.json", handoff)
    require(all(item["passed"] for item in handoff.values()), "Native setup handoff evidence differs")
    require((frame.reference["width"], frame.reference["height"]) == (1280, 720),
            "Native STORE input calibration requires exactly 1280x720")
    probe = StoreProbe(session, transport, recorder, output, frame)
    probe.save(departure=departure, target=target, departure_fuel=fuel)
    try:
        probe.edit_hull(1)
        # The historical first store stages during warp before frame 150 and
        # settles near frame 243. Inspect bounded intermediate native states.
        hidden = probe.step("initial-warp", 120)
        for _ in range(8):
            state = hidden["evaluator"]
            if state["store_open"] is True and state["player_jumping"] is True:
                break
            require(state["choice_window_open"] is not True, "Settled without observing a staged hidden store")
            hidden = probe.step("seek-hidden-store-in-warp", 15)
        else:
            raise RuntimeError("Bounded warp did not show the staged hidden store")
        require(hidden["evaluator"]["blocked_reason"] != "store_open"
                and hidden["resources"]["fuel"] == fuel - 1,
                "Hidden store blocked warp or did not retain one fuel charge")
        settled = probe.step("advance-through-hidden-store", 600)
        require(settled["clock"]["actual_frames"] > 0 and settled["location"] == target
                and settled["resources"]["fuel"] == fuel - 1 and settled["hull"] == {"current": 27, "max": 30}
                and settled["evaluator"]["store_open"] is True and settled["evaluator"]["player_jumping"] is False
                and settled["evaluator"]["choice_window_open"] is True,
                "Hidden store failed to permit a bounded natural arrival")
        time.sleep(.35)  # native UI debounce, no world budget
        probe.step("settled-choice-zero-capture")
        require(single_continue(probe.frame.observation.raw), "Unknown settled arrival choice")
        initial = probe.step("ordinary-continue-one-frame", 1, click="continue")
        require(initial["clock"]["actual_frames"] == 1 and initial["evaluator"]["choice_window_open"] is False
                and initial["evaluator"]["store_open"] is True,
                "Queued Continue did not settle in one native frame")
        original = repair_quotes(initial)
        require(original["one"]["price"] == 2 and original["all"]["price"] == 6
                and original["all"]["count"] > 0,
                "Positive-frame first-store cache did not quote six for three hull")
        blocked = probe.step("visible-store-blocks-advance", 600)
        require(blocked["clock"]["actual_frames"] == 0 and blocked["evaluator"]["blocked_reason"] == "store_open"
                and repair_quotes(blocked) == original, "Visible store did not preserve the native clock blocker")
        probe.step("ordinary-store-close", click="close")
        damaged = probe.edit_hull(2)
        require(repair_quotes(damaged) == original, "Closed-store repair cache changed before reopening")
        reopened = probe.step("ordinary-store-reopen-zero-frame", click="open")
        current = repair_quotes(reopened)
        expected_charge = (reopened["hull"]["max"] - reopened["hull"]["current"]) * current["one"]["price"]
        require(reopened["evaluator"]["store_open"] is True and reopened["hull"] == damaged["hull"]
                and reopened["resources"] == damaged["resources"] and reopened["location"] == target
                and reopened["resources"]["scrap"] >= 16 and current["one"] == original["one"]
                and current["all"]["i"] == original["all"]["i"] and current["all"]["count"] > 0
                and expected_charge == 16 and current["all"]["price"] in (6, expected_charge),
                "Reopened native repair purchase prerequisites differ")
        repaired = probe.step("ordinary-fix-all-zero-frame", click="repair-all")
        debit = reopened["resources"]["scrap"] - repaired["resources"]["scrap"]
        require(repaired["hull"] == {"current": 30, "max": 30}
                and repaired["resources"] == {**reopened["resources"], "scrap": reopened["resources"]["scrap"] - debit}
                and repaired["evaluator"]["store_open"] is True and repaired["location"] == target,
                "Native Fix All did not repair only hull and debit scrap")
        probe.save(repair={"initial": original, "reopened": current, "expected_charge": expected_charge,
                           "actual_charge": debit, "hull_before": reopened["hull"], "hull_after": repaired["hull"]})
        final = probe.step("final-store-close-zero-frame", click="close")
        require(final["evaluator"]["store_open"] is False and final["hull"] == repaired["hull"]
                and final["resources"] == repaired["resources"], "Final close changed gameplay or left the store open")
        if current["all"]["price"] == debit == 6:
            return probe.save(status="reproduced", reason="stale_repair_all_quote_and_charge")
        require(current["all"]["price"] == debit == expected_charge, "Native refreshed quote and actual charge differ")
        return probe.save(status="passed", reason="current_repair_all_quote_and_charge")
    except BaseException as error:
        probe.save(status="error", reason=str(error))
        raise


def validate(output: Path):
    require(arrival.ROOT.resolve() == ROOT, "Run with this diagnostic checkout's harness source imports")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
    driver = Path(__file__)
    arrival_driver = Path(arrival.__file__)
    archived_driver = output / "probe-driver.py"
    archived_driver.write_bytes(driver.read_bytes())
    archived_arrival = output / "store-arrival-helper.py"
    archived_arrival.write_bytes(arrival_driver.read_bytes())
    sources = evidence.snapshot_sources(ROOT, output)
    bridge = output / "fixture-bridge.lua"
    production = source.read_bytes()
    require(evidence.digest(output / "sources" / source.relative_to(ROOT)) == evidence.digest(source),
            "Production bridge changed while archiving")
    bridge.write_bytes(fixture_bridge(production))
    deployed_sha = evidence.digest(bridge)
    meta = {**SCOPE, "seed": 1, "provider": "none", "model": None, "started_at": evidence.stamp(),
            "fixture_hull_edits": HULL_EDITS, "probe_driver_sha256": evidence.digest(archived_driver),
            "arrival_helper_sha256": evidence.digest(archived_arrival),
            "deployed_bridge_sha256": deployed_sha, "source_files_sha256": evidence.source_digest(sources)}
    recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
    protected = None
    errors = []
    result = None
    cleanup = "not_run"
    try:
        protected = ProtectedGame(ftl_user_folder(), output / "save-backup", bridge)
        before = evidence.inventory(protected, source)
        evidence.write(output / "before-inventory.json", {"checked_at": evidence.stamp(), "files_sha256": before})
        require(all(before[str(protected.game / name)] for name in evidence.RUNTIME_FILES),
                "Installed runtime inventory incomplete")
        fingerprint = runtime_fingerprint(ROOT)
        evidence.write(output / "prelaunch-runtime-fingerprint.json", fingerprint)
        build = fingerprint.get("native_build") or {}
        require(build.get("matches_installed_dll") is True and all(
            type(build.get(k)) is type(v) and build[k] == v for k, v in CAPABILITIES.items()),
            "Installed native provenance or capabilities differ")
        with protected.protected():
            try:
                protected.launch()
                fingerprint = runtime_fingerprint(ROOT)
                evidence.write(output / "runtime-fingerprint.json", fingerprint)
                require((fingerprint.get("bridge_lua") or {}).get("sha256") == deployed_sha
                        and fingerprint.get("native_build") == build
                        and all(evidence.digest(protected.game / name) == before[str(protected.game / name)]
                                for name in evidence.RUNTIME_FILES),
                        "Deployed fixture bridge or runtime differs from recorded bytes")
                session = StoreSetupSession(ftl_user_folder(), step_timeout=30)
                departure, target, fuel = prepare(session, output, recorder)
                result = run_probe(session, VisualSession(session, output), recorder, output, departure, target, fuel)
            except BaseException as error:
                errors.append(error)
                if isinstance(error, ExternalInputInterference) and error.observation is not None:
                    evidence.write(output / "external-interference-observation.json", error.observation.raw)
                raise
    except BaseException as error:
        if not errors or error is not errors[0]:
            errors.append(error)
    if protected is not None and protected.manifest:
        cleanup = "not_verified"
        try:
            processes = _processes()
            require(not processes and not protected.pending_launch.exists(), "Game or pending launch remains")
            restoration = json.loads((protected.backup / "restoration.json").read_text(encoding="utf-8"))
            after = evidence.inventory(protected, source)
            evidence.write(output / "after-inventory.json", {"checked_at": evidence.stamp(), "files_sha256": after,
                           "processes": processes, "pending_launch": False})
            require(restoration.get("verified") is True and before == after and source_identity(ROOT) == sources
                    and evidence.digest(driver) == meta["probe_driver_sha256"]
                    and evidence.digest(arrival_driver) == meta["arrival_helper_sha256"],
                    "Post-cleanup save, bridge, runtime or source verification failed")
            cleanup = "verified"
        except BaseException as error:
            errors.append(error)
    status = "error" if errors else result["status"]
    reason = str(errors[0]) if errors else result["reason"]
    recorder.finish(status="error" if errors else "completed", reason=reason, model_calls=0)
    meta.update(status=status, reason=reason, cleanup=cleanup, finished_at=evidence.stamp(),
                errors=[str(error) for error in errors], source_files=sources)
    meta["artifact_sha256"] = {path.relative_to(output).as_posix(): evidence.digest(path)
                               for path in sorted(output.rglob("*")) if path.is_file()}
    evidence.write(output / "validation.json", meta)
    if len(errors) > 1:
        raise BaseExceptionGroup("Native store-refresh diagnostic failed", errors)
    if errors:
        raise errors[0]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = validate(args.output)
    print(f'{result["status"]}: {args.output / "validation.json"}')
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
