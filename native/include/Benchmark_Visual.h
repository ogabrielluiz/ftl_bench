#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

// Pure helpers shared by the engine binding and executable offline regressions.
namespace BenchmarkVisual {
// Native world time is owned explicitly by the visual controller. The permit
// survives the post-world Lua tick through that frame's render: ship rendering
// also advances jump trackers. Ambient renders never gain a world permit.
struct FrameClock {
    // Each admitted update represents one declared 1/60 second step. FTL's
    // conventional duration conversions multiply SpeedFactor by 1/16.
    static float fixed_speed_factor() { return 16.f / 60.f; }
    bool owned=false,advancing=false,frame_permitted=false,world_updated=false;
    uint64_t world_updates=0;
    void control(bool enabled,bool advance) {
        if (!enabled) { owned=false; advancing=false; frame_permitted=false; world_updated=false; return; }
        if (!owned) { frame_permitted=false; world_updated=false; }
        owned=true; advancing=advance;
    }
    void begin_frame() { frame_permitted=!owned || advancing; world_updated=false; }
    bool update_permitted() const { return !owned || frame_permitted; }
    void completed_world_update() {
        if (owned && frame_permitted && !world_updated) { ++world_updates; world_updated=true; }
    }
    bool render_permitted() const { return !owned || (frame_permitted && world_updated); }
    void finish_render() { frame_permitted=false; world_updated=false; }
};
template <typename FPS>
inline void apply_fixed_frame_speed(FPS& fps, const FrameClock& clock) {
    if (clock.owned && clock.frame_permitted) fps.SpeedFactor=FrameClock::fixed_speed_factor();
}
inline bool choice_queued(bool open,int selected,size_t choices) {
    return open && selected>=0 && static_cast<size_t>(selected)<choices;
}
// A process-lifetime monitor armed by the first visual capture. Recapturing
// never erases interference. Coordinates are the physical SIL mouse position,
// independent of the cursor moved by synthetic CApp input.
struct ExternalInputGuard {
    uint64_t generation=0;
    unsigned synthetic_depth=0;
    bool armed=false,detected=false;
    float mouse_x=0.f,mouse_y=0.f;
    void arm(float x,float y) {
        if (armed) return;
        mouse_x=x; mouse_y=y; armed=true;
    }
    void observe(bool meaningful,bool movement,float x=0.f,float y=0.f) {
        if (synthetic_depth) return;
        const bool changed=movement && (x!=mouse_x || y!=mouse_y);
        if (movement) { mouse_x=x; mouse_y=y; }
        if (!armed || !(meaningful || changed)) return;
        ++generation; detected=true;
    }
};
struct SyntheticInputScope {
    ExternalInputGuard& guard;
    explicit SyntheticInputScope(ExternalInputGuard& value) : guard(value) { ++guard.synthetic_depth; }
    ~SyntheticInputScope() { --guard.synthetic_depth; }
    SyntheticInputScope(const SyntheticInputScope&)=delete;
    SyntheticInputScope& operator=(const SyntheticInputScope&)=delete;
};
inline bool point_valid(int x, int y, int width, int height)
{
    return width > 0 && height > 0 && x >= 0 && y >= 0 && x < width && y < height;
}
inline bool modifiers_valid(int modifiers) { return modifiers >= 0 && modifiers <= 3; }
// Native CApp clears these tooltip display fields once before its UI loop.
// A synthetic batch can visit several controls after that loop, so clear only
// the display cache before recomputing each point's hover. Preserve armed
// targeting, drag/cursor state and the normal tooltip delay/history.
template<class Mouse> void clear_pointer_tooltip(Mouse& mouse)
{
    mouse.tooltip.clear();
    mouse.tooltipTitle.clear();
    mouse.bForceTooltip=false;
    mouse.overrideTooltipWidth=-1;
    mouse.staticTooltip.x=-1;
    mouse.staticTooltip.y=-1;
}
// CApp::OnMouseMove updates the native cursor; GUI hover is normally deferred
// until a later UI loop. A click primitive must refresh the same normal hover
// handler before Down/Up, without running simulation or changing hover bits.
template<class App> void mouse_move(App& app,int x,int y,int dx=0,int dy=0,bool left=false,bool right=false,
                                   void (*before_hover)()=nullptr)
{
    if (before_hover) before_hover();
    app.OnMouseMove(x,y,dx,dy,left,right,false);
    const auto position=app.TranslateMouse(x,y);
    if (app.langChooser.bOpen) return; // CApp already forwards this active window
    if (app.menu.bOpen) app.menu.MouseMove(position.x,position.y);
    else if (app.gui) app.gui->MouseMove(position.x,position.y);
}
template<class App> void mouse_click(App& app,int x,int y,int button,void (*before_hover)()=nullptr)
{
    mouse_move(app,x,y,0,0,false,false,before_hover);
    if (button==0) { app.OnLButtonDown(x,y); app.OnLButtonUp(x,y); }
    else { app.OnRButtonDown(x,y); app.OnRButtonUp(x,y); }
}
template<class App> void mouse_drag(App& app,int x,int y,int to_x,int to_y,int button,void (*before_hover)()=nullptr)
{
    mouse_move(app,x,y,0,0,false,false,before_hover);
    if (button==0) app.OnLButtonDown(x,y); else app.OnRButtonDown(x,y);
    const int steps=std::max(1,std::min(64,std::max(std::abs(to_x-x),std::abs(to_y-y))/12+1));
    int previous_x=x,previous_y=y;
    for (int i=1;i<=steps;++i) {
        const int next_x=x+(to_x-x)*i/steps,next_y=y+(to_y-y)*i/steps;
        mouse_move(app,next_x,next_y,next_x-previous_x,next_y-previous_y,button==0,button==1,before_hover);
        previous_x=next_x; previous_y=next_y;
    }
    if (button==0) app.OnLButtonUp(to_x,to_y); else app.OnRButtonUp(to_x,to_y);
}
inline int polled_key_state(int modifiers,int key,int physical)
{
    if (modifiers >= 0) {
        if (key == 0x4b || key == 0x4c) return (modifiers & 1) != 0;
        if (key == 0x4d || key == 0x4e) return (modifiers & 2) != 0;
    }
    return physical;
}
template<class App> struct ModifierScope {
    App& app;
    int& injected;
    bool shift, ctrl;
    int previous;
    ModifierScope(App& target,int& state,int modifiers) : app(target),injected(state),
        shift(target.shift_held),ctrl(target.lCtrl),previous(state)
    {
        injected=modifiers; app.shift_held=(modifiers&1)!=0; app.lCtrl=(modifiers&2)!=0;
    }
    ~ModifierScope() { app.shift_held=shift; app.lCtrl=ctrl; injected=previous; }
};
inline int key_code(const std::string& key)
{
    if (key.size() == 1 && ((key[0] >= 'a' && key[0] <= 'z') ||
        (key[0] >= '0' && key[0] <= '9') || std::strchr("`-=[]\\;',./", key[0]))) return key[0];
    struct Key { const char* name; int code; };
    const Key keys[] = {{"space",32},{"escape",27},{"enter",13},{"tab",9},
        {"backspace",8},{"delete",127},{"up",0x111},{"down",0x112},
        {"right",0x113},{"left",0x114},{"insert",0x115},{"home",0x116},
        {"end",0x117},{"pageup",0x118},{"pagedown",0x119},
        {"f1",0x11a},{"f2",0x11b},{"f3",0x11c},{"f4",0x11d},
        {"f5",0x11e},{"f6",0x11f},{"f7",0x120},{"f8",0x121},
        {"f9",0x122},{"f10",0x123},{"f11",0x124},{"f12",0x125}};
    for (const auto& entry : keys) if (key == entry.name) return entry.code;
    return -1;
}
inline void be32(std::vector<unsigned char>& out, uint32_t value)
{
    for (int shift = 24; shift >= 0; shift -= 8) out.push_back((value >> shift) & 255);
}
inline uint32_t crc32(const unsigned char* data, size_t size)
{
    uint32_t crc = 0xffffffff;
    for (size_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1)));
    }
    return ~crc;
}
inline void chunk(std::vector<unsigned char>& out, const char* type, const std::vector<unsigned char>& data)
{
    be32(out, static_cast<uint32_t>(data.size()));
    const size_t begin = out.size();
    out.insert(out.end(), type, type + 4);
    out.insert(out.end(), data.begin(), data.end());
    be32(out, crc32(out.data() + begin, out.size() - begin));
}
// SIL readback is bottom-to-top RGBA8. PNG is top-to-bottom RGB8. Stored DEFLATE
// blocks avoid backend/codec dependencies and preserve every rendered pixel.
inline std::vector<unsigned char> png(const std::vector<unsigned char>& rgba, int width, int height)
{
    if (width <= 0 || height <= 0 || width > 8192 || height > 8192 ||
        rgba.size() != static_cast<size_t>(width) * height * 4) return {};
    std::vector<unsigned char> raw;
    raw.reserve(static_cast<size_t>(width * 3 + 1) * height);
    for (int y = height - 1; y >= 0; --y) {
        raw.push_back(0); // PNG filter None
        for (int x = 0; x < width; ++x) {
            const size_t offset = (static_cast<size_t>(y) * width + x) * 4;
            raw.insert(raw.end(), rgba.begin() + offset, rgba.begin() + offset + 3);
        }
    }
    std::vector<unsigned char> compressed = {0x78, 0x01};
    for (size_t offset = 0; offset < raw.size();) {
        const unsigned length = static_cast<unsigned>(std::min<size_t>(65535, raw.size() - offset));
        compressed.push_back(offset + length == raw.size() ? 1 : 0);
        compressed.push_back(length & 255); compressed.push_back(length >> 8);
        compressed.push_back((~length) & 255); compressed.push_back(((~length) >> 8) & 255);
        compressed.insert(compressed.end(), raw.begin() + offset, raw.begin() + offset + length);
        offset += length;
    }
    uint32_t a = 1, b = 0;
    for (const auto byte : raw) { a = (a + byte) % 65521; b = (b + a) % 65521; }
    be32(compressed, (b << 16) | a);
    std::vector<unsigned char> out = {137,80,78,71,13,10,26,10};
    std::vector<unsigned char> header;
    be32(header, width); be32(header, height);
    header.insert(header.end(), {8,2,0,0,0});
    chunk(out, "IHDR", header); chunk(out, "IDAT", compressed); chunk(out, "IEND", {});
    return out;
}
} // namespace BenchmarkVisual
