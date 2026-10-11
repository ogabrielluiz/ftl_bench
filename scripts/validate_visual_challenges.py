"""Protected, reproducible visual gameplay challenges; diagnostic evidence only.

Every trial recreates an explicit seed-1 prerequisite. Temporary Lua changes only
the disposable initial challenge state, once; all actor play uses run_visual's
frozen image/hybrid Codex CLI loop and ordinary mouse/keyboard controls. Run
--setup-only before model trials to verify the actual local bindings and starts.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from uuid import uuid4

from ftl_bench.cli import _bench_root
ROOT = _bench_root()
sys.path.insert(0, str(ROOT / "adapter"))

from ftl_bench.installation import runtime_fingerprint
from ftl_bench.protected_game import ProtectedGame
from ftl_bench.session import ftl_user_folder, jump
from ftl_bench.challenge_setup import DeterministicSetupSession as AgentSession, receipt_proof, packet_proof, first_capture_proof
import ftl_bench.challenge_setup as challenge_setup
from ftl_bench.trajectory import TrajectoryRecorder, load_trajectory
from ftl_bench.visual_session import ExternalInputInterference, VisualSession
from run_visual import codex_runtime_identity, run_loop, verify_visual_setup
from visual_agent import CodexVisualAgent, VisualBackendError, VisualProtocolError, PROMPT_PATH
import visual_agent
from visual_cancellation import StopControl, CooperativeStop

PROTOCOL = "visual-challenges-v1"
TIME_CONTRACT = {"visual_clock_version": 2, "fixed_step_numerator": 1, "fixed_step_denominator": 60}
TASKS = {
    "combat": "Defeat the hostile ship in this encounter and collect the normal encounter reward. Keep your ship and all your crew alive. Do not jump away. Confirm the result in the screenshots.",
    "fire-crew-recovery": "Put out all fires and restore ALL crew members to full health, including the initially injured crew member and any injuries sustained during firefighting. Restore the ship's overall oxygen to at least 90%. Keep all crew alive and remain at this beacon. Repair and power the oxygen system if needed. Confirm recovery in the screenshots.",
    "repair-charge-escape": "Repair the damaged engines, give them power, and let the FTL drive charge. Open the star map and jump to one connected beacon. Keep your ship and all crew alive. Confirm arrival in the screenshots.",
}
TASK_VERSIONS = {
    "combat": "combat-task-v1",
    "fire-crew-recovery": "fire-crew-recovery-task-v2",
    "repair-charge-escape": "repair-charge-escape-task-v1",
}


def task_identity(challenge):
    """Version the public objective separately from unchanged fixture mechanics."""
    task = TASKS[challenge]
    return {"task": task, "task_version": TASK_VERSIONS[challenge],
        "task_sha256": hashlib.sha256(task.encode("utf-8")).hexdigest()}


def verify_task_protocol(experiment, challenge):
    """Reject stale task contracts before starting a game or spending model quota."""
    if experiment is None:
        return
    expected = task_identity(challenge)
    if ((experiment.get("task_versions") or {}).get(challenge) != expected["task_version"]
            or (experiment.get("tasks") or {}).get(challenge) != expected):
        raise RuntimeError("Frozen challenge task/version differs from the current public objective")

# These are existing SWIG bindings in the pinned Hyperspace source. The writes
# occur once, after ordinary prerequisite travel, before the first actor frame.
# The INITIAL drive and combat enemy weapon charges are reset explicitly. After
# this prerequisite, no timers, readiness, frame budgets, rewards or outcomes are set.
FIXTURE_LUA = r'''
local visualChallenge={id=__ID__,challenge=__CHALLENGE__,applied=false,
 fixture_only=true,valid_for_model_comparison=false}
local visualChallengeTick=_G.ftl_bench_tick
_G.ftl_bench_tick=function()
 -- Admit the single already-read packet before setup, and mutate before render.
 visualChallengeTick()
 local state=_G.ftl_bench_state
 local app=Hyperspace.App
 if not visualChallenge.applied and not visualChallenge.setup_error
  and state.observation_mode=="visual-v1" and state.visual_pending==true
  and state.visual_capture==nil and state.visual_request_error==nil
  and state.visual_requested_frames==0 and state.frame_budget==0
  and app.world.bStartedGame and not app.gui.choiceBoxOpen then
  local ok,err=pcall(function()
   local receipt=state.benchmark_setup
   assert(receipt and receipt.phase=="visual" and not receipt.error,"deterministic setup handoff missing")
   local seeded=receipt.native_seed
   assert(seeded and seeded.contract=="fresh-start-seed-v3" and seeded.contract_version==3
    and seeded.applied and not seeded.pending and not seeded.failed
    and seeded.native_seed_applications==1 and seeded.c_runtime_seed_applications==1,
    "fresh construction seed evidence missing")
   visualChallenge.initial_rng_seed=seeded.seed
   visualChallenge.rng_seed_applied_here=false
   visualChallenge.seed_contract=seeded.contract
   local p=Hyperspace.ships.player
   visualChallenge.initial_drive_before=p.jump_timer.first
   visualChallenge.initial_drive_max=p.jump_timer.second
   visualChallenge.initial_drive_reset_requested=true
   p.jump_timer.first=0
   if visualChallenge.challenge=="fire-crew-recovery" then
    local oxygen=p:GetSystem(2)
    assert(oxygen,"oxygen system unavailable")
    local crew=p.vCrewList[0]
    assert(crew and crew.iShipId==0 and crew.health.first>0,"crew zero unavailable")
    visualChallenge.fire_room=oxygen:GetRoomId()
    visualChallenge.injured_crew_id=0
    visualChallenge.health_before=crew.health.first
    visualChallenge.health_target=crew.health.second/2
    crew:DirectModifyHealth(visualChallenge.health_target-crew.health.first)
    -- Seed belongs to fresh construction; never reseed this fixture.
    p:StartFire(visualChallenge.fire_room)
   elseif visualChallenge.challenge=="repair-charge-escape" then
    local engines=p:GetSystem(1)
    assert(engines,"engines unavailable")
    visualChallenge.damaged_system_id=1
    visualChallenge.requested_damage_amount=2
    visualChallenge.engine_health_before=engines.healthState.first
    visualChallenge.engine_health_max_before=engines.healthState.second
    engines:AddDamage(2)
    -- Seed belongs to fresh construction; never reseed this fixture.
   else
    local enemy=Hyperspace.ships.enemy
    assert(enemy,"enemy unavailable")
    local weapons=enemy:GetWeaponList()
    assert(weapons and weapons:size()>0,"enemy weapons unavailable")
    visualChallenge.enemy_weapon_charge_before={}
    for i=0,weapons:size()-1 do
     local weapon=weapons[i]
     visualChallenge.enemy_weapon_charge_before[#visualChallenge.enemy_weapon_charge_before+1]={
      slot=i,charge=weapon.cooldown.first,charge_max=weapon.cooldown.second}
     weapon.cooldown.first=0
    end
    visualChallenge.enemy_weapon_charge_reset_requested=true
    -- Seed belongs to fresh construction; never reseed this fixture.
   end
  end)
  if ok then
   visualChallenge.applied=true
   visualChallenge.applied_before_first_capture=true
   visualChallenge.admission_action_seq=state.last_applied_seq
  else visualChallenge.setup_error=tostring(err) end
  state.obs_fresh=false
 end
end
local visualChallengeWriter=Hyperspace.benchmark_write_visual_observation
Hyperspace.benchmark_write_visual_observation=function(payload,...)
 local obs=json.decode(payload)
 obs.visual_challenge_fixture=visualChallenge
 -- fDamage is repair/damage progress, not a count of missing system bars.
 -- These are read-only native health facts, never passed to the visual actor.
 local health={}
 for _,id in ipairs({1,2}) do
  pcall(function()
   local system=Hyperspace.ships.player:GetSystem(id)
   if system then
    local current,maximum=system.healthState.first,system.healthState.second
    health[#health+1]={system_id=id,health_current=current,health_max=maximum,
     damaged_bars=maximum-current}
   end
  end)
 end
 obs.visual_challenge_system_health=health
 return visualChallengeWriter(json.encode(obs),...)
end
'''


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def fixture_bridge(source: bytes, challenge: str, trial_id: str) -> bytes:
    if challenge not in TASKS:
        raise ValueError("Unknown challenge")
    return source + FIXTURE_LUA.replace("__ID__", json.dumps(trial_id)).replace(
        "__CHALLENGE__", json.dumps(challenge)).encode("utf-8")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _ship(raw):
    return raw.get("player_ship") or {}


def _nav(raw):
    return (raw.get("economy") or {}).get("navigation") or {}


def _system(raw, system_id):
    return next((s for s in _ship(raw).get("systems", []) if s.get("id") == system_id), {})


def _system_health(raw, system_id):
    return next((s for s in raw.get("visual_challenge_system_health", []) if s.get("system_id") == system_id), {})


def _fully_repaired(raw, system_id):
    health = _system_health(raw, system_id)
    return (type(health.get("health_current")) is int and type(health.get("health_max")) is int
        and health["health_max"] > 0 and health["health_current"] == health["health_max"]
        and health.get("damaged_bars") == 0 and _system(raw, system_id).get("needs_repair") is False)


def _position(raw):
    value = (raw.get("map") or {}).get("current_pos")
    if isinstance(value, dict) and all(_number(value.get(k)) for k in ("x", "y")):
        return value["x"], value["y"]
    return None


def _counter(raw):
    value = (raw.get("visual") or {}).get("world_updates")
    return int(value) if isinstance(value, str) and value.isdecimal() else None


def time_contract(raw):
    visual = raw.get("visual") or {}
    return {key: visual.get(key) for key in TIME_CONTRACT}


def time_contract_proof(raw):
    checks = {}
    for source in ("visual", "capabilities"):
        current = raw.get(source) or {}
        checks[source + "_fixed_step_contract"] = all(type(current.get(key)) is int and current[key] == expected
            for key, expected in TIME_CONTRACT.items())
        actual, simulated = current.get("world_updates"), current.get("simulated_updates")
        checks[source + "_native_update_counters"] = isinstance(actual, str) and actual.isascii() and actual.isdecimal() and simulated == actual
    checks["captured_and_live_counters_agree"] = (raw.get("visual") or {}).get("world_updates") == (raw.get("capabilities") or {}).get("world_updates")
    return {"passed": all(checks.values()), "checks": checks, "contract": time_contract(raw)}


def _fires(raw):
    rooms = _ship(raw).get("rooms")
    if (not isinstance(rooms, list) or not rooms or any(
            type(room.get("fires")) is not int or room["fires"] < 0 for room in rooms)):
        return None
    return sum(room["fires"] for room in rooms)


def _healthy_crew(raw):
    crew = _ship(raw).get("crew") or []
    return len(crew) == 3 and all(c.get("player_owned") is True and c.get("dead") is False
        and _number(c.get("health_current")) and _number(c.get("health_max"))
        and c["health_current"] == c["health_max"] and c["health_max"] > 0 for c in crew)


def _active_enemy(raw):
    enemy = raw.get("enemy_ship") or {}
    return enemy.get("hostile") is True and enemy.get("destroyed") is False


def _quiet(raw):
    enemy = raw.get("enemy_ship") or {}
    return (raw.get("map") or {}).get("hazard") == "none" and (
        not enemy or enemy.get("hostile") is False or enemy.get("destroyed") is True)


def gameplay_signature(raw):
    """Include gameplay facts, omit tick, clocks, capture identity and wall time."""
    player = _ship(raw)
    return {"seed": raw.get("seed"), "difficulty": raw.get("difficulty"),
        "game_started": raw.get("game_started"), "game_over": raw.get("game_over"),
        "player_ship": {key: player.get(key) for key in (
            "blueprint", "hull", "resources", "reactor", "oxygen_pct", "systems", "crew",
            "rooms", "fires", "intruders", "doors", "weapons", "shields", "shots")},
        "incoming_projectiles": raw.get("incoming_projectiles"),
        "enemy_ship": raw.get("enemy_ship"), "map": raw.get("map"),
        "navigation": _nav(raw), "environment": raw.get("environment"),
        "native_system_health": raw.get("visual_challenge_system_health"),
        "visual_time_contract": time_contract(raw),
        "initial_rng_seed": (raw.get("visual_challenge_fixture") or {}).get("initial_rng_seed"),
        "ftl_score": raw.get("ftl_score"), "ftl_score_components": raw.get("ftl_score_components")}


def setup_proof(challenge, raw):
    nav = _nav(raw)
    partial = (_number(nav.get("drive_current")) and _number(nav.get("drive_max"))
        and 0 <= nav["drive_current"] < nav["drive_max"] and nav.get("can_jump") is False)
    fixture = raw.get("visual_challenge_fixture") or {}
    crew = _ship(raw).get("crew") or []
    checks = {"seed_one": raw.get("seed") == 1 and type(raw.get("seed")) is int,
        "kestrel_easy": _ship(raw).get("blueprint") == "PLAYER_SHIP_HARD" and raw.get("difficulty") == 0,
        "live_game_no_modal": raw.get("game_started") is True and raw.get("game_over") is False
            and raw.get("choice_box_open") is False,
        "paused": raw.get("paused") is True,
        "store_closed": (raw.get("visual_evaluator") or {}).get("store_open") is False,
        "fixture_applied_once": fixture.get("applied") is True and not fixture.get("setup_error")
            and fixture.get("challenge") == challenge,
        "fixture_before_first_capture": fixture.get("applied_before_first_capture") is True
            and type(fixture.get("admission_action_seq")) is int
            and type(raw.get("last_action_seq")) is int
            and fixture["admission_action_seq"] <= raw["last_action_seq"],
        "position_available": _position(raw) is not None,
        "native_clock_available": _counter(raw) is not None,
        "no_environmental_hazard": (raw.get("map") or {}).get("hazard") == "none",
        "partial_drive": partial}
    checks["fixed_step_clock_verified"] = time_contract_proof(raw)["passed"]
    if challenge == "combat":
        checks.update(active_hostile_enemy=_active_enemy(raw), all_crew_healthy=_healthy_crew(raw))
        weapons = (raw.get("enemy_ship") or {}).get("weapons") or []
        checks["initial_enemy_weapons_uncharged"] = fixture.get("enemy_weapon_charge_reset_requested") is True and bool(weapons) and all(
            _number(w.get("charge")) and w["charge"] == 0 and _number(w.get("charge_max")) and w["charge_max"] > 0 for w in weapons)
    elif challenge == "fire-crew-recovery":
        injured = next((c for c in crew if c.get("id") == fixture.get("injured_crew_id")), {})
        room = next((r for r in _ship(raw).get("rooms", []) if r.get("room_id") == fixture.get("fire_room")), {})
        checks.update(quiet_beacon=_quiet(raw), all_crew_alive=len(crew) == 3 and all(
            c.get("dead") is False and _number(c.get("health_current")) and c["health_current"] > 0 for c in crew),
            injury_observed=_number(injured.get("health_current")) and _number(injured.get("health_max"))
                and injured["health_current"] == injured["health_max"] / 2,
            fire_in_oxygen_room=type(room.get("fires")) is int and room["fires"] > 0
                and room.get("room_id") == _system(raw, 2).get("room_id"),
            complete_fire_telemetry=_fires(raw) is not None)
    else:
        engines = _system(raw, 1)
        health = _system_health(raw, 1)
        checks.update(quiet_beacon=_quiet(raw), all_crew_healthy=_healthy_crew(raw),
            engine_healthy_before_setup=type(fixture.get("engine_health_before")) is int
                and fixture["engine_health_before"] == fixture.get("engine_health_max_before")
                and fixture["engine_health_before"] > 0,
            engine_damage_observed=type(health.get("health_current")) is int
                and type(health.get("health_max")) is int
                and 0 <= health["health_current"] < health["health_max"]
                and type(health.get("damaged_bars")) is int and health["damaged_bars"] > 0
                and engines.get("needs_repair") is True)
    checks["initial_drive_reset_verified"] = fixture.get("initial_drive_reset_requested") is True and nav.get("drive_current") == 0
    checks["initial_rng_seed_recorded"] = fixture.get("initial_rng_seed") == 1
    if challenge != "combat":
        checks["pristine_starting_beacon"] = _position(raw) == (88, 152)
    checks["native_system_health_available"] = all(type(_system_health(raw, system_id).get("health_current")) is int
        and type(_system_health(raw, system_id).get("health_max")) is int
        and _system_health(raw, system_id)["health_max"] > 0 for system_id in (1, 2))
    checks["deterministic_setup_verified"] = receipt_proof(raw)["passed"]
    return {"passed": all(checks.values()), "checks": checks}


def prepare(session, challenge, output, stop_control=None):
    """Fixed ordinary prerequisite; semantic setup never becomes actor history."""
    session.configure_setup(output, getattr(session, "setup_delay_seconds", 0.0))
    stop_control = stop_control or StopControl()
    records = []
    def dispatch(label, operation):
        stop_control.check("before_setup_" + label)
        result = operation()
        return result
    def keep(label, obs, actions=(), frames=0):
        records.append({"label": label, "actions": list(actions), "requested_frames": frames, "obs": obs.raw})
        write_json(output / "setup.json", records)
        stop_control.check("after_setup_" + label)
        return obs
    def resolve(obs):
        for _ in range(20):
            if not obs.choice_box_open:
                return obs
            choices = [c for c in (obs.event or {}).get("choices", []) if c.get("enabled") is True]
            if not choices:
                raise RuntimeError("Prerequisite event has no enabled choice")
            time.sleep(.35)
            index = choices[0]["index"]
            obs = keep("ordinary-prerequisite-event", dispatch("event", lambda: session.choose_event(index, 60)),
                       [{"type": "choose_event", "choice_index": index}], 60)
        raise RuntimeError("Prerequisite event did not settle")
    keep("reset-episode-seed-one", dispatch("fresh_start", lambda: session.reset_episode(seed=1)))
    keep("reset", dispatch("reset_ack", session.reset))
    obs = resolve(keep("settle-intro", dispatch("intro", lambda: session.step([], 30)), frames=30))
    if challenge != "combat":
        if not _quiet(obs.raw) or not _healthy_crew(obs.raw) or _position(obs.raw) != (88, 152):
            raise RuntimeError("Pristine seed-one starting-beacon prerequisite differs from the recorded requirement")
        return keep("before-one-time-challenge-setup", obs)
    for _ in range(30):
        if _nav(obs.raw).get("can_jump") is True:
            break
        obs = keep("ordinary-drive-charge", dispatch("charge", lambda: session.step([], 300)), frames=300)
    else:
        raise RuntimeError("Prerequisite drive did not charge normally")
    beacon = 0
    actions = [jump(beacon)]
    obs = resolve(keep(f"fixed-seed-one-hop-{beacon}", dispatch("hop", lambda: session.step(actions, 300)), actions, 300))
    if (challenge == "combat" and not _active_enemy(obs.raw)) or (challenge != "combat" and not _quiet(obs.raw)):
        raise RuntimeError("Fixed beacon prerequisite differs from the recorded hostile/quiet requirement")
    if not _healthy_crew(obs.raw):
        raise RuntimeError("Fixed prerequisite requires all three crew alive and healthy")
    return keep("before-one-time-challenge-setup", obs)


def _crew_preserved(initial, final):
    old = _ship(initial).get("crew") or []
    current = {c.get("id"): c for c in _ship(final).get("crew", [])}
    return bool(old) and len(current) == len(old) and all(
        c.get("id") in current and current[c["id"]].get("dead") is False
        and current[c["id"]].get("player_owned") is True
        and _number(current[c["id"]].get("health_current"))
        and current[c["id"]]["health_current"] > 0 for c in old)


def outcome_proof(challenge, rows):
    observations = [(r.get("i", i), r["obs"]) for i, r in enumerate(rows) if isinstance(r.get("obs"), dict)]
    if not observations:
        return {"achieved": False, "checks": {"native_observations_available": False}, "evidence": {}}
    initial, final = observations[0][1], observations[-1][1]
    hull = _ship(final).get("hull") or {}
    updates = (_counter(initial), _counter(final))
    checks = {"ship_and_crew_survive": final.get("game_over") is False
        and _number(hull.get("current")) and hull["current"] > 0 and _crew_preserved(initial, final),
        "explicit_native_progress": all(v is not None for v in updates) and updates[1] > updates[0]}
    evidence = {"initial_record": observations[0][0], "final_record": observations[-1][0]}
    if challenge == "combat":
        first_score, last_score = initial.get("ftl_score_components") or {}, final.get("ftl_score_components") or {}
        checks.update(enemy_destroyed=_active_enemy(initial) and (final.get("enemy_ship") or {}).get("destroyed") is True,
            native_kill_counter_increased=type(first_score.get("ships_destroyed")) is int
                and type(last_score.get("ships_destroyed")) is int
                and last_score["ships_destroyed"] == first_score["ships_destroyed"] + 1,
            native_reward_collected=type(first_score.get("scrap_collected")) is int
                and type(last_score.get("scrap_collected")) is int
                and last_score["scrap_collected"] > first_score["scrap_collected"],
            encounter_settled=final.get("choice_box_open") is False,
            stayed_at_beacon=_position(initial) is not None and _position(initial) == _position(final))
    elif challenge == "fire-crew-recovery":
        oxygen = _system(final, 2)
        checks.update(initial_fire_and_injury_observed=(_fires(initial) or 0) > 0 and not _healthy_crew(initial),
            all_fires_out=_fires(final) == 0, all_crew_full_health=_healthy_crew(final),
            oxygen_recovered=_number(_ship(final).get("oxygen_pct")) and _ship(final)["oxygen_pct"] >= 90,
            oxygen_system_operational=_fully_repaired(final, 2)
                and _number(oxygen.get("power")) and oxygen["power"] > 0,
            stayed_at_beacon=_position(initial) is not None and _position(initial) == _position(final))
    else:
        health = _system_health(initial, 1)
        checks["initial_engines_damaged"] = type(health.get("damaged_bars")) is int and health["damaged_bars"] > 0
        ready = []
        for index, raw in observations:
            nav, engine = _nav(raw), _system(raw, 1)
            if (_position(raw) == _position(initial) and _fully_repaired(raw, 1)
                and _number(engine.get("power")) and engine["power"] > 0
                and nav.get("can_jump") is True and _number(nav.get("drive_current"))
                and _number(nav.get("drive_max")) and nav["drive_max"] > 0
                and nav["drive_current"] >= nav["drive_max"]):
                ready.append((index, raw))
        checks["repaired_powered_full_drive_observed"] = bool(ready)
        checks["star_map_observed"] = any((raw.get("visual_evaluator") or {}).get("map_open") is True
            and _position(raw) == _position(initial) for _, raw in observations)
        departure = ready[-1][1] if ready else initial
        old_fuel = (_ship(departure).get("resources") or {}).get("fuel")
        new_fuel = (_ship(final).get("resources") or {}).get("fuel")
        destination = _position(final)
        connected = (departure.get("map") or {}).get("connected_beacons") or []
        checks.update(jump_to_connected_beacon=destination is not None and destination != _position(initial)
            and (initial.get("map") or {}).get("sector") == (final.get("map") or {}).get("sector")
            and any((b.get("pos_x"), b.get("pos_y")) == destination for b in connected),
            jump_consumed_one_fuel=type(old_fuel) is int and type(new_fuel) is int and new_fuel == old_fuel - 1,
            arrival_finished=(final.get("visual_evaluator") or {}).get("player_jumping") is False)
        evidence["ready_records"] = [index for index, _ in ready]
    return {"achieved": all(checks.values()), "checks": checks, "evidence": evidence}


def classify_outcome(proof, rows, termination, error=None):
    if error:
        if isinstance(error, ExternalInputInterference):
            return "external_interference"
        if isinstance(error, KeyboardInterrupt):
            return "operator_interruption"
        if isinstance(error, VisualProtocolError) and not isinstance(error, VisualBackendError):
            return "protocol_failure"
        return "infrastructure_failure"
    if proof["achieved"]:
        return "achieved"
    obs = [r["obs"] for r in rows if isinstance(r.get("obs"), dict)]
    current_crew = _ship(obs[-1]).get("crew") if obs else None
    crew_loss = isinstance(current_crew, list) and (len(current_crew) < len(_ship(obs[0]).get("crew") or [])
        or any(c.get("dead") is True or c.get("health_current") == 0 for c in current_crew))
    if obs and (obs[-1].get("game_over") is True or crew_loss
                or ((_ship(obs[-1]).get("hull") or {}).get("current") == 0)):
        return "failed_native_loss"
    if termination in ("decision_budget", "wall_clock_budget", "idle_decision_budget"):
        return "budget_exhausted"
    return "native_goal_not_achieved"


def actor_audit(rows):
    steps = [r for r in rows if r.get("kind") == "step"]
    return bool(steps) and all((r.get("model") or {}).get("provider") == "codex"
        and (r.get("model") or {}).get("tool_use") is False
        and bool((r.get("model") or {}).get("events"))
        and isinstance(((r.get("visual") or {}).get("before") or {}).get("sha256"), str)
        and ((r.get("model") or {}).get("image") or {}).get("sha256") ==
            ((r.get("visual") or {}).get("before") or {}).get("sha256") for r in steps)


def verify_experiment_runtime(experiment, fingerprint, cli_identity, production_hash, fixture_hash):
    """Refuse quota spending when a direct child differs from its frozen protocol."""
    if not experiment:
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_visual_experiment import verify_protocol
    verify_protocol(experiment)
    accepted = (experiment.get("native_acceptance") or {}).get("runtime") or {}
    fresh_contract = {"fresh_start_seed": True, "fresh_seed_contract_version": 3,
        "fresh_seed_contract": "fresh-start-seed-v3"}
    build = fingerprint.get("native_build") or {}
    if any(type(build.get(k)) is not type(v) or build.get(k) != v
            or type(accepted.get(k)) is not type(v) or accepted.get(k) != v for k, v in fresh_contract.items()):
        raise RuntimeError("Actual or accepted native fresh-start-v3 contract is missing or differs")
    expected = {"dll_sha256": (fingerprint.get("native_dll") or {}).get("sha256"),
        "patch_sha256": (fingerprint.get("native_build") or {}).get("patch_sha256"),
        "production_bridge_sha256": production_hash}
    if any(not accepted.get(k) or accepted[k] != value for k, value in expected.items()):
        raise RuntimeError("Actual native DLL, patch or production bridge differs from accepted frozen runtime")
    if cli_identity != experiment.get("codex_cli"):
        raise RuntimeError("Actual Codex CLI differs from the accepted frozen runtime")
    if (fingerprint.get("bridge_lua") or {}).get("sha256") != fixture_hash:
        raise RuntimeError("Deployed fixture bridge differs from the archived challenge fixture")


@contextmanager
def record_stop_before_cleanup(recorder):
    """Persist cooperative stop attribution before protected teardown starts."""
    try:
        yield
    except CooperativeStop as error:
        recorder.finish(status="interrupted", reason="cooperative_stop_requested",
            error=str(error), stop_request=error.evidence)
        raise


def run_trial(args, challenge, repetition, output, cli_identity, experiment, *, scripted_probe=None):
    verify_task_protocol(experiment, challenge)
    control = StopControl(getattr(args, "stop_file", None), getattr(args, "stop_scope", None))
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
    original = source.read_bytes()
    source_hash = digest(original)
    (output / "production-bridge.lua").write_bytes(original)
    driver = Path(__file__).read_bytes()
    (output / "fixture-driver.py").write_bytes(driver)
    temporary = output / "fixture-bridge.lua"
    bridge_bytes = original
    setup_helper = Path(challenge_setup.__file__).read_bytes()
    (output / "challenge_setup.py").write_bytes(setup_helper)
    temporary.write_bytes(fixture_bridge(bridge_bytes, challenge, output.name))
    user = ftl_user_folder()
    live = user / "ftl_bench_dev.lua"
    if live.is_symlink() or (live.exists() and not live.is_file()):
        raise RuntimeError("Unsafe deployed bridge path")
    live_existed = live.exists()
    live_hash = digest(live.read_bytes()) if live_existed else None
    protected = ProtectedGame(user, output / "save-backup", temporary)
    task = TASKS[challenge]
    meta = {"track": "visual-v1", "protocol": PROTOCOL, "challenge": challenge,
        "scenario_id": f"VISUAL-CHALLENGE-{challenge}", "scenario_ids": [f"VISUAL-CHALLENGE-{challenge}"],
        "run_id": output.name, "repetition": repetition, "seed": args.seed,
        "observation_mode": args.mode, "reasoning_effort": args.reasoning_effort,
        "provider": "none" if args.setup_only else "codex", "model": None if args.setup_only else args.model,
        "fixture_only": True, "classification": "diagnostic_only", "valid_for_model_comparison": False,
        "setup_only": args.setup_only, "public_task": task, "task_sha256": digest(task.encode()),
        "task_version": TASK_VERSIONS[challenge],
        "stop_control": {"path": str(control.path) if control.path else None, "scope": control.scope},
        "script_sha256": digest(driver), "production_bridge_sha256": source_hash,
        "fixture_bridge_sha256": digest(temporary.read_bytes()), "fixture_version": 6, "deterministic_setup_contract": "deterministic-setup-v1",
        "setup_helper_sha256": digest(setup_helper), "fresh_seed_contract": "fresh-start-seed-v3",
        "fresh_seed_contract_version": 3,
        "prompt_sha256": digest(PROMPT_PATH.read_bytes()),
        "prompt_version": visual_agent.PROMPT_VERSION,
        "codex_cli": cli_identity, "budgets": {"decisions": args.max_decisions,
            "wall_seconds": args.max_wall_seconds, "idle_decisions": args.max_idle_decisions},
        "validation_status": "diagnostic_only", "external_input_guard_required": True,
        "visual_clock_version": 2, "time_contract": TIME_CONTRACT, "status": "running", "started_at": time.time(),
        "prerequisite": {"seed": 1, "beacon_index": 0 if challenge == "combat" else None,
            "route": "fresh Kestrel A/easy; first enabled ordinary intro choice; normal charge; fixed connected hop0; explicit one-time initial drive and enemy weapon charges reset0" if challenge == "combat" else
                "fresh Kestrel A/easy; first enabled ordinary intro choice; pristine starting beacon88,152; explicit one-time initial drive charge reset0",
            "environment": "hostile encounter without environmental hazard" if challenge == "combat" else "quiet beacon without environmental hazard"},
        "limitations": ["Temporary one-time disposable fixture, not a full-run benchmark.",
            "Quiet challenges reset initial drive charge to zero once; all later charging follows ordinary gameplay.",
            "Combat resets initial drive and enemy weapon charges to zero once, with native before values retained.",
            "Native and DLL C-runtime seed1 apply once before fresh construction; fixture6 does not reseed. Full-game determinism remains unproven.",
            "Repair challenge uses a quiet starting beacon; hostile escape performance is not established."]}
    recorder = TrajectoryRecorder(output / "trajectory.jsonl", meta)
    def manifest(**updates):
        meta.update(updates)
        write_json(output / "run.json", meta)
    manifest()
    error, proof, termination, actor_start, verification = None, None, "not_run", None, None
    stage = "protected_launch"
    try:
        control.check("before_protected_startup")
        with protected.protected(), record_stop_before_cleanup(recorder):
            control.check("before_game_launch")
            protected.launch()
            control.check("after_game_launch")
            fingerprint = runtime_fingerprint(ROOT)
            fingerprint["codex_cli"] = cli_identity
            write_json(output / "runtime-fingerprint.json", fingerprint)
            if not (fingerprint.get("native_build") or {}).get("matches_installed_dll"):
                raise RuntimeError("Installed native DLL provenance mismatch")
            verify_experiment_runtime(experiment, fingerprint, cli_identity, source_hash, meta["fixture_bridge_sha256"])
            stage = "challenge_setup"
            session = AgentSession(step_timeout=30)
            session.setup_delay_seconds = getattr(args, "probe_delay_seconds", 0.0)
            prepare(session, challenge, output, control)
            control.check("after_setup_before_capture")
            transport = VisualSession(session, output)
            frame = transport.capture()
            write_json(output / "initial-fixture-capture.json", {"image": frame.reference,
                "observation": frame.observation.raw, "scope": "First admitted visual capture after fixture initialization and before any visual control or actor input."})
            recorder.record("fixture_setup", [], frame.observation, visual={"observation_mode": args.mode,
                "before": frame.reference, "after": frame.reference, "inputs": [],
                "advance": {"requested_frames": 0, "actual_frames": 0},
                "outcome": {"status": "unknown", "summary": "Initial fixture state before prerequisite evaluation; no model input."}})
            control.check("after_initial_fixture_capture")
            initial_fixture = frame.observation.raw.get("visual_challenge_fixture") or {}
            if (initial_fixture.get("applied") is not True
                    or initial_fixture.get("applied_before_first_capture") is not True):
                raise RuntimeError("Challenge fixture was not applied before the first visual capture")
            store_before = frame
            if (frame.observation.raw.get("visual_evaluator") or {}).get("store_open") is True:
                if (frame.reference.get("width"), frame.reference.get("height")) != (1280, 720):
                    raise RuntimeError("Setup STORE CLOSE calibration requires a 1280x720 image")
                close = [{"type": "click", "x": 854, "y": 572, "button": "left", "modifiers": []}]
                frame = transport.step(frame, close, 0)
                write_json(output / "setup-store-close.json", {"actions": close, "requested_frames": 0,
                    "before_image": store_before.reference, "after_image": frame.reference,
                    "before_observation": store_before.observation.raw, "after_observation": frame.observation.raw})
                if (frame.observation.raw.get("visual_evaluator") or {}).get("store_open") is not False:
                    raise RuntimeError("Ordinary setup CLOSE click did not close the store")
                frame = transport.step(frame, [{"type": "move", "x": 5, "y": 5}], 0)
            verification = verify_visual_setup(frame, args.seed)
            proof = setup_proof(challenge, frame.observation.raw)
            packet_checks = packet_proof(frame.observation.raw, session.setup_packets)
            proof["checks"]["setup_packets_match_intervals"] = packet_checks["passed"]
            proof["passed"] = all(proof["checks"].values())
            native_proof = receipt_proof(frame.observation.raw)
            admission = first_capture_proof(store_before, session.setup_packets)
            write_json(output / "deterministic-setup-admission.json", admission)
            proof["checks"]["first_capture_identity_verified"] = admission["passed"]
            proof["passed"] = all(proof["checks"].values())
            write_json(output / "deterministic-setup-proof.json", {
                **native_proof, "receipt_passed": native_proof["passed"],
                "packet_proof": packet_checks,
                "passed": native_proof["passed"] and packet_checks["passed"]})
            signature = gameplay_signature(frame.observation.raw)
            actor_start = {"first_image": frame.reference, "initial_observation": frame.observation.raw,
                "gameplay_signature": signature, "gameplay_signature_sha256": digest(
                    json.dumps(signature, sort_keys=True, separators=(",", ":")).encode()),
                "setup_proof": proof, "canonical_actor_reset": False,
                "time_contract_proof": time_contract_proof(frame.observation.raw),
                "rng_receipt": {"initial_native_seed": (frame.observation.raw.get("visual_challenge_fixture") or {}).get("initial_rng_seed"),
                    "binding": "fresh-start-seed-v3", "native_seed": (frame.observation.raw.get("deterministic_setup") or {}).get("native_seed"),
                    "scope": "Fresh construction initialization of both generators; no fixture reseed or full-game determinism claim"}}
            write_json(output / "actor-start.json", actor_start)
            write_json(output / "setup-verification.json", {**verification, "challenge_setup": proof})
            manifest(initial_gameplay_sha256=actor_start["gameplay_signature_sha256"], setup_verified=proof["passed"])
            if not proof["passed"]:
                raise RuntimeError("Challenge prerequisite proof failed: " + ", ".join(k for k, v in proof["checks"].items() if not v))
            if args.setup_only:
                recorder.record("reset", [], frame.observation, visual={"observation_mode": args.mode,
                    "before": frame.reference, "after": frame.reference, "inputs": [],
                    "advance": {"requested_frames": 0, "actual_frames": 0},
                    "outcome": {"status": "unknown", "summary": "Verified initial challenge screenshot; no model gameplay."}})
                if scripted_probe:
                    stage = "timing_probe"
                    scripted_probe(session, transport, recorder, frame, output, args)
                    termination = "timing_probe_completed"
                else:
                    termination = "setup_only"
                recorder.finish(reason=termination)
            else:
                stage = "visual_actor"
                agent = CodexVisualAgent(model=args.model, reasoning_effort=args.reasoning_effort,
                    task=task, codex_bin=cli_identity["path"])
                identity = agent.instruction_identity() if hasattr(agent, "instruction_identity") else {
                    "task": task, "task_sha256": digest(task.encode()), "manual_sha256": meta["prompt_sha256"]}
                identity = {**identity, "task_version": TASK_VERSIONS[challenge]}
                manifest(actor_identity=identity)
                trace = []
                def stop_when(first, last):
                    if not trace:
                        trace.append({"i": 0, "obs": first.observation.raw})
                    if trace[-1]["obs"] != last.observation.raw:
                        trace.append({"i": len(trace), "obs": last.observation.raw})
                    return outcome_proof(challenge, trace)["achieved"]
                frozen = {**(experiment or {}), "challenge": challenge, "scenario": challenge,
                    "protocol": PROTOCOL, "task": task, "task_sha256": meta["task_sha256"],
                    "task_version": meta["task_version"],
                    "seed": args.seed, "repetition": repetition, "actor_identity": identity,
                    "fixture_sha256": meta["fixture_bridge_sha256"], "runtime_identity": fingerprint,
                    "budgets": meta["budgets"], "challenge_protocol": PROTOCOL,
                    "fixture_version": meta["fixture_version"], "prerequisites_verified": True,
                    "initial_gameplay_sha256": actor_start["gameplay_signature_sha256"]}
                manifest(experiment=frozen)
                def validate_actor_start(initial):
                    checks = setup_proof(challenge, initial.observation.raw)
                    unchanged = gameplay_signature(initial.observation.raw) == signature
                    result = {"passed": checks["passed"] and unchanged,
                        "setup_proof": checks, "gameplay_unchanged": unchanged, "image": initial.reference}
                    write_json(output / "actor-reset-admission.json", result)
                    if not result["passed"]:
                        raise RuntimeError("Challenge state changed before canonical actor reset; evidence archived")
                # Admission runs after canonical reset/image recording, before any actor call.
                report = run_loop(transport, agent, recorder, mode=args.mode,
                    max_decisions=args.max_decisions, max_wall_seconds=args.max_wall_seconds,
                    max_idle_decisions=args.max_idle_decisions, expected_seed=args.seed,
                    stop_when=stop_when, experiment=frozen, initial_frame_validator=validate_actor_start,
                    stop_control=control)
                termination = report["reason"]
    except BaseException as exc:
        error = exc
        recorder.finish(status="interrupted" if isinstance(exc, (KeyboardInterrupt, ExternalInputInterference)) else "error",
            reason="cooperative_stop_requested" if isinstance(exc, CooperativeStop) else
                "external_interference" if isinstance(exc, ExternalInputInterference) else
                "user_interrupted" if isinstance(exc, KeyboardInterrupt) else
                "visual_backend_error" if isinstance(exc, VisualBackendError) else
                "visual_model_error" if isinstance(exc, VisualProtocolError) else stage + "_error", error=str(exc),
            **({"stop_request": exc.evidence} if isinstance(exc, CooperativeStop) else {}))
    finally:
        receipt = output / "save-backup/restoration.json"
        restored = receipt.is_file() and json.loads(receipt.read_text(encoding="utf-8")).get("verified") is True
        if restored:
            if live.is_symlink() or (live.exists() and not live.is_file()):
                restored = False
            elif not live_existed:
                live.unlink(missing_ok=True)
            else:
                restored = live.is_file() and digest(live.read_bytes()) == live_hash
        source_unchanged = source.is_file() and digest(source.read_bytes()) == source_hash
        if not restored or not source_unchanged:
            error = error or RuntimeError("Save/deployed bridge restoration or production source verification failed")
        rows = load_trajectory(recorder.path)
        terminal = next((r for r in reversed(rows) if r.get("kind") == "end"), {})
        termination = terminal.get("reason", termination)
        if verification:
            write_json(output / "setup-verification.json", {**verification, "challenge_setup": proof})
        if actor_start and not args.setup_only:
            initial_row = next((r for r in rows if r.get("kind") == "reset" and isinstance(r.get("obs"), dict)), None)
            if initial_row:
                ref = (initial_row.get("visual") or {}).get("before")
                if ref:
                    initial_signature = gameplay_signature(initial_row["obs"])
                    actor_start.update(first_image=ref, initial_observation=initial_row["obs"],
                        gameplay_signature=initial_signature,
                        gameplay_signature_sha256=digest(json.dumps(initial_signature, sort_keys=True, separators=(",", ":")).encode()),
                        canonical_actor_reset=True)
                    write_json(output / "actor-start.json", actor_start)
        result = outcome_proof(challenge, rows)
        audited = actor_audit(rows) if not args.setup_only else None
        if not args.setup_only and not error and not audited:
            error = RuntimeError("CLI image decisions lack complete tool-free audit evidence")
        category = "setup_verified" if args.setup_only and not error else classify_outcome(result, rows, termination, error)
        validation = {"protocol": PROTOCOL, "challenge": challenge, "repetition": repetition,
            "fixture_only": True, "valid_for_model_comparison": False, "outcome_category": category,
            "status": "passed" if category in ("achieved", "setup_verified") else "failed",
            "termination": termination, "setup": proof, "outcome": result,
            "cli_image_decisions_audited": audited, "save_restoration_verified": restored,
            "production_source_unchanged": source_unchanged, "error": str(error) if error else None}
        if isinstance(error, CooperativeStop):
            validation["stop_request"] = error.evidence
        validation["failure_type"] = category if category in ("protocol_failure", "infrastructure_failure", "external_interference", "operator_interruption") else None
        write_json(output / "validation.json", validation)
        lifecycle_status = terminal.get("status", "error" if error else "completed")
        if error and lifecycle_status == "completed":
            lifecycle_status = "error"
        manifest(status=lifecycle_status, reason=termination, finished_at=time.time(),
            initial_gameplay_sha256=actor_start["gameplay_signature_sha256"] if actor_start else None,
            outcome_category=category, fixture_acceptance=validation["status"],
            failure_type=validation["failure_type"],
            save_restoration="verified" if restored else "not_verified", production_source_unchanged=source_unchanged,
            error=str(error) if error else None,
            **({"stop_request": error.evidence} if isinstance(error, CooperativeStop) else {}))
    print(json.dumps({"challenge": challenge, "repetition": repetition, "outcome": category, "artifacts": str(output)}), flush=True)
    if isinstance(error, (KeyboardInterrupt, ExternalInputInterference)):
        raise error
    return validation


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--challenge", choices=("all", *TASKS), default="all")
    p.add_argument("--setup-only", action="store_true")
    p.add_argument("--model", default="gpt-6.1-sol")
    p.add_argument("--mode", choices=("image", "hybrid"), default="image")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--reasoning-effort", default="medium")
    p.add_argument("--max-decisions", type=int, default=60)
    p.add_argument("--max-idle-decisions", type=int, default=8)
    p.add_argument("--max-wall-seconds", type=float, default=1800)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--repeat-index", type=int, default=1)
    p.add_argument("--experiment-file", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--stop-file", type=Path)
    p.add_argument("--stop-scope")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.stop_scope and not args.stop_file:
        p.error("stop-scope requires stop-file")
    if args.seed != 1:
        p.error("This version freezes seed 1 and its recorded beacon prerequisites")
    if (args.max_decisions < 1 or args.max_idle_decisions < 1 or not _number(args.max_wall_seconds)
        or args.max_wall_seconds < 1 or not 1 <= args.repeats <= 3 or not 1 <= args.repeat_index <= 3
        or args.repeat_index + args.repeats - 1 > 3):
        p.error("Invalid trial repetitions or bounded budgets")
    experiment = json.loads(args.experiment_file.read_text(encoding="utf-8")) if args.experiment_file else None
    if experiment is not None and not isinstance(experiment, dict):
        p.error("experiment-file must contain a JSON object")
    pending_stop = StopControl(args.stop_file, args.stop_scope).pending()
    cli = None if args.setup_only or pending_stop else codex_runtime_identity()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = (args.output or ROOT / "harness/runs/validation/visual-v1" / ("challenges-" + stamp)).resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = list(TASKS) if args.challenge == "all" else [args.challenge]
    results = []
    for offset in range(args.repeats):
        for challenge in selected:
            trial = output / f"repetition-{offset + 1:02}" / challenge
            results.append({"directory": str(trial), **run_trial(args, challenge,
                args.repeat_index + offset, trial, cli, experiment)})
            write_json(output / "challenges-report.json", {"protocol": PROTOCOL,
                "classification": "diagnostic_only", "valid_for_model_comparison": False,
                "setup_only": args.setup_only, "trials": results})
            if results[-1]["outcome_category"] in ("infrastructure_failure", "protocol_failure"):
                return 2
    # Valid model losses/budget stops are trial results, not infrastructure errors.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
