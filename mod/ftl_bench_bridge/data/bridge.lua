-- ftl_bench bridge: throttled ON_TICK -> build observation -> json -> write file.
-- hs_log_file is C++-only; Lua logs via print (base lib is enabled in the sandbox).
local THROTTLE_INTERVAL = 10   -- write every N ticks (~6 Hz at 60 FPS)
local frame_counter = 0

local function on_tick_handler()
  frame_counter = frame_counter + 1
  if frame_counter % THROTTLE_INTERVAL ~= 0 then return end

  local ok, result = pcall(function()
    local obs = _G.ftl_bench.build_observation(frame_counter)
    local payload = _G.json.encode(obs)
    return Hyperspace.write_json_observation(payload)
  end)

  if not ok then
    print("[ftl_bench] observation tick error: " .. tostring(result))
  elseif result == false then
    print("[ftl_bench] write_json_observation returned false")
  end
end

script.on_internal_event(Defines.InternalEvents.ON_TICK, on_tick_handler)
