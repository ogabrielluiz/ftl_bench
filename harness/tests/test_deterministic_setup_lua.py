"""Execute shipped deterministic setup Lua against native doubles; no game calls."""
import pytest
from lupa.lua53 import LuaRuntime
from ftl_bench.cli import _bench_root


def bridge_source():
    return (_bench_root() / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua").read_text(encoding="utf-8")


def inline_helper(source):
    start = "local function NewDeterministicSetup("
    finish = "\nDeterministicSetup=NewDeterministicSetup("
    if source.count(start) != 1 or source.count(finish) != 1:
        raise ValueError("Missing or ambiguous shipped deterministic setup seams")
    left, right = source.index(start), source.index(finish)
    if right <= left:
        raise ValueError("Shipped deterministic setup seams are out of order")
    return source[left:right]


def test_shipped_test_engine_is_lua53():
    assert LuaRuntime().eval("_VERSION") == "Lua 5.3"


@pytest.mark.parametrize("source", [
    "", "local function NewDeterministicSetup( local function NewDeterministicSetup(\nDeterministicSetup=NewDeterministicSetup(",
    "local function NewDeterministicSetup(\nDeterministicSetup=NewDeterministicSetup(\nDeterministicSetup=NewDeterministicSetup(",
    "\nDeterministicSetup=NewDeterministicSetup( local function NewDeterministicSetup(",
])
def test_missing_or_ambiguous_inline_helper_is_rejected(source):
    with pytest.raises(ValueError):
        inline_helper(source)


def runtime(overwrite=False, running=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      S={frame_budget=0,observation_mode="structured-v7"}
      world_updates=0; owned=false; advancing=false; seed_calls=0; crt_calls=0
      clock_events={};forward_events={};native={}
      stage="main_menu";overwrite=false;construction_uncontrolled=false
      H={App={world={bStartedGame=false},gui={bPaused=false,choiceBoxOpen=false}}}
      json={decode=function(value)
        if value=="native" then return native end
        error("invalid JSON token")
      end}
      capabilities=function() return {visual_clock_version=2,world_updates=tostring(world_updates),
       simulated_updates=tostring(world_updates),fixed_step_numerator=1,fixed_step_denominator=60} end
      counter=function(caps)
        if not caps or caps.visual_clock_version~=2 or caps.fixed_step_numerator~=1
         or caps.fixed_step_denominator~=60 or caps.simulated_updates~=caps.world_updates then return nil end
        return tonumber(caps.world_updates)
      end
      H.benchmark_visual_set_clock=function(enable,advance)
        owned=enable;advancing=advance
        clock_events[#clock_events+1]={owned=owned,advancing=advancing,stage=stage}
        return true
      end
      freeze=function(value) H.App.gui.bPaused=value end
      H.benchmark_fresh_seed_contract_version=function() return 3 end
      H.benchmark_fresh_menu_stage=function() return stage end
      H.benchmark_arm_fresh_seed=function(seed)
        assert(owned and not advancing,"clock must own construction before arm")
        native={contract="fresh-start-seed-v3",contract_version=3,epoch=1,seed=seed,
         pending=true,applied=false,failed=false,names_before_seed=0,names_during_open=0,
         native_seed_applications=0,c_runtime_seed_applications=0,
         utility_name_calls=1,utility_lookup_calls=1,utility_lookup_completed=1,utility_lookup_valid=true,
         utility_name_provenance="StatBoostManager::CreateDummyCrew.GetCrewBlueprint(human)",
         utility_name="Dummy",utility_thread_id=7,names_before_arm=1,unclassified_names_before_arm=0,
         unclassified_names_before_seed=0,intervening_names_after_arm=0,ship_inits_before_arm=0,
         ship_inits_before_seed=0,reservations_before_arm=1,
         reservation_reset_applications=0,reservation_reset_verified=false}
        for _,kind in ipairs({"crew","lost","player","enemy","clone"}) do
          native["factory_"..kind.."_before_arm"]=0;native["factory_"..kind.."_before_reset"]=0
        end
        return true
      end
      H.benchmark_fresh_seed_receipt=function() return "native" end
      H.benchmark_advance_fresh_menu=function()
        forward_events[#forward_events+1]=stage
        assert(owned and not advancing,"construction must not gain ambient world permit")
        if stage=="main_menu" and overwrite then stage="overwrite_confirmation"
        elseif stage=="main_menu" or stage=="overwrite_confirmation" then
          native.pending=false;native.applied=true;native.native_seed_applications=1
          native.c_runtime_seed_applications=1;native.names_during_open=3
          native.boundary="ShipBuilder::Open.before_super"
          native.constructor_timing_controlled=not construction_uncontrolled
          native.fixed_creation_timing=not construction_uncontrolled
          native.construction_clock_owned=owned
          native.construction_fixed_step_numerator=1;native.construction_fixed_step_denominator=60
          native.construction_speed_factor_bits=1049135241;native.construction_scope_active=false
          native.clock_owned_at_boundary=owned
          native.seed_thread_id=7
          native.names_before_seed=1
          native.reservations_before_reset=1;native.reservations_after_reset=0
          native.reservation_names_before_reset={"Dummy"};native.reservation_reset_applications=1
          native.reservation_reset_verified=true;native.reservation_reset_thread_id=7
          seed_calls=seed_calls+1;crt_calls=crt_calls+1;stage="hangar"
        elseif stage=="hangar" then
          stage="start_pending";native.start_pending=true;native.start_completed=false
        end
        native.construction_clicks=#forward_events;native.completed_construction_clicks=#forward_events
        return true
      end
      complete_start_native=function()
        assert(stage=="start_pending" and owned and not advancing)
        stage="in_game";H.App.world.bStartedGame=true
        native.start_pending=false;native.start_completed=true
        native.start_completion_callbacks=1;native.start_extra_hangar_dwell=0
        native.start_world_updates_before=tostring(world_updates)
        native.start_world_updates_after=tostring(world_updates)
        native.start_timing_controlled=true;native.start_world_frozen=true
        native.start_hangar_onloop_requests=1;native.start_hangar_onloop_executed=0
        native.start_game_calls=1;native.start_game_returns=1
        native.start_cfps_fixed_applications=1;native.start_speed_factor_bits=1049135241
        native.start_thread_id=7;native.start_completion_scope_active=false
      end
      H.benchmark_return_to_menu=function() return true end
      H.benchmark_confirm_menu=function() return true end
      request=function(kind)
        return {seq=1,advance_frames=0,benchmark_setup={version=1,fresh=true,seed=1},
         actions={{type=kind or "start_game",mode="new",seed=1}}}
      end
    ''')
    lua.globals().overwrite = overwrite
    if running:
        lua.execute('stage="in_game";H.App.world.bStartedGame=true')
    lua.execute(inline_helper(bridge_source()) +
                "\nD=NewDeterministicSetup(S,H,json,freeze,capabilities,counter)")
    return lua


@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize("kind", ["start_game", "reset_episode"])
def test_fresh_menu_chain_owns_clock_seeds_once_and_freezes_before_return(overwrite, kind):
    lua = runtime(overwrite=overwrite)
    assert lua.globals().D.admit(lua.globals().request(kind))
    assert lua.globals().D.menu()
    assert lua.globals().D.start_pending()
    lua.globals().complete_start_native()
    assert lua.globals().D.complete_start()
    lua.execute('''
      assert(stage=="in_game" and owned and not advancing and H.App.gui.bPaused)
      assert(seed_calls==1 and crt_calls==1 and world_updates==0)
      assert(S.benchmark_setup.phase=="ready")
      assert(S.benchmark_setup.creation.frozen_immediately)
      assert(S.benchmark_setup.creation.zero_unbudgeted_world_updates)
      assert(S.observation_mode=="structured-v7")
    ''')
    assert len(lua.globals().forward_events) == (3 if overwrite else 2)


def test_reset_old_world_permits_measured_steps_then_arms_fresh_seed_at_menu():
    lua = runtime(running=True)
    assert lua.globals().D.admit(lua.globals().request("reset_episode"))
    assert lua.globals().D.reset_tick()
    lua.execute('world_updates=world_updates+1')
    assert lua.globals().D.reset_tick()
    lua.execute('stage="main_menu";H.App.world.bStartedGame=false')
    assert lua.globals().D.menu()
    lua.globals().complete_start_native()
    assert lua.globals().D.complete_start()
    lua.execute('''
      assert(seed_calls==1 and S.benchmark_setup.phase=="ready")
      assert(S.benchmark_setup.intervals[1].status=="complete")
      assert(S.benchmark_setup.intervals[1].actual_updates==1)
      assert(S.benchmark_setup.intervals[2].status=="menu_boundary")
      assert(S.benchmark_setup.intervals[2].actual_updates==0)
      assert(owned and not advancing and H.App.gui.bPaused)
    ''')


def ready():
    lua = runtime()
    assert lua.globals().D.admit(lua.globals().request()) and lua.globals().D.menu()
    lua.globals().complete_start_native()
    assert lua.globals().D.complete_start()
    return lua


def test_exact_budget_counts_world_updates_not_callbacks_and_disables_unbudgeted_dispatch():
    lua = ready()
    assert lua.globals().D.begin_interval(2, 3, "structured", True)
    assert not lua.globals().advancing
    assert lua.globals().D.dispatch_complete()
    for _ in range(6):
        assert lua.globals().D.advance_interval()
    assert lua.globals().S.frame_budget == 3
    for remaining in (2, 1, 0):
        lua.execute("world_updates=world_updates+1")
        assert lua.globals().D.advance_interval()
        assert lua.globals().S.frame_budget == remaining
    lua.execute('''assert(not advancing and owned and H.App.gui.bPaused)
      assert(S.benchmark_setup.intervals[1].actual_updates==3)
      assert(S.benchmark_setup.intervals[1].status=="complete")''')


@pytest.mark.parametrize("counter_value", [-1, 4])
def test_counter_regression_and_overrun_fail_closed(counter_value):
    lua = ready()
    assert lua.globals().D.begin_interval(2, 3, "structured")
    lua.globals().world_updates = counter_value
    assert not lua.globals().D.advance_interval()
    assert lua.globals().D.failed()
    assert lua.globals().owned and not lua.globals().advancing


def test_semantic_dispatch_cannot_hide_a_synchronous_world_update():
    lua = ready()
    assert lua.globals().D.begin_interval(2, 0, "structured", True)
    lua.execute("world_updates=world_updates+1")
    assert not lua.globals().D.dispatch_complete()
    assert lua.globals().D.failed()


def test_visual_handoff_preserves_ownership_counter_and_records_receipt():
    lua = ready()
    assert lua.globals().D.begin_interval(2, 2, "structured")
    lua.execute("world_updates=world_updates+2")
    assert lua.globals().D.advance_interval()
    lua.execute('S.observation_mode="visual-v1"')
    assert lua.globals().D.handoff(3)
    lua.execute('''assert(owned and not advancing and world_updates==2)
      assert(S.benchmark_setup.phase=="visual" and not S.benchmark_setup.active)
      assert(S.benchmark_setup.handoff.world_updates=="2")
      assert(seed_calls==1 and crt_calls==1)''')


def test_handoff_before_budget_completion_is_refused():
    lua = ready()
    assert lua.globals().D.begin_interval(2, 3, "structured")
    assert not lua.globals().D.handoff(3)
    assert lua.globals().D.failed() and lua.globals().owned


@pytest.mark.parametrize("stage", ["hangar", "unsupported_modal", "unavailable"])
def test_preexisting_or_unknown_construction_stage_refuses_seed(stage):
    lua = runtime()
    lua.globals().stage = stage
    assert not lua.globals().D.admit(lua.globals().request())
    assert lua.globals().seed_calls == 0


def test_constructor_timing_missing_or_false_refuses_start():
    lua = runtime()
    lua.globals().construction_uncontrolled = True
    assert lua.globals().D.admit(lua.globals().request())
    assert not lua.globals().D.menu()
    assert lua.globals().stage == "hangar"
    assert lua.globals().H.App.gui.bPaused


def test_native_arm_refusal_preserves_causal_receipt_before_failure():
    lua = runtime()
    lua.execute('''H.benchmark_arm_fresh_seed=function(seed)
      native={failed=true,error="preexisting_ship_construction",ship_inits_before_arm=1,
       names_before_arm=3,seed=seed};return false
    end''')
    assert not lua.globals().D.admit(lua.globals().request())
    receipt = lua.globals().S.benchmark_setup
    assert receipt.native_seed.error == "preexisting_ship_construction"
    assert receipt.native_seed.ship_inits_before_arm == 1
    assert receipt.native_seed.names_before_arm == 3
    assert receipt.native_seed_receipt.raw_response == "native"
    assert receipt.native_seed_receipt.parse_succeeded
    assert receipt.arm_call.succeeded and not receipt.arm_call.accepted
    assert receipt.admission_stage == "main_menu"
    assert receipt.error == "fresh native seed arm refused"
    assert lua.globals().owned and not lua.globals().advancing


@pytest.mark.parametrize("receipt_call", [
    'function() return "{broken-native-json" end',
    'function() error("native receipt exception") end',
])
def test_native_arm_refusal_preserves_raw_receipt_when_decode_fails(receipt_call):
    lua = runtime()
    lua.execute('H.benchmark_arm_fresh_seed=function() return false end;'
                'H.benchmark_fresh_seed_receipt=' + receipt_call)
    assert not lua.globals().D.admit(lua.globals().request())
    receipt = lua.globals().S.benchmark_setup
    assert not receipt.native_seed_receipt.parse_succeeded
    assert receipt.native_seed_receipt.raw_response
    assert receipt.native_seed_receipt.parse_error
    assert receipt.error == "fresh native seed arm refused"


def test_native_arm_exception_preserves_call_error_and_receipt():
    lua = runtime()
    lua.execute('''H.benchmark_arm_fresh_seed=function()
      native={failed=true,error="construction_exception"};error("native arm exception")
    end''')
    assert not lua.globals().D.admit(lua.globals().request())
    receipt = lua.globals().S.benchmark_setup
    assert not receipt.arm_call.succeeded
    assert "native arm exception" in receipt.arm_call.response
    assert receipt.native_seed.error == "construction_exception"


@pytest.mark.parametrize("field,value", [
    ("contract_version", 2), ("utility_name_calls", 2), ("utility_lookup_calls", 0),
    ("utility_lookup_completed", 0), ("utility_lookup_valid", False),
    ("utility_name_provenance", "unclassified lookup"), ("utility_name", ""),
    ("utility_thread_id", 0), ("names_before_arm", 0), ("unclassified_names_before_arm", 1),
    ("ship_inits_before_arm", 1), ("intervening_names_after_arm", 1),
    ("reservations_before_arm", 2), ("reservation_reset_applications", 1),
    ("reservation_reset_verified", True),
    ("names_before_seed", 1), ("unclassified_names_before_seed", 1), ("ship_inits_before_seed", 1),
] + [(f"factory_{kind}_before_arm", 1) for kind in ("crew", "lost", "player", "enemy", "clone")])
def test_v3_pending_receipt_rejects_unclassified_or_preexisting_state(field, value):
    lua = runtime()
    lua.globals().bad_field, lua.globals().bad_value = field, value
    lua.execute('''local original=H.benchmark_arm_fresh_seed
      H.benchmark_arm_fresh_seed=function(seed)
        local accepted=original(seed);native[bad_field]=bad_value;return accepted
      end''')
    assert not lua.globals().D.admit(lua.globals().request())
    assert lua.globals().D.failed() and lua.globals().seed_calls == 0
    assert lua.globals().owned and not lua.globals().advancing


@pytest.mark.parametrize("field,value", [
    ("names_before_seed", 0), ("unclassified_names_before_seed", 1),
    ("ship_inits_before_seed", 1), ("utility_thread_id", 8), ("reservation_reset_thread_id", 8),
    ("reservations_before_reset", 2), ("reservations_after_reset", 1),
    ("reservation_reset_applications", 0), ("reservation_reset_applications", 2),
    ("reservation_reset_verified", False),
] + [(f"factory_{kind}_before_reset", 1) for kind in ("crew", "lost", "player", "enemy", "clone")])
def test_v3_applied_receipt_rejects_bad_orphan_reset_evidence(field, value):
    lua = runtime()
    lua.globals().bad_field, lua.globals().bad_value = field, value
    lua.execute('''local original=H.benchmark_advance_fresh_menu
      H.benchmark_advance_fresh_menu=function()
        local accepted=original();if stage=="hangar" then native[bad_field]=bad_value end
        return accepted
      end''')
    assert lua.globals().D.admit(lua.globals().request())
    assert not lua.globals().D.menu()
    assert lua.globals().D.failed() and lua.globals().stage == "hangar"
    assert lua.globals().owned and not lua.globals().advancing


@pytest.mark.parametrize("names", ['{}', '{"Other"}', '{"Dummy","Other"}'])
def test_v3_reservation_snapshot_must_be_exact_classified_name(names):
    lua = runtime()
    lua.execute('''local original=H.benchmark_advance_fresh_menu
      H.benchmark_advance_fresh_menu=function()
        local accepted=original();if stage=="hangar" then native.reservation_names_before_reset=''' + names + ''' end
        return accepted
      end''')
    assert lua.globals().D.admit(lua.globals().request())
    assert not lua.globals().D.menu()


def test_v3_keeps_raw_classified_name_count_and_single_reservation_reset():
    lua = ready()
    lua.execute('''assert(S.benchmark_setup.native_seed.names_before_arm==1)
      assert(S.benchmark_setup.native_seed.names_before_seed==1)
      assert(S.benchmark_setup.native_seed.unclassified_names_before_arm==0)
      assert(S.benchmark_setup.native_seed.unclassified_names_before_seed==0)
      assert(S.benchmark_setup.native_seed.reservation_reset_applications==1)
      assert(S.benchmark_setup.native_seed.reservation_names_before_reset[1]=="Dummy")
      assert(seed_calls==1 and crt_calls==1)''')


def test_stalled_asynchronous_menu_does_not_wait_with_unaccounted_hangar_clock():
    lua = runtime()
    lua.execute('H.benchmark_advance_fresh_menu=function() return true end')
    assert lua.globals().D.admit(lua.globals().request())
    assert not lua.globals().D.menu()
    assert lua.globals().D.failed() and not lua.globals().advancing


@pytest.mark.parametrize("field,value", [
    ("contract_version", 1), ("native_seed_applications", 2),
    ("c_runtime_seed_applications", 0), ("construction_scope_active", True),
    ("construction_speed_factor_bits", 0), ("completed_construction_clicks", 0),
    ("seed_thread_id", 0),
])
def test_native_seed_or_construction_receipt_mismatch_refuses_start(field, value):
    lua = runtime()
    lua.globals().bad_field, lua.globals().bad_value = field, value
    lua.execute('''local original=H.benchmark_advance_fresh_menu
      H.benchmark_advance_fresh_menu=function()
        local accepted=original()
        if stage=="hangar" then native[bad_field]=bad_value end
        return accepted
      end''')
    assert lua.globals().D.admit(lua.globals().request())
    assert not lua.globals().D.menu()
    assert lua.globals().stage == "hangar"
    assert lua.globals().D.failed()


def test_missing_next_loop_completion_fails_without_waiting_or_retry():
    lua = runtime()
    assert lua.globals().D.admit(lua.globals().request()) and lua.globals().D.menu()
    assert not lua.globals().D.complete_start()
    assert lua.globals().D.failed()
    assert len(lua.globals().forward_events) == 2
    assert not lua.globals().advancing


@pytest.mark.parametrize("field,value", [
    ("start_completion_callbacks", 2), ("start_extra_hangar_dwell", 1),
    ("start_world_updates_after", "1"), ("start_timing_controlled", False),
    ("start_world_frozen", False),
    ("start_hangar_onloop_requests", 2), ("start_hangar_onloop_executed", 1),
    ("start_game_calls", 2), ("start_game_returns", 0),
    ("start_cfps_fixed_applications", 0), ("start_speed_factor_bits", 0),
    ("start_thread_id", 8),
])
def test_deferred_start_completion_receipt_mismatch_fails_closed(field, value):
    lua = runtime()
    assert lua.globals().D.admit(lua.globals().request()) and lua.globals().D.menu()
    lua.globals().complete_start_native()
    lua.globals().native[field] = value
    assert not lua.globals().D.complete_start()
    assert lua.globals().D.failed() and lua.globals().owned and not lua.globals().advancing


def test_unbudgeted_idle_counter_change_cannot_be_hidden_by_next_interval():
    lua = ready()
    lua.execute("world_updates=1")
    assert not lua.globals().D.begin_interval(2, 3, "structured")
    assert lua.globals().D.failed()


def test_completion_scope_may_be_active_at_ready_but_must_close_before_handoff():
    lua = runtime()
    assert lua.globals().D.admit(lua.globals().request()) and lua.globals().D.menu()
    lua.globals().complete_start_native()
    lua.globals().native.start_completion_scope_active = True
    assert lua.globals().D.complete_start()
    assert not lua.globals().D.handoff(3)
    assert lua.globals().D.failed()


def test_completed_scope_can_close_on_next_callback_before_handoff():
    lua = runtime()
    assert lua.globals().D.admit(lua.globals().request()) and lua.globals().D.menu()
    lua.globals().complete_start_native()
    lua.globals().native.start_completion_scope_active = True
    assert lua.globals().D.complete_start()
    lua.execute('native.start_completion_scope_active=false;S.observation_mode="visual-v1"')
    assert lua.globals().D.handoff(3)


def test_decimal_counter_receipts_do_not_switch_to_scientific_notation():
    lua = runtime()
    lua.execute("world_updates=9007199254740990")
    assert lua.globals().D.admit(lua.globals().request())
    assert lua.globals().S.benchmark_setup.clock.initial_world_updates == "9007199254740990"


def test_default_no_optin_leaves_native_clock_untouched():
    lua = runtime()
    packet = lua.table_from({"seq": 1, "advance_frames": 30})
    assert lua.globals().D.admit(packet) and lua.globals().D.guard(packet)
    assert not lua.globals().D.owns()
    assert len(lua.globals().clock_events) == 0
    assert lua.globals().D.observe() is None


def test_shipped_bridge_compiles_and_keeps_default_critical_path():
    lua = LuaRuntime(unpack_returned_tuples=True)
    source = bridge_source()
    assert callable(lua.globals().load(source))
    assert "local r = check_critical(S.danger0, S.adv_elapsed)" in source
    assert "DeterministicSetup.advance_interval()" in source
    assert source.index("DeterministicSetup.advance_interval()") < source.index("local r = check_critical(S.danger0, S.adv_elapsed)")
    assert "local function NewDeterministicSetup(" in inline_helper(source)


def complete_bridge_runtime():
    lua = runtime()
    lua.execute('''
      _G.ftl_bench_state=S;Hyperspace=H;H.ships={};H.Settings={dialogKeys=0}
      script={on_internal_event=function() end,on_render_event=function() end}
      Defines={InternalEvents={},RenderEvents={}}
      _G.ftl_bench_seed_hook=true;_G.ftl_bench_shot_hooks=true;_G.ftl_bench_render_hook=true
      packet=nil;published=0;critical_calls=0
      H.read_json_action=function() return packet and "packet" or "" end
      H.benchmark_visual_capabilities=function() return "caps" end
      H.benchmark_set_difficulty=function(value) return value==0 end
      H.benchmark_difficulty=function() return 0 end
      local old_decode=json.decode
      json.decode=function(value)
        if value=="packet" then return packet end
        if value=="caps" then
          local caps=capabilities();caps.visual_io_version=1;caps.capture=true;caps.input=true
          return caps
        end
        return old_decode(value)
      end
      json.encode=function(value) return "encoded" end
    ''')
    lua.execute(bridge_source())
    lua.execute('''
      for i=1,100 do
        local name=debug.getupvalue(_G.ftl_bench_tick,i)
        if not name then break end
        if name=="write_observation" then
          debug.setupvalue(_G.ftl_bench_tick,i,function() published=published+1;return true end)
        elseif name=="danger_snapshot" then
          debug.setupvalue(_G.ftl_bench_tick,i,function() return {} end)
        elseif name=="check_critical" then
          debug.setupvalue(_G.ftl_bench_tick,i,function() critical_calls=critical_calls+1;return "forced-test-critical" end)
        end
      end
    ''')
    return lua


def test_complete_shipped_tick_uses_counter_budget_and_never_legacy_critical_stop():
    lua = complete_bridge_runtime()
    lua.execute('packet=request();_G.ftl_bench_tick()')
    lua.execute('assert(S.benchmark_setup.phase=="starting");complete_start_native();_G.ftl_bench_tick()')
    lua.execute('''assert(S.benchmark_setup.phase=="ready" and owned and not advancing)
      packet={seq=2,advance_frames=200,actions={},observation_mode="structured-v7"}
      _G.ftl_bench_tick()
      assert(owned and advancing and S.frame_budget==200)
      world_updates=150;_G.ftl_bench_tick()
      assert(S.frame_budget==50 and advancing and critical_calls==0)
      world_updates=200;_G.ftl_bench_tick()
      assert(S.frame_budget==0 and not advancing and critical_calls==0)
      assert(S.benchmark_setup.intervals[1].status=="complete")
      assert(S.benchmark_setup.intervals[1].actual_updates==200)
      assert(seed_calls==1 and crt_calls==1)
    ''')


def test_complete_default_tick_still_applies_legacy_critical_interrupt():
    lua = complete_bridge_runtime()
    lua.execute('''stage="in_game";H.App.world.bStartedGame=true
      S.frame_budget=200;S.adv_elapsed=149
      _G.ftl_bench_tick()
      assert(S.benchmark_setup==nil and critical_calls==1)
      assert(S.frame_budget==0 and S.interrupt_reason=="forced-test-critical")
      assert(not owned)
    ''')


@pytest.mark.parametrize("raises", [False, True])
def test_failed_forward_keeps_post_call_native_cause(raises):
    lua = runtime()
    assert lua.globals().D.admit(lua.globals().request())
    lua.globals().forward_raises = raises
    lua.execute('''H.benchmark_advance_fresh_menu=function()
      native.failed=true;native.error="construction_menu_no_progress";native.construction_clicks=1
      if forward_raises then error("native forward exception") end
      return false
    end''')
    assert not lua.globals().D.menu()
    lua.execute('''
      assert(S.benchmark_setup.phase=="failed" and owned and not advancing)
      assert(S.benchmark_setup.forward_call.stage=="main_menu")
      assert(S.benchmark_setup.forward_call.accepted==false)
      assert(S.benchmark_setup.forward_call.succeeded==not forward_raises)
      assert(S.benchmark_setup.native_seed.failed==true)
      assert(S.benchmark_setup.native_seed.error=="construction_menu_no_progress")
      assert(S.benchmark_setup.native_seed.construction_clicks==1)
      assert(S.benchmark_setup.native_seed_receipt.parse_succeeded==true)
    ''')


def add_menu_diagnostic_bindings(lua):
    lua.execute('''
      local start={bActive=true,bHover=false,hitbox={x=30,y=40,w=120,h=32},position={x=30,y=40}}
      local buttons={[0]=start,[1]={bActive=true},size=function() return 2 end}
      H.App.menu={startButton=start,buttons=buttons,bOpen=true,bScoreScreen=false,bCreditScreen=false,
        bSelectSave=false,finalChoice=-1,confirmNewGame={bOpen=false},shipBuilder={bOpen=false},
        optionScreen={bOpen=false},changelog={bOpen=false}}
      H.App.langChooser={bOpen=false}
      H.Global={GetInstance=function() return {GetCApp=function() return H.App end} end}
    ''')


def test_menu_diagnostics_capture_before_after_fields_and_vector_identity_without_clicks():
    lua=runtime()
    add_menu_diagnostic_bindings(lua)
    lua.execute('''
      local forward=H.benchmark_advance_fresh_menu
      H.benchmark_advance_fresh_menu=function()
        H.App.menu.startButton.bHover=true
        return forward()
      end
    ''')
    assert lua.globals().D.admit(lua.globals().request())
    assert lua.globals().D.menu()
    lua.execute('''
      local rows=S.benchmark_setup.menu_diagnostics
      assert(#rows==2 and #forward_events==2)
      local before=rows[1].before;local after=rows[1].after
      assert(before.start_button_bActive and not before.start_button_bHover)
      assert(after.start_button_bHover and before.start_button_hitbox_x==30)
      assert(before.start_button_hitbox_w==120 and before.start_button_position_y==40)
      assert(before.menu_buttons_count==2 and not before.menu_buttons_truncated)
      assert(before.menu_button_identities[1].is_start==true)
      assert(before.menu_button_identities[2].is_start==false)
      assert(before.menu_button_identities[1].identity==before.start_button_identity)
      assert(before.menu_finalChoice==-1 and before.menu_confirmNewGame_open==false)
      assert(before.menu_bNewGame==nil and #before.errors==1)
      assert(before.errors[1].field=="menu_bNewGame")
      assert(rows[1].forward_call_succeeded and rows[1].forward_call_accepted)
    ''')


@pytest.mark.parametrize("fault",[
    "H.Global=nil",
    "H.Global.GetInstance=function() error('snapshot binding failed') end",
    "H.App.menu=nil",
    "H.App.menu.startButton=setmetatable({}, {__index=function() error('button binding failed') end})",
    "H.App.menu.buttons.size=function() error('vector binding failed') end",
])
def test_menu_snapshot_read_failure_does_not_change_admission_or_number_of_clicks(fault):
    lua=runtime()
    add_menu_diagnostic_bindings(lua)
    lua.execute(fault)
    assert lua.globals().D.admit(lua.globals().request())
    assert lua.globals().D.menu()
    lua.execute('''
      assert(S.benchmark_setup.phase=="starting" and S.benchmark_setup.error==nil)
      assert(#forward_events==2 and seed_calls==1 and crt_calls==1)
      assert(#S.benchmark_setup.menu_diagnostics==2)
      assert(#S.benchmark_setup.menu_diagnostics[1].before.errors>0)
      assert(#S.benchmark_setup.menu_diagnostics[1].after.errors>0)
    ''')


@pytest.mark.parametrize("raises",[False,True])
def test_failed_snapshot_cannot_mask_failed_forward_native_receipt_or_add_click(raises):
    lua=runtime()
    lua.globals().forward_raises=raises
    assert lua.globals().D.admit(lua.globals().request())
    lua.execute('''
      H.Global={GetInstance=function() error("snapshot unavailable") end}
      forward_count=0
      H.benchmark_advance_fresh_menu=function()
        forward_count=forward_count+1
        native.failed=true;native.error="construction_menu_no_progress";native.construction_clicks=1
        if forward_raises then error("native failure") end
        return false
      end
    ''')
    assert not lua.globals().D.menu()
    lua.execute('''
      assert(forward_count==1 and seed_calls==0 and crt_calls==0)
      assert(S.benchmark_setup.native_seed.error=="construction_menu_no_progress")
      assert(S.benchmark_setup.native_seed.construction_clicks==1)
      assert(S.benchmark_setup.native_seed_receipt.parse_succeeded)
      local row=S.benchmark_setup.menu_diagnostics[1]
      assert(#row.before.errors>0 and #row.after.errors>0)
      assert(row.forward_call_succeeded==not forward_raises and not row.forward_call_accepted)
      assert(S.benchmark_setup.error=="native scoped forward click refused")
    ''')


def test_menu_diagnostic_vector_reads_are_bounded_and_readonly():
    lua=runtime()
    add_menu_diagnostic_bindings(lua)
    lua.execute('''
      vector_reads=0
      H.App.menu.buttons=setmetatable({size=function() return 1000000 end},{__index=function(_,index)
        vector_reads=vector_reads+1;return H.App.menu.startButton
      end})
    ''')
    assert lua.globals().D.admit(lua.globals().request()) and lua.globals().D.menu()
    lua.execute('''
      assert(#forward_events==2 and vector_reads==4*128)
      assert(S.benchmark_setup.menu_diagnostics[1].before.menu_buttons_count==1000000)
      assert(S.benchmark_setup.menu_diagnostics[1].before.menu_buttons_truncated)
      assert(#S.benchmark_setup.menu_diagnostics[1].before.menu_button_identities==128)
    ''')
