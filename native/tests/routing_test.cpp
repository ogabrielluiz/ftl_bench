#include "../include/Benchmark_Routing.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <cstring>

int main()
{
    int random_calls = 0, checked = 0;
    auto random = [&]() { ++random_calls; return 0u; };
    auto later_neighbors = [&](int index) {
        assert(index >= 0 && index < 9);
        ++checked;
        return index == 4 || index == 7;
    };
    assert(BenchmarkRouting::choose_sector_index(9, later_neighbors, random) == 4);
    assert(checked == 9 && random_calls == 1);
    assert(BenchmarkRouting::choose_sector_index(9, later_neighbors, []() { return 1u; }) == 7);
    assert(BenchmarkRouting::choose_sector_index(9, later_neighbors, []() { return 2u; }) == 4);
    checked = random_calls = 0;
    auto none = [&](int index) { assert(index >= 0 && index < 9); ++checked; return false; };
    assert(BenchmarkRouting::choose_sector_index(9, none, random) == -1);
    assert(checked == 9 && random_calls == 0);
    assert(BenchmarkRouting::choose_sector_index(0, none, random) == -1);
    assert(random_calls == 0);
    assert(BenchmarkRouting::choose_sector_index(2, [](int index) { return index == 1; },
                                                []() { return 0xffffffffu; }) == 1);
    BenchmarkRouting::TravelContext context;
    context.game.started = true;
    context.button_active = context.engines = context.piloting = true;
    context.fuel = 2;
    context.charge = context.required_charge = 85.f;
    int target = 1, travel_calls = 0;
    std::vector<int*> neighbors{&target};
    auto travel = [&](int* location) { assert(location == &target); ++travel_calls; };
    auto refused = [&](const char* reason) {
        assert(std::strcmp(context.refusal_reason(), reason) == 0);
        assert(!BenchmarkRouting::request_beacon(context, 0, neighbors, travel));
        assert(travel_calls == 0);
    };
    // Real v5 post-kill snapshots bypassed the UI at these three charge values.
    for (float charge : {41.5675f, 62.0388f, 40.4834f, 0.f}) {
        context.charge = charge;
        refused("drive_charging"); // also no-enemy/out-of-combat: no instant charge
    }
    context.charge = 85.f;
    context.enemy_defeat_pending = true;
    // Pending loot is guidance, not an invented travel prerequisite: native UI
    // permits a charged jump, including the v5 fourth post-kill snapshot.
    assert(context.refusal_reason() == nullptr);
    context.enemy_defeat_pending = false;
    assert(BenchmarkRouting::hull_defeat_pending(true, false, false));
    assert(BenchmarkRouting::hull_defeat_pending(true, true, false));
    assert(!BenchmarkRouting::hull_defeat_pending(true, true, true));
    assert(!BenchmarkRouting::hull_defeat_pending(false, false, false));
    assert(BenchmarkRouting::crew_defeat_pending(true, false, 0, 0, false));
    assert(BenchmarkRouting::crew_defeat_pending(true, false, 1, 1, false));
    assert(!BenchmarkRouting::crew_defeat_pending(true, false, 1, 1, true));
    assert(!BenchmarkRouting::crew_defeat_pending(true, true, 0, 0, false));
    assert(!BenchmarkRouting::crew_defeat_pending(false, false, 0, 0, false));
    // A living surrendered pointer is retained but no longer in native combat.
    assert(!BenchmarkRouting::sector_enemy_blocks(false, false));
    assert(BenchmarkRouting::sector_enemy_blocks(true, false));
    assert(!BenchmarkRouting::sector_enemy_blocks(true, true));
    assert(!BenchmarkRouting::sector_enemy_blocks(false, true));
    context.fuel = 0; refused("no_fuel"); context.fuel = 2;
    context.button_active = false; refused("ftl_button_inactive"); context.button_active = true;
    context.engines = false; refused("engines_unavailable"); context.engines = true;
    context.piloting = false; refused("piloting_unavailable"); context.piloting = true;
    context.game.modal = true; refused("modal_open"); context.game.modal = false;
    context.game.mid_warp = true; refused("mid_warp"); context.game.mid_warp = false;
    context.game.pending_travel = true; refused("transition_pending"); context.game.pending_travel = false;
    context.game.pending_sector = true; refused("transition_pending"); context.game.pending_sector = false;
    context.game.waiting = true; refused("fuel_wait_pending"); context.game.waiting = false;
    context.game.main_menu = true; refused("game_unavailable"); context.game.main_menu = false;
    context.game.game_over = true; refused("game_over"); context.game.game_over = false;
    assert(!BenchmarkRouting::request_beacon(context, -1, neighbors, travel));
    assert(!BenchmarkRouting::request_beacon(context, 1, neighbors, travel));
    neighbors[0] = nullptr;
    assert(!BenchmarkRouting::request_beacon(context, 0, neighbors, travel));
    neighbors.clear();
    assert(!BenchmarkRouting::request_beacon(context, 0, neighbors, travel));
    assert(travel_calls == 0);
    neighbors.push_back(&target);
    assert(BenchmarkRouting::request_beacon(context, 0, neighbors, travel));
    assert(travel_calls == 1);
    std::cout << "native sector routing indices and unavailable-route checks passed\n";
}
