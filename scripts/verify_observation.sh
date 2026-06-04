#!/usr/bin/env bash
# ftl_bench — Milestone 1 Task 8 live verification.
# Run while FTL (with the ftl_bench_bridge mod) is running and a game is in progress.
# Confirms the observation file appears, `tick` advances, and the Python
# ObservationClient reads + validates the LIVE state.
set -euo pipefail

# macOS FTL user folder is "FasterThanLight" (confirmed live: getUserFolder()),
# not "FTL". The Hyperspace.command launcher cd's here before exec.
OBS="${1:-$HOME/Library/Application Support/FasterThanLight/ftl_agent_observation.json}"
HARNESS="$(cd "$(dirname "$0")/../harness" && pwd)"

echo "== ftl_bench observation verification =="
echo "watching: $OBS"

# 1. Wait for the file to appear (mod writes it on ON_TICK once loaded).
for i in $(seq 1 30); do
  [ -f "$OBS" ] && break
  echo "  waiting for observation file... ($i/30)"
  sleep 1
done
[ -f "$OBS" ] || { echo "ERROR: observation file never appeared. Is the mod applied and a game running?"; exit 1; }
echo "  file present."

# 2. Confirm `tick` advances (the throttled ON_TICK writer is live).
python3 - "$OBS" <<'PY'
import json, sys, time
p = sys.argv[1]
a = json.load(open(p)); print("  tick A:", a.get("tick"))
time.sleep(3)
b = json.load(open(p)); print("  tick B:", b.get("tick"))
assert b.get("tick", 0) > a.get("tick", -1), "tick did not advance — is the game unpaused?"
print("  STREAM_LIVE_OK")
PY

# 3. The harness reads + validates the LIVE file (end-to-end: game -> C++ write -> harness).
echo "-- ObservationClient on live file:"
cd "$HARNESS"
uv run python - "$OBS" <<'PY'
import sys
from ftl_bench import ObservationClient
o = ObservationClient(sys.argv[1]).read_latest()
hull = (o.player_ship or {}).get("hull")
print(f"  tick={o.tick} game_started={o.game_started} seed={o.seed} hull={hull}")
print("  HARNESS_READ_OK")
PY

echo
echo "== M1 live verification PASSED =="
echo "If hull/crew came back as nil, switch observation.lua pair access from .first/.second to [0]/[1] (see plan Task 8.4)."
