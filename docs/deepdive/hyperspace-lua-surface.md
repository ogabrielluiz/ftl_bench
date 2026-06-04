# FTL-Hyperspace Deepdive — ftl_bench Grounding

## 1. Executive verdict

Building an LLM-agent interface on top of FTL-Hyperspace is **feasible with moderate, well-scoped C++/SWIG work** — the foundation is unusually strong. Hyperspace already exposes a deep, read-only observation surface (full `ShipManager` for player and enemy: hull, reactor, per-system power/damage/ion/hack, crew position/health/skills, weapons/drones, hazards, star map) and most *destructive* actions through SWIG, plus a real-time pause flag (`CommandGui.bPaused`) and a per-frame `ON_TICK` hook. The critical path is **not** observation — it is three things, in order: (a) confirming a usable **transport** out of the locked-down Lua sandbox (no `io`/`os`/sockets by default), which is the single hard blocker; (b) closing the **high-level action gaps** that are UI-driven today — chiefly weapon-target-and-fire, event-choice confirmation, store purchases, and FTL jump trigger; and (c) wrapping the existing pause flag into a **deterministic frame-step** so the real-time sim becomes turn-based without races. Everything downstream depends on the SWIG extension playbook in §2, so that is the true root of the tree. Confidence in this verdict is high; the only genuinely unverified pieces are the transport latency characteristics and the exact race behavior of pause-step against pending animations (see §11).

## 2. How to extend the Lua API

Every gap in this document resolves to the same mechanical playbook. Hyperspace binds C++ to Lua via **SWIG**, with four generated modules — `Hyperspace`, `Graphics`, `Defines`, `RapidXML` — compiled into a single shared library.

**The pipeline:**
1. Add or expose the C++ symbol. Either it already exists in the game headers (`FTLGameELF64.h` / `FTLGameMacOSAMD64.h`) or you add a method to a Hyperspace extension struct (`*_Extend.h/.cpp`, e.g. `ShipManager_Extend.h`, `CrewMember_Extend.h`, `System_Extend.h`).
2. Make the header visible to SWIG by including it in the `%{ ... %}` block (`/Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/hyperspace.i`, lines ~6–33).
3. Bind it with `%rename("%s") Class::Method;` (expose), `%immutable` (read-only field), `%extend Class { ... }` (synthetic methods), `%template(...)` (STL containers), or a typemap (polymorphic pointers — see the `SpaceDrone*`/`Projectile*` dynamic-cast dispatch at `hyperspace.i:118–143`).
4. Rebuild: `cmake --build . --config Release`. SWIG **regenerates wrapper code automatically**; `processSwigRuntime.sh` guards `swigluarun.h`.
5. Test live with `LuaScriptInit::runLuaString()` (interactive console, `LuaScriptInit.cpp:125–145`), or from a mod via `Hyperspace.<Name>(...)`.

**Key files:**
- `/Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/hyperspace.i` — the 4,600+-line master interface; ~90% of work lands here.
- `/Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/defines.i` — enums for `script.on_internal_event` / `on_render_event` identifiers.
- `/Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/LuaScriptInit.cpp` / `.h` — Lua state creation, `luaopen_*` module loading, global registration.
- `/Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/LuaLibScript.h` — callback registry; `TypeInfo` struct holds `swig_type_info*` for polymorphic returns (the model to copy when exposing new class hierarchies).
- `/Users/ogabrielluiz/Projects/FTL-Hyperspace/CMakeLists.txt` (lines ~35–58) — `swig_add_library(Hyperspace TYPE SHARED LANGUAGE lua ...)`.

**Two recommended conventions for ftl_bench:** (1) keep all benchmark-specific bindings in a dedicated section or a new `ftl_bench.i` so the base Hyperspace API stays stable; (2) put pure-config constants (action enums, reward weights) in a plain Lua file (`lua/ftl_bench_defines.lua`) loaded at init — no SWIG rebuild needed to tweak them.

Confidence: high.

## 3. Observation surface (state reads)

Everything below is readable from Lua **today** unless flagged. Primary access is `Hyperspace.ships.player` / `Hyperspace.ships.enemy` (`ShipManager`, metatable override at `hyperspace.i:514–536`) and the `Hyperspace.Global` singleton.

| Group | Exposed today | Notes / flags |
|---|---|---|
| **Own ship — reactor/systems** | `GetAvailablePower()` (max/avail pair), `GetSystemPower(id)`, `GetSystemPowerMax(id)`, `vSystemList`; per-system `fDamage`/`fMaxDamage`, `powerState`, `Functioning()`, `Powered()`, `NeedsRepairing()`, `GetEffectivePower()`, `IsSystemHacked(level)`, `Ioned()`/`IonDamage()` | Comprehensive. Subsystem→system relationships **NOT** queryable (gap, low effort). |
| **Own ship — hull/resources** | `ship` (hull/rooms), `currentScrap` (RO), `fuel_count` (mutable), `GetDroneCount()`, `GetMissileCount()`, `GetAugmentationList()`, `HasAugmentation()`, `GetAugmentationValue()`, `GetOxygenPercentage()`, `bJumping`, `bDestroyed` | Solid. |
| **Own ship — rooms/hazards** | `GetFireCount(roomId)`, `OxygenSystem.oxygenLevels` (per-room), `Room.iRoomId`/`rect`/`bBlackedOut`, `Room_Extend` (timeDilation, sensorBlind, resist chances) | **Room interior slot layout** partially exposed (gap, med). **Door state** (open/closed/locked/hacked) **NOT** exposed — `Ship.vDoorList` exists but `Door` unbound (gap, low). **Breach/`ExplosionAnimation`** detail **NOT** fully exposed (gap, med). |
| **Enemy ship** | Same `ShipManager` surface via `Hyperspace.ships.enemy` / `Global.GetShipManager(1)` | Fully symmetric with player. `WorldManager.bossShip` **NOT** bound — boss ship only reachable in C++ (gap, low). |
| **Crew** | `GetPosition()`, `iRoomId`, `health` pair, `bDead`/`bMindControlled`/`iOnFire`/`bFighting`/`bSuffocating`/`intruder`, `GetSkillLevel()`/`GetSkillProgress()`, `Can{Fight,Repair,Sabotage,Man,Teleport}`, `GetPowerCooldown()`, `PowerReady()`, race traits (`IsTelepathic`/`IsAnaerobic`/`ProvidesPower`), stat multipliers, `task`, `extend.crewPowers`, `extend.CalculateStat()` | Rich. **Per-room crew counts** must be computed Lua-side (gap, low — add `GetCrewByRoom`). **Morale/mood** not modeled. **Detailed "why power not ready"** breakdown not exposed (gap, med). |
| **Weapons / drones** | `GetWeaponList()` → `ProjectileFactory*` (`cooldown`/`baseCooldown`, `powered`, `requiredPower`, `blueprint`, `targets`/`lastTargets`, `chargeLevel`, `iHackLevel`); `GetDroneList()`; `SpaceDrone.currentLocation`/`speedVector`/`weaponBlueprint`/`weaponCooldown` | Read state is strong; *acting* on it is the gap (§4). |
| **Projectiles in flight** | `SpaceManager.projectiles`, `SpaceManager.drones` (RO vectors), per-projectile position/heading/owner/target, derived type via dynamic cast | **Per-projectile damage dealt / hit count** **NOT** exposed (gap, low). **Time-to-impact / trajectory prediction** **NOT** exposed (gap, med). |
| **Shields** | `Shields.shields` (charger/power), `baseShield` (Ellipse), image state | Real-time recharge-rate / time-to-next-layer **NOT** directly exposed (gap, med). |
| **Map / context** | `StarMap.locations`, `currentLoc`, `sectors`, `currentSector`, `worldLevel`, `bMapRevealed`, `pursuitDelay`, `shipPosition`; `Location` fields (`connectedLocations`, `beacon`, `known`/`visited`, `dangerZone`, `nebula`, `boss`, `event`, `store`); `LocationEvent` (text, `stuff`/rewards, `environment`, `store`, `boarders`, `choices`) | Boss pursuit path fields (`bossLoc`, `boss_path`) commented out in `hyperspace.i` (gap, low — uncomment). |
| **Global context / GUI** | `WorldManager` (`currentDifficulty`, `bStartedGame`, `bLoadingGame`, `playerCrewCount`, `killedCrew`), `SpaceManager` hazard flags (`sunLevel`, `pulsarLevel`, `bPDS`, `bNebula`, `bStorm`, `asteroidGenerator.bRunning`), `CommandGui` (`bPaused`, `choiceBoxOpen`, `shipStatus`, etc.), `Global.currentSeed`/`IsSeededRun()` | Hazards are **bool/scalar flags only** — no per-asteroid/sun-pulse enumeration (gap, med). No single `GetGameState()` enum (gap, med — see §10). |

Confidence: high. Core combat/crew/map state is comprehensive enough to prototype against immediately; flagged gaps are mostly "nice to have."

## 4. Action surface

`X` = exposed and directly usable from Lua. Effort estimates are for new bindings.

| Action | Status | Binding / where to hook | Effort |
|---|---|---|---|
| **Power: increase/decrease/cap** | X exposed | `ShipSystem:IncreasePower(amt,force)`, `:DecreasePower(force)`, `:SetPowerCap(cap)`, `:ForceIncreasePower`/`:ForceDecreasePower`, `:UpgradeSystem(amt)` (`hyperspace.i:2158–2181`) | — |
| **Crew: move to room** | X exposed | `CrewMember:MoveToRoom(roomId,slotId,forceMove)` (`:3384`), `:SetRoom`, `:SetRoomPath`, `:SetCurrentSystem`, `:SetTask` | — |
| **Crew: teleport to enemy** | X exposed | `CrewMember_Extend:InitiateTeleport(shipId,roomId,slotId)`; `TeleportSystem:InitiateTeleport()`/`:ForceReady()`/`:SetArmed()` | — |
| **Cloak / battery toggle** | X exposed | `CloakingSystem.bTurnedOn`, `BatterySystem.bTurnedOn` (mutable fields) | — |
| **Hacking: launch drone** | partial | `HackingSystem:BlowHackingDrone()` exposed; **no `TargetSystem(id)` deploy-and-aim wrapper** | med |
| **Mind control: arm** | partial | `MindSystem:SetArmed()`/`:SetHackingLevel()` exposed; `queuedCrew` readable but **no `ControlCrew(target)` one-shot** | med |
| **Weapons: select/arm** | X exposed | `ArmamentControl:SelectArmament()`/`:DeselectArmament()`; `WeaponControl.armedWeapon`/`armedSlot` readable | — |
| **Weapons: target a room + fire** | **NEEDS BINDING (critical)** | `ProjectileFactory:Fire(points, target)` exists but requires pre-computed world `Pointf`s + int `targetId` — agent can't map "room 3" to those. Add `ProjectileFactory:SetWeaponTargetRoom(shipId, roomId)` (compute room center, set `.targets`/`.targetId`/`.currentShipTarget`) + `:AutoTargetRoom(roomId, autoFire)` wrapper. Also expose `WeaponControl::Fire(points,target,autoFire)` (`FTLGameELF64.h:4106`, currently unbound) for the autofire flag, and `Ship:GetRoomCenter(roomId)` (inverse of exposed `GetSelectedRoomId`). | low–med |
| **Weapons: query target** | NEEDS BINDING | `GetTargetedRoom()` via reverse lookup of `targets[0]` through `GetSelectedRoomId(x,y,true)`; `CanFireNow()` cooldown/power/ammo check | low |
| **Beam weapon aim** | NEEDS BINDING | `WeaponSystem:SelectBeamTarget(p1,p2)` — defer; missile/laser targeting covers most cases | high |
| **Drones: deploy / target** | partial | Count modifiable; `SpaceDrone.SetWeaponTarget` exists for space drones, but no "deploy drone X / set movement target" command API | med |
| **Special: doors open/close/lock** | NEEDS BINDING | `Door:ApplyDamage()` exposed (breach), but no `Door:SetOpen/SetLocked`; `Ship.vDoorList` readable | low |
| **Special: oxygen / fire** | X exposed | `OxygenSystem:ModifyRoomOxygen()`/`:EmptyOxygen()`; `ShipManager:StartFire(roomId)`, `:DamageArea/:DamageBeam/:DamageHull/:DamageSystem` | — |
| **Jump / FTL trigger** | **NEEDS BINDING** | `StarMap` exposes no `Jump()`/`ExecuteJump()`. Add `StarMap_Extend:InitiateJump(Location*)` or `WorldManager` wrapper. Jump is currently event-driven only. | low |
| **Event choice: read** | X exposed | `ChoiceBox.selectedChoice`/`potentialChoice` (RO), `.choices`, `:GetChoices()`; `LocationEvent:GetChoices()`/`:AddChoice()`/`:RemoveChoice()`; `PRE/POST_CREATE_CHOICEBOX` callbacks | — |
| **Event choice: select & confirm** | **NEEDS BINDING (critical)** | `selectedChoice` is read-only and setting it does **not** execute. Add `ChoiceBox:selectedChoice` setter + `ChoiceBox:ConfirmChoice(index)` / `OnChoiceSelect()` to trigger underlying game logic. Hook ~`hyperspace.i:987`. | low–med |
| **Store: read contents** | **NEEDS BINDING** | `Store`/`StoreBox` classes entirely unbound; `LocationEvent.pStore` commented out. Expose `Store`, `vStoreBoxes`, item fields/pricing. | high |
| **Store: buy/sell** | **NEEDS BINDING** | `StoreBox::Purchase()` (hooks exist in `CustomStore.cpp` but not Lua-exposed); `Store::MouseClick`/`OnInit`/`KeyDown` unbound. | high |
| **Add equipment / augment (cheat-style)** | X exposed | `ShipManager:AddWeapon()`/`:AddDrone()`; `ShipObject:AddAugmentation()`/`:RemoveAugmentation()` — useful for scenario setup, not normal play | — |

**Bottom line:** roughly 80–85% of the action surface is already live (all power, crew movement/teleport, special-system toggles, environmental damage). The benchmark-blocking new bindings are concentrated in four UI-driven actions: **weapon-target-and-fire, event-choice-confirm, store transactions, and jump trigger.** Of these, jump and choice-confirm and weapon-targeting are low/medium effort; store is the only high-effort item and could be deferred from a v1 that skips shops or handles them via a coarser mechanism.

Confidence: high (weapon-targeting binding is a thin wrapper over existing `GetSelectedRoomId`/drone-targeting logic — low reverse-engineering risk).

## 5. Frame-gating & pause

The real-time sim can be made turn-based **with no strictly required new C++**, using mechanisms already exposed:

- **`Hyperspace.FPS.SpeedFactor`** (float, mutable) — the cleanest pause: set to `0` to freeze time, restore to `1.0` to resume. This is exactly the pattern Hyperspace itself uses during loading (`Global.cpp:186–192`). `Hyperspace.FPS.speedLevel` (int) is a secondary control.
- **`Hyperspace.App.gui.bPaused`** (bool, mutable) — the spacebar-pause flag, also writable. Note `bAutoPaused`, `menu_pause`, `event_pause` are **read-only** and tied to FTL's own pause-on-event logic — do not rely on them for harness control.
- **`ON_TICK`** (`Defines.InternalEvents.ON_TICK`) — fires every frame from `CApp::OnLoop` (`Misc.cpp:1118–1123`), no args/returns. Register via `script.on_internal_event(Defines.InternalEvents.ON_TICK, fn)`.

**Turn-based loop (no new C++):** in `ON_TICK`, keep a frame budget; pause (`SpeedFactor = 0` or `bPaused = true`), let the agent read state and issue actions, then unpause for N frames and re-pause when the budget hits zero.

**What should be built for robustness (not strictly required):**
- **`CFPS:StepFrames(n)`** — atomic "run exactly N frames then pause" to avoid races with pending animations/sim ops that the Lua-side toggle can hit (gap, med; hook `CApp::OnLoop` / new `CFPS` method).
- **`CFPS:GetFrameCount()`** — read a frame counter so the agent can correlate actions to frames (gap, low).
- **`PAUSE_CHANGED` internal event** — so the agent is notified rather than polling `bPaused` (gap, med).

Confidence: high that the polling-based loop works; medium on whether races force the dedicated `StepFrames` hook — this needs a hands-on check (§11).

## 6. Determinism / seeds

**Reading the seed works today; setting it from Lua does not.**

Exposed:
- `Hyperspace.Global.currentSeed` (unsigned int, **read-only / `%immutable`**).
- `Hyperspace.Global.IsSeededRun()` (bool).
- `Defines.InternalEvents.GET_RUN_SEED` — fires at `NewGame`; receives `(bool isCustomSeed, int seed)` and **can return a modified `(isCustomSeed, seed)`**. This is the one Lua hook that can *influence* the seed today.
- `Hyperspace.random32()` and `Hyperspace.setRandomSeed(seed)` (maps to `srandom32`) — the game RNG. **Use these, not Lua `math.random`,** or the agent desyncs from game state.
- `Event:GetBaseEvent(name, worldLevel, ignoreUnique, seed)` — explicit-seed event generation.

What the seed controls: `Global::currentSeed` drives `sectorMapSeed` (map layout), `questSeed`, `bossFleetSeed`, plus per-sector `currentSectorSeed`. C++ has `SetSeed(unsigned int)` (`Seeds.cpp:371`) and a test harness `GameAccess::Seeding::setSeed()`.

**Harness recommendation:** either (a) call `GameAccess::Seeding::setSeed()` from C++ before launching the agent, or (b) add the missing Lua binding — `Hyperspace.SetRunSeed(uint)` wrapping `SetSeed`, or make `currentSeed` mutable (gap, **low**). Also uncomment `StarMap::sectorMapSeed`/`currentSectorSeed` (`hyperspace.i:1375–1378`) and expose `questSeed`/`bossFleetSeed` (low) so the agent/harness can verify sub-seeds.

**Reproducibility caveats:** determinism holds only under an **identical mod set, identical FTL version (Advanced Edition vs vanilla), and identical settings (difficulty, hard mode, unlocks)**. The `std::mt19937 seededRng` engine counter is not directly readable, so mid-run RNG-state checkpointing needs a new getter (med).

Confidence: high.

## 7. Decision-point callbacks

Hyperspace defines 50+ internal events (`lua/InternalEvents.h`, taxonomy in `wiki/Lua-Defines-module.md`) plus 25+ render-layer events (`lua/RenderEvents.h`). Register via `script.on_internal_event(Defines.InternalEvents.<ID>, fn)`. These are the natural re-pause points — gate the agent at semantically meaningful moments rather than every frame.

| Decision context | Hook(s) | Good re-pause behavior |
|---|---|---|
| **Per-frame baseline** | `ON_TICK` | Frame-budget gating; cheapest place to snapshot state. |
| **Combat begins / new encounter** | `JUMP_ARRIVE` (and `JUMP_LEAVE`) | Re-pause on arrival; full re-plan with fresh enemy state. |
| **Incoming threat** | `PROJECTILE_FIRE`, `DAMAGE_AREA`/`DAMAGE_AREA_HIT`, `DAMAGE_BEAM`, `DAMAGE_SYSTEM`, `SHIELD_COLLISION` | Re-pause to react to damage; note ordering vs. damage calc is undocumented (verify, §11). |
| **Crew/system loops** | `SHIP_LOOP(ShipManager)`, `CREW_LOOP(CrewMember)` | Per-ship / per-crew observation each tick without manual iteration. |
| **Narrative / event** | `PRE_CREATE_CHOICEBOX(LocationEvent)`, `POST_CREATE_CHOICEBOX(ChoiceBox, LocationEvent)` | Re-pause when a choice box opens — the key gate for event-choice decisions (pairs with the choice-confirm binding from §4). |
| **Beacon / map context** | `GET_BEACON_HAZARD`, `GET_RUN_SEED` | Inspect/influence hazard and seed at generation time. |
| **Power/abilities** | `ACTIVATE_POWER`, `PREPARE_POWER`, `POWER_REQ`, `POWER_READY`, `SET_BONUS_POWER` | Gate special-ability decisions. |
| **Weapon arming** | `SELECT_ARMAMENT_PRE/POST` | Observe/override weapon selection intent. |

**Recommended pattern:** subscribe to `ON_TICK` for the budget loop plus `JUMP_ARRIVE`, `POST_CREATE_CHOICEBOX`, and a damage hook (`PROJECTILE_FIRE`/`DAMAGE_SYSTEM`) as forced re-pause triggers. A documentation gap worth closing: the exact firing order of each event relative to damage/cooldown resolution is not written down and matters for agent correctness.

Confidence: high on the hook inventory; medium on per-event ordering semantics.

## 8. Transport

**This is the single hard blocker.** The Lua sandbox is deliberately locked down (`lua/linit.c`): only `_G`, `table`, `string`, `math`, `utf8`, `bit32` are enabled — `io`, `os`, `package`, `coroutine`, `debug` are **disabled**, and `LuaScriptInit.cpp` further strips `rawget`/`rawset`/`rawequal`. So **no file I/O, no sockets, no `os.tmpname`, no networking** out of the box. There is no standard way for an external harness to talk to the agent without new C++.

Three options, in recommended order:

- **Option A — file bridge (recommended for prototyping).** Enable `io` in `linit.c` (low) *or*, better, add a narrow C++ binding `Hyperspace.Benchmark.write_json_observation(str)` / `read_action() -> str` doing atomic writes/reads to a fixed dir (e.g. `~/.ftl_hs_agent/`). Harness polls files. Pros: sandbox stays mostly intact, simple, reliable. Cons: file-poll latency.
- **Option B — IPC socket (recommended for low-latency real-time).** New `Agent_Extend.cpp` + SWIG bindings wrapping AF_UNIX sockets (Linux/macOS, prefer the abstract namespace) / Windows named pipes: `Hyperspace.Agent.connect(path) -> handle`, `handle:send_json(str)`, `handle:recv_json() -> str`. Pros: bidirectional, low latency. Cons: more C++, platform-specific.
- **Option C — embedded/stateful Lua tables.** Agent keeps state in `_G`; harness calls a `serialize_observation()`/`deserialize_action()` Lua entry point through a C++ wrapper. No file I/O, but high overhead and requires the harness to drive the interpreter.

**Companion need: JSON.** No JSON library is bundled. Either enable `package` + lua-cjson, or add a small `Hyperspace.json.encode/decode` C++ binding (med). Required regardless of which transport is chosen.

**Wiring:** collect observations in an `ON_TICK` (or the §7 decision hooks) into a Lua table, serialize on demand; route actions through a `process_agent_action(action_json)` dispatcher that calls the `ShipManager`/weapon/crew methods from §4.

Confidence: high that transport requires new C++; medium on which option wins — depends on the latency budget, which is unmeasured (§11).

## 9. Savefile fallback

The savefile path (`SaveFile.h/.cpp`, binary `profile/*.sav` + `continue.sav`) is a **partial, lower-fidelity** alternative — useful for snapshot/restore and deterministic test-case construction, not for real-time observation.

**Can supply:** beacon-granularity game state — player & enemy ship systems/crew/resources, current location index, star-map state, sector/seed context. `StarMap::SaveGame(fd)` / `LoadGame(fd)` and `WorldManager::SaveGame/LoadGame` **exist in C++ but are not Lua-bound** — exposing them (gap, **low**) would enable instant snapshot-save/restore at any beacon, which is high-value for building reproducible scenarios and for tree-search rollback.

**Cannot supply (or only poorly):** real-time hazard granularity, in-flight projectiles, exact frame-level sim state, and live recharge/cooldown timers — all of which only the live API gives. Parsing `continue.sav` directly from Lua is a **high-effort** binary reverse-engineering job (`SaveFileHandler::ParseContinueSaveToLua()`); the format mirrors `profile.sav` (`SaveFile.cpp:61–199`) and would need a field-offset validation harness.

**Recommendation:** treat savefile as a **checkpoint/restore mechanism** (expose `SaveGame`/`LoadGame` — low effort), not as the observation channel. Live API + transport (§8) is the primary path; savefile is the rollback/branching aid.

Confidence: high.

## 10. Extension work list

Prioritized, file-level. "Effort" and "risk" are independent (risk = chance the binding is harder than it looks or destabilizes the build).

**P0 — benchmark-blocking**

| # | Task | File(s) | Effort | Risk |
|---|---|---|---|---|
| 1 | **Transport bridge** — `Hyperspace.Benchmark`/`Agent` class: file or AF_UNIX/named-pipe JSON I/O | new `Agent_Extend.cpp/.h`, `hyperspace.i`, maybe `linit.c` | high | med (platform-specific, sandbox implications) |
| 2 | **JSON encode/decode** binding | new `lua/modules/json.i` or `hyperspace.i` | med | low |
| 3 | **Weapon target-and-fire**: `ProjectileFactory:SetWeaponTargetRoom(shipId,roomId)`, `:AutoTargetRoom(roomId,autoFire)`, `Ship:GetRoomCenter(roomId)`, expose `WeaponControl::Fire(...)` | `hyperspace.i` (~2397), thin C++ over `GetSelectedRoomId` | low–med | low |
| 4 | **Event-choice confirm**: `ChoiceBox.selectedChoice` setter + `:ConfirmChoice(index)` | `hyperspace.i` (~987), `FTLGameMacOSAMD64.h` | low–med | med (must trigger underlying execution path correctly) |
| 5 | **Jump trigger**: `StarMap_Extend:InitiateJump(Location*)` | new/`StarMap_Extend`, `hyperspace.i` | low | low |
| 6 | **Frame-step + pause notify**: `CFPS:StepFrames(n)`, `CFPS:GetFrameCount()`, `PAUSE_CHANGED` event | `FTLGameMacOSAMD64.h`, `Misc.cpp`, `InternalEvents.h`, `hyperspace.i` | med | med (race semantics) |
| 7 | **Seed setter**: `Hyperspace.SetRunSeed(uint)` (wrap `Seeds.cpp::SetSeed`) or mutable `currentSeed` | `hyperspace.i` (~500) | low | low |

**P1 — high value, not strictly blocking**

| # | Task | File(s) | Effort | Risk |
|---|---|---|---|---|
| 8 | **Save/Load snapshot**: bind `StarMap`/`WorldManager` `SaveGame`/`LoadGame` | `hyperspace.i` (~912) | low | low |
| 9 | **Enemy/boss ship**: bind `WorldManager.bossShip`, add `ships.boss` metatable | `hyperspace.i` (~510) | low | low |
| 10 | **`GetGameState()` enum** (CHOICE_PENDING / IN_COMBAT / TRAVELING / PAUSED) | new `CustomGameState` or `Global` method, `hyperspace.i` | med | low |
| 11 | **Door control**: bind `Door` open/close/lock | `hyperspace.i` (`Ship.vDoorList`) | low | low |
| 12 | **Hacking/mind-control targeting shortcuts**: `HackingSystem:TargetSystem(id)`, `MindSystem:ControlCrew(target)` | `hyperspace.i` | med | low |
| 13 | **Per-room crew count / room state** helpers | `ShipManager_Extend.h/.cpp` | low | low |
| 14 | **Seed sub-fields**: uncomment `sectorMapSeed`/`currentSectorSeed`, expose `questSeed`/`bossFleetSeed` | `hyperspace.i` (~1375) | low | low |
| 15 | **Projectile damage/TTL**, weapon `CanFireNow()`, `GetTargetedRoom()` | `hyperspace.i`, `Projectile_Extend.h` | low–med | low |

**P2 — defer-able**

| # | Task | File(s) | Effort | Risk |
|---|---|---|---|---|
| 16 | **Store transactions**: bind `Store`, `StoreBox`, `vStoreBoxes`, `Purchase()`, `LocationEvent.pStore` | `hyperspace.i` (~851/936), `Store_Extend.h`, `CustomStore.cpp` | high | med |
| 17 | **Beam targeting**: `WeaponSystem:SelectBeamTarget(p1,p2)` | `hyperspace.i` | high | med |
| 18 | **Drone deploy/target** command API | `hyperspace.i`, `SpaceDrone` | med | low |
| 19 | **Hazard enumeration** (asteroid/sun/pulse vectors vs. bool flags) | `FTLGameMacOSAMD64.h`, `hyperspace.i` | med | med (structs may need exposing) |
| 20 | **EventButton selection** API (custom-event buttons) | `EventButtons.h/.cpp`, `hyperspace.i` | high | med |
| 21 | **Telemetry/logging** JSON sink for eval traces | new `ftl_bench` module | low | low |
| 22 | **`continue.sav` parser** fallback | `SaveFile.cpp` | high | high (binary RE) |

The two structural roots (#1 transport, #2 JSON) gate everything; the four UI-action bindings (#3–#5, #16) are the gameplay-completeness core; #6–#7 give the turn-based + deterministic guarantees the benchmark depends on.

## 11. Open questions / spikes

1. **Pause/step race (highest priority).** Does the Lua-side `SpeedFactor=0` / `bPaused` toggle in `ON_TICK` cleanly freeze the sim, or do pending animations/sim ops slip a frame? This decides whether the simple polling loop (§5) suffices or whether `CFPS:StepFrames(n)` (#6) is mandatory. Hands-on: pause mid-combat, read state across several ticks, confirm no advancement.
2. **Transport latency budget.** Measure file-bridge round-trip (Option A) vs. socket (Option B) to pick the transport. Unmeasured; drives the §8 decision and whether real-time-ish play is even on the table vs. strictly turn-based.
3. **Choice-confirm execution path.** Verify that a new `ChoiceBox:ConfirmChoice()` actually runs the event's consequences (rewards, state transitions, next event) and isn't just a UI highlight. Setting `selectedChoice` alone is confirmed *not* to execute — the spike is whether the underlying call we hook is reachable/public.
4. **Internal-event firing order.** Document when `PROJECTILE_FIRE`, `DAMAGE_*`, and cooldown updates fire relative to damage resolution (§7). Affects whether the agent sees pre- or post-damage state at each re-pause.
5. **Weapon target-room round-trip.** Confirm `SetWeaponTargetRoom` → `Fire()` actually hits the intended enemy room (room-center → `GetSelectedRoomId` inverse is assumed correct but unverified end-to-end).
6. **Seed completeness.** With a fixed `currentSeed` and identical mods/version, do map layout, events, and boss fleet actually reproduce bit-for-bit across runs? Needs an A/B replay. Also: is mid-run `mt19937` counter checkpointing needed for the benchmark, or is run-start seeding enough?
7. **SaveGame/LoadGame mid-run fidelity.** Once bound (#8), verify a beacon-level save/restore round-trips player+enemy live state without corruption — the precondition for using it as the rollback mechanism (§9).
8. **SWIG threading.** Validate multi-crew / multi-action calls in one tick don't expose SWIG thread-safety issues under load (flagged as implicit-but-unverified).
