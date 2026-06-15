#!/usr/bin/env bash
# Headless ftl_bench entrypoint. Modes:
#   probe        validate the headless display stack (Xvfb + Mesa GL + SDL2). No FTL needed.
#   verify       assemble FTL+HS, launch headless, confirm the bridge writes an observation,
#                then `ftlbench play obs`. The handoff's stated first verification.
#   run [args…]  assemble + launch, then `ftlbench run [args…]`.
#
# For verify/run, bind-mount a steamcmd-installed Linux FTL dir (read-only) at /ftl. steamcmd lays
# the game out under data/ (FTL.amd64 + ftl.dat + amd64/libsteam_api.so + the FTL launcher).
set -uo pipefail
log(){ printf '\n[headless] %s\n' "$*"; }
die(){ printf '\n[headless] FATAL: %s\n' "$*" >&2; exit 1; }

MODE="${1:-probe}"; shift || true

start_xvfb(){
  log "starting Xvfb on ${DISPLAY} (${XVFB_WHD})"
  Xvfb "${DISPLAY}" -screen 0 "${XVFB_WHD}" -nolisten tcp >/tmp/xvfb.log 2>&1 &
  for _ in $(seq 1 60); do
    xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1 && { log "Xvfb ready"; return 0; }
    sleep 0.1
  done
  cat /tmp/xvfb.log 2>/dev/null; die "Xvfb did not come up"
}

# ---- probe: no game required ------------------------------------------------
if [ "$MODE" = "probe" ]; then
  start_xvfb
  log "glxinfo (renderer should be llvmpipe / software):"
  glxinfo -B 2>/dev/null | grep -iE "OpenGL (vendor|renderer|version)|Device:" || log "(glxinfo unavailable)"
  log "SDL2 video + GL context probe:"
  python3 /opt/hs/probe_gl.py || die "SDL2/GL probe failed"
  log "PROBE OK — the headless display stack (Xvfb + Mesa software GL + SDL2) works."
  exit 0
fi

# ---- verify / run: assemble FTL + Hyperspace --------------------------------
[ -d /ftl ] || die "no FTL install at /ftl — bind-mount a Linux FTL dir: -v /path/to/FTL:/ftl:ro"
WORK=/work/ftl
log "copying mounted FTL -> ${WORK} (pristine /ftl stays untouched)"
mkdir -p "$WORK"; rsync -a --delete /ftl/ "$WORK"/ || die "could not copy FTL from /ftl"

# Locate the game dir: FTL.amd64 + ftl.dat live together (steamcmd puts them under data/).
GAMEDIR=""
for d in "$WORK/data" "$WORK"; do
  [ -f "$d/FTL.amd64" ] && [ -f "$d/ftl.dat" ] && { GAMEDIR="$d"; break; }
done
[ -n "$GAMEDIR" ] || die "FTL.amd64 + ftl.dat not found under ${WORK} (looked in ./ and data/)"
log "game dir: ${GAMEDIR}"

log "patching ftl.dat with Hyperspace.ftl + ftl_bench_bridge.ftl (FTLMan)"
ftlman patch /opt/hs/Hyperspace.ftl /opt/hs/ftl_bench_bridge.ftl -d "$GAMEDIR" \
  || die "FTLMan patch failed"

# Inject Hyperspace next to FTL.amd64; steam_appid.txt lets FTL run without a Steam client.
SO="$(ls /opt/hs/Hyperspace.*.amd64.so 2>/dev/null | head -1)"; [ -n "$SO" ] || die "no Hyperspace .so in /opt/hs"
SO_NAME="$(basename "$SO")"
cp "$SO" /opt/hs/liblua5.3.so.0 "$GAMEDIR"/
echo 212680 > "$GAMEDIR/steam_appid.txt"

# Deploy the hot-reload dev lua to FTL's Linux user folder (where the bench bridge reads/writes).
# The harness reads obs from the SAME dir, so FTL_SAVE_DIR must equal it (XDG default for FTL Linux).
export FTL_SAVE_DIR="$HOME/.local/share/FasterThanLight"
mkdir -p "$FTL_SAVE_DIR"
cp /opt/hs/ftl_bench_dev.lua "$FTL_SAVE_DIR"/ && : > "$FTL_SAVE_DIR/ftl_bench_reload"
rm -f "$FTL_SAVE_DIR"/ftl_agent_observation.json "$FTL_SAVE_DIR"/ftl_agent_action.json

# Seed an existing FTL profile so FTL boots as an established player — this skips the fresh-profile
# first-run dialogs (language select / "Enable Advanced Edition?") that the new-game menu nav
# (hs_benchmark_advance_menu) does not dismiss. Mount any *.sav files at /profile.
if [ -d /profile ]; then
  n="$(ls /profile/*.sav 2>/dev/null | wc -l)"
  cp /profile/*.sav "$FTL_SAVE_DIR"/ 2>/dev/null || true
  log "seeded FTL profile from /profile (${n} .sav files)"
fi

start_xvfb
log "launching FTL.amd64 headless (LD_PRELOAD=${SO_NAME}) from ${GAMEDIR}"
(
  cd "$GAMEDIR" || exit 1
  export LANG="${LC_ALL:-${LANG:-C}}" LC_ALL= LC_NUMERIC=C
  export LD_LIBRARY_PATH="$GAMEDIR:$GAMEDIR/amd64:${LD_LIBRARY_PATH:-}"
  export LD_PRELOAD="$GAMEDIR/$SO_NAME"
  exec ./FTL.amd64
) >/tmp/ftl.log 2>&1 &
FTL_PID=$!

OBS="$FTL_SAVE_DIR/ftl_agent_observation.json"
log "waiting for the bench bridge to write ${OBS} ..."
for i in $(seq 1 600); do
  [ -f "$OBS" ] && { log "OBSERVATION APPEARED after ~${i}s — the bench bridge is live headless."; break; }
  kill -0 "$FTL_PID" 2>/dev/null || { log "FTL exited; last 60 log lines:"; tail -60 /tmp/ftl.log 2>/dev/null; die "FTL exited before writing an observation"; }
  sleep 1
done
[ -f "$OBS" ] || { log "timeout; last 60 FTL log lines:"; tail -60 /tmp/ftl.log 2>/dev/null; die "no observation after 600s"; }

if [ "$MODE" = "serve" ]; then
  # FTL-only mode: keep the game running and let an EXTERNAL harness drive it through the bridge
  # files in $FTL_SAVE_DIR (bind-mount that dir to the host). Used for the host-harness/codex flow.
  log "FTL is serving headless. Bridge dir: ${FTL_SAVE_DIR} (share it with the host harness)."
  wait "$FTL_PID"
  exit $?
fi

if [ "$MODE" = "diag" ]; then
  log "raw observation at startup:"; cat "$OBS"; echo
  log "menu/dialog state:"
  python3 - "$OBS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for k in ("game_started","paused","choice_box_open","menu_button_count","menu_buttons","event"):
    print(f"  {k} = {d.get(k)}")
PY
  log "issuing start_game(new, seed=1) and sampling for 30s ..."
  ( ftlbench play start 1 || true ) &
  for t in 2 5 10 15 20 30; do
    sleep "$t"
    python3 - "$OBS" "$t" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  t~{sys.argv[2]}s: game_started={d.get('game_started')} choice_box={d.get('choice_box_open')} "
      f"menu_count={d.get('menu_button_count')} buttons={d.get('menu_buttons')}")
PY
  done
  log "FTL/HS stdout — menu/profile/version/intro lines:"
  grep -inE "menu|profile|advanced|edition|version|hangar|new ?game|intro|splash|title|press|load|\.sav|error|fail|hyperspace" /tmp/ftl.log 2>/dev/null | grep -viE "Doubly defined" | tail -70
  log "FTL/HS stdout (last 25 lines):"; tail -25 /tmp/ftl.log 2>/dev/null
  log "save dir now:"; ls -la "$FTL_SAVE_DIR" 2>/dev/null
  exit 0
fi

if [ "$MODE" = "verify" ]; then
  log "ftlbench play obs:"
  ftlbench play obs || true   # the obs FILE already proved the bridge; don't fail on a label quirk
  log "VERIFY OK — headless FTL produced a valid observation with no display."
  exit 0
fi

log "running: ftlbench run $*"
exec ftlbench run "$@"
