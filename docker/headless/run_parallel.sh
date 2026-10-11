#!/usr/bin/env bash
# Parallel headless run: one isolated FTL container per scenario, CONC shards at a time.
# Each invocation uses a fresh shared output directory and one dashboard; all shard
# attempts are retained and re-scored at the end without selecting the best retry.
#
#   FTL_DIR=~/ftl-linux WHEEL=... HS_DIR=~/projects/FTL-Hyperspace \
#     ./run_parallel.sh --tier public --conc 3 --dashboard -- \
#       --agent llm --backend codex --model gpt-5.5
#
# Options (before `--`): --tier T | --type T | --max N | --conc K | --dashboard
# Everything after `--` is passed to each shard's harness (run_benchmark): --agent/--backend/etc.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FTLB_DIR="${FTLB_DIR:-$(cd "$HERE/../.." && pwd)}"
SUITE="${SUITE:-$FTLB_DIR/scenarios/suite_v1.json}"
CONC="${CONC:-3}"
TIER=""; TYPE=""; MAXN=""; DASHBOARD=0
HARNESS_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --type) TYPE="$2"; shift 2 ;;
    --max)  MAXN="$2"; shift 2 ;;
    --conc) CONC="$2"; shift 2 ;;
    --dashboard) DASHBOARD=1; shift ;;
    --) shift; HARNESS_ARGS=("$@"); break ;;
    *) echo "unknown option: $1 (put harness args after --)"; exit 1 ;;
  esac
done
[ -n "${FTL_DIR:-}" ] || { echo "ERROR: set FTL_DIR=/path/to/linux/FTL"; exit 1; }
[ ${#HARNESS_ARGS[@]} -gt 0 ] || HARNESS_ARGS=(--agent scripted)

# A user --out selects the parent; every parallel invocation gets a fresh child.
# Remove the option before forwarding, so each shard receives exactly one --out.
OUT_PARENT="${FTL_BENCH_OUT:-$FTLB_DIR/harness/runs/benchmark}"
FORWARD_ARGS=()
AGGREGATE_ARGS=()
for ((i=0; i<${#HARNESS_ARGS[@]}; i++)); do
  case "${HARNESS_ARGS[$i]}" in
    --out) i=$((i + 1)); [ "$i" -lt "${#HARNESS_ARGS[@]}" ] || { echo "--out requires a directory"; exit 1; }
           OUT_PARENT="${HARNESS_ARGS[$i]}" ;;
    --out=*) OUT_PARENT="${HARNESS_ARGS[$i]#--out=}" ;;
    --budget-cap) i=$((i + 1)); [ "$i" -lt "${#HARNESS_ARGS[@]}" ] || { echo "--budget-cap requires a number"; exit 1; }
                  FORWARD_ARGS+=(--budget-cap "${HARNESS_ARGS[$i]}"); AGGREGATE_ARGS=(--budget-cap "${HARNESS_ARGS[$i]}") ;;
    --budget-cap=*) FORWARD_ARGS+=("${HARNESS_ARGS[$i]}"); AGGREGATE_ARGS=(--budget-cap "${HARNESS_ARGS[$i]#--budget-cap=}") ;;
    *) FORWARD_ARGS+=("${HARNESS_ARGS[$i]}") ;;
  esac
done
[ -n "$OUT_PARENT" ] || { echo "--out requires a directory"; exit 1; }
case "$OUT_PARENT" in /*) ;; *) OUT_PARENT="$FTLB_DIR/$OUT_PARENT" ;; esac
HARNESS_ARGS=("${FORWARD_ARGS[@]}")
mkdir -p "$OUT_PARENT" || exit 1
RUNS="$(mktemp -d "$OUT_PARENT/parallel-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")" || exit 1
HARNESS_ARGS+=(--out "$RUNS")
echo "== fresh parallel output: $RUNS =="

echo "== building image once =="
bash "$HERE/run.sh" build || exit $?

echo "== splitting suite into per-scenario shards =="
SHARD_DIR="$RUNS/shards"; mkdir -p "$SHARD_DIR"
mapfile -t SUITES < <(python3 "$HERE/split_suite.py" "$SUITE" "$SHARD_DIR" "$TIER" "$TYPE" "$MAXN")
N=${#SUITES[@]}
[ "$N" -gt 0 ] || { echo "no scenarios selected (tier=$TIER type=$TYPE max=$MAXN)"; exit 1; }
echo "  $N scenarios, concurrency $CONC"

cleanup() {
  echo "== cleanup: removing shard containers =="
  docker ps -aq --filter "name=ftl-shard-" 2>/dev/null | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup EXIT

# One shared dashboard (same Windows-venv launch as run_host.sh --dashboard)
if [ "$DASHBOARD" = "1" ]; then
  DASH_PY="${DASH_PY:-/mnt/c/Users/Pichau/Projects/ftl_bench/harness/.venv/Scripts/python.exe}"
  DASH_APP="${DASH_APP:-/mnt/c/Users/Pichau/Projects/ftl_bench/adapter/ftl_live.py}"
  if [ -f "$DASH_PY" ] && [ -f "$DASH_APP" ]; then
    echo "== dashboard -> http://127.0.0.1:8765 =="
    DASH_APP_WIN="$(wslpath -w "$DASH_APP" 2>/dev/null || echo "$DASH_APP")"
    WSLENV="FTL_BENCH_DIR/p" FTL_BENCH_DIR="$RUNS" \
      nohup "$DASH_PY" "$DASH_APP_WIN" >/tmp/ftl_dashboard.log 2>&1 &
    disown || true
  else
    echo "(dashboard requested but $DASH_PY / $DASH_APP not found)"
  fi
fi

run_shard() {
  local idx="$1" suite="$2" sid
  sid="$(basename "$suite" .json)"
  echo "  [shard $idx] start: $sid"
  SKIP_BUILD=1 CONTAINER="ftl-shard-$idx" SAVE_DIR="$HOME/ftl_save_shard_$idx" \
    FTL_DIR="$FTL_DIR" FTLB_DIR="$FTLB_DIR" \
    bash "$HERE/run_host.sh" "${HARNESS_ARGS[@]}" --suite "$suite" --max-instances 1 \
    > "$SHARD_DIR/$sid.log" 2>&1
  local status=$?
  echo "  [shard $idx] done:  $sid (exit $status)"
  return "$status"
}

echo "== launching shards =="
pids=()
i=0
for suite in "${SUITES[@]}"; do
  run_shard "$i" "$suite" & pids+=($!)
  i=$((i + 1))
  # throttle: hold until fewer than CONC shard processes are live (count via kill -0)
  while true; do
    live=0
    for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && live=$((live + 1)); done
    [ "$live" -lt "$CONC" ] && break
    sleep 2
  done
done
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
echo "== all $N shards complete =="

python3 "$HERE/aggregate_parallel.py" "$SUITE" "$RUNS" "$TIER" "$TYPE" "$MAXN" "${AGGREGATE_ARGS[@]}"
aggregate_status=$?
[ "$failed" = "0" ] && [ "$aggregate_status" = "0" ]
