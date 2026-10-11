"""Run the shipped visual state machine against native input/render doubles."""
import json

import pytest

from test_bridge_lua import bridge


def visual_bridge():
    lua = bridge()
    lua.execute("""
      input_calls={}; captures=0; blocked=false; external_generation="0"; external_detected=false
      clock_owned=false; clock_advancing=false; world_updates=0
      Hyperspace.benchmark_visual_set_clock=function(enabled,advance)
        clock_owned=enabled; clock_advancing=advance; return true
      end
      local original_engine_tick=engine_tick
      function engine_tick()
        if not clock_owned or clock_advancing then
          if clock_owned then world_updates=world_updates+1 end
          if on_world_update then on_world_update() end
          original_engine_tick()
        else _G.ftl_bench_tick() end
      end
      Hyperspace.benchmark_visual_capabilities=function()
        return json.encode({visual_io_version=1,capture=true,input=true,width=1280,height=720,
          external_input_guard=true,external_input_generation=external_generation,external_input_detected=external_detected,
          visual_clock_version=2,fixed_step_numerator=1,fixed_step_denominator=60,simulated_updates=tostring(world_updates),world_updates=tostring(world_updates)})
      end
      Hyperspace.benchmark_visual_simulation_blocked=function()
        return blocked or (gui.choiceBoxOpen == true and not (gui.choiceBox and gui.choiceBox.selectedChoice >= 0))
      end
      for _,name in ipairs({'mouse_move','mouse_click','mouse_drag','key_press'}) do
        Hyperspace['benchmark_'..name]=function(...)
          input_calls[#input_calls+1]={name=name,args={...}}
          if name == 'key_press' and (...) == 'space' then gui.bPaused=not gui.bPaused end
          if on_input then on_input(name,...) end
          return true
        end
      end
      Hyperspace.benchmark_write_visual_observation=function(encoded,seq,tick,requested,actual,feedback)
        if capture_fails then return '' end
        assert(gui.bPaused)
        captures=captures+1
        local v={visual_io_version=1,capture_id='capture-'..captures,frame_id='frame-'..captures,
          action_seq=seq,frame=tick,render_frame=captures,width=1280,height=720,
          path='frame-'..captures..'.png',format='png',coordinate_space='client',paused=true,
          requested_frames=requested,actual_frames=actual,input_feedback=json.decode(feedback),
          external_input_generation=external_generation,external_input_detected=external_detected,
          visual_clock_version=2,fixed_step_numerator=1,fixed_step_denominator=60,simulated_updates=tostring(world_updates),world_updates=tostring(world_updates)}
        local obs=json.decode(encoded); obs.visual=v; last_obs=json.encode(obs)
        return json.encode(v)
      end
    """)
    return lua


def request(lua, seq, actions=(), frames=0, expected=None, mode="visual-v1", expected_generation="0"):
    packet = {"seq": seq, "observation_mode": mode, "actions": list(actions), "advance_frames": frames}
    if expected is not None:
        packet["expected_capture_id"] = expected
        if expected_generation is not None:
            packet["expected_external_input_generation"] = expected_generation
    lua.globals().action_json = json.dumps(packet)
    lua.globals().engine_tick()


def render(lua):
    lua.globals().ftl_bench_visual_render()
    return json.loads(lua.globals().last_obs)


def capture(lua):
    request(lua, 1)
    return render(lua)["visual"]["capture_id"]


@pytest.mark.parametrize("field,value", [("visual_clock_version", "1"), ("fixed_step_numerator", "nil"),
    ("fixed_step_numerator", "2"), ("fixed_step_denominator", "30"),
    ("simulated_updates", "'999'"), ("simulated_updates", "nil")])
def test_bridge_refuses_non_fixed_step_runtime_before_native_input(field, value):
    lua = visual_bridge()
    prior = capture(lua)
    lua.execute(f"""
      local original=Hyperspace.benchmark_visual_capabilities
      Hyperspace.benchmark_visual_capabilities=function()
        local caps=json.decode(original()); caps.{field}={value}; return json.encode(caps)
      end
    """)
    request(lua, 2, [{"type": "move", "x": 10, "y": 10}], frames=60, expected=prior)
    assert len(lua.globals().input_calls) == 0
    assert lua.globals().world_updates == 0
    assert lua.globals().ftl_bench_state.visual_request_error == "visual_clock_unavailable"
    assert lua.globals().ftl_bench_state.frame_budget == 0


def test_bridge_propagates_native_fixed_time_without_inventing_duration():
    lua = visual_bridge()
    prior = capture(lua)
    request(lua, 2, frames=3, expected=prior)
    for _ in range(3):
        lua.globals().engine_tick()
    obs = render(lua)
    for field in ("capabilities", "visual"):
        assert obs[field]["visual_clock_version"] == 2
        assert obs[field]["fixed_step_numerator"] == 1
        assert obs[field]["fixed_step_denominator"] == 60
        assert obs[field]["simulated_updates"] == obs[field]["world_updates"] == "3"


@pytest.mark.parametrize("game_started", [False, True])
@pytest.mark.parametrize("unanchored_input", [False, True])
def test_first_visual_packet_published_between_reads_cannot_be_acked_as_structured(game_started, unanchored_input):
    lua = visual_bridge()
    lua.globals().world.bStartedGame = game_started
    lua.globals().unanchored_input = unanchored_input
    lua.execute("""
      ftl_bench_state.last_applied_seq=1
      ftl_bench_state.starting_new=true
      gui.choiceBoxOpen=world.bStartedGame
      gui.choiceBox={selectedChoice=-1,mainText='Fresh opening event'}
      local build=_G.ftl_bench.build_observation
      _G.ftl_bench.build_observation=function(tick)
        local obs=build(tick); obs.game_started=world.bStartedGame; return obs
      end
      reads=0
      local old=json.encode({seq=1,advance_frames=0,
        actions={{type='start_game',mode='new',seed=1}}})
      local visual=json.encode({seq=2,advance_frames=unanchored_input and 60 or 0,
        observation_mode='visual-v1',actions=unanchored_input and {{type='key',key='f'}} or {}})
      Hyperspace.read_json_action=function()
        reads=reads+1
        return reads == 1 and old or visual
      end
    """)

    # Atomic publication may occur after the first file read in this native tick.
    # That tick must use its old packet throughout, never acknowledge the new
    # visual packet through the historical menu or structured-game handler.
    lua.globals().engine_tick()
    first = json.loads(lua.globals().last_obs)
    assert first["last_action_seq"] == 1
    assert first["observation_mode"] == "structured-v7"
    assert lua.globals().reads == 1

    lua.globals().engine_tick()
    assert json.loads(lua.globals().last_obs)["last_action_seq"] == 1
    captured = render(lua)
    assert captured["last_action_seq"] == captured["visual"]["action_seq"] == 2
    assert captured["observation_mode"] == "visual-v1"
    assert captured["visual"]["actual_frames"] == 0
    assert captured["visual"]["world_updates"] == "0"
    assert captured.get("visual_request_error") == ("capture_required" if unanchored_input else None)
    assert captured["game_started"] is game_started
    assert lua.globals().gui.choiceBoxOpen is game_started
    assert lua.globals().gui.choiceBox.selectedChoice == -1
    assert len(lua.globals().input_calls) == 0
    assert lua.globals().clock_owned is True
    assert lua.globals().clock_advancing is False


def test_fresh_seeded_game_initial_capture_preserves_unselected_opening_event():
    lua = visual_bridge()
    lua.execute("""
      world.bStartedGame=false
      gui.choiceBoxOpen=false
      gui.choiceBox={selectedChoice=-1,mainText='Fresh opening event'}
      native_menu_clicks=0; native_event_choices=0
      Hyperspace.benchmark_set_difficulty=function(difficulty) return difficulty == 0 end
      Hyperspace.benchmark_difficulty=function() return 0 end
      Hyperspace.benchmark_advance_menu=function()
        native_menu_clicks=native_menu_clicks+1
        world.bStartedGame=true; gui.choiceBoxOpen=true
      end
      Hyperspace.benchmark_choose_event=function() native_event_choices=native_event_choices+1 end
      local build=_G.ftl_bench.build_observation
      _G.ftl_bench.build_observation=function(tick)
        local obs=build(tick); obs.game_started=world.bStartedGame; return obs
      end
    """)
    request(lua, 1, [{"type": "start_game", "mode": "new", "seed": 1}], mode="structured-v7")
    for _ in range(24):
        lua.globals().engine_tick()
    started = json.loads(lua.globals().last_obs)
    assert started["game_started"] is True
    assert lua.globals().ftl_bench_state.starting_new is True
    assert lua.globals().native_menu_clicks == 1

    request(lua, 2)
    assert json.loads(lua.globals().last_obs)["last_action_seq"] == 1
    first = render(lua)
    for _ in range(10):
        lua.globals().engine_tick()
    assert first["observation_mode"] == "visual-v1"
    assert first["visual"]["action_seq"] == 2
    assert first["visual"]["requested_frames"] == first["visual"]["actual_frames"] == 0
    assert first["visual"]["world_updates"] == "0"
    assert first["paused"] is True
    assert lua.globals().gui.choiceBoxOpen is True
    assert lua.globals().gui.choiceBox.selectedChoice == -1
    assert lua.globals().native_event_choices == 0
    assert lua.globals().native_menu_clicks == 1
    assert len(lua.globals().input_calls) == 0
    assert lua.globals().world_updates == 0


def test_ack_is_published_only_at_a_paused_completed_render_and_captures_are_unique():
    lua = visual_bridge()
    request(lua, 1)
    assert lua.globals().last_obs is None
    first = render(lua)
    assert first["last_action_seq"] == 1
    assert first["visual"]["action_seq"] == 1
    assert first["visual"]["actual_frames"] == 0
    assert first["capabilities"]["visual_io"] is True
    assert first["capabilities"]["visual_clock_version"] == 2
    assert first["capabilities"]["world_updates"] == "0"
    assert first["capabilities"]["world_updates"] == first["visual"]["world_updates"]
    request(lua, 2, expected=first["visual"]["capture_id"])
    assert json.loads(lua.globals().last_obs)["last_action_seq"] == 1
    second = render(lua)
    assert second["visual"]["capture_id"] != first["visual"]["capture_id"]
    assert second["visual"]["frame_id"] != first["visual"]["frame_id"]
    assert second["paused"] is True


@pytest.mark.parametrize("expected,reason", [("older-capture", "stale_capture"), (None, "capture_required")])
def test_stale_or_unanchored_input_never_invokes_handler_or_advances(expected, reason):
    lua = visual_bridge()
    capture(lua)
    request(lua, 2, [{"type": "click", "x": 4, "y": 8}], 600, expected)
    for _ in range(10):
        lua.globals().engine_tick()
    obs = render(lua)
    assert len(lua.globals().input_calls) == 0
    assert lua.globals().gui.bPaused is True
    assert obs["visual"]["requested_frames"] == 600
    assert obs["visual"]["actual_frames"] == 0
    assert obs["visual_request_error"] == reason
    assert obs["visual"]["input_feedback"] == [{"index": 0, "type": "click", "status": "rejected", "reason": reason}]


def test_actual_native_input_types_coordinates_and_modifiers_are_delivered_in_order():
    lua = visual_bridge()
    before = capture(lua)
    actions = [{"type": "move", "x": 1279, "y": 719},
               {"type": "click", "x": 100, "y": 50, "button": "right", "modifiers": ["shift", "ctrl"]},
               {"type": "drag", "x": 10, "y": 20, "to_x": 200, "to_y": 300},
               {"type": "key", "key": "space"}]
    request(lua, 2, actions, 0, before)
    assert lua.globals().gui.bPaused is True  # Space cannot escape model-latency pause
    obs = render(lua)
    calls = lua.globals().input_calls
    assert [calls[i].name for i in range(1, 5)] == ["mouse_move", "mouse_click", "mouse_drag", "key_press"]
    assert [calls[2].args[i] for i in range(1, 5)] == [100, 50, 1, 3]
    assert [calls[3].args[i] for i in range(1, 7)] == [10, 20, 200, 300, 0, 0]
    assert obs["visual"]["input_feedback"] == [{"index": i, "type": a["type"], "status": "delivered"} for i, a in enumerate(actions)]


@pytest.mark.parametrize("action,reason", [
    ({"type": "click", "x": 1280, "y": 0}, "invalid_coordinates"),
    ({"type": "click", "x": 0, "y": 0, "modifiers": ["alt"]}, "unsupported_modifier"),
    ({"type": "drag", "x": 0, "y": 0, "to_x": -1, "to_y": 0}, "invalid_coordinates"),
    ({"type": "click", "x": 0, "y": 0, "button": "middle"}, "unsupported_button"),
    ({"type": "jump", "target": 1}, "unsupported_input"),
])
def test_invalid_or_semantic_input_is_refused_without_native_delivery(action, reason):
    lua = visual_bridge()
    request(lua, 2, [action], 0, capture(lua))
    obs = render(lua)
    assert len(lua.globals().input_calls) == 0
    assert obs["visual"]["input_feedback"][0]["reason"] == reason


def test_frame_budget_counts_simulated_ticks_and_has_no_hidden_damage_interrupt():
    lua = visual_bridge()
    request(lua, 2, [], 200, capture(lua))
    assert lua.globals().gui.bPaused is False
    lua.globals().pl.ship.hullIntegrity.first = 1
    for _ in range(199):
        lua.globals().engine_tick()
    assert lua.globals().gui.bPaused is False
    assert lua.globals().captures == 1
    lua.globals().engine_tick()
    assert lua.globals().gui.bPaused is True
    obs = render(lua)
    assert obs["visual"]["actual_frames"] == 200
    assert obs["visual"]["requested_frames"] == 200


def test_visible_event_stops_advance_on_first_observed_frame():
    lua = visual_bridge()
    request(lua, 2, [], 600, capture(lua))
    for _ in range(7):
        lua.globals().engine_tick()
    lua.globals().gui.choiceBoxOpen = True
    lua.globals().engine_tick()
    assert lua.globals().gui.bPaused is True
    obs = render(lua)
    assert obs["visual"]["actual_frames"] == 8
    assert obs["visual"]["requested_frames"] == 600


def test_existing_blocking_modal_advances_zero_and_normal_weapon_queue_is_untouched():
    lua = visual_bridge()
    before = capture(lua)
    lua.globals().blocked = True
    lua.globals().pf.fireWhenReady = True
    lua.globals().pf.autoFiring = True
    lua.globals().global_autofire = True
    request(lua, 2, [], 600, before)
    obs = render(lua)
    assert obs["visual"]["actual_frames"] == 0
    assert lua.globals().pf.fireWhenReady is True
    assert lua.globals().pf.autoFiring is True
    assert lua.globals().global_autofire is True


def test_capture_failure_does_not_ack_or_replace_last_capture_and_retries_at_render():
    lua = visual_bridge()
    before = capture(lua)
    lua.globals().capture_fails = True
    request(lua, 2, [], 0, before)
    render(lua)
    assert json.loads(lua.globals().last_obs)["last_action_seq"] == 1
    assert lua.globals().ftl_bench_state.visual_capture.capture_id == before
    lua.globals().capture_fails = False
    obs = render(lua)
    assert obs["last_action_seq"] == 2
    assert obs["visual"]["capture_id"] != before


@pytest.mark.parametrize("frames", [-1, 601, 1.5, "30"])
def test_invalid_budget_refuses_entire_packet_before_inputs(frames):
    lua = visual_bridge()
    request(lua, 2, [{"type": "key", "key": "1"}], frames, capture(lua))
    obs = render(lua)
    assert len(lua.globals().input_calls) == 0
    assert obs["visual"]["actual_frames"] == 0
    assert obs["visual_request_error"] == "invalid_frame_budget"


def test_native_resize_invalidates_before_capture_input_coordinates():
    lua = visual_bridge()
    before = capture(lua)
    lua.execute("Hyperspace.benchmark_visual_capabilities=function() return json.encode({visual_io_version=1,capture=true,input=true,width=1920,height=1080,external_input_guard=true,external_input_generation='0',external_input_detected=false,visual_clock_version=2,fixed_step_numerator=1,fixed_step_denominator=60,simulated_updates=tostring(world_updates),world_updates=tostring(world_updates)}) end")
    request(lua, 2, [{"type": "click", "x": 100, "y": 50}], 30, before)
    obs = render(lua)
    assert len(lua.globals().input_calls) == 0
    assert obs["visual_request_error"] == "capture_dimensions_changed"


def test_external_input_after_capture_refuses_all_inputs_and_time_before_dispatch():
    lua = visual_bridge()
    before = capture(lua)
    lua.globals().external_generation = "1"
    lua.globals().external_detected = True
    request(lua, 2, [{"type": "key", "key": "space"}], 600, before)
    obs = render(lua)
    assert len(lua.globals().input_calls) == 0
    assert obs["visual_request_error"] == "external_input_since_capture"
    assert obs["visual"]["actual_frames"] == 0
    assert obs["visual"]["external_input_generation"] == "1"
    assert obs["visual"]["external_input_detected"] is True
    assert obs["visual"]["input_feedback"][0]["status"] == "rejected"
    assert lua.globals().gui.bPaused is True
    # A fresh screenshot is still contaminated; it cannot make the run eligible.
    request(lua, 3, [], 0, obs["visual"]["capture_id"], expected_generation="1")
    again = render(lua)
    assert again["visual"]["capture_id"] != obs["visual"]["capture_id"]
    assert again["visual"]["external_input_detected"] is True
    assert again["visual_request_error"] == "external_input_since_capture"


def test_physical_input_during_advance_stops_at_next_tick_with_truthful_frame_count():
    lua = visual_bridge()
    request(lua, 2, [], 600, capture(lua))
    for _ in range(7):
        lua.globals().engine_tick()
    lua.globals().external_generation = "2"
    lua.globals().external_detected = True
    lua.globals().engine_tick()
    obs = render(lua)
    assert obs["visual"]["actual_frames"] == 8
    assert obs["visual"]["requested_frames"] == 600
    assert obs["visual_request_error"] == "external_input_since_capture"
    assert lua.globals().gui.bPaused is True


def test_idle_external_input_publishes_contamination_without_a_new_action_packet():
    lua = visual_bridge()
    before = capture(lua)
    lua.globals().external_generation = "1"
    lua.globals().external_detected = True
    lua.globals().engine_tick()
    obs = render(lua)
    assert obs["visual"]["capture_id"] != before
    assert obs["visual"]["action_seq"] == 1
    assert obs["visual"]["external_input_detected"] is True
    assert obs["visual"]["actual_frames"] == 0


@pytest.mark.parametrize("generation,reason", [(None, "external_input_generation_required"),
                                              ("wrong", "external_input_generation_mismatch"),
                                              (0, "external_input_generation_mismatch")])
def test_action_generation_must_match_exact_captured_string(generation, reason):
    lua = visual_bridge()
    request(lua, 2, [{"type": "click", "x": 100, "y": 50}], 60, capture(lua), expected_generation=generation)
    obs = render(lua)
    assert obs["visual_request_error"] == reason
    assert obs["visual"]["actual_frames"] == 0
    assert len(lua.globals().input_calls) == 0


def test_old_native_visual_interface_cannot_deliver_without_interference_guard():
    lua = visual_bridge()
    before = capture(lua)
    lua.execute("Hyperspace.benchmark_visual_capabilities=function() return json.encode({visual_io_version=1,capture=true,input=true,width=1280,height=720,visual_clock_version=2,fixed_step_numerator=1,fixed_step_denominator=60,simulated_updates=tostring(world_updates),world_updates=tostring(world_updates)}) end")
    request(lua, 2, [{"type": "key", "key": "space"}], 60, before)
    obs = render(lua)
    assert obs["capabilities"]["external_input_guard"] is False
    assert obs["visual_request_error"] == "external_input_guard_unavailable"
    assert len(lua.globals().input_calls) == 0


def test_visual_clock_counts_native_world_updates_and_idle_renders_cannot_progress_pending_travel():
    lua = visual_bridge()
    lua.execute("pending_travel=false; travel_progress=0; on_world_update=function() if pending_travel then travel_progress=travel_progress+1 end end")
    before = capture(lua)
    lua.globals().pending_travel = True
    for _ in range(200):
        lua.globals().engine_tick()
        render(lua)
    assert lua.globals().travel_progress == 0
    assert lua.globals().world_updates == 0
    request(lua, 2, [], 1, before)
    lua.globals().engine_tick()
    mid = render(lua)
    assert mid["visual"]["actual_frames"] == 1
    assert mid["visual"]["world_updates"] == "1"
    assert mid["capabilities"]["world_updates"] == "1"
    assert mid["capabilities"]["world_updates"] == mid["visual"]["world_updates"]
    assert lua.globals().travel_progress == 1
    for _ in range(200):
        lua.globals().engine_tick()
        render(lua)
    assert lua.globals().travel_progress == 1
    request(lua, 3, [], 0, mid["visual"]["capture_id"])
    after = render(lua)
    assert after["visual"]["world_updates"] == "1" and after["visual"]["actual_frames"] == 0
    assert lua.globals().travel_progress == 1


def test_native_queued_choice_commits_only_on_an_explicit_budget_and_stops_at_next_dialog():
    lua = visual_bridge()
    lua.execute("gui.choiceBoxOpen=true; gui.choiceBox={selectedChoice=-1}; committed_choices=0")
    before = capture(lua)
    lua.execute("on_input=function() gui.choiceBox.selectedChoice=0 end; on_world_update=function() if gui.choiceBox.selectedChoice>=0 then committed_choices=committed_choices+1; gui.choiceBox.selectedChoice=-1 end end")
    request(lua, 2, [{"type": "key", "key": "1"}], 0, before)
    selected = render(lua)
    assert lua.globals().committed_choices == 0
    assert selected["visual"]["actual_frames"] == 0
    for _ in range(10):
        lua.globals().engine_tick()
    assert lua.globals().committed_choices == 0
    request(lua, 3, [], 180, selected["visual"]["capture_id"])
    lua.globals().engine_tick()
    after = render(lua)
    assert lua.globals().committed_choices == 1
    assert after["visual"]["world_updates"] == "1"
    assert after["visual"]["actual_frames"] == 1
    assert lua.globals().gui.choiceBoxOpen is True  # the next unselected dialog stops the budget
    assert lua.globals().clock_advancing is False


def test_backstage_structured_reset_releases_native_visual_clock_ownership():
    lua = visual_bridge()
    capture(lua)
    assert lua.globals().clock_owned is True
    request(lua, 2, [], 0, mode="structured-v7")
    assert lua.globals().clock_owned is False


def test_old_pause_only_dll_is_refused_before_input_or_advance():
    lua = visual_bridge()
    before = capture(lua)
    lua.execute("Hyperspace.benchmark_visual_capabilities=function() return json.encode({visual_io_version=1,capture=true,input=true,width=1280,height=720,external_input_guard=true,external_input_generation='0',external_input_detected=false}) end")
    request(lua, 2, [{"type": "key", "key": "space"}], 60, before)
    obs = render(lua)
    assert obs["visual_request_error"] == "visual_clock_unavailable"
    assert obs["visual"]["actual_frames"] == 0
    assert len(lua.globals().input_calls) == 0
