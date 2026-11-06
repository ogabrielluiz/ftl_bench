"""Image-only, staged Choice actors; all choices become ordinary visual inputs.

This actor sees no native state and never dispatches game input. Its single-input
contract is intentionally distinct from the frozen Codex comparison protocol.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

from visual_agent import (CONTRACT, KEYS, VisualBackendError, VisualDecision,
                          VisualObservation, VisualProtocolError, build_visual_prompt,
                          parse_decision, read_screenshot)
from visual_decision_api import request_choice


DECISION_CONTRACT = "ftl-visual-typed-choice-v1"
PROMPT_VERSION = "ftl-visual-choices-v1"
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts/ftl_visual_choices_v1.md"
DEFAULT_MODELS = {"jev": "jev-1.14.0", "openai-decisions": "gpt-6-luna"}
ADVANCES = (0, 1, 30, 60, 120, 300, 600)
MODIFIERS = ((), ("shift",), ("ctrl",), ("shift", "ctrl"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def write_exclusive(path: Path, value) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(value))


def control_choices() -> dict[str, dict]:
    controls = {"wait": {"description": "Send no input; choose a simulation advance next.", "action": None},
                "move": {"description": "Move the mouse pointer to inspect a target or tooltip.",
                         "action": {"type": "move"}}}
    for kind in ("click", "drag"):
        for button in ("left", "right"):
            for modifiers in MODIFIERS:
                name = ":".join((kind, button, "+".join(modifiers) or "none"))
                controls[name] = {"description": f"{kind.capitalize()} with the {button} mouse button; "
                                 f"modifiers: {', '.join(modifiers) or 'none'}.",
                                 "action": {"type": kind, "button": button, "modifiers": list(modifiers)}}
    for key in KEYS:
        for modifiers in MODIFIERS:
            name = ":".join(("key", key, "+".join(modifiers) or "none"))
            controls[name] = {"description": f"Press and release {key}; modifiers: {', '.join(modifiers) or 'none'}.",
                              "action": {"type": "key", "key": key, "modifiers": list(modifiers)}}
    return controls


def regions(bounds: tuple[int, int, int, int]) -> dict[str, tuple[int, int, int, int]]:
    """Partition every pixel exactly once into at most 225 nonempty rectangles."""
    x0, y0, x1, y1 = bounds
    width, height = x1 - x0 + 1, y1 - y0 + 1
    if width < 1 or height < 1:
        raise ValueError("Empty pixel region")
    columns, rows = min(15, width), min(15, height)
    return {f"r{row:02d}c{column:02d}": (
        x0 + column * width // columns, y0 + row * height // rows,
        x0 + (column + 1) * width // columns - 1,
        y0 + (row + 1) * height // rows - 1)
        for row in range(rows) for column in range(columns)}


def complete_usage(calls: list[dict]) -> dict:
    """Only report a decision total when every attempted stage supplies it."""
    calls = [call for call in calls if call.get("attempts") == 1]
    result = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        values = [(call.get("usage") or {}).get(key) for call in calls]
        if values and all(type(value) is int and value >= 0 for value in values):
            result[key] = sum(values)
    return result


def choice_program(width: int, height: int):
    """Pure staged policy, replayable without credentials, a provider or a game."""
    def question(name, instructions, choices, selected):
        return {"question": {"name": name, "instructions": instructions, "choices": choices},
                "selected": selected}

    def point(label, selected):
        bounds = (0, 0, width - 1, height - 1)
        for level in range(1, 5):
            if bounds[0] == bounds[2] and bounds[1] == bounds[3]:
                return bounds[0], bounds[1]
            cells = regions(bounds)
            options = {key: f"Inclusive pixel rectangle x={b[0]}..{b[2]}, y={b[1]}..{b[3]}."
                       for key, b in cells.items()}
            chosen = yield question(f"{label}_{level}",
                f"Which rectangle contains the intended {label} point for the selected input? "
                "Keep narrowing that same point in the original screenshot; use absolute pixel coordinates.",
                options, {**selected, "target": label, "current_bounds": list(bounds)})
            bounds = cells[chosen]
        if bounds[0] == bounds[2] and bounds[1] == bounds[3]:
            return bounds[0], bounds[1]
        raise VisualProtocolError("Coordinate selection did not converge to one pixel")

    controls = control_choices()
    selected_control = yield question("control", "Which single ordinary input should be sent next to achieve CURRENT TASK?",
                                     {key: row["description"] for key, row in controls.items()}, {})
    template = controls[selected_control]["action"]
    action = json.loads(json.dumps(template)) if template is not None else None
    if action and action["type"] in {"click", "move", "drag"}:
        action["x"], action["y"] = yield from point("start", {"control": selected_control})
        if action["type"] == "drag":
            action["to_x"], action["to_y"] = yield from point("end", {"control": selected_control, "start": [action["x"], action["y"]]})
    actions = [action] if action else []
    advance = int((yield question("advance", "After this exact input, how many simulation frames should elapse before a new screenshot?",
                  {str(n): f"Advance {n} frames ({n / 60:g} seconds)." for n in ADVANCES}, {"actions": actions})))
    return {"actions": actions, "advance_frames": advance,
            "intent": f"Typed choice: {selected_control}; advance {advance} frames."}


class TypedVisualAgent:
    def __init__(self, backend: str, model: str | None = None, *, audit_root: Path,
                 task: str = "Play this FTL run to victory.", timeout_seconds: float = 300,
                 stop_check=None):
        if backend not in DEFAULT_MODELS:
            raise VisualProtocolError("Unsupported typed visual backend")
        self.backend = backend
        self.model = model or DEFAULT_MODELS[backend]
        if not isinstance(self.model, str) or not self.model.strip():
            raise VisualProtocolError("An explicit model is required")
        if backend == "openai-decisions" and self.model != "gpt-6-luna":
            raise VisualProtocolError("OpenAI Decisions currently supports only gpt-6-luna")
        if not isinstance(task, str) or not task.strip() or len(task) > 1000:
            raise VisualProtocolError("Task must contain 1..1000 characters")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 3600:
            raise VisualProtocolError("Timeout must be finite and within 1..3600 seconds")
        self.task, self.timeout_seconds = task, timeout_seconds
        self.audit_root = Path(audit_root).resolve()
        self.stop_check = stop_check
        self._manual = PROMPT_PATH.read_bytes()
        self._instructions = self._manual.decode("utf-8") + "\n\nCURRENT TASK\n" + task

    def require_credentials(self) -> None:
        names = ("OPENAI_API_KEY",) if self.backend == "openai-decisions" else ("TYPESAFE_API_KEY", "JEV_API_KEY")
        if not any((os.environ.get(name) or "").strip() for name in names):
            raise VisualBackendError(f"{names[0]} is required for {self.backend}")
        self._check_private_text(self._instructions + str(self.audit_root))

    def _check_private_text(self, text: str) -> None:
        names = ("OPENAI_API_KEY",) if self.backend == "openai-decisions" else ("TYPESAFE_API_KEY", "JEV_API_KEY")
        for name in names:
            key = (os.environ.get(name) or "").strip()
            if key and key in text:
                raise VisualBackendError("Configured credential appeared in public decision input; nothing was sent or archived")

    def instruction_identity(self) -> dict:
        return {"contract": CONTRACT, "decision_contract": DECISION_CONTRACT,
                "prompt_version": PROMPT_VERSION, "manual_sha256": sha(self._manual),
                "task": self.task, "task_sha256": sha(self.task.encode()),
                "instructions_sha256": sha(self._instructions.encode()),
                "max_actions": 1, "advance_choices": list(ADVANCES),
                "coordinate_selection": "successive-15x15-pixel-regions-v1",
                "memory_policy": "retain-supplied-note-no-generated-memory"}

    def decide(self, observation: VisualObservation) -> VisualDecision:
        image_bytes, image = read_screenshot(observation.image_path)
        if observation.expected_image_sha256 is not None and image["sha256"] != observation.expected_image_sha256:
            raise VisualBackendError("Screenshot differs from the archived frame identity")
        prompt = build_visual_prompt(observation, image, self._instructions)
        self.require_credentials()
        self._check_private_text(prompt)
        directory = self.audit_root / ("decision-" + uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "screenshot.png").write_bytes(image_bytes)
        calls = []
        started = time.monotonic()
        metadata = {"provider": self.backend, "model": self.model, "requested_model": self.model,
                    **self.instruction_identity(), "api_audit_version": 1, "decision_complete": False,
                    "mode": observation.mode, "frame_id": observation.frame_id, "image": image,
                    "prompt_sha256": sha(prompt.encode()), "api_calls": calls,
                    "artifact": directory.relative_to(self.audit_root.parent).as_posix(),
                    "tool_use": False}
        write_exclusive(directory / "input.json", {"prompt": prompt, "image": image,
                        "frame_id": observation.frame_id, "mode": observation.mode,
                        "actor_identity": self.instruction_identity(), "backend": self.backend,
                        "model": self.model})

        def choose(stage: str, instructions: str, options: dict[str, str], selected: dict) -> str:
            if self.stop_check:
                self.stop_check()
            remaining = self.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise VisualBackendError("Typed visual decision exceeded its time budget")
            question = {"name": stage, "instructions": instructions, "choices": options}
            stage_path = directory / f"{len(calls) + 1:02d}-{stage}"
            context = prompt + "\n\nALREADY SELECTED FOR THIS SAME FRAME\n" + canonical(selected).decode()
            try:
                choice, call = request_choice(backend=self.backend, model=self.model, context=context,
                    image_bytes=image_bytes, image=image, question=question, audit_path=stage_path,
                    timeout=min(90.0, remaining))
            except BaseException as error:
                call = getattr(error, "metadata", {}).get("api_call")
                if isinstance(call, dict):
                    calls.append({**call, "artifact": stage_path.relative_to(self.audit_root.parent).as_posix()})
                raise
            calls.append({**call, "artifact": stage_path.relative_to(self.audit_root.parent).as_posix()})
            if not isinstance(choice, str) or choice not in options:
                raise VisualProtocolError("Typed API chose an unavailable option")
            return choice

        try:
            program = choice_program(image["width"], image["height"])
            stage = next(program)
            while True:
                question = stage["question"]
                choice = choose(question["name"], question["instructions"], question["choices"], stage["selected"])
                try:
                    stage = program.send(choice)
                except StopIteration as finished:
                    decision = parse_decision(json.dumps({**finished.value, "memory": observation.memory}), image["width"], image["height"])
                    break
            if time.monotonic() - started >= self.timeout_seconds:
                raise VisualBackendError("Typed visual decision exceeded its time budget")
            if self.stop_check:
                self.stop_check()
            metadata["decision_complete"] = True
            write_exclusive(directory / "decision.json", decision.as_dict())
            return replace(decision, metadata=metadata)
        except BaseException as error:
            metadata.update({key: value for key, value in getattr(error, "metadata", {}).items()
                             if key not in metadata and key != "api_call"})
            error.metadata = metadata
            write_exclusive(directory / "failure.json", {"type": type(error).__name__,
                            "reason": "Typed decision did not complete; no game input emitted by this actor."})
            raise
        finally:
            metadata["latency_seconds"] = round(time.monotonic() - started, 3)
            metadata["usage"] = complete_usage(calls)
            reported = sorted({call["model"] for call in calls if isinstance(call.get("model"), str)})
            metadata["response_model_identity"] = {"status": "reported" if reported else "not_reported", "models": reported}
            write_exclusive(directory / "metadata.json", metadata)
