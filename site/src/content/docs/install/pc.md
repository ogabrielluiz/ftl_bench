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

# Clone the declared native base, build/stage and package mods without installing.
FTLB_BUILD_MEMORY=3g FTLB_BUILD_CPUS=1 FTLB_BUILD_JOBS=1 \
  STAGES="repos build datamod" bash scripts/setup_pc.sh
```

The build wrapper defaults to no explicit container resource caps. Optional
`FTLB_BUILD_MEMORY=3g` sets both Docker `--memory 3g` and `--memory-swap 3g`,
allowing no additional container swap; optional `FTLB_BUILD_CPUS=1` sets a numeric
CPU quota, not a single compiler job. Memory must be a positive integer with an
explicit lowercase `m` or `g` suffix; CPU quota must be a positive integer.
`FTLB_BUILD_JOBS` is a separate positive integer: it forwards `-j` to Ninja
through the upstream Bash build scripts and sets `VCPKG_MAX_CONCURRENCY` for
dependency builds. Unset jobs preserve the upstream command. Memory/CPU limits
apply to the build container, not the whole WSL/Docker VM. An actual fresh build
with 3 GiB / one CPU and no job limit exhausted container memory on 2026-10-14;
five compiler processes were killed. The single-job recipe still requires an
actual successful-build check before its resource requirements are established.
Resource caps do not change the pinned image or declared native base.

Python 3, Git, Docker and `zip` must be available for this build/package window
(along with the shell utilities listed below). A locally supplied official `zip`
package on `PATH` is acceptable. Use the explicit `repos build datamod` stage list
above to avoid modifying the game installation or launching FTL; the wrapper
still patches the selected native sources and stages benchmark artifacts.

Run the script from the benchmark revision you intend to build. It selects its
own real repository root by default, including a Git worktree whose `.git` is a
file. `FTLB_ROOT=/absolute/path/to/checkout` explicitly selects another root;
`PROJ` separately chooses the native checkout location. Existing benchmark HEAD
and local edits are preserved: `repos` never pulls, resets or checks out a new
benchmark revision. Record and review `git rev-parse HEAD` and `git status` before
setup. A standalone copied bootstrap without its repository falls back to
`$PROJ/ftl_bench`, cloning there only when no Git checkout exists; clone failure
is fatal. Select the intended cloned benchmark revision before a build-only
invocation.

`native/manifest.json` declares the native repository, exact base commit and cumulative patch hash. Fresh native clones check out that commit in detached mode. An existing checkout at another commit is refused; the script does not reset it or discard local edits. Compatible local changes at the declared base remain recorded in the source diff and file hashes, so that alone does not establish an exact accepted source tree.

The build uses the supplied immutable image reference directly, bypassing the upstream wrapper's mutable tag. It applies the complete patch selected by the manifest, currently `native/patches/0003-visual-io.patch`. This retains structured protocol-5 controls and adds visual I/O, fixed clock 2 at 1/60 second per update, and fresh-start seed contract v3. Do not stack the historical `0001` or structured-only `0002` patches onto it.

On 2026-10-11, a remote metadata query verified that the immutable manifest above selects the `linux/amd64` image configuration `sha256:f359f36f9eae862d65a133cb9b9076590e2f194f1357f700af3a7db0457c8061`. That is both the locally cached Ubuntu image ID and the image ID recorded by the historical accepted native build. The decoded raw manifest's SHA-256 equals the registry digest. The successful remote query used the Windows Docker CLI; the Ubuntu registry query failed with a routing error.

The local evidence is `dist/native-toolchain-mapping-20261011T034047Z/mapping-receipt.json` (SHA-256 `3f5c98ba7b4f6468fdb51271d1bf1f8e11f98cf7cca89fbda98e246af43a0ac4`), with the cached image inspection, remote manifest and historical build-manifest snapshot beside it. This generated receipt is not included in a fresh clone. It adds a verified registry-to-image mapping; the old provenance still records its original mutable tag and image ID and remains unchanged.

The 2026-10-11 query established **metadata identity** only. On 2026-10-14 Docker recovered after its inaccessible runtime sockets were preserved and recreated. The pinned image layers downloaded, dependencies built, and the fresh native compilation then failed at its container memory limit. The failed source tree, build command, log and kernel OOM evidence remain retained. No successful DLL, installation or acceptance resulted from that attempt. See [current build evidence](https://github.com/ogabrielluiz/ftl_bench/blob/main/docs/NEXT.md#resumed-validation-and-build-attempt-2026-10-14).

The optional durability stage uses `configure_wsl_idle.py` to insert a missing
`vmIdleTimeout=-1` into a unique `[wsl2]` section while preserving other settings,
comments and line endings. Explicit timeout values are preserved. Malformed or
ambiguous files are refused, and a standalone bootstrap without the helper or
Python warns without modifying the file. Applying configuration to a running VM
requires a separately scheduled WSL restart; setup does not restart it.

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

## Package and patch data mods in WSL

A fresh clone has no generated bridge `.ftl`. The `datamod` stage now invokes
`scripts/package_bridge.py` to produce `dist/ftl_bench_bridge.ftl` deterministically
from tracked bridge data and metadata. The external development Lua remains a
separate deployment input. Python 3, Git, `zip`, `sha256sum`, `realpath`, `mktemp`
and Windows/WSL interop are required for these stages; the native source checkout
and its `build-windows-release` directory must already exist.

Supply a Linux FTLMan executable obtained and reviewed separately, plus its exact
SHA-256. Setup does not acquire FTLMan from the network or select a latest release.
A hash pins supplied bytes; it does not establish publisher trust. Replace the
placeholders with your local executable and independently checked digest:

```bash
export PROJ="$HOME/projects"
export FTLMAN='/absolute/path/to/ftlman'
# Optional non-default install: use its WSL-mounted path (GAME is an alias).
export FTL_GAME_DIR='/mnt/d/SteamLibrary/steamapps/common/FTL Faster Than Light'
export FTLMAN_SHA256='<64-hex-SHA256-of-that-executable>'
sha256sum -- "$FTLMAN"
STAGES="datamod" bash scripts/setup_pc.sh
# After loader/native installation, with Windows FTL closed:
STAGES="locate patch" bash scripts/setup_pc.sh
```

The patch stage refuses a missing/non-executable tool, missing or mismatched hash,
active `FTLGame.exe`, or an unavailable Windows process check before invoking
FTLMan. It records tool path/hash/size, both data-mod hashes and pre-patch data
identity in a unique `dist/setup-patch-inputs.*.json` receipt. This records inputs,
not successful installation or live acceptance. Review the receipt and patch
command result; the patcher retains `ftl.dat.vanilla` for its own re-patching flow.
Only the patch stage needs `FTLMAN` and `FTLMAN_SHA256`.

To package the bridge without other setup stages, run
`python3 scripts/package_bridge.py --output dist/ftl_bench_bridge.ftl` from the
repository root. The archive retains `data/hyperspace.xml.append` and the runtime
Lua files with fixed ZIP metadata and sorted paths. Identical repeats leave the
output untouched; changed inputs replace it atomically. Packaging neither
installs the mod nor establishes native acceptance. An explicit
`FTL_GAME_DIR` (or `GAME` alias) must contain `FTLGame.exe`; an invalid override
fails instead of searching unrelated installations. Omit it for default C-drive
discovery. The printed WSL observation check passes the Windows save folder
observation filename explicitly, rather than the verifier's historical macOS
default.

The build stage also reserves an exclusive
`dist/native-build-evidence/build-<UTC>-<process>-<random>/` archive before Docker
compilation. `archive_native_build.py prepare` retains the original patched
source bytes; provenance is written directly to that archive rather than
replacing an original record in the reusable native build directory. `finish`
requires unchanged before/after sources and matching provenance/DLL identity,
retains the artifact bytes and emits `build-origin.json` with hashed fresh-origin
references relative to the benchmark repository root. A failed build leaves its
preparation evidence intact; use a new archive for a later attempt.

Use the benchmark repository root as the single `--evidence-root` for build
origin, source proof, startup/timing collection and admission references; keep
the complete referenced evidence and original build archive. Its generated build origin
is an input to the [portable admission workflow](https://github.com/ogabrielluiz/ftl_bench/blob/main/docs/native-acceptance.md),
not a passing admission by itself: collect source-bound startup and nine timing
probes, retain their producer descriptors and obtain independent review with
eight rejected mutations. Staging/setup never manufactures review or production
acceptance, and local evidence is not included in a fresh clone.

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
