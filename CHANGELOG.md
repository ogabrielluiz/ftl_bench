# Changelog

## Unreleased

- Integrate the visual benchmark, frozen challenge/full-game controllers,
  screenshot replays, conservative HUD extraction and cooperative stopping.
- Preserve the headless reset marker, Linux process detection, WSL CLI output
  path handling and enriched crew observations when merging shared code.
- Keep headless dashboards and aggregation aligned with unique nested run
  directories; preserve previous outputs, expose missing/ambiguous attempts,
  propagate failures and test effective budget caps and retry exclusions.
- Run headless output-contract and dashboard regressions in CI.
- Document partial live results, paused experiments, acceptance boundaries and
  contributor workflow. Existing frozen cohorts remain tied to their original
  sources; merged-source experiments need new acceptance and a new cohort.
- Full-game visual completion and live headless validation of the combined
  contracts remain WIP. The package version stays at 0.2.0; no release is implied.

## 0.2.0

Headless Linux + Docker: run the real FTL + the bench Hyperspace mod under Xvfb in Docker, with no
display, GPU, or Steam client — hermetic and parallelizable. The Python harness drives it through
the same JSON bridge.

- **`docker/headless/`** — image (Ubuntu + Xvfb + Mesa llvmpipe + SDL2 + harness wheel + FTLMan) and
  an entrypoint with `probe` | `verify` | `run` | `serve` | `diag` | `resettest` modes. FTL is
  bind-mounted (steamcmd's `data/` layout), `ftl.dat` is FTLMan-patched, the Linux Hyperspace
  `.so` is `LD_PRELOAD`ed, `steam_appid.txt` lets it run without a Steam client, and the save dir is
  aligned to FTL's `~/.local/share/FasterThanLight` so the game and harness rendezvous.
- **Host-harness flow (`run_host.sh`)** — run the harness on the host driving an FTL-only container
  via a shared save dir; required for the `codex` backend (Windows-only CLI/auth, invoked from WSL).
  `FTL_BENCH_ASSUME_ALIVE=1` skips the cross-container process-liveness/restart checks.
- **Parallel runner (`run_parallel.sh` + `split_suite.py` + `aggregate_parallel.py`)** — one FTL
  container per scenario, K at a time, all feeding one shared dashboard + a re-scored aggregate.
- **Live dashboard** auto-launch (`--dashboard`) for the headless runners.
- **Linux support in the harness** — process liveness recognizes `FTL.amd64`; `reset_episode` waits
  on a new `reset_done_seq` bridge marker (robust when a bind-mounted obs misses the brief menu
  window between games); the `codex` backend translates output paths for Windows `codex.exe` run
  from WSL.
- **Observation** — crew now exposes `species` (race), per-task `skills` (0-5 mastery), and
  `mind_controlled`.

Requires the Linux Hyperspace `.so` built from the FTL-Hyperspace `bench` branch, whose
`hs_benchmark_advance_menu` was updated to dismiss FTL's first-run LanguageChooser + hangar intro
headless.

## 0.1.0

Initial release: the FTL agent-evaluation benchmark, scenario suite, agents (scripted / random /
llm), and the `ftlbench` CLI, driving the real FTL game via the FTL-Hyperspace bridge.
