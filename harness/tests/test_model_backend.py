import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapter"))
import model_backend


class Response:
    headers = {"request-id": "provider-request"}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return json.dumps({"model": "resolved-model", "usage": {"input_tokens": 4}}).encode()


def test_transient_http_retry_records_attempts_and_request_identity(monkeypatch):
    calls, sleeps = [], []
    def request(req, **kwargs):
        calls.append(req)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "rate limit", {}, io.BytesIO(b"wait"))
        return Response()
    monkeypatch.setattr(model_backend.urllib.request, "urlopen", request)
    monkeypatch.setattr(model_backend.time, "sleep", sleeps.append)
    data, metadata = model_backend.post_json("https://example.test", {"model": "requested"},
                                             "fixture-key", provider="fixture")
    assert len(calls) == 2 and calls[0] is calls[1]
    assert sleeps == [2]
    assert metadata["attempts"] == 2 and metadata["request_id"] == "provider-request"
    assert metadata["model"] == "resolved-model" and metadata["usage"]["input_tokens"] == 4
    assert metadata["client_request_id"] == calls[0].get_header("X-client-request-id")


def test_http_error_redacts_credentials_and_does_not_retry_authentication(monkeypatch):
    calls = []
    def request(req, **kwargs):
        calls.append(req)
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(b"fixture-key invalid"))
    monkeypatch.setattr(model_backend.urllib.request, "urlopen", request)
    with pytest.raises(RuntimeError) as error:
        model_backend.post_json("https://example.test", {}, "fixture-key", provider="fixture")
    assert "fixture-key" not in str(error.value) and "[redacted]" in str(error.value)
    assert len(calls) == 1


def test_transport_retries_are_bounded_and_redact_key(monkeypatch):
    calls = []
    def request(req, **kwargs):
        calls.append(req)
        raise urllib.error.URLError("fixture-key transport failed")
    monkeypatch.setattr(model_backend.urllib.request, "urlopen", request)
    monkeypatch.setattr(model_backend.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError) as error:
        model_backend.post_json("https://example.test", {}, "fixture-key", provider="fixture")
    assert len(calls) == 3 and "fixture-key" not in str(error.value)
