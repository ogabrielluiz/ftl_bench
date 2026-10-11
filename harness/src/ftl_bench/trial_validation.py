"""Offline evidence checks for one v4 through v7 Codex full-game trial.

This validates recorded interface/provenance evidence, not model quality or remote
model routing. Missing evidence is inconclusive; declared capabilities alone never
substitute for a missing action acknowledgment or score component.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .observation import is_living_player_crew
from .reporting import load_run_report

CAPABILITIES = ("manual_fire", "global_autofire_control", "live_score", "victory",
                "crew_ownership", "crew_control_guard", "event_choice_state",
                "upgrade_rules", "fuel_recovery")
GUARDED = ("move_crew", "choose_event", "upgrade_system", "upgrade_reactor",
           "wait_for_fuel", "set_distress")


def _integer(value):
    return type(value) is int


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _basename(value):
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]


def verify_codex_trial_v4(directory: Path | str, *, model="gpt-6.1-sol", effort="medium", seed=1) -> dict:
    return _verify_trial(directory, model=model, effort=effort, seed=seed, version="v4")


def verify_codex_trial_v5(directory: Path | str, *, model="gpt-6.1-sol", effort="medium", seed=1) -> dict:
    return _verify_trial(directory, model=model, effort=effort, seed=seed, version="v5")


def verify_codex_trial_v6(directory: Path | str, *, model="gpt-6.1-sol", effort="medium", seed=1) -> dict:
    return _verify_trial(directory, model=model, effort=effort, seed=seed, version="v6")


def verify_codex_trial_v7(directory: Path | str, *, model="gpt-6.1-sol", effort="medium", seed=1) -> dict:
    return _verify_trial(directory, model=model, effort=effort, seed=seed, version="v7")


def _verify_trial(directory, *, model, effort, seed, version):
    try:
        return _verify_codex_trial_v4(directory, model=model, effort=effort, seed=seed, version=version)
    except (AttributeError, TypeError, ValueError, KeyError, IndexError, OSError) as error:
        return {"verifier": f"codex-{version}-recorded-evidence-v1", "validation_status": "inconclusive",
                "valid_for_model_comparison": False, "record_integrity_checks_passed": False,
                "limitations": [f"Malformed or unsupported artifact structure prevents verification ({type(error).__name__})."],
                "errors": [], "report_complete": False,
                "scope": "No validity claim; the artifact structure could not be verified."}


def _verify_codex_trial_v4(directory: Path | str, *, model, effort, seed, version="v4") -> dict:
    directory = Path(directory).resolve()
    errors, gaps = [], []
    snapshots, scores, model_requests = 0, [], 0
    runtime_checks = {}
    guarded = GUARDED + (("leave_sector",) if version in {"v5", "v6", "v7"} else ()) + (("jump",) if version in {"v6", "v7"} else ()) + (("fire_weapon", "fire_beam") if version == "v7" else ())
    required_caps = CAPABILITIES + (("sector_navigation",) if version in {"v5", "v6", "v7"} else ()) + (("beacon_navigation",) if version in {"v6", "v7"} else ()) + (("enemy_hostility",) if version == "v7" else ())
    feedback_counts = {kind: {"requested": 0, "applied": 0, "rejected": 0, "unproven": 0} for kind in guarded}
    pending_choices = disabled_choices = 0

    def issue(message, *, missing=False):
        target = gaps if missing else errors
        if message not in target:
            target.append(message)

    def check_hostility(snapshot, label):
        if version != "v7" or not isinstance(snapshot, dict) or snapshot.get("game_started") is not True:
            return
        enemy = snapshot.get("enemy_ship")
        if not isinstance(enemy, dict):
            return
        if not isinstance(enemy.get("hostile"), bool):
            issue(label + ": native enemy hostility unavailable", missing=True)
        if not isinstance(enemy.get("targetable"), bool):
            issue(label + ": native enemy targetability unavailable", missing=True)
        elif enemy["targetable"] and enemy.get("hostile") is not True:
            issue(label + ": targetability claims a non-hostile or unknown enemy is targetable")

    def read_object(path):
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("expected an object")
            return value
        except (OSError, ValueError, UnicodeError) as error:
            issue(f"{path.name}: {error}", missing=True)
            return {}

    def match(value, expected, label):
        if value is None:
            issue(f"{label}: missing evidence", missing=True)
        elif type(value) is not type(expected) or value != expected:
            issue(f"{label}: expected {expected!r}, recorded {value!r}")

    manifest = read_object(directory / "run.json")
    for key, expected in {"runner_version": version, "ruleset": version, "backend": "codex", "model": model,
                          "reasoning_effort": effort, "prompt_version": "v5", "mode": "gameover",
                          "retries": 0, "control_contract": "owned-player-crew-v1",
                          "economy_contract": "native-economy-and-fuel-recovery-v1"}.items():
        match(manifest.get(key), expected, f"manifest.{key}")
    if version in {"v5", "v6", "v7"}:
        match(manifest.get("routing_contract"), "native-sector-neighbors-v1", "manifest.routing_contract")
    if version in {"v6", "v7"}:
        match(manifest.get("beacon_contract"), "native-beacon-readiness-v1", "manifest.beacon_contract")
    if version == "v7":
        match(manifest.get("hostility_contract"), "native-enemy-hostility-v1", "manifest.hostility_contract")
    if manifest.get("validation_status") == "diagnostic_only" or manifest.get("valid_for_model_comparison") is False:
        issue("The manifest explicitly excludes this run from model comparison.", missing=True)
    planned = manifest.get("scenario_ids")
    if not isinstance(planned, list) or len(planned) != 1:
        issue("Expected exactly one planned scenario for this single-attempt trial.")

    runtime = manifest.get("runtime") or {}
    for kind in ("bridge_lua", "native_dll", "prompt"):
        info = runtime.get(kind) or {}
        digest = info.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            issue(f"runtime.{kind}: missing SHA256", missing=True)
            runtime_checks[kind] = False
            continue
        archive = directory / "runtime" / _basename(info.get("path", ""))
        try:
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            runtime_checks[kind] = actual == digest.lower()
            if not runtime_checks[kind]:
                issue(f"runtime.{kind}: archived SHA256 mismatch")
        except OSError:
            runtime_checks[kind] = False
            issue(f"runtime.{kind}: archived file unavailable; current installed files are not an archive substitute", missing=True)
    native_build = runtime.get("native_build") or {}
    protocol = native_build.get("native_protocol")
    if not _integer(protocol) or protocol < 5:
        issue("runtime.native_build: protocol 5 provenance unavailable", missing=True)
    match(native_build.get("dll_sha256"), (runtime.get("native_dll") or {}).get("sha256"), "native build DLL identity")
    match(native_build.get("matches_installed_dll"), True, "native build installed identity")
    if version in {"v6", "v7"}:
        digest = native_build.get("patch_sha256")
        try:
            actual = hashlib.sha256((directory / "runtime" / "native-benchmark.patch").read_bytes()).hexdigest()
            if not isinstance(digest, str):
                issue("runtime.native_patch: SHA256 unavailable", missing=True)
            elif actual != digest.lower():
                issue("runtime.native_patch: archived SHA256 mismatch")
            runtime_checks["native_patch"] = isinstance(digest, str) and actual == digest.lower()
        except OSError:
            runtime_checks["native_patch"] = False
            issue("runtime.native_patch: archived source patch unavailable", missing=True)

    client = read_object(directory / "client-metadata.json")
    for key, expected in {"backend": "codex", "requested_model": model, "reasoning_effort": effort,
                          "authentication": "ChatGPT"}.items():
        match(client.get(key), expected, f"client.{key}")
    if not isinstance(client.get("client_version"), str) or not client["client_version"].startswith("codex-cli "):
        issue("client.client_version: exact CLI version unavailable", missing=True)
    client_digest = client.get("binary_sha256")
    client_archive = directory / "runtime" / _basename(client.get("binary_path", ""))
    client_path = client_archive if client_archive.is_file() else Path(client.get("binary_path") or "")
    client_hash_verified = False
    try:
        client_hash_verified = hashlib.sha256(client_path.read_bytes()).hexdigest() == client_digest
        if not client_hash_verified:
            issue("client: binary identity SHA256 mismatch")
    except OSError:
        issue("client: CLI binary identity cannot be checked against archive or unchanged local binary", missing=True)

    paths = sorted(directory.glob("*.jsonl"))
    if len(paths) != 1:
        issue("Expected one trajectory file for the single-attempt trial.")
    records = []
    for path in paths:
        try:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("expected an object")
                    records.append(record)
                except ValueError:
                    issue(f"{path.name}:{line_number}: invalid record")
        except (OSError, UnicodeError) as error:
            issue(f"{path.name}: unreadable trajectory: {error}", missing=True)
    metadata = records[0].get("meta", {}) if records and records[0].get("kind") == "meta" else {}
    for key, expected in {"runner_version": version, "ruleset": version, "control_contract": "owned-player-crew-v1",
                          "economy_contract": "native-economy-and-fuel-recovery-v1", "backend": "codex", "model": model,
                          "reasoning_effort": effort}.items():
        match(metadata.get(key), expected, f"trajectory metadata.{key}")
    if version in {"v5", "v6", "v7"}:
        match(metadata.get("routing_contract"), "native-sector-neighbors-v1", "trajectory metadata.routing_contract")
    if version in {"v6", "v7"}:
        match(metadata.get("beacon_contract"), "native-beacon-readiness-v1", "trajectory metadata.beacon_contract")
    if version == "v7":
        match(metadata.get("hostility_contract"), "native-enemy-hostility-v1", "trajectory metadata.hostility_contract")
    definition = metadata.get("scenario") or {}
    for key, expected in {"seed": seed, "ship": "kestrel", "difficulty": "easy", "type": "full_run"}.items():
        match(definition.get(key), expected, f"recorded scenario.{key}")
    if isinstance(planned, list) and definition.get("id") not in planned:
        issue("Recorded scenario is not the planned scenario.")

    previous, final = {}, {}
    for index, record in enumerate(records):
        label = f"record {record.get('i', index)}"
        obs = record.get("obs")
        trace = record.get("model")
        if isinstance(trace, dict):
            model_requests += 1
            match(trace.get("provider"), "codex", label + " provider")
            match(trace.get("model"), model, label + " model")
            if not _number(trace.get("latency_seconds")) or trace["latency_seconds"] < 0:
                issue(label + ": request latency unavailable", missing=True)
        actions = record.get("actions") or []
        if trace and len(actions) > 12:
            issue(label + ": exceeds shared 12-action plan limit")
        if isinstance(obs, dict) and obs.get("game_started") is True:
            snapshots += 1
            final = obs
            caps = obs.get("capabilities") or {}
            for name in required_caps:
                match(caps.get(name), True, label + " capability." + name)
            if not _integer(caps.get("native_protocol")) or caps["native_protocol"] < 5:
                issue(label + ": protocol 5 unavailable")
            match(obs.get("seed"), seed, label + " seed")
            match(obs.get("difficulty"), 0, label + " difficulty")
            match((obs.get("player_ship") or {}).get("blueprint"), "PLAYER_SHIP_HARD", label + " blueprint")
            crew = (obs.get("player_ship") or {}).get("crew")
            if not isinstance(crew, list):
                issue(label + ": player crew unavailable", missing=True)
            else:
                for member in crew:
                    if member.get("player_owned") is not True or member.get("owner_ship_id") != 0:
                        issue(label + ": non-player crew serialized as player crew")
            components = obs.get("ftl_score_components") or {}
            terms = [components.get(key) for key in ("scrap_collected", "ships_destroyed", "beacons_explored")]
            if not all(_number(term) and term >= 0 for term in terms) or components.get("difficulty") not in (0, 1, 2):
                issue(label + ": native score components unavailable", missing=True)
            else:
                multiplier = {0: 1, 1: 1.25, 2: 1.5}[components["difficulty"]]
                expected = int((terms[0] + 20 * terms[1] + 10 * terms[2]) * multiplier)
                match(obs.get("ftl_score"), expected, label + " native score formula")
                match(obs.get("ftl_score_source"), "native_live_v1", label + " native score source")
                match(components.get("difficulty"), obs.get("difficulty"), label + " score difficulty")
                scores.append(obs.get("ftl_score"))
            economy = obs.get("economy") or {}
            if version in {"v5", "v6", "v7"}:
                match(economy.get("sector_navigation_version"), 1, label + " native sector navigation marker")
            if version in {"v6", "v7"}:
                match(economy.get("beacon_navigation_version"), 1, label + " native beacon navigation marker")
                navigation = economy.get("navigation") or {}
                for field in ("can_jump", "enemy_defeat_pending"):
                    if not isinstance(navigation.get(field), bool):
                        issue(label + f": native navigation.{field} unavailable", missing=True)
                current, maximum = navigation.get("drive_current"), navigation.get("drive_max")
                if not all(_number(value) and value >= 0 for value in (current, maximum)):
                    issue(label + ": native drive charge unavailable", missing=True)
                elif navigation.get("can_jump") is True and (maximum <= 0 or current < maximum):
                    issue(label + ": native can_jump contradicts partial/invalid drive charge")
            check_hostility(obs, label)
            if not _integer(economy.get("native_protocol")) or economy["native_protocol"] < 5:
                issue(label + ": native economy protocol unavailable", missing=True)
            recovery = economy.get("fuel_recovery") or {}
            if not all(isinstance(recovery.get(key), bool) for key in ("out_of_fuel", "distress_on", "can_wait", "waiting")):
                issue(label + ": native fuel recovery state unavailable", missing=True)
            event = obs.get("event") or {}
            if obs.get("choice_box_open"):
                for choice in event.get("choices") or []:
                    if not _integer(choice.get("native_type")):
                        issue(label + ": native event choice availability unavailable", missing=True)
                        continue
                    disabled = choice["native_type"] == 1
                    disabled_choices += int(disabled)
                    for key, expected in (("disabled", disabled), ("enabled", not disabled), ("available", not disabled)):
                        match(choice.get(key), expected, label + f" choice {choice.get('index')}.{key}")
                if not _number(event.get("open_time")) or not _integer(event.get("dialog_keys")):
                    issue(label + ": native event opening/hotkey state unavailable", missing=True)
                pending_choices += int(event.get("dialog_keys") == 2 and _number(event.get("open_time")) and event["open_time"] < 0.3)
        if record.get("kind") in {"step", "step_timeout"}:
            pre_obs = record.get("pre_obs")
            check_hostility(pre_obs, label + " pre-dispatch")
            check_hostility(record.get("decision_obs"), label + " model input")
            proven_pre = isinstance(pre_obs, dict)
            before = pre_obs if proven_pre else previous
            if trace and not isinstance(record.get("decision_obs"), dict):
                issue(label + ": actual model-input observation unavailable", missing=True)
            entries = ((obs or {}).get("action_feedback") or []) if isinstance(obs, dict) else []
            by_index = {item.get("action_index"): item for item in entries if isinstance(item, dict)}
            if len(by_index) != len(entries):
                issue(label + ": duplicate or malformed action feedback indices")
            upgrade_batch_proven = proven_pre and record.get("kind") == "step" and _check_distinct_upgrade_batch(
                actions, by_index, before, obs or {}, label, issue)
            prior_actions = []
            for action_index, action in enumerate(actions, 1):
                kind = action.get("type")
                if kind not in guarded:
                    prior_actions.append(kind)
                    continue
                counts = feedback_counts[kind]
                counts["requested"] += 1
                entry = by_index.get(action_index)
                if record.get("kind") == "step_timeout":
                    issue(label + f": {kind} acknowledgment timed out; retained feedback cannot prove dispatch", missing=True)
                    counts["unproven"] += 1
                elif not entry or entry.get("type") != kind:
                    issue(label + f": missing {kind} feedback at action index {action_index}", missing=True)
                    counts["unproven"] += 1
                elif entry.get("status") == "rejected":
                    counts["rejected"] += 1
                    if not isinstance(entry.get("reason"), str) or not entry["reason"]:
                        issue(label + f": {kind} rejection reason missing", missing=True)
                elif entry.get("status") == "applied":
                    counts["applied"] += 1
                    if not proven_pre:
                        issue(label + f": {kind} pre-dispatch observation unavailable; previous result may be stale during idle GUI updates", missing=True)
                    _check_applied(action, entry, before, obs or {}, prior_actions, label, issue,
                                   proven_pre=proven_pre, upgrade_batch_proven=upgrade_batch_proven)
                    if kind == "leave_sector" and proven_pre:
                        start_sector = (before.get("map") or {}).get("sector")
                        later = [row.get("obs") for row in records[index:] if isinstance(row.get("obs"), dict)
                                 and row["obs"].get("game_started") is True]
                        advanced = _integer(start_sector) and any(
                            _integer((state.get("map") or {}).get("sector"))
                            and state["map"]["sector"] > start_sector for state in later)
                        victory = start_sector == 7 and any(state.get("victory") is True for state in later)
                        if advanced or victory:
                            counts["transitions_confirmed"] = counts.get("transitions_confirmed", 0) + 1
                        else:
                            issue(label + ": accepted native sector route has no recorded sector advance or final victory", missing=True)
                    if kind == "jump" and proven_pre:
                        before_map, after_map = before.get("map") or {}, (obs or {}).get("map") or {}
                        moved = before_map.get("current_pos") is not None and after_map.get("current_pos") is not None and before_map["current_pos"] != after_map["current_pos"]
                        if moved:
                            counts["transitions_confirmed"] = counts.get("transitions_confirmed", 0) + 1
                        else:
                            issue(label + ": accepted native beacon jump has no recorded position transition", missing=True)
                else:
                    issue(label + f": invalid {kind} feedback status")
                for field in {"move_crew": ("crew_id", "room_id"), "choose_event": ("choice_index",),
                              "upgrade_system": ("system_id",), "set_distress": ("enabled",),
                              "jump": ("beacon_index",)}.get(kind, ()):
                    if entry:
                        match(entry.get(field), action.get(field), label + f" {kind} feedback.{field}")
                if kind in {"fire_weapon", "fire_beam"} and entry:
                    fields = ("target_room_id",) if kind == "fire_weapon" else ("room_a", "room_b")
                    for field in ("weapon_slot", "target_ship_id", *fields):
                        expected = action.get(field, 1) if field == "target_ship_id" else action.get(field)
                        match(entry.get(field), expected, label + f" {kind} feedback.{field}")
                prior_actions.append(kind)
        if isinstance(obs, dict):
            previous = obs

    terminal = records[-1] if records and records[-1].get("kind") == "end" else None
    if terminal is None:
        issue("Missing final terminal marker.", missing=True)
    else:
        match(terminal.get("setup_verified"), True, "terminal setup verification")
    if terminal and terminal.get("reason") == "win" and final.get("victory") is not True:
        issue("Win terminal reason has no confirmed native victory.")
    elif terminal and terminal.get("reason") == "game_over":
        player = final.get("player_ship") or {}
        hull = (player.get("hull") or {}).get("current")
        dead = _number(hull) and hull <= 0 or isinstance(player.get("crew"), list) and not any(is_living_player_crew(c) for c in player["crew"])
        if final.get("game_over") is not True and not dead:
            issue("Game-over terminal reason has no native terminal/death evidence.")
    if terminal and terminal.get("reason") == "gave_up" and not any(
        action.get("type") == "give_up" for row in records for action in row.get("actions") or []):
        issue("Concession terminal reason has no recorded give-up action.", missing=True)
    if not snapshots or not scores or not model_requests:
        issue("At least one native scored game snapshot and exact-model completion is required.", missing=True)
    report = None
    try:
        report = load_run_report(directory)
        if not report["coverage"]["complete"]:
            issue("Recorded finalized-file coverage is incomplete.", missing=True)
        for message in report["errors"]:
            issue(message)
        if report["instances"] and scores:
            match(report["instances"][0].get("ftl_score"), scores[-1], "replayed final native score")
    except (ValueError, OSError, KeyError, TypeError) as error:
        issue(f"Cannot recompute recorded report: {error}", missing=True)
    status = "invalid" if errors else "inconclusive" if gaps else "verified"
    return {"verifier": f"codex-{version}-recorded-evidence-v1", "validation_status": status,
            "valid_for_model_comparison": status == "verified", "record_integrity_checks_passed": not errors,
            "scope": "Recorded interface/provenance evidence, not model quality, remote model routing, or unexercised action families.",
            "runner_version": manifest.get("runner_version"), "ruleset": manifest.get("ruleset"),
            "control_contract": manifest.get("control_contract"), "economy_contract": manifest.get("economy_contract"),
            "routing_contract": manifest.get("routing_contract"),
            "beacon_contract": manifest.get("beacon_contract"),
            "hostility_contract": manifest.get("hostility_contract"),
            "model": model, "reasoning_effort": effort, "client_version": client.get("client_version"),
            "client_binary_hash_verified": client_hash_verified, "client_binary_source": "archive" if client_archive.is_file() else "unchanged_local_binary",
            "runtime_hash_matches": runtime_checks, "checked_snapshots": snapshots,
            "native_score_snapshots": len(scores), "first_score": scores[0] if scores else None,
            "last_score": scores[-1] if scores else None, "model_completions": model_requests,
            "usage_reporting": "CLI token/cost usage is unavailable; recorded latency does not establish token usage or price.",
            "action_feedback": feedback_counts, "unexercised_action_families": [key for key, value in feedback_counts.items() if not value["requested"]],
            "disabled_choices_observed": disabled_choices, "pending_event_snapshots": pending_choices,
            "final_state": {"game_over": final.get("game_over"), "victory": final.get("victory"),
                            "hull": (final.get("player_ship") or {}).get("hull"),
                            "crew_alive": sum(is_living_player_crew(member) for member in (final.get("player_ship") or {}).get("crew") or []),
                            "score_components": final.get("ftl_score_components"), "economy": final.get("economy")},
            "terminal_record": terminal, "report_complete": bool(report and report["coverage"]["complete"]),
            "limitations": gaps, "errors": errors}


def _check_distinct_upgrade_batch(actions, by_index, before, after, label, issue):
    """Reconcile distinct native purchases only when the complete ordered ledger is visible.

    Each price depends on that target's own capacity. Repeating a target needs its
    unrecorded intermediate next price; event/store/travel operations can alter the
    context or the resource ledger and cannot be reconstructed here.
    """
    upgrade_kinds = {"upgrade_system", "upgrade_reactor"}
    upgrades = [(index, action) for index, action in enumerate(actions, 1)
                if action.get("type") in upgrade_kinds]
    if len(upgrades) < 2:
        return False

    def uncertain(message):
        issue(label + ": upgrade batch " + message, missing=True)

    passive = {"set_system_power", "move_crew", "set_doors"}
    if any(action.get("type") not in upgrade_kinds | passive for action in actions):
        uncertain("contains a context/resource-changing or unsupported operation")
        return False
    keys = [("reactor",) if action["type"] == "upgrade_reactor" else ("system", action.get("system_id"))
            for _, action in upgrades]
    if len(set(keys)) != len(keys):
        uncertain("repeats an upgrade target; its intermediate native next price is unavailable")
        return False
    scrap = ((before.get("player_ship") or {}).get("resources") or {}).get("scrap")
    post_scrap = ((after.get("player_ship") or {}).get("resources") or {}).get("scrap")
    economy, post_economy = before.get("economy") or {}, after.get("economy") or {}
    if not _number(scrap) or not _number(post_scrap):
        uncertain("resource ledger is unavailable")
        return False
    proven = True
    for (index, action), key in zip(upgrades, keys):
        entry = by_index.get(index) or {}
        if (entry.get("type") != action["type"] or entry.get("status") not in {"applied", "rejected"}
                or action["type"] == "upgrade_system" and (
                    not _integer(action.get("system_id")) or entry.get("system_id") != action["system_id"])):
            uncertain("ordered purchase feedback is incomplete or mismatched")
            return False
        if key == ("reactor",):
            item, post_item = economy.get("reactor") or {}, post_economy.get("reactor") or {}
        else:
            item = next((item for item in economy.get("systems") or [] if item.get("system_id") == key[1]), {})
            post_item = next((item for item in post_economy.get("systems") or [] if item.get("system_id") == key[1]), {})
        current, final = item.get("current_max_power"), post_item.get("current_max_power")
        expected_delta = int(entry["status"] == "applied")
        if not _integer(current) or not _integer(final) or final != current + expected_delta:
            uncertain("capacity transitions do not isolate one level per accepted purchase")
            proven = False
        if entry["status"] == "rejected":
            continue
        cost = item.get("next_upgrade_cost")
        if not _integer(cost) or cost < 0:
            uncertain("native purchase price is unavailable")
            return False
        if scrap < cost:
            issue(label + ": unaffordable native upgrade reported applied after earlier purchases")
            proven = False
        scrap -= cost
        if economy.get("upgrade_available") is not True or item.get("can_upgrade") is not True:
            uncertain("initial native availability/permission was blocked or unknown")
            proven = False
    if scrap != post_scrap:
        uncertain("post-action scrap does not reconcile with recorded native purchase prices")
        proven = False
    return proven


def _check_applied(action, entry, before, after, prior_actions, label, issue, *, proven_pre=True, upgrade_batch_proven=False):
    kind = action["type"]
    def uncertain(message):
        issue(label + ": " + message, missing=True)
    def illegal(message):
        issue(label + ": " + message)
    # Feedback identity/selection and request argument types are independent of snapshot age.
    if kind == "choose_event" and entry.get("selected_choice") != action.get("choice_index"):
        illegal("event applied feedback does not confirm the requested native selection")
    if kind == "set_distress" and not isinstance(action.get("enabled"), bool):
        illegal("distress applied without an explicit boolean state")
    if kind == "jump" and (not _integer(action.get("beacon_index")) or action["beacon_index"] < 0):
        illegal("jump applied with an invalid native beacon index")
    if kind in {"fire_weapon", "fire_beam"}:
        if entry.get("queued") is False:
            illegal("fire reported applied without a queued native request")
        elif entry.get("queued") is not True:
            uncertain("native queued-fire acceptance proof unavailable")
        if action.get("target_ship_id", 1) == 1:
            for field in ("enemy_hostile", "enemy_targetable"):
                if entry.get(field) is False:
                    illegal(f"fire reported applied with dispatch {field}=false")
                elif entry.get(field) is not True:
                    uncertain(f"native dispatch {field} proof unavailable")
    if not proven_pre:
        # Legacy result snapshots are contextual only: native UI can advance with frame budget 0.
        # Never turn their ownership, popup, affordability, or waiting state into illegality proof.
        return
    if not before.get("game_started"):
        uncertain(f"{kind} has no in-game pre-action observation")
        return
    if kind in {"fire_weapon", "fire_beam"}:
        ship = action.get("target_ship_id", 1)
        if type(ship) is not int or ship not in (0, 1):
            illegal("fire applied with an unsupported native target ship")
        elif ship == 0:
            weapon = next((item for item in (before.get("player_ship") or {}).get("weapons") or []
                           if item.get("slot", item.get("index")) == action.get("weapon_slot")), None)
            if weapon is None or not isinstance(weapon.get("weapon_type"), str):
                uncertain("self-target weapon type unavailable")
            elif kind != "fire_weapon" or weapon["weapon_type"] != "BOMB":
                illegal("unsupported non-bomb self-target fire reported applied")
        elif entry.get("enemy_hostile") is not True or entry.get("enemy_targetable") is not True:
            enemy = before.get("enemy_ship")
            if "choose_event" in prior_actions:
                uncertain("enemy hostility may have changed within the paused plan")
            elif not isinstance(enemy, dict) or not isinstance(enemy.get("hostile"), bool):
                uncertain("enemy hostility unavailable before firing")
            elif enemy.get("hostile") is not True or enemy.get("targetable") is not True:
                uncertain("enemy targeting precontext blocked/unknown; dispatch-time eligibility was not recorded")
    elif kind == "jump":
        navigation = (before.get("economy") or {}).get("navigation") or {}
        current, maximum = navigation.get("drive_current"), navigation.get("drive_max")
        if any(kind in prior_actions for kind in ("jump", "choose_event", "leave_sector")):
            uncertain("beacon readiness/neighbor state changed within the paused plan")
        elif navigation.get("can_jump") is not True:
            uncertain("native beacon precontext was blocked/unknown; dispatch-time eligibility was not recorded")
        elif not _number(current) or not _number(maximum):
            uncertain("native drive readiness unavailable before jump")
        elif maximum <= 0 or current < maximum:
            illegal("native can_jump contradicts partial/invalid drive charge before jump")
        neighbors = (before.get("map") or {}).get("connected_beacons") or []
        if not any(item.get("index") == action.get("beacon_index") for item in neighbors):
            uncertain("requested beacon absent from recorded native neighbors")
    elif kind == "move_crew":
        member = next((item for item in (before.get("player_ship") or {}).get("crew") or [] if item.get("id") == action.get("crew_id")), None)
        eligible = (member and member.get("player_owned") is True and member.get("owner_ship_id") == 0
                    and member.get("current_ship_id") == 0 and member.get("controllable") is True
                    and is_living_player_crew(member))
        if member and any(member.get(key) is None for key in ("player_owned", "owner_ship_id", "current_ship_id", "controllable", "health_current")):
            uncertain("crew ownership/control/health evidence is incomplete")
        elif not eligible:
            if any(kind in prior_actions for kind in ("teleport_crew", "mind_control", "choose_event")):
                uncertain("crew eligibility changed within the paused plan")
            else:
                illegal("ineligible crew movement reported applied")
    elif kind == "choose_event":
        event = before.get("event") or {}
        choice = next((item for item in event.get("choices") or [] if item.get("index") == action.get("choice_index")), None)
        if "choose_event" in prior_actions:
            uncertain("multiple event selections prevent reconstructing each pre-action popup")
        elif choice is None:
            uncertain("event choice absent from pre-action popup")
        elif choice.get("native_type") == 1 or choice.get("disabled") is True or choice.get("available") is False:
            illegal("disabled event choice reported applied")
        elif not _integer(choice.get("native_type")):
            uncertain("native event choice type unavailable")
        if event.get("dialog_keys") == 0:
            illegal("event selection reported applied with hotkeys disabled")
        elif event.get("dialog_keys") == 2 and _number(event.get("open_time")) and event["open_time"] < 0.3:
            uncertain("event opening delay was pending in the snapshot; dispatch-time UI timer was not recorded")
        elif not _integer(event.get("dialog_keys")) or not _number(event.get("open_time")):
            uncertain("event dispatch timing cannot be checked")
    elif kind in {"upgrade_system", "upgrade_reactor"}:
        economy = before.get("economy") or {}
        if kind == "upgrade_reactor":
            item = economy.get("reactor") or {}
        else:
            item = next((item for item in economy.get("systems") or [] if item.get("system_id") == action.get("system_id")), {})
        cost = item.get("next_upgrade_cost")
        scrap = ((before.get("player_ship") or {}).get("resources") or {}).get("scrap")
        if not upgrade_batch_proven and any(kind in prior_actions for kind in ("upgrade_system", "upgrade_reactor", "store_buy", "store_sell", "choose_event")):
            uncertain("upgrade legal/price state changed within the paused plan")
        elif not _integer(cost) or cost < 0 or not _number(scrap):
            uncertain("native upgrade price/affordability unavailable")
        elif scrap < cost:
            illegal("unaffordable native upgrade reported applied")
        elif (_integer(item.get("max_level")) and _integer(item.get("current_max_power"))
              and item["current_max_power"] >= item["max_level"]):
            illegal("capped native upgrade reported applied")
        elif economy.get("upgrade_available") is not True or item.get("can_upgrade") is not True:
            uncertain("native upgrade precontext was blocked/unknown; dispatch-time GUI legality was not recorded")
        next_economy = after.get("economy") or {}
        next_item = (next_economy.get("reactor") or {}) if kind == "upgrade_reactor" else next(
            (item for item in next_economy.get("systems") or [] if item.get("system_id") == action.get("system_id")), {})
        if not _integer(item.get("current_max_power")) or not _integer(next_item.get("current_max_power")):
            uncertain("applied upgrade level transition unavailable")
        elif next_item["current_max_power"] <= item["current_max_power"]:
            illegal("applied native upgrade has no recorded level increase")
    elif kind in {"wait_for_fuel", "set_distress"}:
        recovery = (before.get("economy") or {}).get("fuel_recovery") or {}
        legal = recovery.get("out_of_fuel") is True and recovery.get("can_wait") is True and recovery.get("waiting") is False
        if any(recovery.get(key) is None for key in ("out_of_fuel", "can_wait", "waiting")):
            uncertain("native fuel recovery legality evidence is incomplete")
        elif not legal:
            if any(kind in prior_actions for kind in ("wait_for_fuel", "set_distress", "choose_event")):
                uncertain("fuel recovery context changed within the paused plan")
            else:
                uncertain("native fuel precontext was blocked; dispatch-time GUI legality was not recorded")
    elif kind == "leave_sector":
        route = before.get("map") or {}
        fuel = ((before.get("player_ship") or {}).get("resources") or {}).get("fuel")
        enemy = before.get("enemy_ship")
        no_live_enemy = enemy is None or isinstance(enemy, dict) and (
            enemy.get("destroyed") is True or enemy.get("hostile") is False)
        if route.get("at_exit") is not True or not _number(fuel) or fuel <= 0 or not no_live_enemy:
            uncertain("native sector route precontext was blocked/unknown; dispatch-time eligibility was not recorded")
