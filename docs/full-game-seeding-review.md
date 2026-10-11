# Full-game initialization seeding review

Read-only review, 2026-10-10. This note proposes a separate versioned full-game
cohort. It does not change the production bridge, installed native runtime, or
the challenge v4 cohort currently under live validation.

## Current seed contract

`run_visual` calls `reset_episode(seed=...)` before its first visual capture.
The Python reset API passes that seed to the bridge. The bridge's menu handling
sets `_G.ftl_bench_desired_seed`; its `GET_RUN_SEED` callback replaces the run seed
inside `StarMap::NewGame`. These calls do not explicitly initialize native
`random32` before hangar construction.

This is narrower than saying the native RNG is never seeded: Hyperspace seeds
it for sector/map generation. The gap is initialization order and later shared
RNG consumers. `BlueprintManager::GetUnusedCrewName` initializes its separate
name RNG from a native `random32()` draw before `StarMap::NewGame` receives the
requested map seed. Crew names can therefore vary. Name variation alone does
not establish that crew gameplay attributes vary.

The observed historical store-stock variation is material. `Store::OnInit`
seeds CRT `srand`, while the global `random32`/`srandom32` overrides that would
connect it to CRT `rand` are commented out. A fixed run/map seed is not by
itself evidence of identical store stock. Opening the star map also consumes
native random draws for cosmetic ship rotation. General equivalence of the
native RNG stream, including idle/render consumers, has not been measured.

## Source locations inspected

Locations refer to the local source checkout read during this review; function
names identify the same points if line numbers change.

- `adapter/run_visual.py:367`: production visual runner's seeded reset.
- `harness/src/ftl_bench/session.py:341` and `:359`: `start_game` and
  `reset_episode` send the seed as a backstage initialization request.
- `mod/ftl_bench_bridge/dev/ftl_bench_dev.lua:50`: `GET_RUN_SEED` callback;
  `:2395–2433`: reset completion/new-game admission and throttled menu advances.
- Sibling `FTL-Hyperspace/Benchmark_Extend.cpp:159`: `hs_benchmark_advance_menu`
  chooses New Game, overwrite confirmation, or hangar Start according to the
  current native menu. The New Game/confirmation click that opens the hangar
  precedes hangar Start.
- `FTL-Hyperspace/CrewNames.cpp:16–24`: name RNG initialized from `random32()`.
- `FTL-Hyperspace/Seeds.cpp:234–270`: run-seed callback in `StarMap::NewGame`;
  `:78`: `ShipBuilder::Open` calls the original method before its additional UI
  work; `:48–64`: store CRT seeding and disabled global RNG overrides above it;
  `:348–359`: native seed for sector-map generation.
- `FTL-Hyperspace/StarMap.cpp:268–275`: map generation seeds native RNG from the
  current sector seed.
- `FTL-Hyperspace/CustomShipSelect.cpp:3819`: hangar opening calls the original
  method before custom selection initialization.
- `FTL-Hyperspace/CustomEvents.cpp:6320–6332`: map-open rotation RNG draws.
- `FTL-Hyperspace/lua/modules/hyperspace.i:451–456`: existing
  `Hyperspace.setRandomSeed` binding to native `srandom32`.
- `FTL-Hyperspace/lua/LuaScriptInit.cpp:52–55`: `math.randomseed` additionally
  discards one `random32` draw; use the explicit native binding for an exact
  documented initialization contract.

## Minimal pending-on-reset proposal

The existing DLL already exposes `Hyperspace.setRandomSeed(seed)`. A Lua-only
proposal can mark native initialization pending when `start_game(mode=new)` is
accepted and when `reset_episode` reaches the menu. Once canonical difficulty
is verified, consume that flag once immediately before the first native menu
advance that can create the fresh hangar. Record the seed, admission path,
menu stage, and successful call; fail initialization if the call fails. Do not
apply it to continuation, resumed saves, actor actions, or later encounters.

The first menu advance may only open an overwrite warning. Seeding before it
is the smallest proposal but is not an established guarantee: ticks and RNG
consumers can occur before the later confirmation actually creates the hangar.
The safest precise boundary is immediately before the hangar-opening click.
If available menu-state evidence cannot identify that boundary, retain that
limitation and test it rather than claiming precise placement. A separately
recorded seed immediately before hangar Start is a possible two-boundary
initialization experiment, not an equivalent claim of one-time seeding. It
would need its own versioned protocol and acceptance.

## Required evidence before a full-game comparison

1. Preserve the current cohort. Archive/hash any future bridge change and
   specify exactly which RNG binding and initialization boundaries it uses.
2. Repeat fresh starts at least three times under varied menu/render waiting
   periods, covering both new-game paths with and without overwrite warning
   and reset from an active game. Use fresh captures, not cached observation
   reads, for each comparison.
3. Compare exact native gameplay state at hangar/run creation and the first
   actor image: crew species, health, skills, positions and ownership; systems,
   weapons, resources and charge; room oxygen, fires and breaches; map,
   environment and enemy state. Record cosmetic name/gender differences
   separately; do not erase gameplay differences or round floating values.
4. Repeat identical ordinary inputs under fixed-step clock v2, including
   encounters through impact outcomes and a fixed store route through stock
   generation. Check zero-frame idle freeze and exact update budgets.
5. Record the actual observed seed application and initial-state fingerprints,
   all save-restoration and cleanup receipts, and any mismatches. A map-seed
   match or a successful short charge path is not full-game RNG acceptance.

Challenge v4 has its own explicit one-time native seed prerequisite and exact
state comparisons. Its fire/combat timing probes can establish equality of
observed states on those inputs; even a pass does not directly measure equality
of internal RNG streams or establish full-game determinism.
