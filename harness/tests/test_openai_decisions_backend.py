"""Offline tests for the OpenAI Decisions wire and actuator contracts."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.response import addinfourl

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import model_backend  # noqa: E402
import openai_decisions_backend as decisions  # noqa: E402
from decision_backends import DecisionContractError  # noqa: E402

KEY = "sk-test-openai-decisions"
USAGE = {
    "input_tokens": 345,
    "input_tokens_details": {"cached_tokens": 150, "cache_write_tokens": 0},
    "output_tokens": 0,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 345,
}


def turn(observation: dict) -> str:
    return "Recent actions: none.\n\nOBSERVATION:\n" + json.dumps(observation) + "\n\nDecide your plan."


def response_for(request: dict, selections: dict | None = None) -> dict:
    selections = selections or {}
    answers = []
    for question in request["questions"]:
        name = question["name"]
        options = [item["value"] for item in question["choices"]]
        choice = selections.get(name, "150" if name == "advance" else "hold")
        answers.append({
            "name": name, "type": "choice", "choice": choice, "confidence": 0.93,
            "probabilities": [{"value": option, "probability": int(option == choice)}
                              for option in reversed(options)],
        })
    return {"answers": answers, "model": "gpt-6-luna", "usage": USAGE}


def test_wire_request_renders_choice_and_preserves_trace(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", f" {KEY} ")
    user = turn({"event": {"choices": [{"index": 4, "text": "Offer fuel"},
                                      {"index": 7, "text": "Unavailable", "disabled": True}]}})
    requests = []

    def urlopen(request, *, timeout):
        body = json.loads(request.data)
        requests.append(body)
        assert request.full_url == "https://api.openai.com/v1/decisions"
        assert request.get_method() == "POST"
        assert request.get_header("Authorization") == f"Bearer {KEY}"
        assert request.get_header("X-client-request-id")
        data = response_for(body, {"event": "event_4", "advance": "260"})
        data["usage"] = {**USAGE, "unexpected": KEY}
        response = io.BytesIO(json.dumps(data).encode())
        response.headers = {"x-request-id": "req-openai-1"}
        return response

    monkeypatch.setattr(model_backend.urllib.request, "build_opener", lambda *handlers: SimpleNamespace(open=urlopen))
    reply = decisions.openai_decisions_complete("Keep the ship alive.", user)
    assert reply == "ACTION:\n  event 4\n  advance 260"
    (body,) = requests
    assert set(body) == {"model", "input", "questions"}
    assert body["model"] == "gpt-6-luna"
    developer, player = body["input"]
    assert developer["role"] == "developer"
    assert developer["content"][0] == {"type": "input_text", "text": "Keep the ship alive."}
    assert player == {"role": "user", "content": [{"type": "input_text", "text": user}]}
    event, advance = body["questions"]
    assert event["name"] == "event"
    assert event["type"] == "choice"
    assert event["instructions"]
    assert [item["value"] for item in event["choices"]] == ["hold", "event_4"]
    assert json.loads(event["choices"][1]["description"])["event_choice"]["text"] == "Offer fuel"
    assert advance["name"] == "advance"
    assert reply.metadata["provider"] == "openai-decisions"
    assert reply.metadata["decision_contract"] == "openai-decisions-actuator-choice-v1"
    assert reply.metadata["request_id"] == "req-openai-1"
    assert reply.metadata["client_request_id"]
    assert reply.metadata["resolved_model"] == "gpt-6-luna"
    assert reply.metadata["usage"] == USAGE
    assert reply.metadata["attempts"] == 1
    assert reply.metadata["question_count"] == 2
    assert reply.metadata["option_count"] == 8
    assert reply.metadata["decision_choices"] == {"event": "event_4", "advance": "260"}
    assert reply.metadata["decision_confidence"]["event"] == 0.93
    assert reply.metadata["decision_probabilities"]["event"] == {"hold": 0, "event_4": 1}
    assert KEY not in json.dumps({"request": body, "metadata": reply.metadata})


def test_single_room_beam_endpoints_are_fixed_without_claiming_model_confidence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    observation = {
        "weapons": [{"slot": 3, "type": "BEAM"}],
        "enemy": {"hostile": True, "targetable": True, "rooms": [{"room_id": 9}]},
    }

    def post(endpoint, request, key, **kwargs):
        assert [question["name"] for question in request["questions"]] == ["beam_3", "concession", "advance"]
        assert all(len(question["choices"]) >= 2 for question in request["questions"])
        return response_for(request, {"beam_3": "fire"}), {}

    monkeypatch.setattr(decisions, "post_json", post)
    reply = decisions.openai_decisions_complete("FTL", turn(observation))
    assert reply == "ACTION:\n  beam 3 9 9\n  advance 150"
    assert reply.metadata["fixed_choices"] == {"beam_3_start": "room_9", "beam_3_end": "room_9"}
    assert set(reply.metadata["decision_probabilities"]) == {"beam_3", "concession", "advance"}


@pytest.mark.parametrize(("edit", "invariant"), [
    (lambda answers: answers.pop(), "answer_count"),
    (lambda answers: answers.append(answers[-1]), "answer_count"),
    (lambda answers: answers.reverse(), "answer_name"),
    (lambda answers: answers.__setitem__(0, {"name": "concession", "type": "refusal", "reason": KEY}), "refusal"),
    (lambda answers: answers[0].update(type="score"), "choice_domain"),
    (lambda answers: answers[0].update(choice=True), "choice_domain"),
    (lambda answers: answers[0].update(choice=KEY), "choice_domain"),
    (lambda answers: answers[0].update(confidence=float("nan")), "confidence_range"),
    (lambda answers: answers[0]["probabilities"][0].update(value=KEY), "probability_options"),
    (lambda answers: answers[0]["probabilities"][0].update(value="hold"), "probability_options"),
    (lambda answers: answers[0]["probabilities"][0].update(probability=False), "probability_range"),
    (lambda answers: answers[0]["probabilities"][0].update(probability=0.5), "probability_sum"),
])
def test_invalid_wire_answers_fail_closed_with_trace(monkeypatch, edit, invariant):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)

    def post(endpoint, request, key, **kwargs):
        response = response_for(request)
        edit(response["answers"])
        return response, {"request_id": "req-openai-2"}

    monkeypatch.setattr(decisions, "post_json", post)
    with pytest.raises(DecisionContractError, match="OpenAI Decisions") as raised:
        decisions.openai_decisions_complete("FTL", turn({}))
    assert raised.value.details["invariant"] == invariant
    assert raised.value.metadata["response_status"] == "contract_error"
    assert raised.value.metadata["request_id"] == "req-openai-2"
    assert raised.value.metadata["usage"] == USAGE
    assert KEY not in json.dumps(raised.value.metadata)


def test_renders_the_returned_choice_even_when_another_option_has_higher_probability(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    observation = {"event": {"choices": [{"index": 4, "text": "Offer fuel"}]}}

    def post(endpoint, request, key, **kwargs):
        response = response_for(request, {"event": "event_4"})
        response["answers"][0]["probabilities"] = [
            {"value": "hold", "probability": 0.6},
            {"value": "event_4", "probability": 0.4},
        ]
        return response, {}

    monkeypatch.setattr(decisions, "post_json", post)
    reply = decisions.openai_decisions_complete("FTL", turn(observation))
    assert reply == "ACTION:\n  event 4\n  advance 150"
    assert reply.metadata["decision_probabilities"]["event"] == {"hold": 0.6, "event_4": 0.4}


def test_shared_plan_rules_reject_concession_with_other_actions(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    observation = {"systems": [{"id": 3, "power": "1/3"}]}

    def post(endpoint, request, key, **kwargs):
        return response_for(request, {"concession": "giveup", "power_3": "level_2"}), {}

    monkeypatch.setattr(decisions, "post_json", post)
    with pytest.raises(DecisionContractError, match="concession together with other actions") as raised:
        decisions.openai_decisions_complete("FTL", turn(observation))
    assert raised.value.metadata["decision_choices"]["concession"] == "giveup"


def test_unsupported_model_missing_key_and_overlarge_request_stay_offline(monkeypatch):
    def unexpected_post(*args, **kwargs):
        pytest.fail("Should have failed before making a request")

    monkeypatch.setattr(decisions, "post_json", unexpected_post)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(DecisionContractError, match="supports only gpt-6-luna"):
        decisions.openai_decisions_complete("FTL", turn({}), "gpt-6.1-sol")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        decisions.openai_decisions_complete("FTL", turn({}))
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    observation = {"systems": [{"id": index, "power": "0/1"} for index in range(400, 801)]}
    with pytest.raises(DecisionContractError, match="at most 400 questions"):
        decisions.openai_decisions_complete("FTL", turn(observation))
    with pytest.raises(DecisionContractError, match="requires a turn containing OBSERVATION JSON"):
        decisions.openai_decisions_complete("Reflect on the last game.", "Write notes for next run.")


def test_http_failure_is_redacted_and_not_retried(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    attempts = []

    def urlopen(request, *, timeout):
        attempts.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {},
                                     io.BytesIO(f"echoed credential: {KEY}".encode()))

    monkeypatch.setattr(model_backend.urllib.request, "build_opener", lambda *handlers: SimpleNamespace(open=urlopen))
    with pytest.raises(RuntimeError, match="openai-decisions API HTTP 503") as raised:
        decisions.openai_decisions_complete("FTL", turn({}))
    assert KEY not in str(raised.value)
    assert len(attempts) == 1


def test_cross_host_redirect_does_not_send_a_second_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    sent = []
    urllib_request = model_backend.urllib.request
    build_opener = urllib_request.build_opener

    def https_open(self, request):
        sent.append((request.full_url, request.get_header("Authorization")))
        headers = Message()
        headers["Location"] = f"https://other.invalid/{KEY}"
        response = addinfourl(io.BytesIO(b""), headers, request.full_url, 302)
        response.msg = "Found"
        return response

    monkeypatch.setattr(urllib_request.HTTPSHandler, "https_open", https_open)
    monkeypatch.setattr(urllib_request, "build_opener",
                        lambda *handlers: build_opener(urllib_request.ProxyHandler({}), *handlers))
    with pytest.raises(RuntimeError, match="HTTP 302: redirects are disabled") as raised:
        decisions.openai_decisions_complete("FTL", turn({}))
    assert sent == [("https://api.openai.com/v1/decisions", f"Bearer {KEY}")]
    assert KEY not in str(raised.value)


def test_agent_rejects_unsupported_decisions_model_before_session_start():
    from llm_agent import make_llm_agent
    with pytest.raises(ValueError, match="only gpt-6-luna"):
        make_llm_agent(backend="openai-decisions", model="gpt-6.1-sol")
