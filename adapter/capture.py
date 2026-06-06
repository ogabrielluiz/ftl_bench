"""capture — let an agent take a screenshot of the live FTL window, on demand.

This is an ADDITIVE capability: it does not change the JSON observation. An agent that
wants to *look* at the game (a hard-to-serialize moment — a beam sweep, a boarding fight,
an ambiguous event art) calls this and reads the returned PNG. The agent plays through the
code-mode / MCP adapter as a vision-capable Claude, so a PNG path is directly usable.

Mechanism (macOS): `screencapture -l <CGWindowID>` grabs FTL's OWN window buffer, which is
occlusion-proof — it returns the game even when another window covers it. The naive
`screencapture -R <region>` is NOT used: it grabs the screen rectangle, so an overlapping
window (a browser, an editor) would be captured instead of FTL.

Resolving the window id needs Quartz (`pyobjc-framework-Quartz`). It is imported lazily so a
missing dependency only disables `screenshot`, never the rest of the CLI/harness. If Quartz is
absent we fall back to an AppleScript-bounds region grab (best-effort; may capture an occluding
window) and say so in the result so the caller is never misled.

The turn-based bridge keeps the game paused between actions, so a capture taken at obs time is a
stable, decision-relevant frame.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

FTL_OWNER = "FTL"


def find_ftl_window_id() -> int | None:
    """The CGWindowID of FTL's largest on-screen window, or None (Quartz missing / not running)."""
    try:
        from Quartz import (  # type: ignore  # lazy: optional dep
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
        )
    except Exception:
        return None
    wins = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    best_id, best_area = None, 0
    for w in wins:
        if (w.get("kCGWindowOwnerName") or "") != FTL_OWNER:
            continue
        b = w.get("kCGWindowBounds") or {}
        area = (b.get("Width", 0) or 0) * (b.get("Height", 0) or 0)
        if area > best_area:
            best_area, best_id = area, w.get("kCGWindowNumber")
    return int(best_id) if best_id else None


def _applescript_bounds() -> tuple[int, int, int, int] | None:
    """FTL window {x, y, w, h} via System Events, or None. Fallback path only."""
    script = ('tell application "System Events" to tell (first process whose name is "FTL") '
              "to get {position, size} of window 1")
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        nums = [int(x.strip()) for x in r.stdout.strip().split(",")]
        return nums[0], nums[1], nums[2], nums[3]
    except (ValueError, IndexError):
        return None


def capture_ftl(out_path: str | Path) -> dict[str, Any]:
    """Capture the FTL window to `out_path` (PNG). Returns a result dict the agent can act on:
        {ok, path, window_id, method, occlusion_proof, [error, hint]}.
    method "window_buffer" is occlusion-proof; "region" may capture an overlapping window."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    wid = find_ftl_window_id()
    if wid is not None:
        r = subprocess.run(["screencapture", "-x", "-o", f"-l{wid}", str(out)],
                           capture_output=True, text=True)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return {"ok": True, "path": str(out), "window_id": wid,
                    "method": "window_buffer", "occlusion_proof": True}
        return {"ok": False, "window_id": wid, "method": "window_buffer",
                "error": (r.stderr or "screencapture failed").strip(),
                "hint": "FTL window id found but capture failed — check Screen Recording permission"}

    # Fallback: no Quartz. Region grab from AppleScript bounds (may catch an occluding window).
    bounds = _applescript_bounds()
    if bounds is None:
        return {"ok": False, "method": "none",
                "error": "could not find the FTL window (Quartz missing AND AppleScript bounds failed)",
                "hint": "is FTL running and on-screen? install pyobjc-framework-Quartz for reliable capture"}
    x, y, w, h = bounds
    r = subprocess.run(["screencapture", "-x", "-o", f"-R{x},{y},{w},{h}", str(out)],
                       capture_output=True, text=True)
    if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
        return {"ok": True, "path": str(out), "window_id": None, "method": "region",
                "occlusion_proof": False,
                "hint": "region grab — if another window overlaps FTL it may appear instead; "
                        "install pyobjc-framework-Quartz for occlusion-proof window capture"}
    return {"ok": False, "method": "region", "error": (r.stderr or "screencapture failed").strip()}


if __name__ == "__main__":
    import json
    import sys
    dest = sys.argv[1] if len(sys.argv) > 1 else "ftl_screenshot.png"
    print(json.dumps(capture_ftl(dest), indent=2))
