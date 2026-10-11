"""OpenAI Responses API with a strict JSON action-plan schema.

Docs: https://developers.openai.com/api/docs/guides/structured-outputs
This is the public Responses API; it does not emulate the preview Decisions API.
"""
from __future__ import annotations

import json
import os

from model_backend import Completion, post_json

COMMANDS = ["power", "fire", "beam", "jump", "event", "leave", "crew", "buy", "sell", "closestore",
            "upgrade", "reactor", "waitfuel", "distress", "cloak", "doors", "mindcontrol", "battery", "hack", "drone",
            "dronerecall", "board", "recall", "giveup"]
PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "reason": {"type": "string"},
        "commands": {"type": "array", "maxItems": 12, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"command": {"type": "string", "enum": COMMANDS},
                           "args": {"type": "array", "items": {"type": "string"}}},
            "required": ["command", "args"]}},
        "advance": {"type": "integer", "minimum": 20, "maximum": 1200},
    }, "required": ["reason", "commands", "advance"],
}


def openai_complete(system: str, user: str, model: str | None) -> Completion:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    body = {"model": model or os.environ.get("OPENAI_MODEL", "gpt-6.1-sol"),
            "instructions": system + "\nReturn the requested structured action plan.",
            "input": user, "store": False,
            "text": {"format": {"type": "json_schema", "name": "ftl_action_plan",
                                 "strict": True, "schema": PLAN_SCHEMA}}}
    effort = os.environ.get("OPENAI_REASONING_EFFORT")
    if effort:
        body["reasoning"] = {"effort": effort}
    data, metadata = post_json("https://api.openai.com/v1/responses", body, key, provider="openai")
    if data.get("status") not in {None, "completed"}:
        raise RuntimeError(f"OpenAI response did not complete: {data.get('status')}")
    chunks = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "refusal":
                raise RuntimeError("OpenAI declined to produce an action plan")
            if part.get("type") == "output_text":
                chunks.append(part.get("text", ""))
    try:
        plan = json.loads("".join(chunks))
        commands, advance, reason = plan["commands"], plan["advance"], plan["reason"]
        if (not isinstance(commands, list) or len(commands) > 12
                or type(advance) is not int or not 20 <= advance <= 1200
                or not isinstance(reason, str)):
            raise ValueError("invalid plan")
        lines = []
        for command in commands:
            verb, args = command["command"], command["args"]
            if verb not in COMMANDS or not isinstance(args, list) or any(not isinstance(a, str) or any(c.isspace() for c in a) for a in args):
                raise ValueError("invalid command")
            lines.append(" ".join([verb, *args]))
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("OpenAI returned an invalid structured action plan") from error
    metadata["action_selection"] = "structured_plan"
    return Completion(reason.replace("\n", " ") + "\nACTION:\n  "
                      + "\n  ".join([*lines, f"advance {advance}"]), metadata)
