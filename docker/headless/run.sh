#!/usr/bin/env bash
# Host helper (run from Linux/WSL): stage build inputs from the two repos, build the headless
# image, and optionally run it.
#
#   ./run.sh build                 # stage vendor/ + docker build
#   ./run.sh probe                 # build + run the display probe (no FTL needed)
#   FTL_DIR=/path/to/FTL ./run.sh verify    # build + launch FTL headless, confirm obs + play obs
#   FTL_DIR=/path/to/FTL ./run.sh run --agent scripted --max-instances 1   # build + scored run
#
# Env overrides: FTLB_DIR (ftl_bench repo, default: this repo), HS_DIR (FTL-Hyperspace repo,
# default ~/projects/FTL-Hyperspace), HS_VARIANT (1.6.13 Steam | 1.6.12 GOG/Humble),
# WHEEL (path to a ftl_bench wheel), IMAGE (image tag), FTL_DIR (Linux FTL install for verify/run).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FTLB_DIR="${FTLB_DIR:-$(cd "$HERE/../.." && pwd)}"
HS_DIR="${HS_DIR:-$HOME/projects/FTL-Hyperspace}"
HS_VARIANT="${HS_VARIANT:-1.6.13}"
IMAGE="${IMAGE:-ftl-bench-headless}"
V="$HERE/vendor"
SO="$HS_DIR/build-linux-${HS_VARIANT}-release/Hyperspace.${HS_VARIANT}.amd64.so"

CMD="${1:-build}"; shift || true

# Optional FTL profile to seed (skips first-run dialogs). Defaults to the Windows FTL save dir,
# which holds an established ae_prof.sav/prof.sav. Set FTL_PROFILE_DIR= to override (empty disables).
PROFILE_DIR="${FTL_PROFILE_DIR-/mnt/c/Users/Pichau/Documents/My Games/FasterThanLight}"
PROFILE_ARGS=()
[ -n "$PROFILE_DIR" ] && [ -d "$PROFILE_DIR" ] && PROFILE_ARGS=(-v "$PROFILE_DIR:/profile:ro")

stage() {
  echo "== staging vendor/ from FTLB_DIR=$FTLB_DIR  HS_DIR=$HS_DIR (variant $HS_VARIANT) =="
  rm -rf "$V"; mkdir -p "$V"
  [ -f "$SO" ] || { echo "ERROR: missing HS .so: $SO"; \
    echo "  build it: (cd \"$HS_DIR\" && buildscripts/linux-${HS_VARIANT}/build-releaseonly-from-docker.sh)"; exit 1; }
  cp "$SO" "$V/"
  cp "$HS_DIR/Release Files/Linux/liblua5.3.so.0" "$V/"
  # Build the .ftl mod zips with python's stdlib zipfile (no host `zip` dependency).
  ( cd "$HS_DIR/Mod Files" && python3 -m zipfile -c "$V/Hyperspace.ftl" * )
  ( cd "$FTLB_DIR/mod/ftl_bench_bridge" && python3 -m zipfile -c "$V/ftl_bench_bridge.ftl" data mod-appendix )
  cp "$FTLB_DIR/mod/ftl_bench_bridge/dev/ftl_bench_dev.lua" "$V/"
  # FTLMan (Linux): stage host-side into vendor/ (the build container can't reach api.github.com).
  # Prefer an existing binary ($FTLMAN, PATH, or the one setup_pc drops in ~/.local/bin); else download.
  local fm="${FTLMAN:-}"
  [ -n "$fm" ] || fm="$(command -v ftlman 2>/dev/null || true)"
  [ -n "$fm" ] || { [ -x "$HOME/.local/bin/ftlman" ] && fm="$HOME/.local/bin/ftlman"; }
  if [ -n "$fm" ] && [ -x "$fm" ]; then
    echo "   using existing FTLMan: $fm"
    cp "$fm" "$V/ftlman"
  else
    local fmurl
    fmurl="$(curl -fsSL https://api.github.com/repos/afishhh/ftlman/releases/latest \
              | grep -oE 'https://[^"]*x86_64[^"]*linux[^"]*\.tar\.gz' | head -1)"
    [ -n "$fmurl" ] || { echo "ERROR: no FTLMan binary found and api.github.com unreachable (set FTLMAN=/path/to/ftlman)"; exit 1; }
    curl -fsSL "$fmurl" -o /tmp/ftlman.tgz && tar -xzf /tmp/ftlman.tgz -C /tmp
    cp "$(find /tmp -maxdepth 2 -name ftlman -type f | head -1)" "$V/ftlman"
  fi
  chmod +x "$V/ftlman"
  local whl="${WHEEL:-}"
  [ -n "$whl" ] || whl="$(ls "$FTLB_DIR"/dist/ftl_bench-*.whl "$FTLB_DIR"/harness/dist/ftl_bench-*.whl 2>/dev/null | head -1 || true)"
  [ -n "$whl" ] || { echo "ERROR: no ftl_bench wheel found (set WHEEL=, or build: cd \"$FTLB_DIR/harness\" && python3 -m build)"; exit 1; }
  cp "$whl" "$V/"
  for f in "Hyperspace.${HS_VARIANT}.amd64.so" liblua5.3.so.0 Hyperspace.ftl ftl_bench_bridge.ftl ftl_bench_dev.lua ftlman; do
    [ -s "$V/$f" ] || { echo "ERROR: vendor/$f missing or empty after staging"; exit 1; }
  done
  ls "$V"/ftl_bench-*.whl >/dev/null 2>&1 || { echo "ERROR: vendor wheel missing after staging"; exit 1; }
  echo "   staged: $(ls "$V" | tr '\n' ' ')"
}

build() {
  stage
  echo "== docker build -> $IMAGE =="
  docker build -t "$IMAGE" "$HERE" || { echo "ERROR: docker build failed"; exit 1; }
}

case "$CMD" in
  stage)  stage ;;
  build)  build ;;
  probe)  build; echo "== docker run probe =="; docker run --rm "$IMAGE" probe ;;
  verify) [ -n "${FTL_DIR:-}" ] || { echo "set FTL_DIR=/path/to/linux/FTL"; exit 1; }
          build; echo "== docker run verify =="; docker run --rm "${PROFILE_ARGS[@]}" -v "$FTL_DIR:/ftl:ro" "$IMAGE" verify ;;
  diag)   [ -n "${FTL_DIR:-}" ] || { echo "set FTL_DIR=/path/to/linux/FTL"; exit 1; }
          build; echo "== docker run diag =="; docker run --rm "${PROFILE_ARGS[@]}" -v "$FTL_DIR:/ftl:ro" "$IMAGE" diag ;;
  resettest) [ -n "${FTL_DIR:-}" ] || { echo "set FTL_DIR=/path/to/linux/FTL"; exit 1; }
          build; echo "== docker run resettest =="; docker run --rm "${PROFILE_ARGS[@]}" -v "$FTL_DIR:/ftl:ro" "$IMAGE" resettest ;;
  run)    [ -n "${FTL_DIR:-}" ] || { echo "set FTL_DIR=/path/to/linux/FTL"; exit 1; }
          build; echo "== docker run run $* =="; docker run --rm "${PROFILE_ARGS[@]}" -v "$FTL_DIR:/ftl:ro" "$IMAGE" run "$@" ;;
  *) echo "usage: run.sh [stage|build|probe|verify|run …]  (FTL_DIR=… required for verify/run)"; exit 1 ;;
esac
