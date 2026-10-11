"""Protected visual acceptance fixture; injected STORE setup is never benchmark data.

Examples (from a checkout with its harness environment active):
  python scripts/validate_visual_live.py --capture-only
  python scripts/validate_visual_live.py --model gpt-6.1-sol --max-decisions 30
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
sys.path.insert(0, str(ROOT / "adapter"))

from ftl_bench.installation import runtime_fingerprint
from ftl_bench.protected_game import ProtectedGame
from ftl_bench.scenario import Scenario, SubObjective
from ftl_bench.session import AgentSession, ftl_user_folder, jump, fire_weapon, set_system_power
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory
from ftl_bench.visual_session import ExternalInputInterference, VisualSession
from run_visual import codex_runtime_identity, run_loop, visual_record
from visual_agent import CodexVisualAgent


STORE_FIXTURE = b'''\nlocal storeFixtureDone=false
local storeFixtureOldTick=_G.ftl_bench_tick
_G.ftl_bench_tick=function()
 local app=Hyperspace.App
 if not storeFixtureDone and app.world.bStartedGame and not app.gui.choiceBoxOpen then
  storeFixtureDone=true
  Hyperspace.CustomEventsParser.GetInstance():LoadEvent(app.world,"STORE",false,1)
  _G.ftl_bench_state.obs_fresh=false
 end
 storeFixtureOldTick()
end
'''


def quiet_store_prerequisite(obs):
    enemy = obs.enemy_ship or {}
    nav = (obs.raw.get("economy") or {}).get("navigation") or {}
    crew = (obs.player_ship or {}).get("crew") or []
    healthy = (len(crew) == 3 and all(type(c.get("health_current")) in (int, float)
               and c["health_current"] > 0 and c["health_current"] == c.get("health_max") for c in crew))
    current, maximum = nav.get("drive_current"), nav.get("drive_max")
    return ((obs.map or {}).get("hazard") == "none"
            and (not enemy or enemy.get("hostile") is False or enemy.get("destroyed") is True)
            and healthy and type(current) in (int, float) and type(maximum) in (int, float)
            and 0 <= current < maximum)


def prepare_store(session, source: Path, output: Path, *, route="quiet"):
    """Reach partial drive charge normally; inject only a normal STORE encounter."""
    setup = []
    def keep(label, observation):
        setup.append({"label": label, "obs": observation.raw})
        (output / "setup.json").write_text(json.dumps(setup, indent=2), encoding="utf-8")
        return observation
    def resolve(obs):
        for _ in range(20):
            if not obs.choice_box_open:
                return obs
            time.sleep(.35)
            eligible = [c for c in (obs.event or {}).get("choices", []) if c.get("enabled") is True]
            if not eligible:
                raise RuntimeError("Fixture event has no enabled choice")
            obs = keep("setup-event", session.choose_event(eligible[0]["index"], 60))
        raise RuntimeError("Fixture event did not settle")
    def fresh():
        session.reset_episode(seed=1)
        session.reset()
        obs = keep("fresh-start", resolve(session.step([], 30)))
        for _ in range(30):
            if obs.raw["economy"]["navigation"]["can_jump"]:
                return obs
            obs = keep("setup-charge", session.step([], 300))
        raise RuntimeError("Fixture could not reach a normally charged drive")

    if route == "quiet":
        # This selection is a diagnostic prerequisite search, never actor input
        # or benchmark data. Each candidate starts a fresh seed-1 episode.
        for beacon in (0, 1, 2, 4):
            obs = fresh()
            obs = resolve(keep(f"quiet-hop-{beacon}", session.step([jump(beacon)], 300)))
            if quiet_store_prerequisite(obs):
                break
        else:
            raise RuntimeError("No quiet partial-charge fixture prerequisite was found")
    elif route == "combat":
        obs = fresh()
        obs = session.step([set_system_power(5, 0), set_system_power(1, 2),
                        set_system_power(3, 3), set_system_power(0, 2)], 0)
        before = dict(obs.raw["ftl_score_components"])
        obs = resolve(keep("setup-arrival", session.step([jump(3)], 300)))
        for _ in range(15):
            if obs.enemy_ship and obs.enemy_ship.get("destroyed") is True:
                break
            obs = resolve(obs)
            obs = keep("setup-combat", session.step([fire_weapon(0, 0), fire_weapon(1, 1)], 720))
        if not obs.enemy_ship or obs.enemy_ship.get("destroyed") is not True:
            raise RuntimeError("Fixture normal combat prerequisite failed")
        for _ in range(24):
            obs = resolve(obs)
            score = obs.raw["ftl_score_components"]
            if (score["ships_destroyed"] > before["ships_destroyed"]
                    and score["scrap_collected"] > before["scrap_collected"]):
                break
            obs = keep("setup-reward", session.step([], 120))
        score = obs.raw["ftl_score_components"]
        if not (score["ships_destroyed"] > before["ships_destroyed"]
                and score["scrap_collected"] > before["scrap_collected"]):
            raise RuntimeError("Fixture combat reward did not settle")
    else:
        raise ValueError("Unknown store fixture route")
    nav = obs.raw["economy"]["navigation"]
    if nav["drive_current"] >= nav["drive_max"]:
        raise RuntimeError("Fixture did not reach a naturally partial drive charge")
    fixture = source.read_bytes() + STORE_FIXTURE
    (output / "fixture-bridge.lua").write_bytes(fixture)
    (output / "fixture.json").write_text(json.dumps({"fixture_only": True,
        "valid_for_model_comparison": False,
        "route": route,
        "prerequisite": "One normal STORE event after ordinary travel; optional diagnostic combat route; no state overrides",
        "bridge_sha256": hashlib.sha256(fixture).hexdigest()}, indent=2), encoding="utf-8")
    (session.user_folder / "ftl_bench_dev.lua").write_bytes(fixture)
    (session.user_folder / "ftl_bench_reload").write_text("", encoding="utf-8")
    time.sleep(1)
    obs = keep("store-start", resolve(session.step([], 30)))
    return obs


def _resources(obs):
    return (obs.get("player_ship") or {}).get("resources") or {}


def prepare_capture_world(session, transport, recorder, output: Path):
    """Resolve the intro, then establish oxygen drain through the rendered UI."""
    session.reset_episode(seed=1)
    obs = session.reset()
    setup = [{"label": "fresh-start", "obs": obs.raw}]
    # Reset can acknowledge the ship before the first game loop opens its intro
    # event. Advance normally once before deciding that no modal needs resolving.
    obs = session.step([], 30)
    setup.append({"label": "settle-initial-event", "obs": obs.raw})
    for _ in range(20):
        if not obs.choice_box_open:
            break
        time.sleep(.35)
        choices = [c for c in (obs.event or {}).get("choices", []) if c.get("enabled") is True]
        if not choices:
            raise RuntimeError("Capture fixture intro has no enabled choice")
        obs = session.choose_event(choices[0]["index"], 30)
        setup.append({"label": "normal-intro-choice", "obs": obs.raw})
    if obs.choice_box_open or not obs.game_started:
        raise RuntimeError("Capture fixture did not reach live gameplay outside the intro modal")
    before = transport.capture()
    recorder.record("reset", [], before.observation,
        visual={"observation_mode": "image", "before": before.reference,
                "after": before.reference, "inputs": [],
                "advance": {"requested_frames": 0, "actual_frames": 0},
                "outcome": {"status": "unknown", "summary": "Initial rendered screenshot before fixture inputs."}})
    if (before.reference.get("width"), before.reference.get("height")) != (1280, 720):
        raise RuntimeError("Capture fixture oxygen-button calibration requires a 1280x720 native screenshot")
    # Calibrated from the actual Kestrel screenshot in render-probe-20261009T0232.
    # Native ordinary right-click removes requested power, unlike the older
    # semantic helper, whose temporary reduction is restored by power management.
    actions = [{"type": "click", "x": 198, "y": 682, "button": "right", "modifiers": []}]
    after = transport.step(before, actions, 60)
    recorder.record("step", actions, after.observation, pre_obs=before.observation,
                    visual=visual_record("image", before, after, actions, 60))
    setup.append({"label": "normal-ui-oxygen-rightclick-and-60-frame-drain", "obs": after.observation.raw})
    (output / "setup.json").write_text(json.dumps(setup, indent=2), encoding="utf-8")
    old_o2 = (before.observation.player_ship or {}).get("oxygen_pct")
    new_o2 = (after.observation.player_ship or {}).get("oxygen_pct")
    systems = (after.observation.player_ship or {}).get("systems") or []
    oxygen_off = any(s.get("id") == 2 and s.get("power") == 0 for s in systems)
    if (after.observation.choice_box_open or not oxygen_off or type(old_o2) not in (int, float)
            or type(new_o2) not in (int, float) or not 0 < new_o2 < old_o2):
        raise RuntimeError("Capture fixture could not prove normal oxygen drain outside a modal")
    (output / "fixture.json").write_text(json.dumps({
        "fixture_only": True, "valid_for_model_comparison": False,
        "prerequisite": "Normal intro choice; ordinary right-click on the calibrated oxygen UI button; 60 normal simulation frames demonstrate active oxygen loss.",
        "ui_calibration": {"width": 1280, "height": 720, "oxygen_button": {"x": 198, "y": 682}},
        "oxygen_before": old_o2, "oxygen_after": new_o2, "oxygen_power": 0,
        "modal_open": False, "state_overrides": False}, indent=2), encoding="utf-8")
    return after


def _store_open(obs):
    return (obs.get("visual_evaluator") or {}).get("store_open")


def verify_normal_controls(transport, recorder, frame, output):
    """Calibrated Kestrel UI checks; all execution uses ordinary visual inputs."""
    checks = {}
    evidence = []

    def perform(actions, frames):
        nonlocal frame
        before = frame
        frame = transport.step(before, actions, frames)
        recorder.record("step", actions, frame.observation, pre_obs=before.observation,
                        visual=visual_record("image", before, frame, actions, frames))
        evidence.append({"actions": actions, "before": before.reference, "after": frame.reference})
        return frame.observation.raw

    def oxygen_power(obs):
        return next((s.get("power") for s in (obs.get("player_ship") or {}).get("systems", [])
                     if s.get("id") == 2), None)

    # The prior fixture right-click turned oxygen off. Use the hotkeys printed in
    # that captured control's tooltip: F adds power, Shift+F removes it.
    obs = perform([{"type": "key", "key": "f", "modifiers": []}], 0)
    checks["ordinary_key_adds_oxygen_power"] = oxygen_power(obs) == 1
    obs = perform([{"type": "key", "key": "f", "modifiers": ["shift"]}], 0)
    checks["shift_key_removes_oxygen_power"] = oxygen_power(obs) == 0
    obs = perform([{"type": "key", "key": "f", "modifiers": []}], 0)
    checks["ordinary_key_restores_oxygen_power"] = oxygen_power(obs) == 1
    crew = (obs.get("player_ship") or {}).get("crew") or []
    selected = {c["id"] for c in crew if c.get("room") in (10, 14) and c.get("player_owned") is True}
    pilots = {c["id"] for c in crew if c.get("room") == 0 and c.get("player_owned") is True}
    if len(selected) != 2 or len(pilots) != 1:
        raise RuntimeError("Crew drag fixture requires the verified starting Kestrel crew positions")
    # Bounds were read from the actual 1280x720 Kestrel capture: the rectangle
    # includes engine and weapons crew, while excluding the cockpit crew.
    perform([{"type": "drag", "x": 385, "y": 312, "to_x": 551, "to_y": 375,
              "button": "left", "modifiers": []}], 0)
    obs = perform([{"type": "click", "x": 665, "y": 307, "button": "right", "modifiers": []}], 600)
    rooms = {c.get("id"): c.get("room") for c in (obs.get("player_ship") or {}).get("crew", [])}
    checks["drag_selected_crew_reach_medbay"] = all(rooms.get(i) == 4 for i in selected)
    checks["unselected_pilot_stays_in_cockpit"] = all(rooms.get(i) == 0 for i in pilots)
    result = {"fixture_only": True, "valid_for_model_comparison": False,
              "checks": checks, "passed": all(checks.values()), "evidence": evidence,
              "calibration": {"width": 1280, "height": 720, "ship": "Kestrel A"}}
    (output / "normal-controls-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["passed"]:
        raise RuntimeError("Normal key/modifier/drag crew control acceptance failed")
    return checks


def _position(obs):
    pos = (obs.get("map") or {}).get("current_pos")
    if (not isinstance(pos, dict) or type(pos.get("x")) not in (int, float)
            or type(pos.get("y")) not in (int, float)):
        return None
    return (pos["x"], pos["y"])


def _native_ready(obs):
    nav = (obs.get("economy") or {}).get("navigation") or {}
    current, maximum = nav.get("drive_current"), nav.get("drive_max")
    return (nav.get("can_jump") is True and type(current) in (int, float)
            and type(maximum) in (int, float) and maximum > 0 and current >= maximum)


def paused_world_signature(obs):
    """Stable gameplay facts only; render counters and UI animation may change."""
    ship = obs.get("player_ship") or {}
    navigation = (obs.get("economy") or {}).get("navigation") or {}
    return {"hull": ship.get("hull"), "resources": ship.get("resources"), "oxygen_pct": ship.get("oxygen_pct"),
            "room_oxygen": [{"room_id": room.get("room_id"), "oxygen": room.get("oxygen")}
                            for room in ship.get("rooms", [])],
            "location": {key: (obs.get("map") or {}).get(key) for key in ("current_pos", "sector", "choosing_new_sector")},
            "crew": [{key: c.get(key) for key in ("id", "room", "health_current", "dead")}
                     for c in ship.get("crew", [])],
            "systems": [{key: s.get(key) for key in ("id", "power", "damage", "ion")}
                        for s in ship.get("systems", [])],
            "ui": obs.get("visual_evaluator"),
            "navigation_context": {key: navigation.get(key) for key in ("reason", "can_jump", "enemy_defeat_pending")},
            "world_updates": (obs.get("visual") or {}).get("world_updates"),
            "drive_current": navigation.get("drive_current"), "drive_max": navigation.get("drive_max"),
            "ftl_score": obs.get("ftl_score"), "score_components": obs.get("ftl_score_components")}


def check_paused_world(before, after, *, same_capture=True):
    old, new = paused_world_signature(before), paused_world_signature(after)
    visual_before, visual_after = before.get("visual") or {}, after.get("visual") or {}
    hull = old.get("hull") or {}
    resources = old.get("resources") or {}
    present = (type(hull.get("current")) in (int, float) and type(resources.get("fuel")) is int
               and type(old.get("drive_current")) in (int, float)
               and type(old.get("drive_max")) in (int, float)
               and type(old.get("oxygen_pct")) in (int, float)
               and type(old.get("ftl_score")) in (int, float)
               and isinstance(old.get("score_components"), dict))
    checks = {"native_world_fields_present": present,
              "paused_before_and_after": before.get("paused") is True and after.get("paused") is True,
              "world_unchanged": old == new}
    if same_capture:
        checks["same_action_ack"] = before.get("last_action_seq") == after.get("last_action_seq")
        checks["same_capture_identity"] = (visual_before.get("capture_id") is not None
            and visual_before.get("capture_id") == visual_after.get("capture_id")
            and visual_before.get("frame_id") == visual_after.get("frame_id"))
    return {"checks": checks, "passed": all(checks.values()), "before": old, "after": new}


def verify_transition_boundary(session, transport, recorder, output):
    """A queued jump must stay frozen through inference and zero-frame inputs."""
    frame = transport.capture()
    if ((frame.reference.get("width"), frame.reference.get("height")) != (1280, 720)
            or _position(frame.observation.raw) != (49, 231)):
        raise RuntimeError("Transition fixture requires the calibrated seed-1 quiet store at 49,231")
    recorder.record("reset", [], frame.observation)

    def step(actions, frames):
        nonlocal frame
        before = frame
        frame = transport.step(before, actions, frames)
        recorder.record("step", actions, frame.observation, pre_obs=before.observation,
                        visual=visual_record("image", before, frame, actions, frames))
        return frame

    def click(x, y):
        return [{"type": "click", "x": x, "y": y, "button": "left", "modifiers": []}]

    step(click(853, 570), 0)
    step([], 600)
    if not _native_ready(frame.observation.raw):
        raise RuntimeError("Transition fixture failed to charge the drive normally")
    step(click(574, 50), 0)
    if (frame.observation.raw.get("visual_evaluator") or {}).get("map_open") is not True:
        raise RuntimeError("Transition fixture failed to open the map")
    departure = frame
    pending = step(click(511, 430), 0)
    time.sleep(3)
    published = session.observe()
    after_zero = step([], 0)
    pause_proof = check_paused_world(pending.observation.raw, after_zero.observation.raw, same_capture=False)
    result = {"fixture_only": True, "valid_for_model_comparison": False,
              "checks": {"queued_jump_frozen_through_idle_and_zero_frames": pause_proof["passed"]},
              "idle_seconds": 3, "pause_proof": pause_proof,
              "pending": pending.reference, "after_zero": after_zero.reference,
              "idle_published_location": _position(published.raw)}

    def save():
        result["status"] = "passed" if all(result["checks"].values()) else "failed"
        (output / "transition-boundary-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    save()
    if not pause_proof["passed"]:
        raise RuntimeError("Queued jump changed gameplay during paused inference or zero-frame input")
    # Exercise the boundary once a requested frame has started the transition,
    # too: FTL historically updates its jump tracker from ship rendering.
    mid_jump = step([], 1)
    actual_frames = mid_jump.observation.raw["visual"]["actual_frames"]
    time.sleep(3)
    after_mid_zero = step([], 0)
    mid_proof = check_paused_world(mid_jump.observation.raw, after_mid_zero.observation.raw, same_capture=False)
    result["mid_jump_pause_proof"] = mid_proof
    result["mid_jump"] = mid_jump.reference
    result["after_mid_zero"] = after_mid_zero.reference
    result["checks"]["started_jump_frozen_through_idle_and_zero_frames"] = mid_proof["passed"]
    save()
    if not mid_proof["passed"]:
        raise RuntimeError("Started jump changed gameplay during paused inference or zero-frame input")
    for _ in range(5):
        step([], 600)
        actual_frames += frame.observation.raw["visual"]["actual_frames"]
        if _position(frame.observation.raw) == (126, 306):
            break
    result["actual_advance_frames"] = actual_frames
    result["checks"].update(
        bounded_frames_complete_selected_jump=(actual_frames > 0 and _position(frame.observation.raw) == (126, 306)),
        exactly_one_fuel_spent=(_resources(frame.observation.raw).get("fuel") == _resources(departure.observation.raw).get("fuel") - 1))
    result["arrival"] = frame.reference
    save()
    if result["status"] != "passed":
        raise RuntimeError("Bounded simulation did not complete the selected native jump")
    recorder.finish(reason="transition_boundary_fixture")
    return result


def validate_store_fixture(records, termination: str) -> dict:
    """Evaluator-only acceptance; native state is never passed to the visual actor."""
    rows = [r for r in records if isinstance(r.get("obs"), dict)]
    checks = {"store_open_at_start": False, "initial_drive_partially_charged": False,
              "exactly_one_fuel_purchased_at_native_price": False,
              "store_closed_after_purchase": False, "store_close_mouse_input_recorded": False,
              "full_charge_observed_before_jump": False, "star_map_open_observed": False,
              "jump_to_connected_beacon": False, "jump_consumed_one_fuel": False,
              "cli_image_decisions_audited": False,
              "fixture_goal_observed": termination == "fixture_goal_observed"}
    evidence = {"fuel_purchase_records": [], "store_close_records": [], "jump_records": []}
    limitations = ["Inspect the recorded store-closing screenshot and click overlay to identify the CLOSE button."]
    if rows:
        first = rows[0]["obs"]
        checks["store_open_at_start"] = _store_open(first) is True
        nav = (first.get("economy") or {}).get("navigation") or {}
        current, maximum = nav.get("drive_current"), nav.get("drive_max")
        checks["initial_drive_partially_charged"] = (type(current) in (int, float)
            and type(maximum) in (int, float) and 0 <= current < maximum)
        purchases, fuel_gains, changes = [], [], []
        purchase_seen, closure_seen = False, False
        audited = []
        for previous, record in zip(rows, rows[1:]):
            before, after = previous["obs"], record["obs"]
            ar, br = _resources(before), _resources(after)
            fuel_before, fuel_after = ar.get("fuel"), br.get("fuel")
            fuel_delta = fuel_after - fuel_before if type(fuel_before) is int and type(fuel_after) is int else None
            if fuel_delta is not None and fuel_delta > 0:
                fuel_gains.append(fuel_delta)
            candidates = [item for item in (before.get("store") or {}).get("buy", [])
                          if isinstance(item, dict) and str(item.get("name", "")).casefold() in {"ftl fuel", "fuel"}
                          and type(item.get("price")) is int and item["price"] >= 0
                          and type(item.get("count")) is int and item["count"] > 0]
            if len(candidates) == 1 and _store_open(before) is True and fuel_delta == 1:
                price, item_index = candidates[0]["price"], candidates[0].get("i")
                after_item = next((item for item in (after.get("store") or {}).get("buy", [])
                                   if isinstance(item, dict) and item.get("i") == item_index), None)
                if (type(ar.get("scrap")) is int and type(br.get("scrap")) is int
                        and br["scrap"] == ar["scrap"] - price
                        and after_item is not None and after_item.get("count") == candidates[0]["count"] - 1):
                    purchases.append(record["i"])
                    purchase_seen = True
            if purchase_seen and _store_open(before) is True and _store_open(after) is False:
                evidence["store_close_records"].append(record["i"])
                closure_seen = True
                checks["store_closed_after_purchase"] = True
                inputs = (record.get("visual") or {}).get("inputs") or []
                if any(i.get("type") == "click" and i.get("button") == "left"
                       and i.get("delivery") == "delivered" for i in inputs):
                    checks["store_close_mouse_input_recorded"] = True
            if closure_seen:
                if _native_ready(after):
                    checks["full_charge_observed_before_jump"] = True
                if (after.get("visual_evaluator") or {}).get("map_open") is True:
                    checks["star_map_open_observed"] = True
            old_pos, new_pos = _position(before), _position(after)
            if old_pos is not None and new_pos is not None and old_pos != new_pos:
                changes.append(record["i"])
                connected = (before.get("map") or {}).get("connected_beacons") or []
                checks["jump_to_connected_beacon"] = (purchase_seen and closure_seen
                    and (before.get("map") or {}).get("sector") == (after.get("map") or {}).get("sector")
                    and any((b.get("pos_x"), b.get("pos_y")) == new_pos for b in connected if isinstance(b, dict)))
                # Charge may be consumed at warp start one record before arrival.
                eligible = [row["obs"] for row in rows if row["i"] < record["i"]
                            and _store_open(row["obs"]) is False and _position(row["obs"]) == old_pos]
                ready = [o for o in eligible if _native_ready(o)]
                checks["full_charge_observed_before_jump"] = bool(ready)
                checks["star_map_open_observed"] = any(
                    (o.get("visual_evaluator") or {}).get("map_open") is True for o in eligible)
                if ready:
                    departure_fuel = _resources(ready[-1]).get("fuel")
                    checks["jump_consumed_one_fuel"] = (type(departure_fuel) is int
                        and type(fuel_after) is int and fuel_after == departure_fuel - 1)
            if record.get("kind") == "step":
                model = record.get("model") or {}
                before_image = (record.get("visual") or {}).get("before") or {}
                audited.append(model.get("tool_use") is False and model.get("provider") == "codex"
                    and (model.get("image") or {}).get("sha256") == before_image.get("sha256")
                    and isinstance(before_image.get("sha256"), str) and bool(model.get("events")))
        checks["exactly_one_fuel_purchased_at_native_price"] = len(purchases) == 1 and fuel_gains == [1]
        checks["cli_image_decisions_audited"] = bool(audited) and all(audited)
        if len(changes) != 1:
            checks["jump_to_connected_beacon"] = False
        evidence["fuel_purchase_records"], evidence["jump_records"] = purchases, changes
    return {"fixture_only": True, "valid_for_model_comparison": False,
            "status": "passed" if all(checks.values()) else "incomplete", "termination": termination,
            "checks": checks, "evidence": evidence, "limitations": limitations}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    fixture_kind = parser.add_mutually_exclusive_group()
    fixture_kind.add_argument("--capture-only", action="store_true")
    fixture_kind.add_argument("--transition-only", action="store_true")
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--max-decisions", type=int, default=45)
    parser.add_argument("--max-idle-decisions", type=int, default=8)
    parser.add_argument("--store-setup", choices=("quiet", "combat"), default="quiet")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.max_decisions < 1:
        parser.error("max-decisions must be positive")
    if args.max_idle_decisions < 1:
        parser.error("max-idle-decisions must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = (args.output or ROOT / "harness/runs/validation/visual-v1" / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    native_fixture = args.capture_only or args.transition_only
    cli_identity = None if native_fixture else codex_runtime_identity()
    source = ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
    protected = ProtectedGame(ftl_user_folder(), output / "save-backup", source)
    scenario = Scenario(id="VISUAL-FIXTURE-capture" if args.capture_only else "VISUAL-FIXTURE-transition" if args.transition_only else "VISUAL-FIXTURE-store",
                        type="full_run", seed=1, goal=[SubObjective("victory", 1, kind="boolean")], budget_jumps=1)
    meta = {
        "track": "visual-v1", "observation_mode": "image", "fixture_only": True,
        "valid_for_model_comparison": False, "classification": "diagnostic_only",
        "provider": "none" if native_fixture else "codex", "model": None if native_fixture else args.model,
        "agent": "native-visual-fixture" if native_fixture else f"codex-{args.model}-visual-v1-fixture",
        "run_id": output.name, "scenario_id": scenario.id, "scenario": scenario.to_dict(),
        "seed": 1, "reasoning_effort": None if native_fixture else "medium",
        "budgets": None if native_fixture else {"decisions": args.max_decisions,
            "idle_decisions": args.max_idle_decisions, "wall_seconds": 3600},
        "codex_cli": cli_identity,
        "prompt_sha256": hashlib.sha256((ROOT / "prompts/ftl_visual_v1.md").read_bytes()).hexdigest()}
    recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
    manifest = {**meta, "started_at": time.time(), "status": "running", "scenario_ids": [scenario.id],
                "validation_status": "diagnostic_only",
                "validation_limitations": ["Injected normal STORE encounter is a control fixture, not benchmark evidence."]
                                          if not args.capture_only else ["Native capture, pause, key/modifier, and calibrated crew-drag control fixture; no model gameplay."]}
    def write_manifest(**updates):
        manifest.update(updates)
        (output / "run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_manifest()
    try:
        with protected.protected():
            protected.launch()
            fingerprint = runtime_fingerprint(ROOT)
            fingerprint["codex_cli"] = cli_identity
            (output / "runtime-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
            if not (fingerprint.get("native_build") or {}).get("matches_installed_dll"):
                raise RuntimeError("Installed DLL provenance mismatch")
            session = AgentSession(step_timeout=20)
            transport = VisualSession(session, output)
            if args.capture_only:
                frame = prepare_capture_world(session, transport, recorder, output)
                print(json.dumps(frame.reference), flush=True)
                idle_started = time.monotonic()
                time.sleep(2)
                idle = session.observe()
                pause_proof = check_paused_world(frame.observation.raw, idle.raw)
                pause_proof["elapsed_seconds"] = round(time.monotonic() - idle_started, 3)
                (output / "paused-inference-proof.json").write_text(json.dumps(pause_proof, indent=2), encoding="utf-8")
                recorder.record("pause-check", [], idle)
                if not pause_proof["passed"]:
                    raise RuntimeError("The game changed during paused model-thinking time")
                # A neutral cursor move checks the normal input handler and capture sequence.
                after = transport.step(frame, [{"type": "move", "x": 5, "y": 5}], 0)
                recorder.record("step", [{"type": "move", "x": 5, "y": 5}], after.observation,
                                visual=visual_record("image", frame, after, [{"type": "move", "x": 5, "y": 5}], 0))
                move_proof = check_paused_world(frame.observation.raw, after.observation.raw, same_capture=False)
                (output / "zero-frame-input-proof.json").write_text(json.dumps(move_proof, indent=2), encoding="utf-8")
                if not move_proof["passed"]:
                    raise RuntimeError("Zero-frame cursor input advanced gameplay")
                control_checks = verify_normal_controls(transport, recorder, after, output)
                recorder.finish(reason="capture_and_move_fixture")
                cursor_delivered = after.observation.raw["visual"]["input_feedback"][0]["status"] == "delivered"
                validation = {"fixture_only": True, "valid_for_model_comparison": False,
                              "status": "passed" if cursor_delivered else "incomplete",
                              "checks": {"paused_capture": True, "cursor_input_acknowledged": cursor_delivered,
                                         "paused_inference_world_frozen": pause_proof["passed"],
                                         "zero_frame_input_world_frozen": move_proof["passed"], **control_checks}}
                (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
                reason = "capture_and_move_fixture"
            elif args.transition_only:
                prepare_store(session, source, output, route="quiet")
                fingerprint = runtime_fingerprint(ROOT)
                fingerprint["codex_cli"] = cli_identity
                validation = verify_transition_boundary(session, transport, recorder, output)
                (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
                reason = "transition_boundary_fixture"
            else:
                prepare_store(session, source, output, route=args.store_setup)
                prepared = transport.capture()
                if _store_open(prepared.observation.raw) is not True:
                    raise RuntimeError("Fixture did not open a native store window")
                fingerprint = runtime_fingerprint(ROOT)
                fingerprint["codex_cli"] = cli_identity
                (output / "runtime-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
                goal = ("Buy exactly one unit of fuel from this store. Use its CLOSE button to close it. "
                        "Allow the FTL drive to charge, open the star map and jump to a connected beacon. "
                        "Use the screenshot to confirm each change.")
                agent = CodexVisualAgent(model=args.model, reasoning_effort="medium", task=goal,
                                         codex_bin=cli_identity["path"])
                report = run_loop(transport, agent, recorder, max_decisions=args.max_decisions,
                    max_wall_seconds=3600, max_idle_decisions=args.max_idle_decisions, expected_seed=1,
                    stop_when=lambda first, last: (_position(first.observation.raw) is not None
                        and _position(last.observation.raw) is not None
                        and _position(first.observation.raw) != _position(last.observation.raw)))
                validation = validate_store_fixture(load_trajectory(recorder.path), report["reason"])
                (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
                reason = report["reason"]
            (output / "runtime-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
        write_manifest(status="completed", reason=reason, finished_at=time.time(), save_restoration="verified",
                       fixture_acceptance=validation["status"])
    except BaseException as error:
        status = "interrupted" if isinstance(error, (KeyboardInterrupt, ExternalInputInterference)) else "error"
        reason = "external_interference" if isinstance(error, ExternalInputInterference) else "fixture_failed"
        recorder.finish(status=status, reason=reason, error=str(error))
        write_manifest(status=status, reason=reason, error=str(error), finished_at=time.time(),
                       save_restoration="see_save_backup_receipt")
        raise
    print(f"Visual fixture artifacts: {output}", flush=True)


if __name__ == "__main__":
    main()
