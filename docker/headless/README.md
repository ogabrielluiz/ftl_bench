# Headless ftl_bench (Linux + Xvfb + Docker)

Run the **real** FTL game + the bench Hyperspace mod with **no display** and **no GPU**, so the
benchmark is hermetic and parallelizable (one container = one game). The Python harness is
unchanged — it drives the game through the JSON bridge files in the FTL save dir, which works
identically whether or not the game is on screen.

See `../../docs/plans/2026-06-11-headless-xvfb-docker.md` for the full design + verified facts.

## Prerequisites

1. **Linux Hyperspace `.so`** built from the FTL-Hyperspace `bench` branch:
   ```sh
   cd ~/projects/FTL-Hyperspace
   buildscripts/linux-1.6.13/build-releaseonly-from-docker.sh   # -> build-linux-1.6.13-release/
   ```
2. **A Linux FTL install** (only for `verify`/`run`, not `probe`). The FTL Linux payload
   (`FTL.amd64` + `ftl.dat` + `data/` + the `FTL` launcher) needs Steam/GOG ownership and is **not**
   shipped in the image. Steam = 1.6.13 (use the 1.6.13 `.so`); GOG/Humble = 1.6.12 (set
   `HS_VARIANT=1.6.12`).

## Usage (from Linux/WSL)

```sh
# 1) Validate the headless display stack — no game needed:
./run.sh probe

# 2) First real verification — does the bridge produce an observation with no display?
FTL_DIR=/path/to/linux/FTL ./run.sh verify

# 3) A scored headless benchmark run:
FTL_DIR=/path/to/linux/FTL ./run.sh run --agent scripted --max-instances 1
```

`run.sh` stages `vendor/` (the HS `.so`, both `.ftl` mods, `liblua`, the dev lua, the harness
wheel) from the two repos, builds the image, and runs the chosen mode. Overrides: `FTLB_DIR`,
`HS_DIR`, `HS_VARIANT`, `WHEEL`, `IMAGE`, `FTL_DIR`.

## Modes (entrypoint)

| Mode | Needs FTL? | What it does |
|---|---|---|
| `probe` | no | Xvfb + Mesa software GL + an SDL2 video/GL-context probe (what FTL does at startup). |
| `verify` | yes | Copy mounted FTL → workdir, patch `ftl.dat` (FTLMan), `LD_PRELOAD` the HS `.so`, deploy the dev lua, launch under Xvfb, wait for `ftl_agent_observation.json`, then `ftlbench play obs`. |
| `run …` | yes | Same assembly, then `ftlbench run …` (scored). |

## Notes / known follow-ups

- **FTL is mounted read-only and copied** into the container before patching — your install stays
  pristine.
- **`SDL_AUDIODRIVER=dummy` + `LIBGL_ALWAYS_SOFTWARE=1`** → no sound server, no GPU.
- **Harness Linux liveness:** `session.ftl_process_alive()` / `run_benchmark.game_alive()` only know
  the macOS/Windows process names; a Linux branch (`pgrep -f FTL.amd64`) is needed so a live game
  isn't mislabeled `FROZEN_KILLED`. Tracked in the design doc (M2/M3).
- **Runtime libs** are a best-effort first cut; refine the apt list against `ldd FTL.amd64` once a
  Linux FTL install is available.
