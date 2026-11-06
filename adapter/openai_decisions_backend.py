"""OpenAI Decisions transport for the structured FTL actuator choices."""
from __future__ import annotations

import json
import os

from decision_backends import DecisionContractError, build_jev_request, render_jev_plan
from model_backend import Completion, post_json

OPENAI_DECISIONS_ENDPOINT = "https://api.openai.com/v1/decisions"
OPENAI_DECISIONS_MODEL = "gpt-6-luna"
OPENAI_DECISIONS_CONTRACT = "openai-decisions-actuator-choice-v1"
_PROVIDER = "openai-decisions"
_MAX_QUESTIONS = 400
_USAGE_FIELDS = {
    "input_tokens": (),
    "input_tokens_details": ("cached_tokens", "cache_write_tokens"),
    "output_tokens": (),
    "output_tokens_details": ("reasoning_tokens",),
    "total_tokens": (),
}


def _translate_request(actuator_request: dict) -> tuple[dict, dict]:
    state = actuator_request["state"]
    questions = []
    fixed_choices = {}
    for name, question in actuator_request["questions"].items():
        criteria = question["criteria"]
        if len(criteria) == 1:
            # A Choice needs at least two options. A beam endpoint can have one.
            fixed_choices[name] = next(iter(criteria))
            continue
        choices = [
            {"value": value,
             "description": description if isinstance(description, str) else json.dumps(description)}
            for value, description in criteria.items()
        ]
        questions.append({"type": "choice", "name": name,
                          "instructions": question["instructions"], "choices": choices})
    if len(questions) > _MAX_QUESTIONS:
        raise DecisionContractError(f"OpenAI Decisions supports at most {_MAX_QUESTIONS} questions per request")
    return {
        "model": actuator_request["model"],
        "input": [
            {"role": "developer", "content": [
                {"type": "input_text", "text": state["interface_and_goal"]},
                {"type": "input_text", "text": state["instructions"]},
            ]},
            {"role": "user", "content": [{"type": "input_text", "text": state["turn"]}]},
        ],
        "questions": questions,
    }, fixed_choices


def _probability(value) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1


def _token_usage(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    usage = {}
    for field, detail_fields in _USAGE_FIELDS.items():
        item = value.get(field)
        if detail_fields and isinstance(item, dict):
            usage[field] = {name: item[name] for name in detail_fields
                            if type(item.get(name)) is int and item[name] >= 0}
        elif not detail_fields and type(item) is int and item >= 0:
            usage[field] = item
    return usage


def _read_answer(answer, question: dict) -> dict:
    name = question["name"]

    def invalid(message: str, invariant: str) -> DecisionContractError:
        return DecisionContractError(f"OpenAI Decisions {message} for {name!r}",
                                     details={"question": name, "invariant": invariant})

    if not isinstance(answer, dict) or answer.get("name") != name:
        raise invalid("returned an unexpected answer name", "answer_name")
    if answer.get("type") == "refusal":
        raise invalid("refused to answer", "refusal")
    options = {choice["value"] for choice in question["choices"]}
    choice = answer.get("choice")
    if answer.get("type") != "choice" or not isinstance(choice, str) or choice not in options:
        raise invalid("returned an invalid choice", "choice_domain")
    confidence = answer.get("confidence")
    if not _probability(confidence):
        raise invalid("returned invalid confidence", "confidence_range")
    entries = answer.get("probabilities")
    if not isinstance(entries, list) or len(entries) != len(options):
        raise invalid("returned an invalid probability list", "probability_options")
    probabilities = {}
    for entry in entries:
        value = entry.get("value") if isinstance(entry, dict) else None
        if not isinstance(value, str) or value not in options or value in probabilities:
            raise invalid("returned a duplicate or unknown probability option", "probability_options")
        probability = entry.get("probability")
        if not _probability(probability):
            raise invalid("returned an invalid option probability", "probability_range")
        probabilities[value] = probability
    return {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": probabilities}


def openai_decisions_complete(system: str, user: str, model: str | None = None) -> Completion:
    """Select FTL actions through one typed request using the configured API key."""
    if model is None:
        model = OPENAI_DECISIONS_MODEL
    if model != OPENAI_DECISIONS_MODEL:
        raise DecisionContractError(f"OpenAI Decisions supports only {OPENAI_DECISIONS_MODEL}")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set for the OpenAI Decisions backend")
    try:
        actuator_request, actuators = build_jev_request(system, user, model)
    except DecisionContractError as error:
        raise DecisionContractError(str(error).replace("Jev", "OpenAI Decisions"),
                                    details=error.details) from None
    request, fixed_choices = _translate_request(actuator_request)
    data, trace = post_json(OPENAI_DECISIONS_ENDPOINT, request, key, provider=_PROVIDER,
                            attempts=1, allow_redirects=False)
    metadata = {
        **trace,
        "action_selection": "enumerated",
        "decision_contract": OPENAI_DECISIONS_CONTRACT,
        "resolved_model": data.get("model"),
        "usage": _token_usage(data.get("usage")),
        "question_count": len(request["questions"]),
        "option_count": sum(len(question["choices"]) for question in request["questions"]),
        "fixed_choices": fixed_choices,
    }
    # Redact any echoed credential from the provider's trace fields before recording them.
    for field in ("model", "resolved_model", "request_id", "client_request_id"):
        value = metadata.get(field)
        metadata[field] = value.replace(key, "[redacted]") if isinstance(value, str) else None
    try:
        answers = data.get("answers")
        if not isinstance(answers, list) or len(answers) != len(request["questions"]):
            raise DecisionContractError("OpenAI Decisions returned an unexpected answer count",
                                        details={"invariant": "answer_count"})
        selected = {
            question["name"]: _read_answer(answer, question)
            for question, answer in zip(request["questions"], answers, strict=True)
        }
        metadata["decision_choices"] = {name: answer["choice"] for name, answer in selected.items()}
        metadata["decision_confidence"] = {name: answer["confidence"] for name, answer in selected.items()}
        metadata["decision_probabilities"] = {name: answer["probabilities"] for name, answer in selected.items()}
        # These local singleton values satisfy the shared renderer's input shape.
        # They are recorded separately from the model's probability estimates.
        fixed_answers = {
            name: {"type": "choice", "choice": value, "confidence": 1, "probabilities": {value: 1}}
            for name, value in fixed_choices.items()
        }
        reply = render_jev_plan({"answers": {**selected, **fixed_answers}}, actuator_request, actuators,
                                require_highest_probability=False)
    except DecisionContractError as error:
        message = str(error)
        if message.startswith("Jev "):
            message = "OpenAI Decisions " + message.removeprefix("Jev ")
        failure = DecisionContractError(message, details=error.details)
        failure.metadata = {**metadata, "response_status": "contract_error",
                            "contract_error": {"message": message, **error.details}}
        raise failure from None
    return Completion(reply, metadata)
