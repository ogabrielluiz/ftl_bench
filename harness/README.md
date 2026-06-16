# ftl-bench

An agent-evaluation benchmark that has an LLM agent play **FTL: Faster Than Light** through a
turn-based, intent-level interface built on the FTL-Hyperspace Lua API. The agent reads a
decision-complete JSON observation and replies with one command; the harness scores how far it
gets on a suite of reproducible, seed-pinned scenarios.

This package ships the Python harness, the scenario suite, the agents, and the `ftlbench`
command line. Driving the real game additionally needs FTL installed (via Steam) plus the bench
Hyperspace mod.

## Install

```bash
pip install ftl-bench
```

## Use

```bash
ftlbench run --agent scripted              # run the scenario suite with the scripted baseline
ftlbench run --agent random --tier public  # the legal-move floor on the public tier
ftlbench run --agent llm --backend anthropic --model claude-sonnet-4-6   # a model plays the suite
ftlbench play obs                          # print the live observation the agent sees
ftlbench install-mod --url <release-asset> # install the prebuilt bench Hyperspace mod into FTL
ftlbench version
```

`ftlbench run --help` and `ftlbench play` show the full options. Results and a reproducibility
manifest are written under `runs/benchmark/`.

## Platforms

The harness runs on native Windows, WSL, or macOS and launches FTL for you (via Steam on
Windows). It reads/writes the FTL user folder, resolved per OS or overridden with `FTL_SAVE_DIR`.

## Headless (Linux + Docker)

`docker/headless/` runs the real FTL + the bench Hyperspace mod under Xvfb in Docker on Linux — no
display, no GPU, no Steam client — so the suite is hermetic and parallelizable. Build the image once
(`run.sh`), bind-mount a Linux FTL install, and drive it through the same JSON bridge:

```sh
cd docker/headless
FTL_DIR=~/ftl-linux bash run.sh verify                      # boot FTL headless + an observation
FTL_DIR=~/ftl-linux bash run.sh run --agent scripted --max-instances 2   # scored runs

# parallel: one FTL container per scenario, K at a time, one live dashboard + aggregate
FTL_DIR=~/ftl-linux bash run_parallel.sh --tier public --conc 3 --dashboard -- --agent scripted
```

The LLM `codex` backend runs the harness on the host (driving an FTL-only container via a shared
save dir) so it can reach the Windows `codex` CLI/auth. See
`docs/plans/2026-06-11-headless-xvfb-docker.md` for the full design.

## More

Full design, architecture, and the in-game bridge live in the project repository:
<https://github.com/ogabrielluiz/ftl_bench>.
