# ftl_bench_bridge

The in-game Hyperspace **Lua mod** that bridges FTL to the external harness.

Responsibilities:
- **Gate the simulation** — a per-frame hook keeps the sim paused by default and unpauses in controlled increments (event-driven decision points).
- **Serialize state** — emit an `Observation` JSON at each decision point.
- **Apply actions** — receive an `Action` and call the Hyperspace Lua API (`CrewMember:MoveToRoom`, `ShipSystem:IncreasePower`, jump, etc.).
- **Transport** — exchange observation/action with the harness. ⚠️ The Hyperspace Lua sandbox disables `io`/`os`/sockets (`lua/linit.c`), so transport requires a **new C++ binding** (file bridge or AF_UNIX/named-pipe socket) plus a **JSON binding** (none bundled). This is the structural prerequisite — deepdive P0 #1–#2.

**Mod packaging note:** the scripts are registered via `data/hyperspace.xml.append` (an **append**, not a plain `hyperspace.xml`). A plain file would *replace* Hyperspace's own `hyperspace.xml` and drop its `<version>` tag — which triggers an in-game "Wrong version of Hyperspace detected" warning and loses Hyperspace's base config. The append adds a second `<scripts>` node, which Hyperspace's parser loads in addition to its own (`Resources.cpp` iterates every `scripts` node). Verified live on FTL 1.6.13 + Hyperspace 1.22.2.

Several actions (weapon room-targeting, event-choice confirm, jump trigger, store) require **new SWIG/Lua bindings** added to an extended Hyperspace build — see spec §6 and the deepdive extension work list (§10).
