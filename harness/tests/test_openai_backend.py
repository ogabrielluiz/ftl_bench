from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import openai_backend


def response(plan):
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(plan)}]}]}


def test_openai_multi_action_plan_uses_strict_schema_and_trace_metadata(monkeypatch):
    captured = {}
    def post(endpoint, body, key, **kwargs):
        captured.update(endpoint=endpoint, body=body)
        return response({"reason": "Release volley", "commands": [
            {"command": "fire", "args": ["0", "3"]},
            {"command": "fire", "args": ["1", "3"]}], "advance": 150}), {"usage": {"total_tokens": 12}}
    monkeypatch.setattr(openai_backend, "post_json", post)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret")
    reply = openai_backend.openai_complete("manual", "observation", "test-model")
    assert "fire 0 3\n  fire 1 3" in reply
    assert reply.metadata["usage"]["total_tokens"] == 12
    assert captured["body"]["text"]["format"]["strict"] is True
    assert captured["body"]["store"] is False


@pytest.mark.parametrize("data", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
    response({"reason": "x", "commands": [{"command": "fire", "args": ["0\ngiveup", "3"]}], "advance": 150}),
    response({"reason": "x", "commands": [], "advance": -1}),
])
def test_unusable_openai_output_is_an_explicit_failure(monkeypatch, data):
    monkeypatch.setattr(openai_backend, "post_json", lambda *a, **k: (data, {}))
    with pytest.raises(RuntimeError):
        openai_backend.openai_complete("manual", "observation", "test-model")
