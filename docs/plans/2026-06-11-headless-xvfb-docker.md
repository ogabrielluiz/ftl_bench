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
- **M3 — scripted-baseline scored run** headless. DONE. The scripted baseline plays a full scored
  game headless (T1-survive8-s1, seed 1: **solved**, ftl_score 50; 8 jumps + 6 combats + 1 kill).
  Root cause of the earlier stall: headless (no display/input) FTL never reached the title menu —
  its first-run **LanguageChooser** (no settings file) blocked it, and the fresh-profile hangar
  **intro tutorial** ate the Start click. Fixed in HS `hs_benchmark_advance_menu`
  (FTL-Hyperspace `bench` @ d85d6df9): hover+click the first language via real `CApp` input
  events (`OnMouseMove`+`OnLButtonDown/Up`) and `ShipBuilder::introScreen.Close()`. The Linux
  liveness fix (`pgrep -f FTL.amd64`) also landed. After pulling the HS fix, rebuild the Linux
  `.so` (`buildscripts/linux-1.6.13/build-releaseonly-from-docker.sh`); `run.sh` re-stages it.
- **M4 — codex / LLM agents headless + parallel.** DONE. The codex backend shells out to the local
  OpenAI `codex` CLI (Windows-only auth here), so a headless codex run runs the **harness on the
  host** (WSL invokes Windows `codex.exe`, with `-o` output paths via `wslpath -w`) driving an
  **FTL-only container** through a shared save-dir volume (`run_host.sh`; `FTL_BENCH_ASSUME_ALIVE=1`
  skips the cross-container liveness/restart). Validated: gpt-5.5 plays scored games headless.
  **Parallel (`run_parallel.sh`):** one FTL container per scenario, K at a time, all feeding one
  shared dashboard + a re-scored aggregate (`split_suite.py` + `aggregate_parallel.py`). This also
  sidesteps the between-instance reset and is the real throughput win — a 6-public-scenario codex
  run completed all 6 in parallel (mean FTL 243.5, Solve 1/6 — agent quality, not infra).
- **Between-instance reset (host-harness):** FIXED. `reset_episode` worked in all-in-one mode (local
  obs) but timed out in host-harness mode, where a bind-mounted obs can miss the brief
  `game_started` false->true menu window between games. The bridge now stamps `reset_done_seq` once
  a reset's new seeded game loads, and the harness waits on that marker (robust even when consecutive
  instances share a seed, e.g. T1-s1 / T2-sector1-s1 are both seed 1). Host-harness sequential is now
  2/2 (was reset-fail).
- **Obs enrichment:** crew now carries `species` (race), per-task `skills` (0-5 mastery, non-zero),
  and `mind_controlled`.

## Live dashboard

`adapter/ftl_live.py` serves the React dashboard on `:8765` (needs `uvicorn`/`fastapi` + the built
`dashboard/dist`, both in the Windows `harness/.venv`). `run_host.sh --dashboard` /
`run_parallel.sh --dashboard` auto-launch it: WSL runs the Windows venv python via interop, the
script path translated with `wslpath -w` and `FTL_BENCH_DIR` passed via `WSLENV=FTL_BENCH_DIR/p`.

## Reproduce (from WSL)

```sh
cd <repo>/docker/headless
export WHEEL=<repo>/dist/ftl_bench-*.whl HS_DIR=~/projects/FTL-Hyperspace FTL_DIR=~/ftl-linux

bash run.sh verify                                   # boot FTL headless + observation
bash run.sh run --agent scripted --max-instances 2   # all-in-one: scored run(s)

# host-harness (codex): FTL-only container + host harness over a shared save dir
bash run_host.sh --dashboard --agent llm --backend codex --model gpt-5.5 --max-instances 4

# parallel: one container per scenario, K at a time, one dashboard + aggregate
bash run_parallel.sh --tier public --conc 3 --dashboard -- --agent llm --backend codex --model gpt-5.5
```

FTL Linux installed via `steamcmd +@sSteamCmdForcePlatformType linux +force_install_dir ~/ftl-linux
+login <user> +app_update 212680 validate` (game lands under `~/ftl-linux/data/`). `run.sh`
auto-mounts the Windows save dir at `/profile` to seed `.sav` files. The codex backend needs the
Windows `codex` CLI + `~/.codex` auth; `CODEX_BIN`/`CODEX_TMPDIR` default to the Windows install.
