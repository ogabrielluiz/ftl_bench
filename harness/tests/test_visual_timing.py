"""No-model fixed-step acceptance must expose real state drift and partial frames."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from ftl_bench.cli import _bench_root

import sys
sys.path.insert(0, str(_bench_root() / "scripts"))
import validate_visual_timing as timing


def raw_state():
    return {"paused": True, "seed": 1, "player_ship": {"oxygen_pct": 100,
        "systems": [{"id": 2, "power": 1}], "crew": [],
        "rooms": [{"room_id": 13, "oxygen": 100, "fires": 1}]},
        "economy": {"navigation": {"drive_current": 0}},
        "visual": {"world_updates": "5", "simulated_updates": "5", **timing.challenges.TIME_CONTRACT},
        "capabilities": {"world_updates": "5", "simulated_updates": "5", **timing.challenges.TIME_CONTRACT},
        "visual_challenge_system_health": [{"system_id": 2, "health_current": 1, "health_max": 1}],
        "visual_challenge_fixture": {"initial_rng_seed": 1}}


def reports(kind="repair-charge-escape"):
    return [{"challenge": kind, "delay_seconds": delay, "passed": True,
        "time_contract": timing.challenges.TIME_CONTRACT,
        "initial_gameplay_sha256": "initial",
        "steps": [{"label": label, "actions": list(packet), "requested_frames": frames,
                   "gameplay_sha256": str(index)}
                  for index, (label, packet, frames) in enumerate(timing.probe_cases(kind))]}
        for delay in timing.DELAYS]


@pytest.mark.parametrize("kind", list(timing.challenges.TASKS))
def test_repeatability_requires_every_exact_state_under_three_wall_delays(kind):
    data = reports(kind)
    assert timing.compare_repeats(data)["passed"]
    for change in (lambda r: r.update(initial_gameplay_sha256="drift"),
                   lambda r: r["steps"][2].update(gameplay_sha256="drift"),
                   lambda r: r["steps"][1].update(requested_frames=119),
                   lambda r: r["steps"][0].update(actions=[]),
                   lambda r: r.update(passed=False),
                   lambda r: r.update(delay_seconds=.9),
                   lambda r: r["steps"].pop()):
        altered = deepcopy(data)
        change(altered[2])
        assert not timing.compare_repeats(altered)["passed"]
    assert not timing.compare_repeats(data[:2])["passed"]


def test_idle_requires_actual_gameplay_and_counters_frozen():
    raw = raw_state()
    cosmetic = deepcopy(raw)
    cosmetic.update(timestamp=900, tick=999)
    cosmetic["visual"].update(capture_id=90)
    assert timing.idle_proof(raw, cosmetic)["passed"]
    for change in (lambda r: r["player_ship"].update(oxygen_pct=99.9999999),
                   lambda r: r["visual"].update(world_updates="6", simulated_updates="6"),
                   lambda r: r.update(paused=False)):
        changed = deepcopy(raw)
        change(changed)
        assert not timing.idle_proof(raw, changed)["passed"]


def test_fire_progression_cannot_be_satisfied_by_drive_charging():
    raw = raw_state()
    charged = deepcopy(raw)
    charged["economy"]["navigation"]["drive_current"] = 1
    assert timing.signature_hash(charged) != timing.signature_hash(raw)
    assert timing.fire_progression(charged) == timing.fire_progression(raw)
    assert not timing.fire_progression_proof(raw, charged)["passed"]
    charged["player_ship"]["rooms"][0]["oxygen"] = 99
    assert timing.fire_progression(charged) != timing.fire_progression(raw)
    assert timing.fire_progression_proof(raw, charged)["passed"]
    charged.pop("visual_challenge_system_health")
    assert not timing.fire_progression_proof(raw, charged)["passed"]


def test_fire_proof_does_not_misread_missing_room_as_fire_extinguished():
    raw = raw_state()
    raw["player_ship"]["rooms"].append({"room_id": 1, "oxygen": 100, "fires": 0})
    changed = deepcopy(raw)
    changed["player_ship"]["rooms"].pop(0)
    assert not timing.fire_progression_proof(raw, changed)["passed"]


def frame(raw):
    identity = raw.get("capture_identity", 0)
    return SimpleNamespace(observation=SimpleNamespace(raw=raw),
        reference={"sha256": "image", "capture_id": identity, "frame_id": identity})


def test_scripted_repair_probe_verifies_ordinary_power_input_and_effective_time(tmp_path, monkeypatch):
    current = [frame(raw_state())]
    calls = []
    class Transport:
        def step(self, before, actions, requested):
            calls.append((actions, requested))
            raw = deepcopy(before.observation.raw)
            raw["capture_identity"] = raw.get("capture_identity", 0) + 1
            if actions and actions[0]["type"] == "key":
                raw["player_ship"]["systems"][0]["power"] = 0 if actions[0]["modifiers"] else 1
            if requested and not raw["player_ship"]["systems"][0]["power"]:
                raw["player_ship"]["oxygen_pct"] -= 1
            updates = str(int(raw["visual"]["world_updates"]) + requested)
            for source in ("visual", "capabilities"):
                raw[source].update(world_updates=updates, simulated_updates=updates)
            raw["visual"].update(actual_frames=requested, input_feedback=[
                {"status": "delivered", "index": i, "type": a["type"]} for i, a in enumerate(actions)])
            current[0] = frame(raw)
            return current[0]
    session = SimpleNamespace(observe=lambda: current[0].observation)
    recorder = SimpleNamespace(record=lambda *a, **kw: None)
    monkeypatch.setattr(timing, "visual_record", lambda *a: {})
    report = timing.run_probe(session, Transport(), recorder, current[0], tmp_path,
        SimpleNamespace(challenge="repair-charge-escape", probe_delay_seconds=0))
    assert report["passed"] and report["model_calls"] == 0
    assert calls == [entry for _, packet, frames in timing.REPAIR_CASES
        for entry in (([], 0), (list(packet), frames))]
    assert sum(s["native_counter_delta"] for s in report["steps"]) == 360
    assert json.loads((tmp_path / "timing-proof.json").read_text())["passed"]


def test_scripted_probe_stops_before_input_when_fresh_idle_state_drifts(tmp_path, monkeypatch):
    raw = raw_state()
    changed = deepcopy(raw)
    changed["player_ship"]["oxygen_pct"] = 99
    changed["capture_identity"] = 1
    session = SimpleNamespace(observe=lambda: SimpleNamespace(raw=changed))
    calls = []
    def idle_only(before, actions, requested):
        assert not actions and not requested
        calls.append((actions, requested))
        return frame(changed)
    monkeypatch.setattr(timing, "visual_record", lambda *a: {})
    recorder = SimpleNamespace(record=lambda *a, **kw: None)
    with pytest.raises(RuntimeError, match="World changed"):
        timing.run_probe(session, SimpleNamespace(step=idle_only), recorder, frame(raw), tmp_path,
            SimpleNamespace(challenge="repair-charge-escape", probe_delay_seconds=0))
    assert calls == [([], 0)]
    assert not json.loads((tmp_path / "timing-proof.json").read_text())["passed"]
