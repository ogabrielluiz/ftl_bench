---
title: Install on a PC (native x86)
description: Set up FTL + Hyperspace on Windows. Runs natively (no WSL needed for runs); native x86 avoids the macOS/Rosetta freeze class.
---

The recommended platform is **native x86 on Windows**. Native x86 avoids the address-translation
crash class that freezes sector transitions when FTL runs under Rosetta on Apple Silicon, so
full-length runs are stable.

There are two phases, and they are independent:

- **Install (one-time):** build the bench Hyperspace mod and patch the game. This currently uses
  WSL + Docker (a prebuilt mod that skips the build is planned).
- **Run:** drive the benchmark. This works on **native Windows Python with no WSL and no env
  vars**, and also from WSL or macOS.

## Install (one-time, via WSL + Docker)

You need Windows with FTL installed via Steam, plus WSL (Ubuntu) with Docker available (Docker
Desktop with WSL integration, or `docker.io`) and `python3`/`git`/`curl`. The Hyperspace build
runs in a container, so you do not install a C++ toolchain by hand.

`scripts/setup_pc.sh` does the whole install and is idempotent (safe to re-run). From WSL:

```bash
bash scripts/setup_pc.sh          # run every stage
bash scripts/setup_pc.sh build    # or run from a given stage onward
```

Stages, in order:

1. **durability**: keep WSL reachable (ssh on boot, disable WSL2 idle shutdown).
2. **repos**: clone/update `ftl_bench` and the Hyperspace fork.
3. **build**: build `Hyperspace.dll` in the Docker devcontainer (MinGW cross-compile).
4. **datamod**: package the `Hyperspace.ftl` and `ftl_bench_bridge.ftl` data mods.
5. **locate**: find the Windows FTL install, its `ftl.dat`, and the save folder.
6. **install**: downgrade FTL to 1.6.9 and drop the loader (`xinput1_4.dll`, `lua-5.3.dll`) plus
   `Hyperspace.dll` next to `FTLGame.exe`.
7. **patch**: patch `ftl.dat` with the two data mods.
8. **deploy**: install the dev script into the save folder.
9. **verify**: sanity checks.

## Run (native Windows, no WSL)

Once the mod is installed, run the benchmark with **native Windows Python** (for example via `uv`).
The runner detects native Windows automatically: it finds the FTL user folder at
`~/Documents/My Games/FasterThanLight`, so you do not set `FTL_SAVE_DIR`, and it launches and
restarts FTL through Steam itself.

```bash
cd harness
uv run python ../adapter/play_cli.py obs                       # live observation
uv run python ../adapter/run_benchmark.py --agent scripted --max-instances 1 --budget-cap 8
```

(Running from WSL or macOS also works; on WSL set `FTL_SAVE_DIR` to the `/mnt/c/...` user folder,
which `setup_pc.sh` writes to `.env.pc`.)

## How it loads (important)

FTL must be launched **through Steam** for Hyperspace to inject. FTL loads xinput at runtime, and
only the Steam launch picks up the local proxy DLL that loads `Hyperspace.dll`. A direct
`FTLGame.exe` launch loads the system xinput instead and Hyperspace never injects. The runner does
the Steam launch (`steam.exe -applaunch 212680`) for you, clears the stale crash flag, redeploys
the dev script, and waits for the bridge, so you do not launch the game by hand.

Then head to the [Quickstart](/evaluate/quickstart/) to run your model.
