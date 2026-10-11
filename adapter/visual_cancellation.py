"""Durable cooperative stop requests; never terminate game or model processes."""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
from uuid import uuid4


class CooperativeStop(KeyboardInterrupt):
    def __init__(self, request, boundary):
        self.evidence = {"request": request, "observed_boundary": boundary,
                         "observed_at": datetime.now(timezone.utc).isoformat()}
        super().__init__("Cooperative stop requested at " + boundary)


def request_stop(path, scope, initiator, reason="operator_requested"):
    """Publish once, atomically, retaining the first request's actual attribution."""
    path = Path(path)
    request = {"contract": "visual-cooperative-stop-v1", "request_id": uuid4().hex,
               "scope": scope, "initiator": initiator, "reason": reason,
               "requested_at": datetime.now(timezone.utc).isoformat(), "requester_pid": os.getpid()}
    # Exclusive publication prevents replacing a prior request or its initiator.
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    try:
        os.link(temporary, path)
    except FileExistsError:
        pass
    finally:
        temporary.unlink()
    return json.loads(path.read_text(encoding="utf-8"))


class StopControl:
    def __init__(self, path=None, scope=None):
        self.path = Path(path).resolve() if path is not None else None
        self.scope = scope or (str(self.path.parent) if self.path else None)

    def pending(self):
        return self.path is not None and (self.path.exists() or self.path.is_symlink())

    @contextmanager
    def record_on_stop(self, recorder):
        """Record startup cancellation before the protected context tears down."""
        try:
            yield
        except CooperativeStop as error:
            recorder.finish(status="interrupted", reason="cooperative_stop_requested",
                            error=str(error), stop_request=error.evidence)
            raise

    def check(self, boundary):
        if not self.pending():
            return
        try:
            request = json.loads(self.path.read_text(encoding="utf-8"))
            if (request.get("contract") != "visual-cooperative-stop-v1"
                    or request.get("scope") != self.scope):
                raise ValueError("Stop request contract/scope mismatch")
        except (ValueError, OSError, AttributeError) as error:
            # A present unreadable control file fails closed, with honest attribution.
            request = {"scope": self.scope, "initiator": "unknown", "invalid_request": str(error)}
        raise CooperativeStop(request, boundary)


def wait_for_protected_child(child, control):
    """Ctrl+C requests cleanup and waits; never send terminate/kill to the child."""
    import subprocess
    while True:
        try:
            return child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            continue
        except KeyboardInterrupt:
            if control.path is None:
                raise
            request_stop(control.path, control.scope, "controller_keyboard_interrupt", "keyboard_interrupt")
