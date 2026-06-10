"""ftl_bench MCP server — lets an LLM agent play FTL through tools.

Wraps the ftl_bench harness (AgentSession) and exposes the environment as MCP
tools. The game (FTL + Hyperspace + the ftl_bench bridge) must already be running
(see scripts/restart_ftl.sh). Each tool returns a compact, agent-readable summary
of the resulting game state.

Run:  cd harness && uv run --with "mcp[cli]" python ../adapter/ftl_mcp_server.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make the harness package importable when run standalone.
_HARNESS_SRC = Path(__file__).resolve().parent.parent / "harness" / "src"
if str(_HARNESS_SRC) not in sys.path:
    sys.path.insert(0, str(_HARNESS_SRC))

from mcp.server.fastmcp import FastMCP

from ftl_bench import (  # noqa: E402
    AgentSession,
    choose_event,
    fire_weapon,
    jump,
    move_crew,
    set_system_power,
)
from ftl_bench.observation import Observation  # noqa: E402

mcp = FastMCP("ftl-bench")
_session = AgentSession()

# FTL system ids -> names (Defines.SystemId), for a readable summary.
SYSTEM_NAMES = {
    0: "shields", 1: "engines", 2: "oxygen", 3: "weapons", 4: "drone_ctrl",
    5: "medbay", 6: "pilot", 7: "sensors", 8: "doors", 9: "teleporter",
    10: "cloaking", 11: "artillery", 12: "battery", 13: "clonebay",
    14: "mind_control", 15: "hacking",
}


def _copy_keys(d: dict | None, keys: tuple[str, ...]) -> dict:
    if not isinstance(d, dict):
        return {}
    return {k: d[k] for k in keys if k in d and d[k] is not None}


def _summary(obs: Observation) -> dict[str, Any]:
    """A compact, agent-readable view of the observation."""
    out: dict[str, Any] = {
        "context": "menu" if not obs.game_started else (
            "event" if obs.choice_box_open else (
                "combat" if obs.enemy_ship else "in_space")),
        "game_started": obs.game_started,
        "paused": obs.paused,
        "tick": obs.tick,
    }
    if not obs.game_started:
        out["hint"] = "Call reset(mode='new'|'continue') to start a run."
        return out

    ps = obs.player_ship or {}
    out["player"] = {
        "hull": ps.get("hull"),
        "reactor": ps.get("reactor"),
        "resources": ps.get("resources"),
        "oxygen_pct": ps.get("oxygen_pct"),
        "systems": [
            {"id": s["id"], "name": SYSTEM_NAMES.get(s["id"], str(s["id"])),
             "power": s.get("power"), "power_max": s.get("power_max"),
             "damage": s.get("damage"),
             **({"needs_repair": True} if s.get("needs_repair") else {})}
            for s in ps.get("systems", [])
        ],
        "crew": [
            {"id": c["id"], "room": c.get("room"),
             "health": c.get("health_current"), "dead": c.get("dead")}
            for c in ps.get("crew", [])
        ],
        "weapons": [
            {"slot": w["slot"], "powered": w.get("powered"),
             "charge": w.get("charge"), "charge_max": w.get("charge_max"),
             "ready": w.get("ready")}
            for w in ps.get("weapons", [])
        ],
    }
    for key in ("cloak", "battery", "hacking", "drones", "teleporter", "mind_control"):
        if ps.get(key):
            out["player"][key] = ps[key]
    if ps.get("rooms"):
        out["player"]["rooms"] = [
            _copy_keys(r, (
                "room_id", "oxygen", "fires", "breaches", "breached", "breach",
                "blacked_out", "rect",
            ))
            for r in ps.get("rooms", [])
        ]
    if ps.get("doors"):
        out["player"]["doors"] = [
            _copy_keys(d, (
                "index", "id", "room_a", "room_b", "open", "locked",
                "forced_open", "hacked",
            ))
            for d in ps.get("doors", [])
        ]
    if obs.enemy_ship:
        es = obs.enemy_ship
        out["enemy"] = {
            "hull": es.get("hull"),
            "shields": es.get("shields"),
            **({"flagship": True} if es.get("flagship") else {}),
            **({"super_shield": es.get("super_shield")} if es.get("super_shield") else {}),
            **_copy_keys(es, ("power_surge_timer", "power_surge_timer_max", "power_surge_type")),
            "rooms": [{"room_id": r["room_id"],
                       "system": SYSTEM_NAMES.get(r["system_id"], str(r["system_id"])),
                       **({"hacked": True} if r.get("hacked") else {})}
                      for r in es.get("rooms", [])],
            **({"rooms_with_crew": es.get("rooms_with_crew")} if es.get("rooms_with_crew") else {}),
            **({"crew": es.get("crew")} if es.get("crew") else {}),
        }
    if (obs.raw or {}).get("flagship"):
        out["flagship"] = (obs.raw or {}).get("flagship")
    if obs.map:
        out["map"] = {
            "sector": obs.map.get("sector"),
            "beacons": obs.map.get("connected_beacons", []),
            **({"sector_choices": obs.map.get("sector_choices")} if obs.map.get("sector_choices") else {}),
        }
    if obs.event:
        out["event"] = obs.event
    return out


# ---- tools -----------------------------------------------------------------

@mcp.tool()
def observe() -> dict[str, Any]:
    """Return the current FTL game state (your view as the agent): context
    (menu/in_space/combat/event), your ship (hull, reactor, systems with power,
    crew, weapons with charge), the enemy ship (hull, shields, targetable rooms)
    when in combat, reachable jump beacons, and event choices when an event is open.
    The game is PAUSED between your actions — nothing changes until you act."""
    return _summary(_session.observe())


@mcp.tool()
def reset(mode: str = "new", seed: int | None = None) -> dict[str, Any]:
    """Start a fresh episode. mode='new' starts a new run (optionally seeded for
    reproducibility) and works even mid-run (abandons it back to the menu first);
    'continue' resumes the saved run from the menu. Returns the first observation."""
    if mode == "new":
        return _summary(_session.reset_episode(seed=seed))
    return _summary(_session.start_game(mode))


@mcp.tool()
def do_jump(beacon_index: int) -> dict[str, Any]:
    """Travel (FTL jump) to a connected beacon by its index (see map.beacons from
    observe()). Costs 1 fuel; the destination may trigger an event or combat."""
    return _summary(_session.jump(beacon_index))


@mcp.tool()
def pick_choice(choice_index: int) -> dict[str, Any]:
    """When an event is open (context='event'), choose option `choice_index`
    (see event.choices from observe()). Applies the choice's consequences."""
    return _summary(_session.choose_event(choice_index))


@mcp.tool()
def power_system(system_id: int, level: int) -> dict[str, Any]:
    """Set a ship system's power to `level` bars (best-effort, limited by your
    reactor). system_id: 0=shields 1=engines 2=oxygen 3=weapons 5=medbay etc."""
    return _summary(_session.step([set_system_power(system_id, level)], advance_frames=20))


@mcp.tool()
def send_crew(crew_id: int, room_id: int) -> dict[str, Any]:
    """Move a crew member (by id) to one of YOUR ship's rooms (e.g. to man a
    system or repair/fight). Crew take time to walk — advance a few frames after."""
    return _summary(_session.step([move_crew(crew_id, room_id)], advance_frames=120))


@mcp.tool()
def shoot(weapon_slot: int, enemy_room_id: int) -> dict[str, Any]:
    """In combat, aim weapon `weapon_slot` at enemy `enemy_room_id` (see
    enemy.rooms) and queue one manual shot/burst. It does not keep auto-firing;
    issue shoot again for the next volley. Power the weapons system (id 3) and
    ensure the weapon is charged first."""
    return _summary(_session.fire_weapon(weapon_slot, enemy_room_id, advance_frames=90))


@mcp.tool()
def advance(frames: int = 120) -> dict[str, Any]:
    """Let game time pass for `frames` frames (~60/sec) while staying in control —
    use to charge weapons, let crew finish walking, or let a jump/combat settle.
    Then the game re-pauses and returns the new state."""
    return _summary(_session.step([], advance_frames=frames))


@mcp.tool()
def run_strategy(code: str) -> dict[str, Any]:
    """CODE MODE: execute Python that drives the env directly — loops, conditionals,
    whole combats — in ONE call, instead of one tool-call per action. In scope:
      session  -> the AgentSession (session.observe()/.step()/.jump()/.choose_event()/
                  .fire_weapon()/.reset_episode(seed=…)/.start_game(…) etc.)
      set_system_power, move_crew, jump, choose_event, fire_weapon  -> action builders
      summary(obs) -> the same compact dict the other tools return
      log(*args)   -> print into the captured output
    Returns {"output": <captured stdout, last 6k chars>, "error": <repr or None>}.
    Example:
      o = session.observe()
      while o.get('enemy_ship'):
          session.fire_weapon(0, o['enemy_ship']['rooms'][0]['room_id'])
          o = session.observe().raw
      log('combat done, hull', o['player_ship']['hull'])
    Note: session.observe() returns an Observation object; use .raw for the dict,
    or call summary(session.observe()) for the compact view."""
    import contextlib
    import io

    buf = io.StringIO()
    ns: dict[str, Any] = {
        "session": _session,
        "set_system_power": set_system_power,
        "move_crew": move_crew,
        "jump": jump,
        "choose_event": choose_event,
        "fire_weapon": fire_weapon,
        "summary": _summary,
        "log": lambda *a: print(*a),
    }
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, ns)  # local benchmark tool: agent-authored strategy
        return {"output": buf.getvalue()[-6000:], "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"output": buf.getvalue()[-6000:], "error": repr(exc)}


if __name__ == "__main__":
    mcp.run()
