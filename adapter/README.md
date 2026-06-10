# adapter

Exposes the `ftl_bench` environment to an LLM agent as **MCP tools**, so a
tool-capable model can play FTL directly.

`ftl_mcp_server.py` wraps `AgentSession` and serves these tools (each returns a
compact, agent-readable summary of the resulting state):

| Tool | What it does |
|------|--------------|
| `observe()` | Current state: context (menu/in_space/combat/event), your ship (hull, reactor, systems+power, crew, weapons+charge), enemy (hull, shields, rooms), jump beacons, event choices |
| `reset(mode)` | Start a run — `'new'` (fresh seeded) or `'continue'` (resume the save) |
| `do_jump(beacon_index)` | FTL-jump to a connected beacon |
| `pick_choice(choice_index)` | Choose an event option |
| `power_system(system_id, level)` | Set a system's power (0=shields 1=engines 3=weapons …) |
| `send_crew(crew_id, room_id)` | Move a crew member to one of your rooms |
| `shoot(weapon_slot, enemy_room_id)` | Queue one manual shot/burst at an enemy room; issue it again for the next volley |
| `advance(frames)` | Let game time pass (charge weapons, finish a jump/combat) then re-pause |
| `run_strategy(code)` | **Code mode**: run agent-authored Python against the env (loops, whole combats) in one call — fewer round-trips than per-action tool calls |

## Prerequisites

The game must be running with the bridge live and not napping in the background:

```bash
defaults write com.example.FTL NSAppSleepDisabled -bool YES   # one-time: keep ticking unfocused
scripts/restart_ftl.sh continue                                # launch + start a run
```

## Run the server

```bash
cd harness && uv run --with "mcp[cli]" python ../adapter/ftl_mcp_server.py
```

To register with Claude Code (`.mcp.json` / `claude mcp add`), point the command at
that line. The server drives a single live FTL instance.

## Baseline agent

`baseline_agent.py` is a scripted heuristic agent (no LLM) that plays a few jumps —
powers shields/weapons, resolves events, and fights — useful as a smoke test and a
scoring baseline:

```bash
cd harness && uv run python ../adapter/baseline_agent.py --jumps 5
```

## Eval harness

`eval.py` runs N seeded episodes (fresh `reset_episode` between each — no FTL restart),
records a trajectory per episode, and aggregates scores (survival rate, mean kills/hull/…):

```bash
cd harness && uv run python ../adapter/eval.py --seeds 1,2,3 --jumps 6
```

## Two ways an agent plays

- **Per-tool MCP** — the model calls `observe`/`do_jump`/`shoot`/… step-by-step (good for
  introspection). No built-in Claude Code "code mode" toggle exists for MCP; tools are normal calls.
- **Code mode** — the model writes Python against this env and runs it. Either via `run_strategy`
  (an MCP tool that execs agent code with `session` + action builders in scope) or, in a
  code-execution agent (Claude Code), by writing+running a script that imports `ftl_bench` directly.
  Recommended for FTL: one script can drive a whole combat without flooding context with
  intermediate observations.
