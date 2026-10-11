# Headless ftl_bench (Linux + Xvfb + Docker)

Run the **real** FTL game + the bench Hyperspace mod with **no display** and **no GPU**,
using one game and save directory per container. The structured Python harness
drives the game through JSON bridge files in that save directory.

The visual benchmark changes are now integrated in source. Live Linux validation
of the combined native/bridge contracts remains WIP: the accepted Windows visual
DLL and its receipts do not certify a Linux `.so`. See [current integration status](../../docs/NEXT.md#main-integration).

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

### Host and parallel outputs

`run_host.sh` sends the harness and optional dashboard to the same output parent,
defaulting to `harness/runs/benchmark` in the checkout. `--out` overrides that path.
The runner retains each invocation in its own child directory.

For `run_parallel.sh`, `--out` after `--` selects the parent of a fresh
`parallel-<timestamp>-<unique>/` directory. Shard suites, logs and nested run
directories are preserved there; earlier results are not cleared. The aggregator
reads the recorded run manifests and supports historical flat trajectories with
an explicit suite. A supplied `--budget-cap` applies to both runner and aggregate.

Only one finalized, unambiguous, non-diagnostic attempt per selected scenario
enters the parallel aggregate. Missing, invalid, unfinished, duplicate and
retry-configured results remain visible and cause a nonzero status; retries are
not silently reduced to the best attempt. `aggregate_parallel.py --json` exposes
the individual attempts and exclusions. This file-derived report does not certify
native runtime acceptance or establish a model comparison.

## Modes (entrypoint)

| Mode | Needs FTL? | What it does |
|---|---|---|
| `probe` | no | Xvfb + Mesa software GL + an SDL2 video/GL-context probe (what FTL does at startup). |
| `verify` | yes | Copy mounted FTL → workdir, patch `ftl.dat` (FTLMan), `LD_PRELOAD` the HS `.so`, deploy the dev lua, launch under Xvfb, wait for `ftl_agent_observation.json`, then `ftlbench play obs`. |
| `run …` | yes | Same assembly, then `ftlbench run …` (scored). |

## Notes / known follow-ups

- **FTL is mounted read-only and copied** into the container before patching — your install stays
  pristine.
- **Host save directories are disposable:** `run_host.sh` recreates `SAVE_DIR`.
  Keep it separate from the personal save/profile directory; profiles are mounted
  read-only for seeding. This scratch-directory lifecycle differs from the
  protected Windows visual runner's backup-and-restore lifecycle.
- **`SDL_AUDIODRIVER=dummy` + `LIBGL_ALWAYS_SOFTWARE=1`** → no sound server, no GPU.
- **Harness Linux liveness:** `session.ftl_process_alive()` and
  `run_benchmark.game_alive()` recognize `FTL.amd64`. Host-harness mode uses
  `FTL_BENCH_ASSUME_ALIVE=1` for a game in another container; this bypasses local
  process probing and is not proof that the remote game is healthy.
- **Reset completion:** the bridge publishes `reset_done_seq` after the seeded
  game starts, so the host can observe completion even when a bind mount misses
  the brief menu state. The session requires the marker to match its reset packet.
- **Recovery remains WIP:** `FTL_BENCH_ASSUME_ALIVE` does not implement container
  restarts. Game-over/timeout recovery still reaches the existing non-Windows
  restart helper, which is macOS-specific; automatic Linux/container recovery
  needs its own implementation and live validation.
- **Runtime libs** are a best-effort first cut; refine the apt list against `ldd FTL.amd64` once a
  Linux FTL install is available.
