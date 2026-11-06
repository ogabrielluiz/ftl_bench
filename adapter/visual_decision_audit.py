"""Offline replay of a completed typed API decision; never calls a provider/game."""
from __future__ import annotations

import json
import base64
import math
from pathlib import Path
import stat

from visual_agent import VisualObservation, VisualProtocolError, build_visual_prompt, parse_decision, read_screenshot
from visual_choice_agent import (DECISION_CONTRACT, PROMPT_PATH, TypedVisualAgent,
                                 canonical, choice_program, complete_usage, sha)
from visual_decision_api import parse_choice_response, reconstruct_request


def _safe_path(path: Path) -> Path:
    path = path.absolute()
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked decision evidence is not supported")
    return path


def _bytes(path: Path, limit: int) -> bytes:
    _safe_path(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Decision evidence must be a regular file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Oversized decision evidence")
    return data


def _read(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON evidence key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Non-finite JSON evidence value")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            reject_constant(value)
        return parsed

    return json.loads(_bytes(path, 2 * 1024 * 1024).decode("utf-8"),
                      object_pairs_hook=unique, parse_constant=reject_constant, parse_float=finite_float)


def audit_decision(directory: Path) -> dict:
    try:
        directory = _safe_path(Path(directory))
        saved = _read(directory / "input.json")
        metadata = _read(directory / "metadata.json")
        image_bytes, image = read_screenshot(_safe_path(directory / "screenshot.png"))
        if saved["image"] != image or metadata["image"] != image:
            raise ValueError("Archived image identity differs")
        if metadata.get("decision_complete") is not True or metadata.get("decision_contract") != DECISION_CONTRACT:
            raise ValueError("No completed supported typed decision")
        agent = TypedVisualAgent(saved["backend"], saved["model"], audit_root=directory,
                                 task=saved["actor_identity"]["task"])
        if saved["actor_identity"] != agent.instruction_identity():
            raise ValueError("Actor instruction identity differs from the versioned contract")
        if any(metadata.get(key) != value for key, value in agent.instruction_identity().items()) or any(
            metadata.get(key) != saved[key] for key in ("model", "mode", "frame_id")) or metadata.get("provider") != saved["backend"]:
            raise ValueError("Decision metadata differs from public input identity")
        instructions = PROMPT_PATH.read_bytes().decode("utf-8") + "\n\nCURRENT TASK\n" + agent.task
        prefix = instructions + "\n\nDECISION INPUT\n"
        prompt = saved["prompt"]
        if not prompt.startswith(prefix) or sha(prompt.encode()) != metadata["prompt_sha256"]:
            raise ValueError("Public prompt identity differs")
        payload = json.loads(prompt[len(prefix):])
        observation = VisualObservation(directory / "screenshot.png", saved["frame_id"], mode=saved["mode"],
            visible_hud=payload.get("visible_hud", {}), history=payload["recent_inputs"], memory=payload["your_memory"])
        if build_visual_prompt(observation, image, instructions) != prompt:
            raise ValueError("Public observation contains unexpected fields or values")
        program = choice_program(image["width"], image["height"])
        stage = next(program)
        calls = metadata["api_calls"]
        if not isinstance(calls, list) or not 2 <= len(calls) <= 10:
            raise ValueError("Invalid number of typed stages")
        client_ids = set()
        rebuilt = None
        for index, call in enumerate(calls, 1):
            if rebuilt is not None:
                raise ValueError("Unexpected stage after completed decision")
            question = stage["question"]
            stage_dir = directory / f"{index:02d}-{question['name']}"
            request = _read(stage_dir / "request.json")
            recorded_call = _read(stage_dir / "call.json")
            if {k: v for k, v in recorded_call.items() if k != "artifact"} != {k: v for k, v in call.items() if k != "artifact"}:
                raise ValueError("Stage summary differs from saved HTTP call")
            if call.get("status") != "completed" or call.get("attempts") != 1 or call.get("response_received") is not True:
                raise ValueError("Stage did not complete with one HTTP response")
            if call.get("http_status") != 200:
                raise ValueError("Stage was not a successful HTTP response")
            if call.get("stage") != question["name"] or request["backend"] != saved["backend"]:
                raise ValueError("Stage identity differs")
            client_id = request["client_request_id"]
            if not client_id or client_id in client_ids or call["client_request_id"] != client_id:
                raise ValueError("HTTP request identity is missing or reused")
            client_ids.add(client_id)
            # Reconstruct exact bytes from the archived PNG, then check every public field.
            wire = reconstruct_request(request, image_bytes)
            body = json.loads(wire)
            expected_headers = {"Content-Type": "application/json", "Accept-Encoding": "identity", "X-Client-Request-Id": client_id}
            if saved["backend"] == "jev":
                expected_headers["TypeSafe-Danger-Zone-Images"] = "true"
            if request["headers"] != expected_headers:
                raise ValueError("Unexpected archived request headers")
            encoded = base64.b64encode(image_bytes).decode("ascii")
            context = prompt + "\n\nALREADY SELECTED FOR THIS SAME FRAME\n" + canonical(stage["selected"]).decode()
            if body["model"] != saved["model"] or call["requested_model"] != saved["model"]:
                raise ValueError("Requested model differs")
            if saved["backend"] == "jev":
                if request["endpoint"] != "https://api.typesafe.ai/v1/systemone" or set(body) != {"model", "state", "questions", "assets"}:
                    raise ValueError("Unexpected Jev request surface")
                if request["headers"].get("TypeSafe-Danger-Zone-Images") != "true":
                    raise ValueError("Missing Jev image opt-in")
                reference = body["state"]["screenshot"]
                if body["state"] != {"context": context, "screenshot": reference} or set(body["assets"]) != {reference}:
                    raise ValueError("Unexpected Jev shared input")
                if body["assets"][reference] != {"type": "image", "format": "png", "data_base64": encoded}:
                    raise ValueError("Unexpected Jev image fields")
                expected = {question["name"]: {"type": "choice", "instructions": question["instructions"], "criteria": question["choices"]}}
            else:
                if request["endpoint"] != "https://api.openai.com/v1/decisions" or set(body) != {"model", "input", "questions"}:
                    raise ValueError("Unexpected Decisions request surface")
                if body["input"] != [{"role": "user", "content": [{"type": "input_text", "text": context},
                                          {"type": "input_image", "image_url": "data:image/png;base64," + encoded}]}]:
                    raise ValueError("Unexpected Decisions shared input")
                expected = [{"type": "choice", "name": question["name"], "instructions": question["instructions"],
                             "choices": [{"value": key, "description": value} for key, value in question["choices"].items()]}]
            if body["questions"] != expected:
                raise ValueError("Stage question or available options differs")
            raw = _bytes(stage_dir / "response.json", 1024 * 1024)
            if len(raw) > 1024 * 1024 or sha(raw) != call["response_sha256"] or len(raw) != call["response_bytes"]:
                raise ValueError("Response byte identity differs")
            answer = parse_choice_response(saved["backend"], saved["model"], question, raw)
            for key, value in answer.items():
                if call.get(key) != value:
                    raise ValueError("Replayed response differs from recorded summary")
            try:
                stage = program.send(answer["choice"])
            except StopIteration as finished:
                rebuilt = {**finished.value, "memory": observation.memory}
        if rebuilt is None:
            raise ValueError("Missing final typed stage")
        decision = _read(directory / "decision.json")
        if decision != rebuilt:
            raise ValueError("Saved action differs from the replayed typed choices")
        parse_decision(json.dumps(decision), image["width"], image["height"])
        if metadata.get("usage") != complete_usage(calls):
            raise ValueError("Usage total differs from stage evidence")
        return {"valid": True, "decision_contract": DECISION_CONTRACT, "provider": saved["backend"],
                "requested_model": saved["model"], "http_requests": len(calls), "image_sha256": image["sha256"],
                "decision": decision, "valid_for_model_comparison": False,
                "scope": "Saved screenshot, typed request/response chain and reconstructed input only; no gameplay or admission proof."}
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError, VisualProtocolError) as error:
        return {"valid": False, "reason": str(error), "valid_for_model_comparison": False}
