#!/usr/bin/env bash
# Autonomous FTL restart: quit, redeploy the dev script, relaunch, keep FTL
# frontmost until the bridge is live, then (optionally) start a game with no
# human click. No re-sign here, so no microphone prompt (that only re-appears
# after a C++/dylib rebuild, which changes the code-signature hash).
#
# Usage: scripts/restart_ftl.sh [continue|new|none]   (default: continue)
set -euo pipefail

MODE="${1:-continue}"
FTL="${FTL_APP:-$HOME/Library/Application Support/Steam/steamapps/common/FTL Faster Than Light/FTL.app}"
SAVE="${FTL_SAVE_DIR:-$HOME/Library/Application Support/FasterThanLight}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

echo "== restart FTL (mode=$MODE) =="
pkill -f "FTL Faster Than Light/FTL.app/Contents/MacOS/FTL" 2>/dev/null || true
sleep 2
bash "$HERE/scripts/deploy_dev.sh" >/dev/null
rm -f "$SAVE/ftl_agent_observation.json" "$SAVE/ftl_agent_action.json" "$SAVE/FTL_HS.log"

open "$FTL"
# FTL freezes its loop when it is not the frontmost window, so keep it foremost
# until the bridge's dev script has loaded and is streaming observations.
for i in $(seq 1 25); do
  open "$FTL" 2>/dev/null || true
  if grep -q "dev script loaded" "$SAVE/FTL_HS.log" 2>/dev/null \
     && [ -f "$SAVE/ftl_agent_observation.json" ]; then
    echo "bridge live after ~${i}s"
    break
  fi
  sleep 1
done

if [ "$MODE" != "none" ]; then
  ( cd "$HERE/harness" && FTL_BENCH_MODE="$MODE" uv run python - <<'PY'
import os
from ftl_bench import AgentSession
s = AgentSession()
o = s.observe()
if not o.game_started:
    o = s.start_game(os.environ.get("FTL_BENCH_MODE", "continue"), timeout=15.0)
print("game_started=%s hull=%s" % (o.game_started, (o.player_ship or {}).get("hull")))
PY
  )
fi
echo "== keep FTL frontmost while the harness drives it =="
