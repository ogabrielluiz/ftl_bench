#include "../include/Benchmark_Visual.h"
#include <fstream>
#include <iostream>
#define CHECK(value) do { if (!(value)) { std::cerr << "failed: " #value "\n"; return 1; } } while (0)
struct Point { int x,y; };
struct Window {
    bool bOpen=false;
    Point hover={-1,-1};
    int refreshes=0;
    void MouseMove(int x,int y) { hover={x,y}; ++refreshes; }
};
struct DeferredApp {
    Window langChooser,menu,game;
    Window* gui=&game;
    Point cursor={-1,-1},pressed={-1,-1},released={-1,-1};
    int downs=0,ups=0,motions=0,wrong_hover=0;
    Point TranslateMouse(int x,int y) { return {(x-20)/2,(y-10)/2}; }
    void OnMouseMove(int x,int y,int,int,bool,bool,bool) {
        cursor=TranslateMouse(x,y); ++motions;
        if (langChooser.bOpen) langChooser.MouseMove(cursor.x,cursor.y);
        // Deliberately defer menu/game hover, exactly like CApp.
    }
    void down(int x,int y) {
        Window& active=menu.bOpen?menu:game;
        pressed=TranslateMouse(x,y); ++downs;
        if (active.hover.x!=pressed.x || active.hover.y!=pressed.y) ++wrong_hover;
    }
    void up(int x,int y) { released=TranslateMouse(x,y); ++ups; }
    void OnLButtonDown(int x,int y) { down(x,y); }
    void OnLButtonUp(int x,int y) { up(x,y); }
    void OnRButtonDown(int x,int y) { down(x,y); }
    void OnRButtonUp(int x,int y) { up(x,y); }
};
int main(int argc, char** argv)
{
    using namespace BenchmarkVisual;
    FrameClock clock;
    clock.begin_frame();
    CHECK(clock.update_permitted() && clock.render_permitted()); // historical mode
    clock.control(true,false);
    CHECK(!clock.update_permitted() && !clock.render_permitted());
    clock.begin_frame(); clock.completed_world_update();
    CHECK(clock.world_updates==0 && !clock.update_permitted());
    clock.control(true,true); // budget starts after the current native world phase
    CHECK(!clock.update_permitted() && !clock.render_permitted());
    clock.begin_frame();
    CHECK(clock.update_permitted() && !clock.render_permitted());
    clock.completed_world_update(); clock.completed_world_update();
    CHECK(clock.world_updates==1 && clock.render_permitted()); // counted once per frame
    struct FPS { float SpeedFactor; } fps={0.01f};
    apply_fixed_frame_speed(fps,clock);
    CHECK(fps.SpeedFactor==16.f/60.f);
    clock.control(true,false); // last budget frame's Lua tick precedes rendering
    CHECK(clock.update_permitted() && clock.render_permitted());
    clock.finish_render();
    CHECK(!clock.render_permitted());
    clock.begin_frame(); clock.completed_world_update();
    CHECK(!clock.update_permitted() && clock.world_updates==1);
    fps.SpeedFactor=0.4f; apply_fixed_frame_speed(fps,clock);
    CHECK(fps.SpeedFactor==0.4f); // ambient UI retains the native wall factor
    clock.control(false,false);
    CHECK(clock.update_permitted() && clock.render_permitted());
    CHECK(choice_queued(true,0,1));
    CHECK(!choice_queued(true,-1,1) && !choice_queued(true,1,1) && !choice_queued(false,0,1));
    ExternalInputGuard external;
    external.observe(true,false); // normal setup before the first capture
    CHECK(external.generation==0 && !external.detected);
    external.arm(0.25f,0.75f);
    external.observe(false,true,0.25f,0.75f); // stationary physical reports
    CHECK(external.generation==0 && !external.detected);
    try {
        SyntheticInputScope first(external);
        SyntheticInputScope nested(external);
        external.observe(true,false); // synthetic buttons/keys
        external.observe(false,true,0.9f,0.1f); // synthetic cursor is NOT physical
        CHECK(external.generation==0 && external.mouse_x==0.25f);
        throw 1;
    } catch (int) {}
    CHECK(external.synthetic_depth==0);
    external.observe(false,false); // memory/device bookkeeping
    external.observe(false,true,0.25f,0.75f); // same physical cursor after synthetic move
    CHECK(external.generation==0);
    external.observe(false,true,0.3f,0.75f); // first real movement is detected
    CHECK(external.generation==1 && external.detected);
    external.observe(false,true,0.3f,0.75f);
    CHECK(external.generation==1); // stationary repeats do not contaminate again
    external.observe(true,false); // a real keyboard/button/scroll/text/touch event
    CHECK(external.generation==2);
    external.arm(0.8f,0.2f); // recapturing cannot clear contamination or rebaseline
    CHECK(external.generation==2 && external.detected && external.mouse_x==0.3f);
    CHECK(point_valid(1279,719,1280,720));
    CHECK(!point_valid(1280,719,1280,720));
    CHECK(!point_valid(-1,0,1280,720));
    CHECK(!point_valid(0,0,0,720));
    DeferredApp game;
    mouse_click(game,198,682,1);
    CHECK(game.wrong_hover==0 && game.downs==1 && game.ups==1);
    CHECK(game.game.hover.x==89 && game.game.hover.y==336); // native client transform once
    mouse_drag(game,100,100,340,220,0);
    CHECK(game.wrong_hover==0 && game.downs==2 && game.ups==2 && game.motions>3);
    CHECK(game.game.hover.x==160 && game.game.hover.y==105);
    CHECK(game.released.x==160 && game.released.y==105);
    game.menu.bOpen=true;
    mouse_click(game,120,90,0);
    CHECK(game.wrong_hover==0 && game.menu.hover.x==50 && game.menu.hover.y==40);
    const int old_menu_refreshes=game.menu.refreshes;
    game.langChooser.bOpen=true;
    mouse_move(game,200,100);
    CHECK(game.langChooser.refreshes==1 && game.langChooser.hover.x==90);
    CHECK(game.menu.refreshes==old_menu_refreshes); // no hover on a covered menu
    CHECK(modifiers_valid(3) && !modifiers_valid(4));
    struct Input { bool shift_held=false,lCtrl=true; } input;
    int injected=-1;
    try {
        ModifierScope<Input> held(input,injected,1);
        CHECK(input.shift_held && !input.lCtrl && injected==1);
        CHECK(polled_key_state(injected,0x4b,0)==1);
        CHECK(polled_key_state(injected,0x4c,0)==1);
        CHECK(polled_key_state(injected,0x4d,1)==0);
        CHECK(polled_key_state(injected,0x20,1)==1);
        throw 1;
    } catch (int) {}
    CHECK(!input.shift_held && input.lCtrl && injected==-1);
    CHECK(polled_key_state(-1,0x4b,0)==0 && polled_key_state(-1,0x4d,1)==1);
    CHECK(key_code("space") == 32 && key_code("f12") == 0x125);
    CHECK(key_code("shift") == -1 && key_code("alt") == -1 && key_code("A") == -1);
    CHECK(key_code(";") == 59);
    CHECK(png({},2,2).empty());
    // Bottom row blue/white, top row red/green. Decode externally to catch an
    // upside-down capture, channel swap, bad checksum, or malformed zlib stream.
    std::vector<unsigned char> rgba = {0,0,255,255, 255,255,255,255,
                                      255,0,0,255, 0,255,0,255};
    const auto image = png(rgba,2,2);
    CHECK(image.size() > 60);
    if (argc > 1) { std::ofstream file(argv[1],std::ios::binary); file.write(reinterpret_cast<const char*>(image.data()),image.size()); CHECK(file.good()); }
    // Exercise multiple stored DEFLATE blocks, not just tiny screenshots.
    CHECK(!png(std::vector<unsigned char>(1280*720*4,255),1280,720).empty());
    std::cout << "visual helper checks passed\n";
}
