---
title: Install on Windows
description: Pin native build inputs, stage the visual DLL and provenance, and install the local runner.
---

Native Windows x86 with FTL **1.6.9**, launched through Steam, is the current full-game validation target. The Python runner needs 3.11+. WSL and Docker are used for building the native dependency; they are not required for native Windows benchmark runs.

## Build the native environment

Install FTL through Steam. The setup script handles the Hyperspace build, loader, data mods and Lua bridge. Select a **registry digest**, rather than a mutable image tag or a local Docker image ID, before the build stage:

```bash
# In WSL, select the historical toolchain whose registry identity was verified.
export DEVCONTAINER='ghcr.io/ftl-hyperspace/hs-devcontainer@sha256:9fc15466b3591395209a479cfbcd50bb78b47d5b78d983c4740cd00acce8aca2'
docker manifest inspect --verbose "$DEVCONTAINER"
docker pull --platform linux/amd64 "$DEVCONTAINER"
docker image inspect "$DEVCONTAINER" --format '{{.Id}} {{json .RepoDigests}}'

# Clone the declared native base, build, and stage artifacts without installing.
STAGES="repos build" bash scripts/setup_pc.sh
```

`native/manifest.json` declares the native repository, exact base commit and cumulative patch hash. Fresh native clones check out that commit in detached mode. An existing checkout at another commit is refused; the script does not reset it or discard local edits. Compatible local changes at the declared base remain recorded in the source diff and file hashes, so that alone does not establish an exact accepted source tree.

The build uses the supplied immutable image reference directly, bypassing the upstream wrapper's mutable tag. It applies the complete patch selected by the manifest, currently `native/patches/0003-visual-io.patch`. This retains structured protocol-5 controls and adds visual I/O, fixed clock 2 at 1/60 second per update, and fresh-start seed contract v3. Do not stack the historical `0001` or structured-only `0002` patches onto it.

On 2026-10-11, a remote metadata query verified that the immutable manifest above selects the `linux/amd64` image configuration `sha256:f359f36f9eae862d65a133cb9b9076590e2f194f1357f700af3a7db0457c8061`. That is both the locally cached Ubuntu image ID and the image ID recorded by the historical accepted native build. The decoded raw manifest's SHA-256 equals the registry digest. The successful remote query used the Windows Docker CLI; the Ubuntu registry query failed with a routing error.

The local evidence is `dist/native-toolchain-mapping-20261011T034047Z/mapping-receipt.json` (SHA-256 `3f5c98ba7b4f6468fdb51271d1bf1f8e11f98cf7cca89fbda98e246af43a0ac4`), with the cached image inspection, remote manifest and historical build-manifest snapshot beside it. This generated receipt is not included in a fresh clone. It adds a verified registry-to-image mapping; the old provenance still records its original mutable tag and image ID and remains unchanged.

This is **metadata verification**, not a fresh build or bit-for-bit DLL reproduction. No image layers were downloaded, and their remote availability was not checked. The isolated cached-only build plan remains unexecuted; complete offline dependency availability, the resulting DLL bytes and acceptance of a newly built runtime remain unproven.

For an existing Hyperspace source checkout:

```bash
python3 scripts/apply_native_patch.py --source /path/to/FTL-Hyperspace --check --require-base
python3 scripts/apply_native_patch.py --source /path/to/FTL-Hyperspace --require-base
```

The helper checks the patch SHA256, recognizes an already applied patch and refuses conflicts. `--require-base` also refuses a different source commit before applying anything. Manual patch/provenance use without the strict option remains available for diagnostics, but the bootstrap requires it. Provenance records the actual source commit, diff and patched-file hashes, immutable image reference, resolved image ID, build command, timestamp and DLL hash. Compiler identity is omitted unless supplied from an actual observation; the script does not assume the old compiler for a different image.

Successful bootstrap builds stage the current pair at `dist/Hyperspace.visual-v1.dll` and `dist/native-build.visual-v1.json`. `scripts/stage_native_artifacts.py` verifies that the DLL hash/size, source base, patch and declared capabilities agree before publishing. Replacing an existing pair retains its exact prior files under `dist/native-history/`; identical inputs are a no-op. The two files are not one atomic filesystem object: an observed publication error rolls back the old pair, and a crash between writes is caught by hash validation before installation.

Staging is a file-identity check, **not live native acceptance**. It neither installs the DLL nor creates an accepted experiment evidence bundle. Existing structured artifacts `dist/Hyperspace.protocol5.dll` and `dist/native-build.protocol5.json` are preserved. Historical protocol-4 files remain separate and cannot satisfy current visual startup.

To validate or stage an externally built pair using the same file-only path:

```bash
python3 scripts/stage_native_artifacts.py verify --dll /path/Hyperspace.dll --provenance /path/native-build.json
python3 scripts/stage_native_artifacts.py stage --dll /path/Hyperspace.dll --provenance /path/native-build.json
```

Other setup stages do not require `DEVCONTAINER`. `bash scripts/setup_pc.sh build` starts at build and continues through installation and deployment; use `STAGES="build"` for a build/stage-only run. Review the selected stages before running them.

## Install a locally built DLL

With FTL closed, install a built DLL and its matching provenance using the local native installer:

```powershell
ftlbench install-native --dll dist/Hyperspace.visual-v1.dll --manifest dist/native-build.visual-v1.json --game-dir "<FTL-install-directory>"
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
