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

import json
import hashlib
import ipaddress
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

from visual_comparison import comparison_catalog, comparison_view, trial_kind, trial_label
from visual_annotations import trial_annotations

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "harness" / "src"))

DEFAULT_BENCH = (REPO / "harness" / "runs" / "benchmark"
                 if (REPO / "harness" / "pyproject.toml").exists() else Path.cwd() / "runs" / "benchmark")
BENCH = Path(os.environ.get("FTL_BENCH_DIR") or DEFAULT_BENCH)
SUITE = Path(os.environ.get("FTL_SUITE") or (REPO / "scenarios" / "suite_v1.json"))
DASHBOARD_DIST = REPO / "dashboard" / "dist"
PORT = int(os.environ.get("FTL_LIVE_PORT", "8765"))
HOST = os.environ.get("FTL_LIVE_HOST", "127.0.0.1")
FEED_TAIL = int(os.environ.get("FTL_LIVE_TAIL", "120"))
DECISION_KINDS = {"step", "step_timeout", "step_unacknowledged", "model_error", "external_interference"}

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
    from ftl_bench import load_suite, score_instance
    from ftl_bench.scenario import Scenario
    from ftl_bench.reporting import summarize_model_usage, validation_from_directory
    from ftl_bench.session import ftl_process_alive
except Exception:  # noqa: BLE001
    load_suite = score_instance = Scenario = None
    summarize_model_usage = None
    validation_from_directory = None
    ftl_process_alive = None
try:
    SCENARIOS = {s.id: s for s in load_suite(str(SUITE))} if load_suite else {}
except (OSError, ValueError, KeyError, TypeError):
    SCENARIOS = {}

_score_cache: dict[str, tuple[tuple[int, int] | None, dict | None]] = {}
_snapshot_cache: dict[str, tuple[tuple[int, int], dict]] = {}
_discovery_cache: dict[str, tuple[tuple[int, int], bool]] = {}


def _signature(path: str | Path) -> tuple[int, int] | None:
    try:
        stat = Path(path).stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _mtime(path: str | Path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _age_seconds(path: str | Path) -> int:
    mtime = _mtime(path)
    return max(0, int(time.time() - mtime)) if mtime else 0


def is_trajectory(path: Path) -> bool:
    """Recognize recorder data, independent of legacy trajectory filenames.

    Diagnostic JSONL sidecars have protocol headers and numeric trace kinds;
    they are evidence files, not harness episodes. Read a bounded prefix so
    discovery does not load their full traces on every dashboard refresh.
    """
    signature = _signature(path)
    key = str(path)
    hit = _discovery_cache.get(key)
    if signature and hit and hit[0] == signature:
        return hit[1]
    recognized = False
    kinds = DECISION_KINDS | {"reset", "setup", "start_game", "reset_episode",
        "terminal_observation", "final_observation", "fixture_setup", "pause-check", "end"}
    try:
        with path.open("r", encoding="utf-8") as stream:
            for _ in range(16):
                line = stream.readline(65537)
                if not line or len(line) > 65536:
                    break
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # A live append may not have completed its header.
                if not isinstance(record, dict):
                    continue
                kind = record.get("kind")
                recognized = (kind == "meta" and isinstance(record.get("meta"), dict)
                    or isinstance(kind, str) and kind in kinds
                    and any(field in record for field in ("obs", "actions", "visual", "status")))
                if recognized or "protocol" in record:
                    break
    except (OSError, UnicodeError):
        pass
    if signature:
        _discovery_cache[key] = (signature, recognized)
    return recognized


def all_files() -> list[str]:
    files = [str(path) for path in BENCH.rglob("*.jsonl") if path.is_file() and is_trajectory(path)]
    return sorted(files, key=_mtime, reverse=True)


def name_of(path: str | Path) -> str:
    """A stable selection key, including the run directory to avoid collisions."""
    path = Path(path)
    try:
        return path.resolve().relative_to(BENCH.resolve()).with_suffix("").as_posix()
    except ValueError:
        return path.stem


def scenario_id_of(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
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


def read_records(path: str | Path) -> list[dict]:
    return snapshot_of(path)["records"]


def snapshot_of(path: str | Path) -> dict:
    path = str(path)
    signature = _signature(path)
    hit = _snapshot_cache.get(path)
    if signature and hit and hit[0] == signature:
        return hit[1]
    records: list[dict] = []
    invalid = False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if isinstance(record, dict):
                        records.append(record)
                    else:
                        invalid = True
                except json.JSONDecodeError:
                    # A live runner may be appending while we read. The next poll
                    # will pick up the completed line.
                    invalid = True
    except (OSError, UnicodeError):
        invalid = True
    meta = next((record.get("meta") for record in records if record.get("kind") == "meta"), {})
    terminal = next((record for record in reversed(records) if record.get("kind") == "end"), None)
    snapshot = {
        "records": records,
        "meta": meta if isinstance(meta, dict) else {},
        "terminal": terminal,
        "invalid": invalid,
    }
    if signature:
        _snapshot_cache[path] = (signature, snapshot)
    return snapshot


def meta_of(path: str | Path) -> dict:
    return snapshot_of(path)["meta"]


def scenario_for(path: str | Path):
    meta = meta_of(path)
    definition = meta.get("scenario")
    if isinstance(definition, dict) and Scenario is not None:
        try:
            return Scenario.from_dict(definition)
        except (KeyError, TypeError, ValueError):
            return None
    return SCENARIOS.get(meta.get("scenario_id") or scenario_id_of(name_of(path)))


def score_for(path: str | Path, *, live: bool = False) -> dict | None:
    if live or score_instance is None:
        return None
    scenario = scenario_for(path)
    if scenario is None:
        return None
    path = str(path)
    signature = _signature(path)
    hit = _score_cache.get(path)
    if hit and hit[0] == signature:
        return hit[1]
    out = None
    try:
        snapshot = snapshot_of(path)
        if snapshot["invalid"]:
            return None
        if not any(isinstance(record.get("obs"), dict) and record["obs"].get("game_started") is True
                   for record in snapshot["records"]):
            # Startup failures have lifecycle records but no gameplay to score.
            return None
        result = score_instance(snapshot["records"], scenario)
        out = {
            "score": round(float(result.get("ftl_score", 0)), 1),
            "solved": bool(result.get("solved")),
            "breakdown": result.get("breakdown") or {},
        }
    except Exception:  # noqa: BLE001
        out = None
    _score_cache[path] = (signature, out)
    return out


def deep(data: dict | None, *keys):
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data


def elapsed_between(record: dict, previous: dict | None) -> float | None:
    values = [row.get("t") for row in (record, previous or {})]
    if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
        return None
    elapsed = values[0] - values[1]
    return round(elapsed, 3) if elapsed >= 0 else None


def selected_trajectory(selection: str) -> Path:
    """Select a recorded trajectory by its discovered key, never by a URL path."""
    selected = next((Path(path) for path in all_files() if name_of(path) == selection), None)
    if selected is None:
        raise ValueError("trajectory not found")
    selected = selected.resolve()
    try:
        selected.relative_to(BENCH.resolve())
    except ValueError as exc:
        raise ValueError("trajectory outside run root") from exc
    return selected


def visual_view(record: dict, path: str | Path, record_index: int) -> dict | None:
    """Add endpoint URLs without giving clients arbitrary filesystem access."""
    visual = record.get("visual")
    if not isinstance(visual, dict):
        return None
    result = {key: visual[key] for key in ("observation_mode", "inputs", "advance", "outcome", "visible_summary",
                                         "visible_summary_provenance", "external_input_guard", "planned_inputs")
              if key in visual}
    for phase in ("before", "after"):
        frame = visual.get(phase)
        if not isinstance(frame, dict):
            continue
        result[phase] = {key: frame[key] for key in ("path", "width", "height", "frame_id", "sha256") if key in frame}
        result[phase]["url"] = "/api/artifact?" + urlencode({"sel": name_of(path), "record": record_index, "phase": phase})
    return result


def replay_snapshot(selection: str, index: int | None = None) -> dict:
    path = selected_trajectory(selection)
    rows = visual_replay_rows(read_records(path))
    if not rows:
        return {"selected": selection, "total": 0, "index": None, "item": None}
    chosen = len(rows) - 1 if index is None else index
    if chosen < 0 or chosen >= len(rows):
        raise ValueError("replay index not found")
    ordinal, row = rows[chosen]
    return {"selected": selection, "total": len(rows), "index": chosen,
            "item": {"i": row.get("i"), "thought": row.get("thought"), "model": row.get("model"),
                     "record_kind": row.get("kind"),
                     "ack_timeout": row.get("kind") in {"step_timeout", "step_unacknowledged"},
                     "visual": visual_view(row, path, ordinal)}}


def visual_replay_rows(records):
    rows = [(ordinal, row) for ordinal, row in enumerate(records)
            if row.get("kind") in DECISION_KINDS | {"model_cancelled"} and isinstance(row.get("visual"), dict)]
    if not rows:
        rows = [(ordinal, row) for ordinal, row in enumerate(records)
                if row.get("kind") in {"reset", "fixture_setup"} and isinstance(row.get("visual"), dict)]
    return rows


def recorded_image(selection: str, record_index: int, phase: str) -> tuple[Path, str]:
    """Only serve a recorded image inside that trajectory's own directory.

    Resolving both paths rejects symlink/junction escapes. Image magic and the
    optional recorded hash prevent serving another file under an image suffix.
    """
    if phase not in {"before", "after"} or record_index < 0:
        raise ValueError("image not found")
    path = selected_trajectory(selection)
    records = read_records(path)
    if record_index >= len(records):
        raise ValueError("image not found")
    frame = deep(records[record_index], "visual", phase)
    name = frame.get("path") if isinstance(frame, dict) else None
    if not isinstance(name, str) or not name or any(char in name for char in ("\\", ":", "\x00")):
        raise ValueError("invalid image path")
    relative = Path(name)
    if relative.is_absolute() or any(part in {".", ".."} for part in name.split("/")):
        raise ValueError("invalid image path")
    image = (path.parent / relative).resolve()
    try:
        image.relative_to(path.parent)
    except ValueError as exc:
        raise ValueError("image outside trajectory directory") from exc
    suffix_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    media_type = suffix_types.get(image.suffix.lower())
    if media_type is None or not image.is_file() or image.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("image unavailable")
    with image.open("rb") as stream:
        prefix = stream.read(12)
        valid = (media_type == "image/png" and prefix.startswith(b"\x89PNG\r\n\x1a\n")
                 or media_type == "image/jpeg" and prefix.startswith(b"\xff\xd8\xff")
                 or media_type == "image/webp" and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP")
        if not valid:
            raise ValueError("invalid image content")
        expected_hash = frame.get("sha256")
        if expected_hash is not None:
            stream.seek(0)
            actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if not isinstance(expected_hash, str) or actual_hash != expected_hash.lower():
                raise ValueError("recorded image hash mismatch")
    return image, media_type


def process_status() -> dict:
    if ftl_process_alive is None:
        return {"known": False, "alive": None, "label": "unknown"}
    try:
        alive = bool(ftl_process_alive())
    except Exception:  # noqa: BLE001
        return {"known": False, "alive": None, "label": "unknown"}
    return {"known": True, "alive": alive, "label": "alive" if alive else "down"}


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
    if action_type == "upgrade_reactor":
        return {"kind": "store", "label": "upgrade reactor"}
    if action_type == "wait_for_fuel":
        return {"kind": "event", "label": "native fuel recovery turn"}
    if action_type == "set_distress":
        return {"kind": "event", "label": f"distress {'on' if action.get('enabled') else 'off'}"}
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


def _player_owned_crew(member: dict) -> bool:
    # Explicit ownership distinguishes our boarders from hostile boarders. Older
    # recordings expose only intruder/on_enemy_ship, or neither field.
    if isinstance(member.get("player_owned"), bool):
        return member["player_owned"]
    owner = member.get("owner_ship_id")
    if isinstance(owner, int) and not isinstance(owner, bool):
        return owner == 0
    return not member.get("intruder") or member.get("on_enemy_ship") is True


def summarize_obs(obs: dict | None) -> dict:
    obs = obs or {}
    player = obs.get("player_ship") or {}
    resources = player.get("resources") or {}
    hull = player.get("hull") or {}
    crew = [crew for crew in player.get("crew", []) or [] if _player_owned_crew(crew) and not crew.get("dead")
            and (not isinstance(crew.get("health_current"), (int, float)) or crew["health_current"] > 0)]
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
        "crew": len(crew) if isinstance(player.get("crew"), list) else None,
        "crew_min": crew_min,
        "crew_low": crew_low,
        "fires": sum(int(fire.get("fires") or 0) for fire in fires) if isinstance(player.get("fires"), list) else None,
        "fire_rooms": [fire.get("room_id") for fire in fires if fire.get("fires")],
        "intruders": len(intruders),
        "damaged": damaged[:6],
        "repair_needed": repair_needed[:6],
        "offline": offline[:6],
        "systems": system_status,
        "enemy": enemy_hull,
        "enemy_present": bool(enemy),
        "enemy_hostile": enemy.get("hostile") if enemy and isinstance(enemy.get("hostile"), bool) else None,
        "incoming": obs.get("incoming_projectiles") or 0,
        "enemy_drones": enemy_drones,
        "event": bool(obs.get("choice_box_open") or obs.get("event")),
        "store": bool(obs.get("store")),
        "ftl_score": obs.get("ftl_score"),
    }


def _phase_key(item: dict) -> str | None:
    if item.get("ack_timeout") or item.get("visual"):
        return None
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
            {"kind": kind, "label": f"{kind} x{count}", "count": count}
            for kind, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        elapsed = [item.get("elapsed_seconds") for item in group]
        total_elapsed = round(sum(elapsed), 3) if all(value is not None for value in elapsed) else None
        first_state, last_state = first.get("state") or {}, last.get("state") or {}
        return [
            {
                "i": f"{first.get('i')}-{last.get('i')}",
                "thought": last.get("thought"),
                "model": last.get("model"),
                "actions": actions,
                "elapsed_seconds": total_elapsed,
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


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def discover_runs(files: list[str]) -> tuple[dict[str, dict], dict[str, str]]:
    """Group attempts by recorded run identity, including runs still preparing."""
    runs: dict[str, dict] = {}
    file_runs: dict[str, str] = {}
    for manifest_path in BENCH.rglob("run.json"):
        manifest = _read_json(manifest_path)
        if not manifest:
            continue
        key = str(manifest_path.parent.resolve())
        annotations = trial_annotations(manifest_path.parent)
        runs[key] = {**manifest, "key": key, "paths": [], "directory": str(manifest_path.parent),
                     "activity": _mtime(manifest_path),
                     "validation": validation_for_run(manifest, manifest_path.parent)}
        if annotations["operator_recovery"] is not None:
            runs[key].update(status="interrupted", reason="abrupt_operator_stop",
                             raw_status=manifest.get("status"), operator_recovery=annotations["operator_recovery"])
    for path in files:
        meta = meta_of(path)
        directory_key = str(Path(path).parent.resolve())
        run_id = meta.get("run_id")
        key = directory_key if directory_key in runs else f"recorded:{run_id}" if run_id else f"legacy:{path}"
        if key not in runs:
            runs[key] = {"key": key, "run_id": run_id, "agent": meta.get("agent"),
                         "status": "unknown", "paths": [], "directory": str(Path(path).parent),
                         "activity": 0, "started_at": 0,
                         "validation": validation_for_run({}, Path(path).parent)}
        run = runs[key]
        run["paths"].append(path)
        run["activity"] = max(run["activity"], _mtime(path))
        records = read_records(path)
        timestamp = next((r.get("t") for r in records if r.get("kind") == "meta"), None)
        if not run.get("started_at") and isinstance(timestamp, (int, float)):
            run["started_at"] = timestamp
        file_runs[path] = key
    return runs, file_runs


def validation_for_run(run: dict, directory: Path) -> dict:
    if validation_from_directory:
        return validation_from_directory(directory, run)
    # The static reader still exposes explicit manifest restrictions when scoring is unavailable.
    excluded = run.get("validation_status") == "diagnostic_only" or run.get("valid_for_model_comparison") is False
    return {"status": run.get("validation_status"), "comparison_eligible": not excluded,
            "valid_for_model_comparison": False if excluded else None,
            "limitations": run.get("validation_limitations") or []}


def lifecycle(path: str, run: dict) -> dict:
    snapshot = snapshot_of(path)
    terminal = snapshot["terminal"]
    if terminal:
        return {"status": terminal.get("status") or "completed", "reason": terminal.get("reason"),
                "error": terminal.get("error"), "finalized": not snapshot["invalid"]}
    if run.get("operator_recovery"):
        return {"status": "interrupted", "reason": "abrupt_operator_stop", "error": None, "finalized": False}
    # An end-less file from a terminal run was interrupted before it could be closed.
    if run.get("status") in {"completed", "error", "failed", "interrupted"}:
        return {"status": "incomplete", "reason": "missing_terminal_record", "error": None, "finalized": False}
    if run.get("status") == "running":
        newest = max(run["paths"], key=_mtime, default=None)
        return {"status": "running" if path == newest else "incomplete", "reason": None,
                "error": None, "finalized": False}
    return {"status": "unknown", "reason": "legacy_lifecycle_unavailable", "error": None, "finalized": False}


def aggregate_current(paths: list[str], states: dict[str, dict], run: dict) -> dict:
    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for path in paths:
        state = states[path]
        if not state["finalized"]:
            continue
        meta = meta_of(path)
        sid = meta.get("scenario_id") or scenario_id_of(name_of(path))
        score = score_for(path)
        by_scenario[sid].append({**state, **(score or {}), "scored": score is not None})
    best = [max(attempts, key=lambda item: (bool(item.get("solved")), item.get("score", 0)))
            for attempts in by_scenario.values()]
    recorded_scored = [item for item in best if item["scored"]]
    validation = run.get("validation") or validation_for_run(run, Path(run.get("directory") or BENCH))
    comparison = best if validation["comparison_eligible"] else []
    scored = [item for item in comparison if item["scored"]]
    planned = run.get("scenario_ids")
    total = len(planned) if isinstance(planned, list) else len({
        meta_of(path).get("scenario_id") or scenario_id_of(name_of(path)) for path in paths
    })
    return {
        "done": len(best), "total": total, "total_known": isinstance(planned, list),
        "mean": round(sum(item["score"] for item in scored) / len(scored), 1) if scored else None,
        "solved": sum(bool(item.get("solved")) for item in comparison), "scored": len(scored),
        "comparison_instances": len(scored), "comparison_excluded": 0 if validation["comparison_eligible"] else len(recorded_scored),
        "recorded_scored": len(recorded_scored),
        "recorded_mean": round(sum(item["score"] for item in recorded_scored) / len(recorded_scored), 1) if recorded_scored else None,
        "recorded_solved": sum(bool(item.get("solved")) for item in best),
        "attempt_files": sum(len(attempts) for attempts in by_scenario.values()),
        "failed": sum(item["status"] in {"error", "failed"} for item in comparison),
        "interrupted": sum(item["status"] == "interrupted" for item in comparison),
        "attempt_failures": sum(item["status"] in {"error", "failed"}
                                for attempts in by_scenario.values() for item in attempts),
        "attempt_interrupted": sum(item["status"] == "interrupted"
                                   for attempts in by_scenario.values() for item in attempts),
        "incomplete": sum(states[path]["status"] == "incomplete" for path in paths),
    }


def _run_view(run: dict | None, states: dict[str, dict]) -> dict:
    run = run or {}
    paths = sorted(run.get("paths") or [], key=_mtime, reverse=True)
    active = next((path for path in paths if states[path]["status"] == "running"), None)
    status = run.get("status") or "unknown"
    if status == "unknown" and paths and all(states[path]["finalized"] for path in paths):
        statuses = {states[path]["status"] for path in paths}
        status = "interrupted" if "interrupted" in statuses else "error" if statuses & {"error", "failed"} else "completed"
    return {
        "agent": run.get("agent"), "run_id": run.get("run_id"), "status": status,
        "reason": run.get("reason"), "error": run.get("error"),
        "current_instance": name_of(paths[0]) if paths else None,
        "active_instance": name_of(active) if active else None,
        "suite": run.get("suite") or str(SUITE), "bench": str(BENCH),
        "dashboard_built": (DASHBOARD_DIST / "index.html").exists(),
        "validation": run.get("validation") or validation_for_run(run, Path(run.get("directory") or BENCH)),
    }


def visual_trial_report(trajectory: str | None) -> dict | None:
    """Expose fixed, bounded sibling receipts for the selected visual trial."""
    if not trajectory:
        return None
    directory = Path(trajectory).resolve().parent
    root = BENCH.resolve()
    if not directory.is_relative_to(root):
        return None
    result = {}
    for filename, key in (("validation.json", "validation"), ("visual-report.json", "report"),
                          ("run.json", "run")):
        path = directory / filename
        try:
            if path.is_symlink() or path.resolve().parent != directory or path.stat().st_size > 2 * 1024 * 1024:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                result[key] = value
        except (OSError, ValueError, UnicodeError):
            continue
    run = result.get("run", {})
    validation = result.get("validation", {})
    report = result.get("report", {})
    if run.get("track") != "visual-v1" and report.get("track") != "visual-v1":
        return None
    def checks(key):
        section = validation.get(key)
        values = section.get("checks") if isinstance(section, dict) else None
        return {str(name): value for name, value in values.items() if type(value) is bool} if isinstance(values, dict) else {}
    return {"challenge": run.get("challenge"), "repetition": run.get("repetition"),
            "task": run.get("public_task"), "model": run.get("model"),
            "task_version": run.get("task_version"),
            "mode": run.get("observation_mode", report.get("observation_mode")),
            "outcome": validation.get("outcome_category", report.get("outcome_category")),
            "reason": report.get("reason", run.get("reason")),
            "setup_only": run.get("setup_only") is True,
            "setup_checks": checks("setup"), "outcome_checks": checks("outcome"),
            "save_restoration": run.get("save_restoration"),
            "limitations": [v for v in run.get("limitations", []) if isinstance(v, str)]
                           if isinstance(run.get("limitations"), list) else [],
            "error": validation.get("error") or run.get("error"),
            **trial_annotations(directory)}


def build(sel: str | None) -> dict:
    files = all_files()
    runs, file_runs = discover_runs(files)
    latest = max(runs.values(), key=lambda run: (run.get("started_at") or run["activity"], run["activity"]), default=None)
    current_paths = set((latest or {}).get("paths") or [])
    states = {path: lifecycle(path, runs[file_runs[path]]) for path in files}
    file_by_name = {name_of(path): path for path in files}
    following = sel in (None, "", "live", "latest")
    show_path = max(current_paths, key=_mtime, default=None) if following else file_by_name.get(sel)
    if not following and show_path is None:
        following = True
        show_path = max(current_paths, key=_mtime, default=None)
    selected_run = runs[file_runs[show_path]] if show_path else latest
    show_name = name_of(show_path) if show_path else None
    instances = []
    for path in files:
        meta = meta_of(path)
        state = states[path]
        score = score_for(path, live=state["status"] in {"running", "incomplete"})
        instances.append({
            "name": name_of(path), "label": trial_label(runs[file_runs[path]], Path(path).stem),
            "trial_kind": trial_kind(runs[file_runs[path]]),
            "scenario": meta.get("scenario_id") or scenario_id_of(name_of(path)),
            "run_id": meta.get("run_id"), "attempt": attempt_of(Path(path).stem),
            "steps": sum(record.get("kind") in DECISION_KINDS for record in read_records(path)),
            "live": state["status"] == "running", "current": path in current_paths,
            "score": (score or {}).get("score"), "solved": (score or {}).get("solved"),
            "tier": meta.get("tier"), "type": meta.get("type"), "age": _age_seconds(path),
            "partial": snapshot_of(path)["invalid"], **state,
            "comparison_eligible": runs[file_runs[path]]["validation"]["comparison_eligible"],
        })
    header = {"instance": show_name, "scenario": None, "agent": None, "run_id": None,
              "steps": 0, "status": "preparing" if (selected_run or {}).get("status") == "running" else "unknown",
              "reason": None, "error": None, "live": False,
              **summarize_obs(None)}
    raw_feed = []
    selected_score = None
    if show_path:
        snapshot = snapshot_of(show_path)
        records, meta = snapshot["records"], snapshot["meta"]
        state = states[show_path]
        header.update({"agent": meta.get("agent"), "run_id": meta.get("run_id"),
                       "status": state["status"], "reason": state["reason"], "error": state["error"],
                       "live": state["status"] == "running", "partial": snapshot["invalid"]})
        header["scenario"] = " / ".join(str(part) for part in (
            meta.get("type"), f"seed {meta['seed']}" if meta.get("seed") is not None else None,
            meta.get("difficulty"), meta.get("tier")) if part)
        observations = [record["obs"] for record in records if isinstance(record.get("obs"), dict)]
        if observations:
            in_game = [obs for obs in observations if obs.get("game_started")]
            header.update(summarize_obs((in_game or observations)[-1]))
        header["model_usage"] = summarize_model_usage(records) if summarize_model_usage else None
        steps = [record for record in records if record.get("kind") in DECISION_KINDS]
        header["steps"] = len(steps)
        header["visual_steps"] = len(visual_replay_rows(records))
        record_indices = {id(record): ordinal for ordinal, record in enumerate(records)}
        for idx in range(max(0, len(steps) - FEED_TAIL), len(steps)):
            record = steps[idx]
            elapsed = elapsed_between(record, steps[idx - 1] if idx > 0 else None)
            summary = summarize_obs(record.get("obs") if isinstance(record.get("obs"), dict) else None)
            raw_feed.append({"i": record.get("i"), "thought": record.get("thought"),
                             "record_kind": record.get("kind"),
                             "model": record.get("model"),
                             "visual": visual_view(record, show_path, record_indices[id(record)]),
                             "ack_timeout": record.get("kind") in {"step_timeout", "step_unacknowledged"},
                             "actions": [action_view(action) for action in (record.get("actions") or []) if isinstance(action, dict)],
                             "elapsed_seconds": elapsed, "state": {key: summary[key] for key in (
                                 "hull", "oxygen", "crew_min", "enemy", "enemy_hostile", "fires", "incoming", "enemy_drones")}})
        selected_score = score_for(show_path, live=state["status"] in {"running", "incomplete"})
    return {
        "instances": instances, "selected": show_name, "following_live": following,
        "header": header, "feed": compact_feed(raw_feed), "selected_score": selected_score,
        "agg": aggregate_current(selected_run["paths"], states, selected_run) if selected_run else None,
        "process": process_status(), "run": _run_view(selected_run, states),
        "latest_run": _run_view(latest, states), "now": int(time.time()),
        "visual_trial": visual_trial_report(show_path),
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

    @app.get("/api/comparisons")
    def api_comparisons(key: str | None = None):
        try:
            return comparison_catalog(BENCH) if key is None else comparison_view(BENCH, key)
        except (ValueError, OSError, UnicodeError):
            raise HTTPException(status_code=404, detail="comparison unavailable") from None

    @app.get("/api/replay")
    def api_replay(sel: str, index: int | None = Query(None, ge=0)):
        try:
            return replay_snapshot(sel, index)
        except (ValueError, OSError):
            raise HTTPException(status_code=404, detail="replay not found") from None

    @app.get("/api/artifact")
    def api_artifact(sel: str, record: int = Query(ge=0), phase: str = Query(pattern="^(before|after)$")):
        try:
            image, media_type = recorded_image(sel, record, phase)
            return FileResponse(image, media_type=media_type,
                                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
        except (ValueError, OSError):
            raise HTTPException(status_code=404, detail="recorded image unavailable") from None

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
    try:
        local_host = HOST == "localhost" or ipaddress.ip_address(HOST).is_loopback
    except ValueError:
        local_host = False
    if not local_host:
        print("The local dashboard requires a loopback host (127.0.0.1, localhost, or ::1).")
        raise SystemExit(2)
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
