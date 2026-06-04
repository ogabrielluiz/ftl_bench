#!/usr/bin/env bash
# ftl_bench — macOS install helper for Milestone 1 (Task 8 prep).
#
# Does the scriptable, app-side parts of the FTL-Hyperspace macOS install
# (Release Files/MacOS/README.txt steps 2-3 + 7):
#   - copy the built Hyperspace dylib + Hyperspace.command into FTL.app
#   - patch Info.plist CFBundleExecutable: FTL -> Hyperspace.command
#   - codesign the app
#
# It does NOT apply the data mods — that is the one GUI step (FTLMan), called
# out at the end. Run this AFTER FTL is installed.
#
# Usage:
#   scripts/install_macos.sh [/path/to/FTL.app]
# If no path is given, the Steam default is used.
set -euo pipefail

DIST="$(cd "$(dirname "$0")/../dist" && pwd)"
DYLIB="$DIST/Hyperspace.1.6.13.amd64.dylib"
COMMAND="$DIST/Hyperspace.command"

FTL_APP="${1:-$HOME/Library/Application Support/Steam/steamapps/common/FTL Faster Than Light/FTL.app}"

echo "== ftl_bench macOS install =="
echo "FTL.app: $FTL_APP"

[ -d "$FTL_APP" ] || { echo "ERROR: FTL.app not found at that path. Pass the path as arg 1."; exit 1; }
[ -f "$DYLIB" ]   || { echo "ERROR: dylib missing: $DYLIB (build Hyperspace first)"; exit 1; }
[ -f "$COMMAND" ] || { echo "ERROR: Hyperspace.command missing: $COMMAND"; exit 1; }

PLIST="$FTL_APP/Contents/Info.plist"
MACOS_DIR="$FTL_APP/Contents/MacOS"

VER="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$PLIST" 2>/dev/null || echo '?')"
echo "FTL CFBundleVersion: $VER"
if [ "$VER" != "1.6.13" ]; then
  echo "WARNING: this dylib is for FTL 1.6.13 but the app reports '$VER'."
  echo "         Build the matching dylib (STEAM_1_6_xx_BUILD) before proceeding. Aborting."
  exit 1
fi

echo "-- copying dylib + launcher into Contents/MacOS"
cp "$DYLIB" "$MACOS_DIR/"
cp "$COMMAND" "$MACOS_DIR/"
chmod +x "$MACOS_DIR/Hyperspace.command"

CURRENT_EXE="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$PLIST")"
echo "-- CFBundleExecutable is currently: $CURRENT_EXE"
if [ "$CURRENT_EXE" != "Hyperspace.command" ]; then
  /usr/libexec/PlistBuddy -c 'Set :CFBundleExecutable Hyperspace.command' "$PLIST"
  echo "   -> set to Hyperspace.command"
fi

echo "-- codesigning (required, or macOS refuses to launch)"
codesign -f -s - --timestamp=none --all-architectures --deep "$FTL_APP"

echo
echo "== app-side install DONE =="
echo
echo "NEXT (manual, GUI — the one step this script can't do):"
echo "  1. Install FTLMan: https://github.com/afishhh/ftlman/releases/latest"
echo "     (Apple Silicon: ftlman-aarch64-apple-darwin.tar.gz)"
echo "  2. In FTLMan, point it at: $FTL_APP/Contents/Resources/"
echo "  3. Put these two mods in FTLMan's mods/ folder and Apply IN THIS ORDER:"
echo "       a) $DIST/hyperspace.ftl"
echo "       b) $DIST/ftl_bench_bridge.ftl"
echo "  4. Launch FTL.app DIRECTLY (not via Steam), start a New Game."
echo "  5. Verify: scripts/verify_observation.sh"
