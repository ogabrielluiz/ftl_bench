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
| `shoot(weapon_slot, enemy_room_id)` | Aim+fire a weapon at an enemy room (auto-fires as it charges) |
| `advance(frames)` | Let game time pass (charge weapons, finish a jump/combat) then re-pause |

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
