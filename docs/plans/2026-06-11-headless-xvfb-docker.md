# Headless ftl_bench — Linux + Xvfb + Docker

**Goal (handoff Next-step #3):** run the *real* FTL game + the bench Hyperspace mod under a
virtual framebuffer (Xvfb) inside Docker on Linux, so the existing harness drives it with no
visible display — hermetic, parallelizable, GPU-free, no Steam/Windows dependency. This is NOT a
reimplementation of FTL; the Python harness is unchanged.

## Why this is a small change

The harness already talks to the game purely through JSON bridge files in the FTL save dir
(`ftl_agent_observation.json` / `ftl_agent_action.json`). Nothing in the Python stack
(`session.py`, `play_cli.py`, `run_benchmark.py`, the agents, scoring) knows or cares whether the
game is on screen. So "headless" reuses every platform-independent piece and swaps only the
binary + adds a display layer.

| Piece | Reused as-is | New for headless |
|---|---|---|
| Harness (`harness/`, `adapter/`) | yes | — |
| Bench bridge mod (`ftl_bench_bridge.ftl`) + `ftl_bench_dev.lua` | yes | — |
| `ftl.dat` patching (FTLMan, Linux binary) | yes | — |
| Hyperspace binary | — | Linux `Hyperspace.1.6.13.amd64.so` (was Windows `Hyperspace.dll`) |
| Injection | — | `LD_PRELOAD` next to `FTL.amd64` (no Steam / no xinput proxy) |
| Display / audio | — | Xvfb (`:99`) + Mesa llvmpipe software GL + `SDL_AUDIODRIVER=dummy` |

## Verified facts (2026-06-11)

- **Linux Hyperspace builds clean from the `bench` branch.** `Hyperspace.1.6.13.amd64.so`
  (ELF64, 13.3 MB, not stripped) built via the existing devcontainer
  (`ghcr.io/ftl-hyperspace/hs-devcontainer:v2`,
  `buildscripts/linux-1.6.13/build-releaseonly-from-docker.sh`, output
  `build-linux-1.6.13-release/`). 135/135 linked, exit 0.
- **The bench C++ is in the Linux `.so`.** Confirmed symbols: `hs_benchmark_{fire_weapon,
  jump_to_beacon,leave_sector,choose_event}` (+ all SWIG `_wrap_benchmark_*` Lua wrappers and the
  Lua-facing `benchmark_*` names), plus the bridge IO hooks `read_json_action` /
  `write_json_observation` (116 `benchmark_` strings). So the whole bench bridge works on Linux.
- **HS `.so` direct NEEDED libs:** `libSDL2-2.0.so.0`, `libstdc++.so.6`, `libgcc_s.so.1`,
  `libpthread`, `libm`, `libdl`, `libc` (boost is statically linked in). Plus the bundled
  `liblua5.3.so.0` (ships in `Release Files/Linux/`, sits next to `FTL.amd64`).
- **Linux injection (from `Release Files/Linux/README.txt`):** copy the `.so` next to `FTL.amd64`
  and add `LD_PRELOAD=./Hyperspace.1.6.13.amd64.so` (+ `LD_LIBRARY_PATH="$here"`) to the `FTL`
  launcher script before `exec`. Steam = 1.6.13, GOG/Humble = 1.6.12 (use the matching `.so`).

## Known harness tweak for Linux

`session.ftl_process_alive()` / `run_benchmark.game_alive()` only recognize the macOS FTL.app
process (pgrep) or Windows `FTLGame.exe` (tasklist). On native Linux the process is `FTL.amd64`,
so liveness would read false and mislabel a live game `FROZEN_KILLED`. Add a Linux branch
(`pgrep -f FTL.amd64`) as part of M2/M3 integration.

## The one hard dependency (needs the user)

The FTL **Linux** game payload — `FTL.amd64` + `ftl.dat` + `data/` + the `FTL` launcher — is not on
this machine and needs Steam ownership to fetch. It can't be baked into a shareable image
(licensing). Sourcing options:

- **(A) Bind-mount a Linux FTL copy** the user provides (Steam Linux / GOG / Humble). Fastest to a
  first run; keeps game data out of the image. **Recommended for the first verification.**
- **(B) `steamcmd` in/around the image** with the user's Steam creds (one-time interactive Steam
  Guard). Most hermetic for CI eventually.
- **(C) One-time manual `steamcmd` download**, then point the harness at the result.

The Docker image + entrypoint are invariant to this choice — FTL is mounted at runtime, never in
the image.

## Architecture: container layout

```
docker/headless/
  Dockerfile        # ubuntu:24.04 + Xvfb + Mesa(software GL) + SDL2 + X libs + python3 + harness
                    # wheel + FTLMan; COPYs vendored HS artifacts (so, Hyperspace.ftl, liblua).
                    # Does NOT contain the FTL game.
  entrypoint.sh     # at run: copy mounted FTL -> writable workdir; patch ftl.dat (FTLMan w/
                    # Hyperspace.ftl + ftl_bench_bridge.ftl); drop the .so + edit the FTL launcher
                    # (LD_PRELOAD); deploy ftl_bench_dev.lua + reload marker to the save dir;
                    # start Xvfb :99; launch FTL under DISPLAY=:99 SDL_AUDIODRIVER=dummy
                    # LIBGL_ALWAYS_SOFTWARE=1; wait for the obs file; exec the harness command.
  run.sh            # host helper: stage vendored inputs -> vendor/, docker build, docker run with
                    # the FTL dir bind-mounted and the save dir on a volume.
  vendor/           # (gitignored) staged build inputs: Hyperspace.1.6.13.amd64.so,
                    # Hyperspace.ftl, liblua5.3.so.0, ftl_bench_bridge.ftl, ftl_bench-*.whl
  README.md
```

Design choices:
- **Pristine FTL stays untouched:** mount read-only, copy into a writable layer, patch the copy.
- **Harness + game in the same container:** they share the save dir (the bridge files). One
  container = one game. Parallelism = N containers (the FLE-style goal).
- **64-bit only:** Steam `FTL.amd64` is x86-64; the matching HS `.so` is amd64 — no i386/multilib.
- **GPU-free:** FTL's old OpenGL runs on Mesa's llvmpipe software rasterizer under Xvfb.

## Milestones

- **M0 — HS Linux build + verify.** DONE (`.so` built, bench symbols confirmed).
- **M1 — display layer.** DONE. Image builds; SDL2+GL probe runs headless under Xvfb
  (`llvmpipe`, GL 4.5, no GPU).
- **M2 — first verification (handoff's stated first step).** DONE. FTL.amd64 boots headless
  (Xvfb + `LD_PRELOAD` HS), the bench bridge loads, and writes a valid
  `ftl_agent_observation.json` in ~4s with no display; `ftlbench play obs` returns it. FTL runs
  fine despite non-fatal Steam-API (`steamclient.so` absent, mitigated by `steam_appid.txt`) and
  ALSA (no sound card, `SDL_AUDIODRIVER=dummy`) warnings.
- **M3 — scripted-baseline scored run** headless. IN PROGRESS — pipeline runs end-to-end (boot →
  patch → bridge → runner → `summary_scripted.json`) and the Linux liveness fix landed
  (`pgrep -f FTL.amd64`). BLOCKER: `reset_episode`'s new-game menu nav doesn't start a game
  headless on the fresh Linux **1.6.13** build (works on the established Windows **1.6.9**). The
  Lua flow is correct (calls `benchmark_advance_menu` every 25 ticks); the C++ `advance_menu`
  no-ops unless the title `MainMenu` is open and only handles New Game → CONFIRM → hangar Start.
  Seeding the Windows `.sav` profile loaded but didn't help. Next: instrument `advance_menu`
  (log `menu.bOpen` / `confirmNewGame.bOpen` / `shipBuilder.bOpen` + the post-New-Game
  "Enable Advanced Edition?" dialog) via an HS rebuild, or extend it to dismiss that dialog.
- **M4 — parallel/CI** harness (N containers) + the steamcmd hermetic image story.

## Reproduce so far (from WSL)

```sh
cd <repo>/docker/headless
WHEEL=<repo>/dist/ftl_bench-*.whl HS_DIR=~/projects/FTL-Hyperspace FTL_DIR=~/ftl-linux \
  bash run.sh verify   # M2: headless boot + observation (works)
#   …same with `diag` (menu/log dump) or `run --agent scripted --max-instances 1` (M3, stalls at reset)
```

FTL Linux was installed via `steamcmd +force_install_dir ~/ftl-linux +login <user> +app_update 212680
validate` (the game lands under `~/ftl-linux/data/`). `run.sh` auto-mounts the Windows save dir at
`/profile` to seed `.sav` files.
