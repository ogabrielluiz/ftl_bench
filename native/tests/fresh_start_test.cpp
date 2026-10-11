// Executes the actual candidate include with narrow fake engine/hook boundaries.
#include <cassert>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
std::vector<std::string> order;
std::vector<unsigned> native_seeds, crt_seeds;
unsigned open_calls=0, init_calls=0, name_calls=0;std::function<void()> native_seed_body;
std::function<void()> open_body, constructor_body, advance_body, confirm_body, app_loop_body, start_game_body;
unsigned world_chain_calls=0, hangar_chain_calls=0, app_calls=0, fps_calls=0, thread_id=42;
void hs_benchmark_advance_menu() { if (advance_body) advance_body(); }
void srandom32(unsigned seed) { if(native_seed_body)native_seed_body();native_seeds.push_back(seed);order.push_back("native_seed"); }
namespace std {
void monitored_srand(unsigned seed) { crt_seeds.push_back(seed);order.push_back("crt_seed");std::srand(seed); }
}
namespace Globals { struct Rect { int x=0,y=0,w=20,h=20; }; }
struct Point { int x=0,y=0; };
struct Button { Globals::Rect hitbox;Point position;bool bActive=true,bHover=false; };
struct Window { bool bOpen=false;Button yesButton; };
struct ShipBlueprint {};
struct BlueprintManager {
    std::vector<std::string> currentNames;
    std::string super(bool*) { ++name_calls;order.push_back("crew_name");currentNames.push_back("test crew");return "test crew"; }
};
struct CrewMember {};
struct CrewMemberFactory { std::vector<CrewMember*> crewMembers,lostMembers;int playerCrew=0,enemyCrew=0,enemyCloneCount=0; };
struct ShipManager {
    int super(ShipBlueprint*,int) { ++init_calls;order.push_back("ship_init");return 7; }
};
struct ShipBuilder {
    bool bOpen=false,bDone=false;
    void super() { ++open_calls;order.push_back("open_super");if (open_body) open_body(); }
};
struct MainMenu {
    bool bOpen=true,bScoreScreen=false,bCreditScreen=false,bSelectSave=false;
    Window optionScreen,changelog,confirmNewGame;
    Button startButton;std::vector<Button*> buttons;int finalChoice=-1;
    ShipBuilder& shipBuilder;
    MainMenu(ShipBuilder& ship):shipBuilder(ship) {}
    void super() { if (constructor_body) constructor_body(); }
    void MouseMove(int,int) {}
    void MouseClick(int,int) { if (confirm_body) confirm_body(); }
};
struct WorldManager {
    bool bStartedGame=false;
    void super() { ++world_chain_calls; }
    void super(ShipManager*) { if (start_game_body) start_game_body();else bStartedGame=true; }
};
struct CFPS { float SpeedFactor=1.25f;void super() { ++fps_calls;SpeedFactor=7.75f; } };
struct CApp { WorldManager* world;MainMenu& menu;Window langChooser;
    CApp(WorldManager* w,MainMenu& m):world(w),menu(m) {}
    void super() { ++app_calls;if (app_loop_body) app_loop_body(); }
};
struct Global {
    CApp* app=nullptr;CFPS* fps=nullptr;BlueprintManager* blueprints=nullptr;CrewMemberFactory factory;
    static Global* GetInstance() { static Global instance;return &instance; }
    CApp* GetCApp() { return app; }
    CFPS* GetCFPS() { return fps; }
    BlueprintManager* GetBlueprints() { return blueprints; }
    CrewMemberFactory* GetCrewFactory() { return &factory; }
};
namespace BenchmarkVisualEngine {
struct Clock { bool owned=false,advancing=false,permitted=false;unsigned long long world_updates=0;bool update_permitted() const { return permitted; } } frame_clock;
}
unsigned GetCurrentThreadId() { return thread_id; }
#define _WIN32 1
#define __i386__ 1
#define srand monitored_srand
#define HOOK_METHOD_PRIORITY(Class,Method,Priority,Arguments) \
    struct Class##Method##Hook : virtual Class { using Class::Class;auto invoke Arguments; }; \
    auto Class##Method##Hook::invoke Arguments
#include "src/features/crash-detection/ui/CrashDialogManager.h"
bool transfer_dialog_open=false;
namespace BenchmarkFreshStartSeed { bool save_transfer_dialog_open() { return transfer_dialog_open; } }
#include "Benchmark_FreshStartSeed.inc"
#undef srand

int main() {
    using namespace BenchmarkFreshStartSeed;
    using namespace BenchmarkFreshStartSeedHooks;
    using namespace BenchmarkFreshStartCompletionHooks;
    struct TestBuilder:ShipBuilderOpenHook,ShipBuilderOnLoopHook {} builder;
    struct TestWorld:WorldManagerStartGameHook,WorldManagerOnLoopHook,WorldManagerPauseLoopHook {} world;
    CFPSOnLoopHook fps;Global::GetInstance()->fps=&fps;
    MainMenuconstructorHook menu(builder);
    CAppOnLoopHook app(&world,menu);Global::GetInstance()->app=&app;
    BlueprintManagerGetUnusedCrewNameHook names;Global::GetInstance()->blueprints=&names;
    ShipManagerOnInitHook ship;
    bool male=false;ShipBlueprint blueprint;
    auto reset=[&]() {
        totals=Totals();state=State();native_seeds.clear();crt_seeds.clear();order.clear();native_seed_body=nullptr;
        names.currentNames.clear();Global::GetInstance()->factory=CrewMemberFactory();thread_id=42;
        transfer_dialog_open=false;CrashDialogManager::existing=nullptr;
        menu.startButton=Button();menu.buttons={&menu.startButton};menu.finalChoice=-1;
        { UtilityNameScope scope;const std::string value=names.invoke(&male);scope.complete(value); }
        order.clear();
        open_calls=init_calls=name_calls=0;open_body=nullptr;constructor_body=nullptr;
        world_chain_calls=hangar_chain_calls=app_calls=fps_calls=0;thread_id=42;
        builder.bDone=false;start_game_body=nullptr;
        BenchmarkVisualEngine::frame_clock.advancing=false;BenchmarkVisualEngine::frame_clock.permitted=false;
        app_loop_body=[&]() {
            fps.invoke();assert(float_bits(fps.SpeedFactor)==1049135241);
            builder.ShipBuilderOnLoopHook::invoke();
            world.WorldManagerStartGameHook::invoke(&ship);
            world.WorldManagerOnLoopHook::invoke();world.WorldManagerPauseLoopHook::invoke();
        };
        confirm_body=[&]() { menu.bSelectSave=false;menu.confirmNewGame.bOpen=false;builder.ShipBuilderOpenHook::invoke();builder.bOpen=true; };
        Global::GetInstance()->app=&app;app.world=&world;world.bStartedGame=false;menu.bOpen=true;menu.bSelectSave=false;menu.bScoreScreen=false;menu.bCreditScreen=false;menu.confirmNewGame.bOpen=false;
        menu.optionScreen.bOpen=menu.changelog.bOpen=false;builder.bOpen=false;app.langChooser.bOpen=false;
        BenchmarkVisualEngine::frame_clock.owned=true;
        BenchmarkVisualEngine::frame_clock.world_updates=0;fps.SpeedFactor=1.25f;
        advance_body=[&]() {
            if (builder.bOpen) { builder.bDone=true; }
            else { builder.ShipBuilderOpenHook::invoke();builder.bOpen=true; }
        };
    };
    unsigned passed=0;
    reset();assert(hs_benchmark_fresh_seed_contract_version()==3);
    assert(std::string(hs_benchmark_fresh_menu_stage())=="main_menu");++passed;
    reset();BenchmarkVisualEngine::frame_clock.owned=false;
    assert(!hs_benchmark_arm_fresh_seed(1));assert(native_seeds.empty());++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(123));assert(native_seeds.empty()&&crt_seeds.empty());
    native_seed_body=[&]() { assert(names.currentNames.empty()&&state.reservation_reset_applications==1); };
    open_body=[&]() { assert(ship.invoke(&blueprint,0)==7);assert(names.invoke(&male)=="test crew"); };
    assert(hs_benchmark_advance_fresh_menu());
    assert((order==std::vector<std::string>{"native_seed","crt_seed","open_super","ship_init","crew_name"}));
    assert(native_seeds==std::vector<unsigned>{123}&&crt_seeds==std::vector<unsigned>{123});
    assert(state.applied&&!state.pending&&!state.failed&&state.native_applications==1&&state.c_runtime_applications==1);
    assert(state.names_during_open==1&&state.ship_inits_during_open==1&&state.seed_thread_id==42);++passed;
    assert(state.fixed_creation_timing&&!state.construction_scope_active&&fps.SpeedFactor==1.25f);++passed;
    builder.bOpen=false;
    assert(!hs_benchmark_arm_fresh_seed(456));assert(state.epoch==2);++passed; // Prearm generation is rejected.
    reset();assert(hs_benchmark_arm_fresh_seed(12));assert(!hs_benchmark_arm_fresh_seed(99));
    assert(state.seed==12&&state.pending&&state.epoch==1);++passed;
    reset();names.invoke(&male);assert(!hs_benchmark_arm_fresh_seed(12));
    assert(state.failed&&state.names_before_arm==2&&state.unclassified_names_before_arm==1&&native_seeds.empty());++passed;
    reset();ship.invoke(&blueprint,0);assert(!hs_benchmark_arm_fresh_seed(12));
    assert(state.failed&&state.ship_inits_before_arm==1&&native_seeds.empty());++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(12));names.invoke(&male);builder.ShipBuilderOpenHook::invoke();
    assert(state.failed&&!state.applied&&open_calls==0&&native_seeds.empty());++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(12));ship.invoke(&blueprint,0);builder.ShipBuilderOpenHook::invoke();
    assert(state.failed&&!state.applied&&open_calls==0&&crt_seeds.empty());++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(12));BenchmarkVisualEngine::frame_clock.owned=false;builder.ShipBuilderOpenHook::invoke();
    assert(state.failed&&open_calls==0&&native_seeds.empty());++passed;
    reset();constructor_body=[&]() { names.invoke(&male); };menu.invoke();
    assert(totals.names_in_main_menu_constructor==1&&!hs_benchmark_arm_fresh_seed(12));++passed;
    reset();menu.optionScreen.bOpen=true;
    assert(std::string(hs_benchmark_fresh_menu_stage())=="unsupported_modal");
    assert(!hs_benchmark_arm_fresh_seed(12)&&state.epoch==0&&native_seeds.empty());++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(0));assert(hs_benchmark_advance_fresh_menu());builder.ShipBuilderOpenHook::invoke();
    assert(open_calls==2&&native_seeds.size()==1&&crt_seeds.size()==1);++passed;
    const std::string receipt=hs_benchmark_fresh_seed_receipt();
    assert(receipt.find("\"contract\":\"fresh-start-seed-v3\"")!=std::string::npos);
    assert(receipt.find("\"constructor_timing_controlled\":true")!=std::string::npos);++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));
    advance_body=[]() { throw std::runtime_error("test"); };
    assert(!hs_benchmark_advance_fresh_menu());
    assert(state.failed&&state.error=="construction_exception"&&!state.construction_scope_active);
    assert(fps.SpeedFactor==1.25f&&!state.in_open);++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));
    open_body=[]() { throw std::runtime_error("open test"); };
    assert(!hs_benchmark_advance_fresh_menu());
    assert(state.applied&&state.failed&&!state.in_open&&!state.construction_scope_active);
    assert(native_seeds.size()==1&&crt_seeds.size()==1&&fps.SpeedFactor==1.25f);++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));advance_body=[]() {};
    assert(!hs_benchmark_advance_fresh_menu());assert(state.error=="construction_menu_no_progress");
    assert(fps.SpeedFactor==1.25f&&!state.construction_scope_active);++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));
    advance_body=[&]() { builder.ShipBuilderOpenHook::invoke();builder.bOpen=true;++BenchmarkVisualEngine::frame_clock.world_updates; };
    assert(!hs_benchmark_advance_fresh_menu());assert(state.error=="construction_world_clock_changed");
    assert(fps.SpeedFactor==1.25f&&!state.construction_scope_active);++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));assert(hs_benchmark_advance_fresh_menu());
    assert(hs_benchmark_advance_fresh_menu());assert(!world.bStartedGame&&state.start_pending);
    assert(std::string(hs_benchmark_fresh_menu_stage())=="start_pending");
    app.invoke();assert(world.bStartedGame&&state.start_completed&&!state.failed);
    assert(state.start_completion_callbacks==1&&state.start_hangar_onloop_requests==1&&state.start_hangar_onloop_executed==0);
    assert(state.start_game_calls==1&&state.start_game_returns==1&&state.start_cfps_fixed_applications==1);
    assert(world_chain_calls==0&&state.start_world_onloop_blocked==1&&state.start_pause_loop_blocked==1);
    assert(!state.completion_scope_active&&state.start_timing_controlled&&state.start_world_frozen);
    assert(state.construction_clicks==2&&state.completed_construction_clicks==2);
    assert(state.construction_initial_updates==0&&state.construction_final_updates==0&&native_seeds.size()==1);
    assert(fps.SpeedFactor==1.25f&&!state.construction_scope_active);++passed;
    auto pending=[&]() { reset();assert(hs_benchmark_arm_fresh_seed(1));assert(hs_benchmark_advance_fresh_menu());assert(hs_benchmark_advance_fresh_menu()); };
    pending();world.WorldManagerOnLoopHook::invoke();world.WorldManagerPauseLoopHook::invoke();
    assert(world_chain_calls==0&&state.frozen_world_onloop_blocked==1&&state.frozen_pause_loop_blocked==1);++passed;
    BenchmarkVisualEngine::frame_clock.permitted=true;
    world.WorldManagerOnLoopHook::invoke();world.WorldManagerPauseLoopHook::invoke();assert(world_chain_calls==2);++passed;
    reset();world.WorldManagerOnLoopHook::invoke();world.WorldManagerPauseLoopHook::invoke();assert(world_chain_calls==2);++passed;
    pending();BenchmarkVisualEngine::frame_clock.owned=false;
    world.WorldManagerOnLoopHook::invoke();world.WorldManagerPauseLoopHook::invoke();assert(world_chain_calls==2);++passed;
    pending();thread_id=43;app.invoke();assert(state.failed&&app_calls==0&&state.error=="invalid_start_completion_admission");++passed;
    pending();BenchmarkVisualEngine::frame_clock.advancing=true;app.invoke();assert(state.failed&&app_calls==0);++passed;
    pending();app_loop_body=[]() {};app.invoke();assert(state.failed&&state.error=="incomplete_start_completion"&&fps.SpeedFactor==1.25f);++passed;
    pending();app_loop_body=[]() { throw std::runtime_error("app"); };app.invoke();
    assert(state.failed&&state.error=="start_completion_exception"&&!state.completion_scope_active&&fps.SpeedFactor==1.25f);++passed;
    pending();start_game_body=[]() { throw std::runtime_error("start"); };app.invoke();
    assert(state.failed&&state.start_game_calls==1&&state.start_game_returns==0&&fps.SpeedFactor==1.25f);++passed;
    pending();app_loop_body=[&]() { fps.invoke();builder.ShipBuilderOnLoopHook::invoke();builder.ShipBuilderOnLoopHook::invoke();world.WorldManagerStartGameHook::invoke(&ship); };
    app.invoke();assert(state.failed&&state.start_extra_hangar_dwell==1&&state.start_game_calls==0);++passed;
    pending();app_loop_body=[&]() { builder.ShipBuilderOnLoopHook::invoke();world.WorldManagerStartGameHook::invoke(&ship); };
    app.invoke();assert(state.failed&&!state.start_completed&&state.start_cfps_fixed_applications==0);++passed;
    pending();start_game_body=[&]() { world.bStartedGame=true;++BenchmarkVisualEngine::frame_clock.world_updates; };
    app.invoke();assert(state.failed&&!state.start_completed&&state.error=="start_game_clock_changed");++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));assert(hs_benchmark_advance_fresh_menu());builder.ShipBuilderOnLoopHook::invoke();
    assert(state.failed&&state.start_extra_hangar_dwell==1&&open_calls==1);++passed;
    reset();menu.bSelectSave=true;menu.confirmNewGame.bOpen=true;assert(hs_benchmark_arm_fresh_seed(77));
    advance_body=[]() { assert(false&&"confirmation must use parent dispatch"); };
    assert(hs_benchmark_advance_fresh_menu()&&state.applied&&builder.bOpen&&native_seeds[0]==77);++passed;
    pending();app_loop_body=[&]() { fps.invoke();builder.ShipBuilderOnLoopHook::invoke();world.WorldManagerStartGameHook::invoke(&ship);
        assert(state.start_completed&&state.completion_scope_active);BenchmarkVisualEngine::frame_clock.advancing=true;
        world.WorldManagerOnLoopHook::invoke(); };
    app.invoke();assert(!state.failed&&state.start_completed&&world_chain_calls==0);++passed;
    pending();start_game_body=[]() {};app.invoke();assert(state.failed&&!state.start_completed);++passed;
    reset();fps.invoke();assert(fps.SpeedFactor==7.75f&&state.start_cfps_fixed_applications==0);++passed;
    reset();const unsigned unusual=0x7fc12345;std::memcpy(&fps.SpeedFactor,&unusual,4);
    assert(hs_benchmark_arm_fresh_seed(9));assert(hs_benchmark_advance_fresh_menu());assert(float_bits(fps.SpeedFactor)==unusual);++passed;
    pending();app_loop_body=[&]() { fps.invoke();builder.ShipBuilderOnLoopHook::invoke();world.WorldManagerStartGameHook::invoke(&ship);world.WorldManagerStartGameHook::invoke(&ship); };
    app.invoke();assert(state.failed&&state.start_game_calls==1&&state.start_game_returns==1);++passed;
    pending();app.invoke();std::cout << hs_benchmark_fresh_seed_receipt() << "\n";
    reset();totals=Totals();names.currentNames.clear();assert(!hs_benchmark_arm_fresh_seed(1));++passed;
    reset();Global::GetInstance()->factory.crewMembers.push_back(nullptr);assert(!hs_benchmark_arm_fresh_seed(1));assert(native_seeds.empty());++passed;
    reset();Global::GetInstance()->factory.lostMembers.push_back(nullptr);assert(!hs_benchmark_arm_fresh_seed(1));++passed;
    for(int field=0;field<3;++field) { reset();auto& f=Global::GetInstance()->factory;
        (field==0?f.playerCrew:field==1?f.enemyCrew:f.enemyCloneCount)=1;assert(!hs_benchmark_arm_fresh_seed(1));++passed; }
    reset();names.currentNames[0]="different";assert(!hs_benchmark_arm_fresh_seed(1));++passed;
    reset();names.currentNames.push_back("extra");assert(!hs_benchmark_arm_fresh_seed(1));++passed;
    reset();names.currentNames.clear();assert(!hs_benchmark_arm_fresh_seed(1));++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));names.currentNames[0]="changed";
    assert(!hs_benchmark_advance_fresh_menu());assert(state.reservation_reset_applications==0&&native_seeds.empty());++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));Global::GetInstance()->factory.playerCrew=1;
    assert(!hs_benchmark_advance_fresh_menu()&&state.reservation_reset_applications==0);++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));names.invoke(&male);
    assert(!hs_benchmark_advance_fresh_menu()&&state.unclassified_names_before_seed==1&&state.intervening_names_after_arm==1);++passed;
    reset();totals=Totals();names.currentNames.clear();
    { UtilityNameScope scope;names.invoke(&male);names.invoke(&male);scope.complete("test crew"); }
    assert(!hs_benchmark_arm_fresh_seed(1)&&!totals.utility_lookup_valid);++passed;
    reset();totals=Totals();names.currentNames.clear();
    { UtilityNameScope scope;names.invoke(&male); }
    assert(!hs_benchmark_arm_fresh_seed(1)&&!totals.utility_lookup_valid);++passed;
    reset();totals=Totals();names.currentNames.clear();
    { UtilityNameScope scope;names.invoke(&male);scope.complete("mismatch"); }
    assert(!hs_benchmark_arm_fresh_seed(1));++passed;
    reset();thread_id=43;assert(!hs_benchmark_arm_fresh_seed(1));++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));thread_id=43;
    assert(!hs_benchmark_advance_fresh_menu()&&state.reservation_reset_applications==0&&native_seeds.empty());++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));assert(state.names_before_arm==1&&state.names_before_seed==0);
    assert(state.reservation_reset_applications==0&&!state.reservation_reset_verified);
    assert(hs_benchmark_advance_fresh_menu());assert(state.names_before_seed==1&&state.reservations_before_reset==1&&state.reservations_after_reset==0);
    assert(state.reservation_reset_verified&&state.reservation_names_before_reset==std::vector<std::string>{"test crew"});++passed;
    pending();app.invoke();std::cout << hs_benchmark_fresh_seed_receipt() << "\n";
    reset();assert(hs_benchmark_arm_fresh_seed(1));
    advance_body=[&]() { menu.startButton.bHover=true; };
    assert(!hs_benchmark_advance_fresh_menu());
    assert(state.error=="construction_menu_no_progress"&&state.menu_diagnostics.size()==1);
    assert(state.menu_diagnostics[0].before.find("\"hover\":false")!=std::string::npos);
    assert(state.menu_diagnostics[0].after.find("\"hover\":true")!=std::string::npos);
    assert(state.menu_diagnostics[0].after.find("\"is_start\":true")!=std::string::npos);
    assert(state.construction_clicks==1&&state.completed_construction_clicks==0&&native_seeds.empty());++passed;
    std::cout << hs_benchmark_fresh_seed_receipt() << "\n";
    reset();transfer_dialog_open=true;CrashDialogManager crash;
    crash.ask=true;crash.choose=true;crash.instructions=true;crash.error=true;CrashDialogManager::existing=&crash;
    const auto saved=menu_snapshot();
    assert(saved.find("\"save_transfer_dialog\":true")!=std::string::npos);
    assert(saved.find("\"crash_ask_report\":true")!=std::string::npos);
    assert(saved.find("\"crash_choose_destination\":true")!=std::string::npos);
    assert(saved.find("\"crash_instructions\":true")!=std::string::npos);
    assert(saved.find("\"crash_error\":true")!=std::string::npos);
    assert(CrashDialogManager::get_instance_calls==0&&native_seeds.empty()&&name_calls==0&&init_calls==0);++passed;
    std::cout << saved << "\n";
    reset();menu.buttons.assign(200,&menu.startButton);
    assert(menu_snapshot().find("\"menu_buttons_truncated\":true")!=std::string::npos);
    assert(menu_snapshot().find("\"index\":127")!=std::string::npos);
    assert(menu_snapshot().find("\"index\":128")==std::string::npos);++passed;
    reset();app.world=nullptr;Global::GetInstance()->app=nullptr;
    assert(capture_menu_snapshot()=="{\"diagnostic_error\":\"app_unavailable\"}");++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));advance_body=[]() { throw std::runtime_error("forward"); };
    assert(!hs_benchmark_advance_fresh_menu()&&state.menu_diagnostics.size()==1);
    assert(state.menu_diagnostics[0].call_exception&&!state.menu_diagnostics[0].after.empty());
    assert(state.error=="construction_exception"&&state.construction_clicks==1&&fps.SpeedFactor==1.25f);++passed;
    reset();const auto original_names=names.currentNames;const auto original_clock=BenchmarkVisualEngine::frame_clock.world_updates;
    const auto original_sf=fps.SpeedFactor;const auto original_button=menu.startButton;
    capture_menu_snapshot();capture_menu_snapshot();
    assert(names.currentNames==original_names&&BenchmarkVisualEngine::frame_clock.world_updates==original_clock&&fps.SpeedFactor==original_sf);
    assert(menu.startButton.bActive==original_button.bActive&&menu.startButton.bHover==original_button.bHover);
    assert(open_calls==0&&native_seeds.empty()&&crt_seeds.empty()&&CrashDialogManager::get_instance_calls==0);++passed;
    reset();assert(hs_benchmark_arm_fresh_seed(1));
    advance_body=[&]() { menu.bSelectSave=true;menu.confirmNewGame.bOpen=true; };
    assert(hs_benchmark_advance_fresh_menu());
    assert(std::string(hs_benchmark_fresh_menu_stage())=="overwrite_confirmation"&&state.pending&&native_seeds.empty());
    assert(state.construction_clicks==1&&state.completed_construction_clicks==1);
    assert(state.menu_diagnostics[0].after.find("\"select_save\":true")!=std::string::npos);
    assert(state.menu_diagnostics[0].after.find("\"overwrite_confirmation\":true")!=std::string::npos);
    open_body=[&]() { names.invoke(&male);ship.invoke(&blueprint,0); };
    assert(hs_benchmark_advance_fresh_menu());
    assert(std::string(hs_benchmark_fresh_menu_stage())=="hangar"&&!menu.bSelectSave&&!menu.confirmNewGame.bOpen);
    assert(state.applied&&native_seeds.size()==1&&crt_seeds.size()==1&&state.reservation_reset_applications==1);
    assert(state.construction_clicks==2&&state.completed_construction_clicks==2&&BenchmarkVisualEngine::frame_clock.world_updates==0);++passed;
    std::cout << hs_benchmark_fresh_seed_receipt() << "\n";
    reset();menu.bSelectSave=true;
    assert(std::string(hs_benchmark_fresh_menu_stage())=="unsupported_modal");
    assert(!hs_benchmark_arm_fresh_seed(1)&&state.epoch==0&&state.construction_clicks==0);++passed;
    reset();menu.bSelectSave=true;menu.confirmNewGame.bOpen=true;builder.bOpen=true;
    assert(std::string(hs_benchmark_fresh_menu_stage())=="ambiguous");
    assert(!hs_benchmark_arm_fresh_seed(1)&&native_seeds.empty());++passed;
    for (int modal=0;modal<4;++modal) {
        reset();menu.bSelectSave=true;menu.confirmNewGame.bOpen=true;
        (modal==0?menu.bScoreScreen:modal==1?menu.bCreditScreen:modal==2?menu.optionScreen.bOpen:menu.changelog.bOpen)=true;
        assert(std::string(hs_benchmark_fresh_menu_stage())=="unsupported_modal");
        assert(!hs_benchmark_arm_fresh_seed(1)&&state.epoch==0&&native_seeds.empty());++passed;
    }
    reset();menu.bSelectSave=true;menu.confirmNewGame.bOpen=true;
    assert(std::string(hs_benchmark_fresh_menu_stage())=="overwrite_confirmation");
    assert(hs_benchmark_arm_fresh_seed(1)&&state.arm_stage=="overwrite_confirmation"&&native_seeds.empty());++passed;
    reset();menu.confirmNewGame.bOpen=true;
    assert(std::string(hs_benchmark_fresh_menu_stage())=="unsupported_modal");
    assert(!hs_benchmark_arm_fresh_seed(1)&&state.epoch==0&&state.construction_clicks==0);++passed;
    std::cout << "{\"actual_candidate_include_tests_passed\":" << passed << "}\n";
}
