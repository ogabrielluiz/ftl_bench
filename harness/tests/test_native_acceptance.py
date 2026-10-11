"""File-only adversarial checks: no game, model, compiler or runtime reads."""
import json
import copy
import re
import importlib.util
import struct
import zlib

import pytest

from ftl_bench import native_acceptance as a
from ftl_bench.cli import _bench_root
from test_fullgame_setup import immediate, packets, good_receipt


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def put(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else encoded(data))
    return {"path": name, "sha256": a.digest(path.read_bytes())}


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def png():
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1280, 720, 8, 2, 0, 0, 0)) + chunk(
        b"IDAT", zlib.compress((b"\0" + b"\0" * (1280 * 3)) * 720)) + chunk(b"IEND", b"")


def visual(raw):
    raw["visual"].update(width=1280, height=720, coordinate_space="client", external_input_generation="0",
        external_input_detected=False, requested_frames=0, actual_frames=0, input_feedback=[], paused=True, visual_io_version=1)
    raw["capabilities"]["external_input_guard"] = True
    ref = dict(raw["visual"])
    for name in ("external_input_detected", "requested_frames", "actual_frames", "input_feedback"):
        ref.pop(name)
    ref.update(sha256=a.digest(png()), path="screens/frame.png")
    return ref


def cleanup(root, hashes, save_count=1):
    originals = {f"original{i}.sav": a.digest(f"save{i}".encode()) for i in range(save_count)}
    backups = {name: put(root, "backup/" + name, f"save{i}".encode()) for i, name in enumerate(originals)}
    hashes = {**hashes, **{"save/" + n: h for n, h in originals.items()}, "save/ftl_bench_dev.lua": None}
    ids = {"absolute-label/" + n: n for n in hashes}
    raw_map = {k: hashes[v] for k, v in ids.items()}
    before = put(root, "before.json", {"files_sha256": raw_map})
    after = put(root, "after.json", {"files_sha256": raw_map, "processes": [], "no_game_process": True,
        "checked_at": "2026-10-11T01:00:01Z"})
    manifest = put(root, "backup/manifest.json", {"files": originals})
    restored = put(root, "backup/restoration.json", {"verified": True, "files": {n: True for n in originals},
        "restored_at": "2026-10-11T01:00:00Z"})
    return put(root, "cleanup.json", {"contract": "portable-cleanup-attestation-v1",
        "before": hashes, "after": hashes, "inventory_ids": ids, "raw_inventory_refs": {"before": before, "after": after},
        "backups": backups, "backup_manifest": manifest, "restoration": restored, "processes": [],
        "checked_at": "2026-10-11T01:00:02Z"})


@pytest.fixture
def evidence(tmp_path):
    source = _bench_root()
    if not (source / "harness/src/ftl_bench/native_acceptance.py").is_file():
        pytest.skip("Checkout-bound evidence proofs require harness/src sources; bundled package roots deliberately refuse native acceptance")
    files = a.source_identity(source)
    refs = {name: put(tmp_path, "sources/" + name, (source / name).read_bytes()) for name in files}
    snapshot = put(tmp_path, "source-snapshot.json", {"source_files": files, "archived_files": refs})
    manifest = json.loads((source / "native/manifest.json").read_text())
    dll_bytes = b"synthetic artifact; not executable"
    dll = put(tmp_path, "native/game.dll", dll_bytes)
    prov = {**a.CAPABILITIES, "repository": manifest["repository"], "source_commit": manifest["base_commit"],
        "patch_sha256": manifest["patch_sha256"], "dll_sha256": dll["sha256"], "dll_size": len(dll_bytes),
        "platform": "windows-x86", "game_version": "1.6.9",
        "source_files_sha256": {p.name: a.digest(p.read_bytes()) for p in (source / "native/include").glob("*")}}
    for name in re.findall(r"^diff --git a/(\S+) b/\1$", (source / manifest["patch"]).read_text(), re.MULTILINE):
        prov["source_files_sha256"].setdefault(name, "b" * 64)
    provenance = put(tmp_path, "native/provenance.json", prov)
    bridge = put(tmp_path, "bridge.lua", (source / a.BRIDGE).read_bytes())
    raw = immediate(1)
    raw.update(paused=True, visual_evaluator={"choice_window_open": True})
    ref = visual(raw)
    image = put(tmp_path, "startup/screens/frame.png", png())
    meta = {"provider": "none", "model": None, "seed": 1, "source_files_sha256": a.source_digest(files)}
    rows = [{"kind": "meta", "i": -1, "meta": meta},
        {"kind": "reset", "i": 0, "actions": [], "obs": raw, "visual": {"before": ref, "after": ref}},
        {"kind": "end", "i": 1, "status": "completed", "reason": "decision_budget", "decisions": 0}]
    trajectory = put(tmp_path, "startup/trajectory.jsonl", b"\n".join(encoded(r) for r in rows))
    runtime = put(tmp_path, "startup/runtime.json", {"native_dll": {"sha256": dll["sha256"]},
        "bridge_lua": {"sha256": bridge["sha256"]}, "native_build": {**prov, "matches_installed_dll": True}})
    session = put(tmp_path, "startup/session.json", {"packets": packets(1)})
    admission = put(tmp_path, "startup/admission.json", {"first_observation": raw, "first_image": ref, "passed": False})
    hashes = {"runtime/" + n: "a" * 64 for n in ("FTLGame.exe", "ftl.dat", "xinput1_4.dll", "lua-5.3.dll")}
    hashes.update({"runtime/Hyperspace.dll": dll["sha256"], "runtime/ftlbench-native.json": provenance["sha256"],
        "source/ftl_bench_dev.lua": bridge["sha256"]})
    spec = {"contract": a.CONTRACT, "source_snapshot": snapshot, "native": {"dll": dll, "provenance": provenance},
        "bridge": bridge, "startup": {"trajectory": trajectory, "runtime": runtime, "session": session, "admission": admission,
        "cleanup": cleanup(tmp_path, hashes), "images": {image["sha256"]: image}}}
    rewrite(tmp_path, spec["startup"]["cleanup"], lambda d: d.update(trajectory=trajectory, session=session))
    return tmp_path, source, spec


def verify(evidence):
    root, source, spec = evidence
    return a.validate(spec, source_root=source, evidence_root=root)


def rewrite(root, ref, mutate):
    document = a.read_json((root / ref["path"]).read_bytes())
    mutate(document)
    ref.update(put(root, ref["path"], document))


def rows(evidence, mutate):
    root, _, spec = evidence
    ref = spec["startup"]["trajectory"]
    records = [a.read_json(line) for line in (root / ref["path"]).read_bytes().splitlines()]
    mutate(records)
    ref.update(put(root, ref["path"], b"\n".join(encoded(r) for r in records)))


def test_startup_scoped_validation_never_promotes_missing_nine_probes(evidence):
    report = verify(evidence)
    assert report["status"] == "pending", report
    assert report["checks"]["fixture_free_startup"] == "validated_scoped"
    assert report["checks"]["native_build_identity"] == "validated_scoped"
    assert report["controller_admission"] is report["production_accepted"] is False
    assert report["errors"] == []
    assert any("exactly nine" in x for x in report["missing_requirements"])
    assert report["checks"]["common_runtime_identity"] == "pending"


@pytest.mark.parametrize("mutation", [None, "changed_asset", "absent_inventory", "missing_raw_inventory"])
def test_common_runtime_joins_individually_valid_cleanup_inventories(evidence, monkeypatch, mutation):
    root, _, spec = evidence
    startup_cleanup = a.read_json((root / spec["startup"]["cleanup"]["path"]).read_bytes())
    probes = []
    for challenge in a.CHALLENGES:
        for repetition, delay in enumerate(a.DELAYS, 1):
            name = f"trials/{challenge}-{repetition}"
            trial_root = root / name
            trial_root.mkdir(parents=True)
            hashes = {k: v for k, v in startup_cleanup["before"].items() if not k.startswith("save/")}
            if mutation == "changed_asset" and not probes:
                hashes["runtime/FTLGame.exe"] = "f" * 64
            if mutation == "absent_inventory" and not probes:
                hashes.pop("runtime/ftl.dat")
            ref = cleanup(trial_root, hashes)
            # Make every nested reference portable to the common evidence root.
            document = a.read_json((trial_root / ref["path"]).read_bytes())
            for nested in [*document["raw_inventory_refs"].values(), *document["backups"].values(),
                           document["backup_manifest"], document["restoration"]]:
                nested["path"] = name + "/" + nested["path"]
            document.update(trajectory=spec["startup"]["trajectory"], session=spec["startup"]["session"])
            if mutation == "missing_raw_inventory" and not probes:
                document["raw_inventory_refs"].pop("after")
            ref = put(root, name + "/cleanup.json", document)
            probes.append({"challenge": challenge, "repetition": repetition, "delay_seconds": delay,
                "cleanup": ref, "trajectory": document["trajectory"], "session": document["session"]})
    spec["probes"] = probes
    # The measured behavior verifier is tested separately; exercise real raw cleanup joins here.
    monkeypatch.setattr(a, "_drivers", lambda: (None, None))
    monkeypatch.setattr(a, "_probe", lambda reader, trial, dll, bridge, challenges, timing, sources, provenance:
        {"states": [], "cleanup": a._cleanup(reader, trial, dll, a.digest(bridge), provenance)})
    report = verify(evidence)
    assert report["production_accepted"] is report["controller_admission"] is False
    if mutation == "changed_asset":
        assert report["checks"]["nine_probe_repeatability"] == "validated_scoped"
        assert report["checks"]["common_runtime_identity"] == "invalid"
        assert report["status"] == "invalid"
        assert "runtime_files" not in report
    elif mutation in {"absent_inventory", "missing_raw_inventory"}:
        assert report["checks"]["common_runtime_identity"] == "pending"
        assert report["status"] == "pending", report
        assert "runtime_files" not in report
    else:
        assert report["checks"]["common_runtime_identity"] == "validated_scoped", report
        assert report["status"] == "validated_scoped", report
        assert report["runtime_files"] == {n: startup_cleanup["before"]["runtime/" + n] for n in a.RUNTIME_FILES}
        assert report["native_identity"]["runtime_files"] == report["runtime_files"]


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "a\\b", "a/../b", "a//b", "./file", "file:ads"])
def test_unsafe_references_fail_closed(tmp_path, name):
    with pytest.raises(a.EvidenceError):
        a.Reader(tmp_path).bytes({"path": name, "sha256": "a" * 64}, "unsafe")


def test_hash_mismatch_is_invalid_not_pending(evidence):
    root, _, spec = evidence
    (root / spec["bridge"]["path"]).write_bytes(b"changed Lua")
    assert verify(evidence)["status"] == "invalid"


def test_old_bridge_cannot_inherit_same_dll_acceptance(evidence):
    root, _, spec = evidence
    spec["bridge"] = put(root, "old.lua", b"historical bridge")
    result = verify(evidence)
    assert result["status"] == "invalid"
    assert result["checks"]["prospective_bridge_identity"] == "invalid"


@pytest.mark.parametrize("field,value", [("native_protocol", True), ("fresh_seed_contract_version", 2),
    ("dll_size", True), ("patch_sha256", "f" * 64), ("dll_sha256", "f" * 64), ("source_commit", "old")])
def test_native_identity_mutations(evidence, field, value):
    root, _, spec = evidence
    rewrite(root, spec["native"]["provenance"], lambda d: d.update({field: value}))
    assert verify(evidence)["status"] == "invalid"


def test_archived_sources_must_cover_exact_inventory(evidence):
    root, _, spec = evidence
    rewrite(root, spec["source_snapshot"], lambda d: d["archived_files"].pop(a.BRIDGE))
    assert verify(evidence)["status"] == "invalid"


@pytest.mark.parametrize("mutation", ["source", "actor", "image", "terminal", "unknown", "decisions"])
def test_raw_startup_contradiction_rejects_claimed_success(evidence, mutation):
    def change(r):
        if mutation == "source":
            r[0]["meta"]["source_files_sha256"] = "0" * 64
        elif mutation == "actor":
            r[1]["model"] = {"response": "called"}
        elif mutation == "image":
            r[1]["visual"]["after"]["capture_id"] = "stale"
        elif mutation == "terminal":
            r.pop()
        elif mutation == "decisions":
            r[-1]["decisions"] = 1
        else:
            r.insert(2, {"kind": "fixture_setup", "i": 1, "actions": [{"type": "key"}]})
            r[-1]["i"] = 2
    rows(evidence, change)
    assert verify(evidence)["status"] == "invalid"


def test_absent_source_join_is_pending_with_producer_guidance(evidence):
    rows(evidence, lambda r: r[0]["meta"].pop("source_files_sha256"))
    result = verify(evidence)
    assert result["status"] == "pending"
    assert any("before launch" in x for x in result["missing_requirements"])


def test_summary_booleans_cannot_supply_cleanup(evidence):
    root, _, spec = evidence
    spec["startup"]["cleanup"] = put(root, "legacy.json", {"passed": True, "checks": {"all": True}})
    result = verify(evidence)
    assert result["status"] == "pending"
    assert any("legacy passed booleans" in x for x in result["missing_requirements"])


@pytest.mark.parametrize("mutation", ["inventory", "process", "time", "extra_save", "null", "runtime"])
def test_cleanup_byte_inventory_and_runtime_joins(evidence, mutation):
    root, _, spec = evidence
    def change(d):
        if mutation == "inventory":
            d["after"]["save/original0.sav"] = "f" * 64
        elif mutation == "process":
            d["processes"] = [123]
        elif mutation == "time":
            d["checked_at"] = "2020-01-01T00:00:00Z"
        elif mutation == "extra_save":
            d["before"]["save/extra.sav"] = d["after"]["save/extra.sav"] = "a" * 64
        elif mutation == "null":
            d["before"]["save/original0.sav"] = d["after"]["save/original0.sav"] = None
        else:
            d["before"]["runtime/Hyperspace.dll"] = d["after"]["runtime/Hyperspace.dll"] = "f" * 64
    rewrite(root, spec["startup"]["cleanup"], change)
    assert verify(evidence)["status"] == "invalid"


@pytest.mark.parametrize("count", [0, 1, 3, 8])
def test_save_inventory_is_exact_and_machine_independent(evidence, count):
    root, _, spec = evidence
    document = a.read_json((root / spec["startup"]["cleanup"]["path"]).read_bytes())
    hashes = {k: v for k, v in document["before"].items() if not k.startswith("save/")}
    spec["startup"]["cleanup"] = cleanup(root, hashes, count)
    rewrite(root, spec["startup"]["cleanup"], lambda d: d.update(
        trajectory=spec["startup"]["trajectory"], session=spec["startup"]["session"]))
    assert verify(evidence)["checks"]["fixture_free_startup"] == "validated_scoped"


def test_no_pixel_png_rejected():
    header = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1280, 720, 8, 2, 0, 0, 0))
    with pytest.raises(a.EvidenceError, match="full image"):
        a._png(header + chunk(b"IEND", b""))


def test_mid_validation_changes_detected(tmp_path):
    ref = put(tmp_path, "input.json", {})
    reader = a.Reader(tmp_path)
    reader.json(ref, "input")
    (tmp_path / ref["path"]).write_text("changed")
    assert not reader.unchanged()


def test_report_creation_preserves_prior_bytes(tmp_path):
    output = tmp_path / "receipt.json"
    a.write_report(output, {"status": "pending"})
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        a.write_report(output, {"status": "passed"})
    assert output.read_bytes() == original


def test_duplicate_json_keys_and_nonfinite_values_rejected():
    for data in (b'{"passed":false,"passed":true}', b'{"x":NaN}', b'{"x":Infinity}'):
        with pytest.raises(a.EvidenceError):
            a.read_json(data)


def probe_raw(challenge):
    raw = good_receipt()
    raw.update(seed=1, difficulty=0, game_started=True, game_over=False, paused=True,
        choice_box_open=False, visual_evaluator={"store_open": False},
        map={"current_pos": {"x": 88, "y": 152}, "hazard": "none"},
        economy={"navigation": {"drive_current": 0, "drive_max": 1, "can_jump": False}},
        player_ship={"blueprint": "PLAYER_SHIP_HARD", "hull": {"current": 30}, "oxygen_pct": 100,
            "crew": [{"id": i, "player_owned": True, "dead": False, "health_current": 100, "health_max": 100} for i in range(3)],
            "systems": [{"id": 1, "needs_repair": False, "room_id": 1}, {"id": 2, "power": 1, "needs_repair": False, "room_id": 2}],
            "rooms": [{"room_id": 1, "fires": 0, "oxygen": 100}, {"room_id": 2, "fires": 0, "oxygen": 100}]},
        visual_challenge_system_health=[{"system_id": i, "health_current": 2, "health_max": 2, "damaged_bars": 0} for i in (1, 2)])
    fixture = raw["visual_challenge_fixture"]
    fixture.update(applied=True, applied_before_first_capture=True, admission_action_seq=4, challenge=challenge,
        initial_drive_reset_requested=True, enemy_weapon_charge_reset_requested=True,
        engine_health_before=2, engine_health_max_before=2, injured_crew_id=0, fire_room=2)
    if challenge == "combat":
        raw["enemy_ship"] = {"hostile": True, "destroyed": False, "weapons": [{"slot": 0, "charge": 0, "charge_max": 10}]}
    elif challenge == "fire-crew-recovery":
        raw["player_ship"]["crew"][0]["health_current"] = 50
        raw["player_ship"]["rooms"][1]["fires"] = 1
    else:
        raw["player_ship"]["systems"][0]["needs_repair"] = True
        raw["visual_challenge_system_health"][0].update(health_current=1, damaged_bars=1)
    return raw


def captured(raw, seq, counter, frames=0, actions=()):
    raw["visual"].update(action_seq=seq, frame_id=f"frame-{seq}", capture_id=f"capture-{seq}",
        world_updates=str(counter), simulated_updates=str(counter), visual_clock_version=2,
        fixed_step_numerator=1, fixed_step_denominator=60)
    raw["last_action_seq"] = seq
    raw.setdefault("capabilities", {}).update(world_updates=str(counter), simulated_updates=str(counter),
        visual_clock_version=2, fixed_step_numerator=1, fixed_step_denominator=60)
    ref = visual(raw)
    raw["visual"].update(requested_frames=frames, actual_frames=frames,
        input_feedback=[{"index": i, "type": x["type"], "status": "delivered", "reason": "native"}
                        for i, x in enumerate(actions)])
    return ref


def add_nine(evidence):
    root, source, spec = evidence
    challenges, timing = a._drivers()
    source_sha = a.source_digest(a.source_identity(source))
    shared_image = put(root, "probe-image.png", png())
    cleanup_ref = spec["startup"]["cleanup"]
    result = []
    for challenge in a.CHALLENGES:
        for repetition, delay in enumerate(a.DELAYS, 1):
            prefix = f"{challenge}/{repetition}"
            raw = probe_raw(challenge)
            image = captured(raw, 4, 90)
            run_id = f"{challenge}-{repetition}"
            production = (source / a.BRIDGE).read_bytes()
            fixture_sha = a.digest(challenges.fixture_bridge(production, challenge, run_id))
            meta = {"provider": "none", "model": None, "seed": 1, "challenge": challenge, "repetition": repetition,
                "fixture_version": 6, "run_id": run_id, "source_files_sha256": source_sha, "probe_delay_seconds": delay,
                "production_bridge_sha256": a.digest(production), "fixture_bridge_sha256": fixture_sha,
                "script_sha256": a.digest((source / "scripts/validate_visual_challenges.py").read_bytes()),
                "setup_helper_sha256": a.digest((source / "harness/src/ftl_bench/challenge_setup.py").read_bytes()),
                "timing_driver_sha256": a.digest((source / "scripts/validate_visual_timing.py").read_bytes())}
            records = [{"kind": "meta", "i": -1, "meta": meta},
                {"kind": "reset", "i": 0, "actions": [], "obs": copy.deepcopy(raw), "t": 0,
                 "visual": {"before": image, "after": image}}]
            admission = put(root, prefix + "/admission.json", {"first_observation": copy.deepcopy(raw), "first_image": image})
            archived_packets = [{"packet": p} for p in [
                {"seq": 1, "advance_frames": 0, "actions": [{"type": "start_game", "mode": "new", "seed": 1}],
                 "benchmark_setup": {"version": 1, "fresh": True, "seed": 1}},
                {"seq": 2, "advance_frames": 30, "actions": []}, {"seq": 3, "advance_frames": 60, "actions": []},
                {"seq": 4, "advance_frames": 0, "actions": [], "observation_mode": "visual-v1"}]]
            seq, counter, now = 4, 90, 0
            for label, actions, frames in timing.probe_cases(challenge):
                for idle, packet, budget in ((True, [], 0), (False, list(actions), frames)):
                    previous = copy.deepcopy(raw)
                    old_image = image
                    seq += 1
                    counter += budget
                    now += delay + .1 if idle else .1
                    if not idle:
                        if challenge == "combat" and budget:
                            raw["player_ship"]["hull"]["current"] = 29
                        if challenge == "fire-crew-recovery" and budget:
                            raw["player_ship"]["rooms"][1]["oxygen"] -= 1
                        if challenge == "repair-charge-escape":
                            if label == "oxygen-off-zero":
                                raw["player_ship"]["systems"][1]["power"] = 0
                            if label == "oxygen-on-zero":
                                raw["player_ship"]["systems"][1]["power"] = 1
                            if budget:
                                raw["player_ship"]["oxygen_pct"] -= 1
                    image = captured(raw, seq, counter, budget, packet)
                    archived_packets.append({"packet": {"seq": seq, "actions": packet, "advance_frames": budget,
                        "observation_mode": "visual-v1", "expected_capture_id": old_image["capture_id"],
                        "expected_external_input_generation": old_image["external_input_generation"]}})
                    records.append({"kind": "step", "i": len(records) - 1, "actions": packet,
                        "thought": label + "-idle-capture" if idle else label, "pre_obs": previous,
                        "obs": copy.deepcopy(raw), "t": now, "visual": {"before": old_image, "after": image,
                            "inputs": [{**x, "delivery": "delivered", "reason": "native"} for x in packet],
                            "advance": {"requested_frames": budget, "actual_frames": budget}}})
            records.append({"kind": "end", "i": len(records) - 1, "status": "completed"})
            runtime = a.read_json((root / spec["startup"]["runtime"]["path"]).read_bytes())
            runtime["bridge_lua"]["sha256"] = fixture_sha
            result.append({"challenge": challenge, "repetition": repetition, "delay_seconds": delay,
                "trajectory": put(root, prefix + "/trajectory.jsonl", b"\n".join(encoded(r) for r in records)),
                "session": put(root, prefix + "/session.json", {"packets": archived_packets}),
                "runtime": put(root, prefix + "/runtime.json", runtime), "cleanup": cleanup_ref,
                "admission": admission,
                "images": {shared_image["sha256"]: shared_image},
                "timing_script": put(root, "timing.py", (source / "scripts/validate_visual_timing.py").read_bytes())})
            cleanup_doc = a.read_json((root / cleanup_ref["path"]).read_bytes())
            cleanup_doc.update(trajectory=result[-1]["trajectory"], session=result[-1]["session"])
            result[-1]["cleanup"] = put(root, prefix + "/cleanup.json", cleanup_doc)
    spec["probes"] = result
    return spec


def test_end_to_end_nine_probes_rederive_raw_data_and_never_promote(evidence):
    add_nine(evidence)
    result = verify(evidence)
    assert result["status"] == "validated_scoped", result
    assert result["repeatability"]["trials"] == 9
    assert result["production_accepted"] is result["controller_admission"] is False


@pytest.mark.parametrize("mutation", ["delivery", "packet_coords", "packet_budget", "stale", "requested", "unknown", "source", "divergence"])
def test_nine_probe_adversarial_raw_mutations(evidence, mutation):
    root, _, spec = evidence
    add_nine(evidence)
    trial = spec["probes"][0]
    if mutation.startswith("packet"):
        def change(d):
            p = d["packets"][5]["packet"]
            if mutation == "packet_coords":
                p["actions"][0]["x"] = 500
            else:
                p["advance_frames"] = 1
        rewrite(root, trial["session"], change)
    else:
        ref = trial["trajectory"]
        r = [a.read_json(line) for line in (root / ref["path"]).read_bytes().splitlines()]
        if mutation == "delivery":
            r[3]["visual"]["inputs"][0]["reason"] = "invented"
        elif mutation == "requested":
            r[3]["obs"]["visual"]["requested_frames"] = 1
        elif mutation == "stale":
            r[2]["obs"]["visual"]["capture_id"] = r[1]["obs"]["visual"]["capture_id"]
        elif mutation == "unknown":
            r[2]["kind"] = "fixture_setup"
        elif mutation == "source":
            r[0]["meta"]["source_files_sha256"] = "f" * 64
        else:
            r[-2]["obs"]["player_ship"]["hull"]["current"] = 28
        ref.update(put(root, ref["path"], b"\n".join(encoded(row) for row in r)))
    rewrite(root, trial["cleanup"], lambda d: d.update(trajectory=trial["trajectory"], session=trial["session"]))
    result = verify(evidence)
    assert result["status"] == "invalid"
    if mutation == "divergence":
        assert any("trajectories diverged" in error for error in result["errors"])


def test_missing_patched_source_hash_rejected(evidence):
    root, _, spec = evidence
    rewrite(root, spec["native"]["provenance"], lambda p: p["source_files_sha256"].pop("StatBoost.cpp"))
    assert verify(evidence)["checks"]["native_build_identity"] == "invalid"


def test_missing_checkout_not_silently_treated_as_wheel_acceptance(tmp_path):
    with pytest.raises(a.MissingEvidence, match="source checkout"):
        a.source_identity(tmp_path)


def test_actual_package_root_is_rejected_outside_checkout_bound_fixture():
    root = _bench_root()
    if (root / "harness/src/ftl_bench/native_acceptance.py").is_file():
        assert "harness/src/ftl_bench/native_acceptance.py" in a.source_identity(root)
    else:
        with pytest.raises(a.MissingEvidence, match="source checkout"):
            a.source_identity(root)


def test_raw_after_inventory_cannot_predate_restoration(evidence):
    root, _, spec = evidence
    cleanup_ref = spec["startup"]["cleanup"]
    document = a.read_json((root / cleanup_ref["path"]).read_bytes())
    rewrite(root, document["raw_inventory_refs"]["after"],
        lambda d: d.update(checked_at="2026-10-11T00:00:00Z"))
    cleanup_ref.update(put(root, cleanup_ref["path"], document))
    assert verify(evidence)["status"] == "invalid"


@pytest.mark.parametrize("changed", [False, True])
def test_reconstructed_complete_source_map_must_match_provenance(evidence, monkeypatch, changed):
    from ftl_bench import native_build_origin
    root, source, spec = evidence
    proof = {"contract": native_build_origin.CONTRACT, "objects": {}}
    spec["native"]["source_reconstruction"] = put(root, "native/source-proof.json", proof)
    provenance = a.read_json((root / spec["native"]["provenance"]["path"]).read_bytes())
    reconstructed = dict(provenance["source_files_sha256"])
    if changed:
        reconstructed["Benchmark_Extend.cpp"] = "f" * 64
    def derive(*, manifest, patch, proof: dict, reader):
        assert proof == {"contract": native_build_origin.CONTRACT, "objects": {}}
        assert a.digest(patch) == manifest["patch_sha256"]
        assert reader.root == root
        return {"source_files_sha256": reconstructed, "base_commit": manifest["base_commit"],
                "patch_sha256": a.digest(patch)}
    # Object authentication and patch semantics have separate real-byte tests.
    monkeypatch.setattr(native_build_origin, "reconstruct_sources", derive)
    report = verify(evidence)
    assert report["controller_admission"] is False
    if changed:
        assert report["checks"]["native_build_identity"] == "invalid"
        assert any("Reconstructed native source bytes" in error for error in report["errors"])
    else:
        assert report["native_identity"]["source_reconstruction"]["source_files_sha256"] == reconstructed
        assert spec["native"]["source_reconstruction"]["path"] in report["evidence_files"]


def assembly_module():
    spec = importlib.util.spec_from_file_location("_test_acceptance_cli", _bench_root() / "scripts/validate_native_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help_import_remains_available_in_bundle(capsys):
    with pytest.raises(SystemExit) as result:
        assembly_module().main(["--help"])
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert "--assemble-spec" in output and "--evidence-root" in output


def test_assembly_and_verification_pin_real_descriptor_joins(evidence):
    root, source, spec = evidence
    add_nine(evidence)
    first = put(root, "startup-evidence.json", {"contract": "visual-startup-evidence-v1",
        "source_snapshot": spec["source_snapshot"], "startup": spec["startup"]})
    second = put(root, "timing-evidence.json", {"contract": "visual-timing-evidence-v1",
        "source_snapshot": spec["source_snapshot"], "probes": spec["probes"]})
    assembled = assembly_module().assemble(evidence_root=root, startup_evidence=root / first["path"],
        timing_evidence=root / second["path"], dll=root / spec["native"]["dll"]["path"],
        provenance=root / spec["native"]["provenance"]["path"], bridge=root / spec["bridge"]["path"])
    assert a.validate(assembled, source_root=source, evidence_root=root)["status"] == "validated_scoped"
    proof = put(root, "source-reconstruction.json", {"contract": "native-source-reconstruction-v1", "objects": {}})
    with_proof = assembly_module().assemble(evidence_root=root, startup_evidence=root / first["path"],
        timing_evidence=root / second["path"], dll=root / spec["native"]["dll"]["path"],
        provenance=root / spec["native"]["provenance"]["path"], bridge=root / spec["bridge"]["path"],
        source_evidence=root / proof["path"])
    assert with_proof["native"]["source_reconstruction"] == proof
    assert a.validate(with_proof, source_root=source, evidence_root=root)["checks"]["native_build_identity"] == "pending"
    assembled["startup"] = copy.deepcopy(assembled["startup"])
    assembled["startup"]["images"] = {}
    result = a.validate(assembled, source_root=source, evidence_root=root)
    assert result["status"] == "invalid"
    assert result["checks"]["producer_descriptor_joins"] == "invalid"


def test_assembly_refuses_changed_source_snapshots(evidence):
    root, _, spec = evidence
    first = put(root, "startup-evidence.json", {"source_snapshot": spec["source_snapshot"], "startup": spec["startup"]})
    changed = put(root, "different-snapshot.json", {"source_files": {"changed": "f" * 64}})
    second = put(root, "timing-evidence.json", {"source_snapshot": changed, "probes": []})
    with pytest.raises(ValueError, match="different source snapshots"):
        assembly_module().assemble(evidence_root=root, startup_evidence=root / first["path"],
            timing_evidence=root / second["path"], dll=root / spec["native"]["dll"]["path"],
            provenance=root / spec["native"]["provenance"]["path"], bridge=root / spec["bridge"]["path"])


def test_cleanup_from_other_trial_cannot_substitute(evidence):
    add_nine(evidence)
    evidence[2]["probes"][0]["cleanup"] = evidence[2]["startup"]["cleanup"]
    report = verify(evidence)
    assert report["status"] == "invalid"
    assert any("different trial" in error for error in report["errors"])


@pytest.mark.parametrize("mutation", ["paused", "width", "coordinate_space", "capture_id", "clock"])
def test_native_capture_semantics_are_not_only_matching_reference_hashes(evidence, mutation):
    root, _, spec = evidence
    admission = a.read_json((root / spec["startup"]["admission"]["path"]).read_bytes())
    raw, reference = admission["first_observation"], admission["first_image"]
    if mutation == "clock":
        raw["capabilities"]["fixed_step_denominator"] = 30
    else:
        value = {"paused": False, "width": 100, "coordinate_space": "screen", "capture_id": True}[mutation]
        raw["visual"][mutation] = value
        reference[mutation] = value
    with pytest.raises(a.EvidenceError):
        a._capture(a.Reader(root), spec["startup"], raw, reference)
