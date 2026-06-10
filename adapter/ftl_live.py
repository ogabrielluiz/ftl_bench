"""ftl_bench live dashboard API.

Run:

    cd harness
    uv run --extra dashboard python ../adapter/ftl_live.py

Then open http://127.0.0.1:8765.

The server is read-only. It tails benchmark JSONL trajectories, scores completed
instances with the harness scorer, reports process status, and serves the built
React dashboard from dashboard/dist when present.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "harness" / "src"))

BENCH = Path(os.environ.get("FTL_BENCH_DIR") or (REPO / "harness" / "runs" / "benchmark"))
SUITE = Path(os.environ.get("FTL_SUITE") or (REPO / "scenarios" / "suite_v1.json"))
DASHBOARD_DIST = REPO / "dashboard" / "dist"
PORT = int(os.environ.get("FTL_LIVE_PORT", "8765"))
HOST = os.environ.get("FTL_LIVE_HOST", "127.0.0.1")
FEED_TAIL = int(os.environ.get("FTL_LIVE_TAIL", "120"))
RUN_WINDOW = int(os.environ.get("FTL_LIVE_RUN_WINDOW", str(6 * 3600)))

SYS_NAMES = {
    0: "shields",
    1: "engines",
    2: "oxygen",
    3: "weapons",
    4: "drones",
    5: "medbay",
    6: "piloting",
    7: "sensors",
    8: "doors",
    9: "teleporter",
    10: "cloak",
    12: "battery",
    14: "mind",
    15: "hacking",
}

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
except Exception:  # noqa: BLE001
    FastAPI = HTTPException = Query = None
    FileResponse = HTMLResponse = StaticFiles = None

try:
    from ftl_bench import load_suite, load_trajectory, score_instance
    from ftl_bench.session import ftl_process_alive

    SCENARIOS = {s.id: s for s in load_suite(str(SUITE))}
except Exception:  # noqa: BLE001
    load_suite = load_trajectory = score_instance = None
    ftl_process_alive = None
    SCENARIOS = {}

_score_cache: dict[str, tuple[float, dict | None]] = {}
_meta_cache: dict[str, tuple[float, dict | None]] = {}


def _mtime(path: str | Path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _age_seconds(path: str | Path) -> int:
    mtime = _mtime(path)
    return max(0, int(time.time() - mtime)) if mtime else 0


def all_files() -> list[str]:
    files = glob.glob(str(BENCH / "*.jsonl"))
    return sorted(files, key=_mtime, reverse=True)


def current_file(files: list[str] | None = None) -> str | None:
    files = files if files is not None else all_files()
    return files[0] if files else None


def name_of(path: str | Path) -> str:
    name = os.path.basename(str(path))
    return name[:-6] if name.endswith(".jsonl") else name


def scenario_id_of(name: str) -> str:
    base = name
    if "." in base:
        head, tail = base.rsplit(".", 1)
        if tail.startswith("a") and tail[1:].isdigit():
            base = head
    return base


def attempt_of(name: str) -> int | None:
    if "." not in name:
        return None
    _, tail = name.rsplit(".", 1)
    if tail.startswith("a") and tail[1:].isdigit():
        return int(tail[1:])
    return None


def meta_of(path: str | Path) -> dict | None:
    path = str(path)
    mtime = _mtime(path)
    if not mtime:
        return None
    hit = _meta_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    meta = None
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline().strip()
        record = json.loads(first) if first else {}
        if record.get("kind") == "meta":
            meta = record.get("meta", {})
    except Exception:  # noqa: BLE001
        meta = None
    _meta_cache[path] = (mtime, meta)
    return meta


def read_records(path: str | Path) -> list[dict]:
    records: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    # A live runner may be appending while we read. The next poll
                    # will pick up the completed line.
                    continue
    except OSError:
        pass
    return records


def score_for(path: str | Path, *, live: bool = False) -> dict | None:
    if live or score_instance is None:
        return None
    sid = scenario_id_of(name_of(path))
    scenario = SCENARIOS.get(sid)
    if scenario is None:
        return None
    path = str(path)
    mtime = _mtime(path)
    hit = _score_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    out = None
    try:
        result = score_instance(load_trajectory(path), scenario)
        out = {
            "score": round(float(result.get("ftl_score", 0)), 1),
            "solved": bool(result.get("solved")),
            "breakdown": result.get("breakdown") or {},
        }
    except Exception:  # noqa: BLE001
        out = None
    _score_cache[path] = (mtime, out)
    return out


def deep(data: dict | None, *keys):
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data


def frame_of(obs: dict | None):
    obs = obs or {}
    value = obs.get("render_count")
    return value if value is not None else obs.get("tick")


def process_status() -> dict:
    if ftl_process_alive is None:
        return {"known": False, "alive": None, "label": "unknown"}
    try:
        alive = bool(ftl_process_alive())
    except Exception:  # noqa: BLE001
        return {"known": False, "alive": None, "label": "unknown"}
    return {"known": True, "alive": alive, "label": "alive" if alive else "down"}


def run_files(files: list[str], current: str | None) -> set[str]:
    if not current:
        return set()
    cur_meta = meta_of(current) or {}
    cur_run_id = cur_meta.get("run_id")
    cur_agent = cur_meta.get("agent")
    cur_mtime = _mtime(current)
    if cur_run_id:
        return {path for path in files if (meta_of(path) or {}).get("run_id") == cur_run_id}
    if not cur_agent:
        return {current}
    return {
        path
        for path in files
        if (meta_of(path) or {}).get("agent") == cur_agent
        and 0 <= cur_mtime - _mtime(path) <= RUN_WINDOW
    }


def _sys(system_id) -> str:
    try:
        sid = int(system_id)
    except (TypeError, ValueError):
        return str(system_id)
    return SYS_NAMES.get(sid, f"sys{sid}")


def action_view(action: dict) -> dict:
    action_type = action.get("type", "")
    if action_type == "set_system_power":
        return {"kind": "power", "label": f"power {_sys(action.get('system_id'))}={action.get('level')}"}
    if action_type == "move_crew":
        return {"kind": "crew", "label": f"crew {action.get('crew_id')} -> room {action.get('room_id')}"}
    if action_type == "fire_weapon":
        return {"kind": "fire", "label": f"fire w{action.get('weapon_slot')} -> room {action.get('target_room_id')}"}
    if action_type == "fire_beam":
        return {
            "kind": "fire",
            "label": f"beam w{action.get('weapon_slot')} {action.get('room_a')}->{action.get('room_b')}",
        }
    if action_type == "jump":
        return {"kind": "jump", "label": f"jump beacon {action.get('beacon_index')}"}
    if action_type == "leave_sector":
        return {"kind": "jump", "label": "leave sector"}
    if action_type == "choose_event":
        return {"kind": "event", "label": f"event choice {action.get('choice_index')}"}
    if action_type == "set_doors":
        target = f"room {action.get('room_id')}" if action.get("room_id") is not None else "all"
        state = "open" if action.get("open") else "close"
        airlocks = " + airlocks" if action.get("include_airlocks") else ""
        return {"kind": "doors", "label": f"doors {state} {target}{airlocks}"}
    if action_type == "store_buy":
        return {"kind": "store", "label": f"buy {action.get('index')}"}
    if action_type == "store_sell":
        return {"kind": "store", "label": f"sell {action.get('index')}"}
    if action_type == "upgrade_system":
        return {"kind": "store", "label": f"upgrade {_sys(action.get('system_id'))}"}
    if action_type == "hack_system":
        return {"kind": "special", "label": f"hack {_sys(action.get('target_system_id'))}"}
    if action_type == "deploy_drone":
        slot = "" if action.get("slot") is None else f" slot {action.get('slot')}"
        return {"kind": "special", "label": f"drone{slot}"}
    if action_type == "recall_drones":
        return {"kind": "special", "label": "recall drones"}
    if action_type == "teleport_crew":
        label = "board" if action.get("command") == 1 else "recall"
        return {"kind": "special", "label": f"{label} room {action.get('target_room_id')}"}
    if action_type in {"cloak", "battery"}:
        return {"kind": "special", "label": action_type}
    if action_type == "mind_control":
        return {"kind": "special", "label": f"mind room {action.get('target_room_id')}"}
    return {"kind": "other", "label": action_type or "advance"}


def summarize_obs(obs: dict | None) -> dict:
    obs = obs or {}
    player = obs.get("player_ship") or {}
    resources = player.get("resources") or {}
    hull = player.get("hull") or {}
    crew = [crew for crew in player.get("crew", []) or [] if not crew.get("dead")]
    crew_health = [
        float(member.get("health_current") or 0)
        for member in crew
        if member.get("health_current") is not None
    ]
    crew_min = round(min(crew_health), 1) if crew_health else None
    crew_low = sum(1 for hp in crew_health if hp <= 35)
    fires = player.get("fires") or []
    intruders = player.get("intruders") or []
    damaged = []
    repair_needed = []
    offline = []
    system_status = []
    for system in player.get("systems", []) or []:
        name = _sys(system.get("id"))
        power = system.get("power")
        power_max = system.get("power_max")
        damage = system.get("damage") or 0
        needs_repair = bool(system.get("needs_repair"))
        ion = system.get("ion") or 0
        if damage or ion:
            damaged.append(name)
        if needs_repair:
            repair_needed.append(name)
        if power_max and not power and name in {"shields", "engines", "oxygen", "weapons", "medbay"}:
            offline.append(name)
        if name in {"shields", "engines", "oxygen", "weapons", "medbay", "piloting", "doors"}:
            system_status.append(
                {
                    "name": name,
                    "power": power,
                    "max": power_max,
                    "damage": damage,
                    "needs_repair": needs_repair,
                    "ion": ion,
                    "powered": bool(system.get("powered")),
                }
            )
    enemy_hull = None
    enemy = obs.get("enemy_ship")
    enemy_drones = []
    if enemy:
        ehull = enemy.get("hull") or {}
        if ehull.get("current") is not None and ehull.get("max") is not None:
            enemy_hull = f"{ehull.get('current')}/{ehull.get('max')}"
        enemy_drones = [
            {
                "type": drone.get("name")
                or {0: "defense", 1: "combat", 7: "shield"}.get(drone.get("type"), drone.get("type")),
                "firing": bool(drone.get("firing")),
            }
            for drone in (enemy.get("drones") or [])
            if drone.get("deployed")
        ]
    return {
        "sector": deep(obs, "map", "sector"),
        "hull": hull.get("current"),
        "hull_max": hull.get("max"),
        "oxygen": player.get("oxygen_pct"),
        "fuel": resources.get("fuel"),
        "missiles": resources.get("missiles"),
        "parts": resources.get("drone_parts"),
        "scrap": resources.get("scrap"),
        "crew": len(crew),
        "crew_min": crew_min,
        "crew_low": crew_low,
        "fires": sum(int(fire.get("fires") or 0) for fire in fires),
        "fire_rooms": [fire.get("room_id") for fire in fires if fire.get("fires")],
        "intruders": len(intruders),
        "damaged": damaged[:6],
        "repair_needed": repair_needed[:6],
        "offline": offline[:6],
        "systems": system_status,
        "enemy": enemy_hull,
        "enemy_present": bool(enemy),
        "incoming": obs.get("incoming_projectiles") or 0,
        "enemy_drones": enemy_drones,
        "event": bool(obs.get("choice_box_open") or obs.get("event")),
        "store": bool(obs.get("store")),
        "ftl_score": obs.get("ftl_score"),
    }


def _phase_key(item: dict) -> str | None:
    actions = item.get("actions") or []
    kinds = [action.get("kind") for action in actions]
    if not kinds:
        return "wait"
    if any(kind in {"fire", "jump", "event", "store", "special"} for kind in kinds):
        return None
    if not all(kind in {"power", "crew", "doors", "other"} for kind in kinds):
        return None
    state = item.get("state") or {}
    enemy = state.get("enemy") or ""
    enemy_dead = isinstance(enemy, str) and enemy.startswith("0/")
    oxygen = state.get("oxygen")
    recovering = (
        enemy_dead
        or (isinstance(oxygen, (int, float)) and oxygen < 60)
        or bool(state.get("fires"))
    )
    return "recovery" if recovering else "stabilize"


def compact_feed(items: list[dict]) -> list[dict]:
    def summarize(group: list[dict], key: str | None) -> list[dict]:
        if key is None or len(group) < 3:
            return group
        first, last = group[0], group[-1]
        counts: dict[str, int] = defaultdict(int)
        for item in group:
            for action in item.get("actions") or []:
                counts[action.get("kind") or "other"] += 1
        actions = [
            {"kind": kind, "label": f"{kind} x{count}"}
            for kind, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        total_advance = sum((item.get("advance") or 0) for item in group)
        first_state, last_state = first.get("state") or {}, last.get("state") or {}
        return [
            {
                "i": f"{first.get('i')}-{last.get('i')}",
                "thought": last.get("thought"),
                "actions": actions,
                "advance": total_advance,
                "state": last_state,
                "collapsed": True,
                "count": len(group),
                "phase": key,
                "summary": {
                    "hull_from": first_state.get("hull"),
                    "hull_to": last_state.get("hull"),
                    "oxygen_from": first_state.get("oxygen"),
                    "oxygen_to": last_state.get("oxygen"),
                    "fires_from": first_state.get("fires"),
                    "fires_to": last_state.get("fires"),
                },
            }
        ]

    out: list[dict] = []
    group: list[dict] = []
    key: str | None = None
    sentinel = object()
    for item in items + [sentinel]:  # type: ignore[list-item]
        item_key = None if item is sentinel else _phase_key(item)  # type: ignore[arg-type]
        if group and item_key != key:
            out.extend(summarize(group, key))
            group = []
            key = None
        if item is sentinel:
            break
        if item_key:
            group.append(item)  # type: ignore[arg-type]
            key = item_key
        else:
            out.append(item)  # type: ignore[arg-type]
    return out


def aggregate_current(files: list[str], current_paths: set[str], cur_name: str | None) -> dict | None:
    if not SCENARIOS:
        return None
    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for path in files:
        if path not in current_paths:
            continue
        name = name_of(path)
        if name == cur_name:
            continue
        scenario_id = scenario_id_of(name)
        if scenario_id not in SCENARIOS:
            continue
        score = score_for(path, live=False)
        if score:
            by_scenario[scenario_id].append({"path": path, "name": name, **score})
    best = [max(attempts, key=lambda x: (x["solved"], x["score"])) for attempts in by_scenario.values()]
    if not best:
        return None
    return {
        "done": len(best),
        "total": len(SCENARIOS),
        "mean": round(sum(item["score"] for item in best) / len(best), 1),
        "solved": sum(1 for item in best if item["solved"]),
        "attempt_files": sum(len(attempts) for attempts in by_scenario.values()),
    }


def build(sel: str | None) -> dict:
    files = all_files()
    cur = current_file(files)
    cur_name = name_of(cur) if cur else None
    current_paths = run_files(files, cur)
    file_by_name = {name_of(path): path for path in files}

    instances = []
    for path in files:
        name = name_of(path)
        live = name == cur_name
        score = score_for(path, live=live)
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                steps = max(sum(1 for _ in fh) - 1, 0)
        except OSError:
            steps = 0
        meta = meta_of(path) or {}
        scenario_id = scenario_id_of(name)
        instances.append(
            {
                "name": name,
                "scenario": scenario_id,
                "attempt": attempt_of(name),
                "steps": steps,
                "live": live,
                "current": path in current_paths,
                "score": (score or {}).get("score"),
                "solved": (score or {}).get("solved"),
                "tier": meta.get("tier"),
                "type": meta.get("type"),
                "age": _age_seconds(path),
            }
        )

    following = sel in (None, "", "live")
    if following:
        show_name, show_path = cur_name, cur
    elif sel in file_by_name:
        show_name, show_path = sel, file_by_name[sel]
    else:
        show_name, show_path, following = cur_name, cur, True

    header = {
        "instance": show_name,
        "scenario": None,
        "agent": None,
        "run_id": None,
        "steps": 0,
        **summarize_obs(None),
    }
    raw_feed = []
    selected_score = None
    if show_path and os.path.exists(show_path):
        records = read_records(show_path)
        meta = next((record for record in records if record.get("kind") == "meta"), None)
        if meta:
            m = meta.get("meta", {})
            header["agent"] = m.get("agent")
            header["run_id"] = m.get("run_id")
            header["scenario"] = " / ".join(
                str(part)
                for part in (m.get("type"), f"seed {m.get('seed')}", m.get("difficulty"), m.get("tier"))
                if part
            )
        steps = [record for record in records if record.get("kind") == "step"]
        header["steps"] = len(steps)
        if steps:
            header.update(summarize_obs(steps[-1].get("obs") or {}))
        frames = [frame_of(step.get("obs")) for step in steps]
        start = max(0, len(steps) - FEED_TAIL)
        for idx in range(start, len(steps)):
            record = steps[idx]
            advance = None
            if idx > 0 and frames[idx] is not None and frames[idx - 1] is not None:
                advance = frames[idx] - frames[idx - 1]
            obs_summary = summarize_obs(record.get("obs") or {})
            raw_feed.append(
                {
                    "i": record.get("i"),
                    "thought": record.get("thought"),
                    "actions": [action_view(action) for action in (record.get("actions") or [])],
                    "advance": advance,
                    "state": {
                        "hull": obs_summary["hull"],
                        "oxygen": obs_summary["oxygen"],
                        "crew_min": obs_summary["crew_min"],
                        "enemy": obs_summary["enemy"],
                        "fires": obs_summary["fires"],
                        "incoming": obs_summary["incoming"],
                        "enemy_drones": obs_summary["enemy_drones"],
                    },
                }
            )
        selected_score = score_for(show_path, live=(show_name == cur_name))

    cur_meta = meta_of(cur) if cur else None
    return {
        "instances": instances,
        "selected": show_name,
        "following_live": following,
        "header": header,
        "feed": compact_feed(raw_feed),
        "agg": aggregate_current(files, current_paths, cur_name),
        "selected_score": selected_score,
        "process": process_status(),
        "run": {
            "agent": (cur_meta or {}).get("agent"),
            "run_id": (cur_meta or {}).get("run_id"),
            "current_instance": cur_name,
            "suite": str(SUITE),
            "bench": str(BENCH),
            "dashboard_built": (DASHBOARD_DIST / "index.html").exists(),
        },
        "now": int(time.time()),
    }


def _missing_dashboard_html() -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>ftl_bench live</title></head>
<body style="font-family: system-ui; margin: 40px; max-width: 760px">
<h1>ftl_bench live API is running</h1>
<p>The React dashboard has not been built yet.</p>
<pre>cd {REPO / "dashboard"}
npm install
npm run build
cd {REPO / "harness"}
uv run --extra dashboard python ../adapter/ftl_live.py</pre>
<p>JSON endpoint: <a href="/api/state">/api/state</a></p>
</body></html>"""


def create_app():
    if FastAPI is None:
        return None
    app = FastAPI(title="ftl_bench live", version="0.1.0")

    @app.get("/api/health")
    def api_health():
        return {
            "ok": True,
            "bench": str(BENCH),
            "suite": str(SUITE),
            "dashboard_built": (DASHBOARD_DIST / "index.html").exists(),
            "scorer": score_instance is not None,
        }

    @app.get("/api/state")
    def api_state(sel: str = Query("live")):
        return build(sel)

    assets = DASHBOARD_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    @app.get("/{path:path}")
    def frontend(path: str = ""):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        index = DASHBOARD_DIST / "index.html"
        requested = (DASHBOARD_DIST / path).resolve()
        root = DASHBOARD_DIST.resolve()
        try:
            requested.relative_to(root)
            inside_root = True
        except ValueError:
            inside_root = False
        if inside_root and requested.is_file():
            return FileResponse(requested)
        if index.exists():
            return FileResponse(index)
        return HTMLResponse(_missing_dashboard_html())

    return app


app = create_app()


def main() -> None:
    if app is None:
        print("FastAPI dashboard dependencies are missing.")
        print("Run: cd harness && uv sync --extra dashboard")
        print("Then: uv run --extra dashboard python ../adapter/ftl_live.py")
        raise SystemExit(2)
    try:
        import uvicorn
    except Exception:  # noqa: BLE001
        print("uvicorn is missing. Run: cd harness && uv sync --extra dashboard")
        raise SystemExit(2)
    print(
        f"ftl_bench live dashboard: http://{HOST}:{PORT} "
        f"(bench={BENCH}, scorer={'on' if score_instance else 'off'})"
    )
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
