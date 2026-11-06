"""The visual Choice boundary preserves wire evidence without live API calls."""
from __future__ import annotations

import base64
from email.message import Message
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import ssl
import sys
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import visual_decision_api as api  # noqa: E402


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX1sAAAAASUVORK5CYII="
)
IMAGE = {"path": "screens/frame.png", "capture_id": "capture-1", "sha256": hashlib.sha256(PNG).hexdigest()}
CONTEXT = "Visible state from FTL. Previous input opened the map."
QUESTION = {"name": "region", "instructions": "Which control is visible?",
            "choices": {"map": "Map button", "hold": "No visible control"}}
KEY = "visual-api-test-secret-a877b"


class Reply(io.BytesIO):
    status = 200

    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = Message()
        for name, value in (headers or {"x-request-id": "server-123"}).items():
            self.headers[name] = value
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)

    read1 = read


class OneShot:
    def __init__(self, reply, stage):
        self.reply = reply
        self.stage = stage
        self.requests = []

    def open(self, request, *, timeout):
        assert (self.stage / "request.json").exists()
        assert not (self.stage / "call.json").exists()
        self.requests.append((request, timeout))
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply


def request(stage, backend="openai-decisions", **overrides):
    args = {"backend": backend, "model": "jev-1.14.0" if backend == "jev" else "gpt-6-luna",
            "context": CONTEXT, "image_bytes": PNG, "image": IMAGE,
            "question": QUESTION, "audit_path": stage, "timeout": 2.5}
    return api.request_choice(**(args | overrides))


def mocked(monkeypatch, stage, reply):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    opener = OneShot(reply, stage)
    monkeypatch.setattr(api, "build_opener", lambda *handlers: opener)
    return opener


def response(backend, choice="map", probabilities=None, name="region"):
    probabilities = probabilities or {"map": 0.75, "hold": 0.25}
    answer = {"type": "choice", "choice": choice, "confidence": 0.42, "probabilities": probabilities}
    if backend == "openai-decisions":
        answer["name"] = name
        answer["probabilities"] = [{"value": value, "probability": p} for value, p in probabilities.items()]
        answers = [answer]
    else:
        answers = {name: answer}
    return {"model": "model-reported-by-provider", "answers": answers,
            "usage": {"input_tokens": 57, "input_tokens_details": {"cached_tokens": 5}}}


def read_json(path):
    return json.loads(path.read_bytes())


@pytest.mark.parametrize("backend, endpoint", [
    ("jev", "https://api.typesafe.ai/v1/systemone"),
    ("openai-decisions", "https://api.openai.com/v1/decisions"),
])
def test_provider_wire_request_and_exact_replay(monkeypatch, tmp_path, backend, endpoint):
    stage = tmp_path / "first"
    # OpenAI's documented answer selects a supplied value, without an argmax guarantee.
    choice = "map" if backend == "jev" else "hold"
    payload = response(backend, choice=choice)
    raw = json.dumps(payload, indent=2).encode()
    reply = Reply(raw, {"x-request-id": "server-123", "set-cookie": KEY})
    opener = mocked(monkeypatch, stage, reply)
    selected, call = request(stage, backend)
    (wire, timeout), = opener.requests
    headers = {key.lower(): value for key, value in wire.header_items()}
    body = json.loads(wire.data)
    saved = read_json(stage / "request.json")
    assert wire.full_url == saved["endpoint"] == endpoint
    assert wire.get_method() == "POST" and timeout == 2.5
    assert headers["authorization"] == "Bearer " + KEY
    assert headers["x-client-request-id"] == call["client_request_id"] == saved["client_request_id"]
    assert saved["image"] == IMAGE
    assert api.reconstruct_request(saved, PNG) == wire.data
    assert saved["wire_sha256"] == hashlib.sha256(wire.data).hexdigest()
    assert saved["wire_bytes"] == len(wire.data)
    with pytest.raises(ValueError, match="PNG bytes"):
        api.reconstruct_request(saved, PNG + b"altered")
    with pytest.raises(ValueError, match="wire identity"):
        api.reconstruct_request(saved | {"wire_sha256": "f" * 64}, PNG)

    if backend == "jev":
        assert headers["typesafe-danger-zone-images"] == "true"
        ref = body["state"]["screenshot"]
        assert body["state"]["context"] == CONTEXT
        assert body["questions"] == {"region": {"type": "choice", "instructions": QUESTION["instructions"],
                                                "criteria": QUESTION["choices"]}}
        asset = body["assets"][ref]
        assert asset["format"] == "png" and base64.b64decode(asset["data_base64"]) == PNG
        assert saved["body"]["assets"][ref]["data_base64"] == {"archived_png_sha256": IMAGE["sha256"]}
    else:
        assert "typesafe-danger-zone-images" not in headers
        assert body["model"] == "gpt-6-luna"
        assert body["input"][0]["role"] == "user"
        text, image = body["input"][0]["content"]
        assert text == {"type": "input_text", "text": CONTEXT}
        assert image["type"] == "input_image"
        scheme, encoded = image["image_url"].split(",", 1)
        assert scheme == "data:image/png;base64" and base64.b64decode(encoded) == PNG
        assert body["questions"] == [{"type": "choice", "name": "region",
                                      "instructions": QUESTION["instructions"], "choices": [
                                          {"value": "map", "description": "Map button"},
                                          {"value": "hold", "description": "No visible control"},
                                      ]}]
    assert (stage / "response.json").read_bytes() == raw
    assert call["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert read_json(stage / "call.json") == call
    replay = api.parse_choice_response(backend, body["model"], QUESTION, raw)
    assert {field: call[field] for field in replay} == replay
    assert selected == choice == call["choice"]
    assert call["confidence"] == 0.42 and call["selected_probability"] == (0.75 if choice == "map" else 0.25)
    assert call["status"] == "completed" and call["attempts"] == 1 and call["response_received"] is True
    assert call["response_headers"] == {"x-request-id": "server-123"}
    assert call["request_id"] == "server-123"
    assert reply.read_sizes == [(1 << 20) + 1, (1 << 20) + 1 - len(raw)]
    assert not (stage / "safeerror.json").exists()
    assert all(KEY.encode() not in file.read_bytes() for file in stage.iterdir())
    assert base64.b64encode(PNG) not in (stage / "request.json").read_bytes()


def test_full_distribution_saved_and_call_summary_bounded(monkeypatch, tmp_path):
    stage = tmp_path / "region"
    options = {f"r{n:03}": f"Grid region {n}" for n in range(255)}
    probabilities = dict.fromkeys(options, 1 / len(options))
    payload = response("jev", choice="r254", probabilities=probabilities)
    mocked(monkeypatch, stage, Reply(json.dumps(payload).encode()))
    selected, call = request(stage, "jev", question=QUESTION | {"choices": options})
    assert selected == "r254" and call["option_count"] == 255
    assert len(call["top_choices"]) == 5
    assert len(read_json(stage / "response.json")["answers"]["region"]["probabilities"]) == 255


@pytest.mark.parametrize("backend, raw, error_code", [
    ("openai-decisions", b'{"answers":[],"answers":[]}', "duplicate_response_key"),
    ("openai-decisions", b'{"unrecognized":NaN}', "nonfinite_response_number"),
    ("openai-decisions", b'{"unrecognized":1e400}', "nonfinite_response_number"),
    ("openai-decisions", b'{"answers":[{"name":"region","type":"refusal"}]}', "provider_refusal"),
    ("openai-decisions", b'{"answers":[{"name":"other","type":"choice"}]}', "unexpected_answer_names"),
    ("openai-decisions", b'{"answers":[{},{}]}', "unexpected_answer_count"),
    ("openai-decisions", json.dumps(response("openai-decisions", probabilities={"map": 0.6, "hold": 0.3})).encode(),
     "invalid_probability_sum"),
    ("openai-decisions", json.dumps(response("openai-decisions", probabilities={"map": 1.25, "hold": -0.25})).encode(),
     "invalid_option_probability"),
    ("openai-decisions", json.dumps(response("openai-decisions", probabilities={"map": True, "hold": 0})).encode(),
     "invalid_option_probability"),
    ("openai-decisions", json.dumps(response("openai-decisions", probabilities={"map": 0.5, "other": 0.5})).encode(),
     "unexpected_probability_options"),
    ("jev", json.dumps(response("jev", choice="hold")).encode(), "jev_choice_is_not_maximum"),
    ("jev", b'{"answers":{"region":{},"extra":{}}}', "unexpected_answer_names"),
    ("jev", b'{"answers":{}}', "unexpected_answer_names"),
    pytest.param("openai-decisions", b" " * ((1 << 20) + 1), "response_size_limit", id="oversized-response"),
])
def test_invalid_responses_fail_closed(monkeypatch, tmp_path, backend, raw, error_code):
    stage = tmp_path / "first"
    opener = mocked(monkeypatch, stage, Reply(raw))
    with pytest.raises(api.VisualBackendError, match=error_code) as caught:
        request(stage, backend)
    call = caught.value.metadata["api_call"]
    assert call == read_json(stage / "call.json")
    assert call["status"] == "invalid_response" and call["attempts"] == 1
    assert call["response_received"] is True and len(opener.requests) == 1
    assert read_json(stage / "safeerror.json")["error_code"] == error_code
    artifact = stage / call["response_artifact"]
    assert artifact.stat().st_size <= 1 << 20
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == call["retained_response_sha256"]
    if error_code == "provider_refusal":
        assert artifact.name == "response.json" and artifact.read_bytes() == raw
    if error_code == "response_size_limit":
        assert artifact.name == "response.bin" and call["response_truncated"] is True


def test_http_failure_never_retries_or_redirects_and_saves_safe_evidence(monkeypatch, tmp_path):
    stage = tmp_path / "first"
    headers = Message()
    headers["Location"] = "https://untrusted.invalid/" + KEY
    headers["x-request-id"] = KEY
    escaped = "".join(f"\\u{ord(char):04x}" for char in KEY)
    error_body = Reply(f"Provider says: {KEY}; encoded key {escaped}".encode())
    error = HTTPError("https://api.openai.com/v1/decisions", 307, KEY, headers, error_body)
    opener = mocked(monkeypatch, stage, error)
    with pytest.raises(api.VisualBackendError) as caught:
        request(stage)
    call = caught.value.metadata["api_call"]
    assert call["status"] == "error" and call["http_status"] == 307
    assert call["response_received"] is True and call["request_id"] is None
    assert len(opener.requests) == 1 and len(error_body.read_sizes) == 2
    assert error_body.read_sizes[0] == (1 << 20) + 1
    assert call["response_redactions"] == 2
    assert (stage / "response.bin").read_bytes() == b"Provider says: [REDACTED]; encoded key [REDACTED]"
    assert KEY not in str(caught.value)
    assert all(KEY.encode() not in file.read_bytes() for file in stage.iterdir())
    redirect = api._NoRedirect()
    assert redirect.redirect_request(opener.requests[0][0], None, 307, "Redirect", headers, headers["Location"]) is None


def test_missing_response_and_reused_artifact_path(monkeypatch, tmp_path):
    stage = tmp_path / "first"
    opener = mocked(monkeypatch, stage, URLError(KEY))
    with pytest.raises(api.VisualBackendError) as caught:
        request(stage)
    assert caught.value.metadata["api_call"]["response_received"] is False
    before = {file.name: file.read_bytes() for file in stage.iterdir()}
    with pytest.raises(api.VisualBackendError, match="audit directory"):
        request(stage)
    assert before == {file.name: file.read_bytes() for file in stage.iterdir()}
    assert len(opener.requests) == 1
    assert all(KEY.encode() not in content for content in before.values())


@pytest.mark.parametrize("trickle_headers", [False, True], ids=["body", "headers"])
def test_http_trickle_cannot_extend_absolute_deadline(monkeypatch, tmp_path, trickle_headers):
    stage = tmp_path / "trickle"
    requests = []
    stopped = threading.Event()
    initial = b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 30\r\n"

    class Trickle(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                self.wfile.write(initial + (b"X-Slow: " if trickle_headers else b"\r\n"))
                for _ in range(30):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    if stopped.wait(0.05):
                        return
                if trickle_headers:
                    self.wfile.write(b"\r\n\r\n" + b"x" * 30)
            except OSError:
                pass  # The client closes its socket at the deadline.

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Trickle) as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        worker.start()
        try:
            monkeypatch.setenv("OPENAI_API_KEY", KEY)
            monkeypatch.setenv("NO_PROXY", "127.0.0.1")
            endpoint = f"http://127.0.0.1:{server.server_port}/v1/decisions"
            monkeypatch.setitem(api._ENDPOINTS, "openai-decisions", ("openai-decisions", endpoint))
            started = time.monotonic()
            with pytest.raises(api.VisualBackendError, match="request_deadline_exceeded") as caught:
                request(stage, timeout=0.25)
            elapsed = time.monotonic() - started
        finally:
            stopped.set()
            server.shutdown()
            worker.join()
    call = caught.value.metadata["api_call"]
    assert 0.17 < elapsed < 0.95  # A complete reply requires at least 1.45 seconds.
    assert len(requests) == 1 and call["attempts"] == 1 and call["status"] == "error"
    assert call["response_received"] is (not trickle_headers)
    assert read_json(stage / "call.json") == call
    if not trickle_headers:
        partial = (stage / "response.bin").read_bytes()
        assert call["response_partial"] is True and 0 < len(partial) < 30
        assert call["response_bytes"] == len(partial) and call["response_sha256"] == hashlib.sha256(partial).hexdigest()


@pytest.mark.parametrize("tunnel", [False, True], ids=["direct", "proxy-tunnel"])
def test_https_wraps_target_hostname_with_remaining_deadline(monkeypatch, tunnel):
    now = [1.0]
    calls = []
    monkeypatch.setattr(api, "time", SimpleNamespace(monotonic=lambda: now[0]))

    class Socket:
        def setsockopt(self, *args):
            pass

        def settimeout(self, timeout):
            self.timeout = timeout

        def connect(self, address):
            calls.append(("connect", address, self.timeout))
            now[0] += 2.0

        def sendall(self, data):
            calls.append(("send", data, self.timeout))
            now[0] += 1.0

        def makefile(self, mode, *, buffering):
            assert (mode, buffering) == ("rb", 0)
            return io.BytesIO(b"HTTP/1.1 200 Connection established\r\n\r\n")

        def close(self):
            pass

    raw, tls = Socket(), Socket()
    destination = ("127.0.0.1", 443)
    connect_host = "proxy.test" if tunnel else "provider.test"

    def lookup(host, port, *, type):
        assert (host, port, type) == (connect_host, 443, api.socket.SOCK_STREAM)
        now[0] += 1.0
        return [(api.socket.AF_INET, type, 0, "", destination)]

    def wrap(sock, *, server_hostname):
        assert sock is raw
        calls.append(("tls", server_hostname, sock.timeout))
        return tls

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(context, "wrap_socket", wrap)
    monkeypatch.setattr(api.socket, "getaddrinfo", lookup)
    monkeypatch.setattr(api.socket, "socket", lambda *args: raw)
    connection = api._DeadlineHTTPSConnection(connect_host, deadline=11.0, timeout=45.0, context=context)
    if tunnel:
        connection.set_tunnel("provider.test", 443)
    connection.connect()
    assert calls[0] == ("connect", destination, 9.0)
    if tunnel:
        assert calls[1][0] == "send" and calls[1][1].startswith(b"CONNECT provider.test:443 ")
        assert calls[1][2] == 7.0
    assert calls[-1] == ("tls", "provider.test", 6.0 if tunnel else 7.0)
    assert connection.sock.sock is tls
    now[0] = 11.0
    with pytest.raises(TimeoutError, match="deadline expired"):
        connection.sock.sendall(b"post body")
    assert calls[-1][0] == "tls"  # The HTTPS body never enters an expired socket.
    connection.close()


def test_dns_returning_after_deadline_cannot_open_connection(monkeypatch):
    now = [1.0]
    monkeypatch.setattr(api, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def lookup(*args, **kwargs):
        now[0] = 3.0
        return [(api.socket.AF_INET, api.socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(api.socket, "getaddrinfo", lookup)
    monkeypatch.setattr(api.socket, "socket", lambda *args: pytest.fail("socket created after deadline"))
    with pytest.raises(TimeoutError, match="deadline expired"):
        api._connect(2.0, ("provider.test", 443), 1.0)


def test_keyboard_interrupt_preserves_in_flight_call_and_propagates(monkeypatch, tmp_path):
    first, second = tmp_path / "region", tmp_path / "advance"
    mocked(monkeypatch, first, Reply(json.dumps(response("openai-decisions")).encode()))
    _, previous_call = request(first)
    interrupt = KeyboardInterrupt()
    opener = mocked(monkeypatch, second, interrupt)
    with pytest.raises(KeyboardInterrupt) as caught:
        request(second, question=QUESTION | {"name": "advance"})
    call = caught.value.metadata["api_call"]
    assert caught.value is interrupt
    assert len(opener.requests) == 1 and call["attempts"] == 1
    assert call["stage"] == "advance" and call["status"] == "error"
    assert call["response_received"] is False and call["error_code"] == "operator_interrupted"
    assert read_json(second / "safeerror.json")["error_code"] == "operator_interrupted"
    assert read_json(second / "call.json") == call
    assert read_json(first / "call.json") == previous_call


@pytest.mark.parametrize("write_failure", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_keyboard_interrupt_preserves_partial_body_without_masking_interrupt(monkeypatch, tmp_path, write_failure, empty):
    stage = tmp_path / "interrupted-body"
    interrupt = KeyboardInterrupt()
    encoded_key = "".join(f"%{ord(char):02X}" for char in KEY).encode()
    prefix = b"" if empty else b'{"debug":"' + encoded_key

    class InterruptedBody(Reply):
        def read1(self, size=-1):
            if empty or self.read_sizes:
                raise interrupt
            return self.read(size)

    if write_failure:
        write_bytes = api._write_bytes

        def fail_response(path, data):
            if path.name == "response.bin":
                raise OSError("simulated audit write failure")
            write_bytes(path, data)

        monkeypatch.setattr(api, "_write_bytes", fail_response)
    opener = mocked(monkeypatch, stage, InterruptedBody(prefix))
    with pytest.raises(KeyboardInterrupt) as caught:
        request(stage)
    assert caught.value is interrupt and len(opener.requests) == 1
    call = caught.value.metadata["api_call"]
    assert call["status"] == "error" and call["error_code"] == "operator_interrupted"
    assert call["response_received"] is True and call["response_partial"] is True
    assert call["response_bytes"] == len(prefix) and call["response_sha256"] == hashlib.sha256(prefix).hexdigest()
    assert read_json(stage / "safeerror.json")["error_code"] == "operator_interrupted"
    assert read_json(stage / "call.json") == call
    if write_failure:
        assert call["audit_error_code"] == "interrupted_response_audit_write_failed"
        assert not (stage / "response.bin").exists()
    else:
        retained = (stage / "response.bin").read_bytes()
        assert retained == (b"" if empty else b'{"debug":"[REDACTED]')
        assert call["response_redactions"] == (0 if empty else 1)
        assert call["retained_response_sha256"] == hashlib.sha256(retained).hexdigest()


def test_encoded_response_is_rejected_without_archiving_opaque_body(monkeypatch, tmp_path):
    stage = tmp_path / "compressed"
    raw = gzip.compress(KEY.encode())
    mocked(monkeypatch, stage, Reply(raw, {"content-encoding": "gzip"}))
    with pytest.raises(api.VisualBackendError, match="unsupported_response_encoding") as caught:
        request(stage)
    call = caught.value.metadata["api_call"]
    assert call["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert "response_artifact" not in call
    assert {path.name for path in stage.iterdir()} == {"request.json", "safeerror.json", "call.json"}


def test_jev_falls_back_to_its_alternate_configured_key(monkeypatch, tmp_path):
    stage = tmp_path / "alternate-key"
    opener = mocked(monkeypatch, stage, Reply(json.dumps(response("jev")).encode()))
    monkeypatch.setenv("TYPESAFE_API_KEY", " ")
    monkeypatch.setenv("JEV_API_KEY", KEY)
    request(stage, "jev")
    assert opener.requests[0][0].get_header("Authorization") == "Bearer " + KEY


def test_credentials_cannot_be_archived_in_request_or_response(monkeypatch, tmp_path):
    first, second = tmp_path / "request", tmp_path / "response"
    opener = mocked(monkeypatch, first, Reply(b"{}"))
    with pytest.raises(api.VisualBackendError, match="credential_in_request_evidence"):
        request(first, context=CONTEXT + KEY)
    assert not opener.requests and not (first / "request.json").exists()
    raw = json.dumps(response("openai-decisions") | {"unrecognized": KEY}).encode()
    mocked(monkeypatch, second, Reply(raw))
    with pytest.raises(api.VisualBackendError, match="credential_in_response"):
        request(second)
    assert all(KEY.encode() not in file.read_bytes() for stage in (first, second) for file in stage.iterdir())
    assert read_json(second / "call.json")["response_redactions"] == 1


@pytest.mark.parametrize("json_escape_percent", [False, True])
def test_success_response_rejects_url_encoded_credential_in_usage(monkeypatch, tmp_path, json_escape_percent):
    stage = tmp_path / "encoded-credential"
    encoded_key = "".join(f"%{ord(char):02X}" for char in KEY).encode()
    payload = response("openai-decisions")
    payload["usage"]["encoded_debug"] = encoded_key.decode()
    raw = json.dumps(payload).encode()
    if json_escape_percent:
        raw = raw.replace(b"%", br"\u0025")
    mocked(monkeypatch, stage, Reply(raw))
    with pytest.raises(api.VisualBackendError, match="credential_in_response") as caught:
        request(stage)
    call = caught.value.metadata["api_call"]
    assert call["status"] == "invalid_response" and call["usage"] is None
    assert call["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert call["response_redactions"] == 1
    assert read_json(stage / "response.bin")["usage"]["encoded_debug"] == "[REDACTED]"
    assert not (stage / "response.json").exists()
    assert all(encoded_key not in file.read_bytes() for file in stage.iterdir())


def test_preflight_rejects_invalid_options_model_and_image(monkeypatch, tmp_path):
    for index, overrides in enumerate((
        {"question": QUESTION | {"choices": {"one": "Only one option"}}},
        {"question": QUESTION | {"choices": {str(i): str(i) for i in range(256)}}},
        {"model": "gpt-6.1-sol"},
        {"image_bytes": PNG + b"altered"},
    )):
        stage = tmp_path / str(index)
        opener = mocked(monkeypatch, stage, Reply(b"{}"))
        with pytest.raises(api.VisualBackendError) as caught:
            request(stage, **overrides)
        assert caught.value.metadata["api_call"]["attempts"] == 0
        assert not opener.requests
