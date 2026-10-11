"""Image-only decision boundary for FTL's ordinary mouse and keyboard controls.

This module never imports the native observation or session. Its input is an image,
an explicitly allowlisted visible HUD, and the actor's own bounded action history.
It does not execute game inputs. A successful CLI exit is insufficient: JSONL events
must prove a completed turn with no tool calls before a decision can be returned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import zlib


CONTRACT = "ftl-visual-actions-v1"
MAX_ACTIONS = 4
MAX_ADVANCE_FRAMES = 600
MAX_MEMORY_CHARS = 1200
MAX_INTENT_CHARS = 240
MAX_HISTORY = 8
PROMPT_VERSION = "ftl-visual-v2"
CLI_EVENT_POLICY = "ftl-codex-cli-reconnect-v1"
LEGACY_CLI_EVENT_POLICY = "ftl-codex-cli-strict-v1"
_RECONNECT = re.compile(
    r"Reconnecting\.\.\. ([1-5])/5 \(stream disconnected before completion: "
    r"(?:websocket closed by server before response\.completed|"
    r"IO error: An existing connection was forcibly closed by the remote host\. \(os error 10054\))\)")
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "ftl_visual_v2.md"
HUD_INTS = {"hull_current", "hull_max", "fuel", "scrap", "missiles", "drone_parts"}
KEYS = tuple("abcdefghijklmnopqrstuvwxyz0123456789") + (
    "escape", "enter", "tab", "backspace", "space", "up", "down", "left", "right",
)
MODIFIERS = ("shift", "ctrl")


class VisualProtocolError(RuntimeError):
    """Decision is unusable; end or flag the trial, never silently advance FTL."""

    def __init__(self, message: str, *, metadata: dict | None = None):
        super().__init__(message)
        self.metadata = metadata or {}


class VisualBackendError(VisualProtocolError):
    """The CLI/backend failed before a usable, audited response was available."""


@dataclass(frozen=True)
class VisualObservation:
    image_path: Path
    frame_id: str
    mode: str = "image"
    visible_hud: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    memory: str = ""


@dataclass(frozen=True)
class VisualDecision:
    actions: list[dict]
    advance_frames: int
    intent: str
    memory: str
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"actions": self.actions, "advance_frames": self.advance_frames,
                "intent": self.intent, "memory": self.memory}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _integer(value, minimum: int, maximum: int, name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise VisualProtocolError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _text(value, maximum: int, name: str) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise VisualProtocolError(f"{name} must be a string of at most {maximum} characters")
    return value


def _exact_keys(value, keys: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise VisualProtocolError(f"{name} has missing or unexpected fields")


def _json_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise VisualProtocolError("JSON contains a duplicate field")
        obj[key] = value
    return obj


def _decode_json(text: str):
    try:
        return json.loads(text, object_pairs_hook=_json_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              VisualProtocolError("JSON contains a non-finite number")))
    except (ValueError, TypeError) as error:
        raise VisualProtocolError("invalid JSON decision or event") from error


def read_screenshot(path: Path) -> tuple[bytes, dict]:
    """Read once, validate PNG structure/CRC, then hash the exact attached bytes."""
    try:
        with Path(path).open("rb") as image:
            data = image.read(16 * 1024 * 1024 + 1)
    except OSError as error:
        raise VisualProtocolError("screenshot is missing or unreadable") from error
    if len(data) > 16 * 1024 * 1024 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise VisualProtocolError("screenshot must be a PNG of at most 16 MiB")
    offset, dimensions, image_data, ended = 8, None, False, False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + length
        if end > len(data):
            raise VisualProtocolError("screenshot PNG is truncated")
        tag = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(tag + payload) & 0xFFFFFFFF != crc:
            raise VisualProtocolError("screenshot PNG checksum is invalid")
        if dimensions is None:
            if tag != b"IHDR" or length != 13:
                raise VisualProtocolError("screenshot PNG has no valid header")
            dimensions = struct.unpack_from(">II", payload)
        elif tag == b"IHDR":
            raise VisualProtocolError("screenshot PNG repeats its header")
        if tag == b"IDAT" and length:
            image_data = True
        offset = end
        if tag == b"IEND":
            if length or offset != len(data):
                raise VisualProtocolError("screenshot PNG has invalid trailing data")
            ended = True
            break
    if not dimensions or not image_data or not ended:
        raise VisualProtocolError("screenshot PNG is incomplete")
    width, height = dimensions
    _integer(width, 1, 8192, "image width")
    _integer(height, 1, 8192, "image height")
    return data, {"sha256": _sha(data), "width": width, "height": height,
                  "mime_type": "image/png", "bytes": len(data)}


def validate_action(action: dict, width: int, height: int) -> dict:
    """Strict independent validation; do not trust provider schema enforcement."""
    if not isinstance(action, dict):
        raise VisualProtocolError("action must be an object")
    kind = action.get("type")
    fields = {"click": {"type", "x", "y", "button", "modifiers"},
              "move": {"type", "x", "y"},
              "drag": {"type", "x", "y", "to_x", "to_y", "button", "modifiers"},
              "key": {"type", "key", "modifiers"}}
    if not isinstance(kind, str) or kind not in fields:
        raise VisualProtocolError("unsupported visual action")
    _exact_keys(action, fields[kind], "action")
    if kind in {"click", "move", "drag"}:
        _integer(action["x"], 0, width - 1, "x")
        _integer(action["y"], 0, height - 1, "y")
    if kind == "drag":
        _integer(action["to_x"], 0, width - 1, "to_x")
        _integer(action["to_y"], 0, height - 1, "to_y")
    if kind in {"click", "drag"} and action["button"] not in ("left", "right"):
        raise VisualProtocolError("unsupported mouse button")
    if kind == "key":
        if action["key"] not in KEYS:
            raise VisualProtocolError("unsupported key")
    if kind in {"key", "click", "drag"}:
        modifiers = action["modifiers"]
        allowed_modifiers = MODIFIERS if kind == "key" else ("shift", "ctrl")
        if (not isinstance(modifiers, list) or len(modifiers) > 2
                or any(m not in allowed_modifiers for m in modifiers)
                or len(set(modifiers)) != len(modifiers)):
            raise VisualProtocolError("unsupported or repeated key modifier")
    return {**action, **({"modifiers": list(action["modifiers"])} if "modifiers" in action else {})}


def parse_decision(text: str, width: int, height: int) -> VisualDecision:
    if not isinstance(text, str) or len(text) > 16384:
        raise VisualProtocolError("decision is missing or too large")
    data = _decode_json(text)
    _exact_keys(data, {"actions", "advance_frames", "intent", "memory"}, "decision")
    if not isinstance(data["actions"], list) or len(data["actions"]) > MAX_ACTIONS:
        raise VisualProtocolError(f"decision needs at most {MAX_ACTIONS} actions")
    actions = [validate_action(a, width, height) for a in data["actions"]]
    return VisualDecision(actions, _integer(data["advance_frames"], 0, MAX_ADVANCE_FRAMES, "advance_frames"),
                          _text(data["intent"], MAX_INTENT_CHARS, "intent"),
                          _text(data["memory"], MAX_MEMORY_CHARS, "memory"))


def decision_schema(width: int, height: int) -> dict:
    def obj(properties):
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    x = {"type": "integer", "minimum": 0, "maximum": width - 1}
    y = {"type": "integer", "minimum": 0, "maximum": height - 1}
    button = {"type": "string", "enum": ["left", "right"]}
    mouse_modifiers = {"type": "array", "maxItems": 2,
                       "items": {"type": "string", "enum": ["shift", "ctrl"]}}
    action_specs = {"click": {"x": x, "y": y, "button": button, "modifiers": mouse_modifiers},
                    "move": {"x": x, "y": y},
                    "drag": {"x": x, "y": y, "to_x": x, "to_y": y, "button": button,
                             "modifiers": mouse_modifiers},
                    "key": {"key": {"type": "string", "enum": list(KEYS)},
                            "modifiers": {"type": "array", "maxItems": 2,
                                          "items": {"type": "string", "enum": list(MODIFIERS)}}}}
    return obj({"actions": {"type": "array", "maxItems": MAX_ACTIONS,
                             "items": {"anyOf": [obj({"type": {"type": "string", "enum": [kind]}, **spec})
                                                 for kind, spec in action_specs.items()]}},
                "advance_frames": {"type": "integer", "minimum": 0, "maximum": MAX_ADVANCE_FRAMES},
                "intent": {"type": "string", "maxLength": MAX_INTENT_CHARS},
                "memory": {"type": "string", "maxLength": MAX_MEMORY_CHARS}})


def _visible_hud(hud: dict) -> dict:
    if not isinstance(hud, dict) or set(hud) - (HUD_INTS | {"paused"}):
        raise VisualProtocolError("visible HUD has unapproved fields")
    for key, value in hud.items():
        if key == "paused":
            if type(value) is not bool:
                raise VisualProtocolError("paused must be a boolean")
        else:
            _integer(value, 0, 1000000, key)
    return dict(hud)


def _history(history: list[dict], width: int, height: int) -> list[dict]:
    if not isinstance(history, list):
        raise VisualProtocolError("history must be a list")
    result = []
    for entry in history[-MAX_HISTORY:]:
        allowed = {"actions", "advance_frames", "actual_advance_frames", "intent", "delivery"}
        if not isinstance(entry, dict) or set(entry) - allowed:
            raise VisualProtocolError("history has unapproved fields")
        copied = {}
        if "actions" in entry:
            if not isinstance(entry["actions"], list) or len(entry["actions"]) > MAX_ACTIONS:
                raise VisualProtocolError("invalid history actions")
            copied["actions"] = [validate_action(a, width, height) for a in entry["actions"]]
        for key in ("advance_frames", "actual_advance_frames"):
            if key in entry:
                copied[key] = _integer(entry[key], 0, MAX_ADVANCE_FRAMES, key)
        if "intent" in entry:
            copied["intent"] = _text(entry["intent"], MAX_INTENT_CHARS, "history intent")
        if "delivery" in entry:
            if entry["delivery"] not in ("delivered", "rejected", "interrupted", "unknown"):
                raise VisualProtocolError("unsupported input delivery status")
            copied["delivery"] = entry["delivery"]
        result.append(copied)
    return result


def build_visual_prompt(observation: VisualObservation, image: dict, manual: str) -> str:
    if observation.mode not in {"image", "hybrid"}:
        raise VisualProtocolError("observation mode must be image or hybrid")
    frame_id = _text(observation.frame_id, 128, "frame_id")
    if not frame_id:
        raise VisualProtocolError("frame_id is required")
    hud = _visible_hud(observation.visible_hud)
    if observation.mode == "image" and hud:
        raise VisualProtocolError("image-only mode cannot include a HUD summary")
    payload = {"frame_id": frame_id, "image": {key: image[key] for key in ("sha256", "width", "height")},
               "mode": observation.mode,
               "recent_inputs": _history(observation.history, image["width"], image["height"]),
               "your_memory": _text(observation.memory, MAX_MEMORY_CHARS, "memory")}
    if observation.mode == "hybrid":
        payload["visible_hud"] = hud
    return manual + "\n\nDECISION INPUT\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _cli_bytes(value):
    return value if isinstance(value, bytes) else (value or "").encode("utf-8")


def _redact_cli_credentials(raw):
    patterns = (rb"(?i)(\b(?:authorization\s*:\s*)?(?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+",
                rb"(?i)(\b(?:api[_-]?key|access[_-]?token)\s*(?:\\?[\"'])?\s*[:=]\s*(?:\\?[\"'])?)[A-Za-z0-9._~+/=-]+",
                rb"\b(?:sk-|apikey_)[A-Za-z0-9_-]+")
    count = 0
    for pattern in patterns:
        raw, matches = re.subn(pattern, lambda match: (match.group(1) if match.lastindex else b"") + b"[REDACTED]", raw)
        count += matches
    return raw, count


def _cli_diagnostic_text(value, limit):
    if not isinstance(value, str):
        value = "<" + type(value).__name__ + ">"
    return _redact_cli_credentials(value.encode("utf-8"))[0][:limit].decode("utf-8", errors="ignore")


def _cli_failure(kind, stdout=None, stderr=None, *, partial=False, error=None):
    """Retain bounded private diagnostic bytes independently of temporary files."""
    result = {"kind": kind, "partial": partial}
    for name, value, limit in (("stdout", stdout, 2 * 1024 * 1024), ("stderr", stderr, 64 * 1024)):
        raw = _cli_bytes(value)
        redacted, redaction_count = _redact_cli_credentials(raw)
        retained = redacted[:limit]
        try:
            raw.decode("utf-8")
            valid = True
        except UnicodeError:
            valid = False
        result[name] = {"available": value is not None, "representation": "original_bytes" if isinstance(value, bytes) else "utf8_encoded_text",
                        "sha256": _sha(raw), "hash_scope": "original_bytes", "bytes": len(raw),
                        "retained_sha256": _sha(retained), "retained_hash_scope": "redacted_retained_bytes",
                        "redacted": redaction_count > 0, "redaction_count": redaction_count,
                        "redacted_bytes": len(redacted), "retained_bytes": len(retained),
                        "truncated": len(redacted) > limit, "utf8_valid": valid,
                        "base64": base64.b64encode(retained).decode("ascii"),
                        "text": retained.decode("utf-8", errors="replace")}
    if error is not None:
        result["error"] = _cli_diagnostic_text(str(error), 1024)
    return result


def audit_codex_events(stdout: str, *, policy: str = CLI_EVENT_POLICY) -> dict:
    """Fail closed if tool activity, an unknown item, or an incomplete turn appears."""
    if not isinstance(stdout, str) or len(stdout) > 2 * 1024 * 1024:
        raise VisualProtocolError("CLI event stream is missing or too large")
    if not isinstance(policy, str) or policy not in {CLI_EVENT_POLICY, LEGACY_CLI_EVENT_POLICY}:
        raise VisualProtocolError("Unknown CLI event policy")
    modern = policy == CLI_EVENT_POLICY
    notices, thread_started, agent_message_started = [], False, False
    events, completed, started, messages = [], False, False, []
    for event_index, line in enumerate(line for line in stdout.splitlines() if line.strip()):
        if not line.strip():
            continue
        try:
            event = _decode_json(line)
        except VisualProtocolError as error:
            raise VisualProtocolError(str(error), metadata={"cli_failure_context": {
                "kind": "malformed_json", "event_index": event_index}}) from error
        if not isinstance(event, dict):
            raise VisualProtocolError("CLI event is not an object")
        kind = event.get("type")
        if not isinstance(kind, str):
            raise VisualProtocolError("CLI failed or emitted an unsupported event", metadata={
                "cli_failure_context": {"kind": "unsupported_event",
                "event_type": kind, "event_index": event_index}})
        if completed:
            raise VisualProtocolError("CLI emitted events after turn completion")
        if kind == "thread.started":
            if started or events:
                raise VisualProtocolError("CLI started an unexpected extra thread")
            thread_started = True
        elif kind == "turn.started":
            if started:
                raise VisualProtocolError("CLI started an unexpected extra turn")
            started = True
        elif kind in {"item.started", "item.updated", "item.completed"}:
            item = event.get("item")
            if not started or not isinstance(item, dict) or not isinstance(item.get("type"), str) or item.get("type") not in {"reasoning", "agent_message"}:
                raise VisualProtocolError("CLI tool use or unknown activity invalidates this decision",
                    metadata={"cli_failure_context": {"kind": "unsupported_activity",
                              "event_type": kind, "event_index": event_index,
                              "item_type": item.get("type") if isinstance(item, dict) else None}})
            if item.get("type") == "agent_message":
                agent_message_started = True
            if kind == "item.completed" and item.get("type") == "agent_message":
                messages.append(item.get("text"))
        elif kind == "turn.completed":
            if not started or not messages:
                raise VisualProtocolError("CLI completion lacks an audited agent message")
            if modern and (not thread_started or len(messages) != 1):
                raise VisualProtocolError("CLI completion requires one thread and exactly one final message")
            completed = True
        elif kind == "error" and modern:
            message = event.get("message")
            match = _RECONNECT.fullmatch(message) if isinstance(message, str) else None
            if (set(event) != {"type", "message"} or not match or not started
                    or not thread_started or agent_message_started or len(notices) >= 5
                    or (notices and int(match.group(1)) <= notices[-1]["attempt"])):
                raise VisualProtocolError("CLI failed or emitted an unsupported event", metadata={
                    "cli_failure_context": {"kind": "unsupported_event",
                    "event_type": kind, "event_index": event_index}})
            notices.append({"event_index": event_index, "attempt": int(match.group(1)),
                            "max_attempts": 5, "message": message})
        else:
            raise VisualProtocolError("CLI failed or emitted an unsupported event",
                                      metadata={"cli_failure_context": {"kind": "unsupported_event",
                                                "event_type": kind, "event_index": event_index}})
        events.append(event)
    if not completed:
        raise VisualProtocolError("CLI event stream did not complete")
    usage = events[-1].get("usage")
    if usage is not None:
        if not isinstance(usage, dict) or any(type(v) is not int or v < 0 for v in usage.values()):
            raise VisualProtocolError("CLI usage is malformed")
    identities = []
    for index, event in enumerate(events):
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        for value, source in ((event.get("model"), "model"),
                              (item.get("model"), "item.model")):
            if isinstance(value, str) and value.strip():
                identities.append({"event_index": index, "field": source, "model": value})
    return {"cli_event_policy": policy, "reconnect_notices": notices,
            "events": events, "event_stream_sha256": _sha(stdout.encode("utf-8")),
            "tool_use": False, "usage": usage, "last_message": messages[-1],
            "response_model_identity": {
                "status": "reported" if identities else "not_reported",
                "models": sorted({item["model"] for item in identities}), "evidence": identities}}


def _codex_executable(explicit: str | Path | None) -> str:
    candidate = explicit or os.environ.get("CODEX_BIN") or shutil.which("codex")
    if not candidate:
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/OpenAI/Codex/bin/codex.exe"
    resolved = shutil.which(str(candidate)) or str(candidate)
    if not Path(resolved).is_file():
        raise VisualBackendError("Codex CLI executable was not found")
    return str(Path(resolved).resolve())


class CodexVisualAgent:
    def __init__(self, model: str = "gpt-6.1-sol", reasoning_effort: str = "medium", *,
                 timeout_seconds: float = 300, codex_bin: str | Path | None = None,
                 task: str = "Play this FTL run to victory."):
        if not isinstance(model, str) or not model.strip():
            raise VisualProtocolError("an explicit model is required")
        if reasoning_effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
            raise VisualProtocolError("unsupported reasoning effort")
        if not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 3600:
            raise VisualProtocolError("timeout_seconds must be in 1..3600")
        self.task = _text(task, 1000, "task")
        if not task.strip():
            raise VisualProtocolError("task cannot be empty")
        self.model, self.reasoning_effort = model, reasoning_effort
        self.timeout_seconds, self.codex_bin = timeout_seconds, codex_bin
        try:
            self._manual_bytes = PROMPT_PATH.read_bytes()
            self._instructions = self._manual_bytes.decode("utf-8") + "\n\nCURRENT TASK\n" + self.task
        except (OSError, UnicodeError) as error:
            raise VisualBackendError("Visual actor instructions are unreadable") from error

    def instruction_identity(self) -> dict:
        return {"contract": CONTRACT, "prompt_version": PROMPT_VERSION,
                "cli_event_policy": CLI_EVENT_POLICY,
                "manual_sha256": _sha(self._manual_bytes), "task": self.task,
                "task_sha256": _sha(self.task.encode("utf-8")),
                "instructions_sha256": _sha(self._instructions.encode("utf-8"))}

    def decide(self, observation: VisualObservation) -> VisualDecision:
        try:
            image_bytes, image = read_screenshot(observation.image_path)
            prompt = build_visual_prompt(observation, image, self._instructions)
        except VisualProtocolError as error:
            raise VisualBackendError("Visual decision input failed validation: " + str(error)) from error
        schema = decision_schema(image["width"], image["height"])
        executable = _codex_executable(self.codex_bin)
        metadata = {"provider": "codex", "model": self.model, "reasoning_effort": self.reasoning_effort,
                    "contract": CONTRACT, "prompt_version": PROMPT_VERSION,
                    "cli_event_policy": CLI_EVENT_POLICY,
                    "mode": observation.mode, "frame_id": observation.frame_id,
                    "image": image, "prompt_sha256": _sha(prompt.encode("utf-8")),
                    "manual_sha256": _sha(self._manual_bytes), "prompt": prompt, "schema": schema,
                    "task": self.task, "task_sha256": _sha(self.task.encode("utf-8")),
                    "instructions_sha256": _sha(self._instructions.encode("utf-8")),
                    "schema_sha256": _sha(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")),
                    "requested_model": self.model,
                    "response_model_identity": {"status": "not_reported", "models": [], "evidence": []},
                    "usage": None, "attempts": 1}
        # A fresh directory contains only the explicit decision inputs, not the repo,
        # native state, run logs or previous sessions. This is input isolation, not an
        # OS-level guarantee that the CLI cannot read other directories.
        with tempfile.TemporaryDirectory(prefix="ftl_visual_decision_") as temp:
            staging = Path(temp)
            staged_image = staging / "screenshot.png"
            staged_image.write_bytes(image_bytes)
            schema_path = staging / "decision.schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            answer_path = staging / "answer.json"
            command = [executable, "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
                       "-s", "read-only", "--color", "never", "--json", "--image", str(staged_image),
                       "--output-schema", str(schema_path), "-o", str(answer_path),
                       "-c", f"model_reasoning_effort={self.reasoning_effort}", "-m", self.model, "-"]
            started = time.monotonic()
            try:
                result = subprocess.run(command, input=prompt.encode("utf-8"), cwd=staging, capture_output=True,
                                        timeout=self.timeout_seconds)
            except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
                metadata["latency_seconds"] = round(time.monotonic() - started, 3)
                metadata["cli_failure"] = _cli_failure(
                    "timeout" if isinstance(error, subprocess.TimeoutExpired) else "request_failure",
                    getattr(error, "output", None), getattr(error, "stderr", None),
                    partial=isinstance(error, subprocess.TimeoutExpired))
                raise VisualBackendError("Codex visual request failed or timed out", metadata=metadata) from error
            metadata["latency_seconds"] = round(time.monotonic() - started, 3)
            metadata["cli_exit_code"] = result.returncode
            metadata["event_stream_sha256"] = _sha(_cli_bytes(result.stdout))
            if result.returncode:
                metadata["cli_failure"] = _cli_failure("nonzero_exit", result.stdout, result.stderr)
                raise VisualBackendError(f"Codex visual request failed (exit {result.returncode})", metadata=metadata)
            phase = "event_stream"
            try:
                stdout = _cli_bytes(result.stdout).decode("utf-8")
                if len(_cli_bytes(result.stdout)) > 2 * 1024 * 1024:
                    raise VisualProtocolError("CLI event stream is missing or too large")
                audit = audit_codex_events(stdout)
                metadata.update({key: value for key, value in audit.items() if key != "last_message"})
                phase = "final_answer"
                # Never recover an absent final answer from mixed logs or switch to text.
                answer = answer_path.read_text(encoding="utf-8")
                if not isinstance(audit["last_message"], str) or answer.strip() != audit["last_message"].strip():
                    raise VisualProtocolError("CLI final answer disagrees with its audited event stream")
                if staged_image.read_bytes() != image_bytes:
                    raise VisualProtocolError("attached screenshot changed during the decision")
                parsed = parse_decision(answer, image["width"], image["height"])
            except (OSError, UnicodeError) as error:
                metadata["cli_failure"] = _cli_failure("invalid_utf8" if phase == "event_stream" else "unreadable_final_answer", result.stdout, result.stderr, error=error)
                metadata.pop("events", None)
                raise VisualBackendError("Codex final answer or staged image is unreadable", metadata=metadata) from error
            except VisualProtocolError as error:
                context = error.metadata.get("cli_failure_context", {})
                kind = context.get("kind") or ("invalid_final_answer" if phase == "final_answer" else
                       "malformed_json" if "JSON" in str(error) else "invalid_event_stream")
                metadata["cli_failure"] = _cli_failure(kind, result.stdout, result.stderr, error=error)
                for field in ("event_type", "item_type"):
                    if field in context:
                        context[field] = _cli_diagnostic_text(context[field], 256)
                metadata["cli_failure"].update(context)
                metadata.pop("events", None)
                raise VisualProtocolError(str(error), metadata=metadata) from error
            if audit["reconnect_notices"]:
                metadata["cli_recovery"] = {
                    **_cli_failure("recovered_reconnect", result.stdout, result.stderr),
                    "notices": audit["reconnect_notices"],
                    "usage_scope": "completed_turn_only",
                    "aborted_sampling_usage": "unavailable"}
            metadata["answer_sha256"] = _sha(answer.encode("utf-8"))
            return VisualDecision(parsed.actions, parsed.advance_frames, parsed.intent, parsed.memory, metadata)
