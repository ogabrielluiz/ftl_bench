#!/usr/bin/env bash
# Hot-reload the ftl_bench dev script into the RUNNING game — no relaunch, no
# re-patch, run state preserved. The in-.dat bootstrap re-runs the dev script
# (via Hyperspace.benchmark_reload_dev) when it sees the reload marker.
set -euo pipefail

SAVE="${FTL_SAVE_DIR:-$HOME/Library/Application Support/FasterThanLight}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"

[ -f "$SRC" ] || { echo "ERROR: dev script not found: $SRC"; exit 1; }
luac -p "$SRC" 2>/dev/null && echo "syntax OK" || { echo "ERROR: dev script has a syntax error"; luac -p "$SRC"; exit 1; }

cp "$SRC" "$SAVE/ftl_bench_dev.lua"
: > "$SAVE/ftl_bench_reload"     # touch the reload marker; bootstrap consumes it within ~15 ticks
echo "deployed -> $SAVE/ftl_bench_dev.lua  (+ reload marker)"
