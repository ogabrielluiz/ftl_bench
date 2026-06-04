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

# Keep FTL ticking while unfocused so we never need to force it frontmost (App Nap
# off → its loop runs in the background; the bridge injects menu clicks regardless
# of focus). This avoids `osascript activate`, which LAUNCHES a second, vanilla,
# bridge-less FTL via LaunchServices if the app isn't registered yet (the "two FTL
# open" duplicate).
defaults write com.example.FTL NSAppSleepDisabled -bool YES 2>/dev/null || true
defaults write com.example.FTL LSAppNapIsDisabled -bool YES 2>/dev/null || true

# Launch the Hyperspace.command launcher DIRECTLY — it sets DYLD_INSERT_LIBRARIES
# and execs FTL so the bridge dylib is injected. Do NOT use `open "$FTL"`: on this
# Steam install LaunchServices starts the vanilla MacOS/FTL binary directly, the
# dylib is never inserted, and you get a bridge-less FTL that hangs (no pause, no
# observation stream). That bridge-less launch was the "frozen FTL" failure mode.
"$FTL/Contents/MacOS/Hyperspace.command" >"$SAVE/launch_out.txt" 2>&1 &
for i in $(seq 1 30); do
  if grep -q "dev script loaded" "$SAVE/FTL_HS.log" 2>/dev/null \
     && [ -f "$SAVE/ftl_agent_observation.json" ]; then
    echo "bridge live after ~${i}s"
    break
  fi
  sleep 1
done
# Safety net: never leave a duplicate running (it would corrupt the shared obs file).
n=$(pgrep -f "FTL Faster Than Light/FTL.app/Contents/MacOS/FTL" | wc -l | tr -d ' ')
[ "$n" -gt 2 ] && echo "WARNING: $n FTL processes (expected 1 game = parent+child)"

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
