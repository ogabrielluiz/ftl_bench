#include "../include/Benchmark_Economy.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>

namespace {
struct TestPoint { int x, y; };
struct TestRect { int x, y, w, h; };
struct TestButton {
    explicit TestButton(TestRect rectangle) : hitbox(rectangle) {}
    TestRect hitbox;
    bool active = true, hover = false, state = false;
};

// Match the native StarMap contract: MouseMove subtracts map.position, then
// GenericButton tests its local hitbox. MouseClick consumes active + hover.
struct TestMap {
    TestPoint position{218, 93};
    TestButton wait{{24, 570, 91, 31}};
    TestButton distress{{210, 570, 91, 31}};
    bool waiting = false;

    void MouseMove(int x, int y)
    {
        x -= position.x;
        y -= position.y;
        for (auto button : {&wait, &distress}) {
            const auto& box = button->hitbox;
            button->hover = x > box.x && x < box.x + box.w &&
                            y > box.y && y < box.y + box.h;
        }
    }

    void MouseClick(int, int)
    {
        if (wait.active && wait.hover) waiting = true;
        if (distress.active && distress.hover) distress.state = !distress.state;
    }
};
}
int main()
{
    using namespace BenchmarkEconomy;
    const std::vector<int> shields{100, 20, 30, 40, 60, 80, 100, 120};
    const std::vector<int> weapons{40, 25, 35, 50, 75, 90, 100, 120};
    assert(system_cost(2, 8, shields) == 20);
    assert(system_cost(3, 8, shields) == 30);
    assert(system_cost(4, 8, weapons) == 50);
    assert(system_cost(8, 8, shields) == -1);
    assert(system_cost(0, 8, shields) == -1);
    assert(system_cost(4, 8, std::vector<int>{10}) == -1);
    assert(system_cost(1, 2, std::vector<int>{-1}) == -1);

    const std::vector<int> reactor{15, 30, -1, -1, -1, -1};
    assert(reactor_cost(4, 25, reactor, 5) == 30);
    assert(reactor_cost(5, 25, reactor, 5) == 20);
    assert(reactor_cost(24, 25, reactor, 5) == 35);
    assert(reactor_cost(25, 25, reactor, 5) == -1);
    assert(reactor_cost(30, 40, reactor, 5) == -1);
    assert(reactor_cost(30, 40, std::vector<int>{15, 30, -1, -1, -1, -1, -1, -1}, 5) == 45);
    assert(reactor_cost(10, 25, std::vector<int>{7, 11, 13, 17}, 9) == 17);
    assert(reactor_cost(2, 25, std::vector<int>{}, 5) == -1);

    Context context;
    assert(!context.ready());
    context.started = true;
    assert(context.ready());
    context.arrival_complete = true;
    assert(context.ready()); // A settled game keeps CommandGui.jumpComplete true.
    bool Context::* blockers[] = {&Context::main_menu, &Context::game_over,
        &Context::destroyed, &Context::mid_warp, &Context::pending_travel,
        &Context::pending_sector, &Context::waiting, &Context::modal};
    for (auto blocker : blockers) {
        context.*blocker = true;
        assert(!context.ready());
        context.*blocker = false;
        assert(context.ready());
    }

    TestMap wait_map;
    click_map_button(wait_map, wait_map.wait);
    assert(wait_map.waiting && wait_map.wait.hover && !wait_map.distress.state);
    TestMap distress_map;
    click_map_button(distress_map, distress_map.distress);
    assert(distress_map.distress.state && distress_map.distress.hover && !distress_map.waiting);
    click_map_button(distress_map, distress_map.distress);
    assert(!distress_map.distress.state);
    wait_map.wait.active = false;
    wait_map.waiting = false;
    click_map_button(wait_map, wait_map.wait);
    assert(!wait_map.waiting);
    int level = 2, scrap = 40, upgrade_calls = 0, spend_calls = 0;
    auto get_level = [&]() { return level; };
    auto upgrade = [&]() { ++upgrade_calls; ++level; };
    auto spend = [&](int cost) { ++spend_calls; scrap -= cost; };
    assert(!purchase(false, 20, scrap, get_level, upgrade, spend));
    assert(!purchase(true, -1, scrap, get_level, upgrade, spend));
    assert(!purchase(true, 50, scrap, get_level, upgrade, spend));
    assert(upgrade_calls == 0 && spend_calls == 0 && level == 2 && scrap == 40);
    assert(!purchase(true, 20, scrap, get_level, [&]() { ++upgrade_calls; }, spend));
    assert(upgrade_calls == 1 && spend_calls == 0 && level == 2 && scrap == 40);
    assert(purchase(true, 20, scrap, get_level, upgrade, spend));
    assert(level == 3 && scrap == 20 && spend_calls == 1);
    assert(!purchase(true, 30, scrap, get_level, upgrade, spend));
    assert(level == 3 && scrap == 20 && spend_calls == 1);
    std::cout << "native economy price, context and transaction checks passed\n";
}
