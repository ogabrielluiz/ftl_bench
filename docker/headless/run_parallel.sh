#!/usr/bin/env bash
# Parallel headless run: one FTL container per scenario, CONC shards at a time. This sidesteps the
# broken between-instance reset (each container does a single fresh-boot reset, the path that
# works) AND gives real headless throughput. All shards feed one shared runs dir + one dashboard;
# we re-score + aggregate at the end.
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

echo "== building image once =="
bash "$HERE/run.sh" build

echo "== splitting suite into per-scenario shards =="
SHARD_DIR="$HERE/.shards"; rm -rf "$SHARD_DIR"; mkdir -p "$SHARD_DIR"
mapfile -t SUITES < <(python3 "$HERE/split_suite.py" "$SUITE" "$SHARD_DIR" "$TIER" "$TYPE" "$MAXN")
N=${#SUITES[@]}
[ "$N" -gt 0 ] || { echo "no scenarios selected (tier=$TIER type=$TYPE max=$MAXN)"; exit 1; }
echo "  $N scenarios, concurrency $CONC"

RUNS="$FTLB_DIR/runs/benchmark"; mkdir -p "$RUNS"
echo "== clearing shared runs dir ($RUNS) =="
rm -f "$RUNS"/*.jsonl

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
  echo "  [shard $idx] done:  $sid"
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
wait
echo "== all $N shards complete =="

python3 "$HERE/aggregate_parallel.py" "$SUITE" "$RUNS" "$TIER" "$TYPE" "$MAXN"
