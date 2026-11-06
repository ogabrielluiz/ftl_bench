"""One audited, screenshot-bound Choice request per visual decision stage."""
from __future__ import annotations

import base64
from copy import deepcopy
from functools import partial
import hashlib
from http.client import HTTPConnection, HTTPException, HTTPSConnection
import io
import json
import math
import os
from pathlib import Path
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import uuid4

from visual_agent import VisualBackendError


_ENDPOINTS = {
    "jev": ("typesafe", "https://api.typesafe.ai/v1/systemone"),
    "openai-decisions": ("openai-decisions", "https://api.openai.com/v1/decisions"),
}
_KEY_NAMES = {
    "jev": ("TYPESAFE_API_KEY", "JEV_API_KEY"),
    "openai-decisions": ("OPENAI_API_KEY",),
}
_MAX_RESPONSE_BYTES = 1 << 20
_SUM_TOLERANCE = 1e-3
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IMAGE_FIELDS = ("path", "sha256", "capture_id", "frame_id", "action_seq", "width", "height")
_RESPONSE_HEADERS = ("x-request-id", "request-id", "x-typesafe-request-id", "content-type", "content-encoding")


class _Reject(ValueError):
    """A fixed, safe failure code suitable for saved evidence."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _remaining(deadline: float) -> float:
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("Visual HTTP deadline expired")
    return seconds


class _DeadlineReader(io.RawIOBase):
    def __init__(self, sock: socket.socket, deadline: float):
        self.sock = sock
        self.deadline = deadline
        # Retain the socket descriptor until HTTPResponse closes its file.
        self.raw = sock.makefile("rb", buffering=0)

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(_remaining(self.deadline))
        return self.raw.readinto(buffer)

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class _DeadlineSocket:
    def __init__(self, sock: socket.socket, deadline: float):
        self.sock = sock
        self.deadline = deadline

    def makefile(self, mode):
        if mode != "rb":
            raise ValueError("Unexpected HTTP socket file mode")
        return io.BufferedReader(_DeadlineReader(self.sock, self.deadline))

    def sendall(self, data):
        self.sock.settimeout(_remaining(self.deadline))
        self.sock.sendall(data)

    def __getattr__(self, name):
        return getattr(self.sock, name)


def _connect(deadline: float, address, _timeout, source_address=None):
    _remaining(deadline)
    # The OS's synchronous resolver cannot be interrupted by socket timeouts.
    try:
        addresses = socket.getaddrinfo(*address, type=socket.SOCK_STREAM)
    except OSError:
        _remaining(deadline)
        raise
    _remaining(deadline)
    last_error = OSError("No socket addresses found")
    for family, kind, protocol, _, target in addresses:
        sock = socket.socket(family, kind, protocol)
        try:
            if source_address:
                sock.bind(source_address)
            sock.settimeout(_remaining(deadline))
            sock.connect(target)
        except OSError as error:
            sock.close()
            last_error = error
        except BaseException:
            sock.close()
            raise
        else:
            return _DeadlineSocket(sock, deadline)
    raise last_error


class _DeadlineConnection:
    def __init__(self, host, *, deadline: float, **kwargs):
        super().__init__(host, **kwargs)
        self.deadline = deadline
        self._create_connection = partial(_connect, deadline)


class _DeadlineHTTPConnection(_DeadlineConnection, HTTPConnection):
    pass


class _DeadlineHTTPSConnection(_DeadlineConnection, HTTPSConnection):
    def connect(self):
        # The base HTTP method also establishes a configured HTTPS proxy tunnel.
        HTTPConnection.connect(self)
        sock = self.sock.sock
        sock.settimeout(_remaining(self.deadline))
        tls = self._context.wrap_socket(sock, server_hostname=self._tunnel_host or self.host)
        self.sock = _DeadlineSocket(tls, self.deadline)


class _DeadlineHTTPHandler(HTTPHandler):
    def __init__(self, deadline: float):
        super().__init__()
        self.deadline = deadline

    def http_open(self, req):
        return self.do_open(partial(_DeadlineHTTPConnection, deadline=self.deadline), req)


class _DeadlineHTTPSHandler(HTTPSHandler):
    def __init__(self, deadline: float):
        super().__init__()
        self.deadline = deadline

    def https_open(self, req):
        return self.do_open(partial(_DeadlineHTTPSConnection, deadline=self.deadline), req, context=self._context)


def _read_body(response, body: bytearray, deadline: float) -> None:
    while len(body) <= _MAX_RESPONSE_BYTES:
        _remaining(deadline)
        chunk = response.read1(_MAX_RESPONSE_BYTES + 1 - len(body))
        if not chunk:
            break
        body.extend(chunk)
    _remaining(deadline)


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _write(path: Path, value) -> None:
    _write_bytes(path, _json_bytes(value) + b"\n")


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wire_body(saved: dict, image_bytes: bytes) -> bytes:
    body = deepcopy(saved["body"])
    digest = _digest(image_bytes)
    if not image_bytes.startswith(_PNG_SIGNATURE) or saved["image"]["sha256"] != digest:
        raise ValueError("Archived PNG bytes do not match the request image identity")
    marker = {"archived_png_sha256": digest}
    encoded = base64.b64encode(image_bytes).decode("ascii")
    if saved["backend"] == "jev":
        asset = body["assets"][body["state"]["screenshot"]]
        if asset["data_base64"] != marker:
            raise ValueError("Jev image placeholder is inconsistent")
        asset["data_base64"] = encoded
    elif saved["backend"] == "openai-decisions":
        part = body["input"][0]["content"][1]
        if part["image_url"] != marker:
            raise ValueError("OpenAI image placeholder is inconsistent")
        part["image_url"] = "data:image/png;base64," + encoded
    else:
        raise ValueError("Unknown visual decision backend")
    return _json_bytes(body)


def reconstruct_request(savedrequest: dict, imagebytes: bytes) -> bytes:
    """Recover and verify the exact POST body using the archived decision image."""
    try:
        wire = _wire_body(savedrequest, imagebytes)
        if savedrequest["wire_sha256"] != _digest(wire) or savedrequest["wire_bytes"] != len(wire):
            raise ValueError("Reconstructed visual request does not match the wire identity")
    except (AttributeError, IndexError, KeyError, TypeError) as error:
        raise ValueError("Malformed visual request evidence") from error
    return wire


def _request_record(backend: str, model: str, context: str, image: dict,
                    question: dict, client_id: str) -> dict:
    name, instructions, choices = (question.get(field) for field in ("name", "instructions", "choices"))
    if not isinstance(name, str) or not name or not isinstance(instructions, str):
        raise _Reject("invalid_question")
    if not isinstance(choices, dict) or not 2 <= len(choices) <= 255 or any(
        not isinstance(value, str) or not isinstance(description, str)
        for value, description in choices.items()
    ):
        raise _Reject("invalid_choice_options")
    if not isinstance(context, str):
        raise _Reject("invalid_context")
    marker = {"archived_png_sha256": image["sha256"]}
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity", "X-Client-Request-Id": client_id}
    if backend == "jev":
        ref = str(uuid4())
        headers["TypeSafe-Danger-Zone-Images"] = "true"
        body = {
            "model": model,
            "state": {"context": context, "screenshot": ref},
            "questions": {name: {"type": "choice", "instructions": instructions, "criteria": choices}},
            "assets": {ref: {"type": "image", "format": "png", "data_base64": marker}},
        }
    else:
        body = {
            "model": model,
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": context},
                {"type": "input_image", "image_url": marker},
            ]}],
            "questions": [{"type": "choice", "name": name, "instructions": instructions,
                           "choices": [{"value": value, "description": description}
                                       for value, description in choices.items()]}],
        }
    provider, endpoint = _ENDPOINTS[backend]
    return {"backend": backend, "provider": provider, "endpoint": endpoint,
            "client_request_id": client_id, "headers": headers, "image": image, "body": body}


def _unique_object(pairs):
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise _Reject("duplicate_response_key")
        obj[name] = value
    return obj


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise _Reject("nonfinite_response_number")
    return number


def _decode_response(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_float=_finite_float, parse_constant=_finite_float)
    except _Reject:
        raise
    except (ValueError, RecursionError):
        raise _Reject("invalid_response_json") from None


def _probability(value) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1


def _read_choice(data: dict, backend: str, question: dict) -> dict:
    name = question["name"]
    options = question["choices"]
    answers = data.get("answers")
    if backend == "jev":
        if not isinstance(answers, dict) or answers.keys() != {name}:
            raise _Reject("unexpected_answer_names")
        answer = answers[name]
    else:
        if not isinstance(answers, list) or len(answers) != 1 or not isinstance(answers[0], dict):
            raise _Reject("unexpected_answer_count")
        answer = answers[0]
        if answer.get("name") != name:
            raise _Reject("unexpected_answer_names")
    if isinstance(answer, dict) and answer.get("type") == "refusal":
        raise _Reject("provider_refusal")
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise _Reject("unexpected_answer_type")
    choice, confidence = answer.get("choice"), answer.get("confidence")
    if not isinstance(choice, str) or choice not in options or not _probability(confidence):
        raise _Reject("invalid_choice_or_confidence")
    probabilities = answer.get("probabilities")
    if backend == "openai-decisions":
        if not isinstance(probabilities, list) or len(probabilities) != len(options):
            raise _Reject("unexpected_probability_options")
        entries, probabilities = probabilities, {}
        for entry in entries:
            value = entry.get("value") if isinstance(entry, dict) else None
            if not isinstance(value, str) or value in probabilities:
                raise _Reject("unexpected_probability_options")
            probabilities[value] = entry.get("probability")
    if not isinstance(probabilities, dict) or probabilities.keys() != options.keys():
        raise _Reject("unexpected_probability_options")
    if not all(_probability(value) for value in probabilities.values()):
        raise _Reject("invalid_option_probability")
    if not math.isclose(math.fsum(probabilities.values()), 1.0, rel_tol=0, abs_tol=_SUM_TOLERANCE):
        raise _Reject("invalid_probability_sum")
    # TypeSafe specifies that Choice returns a highest-probability option.
    if backend == "jev" and probabilities[choice] < max(probabilities.values()):
        raise _Reject("jev_choice_is_not_maximum")
    ranked = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))[:5]
    return {"choice": choice, "confidence": confidence, "selected_probability": probabilities[choice],
            "top_choices": [{"value": value, "probability": probability} for value, probability in ranked],
            "option_count": len(options)}


def _response_metadata(data) -> dict:
    if not isinstance(data, dict) or "error" in data or "refusal" in data:
        raise _Reject("invalid_response_object")
    model = data.get("model")
    if model is not None and (not isinstance(model, str) or not model):
        raise _Reject("invalid_reported_model")
    usage = data.get("usage")
    if usage is not None and not isinstance(usage, dict):
        raise _Reject("invalid_reported_usage")
    return {"model": model, "usage": usage}


def parse_choice_response(backend: str, model: str, question: dict, data: dict | bytes) -> dict:
    """Validate a provider response for offline replay of a known request."""
    if backend not in _ENDPOINTS or (backend == "openai-decisions" and model != "gpt-6-luna"):
        raise ValueError("Unsupported visual decision backend or model")
    if isinstance(data, bytes):
        if len(data) > _MAX_RESPONSE_BYTES:
            raise ValueError("Visual decision response exceeds the size limit")
        data = _decode_response(data)
    _json_bytes(data)  # Also reject non-finite numbers supplied in already decoded data.
    return {**_response_metadata(data), **_read_choice(data, backend, question)}


def _response_headers(headers, key: str) -> dict:
    allowed = {}
    for name in _RESPONSE_HEADERS:
        value = headers.get(name)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:;/= -]{1,256}", value) and key not in value:
            allowed[name] = value
    return allowed


def _note_response(call: dict, status: int, headers, key: str) -> None:
    safe = _response_headers(headers, key)
    call.update(response_received=True, http_status=status, response_headers=safe,
                request_id=safe.get("x-request-id") or safe.get("request-id") or safe.get("x-typesafe-request-id"))


def _credential_pattern(key: str) -> re.Pattern[bytes]:
    # Match literal credentials as well as individual JSON and URL escapes.
    parts = []
    for char in key:
        variants = {char.encode(), _json_bytes(char)[1:-1], f"\\u{ord(char):04x}".encode(),
                    f"%{ord(char):02x}".encode()}
        parts.append(b"(?:" + b"|".join(re.escape(part) for part in variants) + b")")
    return re.compile(b"".join(parts), re.I)


def _retain_response(path: Path, raw: bytes, call: dict, *, redactions: int = 0) -> None:
    retained = raw[:_MAX_RESPONSE_BYTES]
    _write_bytes(path, retained)
    call.update(response_artifact=path.name, retained_response_sha256=_digest(retained),
                retained_response_bytes=len(retained), response_redactions=redactions)


def _note_partial_response(call: dict, prefix: bytearray) -> bytes:
    raw = bytes(prefix)
    call.update(response_sha256=_digest(raw), response_bytes=len(raw), response_partial=True,
                response_truncated=len(raw) > _MAX_RESPONSE_BYTES)
    return raw


def _retain_redacted_response(path: Path, raw: bytes, call: dict, credential: re.Pattern[bytes]) -> None:
    redacted, count = credential.subn(b"[REDACTED]", raw[:_MAX_RESPONSE_BYTES])
    _retain_response(path, redacted, call, redactions=count)


def request_choice(*, backend: str, model: str, context: str, image_bytes: bytes, image: dict,
                   question: dict, audit_path: Path, timeout: float) -> tuple[str, dict]:
    """Submit a bounded single-attempt Choice and preserve its replay evidence."""
    started = time.monotonic()
    audit_path = Path(audit_path)
    call = {"artifact": audit_path.as_posix(), "provider": None, "stage": None,
            "requested_model": None, "model": None, "usage": None, "attempts": 0,
            "request_id": None, "client_request_id": str(uuid4()), "response_received": False,
            "status": "error", "latency_seconds": None}
    raw = None
    body_prefix = bytearray()
    encoded = False
    interrupted = False
    try:
        audit_path.mkdir(parents=True)
    except OSError:
        raise VisualBackendError("Visual decision could not create its audit directory",
                                 metadata={"api_call": call}) from None

    try:
        if backend not in _ENDPOINTS:
            raise _Reject("unsupported_backend")
        call["provider"] = _ENDPOINTS[backend][0]
        key = next((value for name in _KEY_NAMES[backend] if (value := os.environ.get(name, "").strip())), "")
        if not isinstance(model, str) or not model or not model.isascii() or (key and key in model):
            raise _Reject("invalid_model")
        call["requested_model"] = model
        if backend == "openai-decisions" and model != "gpt-6-luna":
            raise _Reject("unsupported_openai_decisions_model")
        if not isinstance(question, dict):
            raise _Reject("invalid_question")
        name = question.get("name")
        if isinstance(name, str) and name.isascii() and (not key or key not in name):
            call["stage"] = name
        if type(timeout) not in (int, float) or not 0 < timeout < math.inf:
            raise _Reject("invalid_timeout")
        if not isinstance(image_bytes, bytes) or not image_bytes.startswith(_PNG_SIGNATURE) or not isinstance(image, dict):
            raise _Reject("invalid_png")
        image = {field: image[field] for field in _IMAGE_FIELDS if field in image}
        if image.get("sha256") != _digest(image_bytes):
            raise _Reject("image_sha256_mismatch")
        saved = _request_record(backend, model, context, image, question, call["client_request_id"])
        wire = _wire_body(saved, image_bytes)
        saved.update(wire_sha256=_digest(wire), wire_bytes=len(wire))
        if key and _json_bytes(key)[1:-1] in _json_bytes(saved):
            raise _Reject("credential_in_request_evidence")
        call["stage"] = name
        _write(audit_path / "request.json", saved)
        if not 1 <= len(key) <= 1024 or not key.isascii() or not key.isprintable() or any(char.isspace() for char in key):
            raise _Reject("api_key_missing_or_invalid")

        credential = _credential_pattern(key)
        request = Request(saved["endpoint"], data=wire, method="POST",
                          headers={**saved["headers"], "Authorization": f"Bearer {key}"})
        started = time.monotonic()
        deadline = started + timeout
        opener = build_opener(_NoRedirect(), _DeadlineHTTPHandler(deadline), _DeadlineHTTPSHandler(deadline))
        call["attempts"] = 1
        try:
            with opener.open(request, timeout=timeout) as response:
                _note_response(call, response.status, response.headers, key)
                encoded = response.headers.get("content-encoding", "identity").strip().lower() != "identity"
                declared_length = response.headers.get("content-length")
                _read_body(response, body_prefix, deadline)
        except HTTPError as error:
            with error:
                _note_response(call, error.code, error.headers, key)
                encoded = error.headers.get("content-encoding", "identity").strip().lower() != "identity"
                _read_body(error, body_prefix, deadline)
        finally:
            call["latency_seconds"] = round(time.monotonic() - started, 6)

        raw = bytes(body_prefix)
        truncated = len(raw) > _MAX_RESPONSE_BYTES
        call.update(response_sha256=_digest(raw), response_bytes=len(raw), response_truncated=truncated)
        if encoded:
            raise _Reject("unsupported_response_encoding")
        if call["http_status"] != 200:
            raise _Reject("http_error")
        call["status"] = "invalid_response"
        if truncated:
            raise _Reject("response_size_limit")
        if declared_length is not None and (not re.fullmatch(r"[0-9]{1,16}", declared_length)
                                            or int(declared_length) != len(raw)):
            raise _Reject("response_length_mismatch")
        try:
            data = _decode_response(raw)
            safe = _json_bytes(data)
        except _Reject:
            raise
        except (ValueError, UnicodeError, RecursionError):
            raise _Reject("invalid_response_json") from None
        redacted, count = credential.subn(b"[REDACTED]", safe)
        if count:
            # The decoded form also catches a percent escape whose percent
            # sign was itself JSON escaped in the wire bytes.
            _retain_response(audit_path / "response.bin", redacted, call, redactions=count)
            raise _Reject("credential_in_response")
        if credential.search(raw):
            raise _Reject("credential_in_response")
        _retain_response(audit_path / "response.json", raw, call)
        call.update(_response_metadata(data))
        result = _read_choice(data, backend, question)
        call.update(result, status="completed")
        return result["choice"], call
    except (OSError, HTTPException, ValueError, TypeError, RecursionError) as error:
        if isinstance(error, _Reject):
            code = str(error)
        elif call["attempts"] and isinstance(error.reason if isinstance(error, URLError) else error, TimeoutError):
            code = "request_deadline_exceeded"
        elif isinstance(error, (OSError, HTTPException)):
            code = "transport_or_audit_error"
        else:
            code = "invalid_request_evidence"
        if raw is None and call["response_received"]:
            raw = _note_partial_response(call, body_prefix)
        call["error_code"] = code
        try:
            if raw is not None and not encoded and "response_artifact" not in call:
                _retain_redacted_response(audit_path / "response.bin", raw, call, credential)
            _write(audit_path / "safeerror.json", {"error_code": code, "http_status": call.get("http_status"),
                                                   "response_received": call["response_received"]})
        except OSError:
            raise VisualBackendError("Visual decision could not save its failure evidence",
                                     metadata={"api_call": call}) from None
        raise VisualBackendError(f"Visual decision failed ({code})", metadata={"api_call": call}) from None
    except KeyboardInterrupt as error:
        interrupted = True
        call.update(status="error", error_code="operator_interrupted")
        error.metadata = {**getattr(error, "metadata", {}), "api_call": call}
        if raw is None and call["response_received"]:
            raw = _note_partial_response(call, body_prefix)
        if raw is not None and not encoded and "response_artifact" not in call:
            try:
                _retain_redacted_response(audit_path / "response.bin", raw, call, credential)
            except OSError:
                call["audit_error_code"] = "interrupted_response_audit_write_failed"
        try:
            _write(audit_path / "safeerror.json", {"error_code": call["error_code"], "http_status": call.get("http_status"),
                                                   "response_received": call["response_received"]})
        except OSError:
            call["audit_error_code"] = "interrupted_error_audit_write_failed"
        raise
    finally:
        if call["latency_seconds"] is None:
            call["latency_seconds"] = round(time.monotonic() - started, 6)
        try:
            _write(audit_path / "call.json", call)
        except OSError:
            if interrupted:
                call["audit_error_code"] = "call_audit_write_failed"
            else:
                call.update(status="error", error_code="call_audit_write_failed")
                raise VisualBackendError("Visual decision could not save its call evidence",
                                         metadata={"api_call": call}) from None
