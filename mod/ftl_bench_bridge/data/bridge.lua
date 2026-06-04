-- ftl_bench bootstrap (patched into ftl.dat; intentionally minimal & stable).
-- The real per-tick logic lives in an EXTERNAL file the bridge hot-reloads:
--   ~/Library/Application Support/FasterThanLight/ftl_bench_dev.lua
-- which defines _G.ftl_bench_tick (called every frame here). Touching a
-- 'ftl_bench_reload' marker makes Hyperspace.benchmark_reload_dev() re-run it
-- live — no re-patch, no relaunch, run state preserved. See scripts/deploy_dev.sh.
local reload_counter = 0

script.on_internal_event(Defines.InternalEvents.ON_TICK, function()
  reload_counter = reload_counter + 1
  if reload_counter % 15 == 0 then
    pcall(Hyperspace.benchmark_reload_dev)   -- no-op unless the marker file exists
  end
  local tick = _G.ftl_bench_tick
  if tick then pcall(tick) end
end)

print("[ftl_bench] bootstrap loaded (hot-reload ready)")
