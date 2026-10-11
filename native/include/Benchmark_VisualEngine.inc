// Included in Benchmark_Extend.cpp after the existing observation transport.
// The SIL functions are the game's backend-neutral renderer API, used by both
// D3D11 and OpenGL. Reading before finish_frame captures the current client frame.
#if defined(_WIN32) && defined(__i386__)
namespace BenchmarkVisualEngine {
    void* read_pixels_address = nullptr;
    void* width_address = nullptr;
    void* height_address = nullptr;
    void* finish_address = nullptr;
    void* key_state_address = nullptr;
    void* mouse_position_address = nullptr;
    const short read_args[] = {0x1ff,0x1ff,0x1ff,0x1ff,0x1ff};
    ZHL::FunctionDefinition read_def("benchmark_graphics_read_pixels", typeid(int (*)(int,int,int,int,void*)),
        "5589e557565383e4f083ec208b45188b55088b4d0c8b5d1085c0", read_args,5,2,&read_pixels_address);
    ZHL::FunctionDefinition width_def("benchmark_graphics_width", typeid(int (*)()),
        "a1????????c38d76008dbc2700000000a1????????c38d76008dbc27000000005589e583e4f083ec30", nullptr,0,2,&width_address);
    ZHL::FunctionDefinition height_def("benchmark_graphics_height", typeid(int (*)()),
        "a1????????c38d76008dbc27000000005589e583e4f083ec308d44242cc744242800000000", nullptr,0,2,&height_address);
    ZHL::FunctionDefinition finish_def("benchmark_graphics_finish_frame", typeid(void (*)()),
        "5589e583e4f0e8????????c9c38d76005589e583e4f083ec10c7042400000000", nullptr,0,6,&finish_address);
    const short key_args[] = {0x1ff};
    ZHL::FunctionDefinition key_def("benchmark_input_key_state", typeid(int (*)(int)),
        "31c0803d????????0074168b4c24048d51ff81fa9000000077070fb681????????f3c3", key_args,1,2,&key_state_address);
    const short mouse_position_args[] = {0x1ff,0x1ff};
    ZHL::FunctionDefinition mouse_position_def("benchmark_input_mouse_position", typeid(void (*)(float*,float*)),
        "8b5424048b44240885d2740cf30f1005????????f30f110285c0740cf30f1005????????f30f1100f3c3", mouse_position_args,2,6,&mouse_position_address);
    BenchmarkVisual::ExternalInputGuard external_input;
    BenchmarkVisual::FrameClock frame_clock;
    bool in_render = false;
    unsigned long long render_frame = 0;
    unsigned long long capture_counter = 0;
    const unsigned long long session_id = []() -> unsigned long long {
        FILETIME time;
        GetSystemTimeAsFileTime(&time);
        return (static_cast<unsigned long long>(time.dwHighDateTime) << 32) | time.dwLowDateTime;
    }();
    int injected_modifiers = -1;
    bool available() { return read_pixels_address && width_address && height_address && finish_address && key_state_address && mouse_position_address; }
    int width() { return available() ? reinterpret_cast<int (*)()>(width_address)() : 0; }
    int height() { return available() ? reinterpret_cast<int (*)()>(height_address)() : 0; }
    bool point(int x,int y) { return BenchmarkVisual::point_valid(x,y,width(),height()); }
    CApp* input_app()
    {
        CApp* app = Global::GetInstance()->GetCApp();
        return available() && app && app->gui && !app->minimized ? app : nullptr;
    }
    void clear_pointer_tooltip()
    {
        MouseControl* mouse=Global::GetInstance()->GetMouseControl();
        if (mouse) BenchmarkVisual::clear_pointer_tooltip(*mouse);
    }
    void refresh_pointer_hover(CApp* app)
    {
        MouseControl* mouse=Global::GetInstance()->GetMouseControl();
        if (!app || !mouse) return;
        clear_pointer_tooltip();
        // Keyboard handlers may change the active window without moving the
        // cursor. Recompute normal hover at its already-translated GUI point;
        // preserve native tooltip delay and do not synthesize a mouse event.
        const Point position=mouse->position;
        if (app->langChooser.bOpen) app->langChooser.MouseMove(position.x,position.y);
        else if (app->menu.bOpen) app->menu.MouseMove(position.x,position.y);
        else if (app->gui) app->gui->MouseMove(position.x,position.y);
    }
    void refresh_idle_map_ui(CApp* app)
    {
        if (!frame_clock.owned || frame_clock.advancing || !app || !app->gui || !app->world ||
            !app->world->bStartedGame || app->gui->gameover || app->gui->alreadyWon) return;
        CompleteShip* ship=app->world->playerShip;
        if (!ship || !ship->shipManager || ship->shipManager->bJumping) return;
        StarMap& map=app->world->starMap;
        if (!map.bOpen || map.bChoosingNewSector || map.readyToTravel ||
            map.waiting.running || map.potentialLoc) return;
        // CustomMap::OnLoop owns the native fuel mode and active-button cache.
        // With sector/travel/wait work excluded, this is an ordinary UI refresh;
        // no sector commit, UpdateDangerZone or world update can run here.
        map.OnLoop();
    }
    // Scoped cached input bits plus the normal SIL poll cover native callbacks
    // without leaving held keys behind or changing physical keyboard state.
    using ModifierScope = BenchmarkVisual::ModifierScope<CApp>;
}

// Native pause still runs PauseLoop/GUI travel commits. Keep those world paths
// frozen while retaining CApp input, render, and its post-loop Lua controller.
HOOK_METHOD_PRIORITY(CApp, OnLoop, 99999, () -> void)
{
    BenchmarkVisualEngine::frame_clock.begin_frame();
    super();
}
HOOK_METHOD_PRIORITY(CFPS, OnLoop, 99999, () -> void)
{
    // FTL 1.6.9 CApp::OnLoop calls this before WorldManager and CommandGui.
    // Keep native wall-time bookkeeping and ambient UI timing, then replace
    // only the permitted benchmark frame's base simulation factor. The value
    // survives its render, including jump trackers; the next native OnLoop
    // recomputes ordinary timing. Gameplay GetSpeedFactor multipliers remain
    // in their existing hook chain, and local temporary field scales remain.
    super();
    if (this==Global::GetInstance()->GetCFPS())
        BenchmarkVisual::apply_fixed_frame_speed(*this,BenchmarkVisualEngine::frame_clock);
}
HOOK_METHOD_PRIORITY(WorldManager, OnLoop, 99999, () -> void)
{
    auto& clock=BenchmarkVisualEngine::frame_clock;
    CApp* app=Global::GetInstance()->GetCApp();
    const bool current=app && app->world==this;
    if (current && !clock.update_permitted()) return;
    super();
    if (current) clock.completed_world_update();
}
HOOK_METHOD_PRIORITY(WorldManager, PauseLoop, 99999, () -> void)
{
    auto& clock=BenchmarkVisualEngine::frame_clock;
    CApp* app=Global::GetInstance()->GetCApp();
    const bool current=app && app->world==this;
    if (current && !clock.update_permitted()) return;
    super();
    if (current) clock.completed_world_update();
}
HOOK_METHOD_PRIORITY(CommandGui, OnLoop, 99999, () -> void)
{
    CApp* app=Global::GetInstance()->GetCApp();
    const bool current=app && app->gui==this;
    if (current && !BenchmarkVisualEngine::frame_clock.update_permitted()) {
        // CApp still resets and ages tooltips every UI frame. Replay only the
        // ordinary stationary hover after that reset, never GUI/world OnLoop.
        BenchmarkVisualEngine::refresh_pointer_hover(app);
        return;
    }
    super();
}
HOOK_METHOD_PRIORITY(AnimationTracker, Update, 99999, () -> void)
{
    if (!BenchmarkVisualEngine::frame_clock.render_permitted()) {
        CApp* app=Global::GetInstance()->GetCApp();
        if (app && app->world) {
            const auto is_jump=[this](CompleteShip* ship) {
                return ship && ship->shipManager && this==&ship->shipManager->jumpAnimation;
            };
            if (is_jump(app->world->playerShip)) return;
            for (CompleteShip* ship : app->world->ships) if (is_jump(ship)) return;
        }
    }
    super(); // all ordinary UI animation, including ChoiceBox openTime, continues
}

// Only the normal input-event boundary is observed. Synthetic primitives call
// CApp handlers directly and are additionally scoped for nested native dispatch.
HOOK_METHOD(CEvent, OnEvent, (const InputEvent* event) -> void)
{
    using namespace BenchmarkVisualEngine;
    CApp* app=Global::GetInstance()->GetCApp();
    if (event && app && this==static_cast<CEvent*>(app)) {
        bool meaningful=false,movement=false;
        float x=0.f,y=0.f;
        switch (event->type) {
        case INPUT_EVENT_MOUSE: {
            const auto* mouse=reinterpret_cast<const MouseInputEvent*>(&event->event);
            x=mouse->x; y=mouse->y;
            movement=event->detail==INPUT_MOUSE_MOVE;
            meaningful=(event->detail>=INPUT_MOUSE_LMB_DOWN && event->detail<=INPUT_MOUSE_RMB_UP) ||
                ((event->detail==INPUT_MOUSE_SCROLL_H || event->detail==INPUT_MOUSE_SCROLL_V) && mouse->scroll!=0.f);
            break;
        }
        case INPUT_EVENT_KEYBOARD:
        case INPUT_EVENT_TEXT:
        case INPUT_EVENT_TOUCH: meaningful=true; break;
        case INPUT_EVENT_JOYSTICK:
            meaningful=event->detail>=INPUT_JOYSTICK_BUTTON_DOWN && event->detail<=INPUT_JOYSTICK_STICK_CHANGE;
            break;
        default: break; // memory pressure and device connection are not input
        }
        external_input.observe(meaningful,movement,x,y);
    }
    super(event); // user input keeps its ordinary game behavior
}

HOOK_GLOBAL(benchmark_input_key_state, (int key) -> int)
{
    const int modifiers = BenchmarkVisualEngine::injected_modifiers;
    return BenchmarkVisual::polled_key_state(modifiers,key,super(key));
}

HOOK_GLOBAL(benchmark_graphics_finish_frame, () -> void)
{
    using namespace BenchmarkVisualEngine;
    ++render_frame;
    in_render = true;
    auto context = Global::GetInstance()->getLuaContext();
    if (context && context->GetLua()) {
        lua_State* lua = context->GetLua();
        const int top = lua_gettop(lua);
        lua_getglobal(lua,"ftl_bench_visual_render");
        if (lua_isfunction(lua,-1) && lua_pcall(lua,0,0,0) != 0)
            hs_log_file("[Benchmark] visual render callback failed: %s\n",lua_tostring(lua,-1));
        lua_settop(lua,top);
    }
    in_render = false;
    frame_clock.finish_render();
    super();
}
#endif

const char* hs_benchmark_visual_capabilities()
{
#if defined(_WIN32) && defined(__i386__)
    static std::string result;
    if (!BenchmarkVisualEngine::available()) return "{\"visual_io_version\":0,\"capture\":false,\"input\":false}";
    std::ostringstream json;
    json << "{\"visual_io_version\":1,\"capture\":true,\"input\":true,\"modifiers\":[\"shift\",\"ctrl\"],\"format\":\"png\",\"coordinate_space\":\"client\",\"width\":"
         << BenchmarkVisualEngine::width() << ",\"height\":" << BenchmarkVisualEngine::height()
         << ",\"visual_clock_version\":2,\"fixed_step_numerator\":1,\"fixed_step_denominator\":60,\"simulated_updates\":\""
         << BenchmarkVisualEngine::frame_clock.world_updates << "\",\"world_updates\":\"" << BenchmarkVisualEngine::frame_clock.world_updates
         << "\",\"external_input_guard\":true,\"external_input_generation\":\"" << BenchmarkVisualEngine::external_input.generation
         << "\",\"external_input_detected\":" << (BenchmarkVisualEngine::external_input.detected ? "true" : "false") << '}';
    result=json.str(); return result.c_str();
#else
    return "{\"visual_io_version\":0,\"capture\":false,\"input\":false}";
#endif
}

bool hs_benchmark_visual_set_clock(bool enabled,bool advancing)
{
#if defined(_WIN32) && defined(__i386__)
    if (!BenchmarkVisualEngine::available()) return false;
    BenchmarkVisualEngine::frame_clock.control(enabled,advancing);
    return true;
#else
    return false;
#endif
}

namespace {
const char* visual_blocked_reason(CApp* app)
{
    if (!app || !app->gui || !app->world || !app->world->bStartedGame) return "no_game";
    CommandGui& gui = *app->gui;
    StarMap& map = app->world->starMap;
    const bool jumping=app->world->playerShip && app->world->playerShip->shipManager &&
        app->world->playerShip->shipManager->bJumping;
    // Native clicks queue sector selection and fuel waiting before OnLoop
    // commits them. Permit only those accepted map operations, not an idle map.
    const int sector=map.finalSectorChoice;
    const bool queued_sector=map.bOpen && map.bChoosingNewSector && map.currentSector &&
        sector>=0 && static_cast<size_t>(sector)<map.sectors.size() &&
        map.sectors[sector] && map.NeighboringSector(sector);
    const bool map_progress=map.readyToTravel || jumping || queued_sector || map.waiting.running;
    const bool queued_choice=BenchmarkVisual::choice_queued(gui.choiceBoxOpen || gui.choiceBox.bOpen,
        gui.choiceBox.selectedChoice,gui.choiceBox.choices.size());
    if (gui.gameover || gui.alreadyWon) return "terminal";
    // RenderStatic skips regular choice/focus windows while the ship is jumping.
    // A staged arrival dialog must not stop its still-hidden reverse warp.
    if (!jumping && !queued_choice && (gui.choiceBoxOpen || gui.choiceBox.bOpen)) return "choice_open";
    if (gui.menuBox.bOpen) return "menu_open";
    if (gui.optionsBox.bOpen) return "options_open";
    if (gui.inputBox.bOpen) return "input_open";
    if (gui.gameOverScreen.bOpen) return "game_over_screen";
    if (gui.shipScreens.bOpen) return "ship_screen_open";
    if (!jumping && !queued_choice && gui.storeScreens.bOpen) return "store_open";
    if (gui.upgradeScreen.bOpen) return "upgrade_open";
    if (gui.crewScreen.bOpen) return "crew_screen_open";
    if (gui.equipScreen.bOpen) return "equipment_open";
    if (gui.leaveCrewDialog.bOpen) return "leave_crew_dialog";
    if (gui.writeErrorDialog.bOpen) return "write_error_dialog";
    if (map.bOpen && !map_progress) return "map_open";
    if (!jumping) {
        for (FocusWindow* window : gui.focusWindows)
            if (window && window->bOpen && !(window == &map && map_progress) &&
                !(window == &gui.choiceBox && queued_choice) &&
                !(window == &gui.storeScreens && queued_choice)) return "focus_window_open";
    }
    return "";
}
}

bool hs_benchmark_visual_simulation_blocked()
{
    return visual_blocked_reason(Global::GetInstance()->GetCApp())[0]!='\0';
}

bool hs_benchmark_mouse_move(int x,int y)
{
#if defined(_WIN32) && defined(__i386__)
    CApp* app = BenchmarkVisualEngine::input_app();
    if (!app || !BenchmarkVisualEngine::point(x,y)) return false;
    BenchmarkVisual::SyntheticInputScope synthetic(BenchmarkVisualEngine::external_input);
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    BenchmarkVisual::mouse_move(*app,x,y,0,0,false,false,BenchmarkVisualEngine::clear_pointer_tooltip);
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    return true;
#else
    return false;
#endif
}
bool hs_benchmark_mouse_click(int x,int y,int button,int modifiers)
{
#if defined(_WIN32) && defined(__i386__)
    CApp* app = BenchmarkVisualEngine::input_app();
    if (!app || !BenchmarkVisual::modifiers_valid(modifiers) || (button != 0 && button != 1) || !BenchmarkVisualEngine::point(x,y)) return false;
    BenchmarkVisual::SyntheticInputScope synthetic(BenchmarkVisualEngine::external_input);
    BenchmarkVisualEngine::ModifierScope held(*app,BenchmarkVisualEngine::injected_modifiers,modifiers);
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    BenchmarkVisual::mouse_click(*app,x,y,button,BenchmarkVisualEngine::clear_pointer_tooltip);
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    return true;
#else
    return false;
#endif
}
bool hs_benchmark_mouse_drag(int x,int y,int to_x,int to_y,int button,int modifiers)
{
#if defined(_WIN32) && defined(__i386__)
    CApp* app = BenchmarkVisualEngine::input_app();
    if (!app || !BenchmarkVisual::modifiers_valid(modifiers) || (button != 0 && button != 1) ||
        !BenchmarkVisualEngine::point(x,y) || !BenchmarkVisualEngine::point(to_x,to_y)) return false;
    BenchmarkVisual::SyntheticInputScope synthetic(BenchmarkVisualEngine::external_input);
    BenchmarkVisualEngine::ModifierScope held(*app,BenchmarkVisualEngine::injected_modifiers,modifiers);
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    BenchmarkVisual::mouse_drag(*app,x,y,to_x,to_y,button,BenchmarkVisualEngine::clear_pointer_tooltip);
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    return true;
#else
    return false;
#endif
}
bool hs_benchmark_key_press(const char* key,int modifiers)
{
#if defined(_WIN32) && defined(__i386__)
    CApp* app = BenchmarkVisualEngine::input_app();
    const int code = key ? BenchmarkVisual::key_code(key) : -1;
    if (!app || !BenchmarkVisual::modifiers_valid(modifiers) || code < 0) return false;
    BenchmarkVisual::SyntheticInputScope synthetic(BenchmarkVisualEngine::external_input);
    BenchmarkVisualEngine::ModifierScope held(*app,BenchmarkVisualEngine::injected_modifiers,modifiers);
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    app->OnKeyDown(static_cast<SDLKey>(code));
    app->OnKeyUp(static_cast<SDLKey>(code));
    BenchmarkVisualEngine::refresh_idle_map_ui(app);
    BenchmarkVisualEngine::refresh_pointer_hover(app);
    return true;
#else
    return false;
#endif
}

const char* hs_benchmark_write_visual_observation(const char* observation,int seq,int tick,
                                                int requested_frames,int actual_frames,const char* feedback)
{
    static std::string result;
    result.clear();
#if defined(_WIN32) && defined(__i386__)
    using namespace BenchmarkVisualEngine;
    CApp* app = Global::GetInstance()->GetCApp();
    if (!available() || !frame_clock.owned || frame_clock.advancing || !in_render || !app || !app->gui || !app->gui->bPaused || !observation || !feedback) return result.c_str();
    std::string json(observation);
    if (json.size() < 2 || json.front() != '{' || json.back() != '}' || requested_frames < 0 ||
        requested_frames > 600 || actual_frames < 0 || actual_frames > requested_frames) return result.c_str();
    const int w = width(), h = height();
    if (w <= 0 || h <= 0 || w > 8192 || h > 8192) return result.c_str();
    std::vector<unsigned char> pixels(static_cast<size_t>(w)*h*4);
    if (!reinterpret_cast<int (*)(int,int,int,int,void*)>(read_pixels_address)(0,0,w,h,pixels.data())) return result.c_str();
    const auto image = BenchmarkVisual::png(pixels,w,h);
    if (image.empty()) return result.c_str();
    std::ostringstream identity;
    identity << GetCurrentProcessId() << '-' << session_id << '-' << render_frame << '-' << ++capture_counter;
    const std::string id = identity.str(), name = "ftl_visual_"+id+".png";
    const std::string final_path = get_observation_dir()+name, temp_path = final_path+".tmp";
    {
        std::ofstream file(temp_path,std::ios::binary);
        if (!file.is_open()) return result.c_str();
        file.write(reinterpret_cast<const char*>(image.data()),image.size());
        file.flush();
        if (!file.good()) { file.close(); std::remove(temp_path.c_str()); return result.c_str(); }
    }
    if (std::rename(temp_path.c_str(),final_path.c_str()) != 0) { std::remove(temp_path.c_str()); return result.c_str(); }
    float physical_x=0.f,physical_y=0.f;
    reinterpret_cast<void (*)(float*,float*)>(mouse_position_address)(&physical_x,&physical_y);
    external_input.arm(physical_x,physical_y);
    std::ostringstream metadata;
    metadata << "{\"visual_io_version\":1,\"capture_id\":\"" << id << "\",\"frame_id\":\"" << GetCurrentProcessId()
      << '-' << session_id << '-' << render_frame << "\",\"action_seq\":" << seq << ",\"frame\":" << tick
      << ",\"render_frame\":" << render_frame << ",\"width\":" << w << ",\"height\":" << h
      << ",\"path\":\"" << name << "\",\"format\":\"png\",\"coordinate_space\":\"client\",\"paused\":true"
      << ",\"requested_frames\":" << requested_frames << ",\"actual_frames\":" << actual_frames
      << ",\"visual_clock_version\":2,\"fixed_step_numerator\":1,\"fixed_step_denominator\":60,\"simulated_updates\":\""
      << frame_clock.world_updates << "\",\"world_updates\":\"" << frame_clock.world_updates
      << "\",\"external_input_generation\":\"" << external_input.generation
      << "\",\"external_input_detected\":" << (external_input.detected ? "true" : "false")
      << ",\"input_feedback\":" << feedback << '}';
    std::ostringstream windows;
    windows << std::boolalpha << ",\"visual_evaluator\":{\"store_open\":" << app->gui->storeScreens.bOpen
      << ",\"map_open\":" << (app->world && app->world->starMap.bOpen)
      << ",\"choice_open\":" << app->gui->choiceBoxOpen
      << ",\"choice_window_open\":" << app->gui->choiceBox.bOpen
      << ",\"player_jumping\":" << (app->world && app->world->playerShip && app->world->playerShip->shipManager && app->world->playerShip->shipManager->bJumping)
      << ",\"simulation_blocked\":" << (visual_blocked_reason(app)[0]!='\0')
      << ",\"blocked_reason\":\"" << visual_blocked_reason(app) << "\"}";
    json.pop_back(); json += ",\"visual\":"+metadata.str()+windows.str()+"}";
    if (!hs_benchmark_write_observation(json.c_str())) { std::remove(final_path.c_str()); return result.c_str(); }
    result = metadata.str();
#endif
    return result.c_str();
}
