// Isolated candidate: one fresh-start seed boundary, no encounter/action reseeds.
// Included at the end of Benchmark_Extend.cpp, after the visual clock is defined.
#include <cstdlib>
#include <cstring>
#include <limits>
#include <cstdint>
#include <algorithm>
#include "Benchmark_FreshStartUtility.h"
#if defined(_WIN32) && defined(__i386__)
#include "src/features/crash-detection/ui/CrashDialogManager.h"
#endif

namespace BenchmarkFreshStartSeed {
constexpr unsigned contract_version=3;
constexpr int outer_priority=-1000000;
struct Totals {
    unsigned long long names=0, ship_inits=0,utility_name_calls=0;
    unsigned utility_lookup_calls=0,utility_lookup_completed=0,utility_thread_id=0;
    bool utility_scope_active=false,utility_lookup_valid=true;
    std::string utility_name;
    unsigned main_menu_constructors=0, ship_builder_constructors=0;
    unsigned long long names_in_main_menu_constructor=0, names_in_ship_builder_constructor=0;
} totals;
struct ForwardDiagnostic { std::string stage,before,after;bool call_exception=false; };
struct State {
    unsigned seed=0, epoch=0, native_applications=0, c_runtime_applications=0;
    unsigned long long names_before_arm=0, names_before_seed=0, names_after_seed=0, names_during_open=0;
    unsigned long long ship_inits_before_arm=0, ship_inits_before_seed=0, ship_inits_after_seed=0, ship_inits_during_open=0;
    bool pending=false, applied=false, failed=false, in_open=false;
    bool owned_at_arm=false, owned_at_boundary=false, update_permitted_at_boundary=false;
    bool construction_scope_active=false, fixed_creation_timing=false;
    bool start_pending=false, start_completed=false, completion_scope_active=false;
    bool start_timing_controlled=false, start_world_frozen=false;
    unsigned start_completion_callbacks=0, start_extra_hangar_dwell=0;
    unsigned start_hangar_onloop_requests=0, start_hangar_onloop_executed=0;
    unsigned start_game_calls=0, start_game_returns=0, start_cfps_fixed_applications=0;
    unsigned start_world_onloop_blocked=0, start_pause_loop_blocked=0;
    unsigned long long frozen_world_onloop_blocked=0, frozen_pause_loop_blocked=0;
    unsigned start_speed_factor_bits=0, start_thread_id=0;
    unsigned long long start_world_updates_before=0, start_world_updates_after=0;
    unsigned construction_clicks=0, completed_construction_clicks=0;
    unsigned long long construction_initial_updates=0, construction_final_updates=0;
    unsigned speed_factor_bits_at_boundary=0, seed_thread_id=0;
    unsigned long long unclassified_names_before_arm=0,unclassified_names_before_seed=0,intervening_names_after_arm=0;
    unsigned reservation_reset_applications=0,reservation_reset_thread_id=0;
    bool reservation_reset_verified=false;
    unsigned long long reservations_before_arm=0,reservations_before_reset=0,reservations_after_reset=0;
    int factory_crew_before_arm=-1,factory_lost_before_arm=-1,factory_player_before_arm=-1,factory_enemy_before_arm=-1,factory_clone_before_arm=-1;
    int factory_crew_before_reset=-1,factory_lost_before_reset=-1,factory_player_before_reset=-1,factory_enemy_before_reset=-1,factory_clone_before_reset=-1;
    std::vector<std::string> reservation_names_before_reset;
    std::vector<ForwardDiagnostic> menu_diagnostics;
    std::string arm_stage, error;
} state;
UtilityNameScope::UtilityNameScope() {
    if (totals.utility_scope_active || state.epoch || totals.utility_lookup_calls) totals.utility_lookup_valid=false;
    ++totals.utility_lookup_calls;totals.utility_scope_active=true;
#if defined(_WIN32) && defined(__i386__)
    totals.utility_thread_id=GetCurrentThreadId();
#endif
}
UtilityNameScope::~UtilityNameScope() {
    totals.utility_scope_active=false;
    if (!finished) totals.utility_lookup_valid=false;
}
void UtilityNameScope::complete(const std::string& captured_name) {
    finished=true;++totals.utility_lookup_completed;
    if (totals.utility_name_calls!=1 || captured_name.empty() || captured_name!=totals.utility_name)
        totals.utility_lookup_valid=false;
}
bool known_utility() {
    return !totals.utility_scope_active && totals.utility_lookup_valid && totals.utility_lookup_calls==1 &&
           totals.utility_lookup_completed==1 && totals.utility_name_calls==1 && !totals.utility_name.empty();
}
bool record_empty_factory(bool arm) {
    CrewMemberFactory* factory=Global::GetInstance()->GetCrewFactory();
    if (!factory) return false;
    int& crew=arm?state.factory_crew_before_arm:state.factory_crew_before_reset;
    int& lost=arm?state.factory_lost_before_arm:state.factory_lost_before_reset;
    int& player=arm?state.factory_player_before_arm:state.factory_player_before_reset;
    int& enemy=arm?state.factory_enemy_before_arm:state.factory_enemy_before_reset;
    int& clone=arm?state.factory_clone_before_arm:state.factory_clone_before_reset;
    crew=static_cast<int>(factory->crewMembers.size());lost=static_cast<int>(factory->lostMembers.size());
    player=factory->playerCrew;enemy=factory->enemyCrew;clone=factory->enemyCloneCount;
    return factory->crewMembers.empty() && factory->lostMembers.empty() && player==0 && enemy==0 && clone==0;
}
bool sole_utility_reservation(BlueprintManager* blueprints) {
    return blueprints && blueprints->currentNames.size()==1 && blueprints->currentNames[0]==totals.utility_name;
}
std::string quoted(const std::string& value) {
    std::ostringstream out;out << '"';
    const char hex[]="0123456789abcdef";
    for (unsigned char c:value) {
        if (c=='"' || c=='\\') out << '\\' << char(c);
        else if (c<32) out << "\\u00" << hex[c>>4] << hex[c&15];
        else out << char(c);
    }
    out << '"';return out.str();
}
#if defined(_WIN32) && defined(__i386__)
// Optional evidence only. Never consulted for clicks, admission or timing.
std::string menu_snapshot() {
    CApp* app=Global::GetInstance()->GetCApp();
    if (!app) return "{\"diagnostic_error\":\"app_unavailable\"}";
    MainMenu& menu=app->menu;Button& button=menu.startButton;
    std::ostringstream json;json << std::boolalpha
        << "{\"world_updates\":\"" << BenchmarkVisualEngine::frame_clock.world_updates << "\",\"menu_open\":" << menu.bOpen << ",\"final_choice\":" << menu.finalChoice
        << ",\"score_screen\":" << menu.bScoreScreen << ",\"credit_screen\":" << menu.bCreditScreen
        << ",\"select_save\":" << menu.bSelectSave << ",\"option_screen\":" << menu.optionScreen.bOpen
        << ",\"changelog\":" << menu.changelog.bOpen << ",\"overwrite_confirmation\":" << menu.confirmNewGame.bOpen
        << ",\"ship_builder_open\":" << menu.shipBuilder.bOpen << ",\"ship_builder_done\":" << menu.shipBuilder.bDone
        << ",\"language_chooser\":" << app->langChooser.bOpen
        << ",\"save_transfer_dialog\":" << save_transfer_dialog_open()
        << ",\"start_button\":{\"identity\":" << quoted(std::to_string(reinterpret_cast<std::uintptr_t>(&button)))
        << ",\"active\":" << button.bActive << ",\"hover\":" << button.bHover
        << ",\"hitbox\":{\"x\":" << button.hitbox.x << ",\"y\":" << button.hitbox.y
        << ",\"w\":" << button.hitbox.w << ",\"h\":" << button.hitbox.h << '}'
        << ",\"position\":{\"x\":" << button.position.x << ",\"y\":" << button.position.y << "}}";
    const auto* crash=CrashDialogManager::PeekInstanceForBenchmark();
    json << ",\"crash_dialog_manager_present\":" << (crash!=nullptr)
        << ",\"crash_ask_report\":" << (crash && crash->IsAskReportDialogOpen())
        << ",\"crash_choose_destination\":" << (crash && crash->IsChooseDestinationDialogOpen())
        << ",\"crash_instructions\":" << (crash && crash->IsInstructionsDialogOpen())
        << ",\"crash_error\":" << (crash && crash->IsErrorDialogOpen());
    json << ",\"menu_buttons_count\":" << menu.buttons.size()
        << ",\"menu_buttons_truncated\":" << (menu.buttons.size()>128) << ",\"menu_buttons\":[";
    const size_t count=std::min<size_t>(menu.buttons.size(),128);
    for (size_t index=0;index<count;++index) {
        if (index) json << ',';
        json << "{\"index\":" << index
            << ",\"identity\":" << quoted(std::to_string(reinterpret_cast<std::uintptr_t>(menu.buttons[index])))
            << ",\"is_start\":" << (menu.buttons[index]==&button) << '}';
    }
    json << "]}";return json.str();
}
std::string capture_menu_snapshot() {
    try { return menu_snapshot(); }
    catch (...) { return "{\"diagnostic_error\":\"snapshot_exception\"}"; }
}
#endif
unsigned float_bits(const float& value) { unsigned result=0;std::memcpy(&result,&value,4);return result; }
bool owned() {
#if defined(_WIN32) && defined(__i386__)
    return BenchmarkVisualEngine::frame_clock.owned;
#else
    return false;
#endif
}
void fail(const char* message) { state.pending=false;if (!state.failed) state.error=message;state.failed=true; }
#if defined(_WIN32) && defined(__i386__)
// Sets only the cached base factor for synchronous construction calls. The
// ordinary GetSpeedFactor hook chain and native temporal multipliers remain.
struct ConstructionScope {
    CFPS* fps;unsigned saved_bits;bool& active;
    explicit ConstructionScope(CFPS* value,bool completion=false):fps(value),saved_bits(float_bits(value->SpeedFactor)),
        active(completion?state.completion_scope_active:state.construction_scope_active) {
        fps->SpeedFactor=16.f/60.f;active=true;
    }
    ~ConstructionScope() {
        std::memcpy(&fps->SpeedFactor,&saved_bits,4);active=false;
    }
};
#endif
}

unsigned hs_benchmark_fresh_seed_contract_version()
{
#if defined(_WIN32) && defined(__i386__)
    return BenchmarkFreshStartSeed::contract_version;
#else
    return 0;
#endif
}

const char* hs_benchmark_fresh_menu_stage()
{
    CApp* app=Global::GetInstance()->GetCApp();
    if (!app || !app->world) return "unavailable";
    if (app->world->bStartedGame) return "in_game";
    if (BenchmarkFreshStartSeed::state.start_pending && app->menu.shipBuilder.bDone) return "start_pending";
    if (app->langChooser.bOpen) return "language_chooser";
    MainMenu& menu=app->menu;
    if (!menu.bOpen) return "closed";
    // Native New Game sets bSelectSave while confirmNewGame is open; the
    // parent confirmation click clears bSelectSave before normal ShipBuilder Open.
    // Either unmatched flag remains unsupported.
    if (menu.bScoreScreen || menu.bCreditScreen || (menu.bSelectSave != menu.confirmNewGame.bOpen) ||
        menu.optionScreen.bOpen || menu.changelog.bOpen) return "unsupported_modal";
    if (menu.confirmNewGame.bOpen && menu.shipBuilder.bOpen) return "ambiguous";
    if (menu.confirmNewGame.bOpen) return "overwrite_confirmation";
    if (menu.shipBuilder.bOpen) return "hangar";
    return "main_menu";
}

bool hs_benchmark_arm_fresh_seed(unsigned seed)
{
    using namespace BenchmarkFreshStartSeed;
    const std::string stage=hs_benchmark_fresh_menu_stage();
    if (state.pending || state.construction_scope_active || state.completion_scope_active || !owned() || (stage!="main_menu" && stage!="overwrite_confirmation") ||
        state.epoch==std::numeric_limits<unsigned>::max()) return false;
    const unsigned next_epoch=state.epoch+1;
    state=State();state.epoch=next_epoch;state.seed=seed;state.arm_stage=stage;
    state.owned_at_arm=true;state.names_before_arm=totals.names;state.ship_inits_before_arm=totals.ship_inits;
    // Only the precise startup dummy lookup is classified; real generated
    // crew/ships and other orphan reservations remain inadmissible.
    state.unclassified_names_before_arm=totals.names>=totals.utility_name_calls?totals.names-totals.utility_name_calls:totals.names;
    BlueprintManager* blueprints=Global::GetInstance()->GetBlueprints();
    if (blueprints) state.reservations_before_arm=blueprints->currentNames.size();
    if (!known_utility() || totals.names!=totals.utility_name_calls || totals.ship_inits || !record_empty_factory(true) ||
        !sole_utility_reservation(blueprints)
#if defined(_WIN32) && defined(__i386__)
        || totals.utility_thread_id!=GetCurrentThreadId()
#endif
        ) { fail("invalid_clean_start_before_arm");return false; }
    state.pending=true;
    return true;
}

const char* hs_benchmark_fresh_seed_receipt()
{
    using namespace BenchmarkFreshStartSeed;
    static std::string receipt;
    std::ostringstream json;
    json << std::boolalpha << "{\"contract\":\"fresh-start-seed-v3\",\"contract_version\":3"
         << ",\"boundary\":\"ShipBuilder::Open.before_super\",\"epoch\":" << state.epoch
         << ",\"seed\":" << state.seed << ",\"pending\":" << state.pending << ",\"applied\":" << state.applied
         << ",\"failed\":" << state.failed << ",\"arm_stage\":\"" << state.arm_stage << "\",\"error\":\"" << state.error << '"'
         << ",\"native_seed_applications\":" << state.native_applications
         << ",\"c_runtime_seed_applications\":" << state.c_runtime_applications
         << ",\"c_runtime\":\"DLL msvcrt.dll std::srand\",\"seed_thread_id\":" << state.seed_thread_id
         << ",\"names_before_arm\":" << state.names_before_arm << ",\"names_before_seed\":" << state.names_before_seed
         << ",\"names_after_seed\":" << state.names_after_seed << ",\"names_during_open\":" << state.names_during_open
         << ",\"ship_inits_before_arm\":" << state.ship_inits_before_arm
         << ",\"ship_inits_before_seed\":" << state.ship_inits_before_seed
         << ",\"ship_inits_after_seed\":" << state.ship_inits_after_seed
         << ",\"ship_inits_during_open\":" << state.ship_inits_during_open
         << ",\"main_menu_constructors\":" << totals.main_menu_constructors
         << ",\"ship_builder_constructors\":" << totals.ship_builder_constructors
         << ",\"names_in_main_menu_constructor\":" << totals.names_in_main_menu_constructor
         << ",\"names_in_ship_builder_constructor\":" << totals.names_in_ship_builder_constructor
         << ",\"clock_owned_at_arm\":" << state.owned_at_arm
         << ",\"clock_owned_at_boundary\":" << state.owned_at_boundary
         << ",\"clock_update_permitted_at_boundary\":" << state.update_permitted_at_boundary
         << ",\"base_speed_factor_bits_at_boundary\":" << state.speed_factor_bits_at_boundary
         << ",\"construction_speed_factor_bits\":" << state.speed_factor_bits_at_boundary
         << ",\"fixed_creation_timing\":" << state.fixed_creation_timing
         << ",\"constructor_timing_controlled\":" << state.fixed_creation_timing
         << ",\"construction_clock_owned\":" << state.owned_at_boundary
         << ",\"construction_fixed_step_numerator\":1,\"construction_fixed_step_denominator\":60"
         << ",\"construction_scope_active\":" << state.construction_scope_active
         << ",\"construction_clicks\":" << state.construction_clicks
         << ",\"completed_construction_clicks\":" << state.completed_construction_clicks
         << ",\"construction_initial_world_updates\":\"" << state.construction_initial_updates
         << "\",\"construction_final_world_updates\":\"" << state.construction_final_updates << "\"}";
    std::string text=json.str();text.pop_back();
    json.str("");json.clear();json << text
         << ",\"start_pending\":" << state.start_pending << ",\"start_completed\":" << state.start_completed
         << ",\"start_completion_callbacks\":" << state.start_completion_callbacks
         << ",\"start_extra_hangar_dwell\":" << state.start_extra_hangar_dwell
         << ",\"start_world_updates_before\":\"" << state.start_world_updates_before
         << "\",\"start_world_updates_after\":\"" << state.start_world_updates_after << '"'
         << ",\"start_timing_controlled\":" << state.start_timing_controlled
         << ",\"start_world_frozen\":" << state.start_world_frozen
         << ",\"start_completion_scope_active\":" << state.completion_scope_active
         << ",\"start_hangar_onloop_requests\":" << state.start_hangar_onloop_requests
         << ",\"start_hangar_onloop_executed\":" << state.start_hangar_onloop_executed
         << ",\"start_game_calls\":" << state.start_game_calls << ",\"start_game_returns\":" << state.start_game_returns
         << ",\"start_cfps_fixed_applications\":" << state.start_cfps_fixed_applications
         << ",\"start_world_onloop_blocked\":" << state.start_world_onloop_blocked
         << ",\"start_pause_loop_blocked\":" << state.start_pause_loop_blocked
         << ",\"start_speed_factor_bits\":" << state.start_speed_factor_bits
         << ",\"start_thread_id\":" << state.start_thread_id << '}';
    receipt=json.str();receipt.pop_back();
    receipt+=",\"frozen_world_onloop_blocked\":"+std::to_string(state.frozen_world_onloop_blocked)+
             ",\"frozen_pause_loop_blocked\":"+std::to_string(state.frozen_pause_loop_blocked)+"}";
    receipt.pop_back();
    std::ostringstream extra;extra << std::boolalpha
        << ",\"utility_name_calls\":" << totals.utility_name_calls
        << ",\"utility_lookup_calls\":" << totals.utility_lookup_calls
        << ",\"utility_lookup_completed\":" << totals.utility_lookup_completed
        << ",\"utility_lookup_valid\":" << totals.utility_lookup_valid
        << ",\"utility_name_provenance\":\"StatBoostManager::CreateDummyCrew.GetCrewBlueprint(human)\""
        << ",\"utility_name\":" << quoted(totals.utility_name) << ",\"utility_thread_id\":" << totals.utility_thread_id
        << ",\"unclassified_names_before_arm\":" << state.unclassified_names_before_arm
        << ",\"unclassified_names_before_seed\":" << state.unclassified_names_before_seed
        << ",\"intervening_names_after_arm\":" << state.intervening_names_after_arm
        << ",\"reservations_before_arm\":" << state.reservations_before_arm
        << ",\"reservations_before_reset\":" << state.reservations_before_reset
        << ",\"reservations_after_reset\":" << state.reservations_after_reset
        << ",\"reservation_reset_applications\":" << state.reservation_reset_applications
        << ",\"reservation_reset_verified\":" << state.reservation_reset_verified
        << ",\"reservation_reset_thread_id\":" << state.reservation_reset_thread_id;
    extra << ",\"reservation_names_before_reset\":[";
    for (size_t i=0;i<state.reservation_names_before_reset.size();++i) {
        if (i) extra << ',';extra << quoted(state.reservation_names_before_reset[i]);
    }
    extra << ']';
#define FRESH_FACTORY_RECEIPT(field) extra << ",\"" #field "\":" << state.field
    FRESH_FACTORY_RECEIPT(factory_crew_before_arm);FRESH_FACTORY_RECEIPT(factory_lost_before_arm);
    FRESH_FACTORY_RECEIPT(factory_player_before_arm);FRESH_FACTORY_RECEIPT(factory_enemy_before_arm);FRESH_FACTORY_RECEIPT(factory_clone_before_arm);
    FRESH_FACTORY_RECEIPT(factory_crew_before_reset);FRESH_FACTORY_RECEIPT(factory_lost_before_reset);
    FRESH_FACTORY_RECEIPT(factory_player_before_reset);FRESH_FACTORY_RECEIPT(factory_enemy_before_reset);FRESH_FACTORY_RECEIPT(factory_clone_before_reset);
#undef FRESH_FACTORY_RECEIPT
    extra << ",\"menu_diagnostics_contract\":\"native-menu-forward-diagnostic-v1\",\"menu_forward_diagnostics\":[";
    for (size_t index=0;index<state.menu_diagnostics.size();++index) {
        if (index) extra << ',';
        const ForwardDiagnostic& row=state.menu_diagnostics[index];
        extra << "{\"index\":" << index+1 << ",\"stage\":" << quoted(row.stage)
            << ",\"before\":" << row.before << ",\"after\":" << (row.after.empty()?"null":row.after)
            << ",\"call_exception\":" << row.call_exception << '}';
    }
    extra << ']';
    receipt+=extra.str()+"}";return receipt.c_str();
}

// One existing forward click only. Lua owns the bounded synchronous chain;
// this wrapper prevents each click from inheriting ambient construction dt.
bool hs_benchmark_advance_fresh_menu()
{
    using namespace BenchmarkFreshStartSeed;
#if defined(_WIN32) && defined(__i386__)
    const std::string before=hs_benchmark_fresh_menu_stage();
    if (state.failed || state.construction_scope_active || (!state.pending && !state.applied) || !owned() ||
        (before!="main_menu" && before!="overwrite_confirmation" && before!="hangar")) return false;
    if (before=="hangar" && (!state.applied || state.native_applications!=1 || state.c_runtime_applications!=1)) {
        fail("unseeded_hangar");return false;
    }
    CFPS* fps=Global::GetInstance()->GetCFPS();
    if (!fps || (state.applied && state.seed_thread_id!=GetCurrentThreadId())) {
        fail("invalid_construction_clock_or_thread");return false;
    }
    const unsigned long long updates=BenchmarkVisualEngine::frame_clock.world_updates;
    if (!state.construction_clicks) state.construction_initial_updates=updates;
    ++state.construction_clicks;
    state.menu_diagnostics.push_back(ForwardDiagnostic());
    ForwardDiagnostic& diagnostic=state.menu_diagnostics.back();
    diagnostic.stage=before;diagnostic.before=capture_menu_snapshot();
    try {
        ConstructionScope scope(fps);
        if (before=="overwrite_confirmation") {
            // ConfirmWindow alone does not dispatch MainMenu's confirmed action.
            CApp* app=Global::GetInstance()->GetCApp();
            const Globals::Rect& box=app->menu.confirmNewGame.yesButton.hitbox;
            const int x=box.x+box.w/2,y=box.y+box.h/2;
            app->menu.MouseMove(x,y);app->menu.MouseClick(x,y);
        } else {
            hs_benchmark_advance_menu();
        }
        diagnostic.after=capture_menu_snapshot();
        CApp* app=Global::GetInstance()->GetCApp();
        if (before=="hangar" && app && app->world && !app->world->bStartedGame && app->menu.shipBuilder.bDone) {
            state.start_pending=true;state.start_world_updates_before=updates;state.start_world_updates_after=updates;
        }
        state.construction_final_updates=BenchmarkVisualEngine::frame_clock.world_updates;
        const std::string after=hs_benchmark_fresh_menu_stage();
        if (state.failed) return false;
        if (!owned() || state.construction_final_updates!=updates) { fail("construction_world_clock_changed");return false; }
        if (after==before || (after!="overwrite_confirmation" && after!="hangar" && after!="start_pending")) {
            fail("construction_menu_no_progress");return false;
        }
        ++state.completed_construction_clicks;
        return true;
    } catch (...) {
        diagnostic.call_exception=true;diagnostic.after=capture_menu_snapshot();
        fail("construction_exception");return false;
    }
#else
    return false;
#endif
}

#if defined(_WIN32) && defined(__i386__)
// Read-only predicates used by hooks; receipts never drive or finalize state.
namespace BenchmarkFreshStartSeed {
bool current_world(const WorldManager* world) {
    CApp* app=Global::GetInstance()->GetCApp();return app && app->world==world;
}
bool completion_world_frozen() {
    const auto& clock=BenchmarkVisualEngine::frame_clock;
    return clock.owned && !clock.advancing && !clock.update_permitted() &&
           clock.world_updates==state.start_world_updates_before;
}
}
namespace BenchmarkFreshStartCompletionHooks {
HOOK_METHOD_PRIORITY(CFPS, OnLoop, -1000000, () -> void)
{
    super(); // Includes ordinary bookkeeping and the existing clock2 hook.
    using namespace BenchmarkFreshStartSeed;
    if (state.completion_scope_active && this==Global::GetInstance()->GetCFPS()) {
        this->SpeedFactor=16.f/60.f;++state.start_cfps_fixed_applications;
    }
}
HOOK_METHOD_PRIORITY(CApp, OnLoop, -1000000, () -> void)
{
    using namespace BenchmarkFreshStartSeed;
    if (!state.start_pending) { super();return; }
    CFPS* fps=Global::GetInstance()->GetCFPS();
    if (this!=Global::GetInstance()->GetCApp() || !fps || state.failed || state.start_completion_callbacks ||
        !completion_world_frozen() || state.seed_thread_id!=GetCurrentThreadId()) {
        fail("invalid_start_completion_admission");return;
    }
    ++state.start_completion_callbacks;
    state.start_thread_id=GetCurrentThreadId();
    try {
        ConstructionScope scope(fps,true);
        super(); // MainMenu consumes bDone; CApp normally invokes StartGame.
        state.start_world_updates_after=BenchmarkVisualEngine::frame_clock.world_updates;
        if (!state.failed && (!state.start_completed || state.start_game_calls!=1 || state.start_game_returns!=1 ||
            state.start_cfps_fixed_applications!=1 || state.start_hangar_onloop_requests!=1 ||
            !BenchmarkVisualEngine::frame_clock.owned || state.start_world_updates_after!=state.start_world_updates_before))
            fail("incomplete_start_completion");
    } catch (...) { fail("start_completion_exception"); }
}
HOOK_METHOD_PRIORITY(ShipBuilder, OnLoop, -1000000, () -> void)
{
    using namespace BenchmarkFreshStartSeed;
    CApp* app=Global::GetInstance()->GetCApp();
    if (state.applied && owned() && app && app->world && this==&app->menu.shipBuilder && !app->world->bStartedGame) {
        if (state.completion_scope_active && state.start_pending) {
            ++state.start_hangar_onloop_requests;
            if (state.start_hangar_onloop_requests!=1) { ++state.start_extra_hangar_dwell;fail("extra_completion_hangar_dwell"); }
        } else { ++state.start_extra_hangar_dwell;fail("unbudgeted_seeded_hangar_dwell"); }
        return; // Avoid ShipManager/crew-factory aging; GetShip still consumes bDone normally.
    }
    if (state.completion_scope_active) ++state.start_hangar_onloop_executed;
    super();
}
HOOK_METHOD_PRIORITY(WorldManager, StartGame, -1000000, (ShipManager* ship) -> void)
{
    using namespace BenchmarkFreshStartSeed;
    if (!state.applied || !current_world(this)) { super(ship);return; }
    const float fixed=16.f/60.f;CFPS* fps=Global::GetInstance()->GetCFPS();
    if (!state.completion_scope_active || !state.start_pending || state.failed || !completion_world_frozen() ||
        state.start_game_calls || !fps || float_bits(fps->SpeedFactor)!=float_bits(fixed)) {
        fail("invalid_start_game_boundary");return;
    }
    ++state.start_game_calls;state.start_speed_factor_bits=float_bits(fps->SpeedFactor);
    super(ship);++state.start_game_returns;
    state.start_world_updates_after=BenchmarkVisualEngine::frame_clock.world_updates;
    state.start_world_frozen=completion_world_frozen();
    state.start_timing_controlled=state.start_world_frozen && state.start_cfps_fixed_applications==1 && this->bStartedGame;
    if (!state.start_timing_controlled) { fail("start_game_clock_changed");return; }
    // Completed before post-loop Lua tick. The separate scope remains active
    // through that callback, holding later World loops even after pending clears.
    state.start_pending=false;state.start_completed=true;
}
HOOK_METHOD_PRIORITY(WorldManager, OnLoop, -1000000, () -> void)
{
    using namespace BenchmarkFreshStartSeed;
    if (state.completion_scope_active && current_world(this)) { ++state.start_world_onloop_blocked;return; }
    if (state.applied && owned() && !BenchmarkVisualEngine::frame_clock.update_permitted() && current_world(this)) {
        ++state.frozen_world_onloop_blocked;return;
    }
    super();
}
HOOK_METHOD_PRIORITY(WorldManager, PauseLoop, -1000000, () -> void)
{
    using namespace BenchmarkFreshStartSeed;
    if (state.completion_scope_active && current_world(this)) { ++state.start_pause_loop_blocked;return; }
    if (state.applied && owned() && !BenchmarkVisualEngine::frame_clock.update_permitted() && current_world(this)) {
        ++state.frozen_pause_loop_blocked;return;
    }
    super();
}
}
#endif

// ZHL installs descending priority: later lower priorities wrap earlier hooks.
// No existing Open wrapper has this priority; both default wrappers are inside.
namespace BenchmarkFreshStartSeedHooks {
HOOK_METHOD_PRIORITY(ShipBuilder, Open, -1000000, () -> void)
{
    using namespace BenchmarkFreshStartSeed;
    if (!state.pending) { super();return; }
    CApp* app=Global::GetInstance()->GetCApp();
    state.pending=false;
    state.names_before_seed=totals.names;state.ship_inits_before_seed=totals.ship_inits;
    state.unclassified_names_before_seed=totals.names>=totals.utility_name_calls?totals.names-totals.utility_name_calls:totals.names;
    state.intervening_names_after_arm=totals.names-state.names_before_arm;
    BlueprintManager* blueprints=Global::GetInstance()->GetBlueprints();
    if (!app || !app->world || app->world->bStartedGame || this!=&app->menu.shipBuilder ||
        !known_utility() || totals.names!=totals.utility_name_calls || state.intervening_names_after_arm ||
        state.ship_inits_before_seed || !record_empty_factory(false) || !sole_utility_reservation(blueprints) ||
        !owned() || !state.construction_scope_active) {
        fail("invalid_or_late_open_boundary");return;
    }
    state.owned_at_boundary=owned();
#if defined(_WIN32) && defined(__i386__)
    state.update_permitted_at_boundary=BenchmarkVisualEngine::frame_clock.update_permitted();
    CFPS* fps=Global::GetInstance()->GetCFPS();
    if (fps) state.speed_factor_bits_at_boundary=float_bits(fps->SpeedFactor);
    const float fixed_factor=16.f/60.f;
    if (!fps || state.speed_factor_bits_at_boundary!=float_bits(fixed_factor)) {
        fail("construction_factor_not_fixed");return;
    }
    if (totals.utility_thread_id!=GetCurrentThreadId()) { fail("utility_seed_thread_changed");return; }
    state.fixed_creation_timing=true;
    state.reservations_before_reset=blueprints->currentNames.size();
    state.reservation_names_before_reset=blueprints->currentNames;
    state.reservation_reset_thread_id=GetCurrentThreadId();
    // Normal SetUsedCrewNames is exactly vector assignment. With a proven empty
    // real factory, clear only the known orphan utility reservation, once here.
    blueprints->currentNames.clear();++state.reservation_reset_applications;
    state.reservations_after_reset=blueprints->currentNames.size();
    state.reservation_reset_verified=blueprints->currentNames.empty();
    if (!state.reservation_reset_verified) { fail("clean_start_reservation_reset_failed");return; }
    state.seed_thread_id=GetCurrentThreadId();
    // Exactly one application each in the same DLL/thread as this native hook.
    srandom32(state.seed);++state.native_applications;
    std::srand(state.seed);++state.c_runtime_applications;
    state.applied=true;
    struct OpenScope { OpenScope() { state.in_open=true; } ~OpenScope() { state.in_open=false; } } open_scope;
    super();
#else
    fail("unsupported_platform");
#endif
}

HOOK_METHOD_PRIORITY(BlueprintManager, GetUnusedCrewName, -1000000, (bool* isMale_ret) -> std::string)
{
    using namespace BenchmarkFreshStartSeed;
    ++totals.names;
    if (state.pending) {
        state.names_before_seed=totals.names;
        state.unclassified_names_before_seed=totals.names-totals.utility_name_calls;
        state.intervening_names_after_arm=totals.names-state.names_before_arm;
    }
    if (state.applied) ++state.names_after_seed;
    if (state.in_open) ++state.names_during_open;
    std::string value=super(isMale_ret);
    if (totals.utility_scope_active) {
        ++totals.utility_name_calls;
        if (totals.utility_name_calls!=1) totals.utility_lookup_valid=false;
        totals.utility_name=value;
    }
    return value;
}

HOOK_METHOD_PRIORITY(ShipManager, OnInit, -1000000, (ShipBlueprint* blueprint,int ship_level) -> int)
{
    using namespace BenchmarkFreshStartSeed;
    ++totals.ship_inits;
    if (state.pending) state.ship_inits_before_seed=totals.ship_inits;
    if (state.applied) ++state.ship_inits_after_seed;
    if (state.in_open) ++state.ship_inits_during_open;
    return super(blueprint,ship_level);
}

HOOK_METHOD_PRIORITY(MainMenu, constructor, -1000000, () -> void)
{
    using namespace BenchmarkFreshStartSeed;
    const unsigned long long before=totals.names;
    ++totals.main_menu_constructors;super();
    totals.names_in_main_menu_constructor+=totals.names-before;
}

HOOK_METHOD_PRIORITY(ShipBuilder, constructor, -1000000, () -> void)
{
    using namespace BenchmarkFreshStartSeed;
    const unsigned long long before=totals.names;
    ++totals.ship_builder_constructors;super();
    totals.names_in_ship_builder_constructor+=totals.names-before;
}
}
