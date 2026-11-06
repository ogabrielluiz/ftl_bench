"""Small shared HTTP boundary for model backends, with bounded retries and trace metadata."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from uuid import uuid4


class Completion(str):
    def __new__(cls, text: str, metadata: dict):
        result = super().__new__(cls, text)
        result.metadata = metadata
        return result


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_json(endpoint: str, body: dict, key: str, *, provider: str,
              timeout: float = 90, attempts: int = 3, headers: dict | None = None,
              allow_redirects: bool = True) -> tuple[dict, dict]:
    if not key:
        raise RuntimeError(f"{provider} API key is not configured")
    client_id = str(uuid4())
    request = urllib.request.Request(
        endpoint, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Client-Request-Id": client_id,
                 **(headers if headers is not None else {"Authorization": f"Bearer {key}"})}, method="POST")
    open_request = (urllib.request.urlopen if allow_redirects else
                    urllib.request.build_opener(_RejectRedirects()).open)
    started = time.monotonic()
    for attempt in range(attempts):
        try:
            with open_request(request, timeout=timeout) as response:
                data = json.loads(response.read())
                if not isinstance(data, dict):
                    raise RuntimeError(f"{provider} returned an invalid response object")
                metadata = {"provider": provider, "model": data.get("model") or body.get("model"),
                            "request_id": response.headers.get("x-request-id") or response.headers.get("request-id"),
                            "client_request_id": client_id, "usage": data.get("usage"),
                            "latency_seconds": round(time.monotonic() - started, 3),
                            "attempts": attempt + 1}
                return data, metadata
        except urllib.error.HTTPError as error:
            if not allow_redirects and 300 <= error.code < 400:
                error.close()
                raise RuntimeError(f"{provider} API HTTP {error.code}: redirects are disabled") from None
            detail = error.read().decode("utf-8", errors="replace").replace(key, "[redacted]")[:300]
            if error.code in {429, 500, 502, 503, 504, 529} and attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"{provider} API HTTP {error.code}: {detail or error.reason}") from None
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"{provider} API transport error: {str(error).replace(key, '[redacted]')}") from None
    raise RuntimeError(f"{provider} request failed")
