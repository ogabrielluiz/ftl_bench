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

## More

Full design, architecture, and the in-game bridge live in the project repository:
<https://github.com/ogabrielluiz/ftl_bench>.
