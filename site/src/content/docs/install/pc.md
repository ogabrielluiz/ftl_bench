---
title: Install on Windows
description: Build and verify the protocol-5 benchmark native dependency, bridge and local runner.
---

Native Windows x86 with FTL **1.6.9**, launched through Steam, is the current full-game validation target. The Python runner needs 3.11+. WSL and Docker are used for building the native dependency; they are not required for native Windows benchmark runs.

## Build the native environment

Install FTL through Steam. The source setup script handles the Hyperspace build, loader, data mods and Lua bridge:

```bash
# From the repository in WSL; review the stages before running
bash scripts/setup_pc.sh build
```

This starts at the build stage and continues through data-mod packaging, locating the game, native installation, data patching, bridge deployment and checks. A full invocation also performs the script's WSL/repository setup stages.

The build applies the complete `native/patches/0002-economy-fuel-controls.patch` before Docker compilation. Protocol 5 retains reliable control/setup/score/victory and adds exact native system/reactor upgrades and out-of-fuel Wait/distress actions. An older DLL is insufficient. This full patch supersedes `0001`; do not apply both patches to one checkout.

For an existing Hyperspace source checkout:

```bash
python3 scripts/apply_native_patch.py --source /path/to/FTL-Hyperspace --check
python3 scripts/apply_native_patch.py --source /path/to/FTL-Hyperspace
```

The helper checks the patch SHA256, recognizes an already applied patch and refuses conflicts. `native/manifest.json` pins the reference source/patch. Build provenance records the actual source commit and diff, toolchain/container image and DLL hash, even when a compatible cached checkout has a different base.

The current local artifact pair is `dist/Hyperspace.protocol5.dll` and `dist/native-build.protocol5.json`; the source setup script also writes current provenance to the latter path. Archived protocol-4 files remain separate: `native/manifest.protocol4.json`, the `0001` patch, `dist/Hyperspace.protocol4.dll`, `dist/native-build.json` and `dist/native-build.protocol4.json`.

## Install a locally built DLL

With FTL closed, install a built DLL and its matching provenance using the local native installer:

```powershell
ftlbench install-native --dll <Hyperspace.dll-path> --manifest <native-build.json-path> --game-dir "<FTL-install-directory>"
```

It verifies the DLL hash/protocol, refuses a running game and retains replaced artifacts. This installs the DLL and provenance; the loader and data mods must already be installed. The Python wheel does not contain FTL or Hyperspace.dll. `install-mod --url` only downloads a supplied asset and does not replace this setup.

## Deploy and verify

```powershell
uv sync --directory harness --extra dashboard --extra dev
uv run --directory harness ftlbench deploy-bridge
# Launch FTL through Steam
uv run --directory harness ftlbench doctor --live --full-game
uv run --directory harness ftlbench play obs
```

Bridge deployment backs up the previous external Lua script. Doctor is read-only and never calls a model. Its live checks require the actual bridge capabilities; a full-game check also requires victory reporting.

Runner/ruleset v7 requires current Lua crew guards plus `upgrade_rules`, `fuel_recovery`, `sector_navigation`, `beacon_navigation` and `enemy_hostility`. Deploy the current Lua script together with protocol 5. The `owned-player-crew-v1`, `native-economy-and-fuel-recovery-v1`, `native-sector-neighbors-v1`, `native-beacon-readiness-v1` and `native-enemy-hostility-v1` contracts are checked independently; passing an older installation check does not establish current compatibility.

Native Windows resolves the FTL user folder automatically. Use `FTL_SAVE_DIR` to override it; on WSL point this at the Windows user folder. `FTL_GAME_DIR` can select a non-default Steam installation.

The runner automatically verifies seed, ship and difficulty after reset. Only Kestrel A/easy is supported; unsupported requests fail before game setup. A valid installation check is distinct from a retained full-game win.

Then follow [Quickstart](/evaluate/quickstart/).
