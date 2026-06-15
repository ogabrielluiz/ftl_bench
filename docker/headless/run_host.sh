#!/usr/bin/env bash
# Host-harness headless run: start an FTL-only container (entrypoint `serve` mode) and drive it from
# the HOST harness through the bridge files in a shared save dir. This is the path for the codex
# backend, whose CLI + auth live on Windows: WSL invokes Windows codex.exe via interop, while FTL
# runs headless in the container. Also works with --agent scripted (no codex) to test the plumbing.
#
#   FTL_DIR=~/ftl-linux ./run_host.sh --agent scripted --max-instances 1 --budget-cap 8
#   FTL_DIR=~/ftl-linux ./run_host.sh --agent llm --backend codex --model gpt-5.5 --max-instances 1
#
# Env: FTL_DIR (required, Linux FTL install), SAVE_DIR (shared bridge dir, default ~/ftl_headless_save),
#      CODEX_BIN (Windows codex.exe), CODEX_TMPDIR (/mnt/c temp dir codex.exe can write to),
#      CODEX_REASONING_EFFORT (passed through), IMAGE, FTLB_DIR, HS_DIR, FTL_PROFILE_DIR, CONTAINER.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FTLB_DIR="${FTLB_DIR:-$(cd "$HERE/../.." && pwd)}"
IMAGE="${IMAGE:-ftl-bench-headless}"
CONTAINER="${CONTAINER:-ftl-headless}"
SAVE_DIR="${SAVE_DIR:-$HOME/ftl_headless_save}"
CODEX_BIN="${CODEX_BIN:-/mnt/c/Users/Pichau/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe}"
CODEX_TMPDIR="${CODEX_TMPDIR:-/mnt/c/Users/Pichau/AppData/Local/Temp/ftlbench}"
[ -n "${FTL_DIR:-}" ] || { echo "ERROR: set FTL_DIR=/path/to/linux/FTL"; exit 1; }

PROFILE_DIR="${FTL_PROFILE_DIR-/mnt/c/Users/Pichau/Documents/My Games/FasterThanLight}"
PROFILE_ARGS=()
[ -n "$PROFILE_DIR" ] && [ -d "$PROFILE_DIR" ] && PROFILE_ARGS=(-v "$PROFILE_DIR:/profile:ro")

echo "== ensuring image is built =="
bash "$HERE/run.sh" build

echo "== resetting shared save dir: $SAVE_DIR =="
rm -rf "$SAVE_DIR"; mkdir -p "$SAVE_DIR" "$CODEX_TMPDIR"

echo "== starting FTL-only container ($CONTAINER) =="
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  "${PROFILE_ARGS[@]}" \
  -v "$FTL_DIR:/ftl:ro" \
  -v "$SAVE_DIR:/root/.local/share/FasterThanLight" \
  "$IMAGE" serve >/dev/null

cleanup() { echo "== stopping container =="; docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== waiting for FTL to boot (obs file) =="
for i in $(seq 1 120); do
  [ -f "$SAVE_DIR/ftl_agent_observation.json" ] && { echo "  FTL up after ~${i}s"; break; }
  docker ps -q -f "name=$CONTAINER" | grep -q . || { echo "container exited early:"; docker logs "$CONTAINER" 2>&1 | tail -30; exit 1; }
  sleep 1
done
[ -f "$SAVE_DIR/ftl_agent_observation.json" ] || { echo "no obs after 120s:"; docker logs "$CONTAINER" 2>&1 | tail -30; exit 1; }

echo "== running host harness: $* =="
cd "$FTLB_DIR"
FTL_SAVE_DIR="$SAVE_DIR" \
FTL_BENCH_ASSUME_ALIVE=1 \
CODEX_BIN="$CODEX_BIN" \
CODEX_TMPDIR="$CODEX_TMPDIR" \
  python3 adapter/run_benchmark.py "$@"
