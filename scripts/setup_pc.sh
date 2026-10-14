#!/usr/bin/env bash
# ============================================================================
# ftl_bench — one-shot PC (WSL2) bootstrap
# ----------------------------------------------------------------------------
# Goal: stand up the FTL benchmark on the Windows PC with NATIVE x86 FTL +
# a NATIVE-x86 Windows Hyperspace.dll, eliminating the Rosetta crash class that
# freezes sector transitions on the Mac.
#
# WHY this works without MSVC / Visual Studio:
#   The Hyperspace Windows build is a Docker (MinGW cross-compile) build. The
#   whole toolchain (vcpkg + MinGW + cmake + ninja) lives in a published image
#   Require DEVCONTAINER=registry/repository@sha256:<digest> for the build stage.
#   The native base comes from native/manifest.json; no floating native HEAD.
#   Output: dist/Hyperspace.visual-v1.dll + native-build.visual-v1.json.
#
# WHAT is platform-independent (reused as-is from the Mac work):
#   - Hyperspace.ftl data mod  (re-zipped from the repo's "Mod Files/" to match
#                               the DLL we just built)
#   - ftl_bench_bridge.ftl     (the bench bridge data mod, in dist/)
#   - ftl_bench_dev.lua         (hot-reloaded dev script)
#   Only the binary differs: dylib (Mac) -> Hyperspace.dll (Windows).
#
# WHAT needs Windows admin (game lives under Program Files):
#   - downgrade FTL to 1.6.9  (downgrade.bat)
#   - drop the loader proxy (xinput1_4.dll + lua-5.3.dll + patch/) and our
#     Hyperspace.dll next to FTLGame.exe
#   These are emitted as install_into_game.bat and run elevated at the end.
#
# Idempotent: safe to re-run. Each stage checks before doing work.
#
# Usage (on the PC, inside WSL):
#   bash setup_pc.sh            # run every stage
#   bash setup_pc.sh build      # run from the 'build' stage onward
#   STAGES="repos build" bash setup_pc.sh   # run only the named stages
# ============================================================================
set -uo pipefail

# ---- config ---------------------------------------------------------------
PROJ="${PROJ:-$HOME/projects}"
FTLB_REPO="https://github.com/ogabrielluiz/ftl_bench.git"
DEVCONTAINER="${DEVCONTAINER:-}" # explicit immutable registry digest; build stage only
FTLMAN="${FTLMAN:-}"            # caller-supplied Linux executable; no acquisition
FTLMAN_SHA256="${FTLMAN_SHA256:-}" # required exact executable SHA-256
WIN_USER="${WIN_USER:-}"        # auto-detected if empty

SCRIPT_FILE="$(realpath -- "${BASH_SOURCE[0]}")" || { echo "cannot resolve bootstrap script" >&2; exit 1; }
SCRIPT_ROOT="$(cd -- "$(dirname -- "$SCRIPT_FILE")/.." && pwd -P)" || exit 1
if [ -n "${FTLB_ROOT:-}" ]; then
  FTLB="$(realpath -m -- "$FTLB_ROOT")" || exit 1
elif [ -e "$SCRIPT_ROOT/.git" ] && [ -f "$SCRIPT_ROOT/native/manifest.json" ]; then
  FTLB="$SCRIPT_ROOT"
else
  FTLB="$PROJ/ftl_bench"
fi
HS="$PROJ/FTL-Hyperspace"

log()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '   \033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mFATAL: %s\033[0m\n' "$*" >&2; exit 1; }

load_native_pins() {
  local pins
  pins="$(python3 "$FTLB/scripts/stage_native_artifacts.py" config)" || die "invalid native manifest/patch"
  mapfile -t native_pins <<< "$pins"
  [ "${#native_pins[@]}" = "2" ] || die "invalid native source configuration"
  HS_REPO="${native_pins[0]}"; HS_COMMIT="${native_pins[1]}"
}

# stage selection ------------------------------------------------------------
ALL_STAGES="durability repos build datamod locate install patch deploy verify"
if [ -n "${STAGES:-}" ]; then
  RUN="$STAGES"
elif [ $# -ge 1 ]; then
  # run from the named stage onward
  start="$1"; RUN=""; seen=0
  for s in $ALL_STAGES; do [ "$s" = "$start" ] && seen=1; [ $seen = 1 ] && RUN="$RUN $s"; done
  [ -n "$RUN" ] || die "unknown stage '$start' (valid: $ALL_STAGES)"
else
  RUN="$ALL_STAGES"
fi
want() { case " $RUN " in *" $1 "*) return 0;; *) return 1;; esac; }

# detect Windows user (for /mnt/c paths) ------------------------------------
detect_win_user() {
  [ -n "$WIN_USER" ] && { echo "$WIN_USER"; return; }
  # prefer the user that owns a "My Games" FTL save dir
  for d in /mnt/c/Users/*/; do
    [ -d "$d/Documents/My Games/FasterThanLight" ] && { basename "$d"; return; }
  done
  # fall back to whoami via cmd.exe
  cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n'
}

echo "ftl_bench PC bootstrap — stages:$RUN"

# ===========================================================================
# STAGE durability — make the SSH connection survive WSL2 idle-shutdown
# ===========================================================================
if want durability; then
  log "durability: keep WSL reachable across idle + reboot"
  # 1) ssh server present + running + autostart
  if ! command -v sshd >/dev/null 2>&1; then
    warn "openssh-server not installed — installing (needs sudo)"
    sudo apt-get update -y && sudo apt-get install -y openssh-server
  fi
  sudo service ssh start 2>/dev/null && ok "ssh service started"
  # autostart ssh on WSL boot via /etc/wsl.conf boot.command
  if ! grep -q 'service ssh start' /etc/wsl.conf 2>/dev/null; then
    printf '[boot]\ncommand = "service ssh start"\n' | sudo tee -a /etc/wsl.conf >/dev/null
    ok "wsl.conf boot.command set (ssh autostarts on WSL boot)"
  fi
  # 2) disable WSL2 idle VM shutdown via Windows-side .wslconfig
  wu="$(detect_win_user)"; [ -n "$wu" ] && WIN_USER="$wu"
  WSLCONF="/mnt/c/Users/$WIN_USER/.wslconfig"
  if [ -n "$WIN_USER" ] && [ -d "/mnt/c/Users/$WIN_USER" ]; then
    # Durability precedes repos for standalone bootstrap copies. Never append
    # blindly when the checkout/helper or Python is not available yet.
    IDLE_HELPER="$FTLB/scripts/configure_wsl_idle.py"
    if [ ! -f "$IDLE_HELPER" ] || ! command -v python3 >/dev/null 2>&1; then
      warn "WSL idle helper/Python unavailable; preserving $WSLCONF (review after repos)"
    elif IDLE_RESULT="$(python3 -B "$IDLE_HELPER" --path "$WSLCONF")"; then
      if [[ "$IDLE_RESULT" == *'"status": "preserved_explicit_value"'* ]]; then
        warn ".wslconfig explicit vmIdleTimeout preserved; idle shutdown was not disabled"
      else
        ok ".wslconfig vmIdleTimeout=-1 (effective after an operator-scheduled WSL restart)"
      fi
    else
      warn "WSL idle configuration refused; preserving $WSLCONF for manual review"
    fi
  else
    warn "could not detect Windows user dir; set WIN_USER=... and re-run durability"
  fi
fi

# ===========================================================================
# STAGE repos — clone/update both repos
# ===========================================================================
if want repos; then
  log "repos: preserve selected ftl_bench revision; prepare the declared native base"
  mkdir -p "$PROJ"
  if [ -e "$FTLB/.git" ]; then
    git -C "$FTLB" rev-parse --verify HEAD >/dev/null \
      || die "selected benchmark checkout has no valid HEAD: $FTLB"
    ok "benchmark checkout preserved (HEAD and local edits): $FTLB"
  else
    git clone "$FTLB_REPO" "$FTLB" || die "could not clone benchmark into $FTLB"
    ok "ftl_bench cloned; select the intended revision before building"
  fi
  load_native_pins
  if [ -e "$HS/.git" ]; then
    [ "$(git -C "$HS" rev-parse HEAD)" = "$HS_COMMIT" ] \
      || die "existing Hyperspace HEAD differs from $HS_COMMIT; preserve it and use a separate checkout"
    ok "Hyperspace already at declared base $HS_COMMIT (local changes preserved)"
  else
    git clone --no-checkout "$HS_REPO" "$HS" \
      && git -C "$HS" checkout --detach "$HS_COMMIT" \
      || die "could not prepare declared native base $HS_COMMIT"
    ok "Hyperspace cloned @ $HS_COMMIT"
  fi
  (cd "$HS" && echo "   HEAD: $(git log --oneline -1)")
fi

# ===========================================================================
# STAGE build — Hyperspace.dll via the devcontainer (Docker / MinGW)
# ===========================================================================
if want build; then
  log "build: Hyperspace.dll (Docker devcontainer, MinGW cross-compile)"
  BUILD_RESOURCES=()
  if [ "${FTLB_BUILD_MEMORY+x}" = x ]; then
    [[ "$FTLB_BUILD_MEMORY" =~ ^[1-9][0-9]*[mg]$ ]] \
      || die "FTLB_BUILD_MEMORY must be a positive integer with explicit m/g suffix"
    BUILD_RESOURCES+=(--memory "$FTLB_BUILD_MEMORY" --memory-swap "$FTLB_BUILD_MEMORY")
  fi
  if [ "${FTLB_BUILD_CPUS+x}" = x ]; then
    [[ "$FTLB_BUILD_CPUS" =~ ^[1-9][0-9]*$ ]] \
      || die "FTLB_BUILD_CPUS must be a positive integer"
    BUILD_RESOURCES+=(--cpus "$FTLB_BUILD_CPUS")
  fi
  BUILD_INNER='source .devcontainer/devcontainer-fixes.sh && buildscripts/windows/build-releaseonly.sh'
  if [ "${FTLB_BUILD_JOBS+x}" = x ]; then
    [[ "$FTLB_BUILD_JOBS" =~ ^[1-9][0-9]*$ ]] \
      || die "FTLB_BUILD_JOBS must be a positive integer"
    BUILD_RESOURCES+=(-e "FTLB_BUILD_JOBS=$FTLB_BUILD_JOBS" -e "VCPKG_MAX_CONCURRENCY=$FTLB_BUILD_JOBS")
    BUILD_INNER='ninja() { command ninja -j "$FTLB_BUILD_JOBS" "$@"; }; export -f ninja; source .devcontainer/devcontainer-fixes.sh && buildscripts/windows/build-releaseonly.sh'
  fi
  [[ "$DEVCONTAINER" =~ ^[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}$ ]] \
    || die "set DEVCONTAINER to an immutable registry/repository@sha256:<digest>; a tag or local image ID is insufficient"
  command -v docker >/dev/null 2>&1 || die "docker not found in WSL. Install Docker Desktop (enable WSL integration) or 'sudo apt-get install -y docker.io && sudo usermod -aG docker $USER' then re-login."
  docker info >/dev/null 2>&1 || die "docker daemon not reachable. Start Docker Desktop (or 'sudo service docker start') and re-run 'build'."
  command -v python3 >/dev/null 2>&1 || die "python3 is required to validate the versioned native patch"
  load_native_pins
  python3 "$FTLB/scripts/apply_native_patch.py" --source "$HS" --require-base || die "native base/patch conflicts; existing source changes were preserved"
  docker pull --platform linux/amd64 "$DEVCONTAINER" || die "declared immutable toolchain image unavailable"
  BUILD_EVIDENCE_ROOT="$FTLB"
  BUILD_ARCHIVE="$FTLB/dist/native-build-evidence/build-$(date -u +%Y%m%dT%H%M%S%NZ)-$$-$RANDOM"
  python3 -B "$FTLB/scripts/archive_native_build.py" prepare --source "$HS" --source-root "$FTLB" \
    --evidence-root "$BUILD_EVIDENCE_ROOT" --output "$BUILD_ARCHIVE" \
    || die "could not exclusively archive original native build sources"
  # Bypass the upstream Docker wrapper, which selects a mutable v2 tag.
  BUILD_CMD=(docker run --rm --platform linux/amd64
    "${BUILD_RESOURCES[@]}"
    -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspaces/FTL-Hyperspace \
    -v "$HS:/workspaces/FTL-Hyperspace" -w /workspaces/FTL-Hyperspace
    "$DEVCONTAINER" bash -c "$BUILD_INNER")
  "${BUILD_CMD[@]}" || die "Hyperspace.dll build failed"
  printf -v BUILD_COMMAND '%q ' "${BUILD_CMD[@]}"
  DLL="$HS/build-windows-release/Hyperspace.dll"
  [ -f "$DLL" ] || die "expected $DLL, not produced"
  PROVENANCE="$BUILD_ARCHIVE/native-build.visual-v1.json"
  python3 "$FTLB/scripts/write_native_provenance.py" --source "$HS" --dll "$DLL" --output "$PROVENANCE" \
    --image "$DEVCONTAINER" --require-base --require-immutable-image \
    --build-command "$BUILD_COMMAND" \
    || die "could not record native build provenance"
  python3 -B "$FTLB/scripts/archive_native_build.py" finish --source "$HS" --source-root "$FTLB" \
    --evidence-root "$BUILD_EVIDENCE_ROOT" --output "$BUILD_ARCHIVE" \
    --dll "$DLL" --provenance "$PROVENANCE" \
    || die "native build source/provenance archive verification failed"
  python3 "$FTLB/scripts/stage_native_artifacts.py" stage \
    --dll "$BUILD_ARCHIVE/artifacts/Hyperspace.visual-v1.dll" \
    --provenance "$BUILD_ARCHIVE/artifacts/native-build.visual-v1.json" \
    || die "could not stage the visual DLL/provenance pair"
  ok "built and staged visual-v1 DLL/provenance; original build origin: $BUILD_ARCHIVE/build-origin.json; live acceptance is still required"
fi

# ===========================================================================
# STAGE datamod — package Hyperspace.ftl to MATCH the DLL we just built
# ===========================================================================
if want datamod; then
  log "datamod: package Hyperspace.ftl from Mod Files/ (matches the built DLL)"
  command -v zip >/dev/null 2>&1 || { sudo apt-get install -y zip; }
  # Docker may own the native build directory. Package only into caller-owned
  # benchmark dist, leaving native output and Mod Files untouched.
  mkdir -p "$FTLB/dist" || die "could not create benchmark dist"
  HSFTL="$FTLB/dist/Hyperspace.ftl"
  [ ! -L "$FTLB/dist" ] && [ ! -L "$HSFTL" ] \
    && { [ ! -e "$HSFTL" ] || [ -f "$HSFTL" ]; } || die "unsafe Hyperspace data-mod output"
  (
    package_dir="$(mktemp -d "$FTLB/dist/.hyperspace-package.XXXXXX")" || exit 1
    trap 'rm -f -- "$package_dir/Hyperspace.ftl"; rmdir -- "$package_dir"' EXIT
    cd "$HS/Mod Files" || exit 1
    zip -rq "$package_dir/Hyperspace.ftl" . -x Hyperspace.ftl || exit 1
    mv -f -- "$package_dir/Hyperspace.ftl" "$HSFTL"
  ) && ok "Hyperspace.ftl packaged ($(du -h "$HSFTL" | cut -f1))" \
    || die "Hyperspace data-mod packaging failed"
  python3 -B "$FTLB/scripts/package_bridge.py" --source-root "$FTLB" \
    --output "$FTLB/dist/ftl_bench_bridge.ftl" || die "bridge data-mod packaging failed"
  ok "ftl_bench_bridge.ftl packaged from tracked bridge inputs"
fi

# ===========================================================================
# STAGE locate — find the Windows FTL game dir + data file
# ===========================================================================
GAME="${FTL_GAME_DIR:-${GAME:-}}"; FTLDAT=""; SAVE=""
locate_game() {
  local cands=(
    "/mnt/c/Program Files (x86)/Steam/steamapps/common/FTL Faster Than Light"
    "/mnt/c/Program Files/Steam/steamapps/common/FTL Faster Than Light"
  )
  if [ -n "$GAME" ]; then
    [ -d "$GAME" ] && [ -f "$GAME/FTLGame.exe" ] \
      || die "explicit FTL_GAME_DIR/GAME is not a Windows FTL install: $GAME"
  else
    for d in "${cands[@]}"; do [ -d "$d" ] && { GAME="$d"; break; }; done
  fi
  [ -z "$GAME" ] && GAME="$(find /mnt/c -maxdepth 6 -type d -name 'FTL Faster Than Light' 2>/dev/null | head -1)"
  [ -n "$GAME" ] || return 1
  # FTL 1.6.x: ftl.dat lives in the game root (post-downgrade 1.6.9 too)
  for c in "$GAME/ftl.dat" "$GAME/resources/ftl.dat" "$GAME/data/ftl.dat"; do
    [ -f "$c" ] && { FTLDAT="$c"; break; }
  done
  local wu; wu="$(detect_win_user)"
  SAVE="/mnt/c/Users/$wu/Documents/My Games/FasterThanLight"
}
if want locate; then
  log "locate: Windows FTL install + data + save dir"
  locate_game || die "FTL install not found under /mnt/c. Set FTL_GAME_DIR to its WSL path and re-run."
  ok "game:   $GAME"
  ok "ftl.dat:$FTLDAT  $( [ -n "$FTLDAT" ] || echo '(not found yet — appears after downgrade)')"
  ok "save:   $SAVE  $( [ -d "$SAVE" ] && echo '(exists)' || echo '(will be created on first launch)')"
  ls "$GAME/FTLGame.exe" >/dev/null 2>&1 && ok "FTLGame.exe present" || warn "FTLGame.exe not in game dir?"
fi

# ===========================================================================
# STAGE install — generate + run the elevated Windows installer
#   (downgrade to 1.6.9 + drop loader proxy + our Hyperspace.dll)
# ===========================================================================
if want install; then
  log "install: loader + DLL into the game dir (needs Windows admin)"
  [ -n "$GAME" ] || locate_game || die "run 'locate' first"
  REL="$HS/Release Files/Windows"
  DLL="$FTLB/dist/Hyperspace.visual-v1.dll"
  PROVENANCE="$FTLB/dist/native-build.visual-v1.json"
  [ -f "$DLL" ] || die "build the DLL first (stage build)"
  python3 "$FTLB/scripts/stage_native_artifacts.py" verify --dll "$DLL" --provenance "$PROVENANCE" \
    || die "staged visual pair is invalid; run stage build first"
  # WSL must inspect the Windows process, not pgrep a Linux/macOS process name.
  live_processes="$(/mnt/c/Windows/System32/tasklist.exe /fi 'imagename eq FTLGame.exe' 2>/dev/null)" \
    || die "cannot verify FTL is closed; no installation changes made"
  case "$live_processes" in *FTLGame.exe*) die "close FTL before installing native files";; esac
  # stage the files to copy into a temp dir on C: that the .bat will read
  STAGEDIR="/mnt/c/ftl_bench_install"
  mkdir -p "$STAGEDIR"
  cp "$REL/xinput1_4.dll" "$REL/lua-5.3.dll" "$REL/downgrade.bat" "$STAGEDIR/" 2>/dev/null
  cp -r "$REL/patch" "$STAGEDIR/" 2>/dev/null
  # convert the WSL game path to a Windows path for the .bat
  GAME_WIN="$(wslpath -w "$GAME")"
  BAT="$STAGEDIR/install_into_game.bat"
  cat > "$BAT" <<EOF
@echo off
REM ftl_bench — Windows-side install (run as Administrator)
set GAME=$GAME_WIN
echo Installing into "%GAME%"
cd /d "%GAME%"
echo --- downgrading FTL to 1.6.9 (if not already) ---
if not exist FTLGame_orig.exe ( copy /Y "C:\\ftl_bench_install\\downgrade.bat" downgrade.bat >nul & call downgrade.bat ) else ( echo already downgraded )
echo --- copying Hyperspace loader ---
copy /Y "C:\\ftl_bench_install\\xinput1_4.dll" . >nul
copy /Y "C:\\ftl_bench_install\\lua-5.3.dll" . >nul
xcopy /E /I /Y "C:\\ftl_bench_install\\patch" patch >nul
echo --- done ---
exit /b %errorlevel%
EOF
  ok "generated $BAT"
  warn "running it elevated (accept the UAC prompt on the PC)..."
  # try to launch elevated; user must click 'Yes' on the UAC dialog
  powershell.exe -NoProfile -Command '$nativeLoader = Start-Process -WindowStyle Hidden -Wait -PassThru -Verb RunAs -FilePath cmd.exe -ArgumentList "/c","C:\ftl_bench_install\install_into_game.bat"; exit $nativeLoader.ExitCode' 2>/dev/null \
    || die "loader installation failed or elevation was declined; native DLL was not replaced"
  # Install the verified DLL and matching provenance through the same backed-up
  # code path used by native Windows. FTL_SAVE_DIR activates Windows process checks.
  FTL_SAVE_DIR="$SAVE" PYTHONPATH="$FTLB/harness/src" python3 -m ftl_bench.cli install-native \
    --dll "$DLL" --manifest "$PROVENANCE" --game-dir "$GAME" \
    || die "verified native installation failed; inspect the reported error"
  ok "native DLL and matching provenance installed with retained backups"
fi

# ===========================================================================
# STAGE patch — patch ftl.dat with Hyperspace.ftl + ftl_bench_bridge.ftl
#   (FTLMan Linux binary, run from WSL against the Windows ftl.dat)
# ===========================================================================
if want patch; then
  log "patch: ftl.dat <- Hyperspace.ftl + ftl_bench_bridge.ftl (FTLMan, from WSL)"
  [ -n "$GAME" ] || locate_game || true
  # re-find ftl.dat (it appears/relocates after the downgrade)
  for c in "$GAME/ftl.dat" "$GAME/resources/ftl.dat" "$GAME/data/ftl.dat"; do
    [ -f "$c" ] && { FTLDAT="$c"; break; }
  done
  [ -n "$FTLDAT" ] || die "ftl.dat not found under $GAME — run the install/downgrade first."
  DATADIR="$(dirname "$FTLDAT")"
  [ -n "$FTLMAN" ] && [ -f "$FTLMAN" ] && [ -x "$FTLMAN" ] \
    || die "set FTLMAN to a caller-provided executable Linux FTLMan file"
  [[ "$FTLMAN_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] \
    || die "set FTLMAN_SHA256 to the exact executable SHA-256"
  FM="$(realpath -- "$FTLMAN")" || die "cannot resolve FTLMan input"
  fm_actual="$(sha256sum -- "$FM")" || die "cannot hash FTLMan input"
  fm_actual="${fm_actual%% *}"
  [ "$fm_actual" = "${FTLMAN_SHA256,,}" ] || die "FTLMan SHA-256 mismatch; no patch performed"
  live_processes="$(/mnt/c/Windows/System32/tasklist.exe /fi 'imagename eq FTLGame.exe' 2>/dev/null)" \
    || die "cannot verify FTL is closed; no patch performed"
  case "${live_processes,,}" in *ftlgame.exe*) die "close FTL before patching data";; esac
  HSFTL="$FTLB/dist/Hyperspace.ftl"
  BRIDGE="$FTLB/dist/ftl_bench_bridge.ftl"
  [ -f "$HSFTL" ] && [ -f "$BRIDGE" ] || die "missing data mods ($HSFTL / $BRIDGE) — run 'datamod'."
  mkdir -p "$FTLB/dist" || die "cannot create patch-input receipt directory"
  INPUT_RECEIPT="$(mktemp "$FTLB/dist/setup-patch-inputs.XXXXXXXX.json")" \
    || die "cannot reserve patch-input receipt"
  python3 - "$INPUT_RECEIPT" "$FM" "$fm_actual" "$HSFTL" "$BRIDGE" "$FTLDAT" <<'PY'
import hashlib, json, pathlib, sys
receipt, tool, expected, hs, bridge, data = sys.argv[1:]
def identity(name):
    path = pathlib.Path(name)
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
inputs = {"ftlman": identity(tool), "hyperspace_mod": identity(hs),
          "bridge_mod": identity(bridge), "ftl_dat_before": identity(data)}
if inputs["ftlman"]["sha256"] != expected:
    raise SystemExit("FTLMan changed after verification; no patch performed")
pathlib.Path(receipt).write_text(json.dumps({"contract": "setup-patch-inputs-v1",
    "inputs": inputs, "scope": "Pinned inputs before patch; not installation or live acceptance."}, indent=2) + "\n")
PY
  [ "$?" = 0 ] || die "cannot record verified patch inputs; no patch performed"
  ok "pinned patch inputs: $INPUT_RECEIPT"
  "$FM" patch "$HSFTL" "$BRIDGE" -d "$DATADIR" \
    && ok "ftl.dat patched (FTLMan keeps ftl.dat.vanilla for idempotent re-patch)" \
    || die "FTLMan patch failed"
fi

# ===========================================================================
# STAGE deploy — drop the dev lua + point the harness at the Windows save dir
# ===========================================================================
if want deploy; then
  log "deploy: dev lua -> Windows save dir + harness config"
  [ -n "$SAVE" ] || { locate_game; }
  mkdir -p "$SAVE" 2>/dev/null
  SRC="$FTLB/mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
  [ -f "$SRC" ] && cp "$SRC" "$SAVE/ftl_bench_dev.lua" && : > "$SAVE/ftl_bench_reload" \
    && ok "ftl_bench_dev.lua deployed to $SAVE" || warn "dev lua not found at $SRC"
  # persist the save dir for the harness
  echo "export FTL_SAVE_DIR=\"$SAVE\"" > "$FTLB/.env.pc"
  ok "wrote $FTLB/.env.pc (source it before running the harness)"
fi

# ===========================================================================
# STAGE verify — sanity checks
# ===========================================================================
if want verify; then
  log "verify: install sanity"
  [ -n "$GAME" ] || locate_game || true
  for f in FTLGame.exe FTLGame_orig.exe xinput1_4.dll lua-5.3.dll Hyperspace.dll; do
    [ -e "$GAME/$f" ] && ok "game/$f" || warn "game/$f MISSING"
  done
  [ -f "$GAME/ftl.dat.vanilla" ] && ok "ftl.dat.vanilla (patched, revertible)" || warn "ftl.dat not patched yet"
  echo
  echo "NEXT (on the PC):"
  echo "  1. Launch FTL from Steam (or run FTLGame.exe). The xinput1_4.dll proxy injects Hyperspace."
  echo "     (GUI needs WSLg or a Windows-side launch; from WSL: cmd.exe /c start \"\" \"\$(wslpath -w \"$GAME\")\\FTLGame.exe\")"
  echo "  2. From WSL:  source $FTLB/.env.pc && bash $FTLB/scripts/verify_observation.sh \"$SAVE/ftl_agent_observation.json\""
  echo "  3. Run a scripted game and compare crash rate to macOS:"
  echo "     source $FTLB/.env.pc && python3 $FTLB/adapter/run_benchmark.py --agent scripted ..."
fi

log "bootstrap stages complete: $RUN"
