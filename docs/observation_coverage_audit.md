# Observation coverage audit

Updated 2026-10-04. This is an interface audit, not an agent strategy guide. The prompt exposes facts and command semantics; strategy remains the agent's responsibility.

## Evidence levels

A preserved field proves adapter coverage. A real Lua engine-double test proves bridge control logic. Only a retained real-game observation/action trace proves a binding and actuator on the deployed native build. Optional probes remain optional until that evidence exists.

| Player-visible information | Current contract | Evidence / limits |
|---|---|---|
| Hull, oxygen, fuel, missiles, drone parts, scrap | Preserved in compact | Drone parts regression locks the resource field |
| Reactor allocation and storm cap | Raw and compact usable power fields | Native PowerManager-backed observation; special hazards need live traces |
| Systems, repair, ion and hacking | Power, room, damage, repair, `ion`, `ioned`, `hacked` | Compact regressions; idle hacking uses native lock count 0 |
| Crew, fires and intruders | Owned player crew with original IDs, owner/location/control fields; separate hostile intruders | Detailed skills remain raw-only; native control guard and both serializers covered by real Lua regressions |
| Rooms and doors | Oxygen/fire and optional breach facts; inner doors and outer airlocks | Airlocks marked `airlock: true`, space endpoint -1; real Lua and compact regressions |
| Player weapons | Type, power, charge, ready and pending fire | Real Lua tests cover charging beams, missed full-charge ticks and one release |
| Shot outcomes and enemy attacks | Shot counters, enemy weapon charge, incoming projectiles | Native projectile event coverage needs representative live traces |
| Enemy combat/targeting | Exact native hostility plus destruction/warp facts; friendly ship pointers remain visible | Native `_targetable.hostile` matches combat UI; unknown is never inferred hostile; retained v7 live fixture verifies natural surrender, refused fire/no ammo loss and charged friendly sector departure |
| Enemy systems/crew/drones | Rooms, hacking, crew positions and optional health/tasks | Bound facts only; optional scalar probes are not invented |
| Special systems | Cloak, battery, hacking, drones, teleporter, mind-control readiness | Per-system blocks preserved; installed capability does not prove every encounter works |
| Map and hazards | Sector/current position, connected beacons and known route metadata | Travel credit requires actual observed movement |
| Events | Text, original indices, native type/availability, open time and keyboard mode | Native type 1 is disabled; Lua regressions cover delay, pending selection and refusal; hidden rewards/costs are not guessed |
| Stores | Visible indexed transactions | Bound inventory/price facts only |
| Upgrades | Native system/reactor next cost, cap and `can_upgrade` | Retained native fixture verifies exact prices and no charge on invalid, unaffordable or blocked requests; no Lua price table/deduction |
| Fuel recovery | Native out-of-fuel, distress, wait legality and waiting state | Retained native fixture verifies closed-map controls, distress idempotence and Wait followed by an encounter; frame waits do not substitute for a recovery turn |
| Sector chooser | Choosing flag; choices if bound | Richer choice facts remain unverified |
| Flagship specifics | Presence plus optional phase/surge/super-shield facts | Raw stage counters cannot establish victory or completed phases |
| Native victory | Explicit top-level `victory` from native getter | Getter uses GUI won/victory flags; absent capability is not a false win |
| Native score | Pure live StatTracker getter, tagged `native_live_v1` | Exact FTL 1.6.9 scrap/kill/beacon formula verified against installed executable; saved TopScore can be stale |
| Setup identity | Seed, ship blueprint, native difficulty | Runner checks Kestrel A/`PLAYER_SHIP_HARD` and easy/`0` after reset |
| Concession/error lifecycle | Terminal records retained | `giveup` is an unsolved harness concession, not a game victory |

## Native dependency

`native/patches/0002-economy-fuel-controls.patch` is the complete protocol-5 patch. It retains reliable controls, setup, live score and victory getters and adds exact system/reactor upgrades plus native fuel recovery. The original protocol-4 patch/manifest remain archived. Lua adds guarded crew/event handling and verifies economy bindings/state before reporting `upgrade_rules` and `fuel_recovery` capabilities. Runner/ruleset v7 additionally requires `native-sector-neighbors-v1`, native economy `sector_navigation_version: 1` and Lua `sector_navigation: true`, so the earlier protocol-5 sector type/index defect cannot satisfy the current routing gate. `native-beacon-readiness-v1` separately requires economy `beacon_navigation_version: 1` and Lua `beacon_navigation: true`, enforcing native button/full-timer/system/fuel/context readiness, with pending defeat as guidance only.

`native-enemy-hostility-v1` requires Lua `enemy_hostility: true`. A surrendered ship can retain positive hull, weapons and a native ship pointer; combat and targeting use the native `_targetable.hostile` flag. Non-hostile, destroyed, jumping or unknown-state enemy targets reject enemy-directed weapon requests and clear queued enemy fire. Dispatch feedback records `enemy_hostile`, `enemy_targetable` and accepted queue state. `targetable` and compact `active` never become true from hull or equipment alone. Friendly ships do not independently block a charged native-legal sector exit.

Raw and compact `economy` preserve `upgrade_available`, native system IDs, base caps, maximum levels, next costs and `can_upgrade`, plus reactor and `fuel_recovery` facts. Native nullable cost/reactor entries may be omitted by the Lua codec; absent cost is unknown/unavailable, never zero/free. Native cost remains visible when a modal/combat state blocks purchasing. The native action checks legality/cap/affordability again and charges only a successful level increase. No generic Lua price table or independent scrap deduction remains.

`waitfuel` queues the game's out-of-fuel Wait button and `distress on|off` uses its toggle. Normal frame progression resolves animation, encounters and fleet consequences. The bridge never creates fuel or chooses an event outcome. Fuel recovery is a game turn; ordinary `wait`/`advance` only pass frames. Upgrade/fuel `action_feedback` reports native acceptance, refusal, missing bindings and exceptions.

Events read actual `ChoiceText.type`: type 1 is disabled; known other types are available, without inferring a blue marker. Native `ChoiceBox.openTime` and immutable `Settings.dialogKeys` are exposed. Selection goes through the native number-key path once. The bridge rejects disabled and already queued choices and preserves native input delay. Applied feedback requires the requested `selectedChoice`, meaning queued selection rather than a completed branch. Hidden `ResourceEvent` outcomes and unverified visible costs remain omitted.

The authoritative native victory getter reads `CommandGui::alreadyWon` or the game-over screen's `bVictory`, gated on a started game. The bridge emits a boolean; the scorer never turns a raw boss stage or ordinary game-over screen into a win.

Lua capabilities `crew_control_guard` and `crew_ownership` establish `owned-player-crew-v1`. Native `vCrewList` can include hostile boarders; neither physical presence nor the `intruder` flag alone establishes ownership. `iShipId == 0` identifies player-owned crew, while `currentShipId` identifies location. Movement requires ownership, `GetControllable()` and positive health, and rejected moves appear in `action_feedback`. Own boarders retain ownership. The previous direct `MoveToRoom` path bypassed UI controllability; its model trial was stopped and retained only as a diagnostic. No DLL rebuild was needed because these getters were already bound.

Setup identity uses native `myBlueprint.blueprintName` and the engine's `Global::difficulty` settings pointer. Live checks caught an absent `name` field and an invalid raw `WorldManager.currentDifficulty` value; those probes are no longer used. The guarded native setter selects easy before a new-game click and the bridge verifies it before allowing the flow to advance. Actual post-reset identity is still independently checked.

The live-score getter uses current-run `ScoreKeeper::stats[2/0/1].current`, without calling `Save`. The Windows FTL 1.6.9 `ScoreKeeper::Save` calculation at 0x442bcd–0x442c20 confirms scrap + 20×kills + 10×beacons, multiplied by 1.0/1.25/1.5 for easy/normal/hard and truncated. Raw score components accompany the getter. Legacy TopScore snapshot values are not authoritative current-run scores.

Historical v2 Windows validation matched this formula in all 35 scored snapshots, including fresh retry score 10 and crew-loss score 59. The later v3 Sol trace matched 91 scored snapshots and ended in a fuel-zero concession at 329, with no game over/victory. It is diagnostic because event availability, upgrade pricing and recovery were incomplete. Neither is a v7 model comparison. See `docs/NEXT.md` for retained evidence and all five contract boundaries.

The patch manifest records the reference source commit and patch hash. Installed DLL/bridge hashes and native build provenance are recorded independently in run manifests, so a claimed build does not substitute for the artifact actually used.

## Remaining non-strategy gaps

- Retain representative real-engine traces for optional event markers, sector choices, flagship surge state, breach facts and special-system actuators. Native upgrade/fuel, beacon-readiness and all-seven-sector fixtures are retained separately and excluded from model comparisons.
- Expose completed intermediate flagship phases only after verified native semantics and bindings exist.
- Broaden ship/difficulty setup only when the native interface can select and verify them.
