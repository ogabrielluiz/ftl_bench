
# ftl_bench Milestone 2 — Pause-Gating + Action Dispatch Closed Loop

> **✅ STATUS: M2 COMPLETE — verified live on FTL 1.6.13 + Hyperspace 1.22.2.**
> The agent drives the ship through a turn-based loop: `reset()` → frozen; `step([set_system_power(1,2), move_crew(0,14)], advance_frames=180)` → engines powered 1→2, crew 0 moved room 0→5, re-paused, `last_action_seq` incremented. **Pause verified**: `bPaused` alone freezes the sim (a walking crew member halted for 4s while paused). **Two corrections found live:** (1) `FPS.SpeedFactor` is **%immutable** (writing it threw "This variable is immutable" and killed the ON_TICK callback) — removed; `bPaused` alone suffices. (2) `set_system_power` is **reactor-limited / best-effort**: requesting power beyond available reactor under-shoots (correct behavior); a `Force` variant is future work.
>
> **Dev workflow upgrade (hot-reload):** the in-`.dat` bridge is now a thin **bootstrap**; the real logic lives in an external `ftl_bench_dev.lua` re-run live via `Hyperspace.benchmark_reload_dev()` (marker-gated, since Lua `load` is sandbox-stripped). Iterate with `scripts/deploy_dev.sh` — no re-patch, no relaunch, run state preserved. `_G.ftl_bench_state` persists the loop across reloads.

## 1. Control model

M2 turns the M1 read-only observation stream into a **turn-based closed loop** driven entirely from `ON_TICK` (which fires in `CApp::OnLoop` *after* `super()`, i.e. after the current frame's world-state update — verified at `Misc.cpp:1118-1123`). The game sits **paused by default** (`gui.bPaused = true`, `FPS.SpeedFactor = 0`). The Python harness writes an atomic action file `{seq, advance_frames, actions[]}`; each tick the bridge reads it via the new `Hyperspace.read_json_action()` C++ binding, dedups on `seq > last_applied_seq`, applies each action through verified Lua bindings, then **opens a frame budget** by unpausing (`bPaused=false`, `SpeedFactor=1`) for `advance_frames` ON_TICK firings, and re-pauses when the budget hits zero. On every paused tick it writes an observation stamped with `last_action_seq` and the live `paused` flag, which is the harness's acknowledgement signal. Dedup + the seq-stamped observation make the protocol idempotent and race-tolerant without file locking.

```
        write action file (seq=N)
   harness ───────────────────────────► [ftl_agent_action.json]
      ▲                                        │ read each tick
      │ poll obs                               ▼
      │ until                          ┌──────────────────┐
      │ last_action_seq==N    PAUSED   │  ON_TICK handler │
      │ && paused==true       state    │  bPaused=true    │
      │                                │  SpeedFactor=0   │
      │                                └───────┬──────────┘
      │                          seq>last_applied_seq?
      │                                        │ yes: apply actions,
      │                                        │ last_applied_seq=seq,
      │                                        │ budget=advance_frames,
      │                                        │ bPaused=false, SpeedFactor=1
      │                                        ▼
      │                                ┌──────────────────┐
      │                                │  ADVANCING state │
      │                                │  budget-- each   │◄─┐
      │                                │  ON_TICK firing  │  │ budget>0
      │                                └───────┬──────────┘──┘
      │                          budget==0 → bPaused=true, SpeedFactor=0
      │                                        ▼
      └──────────── write obs(last_action_seq, paused=true) ◄── PAUSED
```

State set: `PAUSED` (waiting for new seq), `ADVANCING` (consuming frame budget). Observation is written only when paused, so the harness never sees a mid-advance snapshot.

## 2. C++ additions

The reader is **already implemented** at `Benchmark_Extend.cpp:68-78` / `Benchmark_Extend.h:23` as `hs_benchmark_read_observation()` reading the *observation* path — but M2 needs a reader for the *action* path. Add a sibling `hs_benchmark_read_action()` that reads `{getUserFolder()}/ftl_agent_action.json` and returns the contents via a static `std::string` (the proven `__str__`/`HyperspaceVersion` marshaling pattern at `hyperspace.i:466-469`). Missing file → return `""` (empty string, no throw).

**`Benchmark_Extend.h`** — add the declaration next to the existing reader (line ~23):

```cpp
// Reads {getUserFolder()}/ftl_agent_action.json; returns contents,
// or empty string "" if the file is absent/unreadable.
const char* hs_benchmark_read_action();
```

**`Benchmark_Extend.cpp`** — add after the existing `hs_benchmark_read_observation()` (line ~78), mirroring its file-read logic but with the action filename and a static buffer for safe const char* marshaling:

```cpp
const char* hs_benchmark_read_action()
{
    // getUserFolder() returns a path WITH a trailing separator (verified Benchmark_Extend.h:17)
    static std::string buffer;
    buffer.clear();

    std::string path = FileHelper::getUserFolder() + "ftl_agent_action.json";
    std::ifstream in(path, std::ios::in | std::ios::binary);
    if (!in.good())
    {
        return buffer.c_str();   // "" — file absent is normal, not an error
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    buffer = ss.str();
    return buffer.c_str();        // static lifetime → safe for SWIG Lua string typemap
}
```

(Reuse the same `<fstream>`/`<sstream>` includes and `FileHelper` usage the existing `hs_benchmark_read_observation()` already relies on; no `std_string.i` needed — `const char*` returns marshal via the default typemaps already pulled in at `hyperspace.i:4`.)

**`hyperspace.i`** — register the free function immediately after the existing write binding (`hyperspace.i:461`, the `write_json_observation` `%rename`), matching the `srandom32`/`setRandomSeed` free-function `%rename` style:

```swig
%rename("read_json_action") hs_benchmark_read_action;
const char* hs_benchmark_read_action();
```

This exposes it as `Hyperspace.read_json_action()`. **Rebuild required** (SWIG regen + native build) before the bridge can call it — this is M2 Task 1.

> Live-test flag: the static-buffer-per-tick contract means **call `read_json_action()` exactly once per tick**; a second call in the same tick returns the first call's content. Verified-safe for single-read-per-tick; flagged as a usage constraint, not a re-test.

## 3. Action protocol

**Action file** — `{getUserFolder()}/ftl_agent_action.json`, written atomically by the harness (temp-file + rename):

```json
{
  "seq": 1,
  "advance_frames": 30,
  "actions": [
    { "type": "set_system_power", "system_id": 0, "level": 2 },
    { "type": "move_crew",        "crew_id": 1,   "room_id": 5, "slot_id": -1 }
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `seq` | int | Monotonic. Bridge applies only if `seq > last_applied_seq`. |
| `advance_frames` | int | Number of ON_TICK firings to unpause for (default 30 if absent). **Unit = ON_TICK firings**, not engine sub-steps — see Risks. |
| `actions[]` | list | Applied in order, before unpausing. |
| `actions[].type` | string | `set_system_power` \| `move_crew` (M2 scope). |
| `set_system_power` | `system_id` (SystemId enum), `level` (target int) | Drive `powerState.first` to `level` via Increase/DecreasePower. |
| `move_crew` | `crew_id` (vCrewList index), `room_id` (int), `slot_id` (int, default -1) | `vCrewList[crew_id]:MoveToRoom(room_id, slot_id, false)`. |

**Observation additions** — bump `schema_version` to `2` and add two fields to the M1 builder (M1 hard-codes `paused` at `observation.lua:102`; M2 must emit the **live** state):

```json
{
  "schema_version": 2,
  "last_action_seq": 1,
  "paused": true
}
```

- `last_action_seq`: `null` until the first action is applied, then the seq of the last applied action. **The harness's ack key.**
- `paused`: real `gui.bPaused` at write time (always `true` in M2 because obs is written only while paused, but read live, not hard-coded).

## 4. bridge.lua (full rewrite)

Depends only on verified bindings: `Hyperspace.App.gui.bPaused` (writable, `observation.lua:102`), `Hyperspace.FPS.SpeedFactor` (writable struct member), `Hyperspace.read_json_action()` (new, §2), `Hyperspace.write_json_observation()` (`hyperspace.i:461`), `Hyperspace.ships.player:GetSystem(id)` (`hyperspace.i:1631`), `ShipSystem:IncreasePower/DecreasePower` (`hyperspace.i:2174/2180`), `ShipSystem.powerState.first/.second` (`hyperspace.i:2202`), `ShipManager.vCrewList[i]` (`hyperspace.i:300/1697`), `CrewMember:MoveToRoom(room, slot, force)` (`hyperspace.i:3391`), `_G.json` (`json.lua`), `_G.ftl_bench` observation builder (`observation.lua`).

```lua
-- mod/ftl_bench_bridge/data/bridge.lua  (M2 full rewrite)
local json = _G.json

local frame_counter   = 0
local frame_budget    = 0
local last_applied_seq = nil   -- nil until first action applied

------------------------------------------------------------------
-- Action dispatchers (verified bindings only)
------------------------------------------------------------------

local function apply_set_system_power(mgr, act)
  local sys = mgr:GetSystem(act.system_id)          -- hyperspace.i:1631
  if not sys then return end
  local target = act.level or 0
  local current = sys.powerState.first              -- pair .first = current
  while current < target do
    sys:IncreasePower(1, false)                     -- (levels, manual=false)
    current = current + 1
  end
  while current > target do
    sys:DecreasePower(false)                        -- (manual=false)
    current = current - 1
  end
end

local function apply_move_crew(mgr, act)
  local list = mgr.vCrewList                         -- 0-indexed SWIG vector
  if not list then return end
  if act.crew_id == nil or act.crew_id < 0 or act.crew_id >= list:size() then return end
  local crew = list[act.crew_id]
  if not crew then return end
  local slot = act.slot_id
  if slot == nil then slot = -1 end                  -- -1 = any slot (unverified, live-test)
  crew:MoveToRoom(act.room_id, slot, false)          -- hyperspace.i:3391
end

local function dispatch_actions(actions)
  local mgr = Hyperspace.ships.player                -- hyperspace.i:521-543
  if not mgr then return end
  for _, act in ipairs(actions or {}) do
    if act.type == "set_system_power" then
      apply_set_system_power(mgr, act)
    elseif act.type == "move_crew" then
      apply_move_crew(mgr, act)
    end
    -- unknown types silently ignored
  end
end

------------------------------------------------------------------
-- Pause / advance primitives
------------------------------------------------------------------

local function freeze()
  local gui = Hyperspace.App and Hyperspace.App.gui
  if gui then gui.bPaused = true end
  local fps = Hyperspace.FPS
  if fps then fps.SpeedFactor = 0.0 end              -- backstop for time-scaled systems
end

local function unfreeze()
  local gui = Hyperspace.App and Hyperspace.App.gui
  if gui then gui.bPaused = false end
  local fps = Hyperspace.FPS
  if fps then fps.SpeedFactor = 1.0 end
end

------------------------------------------------------------------
-- Observation
------------------------------------------------------------------

local function write_observation()
  local ok, err = pcall(function()
    local obs = _G.ftl_bench.build_observation(frame_counter)  -- M1 builder
    obs.schema_version  = 2
    obs.last_action_seq = last_applied_seq                       -- nil or int
    local gui = Hyperspace.App and Hyperspace.App.gui
    obs.paused = (gui ~= nil) and gui.bPaused or true            -- live, not hard-coded
    Hyperspace.write_json_observation(json.encode(obs))
  end)
  -- swallow errors; never let obs failure crash the tick
  return ok, err
end

------------------------------------------------------------------
-- ON_TICK state machine
------------------------------------------------------------------

local function on_tick_handler()
  frame_counter = frame_counter + 1
  local gui = Hyperspace.App and Hyperspace.App.gui
  if not gui then return end

  if frame_budget > 0 then
    -- ADVANCING: consume one frame of budget this tick
    frame_budget = frame_budget - 1
    if frame_budget == 0 then
      freeze()
      write_observation()        -- ack the just-completed advance
    end
    return
  end

  -- PAUSED: ensure frozen, look for a new action
  freeze()

  local action_str = Hyperspace.read_json_action()   -- single read per tick
  if action_str and action_str ~= "" then
    local ok, action = pcall(json.decode, action_str)
    if ok and type(action) == "table" and action.seq ~= nil
       and (last_applied_seq == nil or action.seq > last_applied_seq) then
      dispatch_actions(action.actions)
      last_applied_seq = action.seq
      frame_budget = action.advance_frames or 30
      if frame_budget > 0 then
        unfreeze()               -- enter ADVANCING; obs written when budget hits 0
        return
      end
    end
  end

  -- Still paused with no new action (or zero-budget action): write current obs
  write_observation()
end

script.on_internal_event(Defines.InternalEvents.ON_TICK, on_tick_handler)
```

Notes: `freeze()` is called every paused tick (idempotent) so the game cannot drift if some subsystem ignored a prior pause. The zero-budget path (`advance_frames=0`) is treated as "apply + re-observe without advancing", useful for power/crew setup before the agent commits to a time step.

## 5. harness step() API

Python side. `step()` writes the action atomically, then polls the observation until it sees `last_action_seq == seq && paused`. `AgentSession` wraps the M1 reset/observe with the new step.

```python
# harness/src/ftl_bench/session.py
import json
import time
from pathlib import Path

from ftl_bench.observation import ObservationClient, ObservationValidationError


class AgentSession:
    """Closed-loop session over the paused FTL bridge (M2)."""

    def __init__(self, user_folder: Path, poll_interval: float = 0.01,
                 step_timeout: float = 5.0):
        self.user_folder = Path(user_folder)
        self.obs_path = self.user_folder / "ftl_agent_observation.json"
        self.action_path = self.user_folder / "ftl_agent_action.json"
        self.client = ObservationClient(self.obs_path)   # M1 reader/validator
        self.poll_interval = poll_interval
        self.step_timeout = step_timeout
        self.action_seq = 0

    # ---- observe -------------------------------------------------
    def observe(self):
        """Return the latest validated observation (no action)."""
        return self.client.read_latest()

    # ---- reset ---------------------------------------------------
    def reset(self):
        """Clear any stale action file and return the first paused observation."""
        if self.action_path.exists():
            self.action_path.unlink()
        self.action_seq = 0
        return self._wait_for(lambda obs: obs.paused)

    # ---- step ----------------------------------------------------
    def step(self, actions, advance_frames: int = 30):
        """Write an action, advance the world, return the resulting observation."""
        self.action_seq += 1
        payload = {
            "seq": self.action_seq,
            "advance_frames": advance_frames,
            "actions": actions,           # list of {"type": ..., ...}
        }
        self._write_action_atomic(payload)
        return self._wait_for(
            lambda obs: obs.last_action_seq == self.action_seq and obs.paused
        )

    # ---- internals -----------------------------------------------
    def _write_action_atomic(self, payload: dict):
        tmp = self.action_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self.action_path)     # atomic rename on same filesystem

    def _wait_for(self, predicate):
        deadline = time.monotonic() + self.step_timeout
        while time.monotonic() < deadline:
            try:
                obs = self.client.read_latest()
                if predicate(obs):
                    return obs
            except (FileNotFoundError, ObservationValidationError):
                pass
            time.sleep(self.poll_interval)
        raise TimeoutError(
            f"action seq {self.action_seq} not acked within {self.step_timeout}s"
        )
```

Convenience action constructors (optional, keep the harness call sites readable):

```python
def set_system_power(system_id: int, level: int) -> dict:
    return {"type": "set_system_power", "system_id": system_id, "level": level}

def move_crew(crew_id: int, room_id: int, slot_id: int = -1) -> dict:
    return {"type": "move_crew", "crew_id": crew_id, "room_id": room_id, "slot_id": slot_id}
```

Usage:

```python
sess = AgentSession(Path("~/Library/Application Support/FasterThanLight").expanduser())
obs = sess.reset()
obs = sess.step([set_system_power(0, 2), move_crew(1, 5)], advance_frames=30)
print(obs.player_ship["hull"], obs.last_action_seq, obs.paused)
```

`ObservationClient.read_latest()` (M1) must surface `last_action_seq` (default `None`) and `paused` (default `False`) on the returned object — add them to the M1 dataclass/dict mapping when bumping to `schema_version: 2`.

## 6. Pause mechanism decision

**Use BOTH, with `bPaused` as primary and `SpeedFactor` as backstop.** Rationale from grounding:

- `gui.bPaused` is writable from Lua (`hyperspace.i:883`, no `%immutable`, unlike `bAutoPaused` at 884-885) and already used live in M1's observation. It is the canonical FTL pause flag the **original engine** checks (Hyperspace extension code has *zero* `bPaused` checks — `grep` confirmed — so pause-block logic lives in the base engine).
- `FPS.SpeedFactor = 0` independently halts **time-scaled** subsystems (crew healing, weapon charge, fire spread) because `CustomCrew.cpp`/`CustomWeapons.cpp`/`CustomEvents.cpp` scale their per-frame deltas by `GetSpeedFactor()`. This is the backstop for any subsystem that does *not* consult `bPaused`.

`bPaused` alone is **unverified** to freeze the full simulation (grounding risk: "bPaused may control UI overlay only"), and `SpeedFactor=0` alone is **unverified** to halt non-time-scaled paths (AI decisions, rendering, animation stepping). Setting both is strictly safer and both are cheap idempotent writes.

> **Live-test to run FIRST (gates everything else):** in a live combat, run a tiny script — `gui.bPaused=true` only; observe whether the enemy weapon charge bar, your O2/fire, and crew motion freeze. Then add `FPS.SpeedFactor=0` and re-observe. Record which of {bPaused-only, SpeedFactor-only, both} actually produces a fully frozen frame. If both-together does not fully freeze (e.g. animations still slip), escalate to advancing the budget in 1-frame steps and re-freezing each tick (already what the state machine does). Caveat from grounding: `CustomEvents.cpp` uses `SpeedFactor=0` only *transiently*; sustained `SpeedFactor=0` across many ticks is the one novel usage M2 introduces — watch for edge-case bugs (cached SpeedFactor references) during this test.

## 7. Risks & live-tests (in execution order)

1. **Does pause actually freeze the world?** (BLOCKER — §6 live-test.) Test `bPaused` alone, `SpeedFactor=0` alone, and both. Until this passes, the whole loop is theoretical. Verify: enemy weapon charge, your fire/O2, crew motion all halt.
2. **Does the new `read_json_action()` binding marshal correctly?** After rebuild, from Lua: write a file by hand, call `Hyperspace.read_json_action()`, confirm it returns the bytes; delete the file, confirm it returns `""` (not nil, no throw). Pattern is verified-safe but the binding is new code.
3. **Does `IncreasePower/DecreasePower` actually move `powerState.first`?** Apply `set_system_power(SYS_SHIELDS, 3)` paused, advance a frame, read obs, confirm `powerState.first == 3`. Risk: reactor-power shortfall or `manual=false` semantics may clamp below target (loop is bounded by `current` so it can't infinite-loop, but may under-shoot). If it under-shoots, fall back to `ForceIncreasePower` (`hyperspace.i:2165`) or `SetPowerCap` first.
4. **Does `MoveToRoom(room, -1, false)` move crew, and is `-1` "any slot"?** Slot `-1` semantics are *unverified* (inferred from `CustomTeleport.slotId`). Test: move crew to a known room, advance, read `crew.iRoomId` in obs. If `-1` fails, sweep `slot_id ∈ {0..n}` or pass an explicit slot from the observed room layout. Also confirm `MoveToRoom`'s bool return (success vs. fail) for invalid `room_id` (silent fail expected).
5. **Frame-budget unit semantics.** Confirm whether `advance_frames` = ON_TICK firings == engine frames 1:1 (the state machine assumes 1 budget decrement per ON_TICK). If ON_TICK is throttled below frame rate anywhere, `advance_frames` becomes "ticks" not "frames" — measure wall-clock world advance for a known budget.
6. **Pause-race on re-freeze.** When `frame_budget` hits 0 and we re-freeze, a projectile/animation may slip one frame (M1 deepdive §11.1 pause-race spike). Verify by stepping `advance_frames=1` repeatedly and checking obs continuity. Inherit the M1 spike's resolution.
7. **Seq dedup persists across ticks.** `last_applied_seq` is a module-local; confirm Lua local persistence holds across ON_TICK firings (expected, but verify a re-sent identical seq is ignored).
8. **Action/obs file race.** Both use atomic temp-rename, and dedup tolerates a stale read (bridge just waits for the next tick). Confirm no partial-JSON read causes a `json.decode` throw that escapes the `pcall` (it's guarded — verify the guard).

## 8. Task checklist (build order, each independently testable)

- [ ] **T1 — Pause live-test (§6/§7.1).** Hand-run `bPaused`/`SpeedFactor` script in live combat. **Output:** which combination fully freezes. *Test:* visual freeze of weapon charge + fire + crew. **Gates all later tasks.**
- [ ] **T2 — Add `hs_benchmark_read_action()` C++ + SWIG.** Edit `Benchmark_Extend.h`, `Benchmark_Extend.cpp`, `hyperspace.i` (§2). Rebuild. *Test:* §7.2 — file present returns bytes, absent returns `""`.
- [ ] **T3 — Bump observation to schema_version 2.** Add `last_action_seq` + live `paused` to the M1 builder; update Python `ObservationClient` to expose both (defaults `None`/`False`). *Test:* read obs, confirm fields present and `paused` reflects a manually-set `bPaused`.
- [ ] **T4 — Bridge PAUSE-only loop (no actions yet).** Rewrite `bridge.lua` to freeze every tick and write obs; ignore actions. *Test:* game stays paused indefinitely; obs streams with `last_action_seq: null, paused: true`.
- [ ] **T5 — Action read + seq dedup + frame budget (no dispatch).** Wire `read_json_action()` → decode → dedup → `frame_budget` → unfreeze/refreeze; `dispatch_actions` is a no-op stub. *Test:* §7.5/§7.7 — write `{seq:1, advance_frames:30, actions:[]}`, confirm world advances ~30 frames then re-pauses and `last_action_seq` becomes 1; re-send seq 1, confirm ignored.
- [ ] **T6 — `set_system_power` dispatcher.** Implement `apply_set_system_power` (§4). *Test:* §7.3 — drive shields to level 2, advance, obs shows `powerState.first == 2`. Fallback to Force/SetPowerCap if it under-shoots.
- [ ] **T7 — `move_crew` dispatcher.** Implement `apply_move_crew` (§4). *Test:* §7.4 — move crew 0 to a known room, advance, obs `iRoomId` matches; resolve `slot_id=-1` vs explicit slot.
- [ ] **T8 — Python `AgentSession` (§5).** Implement `reset`/`observe`/`step` + action constructors. *Test:* end-to-end `reset(); step([set_system_power(0,2), move_crew(0,5)])` returns an obs with `last_action_seq==1`, correct power/room, within timeout.
- [ ] **T9 — Race & robustness pass (§7.6/§7.8).** Step `advance_frames=1` in a tight loop; confirm continuity, no escaped `json.decode` errors, no obs gaps. Confirm atomic action writes never yield partial reads.