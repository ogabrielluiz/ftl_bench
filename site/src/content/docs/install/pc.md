---
title: Install on a PC (native x86)
description: Set up FTL + Hyperspace natively on Windows / WSL, the recommended platform for ftl_bench.
---

The recommended way to run `ftl_bench` is **native x86 on Windows** (driven from WSL). Native x86
avoids the address-translation crash class that freezes sector transitions when FTL runs under
Rosetta on Apple Silicon, so full-length runs are stable.

You drive everything from a WSL shell; the game itself runs as a normal Windows process.

## What you need

- Windows with FTL installed via Steam, plus WSL (Ubuntu).
- Docker available inside WSL (Docker Desktop with WSL integration, or `docker.io`). The
  Hyperspace build runs in a container, so you do not install a C++ toolchain by hand.
- `python3`, `git`, and `curl` in WSL.

## One-shot bootstrap

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
7. **patch**: patch `ftl.dat` with the two data mods (FTLMan, run from WSL).
8. **deploy**: install the dev script into the save folder and point the harness at it.
9. **verify**: sanity checks.

## How it loads (important)

On Windows, FTL must be launched **through Steam** for Hyperspace to inject. FTL loads xinput at
runtime; only the Steam launch picks up the local proxy DLL that loads `Hyperspace.dll`. A direct
`FTLGame.exe` launch loads the system xinput instead and Hyperspace never injects.

The benchmark runner handles this for you: it launches and relaunches FTL via Steam
(`steam.exe -applaunch 212680`), clears the stale crash flag, redeploys the dev script, and waits
for the bridge to come up. You do not normally launch the game by hand.

## Point the harness at the save folder

```bash
export FTL_SAVE_DIR="/mnt/c/Users/<you>/Documents/My Games/FasterThanLight"
```

`setup_pc.sh` also writes this to `ftl_bench/.env.pc`, so you can `source .env.pc` before running.

## Verify

```bash
source .env.pc
python3 adapter/play_cli.py obs          # should print a live observation
python3 adapter/run_benchmark.py --agent scripted --max-instances 1 --budget-cap 8
```

Then head to the [Quickstart](/evaluate/quickstart/) to run your model.
