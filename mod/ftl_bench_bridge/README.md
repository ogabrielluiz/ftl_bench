# ftl_bench_bridge

The in-game Hyperspace **Lua mod** that bridges FTL to the external harness.

Responsibilities:
- **Gate the simulation** — a per-frame hook keeps the sim paused by default and unpauses in controlled increments (event-driven decision points).
- **Serialize state** — emit an `Observation` JSON at each decision point.
- **Apply actions** — receive an `Action` and call the Hyperspace Lua API (`CrewMember:MoveToRoom`, `ShipSystem:IncreasePower`, jump, etc.).
- **Transport** — exchange observation/action with the harness (file-polling default; socket if the Lua sandbox permits).

Some actions (weapon room-targeting, event-choice selection, store buy/sell) require **new SWIG/Lua bindings** added to an extended Hyperspace build — see the spec §6 and the deepdive extension work list.
