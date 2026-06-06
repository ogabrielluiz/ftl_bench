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
#   ghcr.io/ftl-hyperspace/hs-devcontainer:v2. We pull it and run the repo's own
#   build script. Output: build-windows-release/Hyperspace.dll.
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
HS_REPO="https://github.com/ogabrielluiz/FTL-Hyperspace.git"
HS_BRANCH="bench"
DEVCONTAINER="ghcr.io/ftl-hyperspace/hs-devcontainer:v2"
FTLMAN_VER="${FTLMAN_VER:-}"   # empty = latest
WIN_USER="${WIN_USER:-}"        # auto-detected if empty

FTLB="$PROJ/ftl_bench"
HS="$PROJ/FTL-Hyperspace"

log()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '   \033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mFATAL: %s\033[0m\n' "$*" >&2; exit 1; }

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
    if ! grep -q 'vmIdleTimeout' "$WSLCONF" 2>/dev/null; then
      printf '[wsl2]\nvmIdleTimeout=-1\n' >> "$WSLCONF" 2>/dev/null \
        && ok ".wslconfig vmIdleTimeout=-1 (no idle shutdown) — effective after 'wsl --shutdown')" \
        || warn "could not write $WSLCONF (do it by hand)"
    else
      ok ".wslconfig already disables idle shutdown"
    fi
  else
    warn "could not detect Windows user dir; set WIN_USER=... and re-run durability"
  fi
fi

# ===========================================================================
# STAGE repos — clone/update both repos
# ===========================================================================
if want repos; then
  log "repos: clone/update ftl_bench (main) + FTL-Hyperspace ($HS_BRANCH)"
  mkdir -p "$PROJ"
  if [ -d "$FTLB/.git" ]; then (cd "$FTLB" && git pull --ff-only) && ok "ftl_bench updated"
  else git clone "$FTLB_REPO" "$FTLB" && ok "ftl_bench cloned"; fi
  if [ -d "$HS/.git" ]; then
    (cd "$HS" && git fetch origin && git checkout "$HS_BRANCH" && git pull --ff-only) && ok "Hyperspace @ $HS_BRANCH updated"
  else
    git clone --branch "$HS_BRANCH" "$HS_REPO" "$HS" && ok "Hyperspace cloned @ $HS_BRANCH"
  fi
  (cd "$HS" && echo "   HEAD: $(git log --oneline -1)")
fi

# ===========================================================================
# STAGE build — Hyperspace.dll via the devcontainer (Docker / MinGW)
# ===========================================================================
if want build; then
  log "build: Hyperspace.dll (Docker devcontainer, MinGW cross-compile)"
  command -v docker >/dev/null 2>&1 || die "docker not found in WSL. Install Docker Desktop (enable WSL integration) or 'sudo apt-get install -y docker.io && sudo usermod -aG docker $USER' then re-login."
  docker info >/dev/null 2>&1 || die "docker daemon not reachable. Start Docker Desktop (or 'sudo service docker start') and re-run 'build'."
  docker pull "$DEVCONTAINER" && ok "devcontainer image present"
  (cd "$HS" && buildscripts/windows/build-releaseonly-from-docker.sh) || die "Hyperspace.dll build failed"
  DLL="$HS/build-windows-release/Hyperspace.dll"
  [ -f "$DLL" ] || die "expected $DLL, not produced"
  ok "built $(du -h "$DLL" | cut -f1) Hyperspace.dll"
fi

# ===========================================================================
# STAGE datamod — package Hyperspace.ftl to MATCH the DLL we just built
# ===========================================================================
if want datamod; then
  log "datamod: package Hyperspace.ftl from Mod Files/ (matches the built DLL)"
  command -v zip >/dev/null 2>&1 || { sudo apt-get install -y zip; }
  ( cd "$HS/Mod Files" && rm -f Hyperspace.ftl && zip -rq ../build-windows-release/Hyperspace.ftl . -x Hyperspace.ftl ) \
    && ok "Hyperspace.ftl packaged ($(du -h "$HS/build-windows-release/Hyperspace.ftl" | cut -f1))"
  # bench bridge mod is in the ftl_bench dist (platform-independent)
  [ -f "$FTLB/dist/ftl_bench_bridge.ftl" ] && ok "ftl_bench_bridge.ftl present (reused)" \
    || warn "dist/ftl_bench_bridge.ftl missing — re-run its packaging in ftl_bench"
fi

# ===========================================================================
# STAGE locate — find the Windows FTL game dir + data file
# ===========================================================================
GAME=""; FTLDAT=""; SAVE=""
locate_game() {
  local cands=(
    "/mnt/c/Program Files (x86)/Steam/steamapps/common/FTL Faster Than Light"
    "/mnt/c/Program Files/Steam/steamapps/common/FTL Faster Than Light"
  )
  for d in "${cands[@]}"; do [ -d "$d" ] && { GAME="$d"; break; }; done
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
  locate_game || die "FTL install not found under /mnt/c. Set GAME=... and re-run."
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
  DLL="$HS/build-windows-release/Hyperspace.dll"
  [ -f "$DLL" ] || die "build the DLL first (stage build)"
  # stage the files to copy into a temp dir on C: that the .bat will read
  STAGEDIR="/mnt/c/ftl_bench_install"
  mkdir -p "$STAGEDIR"
  cp "$REL/xinput1_4.dll" "$REL/lua-5.3.dll" "$REL/downgrade.bat" "$STAGEDIR/" 2>/dev/null
  cp -r "$REL/patch" "$STAGEDIR/" 2>/dev/null
  cp "$DLL" "$STAGEDIR/Hyperspace.dll"
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
echo --- copying Hyperspace loader + DLL ---
copy /Y "C:\\ftl_bench_install\\xinput1_4.dll" . >nul
copy /Y "C:\\ftl_bench_install\\lua-5.3.dll" . >nul
copy /Y "C:\\ftl_bench_install\\Hyperspace.dll" . >nul
xcopy /E /I /Y "C:\\ftl_bench_install\\patch" patch >nul
echo --- done ---
echo You can close this window.
pause
EOF
  ok "generated $BAT"
  warn "running it elevated (accept the UAC prompt on the PC)..."
  # try to launch elevated; user must click 'Yes' on the UAC dialog
  powershell.exe -NoProfile -Command "Start-Process -Verb RunAs -FilePath cmd.exe -ArgumentList '/c','C:\\ftl_bench_install\\install_into_game.bat'" 2>/dev/null \
    && ok "elevated installer launched (watch the PC for the UAC prompt + window)" \
    || warn "could not auto-elevate. On the PC: right-click C:\\ftl_bench_install\\install_into_game.bat -> Run as administrator"
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
  # get FTLMan (Linux) once
  FM="$HOME/.local/bin/ftlman"
  if [ ! -x "$FM" ]; then
    mkdir -p "$HOME/.local/bin"
    url="$(curl -fsSL https://api.github.com/repos/afishhh/ftlman/releases/latest \
            | grep -oE 'https://[^"]*x86_64[^"]*linux[^"]*\.tar\.gz' | head -1)"
    [ -n "$url" ] || die "could not resolve FTLMan linux download URL"
    curl -fsSL "$url" -o /tmp/ftlman.tgz && tar -xzf /tmp/ftlman.tgz -C /tmp
    f="$(find /tmp -maxdepth 2 -name ftlman -type f 2>/dev/null | head -1)"
    cp "$f" "$FM" && chmod +x "$FM" && ok "FTLMan installed -> $FM"
  fi
  HSFTL="$HS/build-windows-release/Hyperspace.ftl"
  BRIDGE="$FTLB/dist/ftl_bench_bridge.ftl"
  [ -f "$HSFTL" ] && [ -f "$BRIDGE" ] || die "missing data mods ($HSFTL / $BRIDGE) — run 'datamod'."
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
  echo "  2. From WSL:  source $FTLB/.env.pc && bash $FTLB/scripts/verify_observation.sh"
  echo "  3. Run a scripted game and compare crash rate to macOS:"
  echo "     source $FTLB/.env.pc && python3 $FTLB/adapter/run_benchmark.py --agent scripted ..."
fi

log "bootstrap stages complete: $RUN"
