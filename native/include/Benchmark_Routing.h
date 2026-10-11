#pragma once
#include "Benchmark_Economy.h"
#include <vector>

namespace BenchmarkRouting {
// FTLButton::MouseClick and CommandGui::LButtonDown both require a full native
// timer, including outside combat. Never substitute enemy absence/death for it.
struct TravelContext {
    BenchmarkEconomy::Context game;
    bool button_active = false;
    bool engines = false;
    bool piloting = false;
    bool enemy_defeat_pending = false;
    int fuel = 0;
    float charge = 0.f;
    float required_charge = 0.f;

    const char* refusal_reason() const
    {
        if (!game.started || game.main_menu) return "game_unavailable";
        if (game.game_over || game.destroyed) return "game_over";
        if (game.mid_warp) return "mid_warp";
        if (game.pending_travel || game.pending_sector) return "transition_pending";
        if (game.waiting) return "fuel_wait_pending";
        if (game.modal) return "modal_open";
        if (fuel < 1) return "no_fuel";
        if (!button_active) return "ftl_button_inactive";
        if (!engines) return "engines_unavailable";
        if (!piloting) return "piloting_unavailable";
        if (!(charge >= required_charge)) return "drive_charging";
        return nullptr;
    }
};

inline bool hull_defeat_pending(bool destroyed, bool animation_done, bool native_processed)
{
    return destroyed && (!animation_done || !native_processed);
}

// Accepted surrender retains a live ship object. Only the native combat
// hostility flag makes that surviving ship block a sector departure.
inline bool sector_enemy_blocks(bool hostile, bool destroyed)
{
    return hostile && !destroyed;
}

// Native crew defeat uses the factory's surviving/clone crew counters and the
// automation flag. It does not require a hull explosion. Once WorldManager
// clears hostility its death event was handled; an open reward dialog is modal.
inline bool crew_defeat_pending(bool hostile, bool automated, int crew, int clones,
                                bool clone_system_functioning)
{
    return hostile && !automated &&
           (crew - (clone_system_functioning ? 0 : clones)) == 0;
}

template<class Neighbors, class Travel>
bool request_beacon(const TravelContext& context, int index, const Neighbors& neighbors,
                    Travel travel)
{
    if (context.refusal_reason() || index < 0 ||
        index >= static_cast<int>(neighbors.size()) || !neighbors[index]) return false;
    travel(neighbors[index]);
    return true;
}

// Sector buttons and NeighboringSector use global indices into StarMap.sectors.
// GetRandomSectorChoice generates a sector type (0..2), not one of these indices.
template<class Neighboring, class Random>
int choose_sector_index(int count, Neighboring neighboring, Random random)
{
    std::vector<int> choices;
    for (int index = 0; index < count; ++index) {
        if (neighboring(index)) choices.push_back(index);
    }
    if (choices.empty()) return -1;
    return choices[static_cast<unsigned>(random()) % choices.size()];
}
}
