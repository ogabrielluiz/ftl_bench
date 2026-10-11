#pragma once
#include <vector>

// These rules use the same indices and ship definition fields as the native
// UpgradeBox and Hyperspace ReactorButton. A negative cost means unavailable.
namespace BenchmarkEconomy {
inline int system_cost(int level, int maximum, const std::vector<int>& prices)
{
    if (level < 1 || level >= maximum || level > static_cast<int>(prices.size())) return -1;
    return prices[level - 1] >= 0 ? prices[level - 1] : -1;
}

inline int reactor_cost(int level, int maximum, const std::vector<int>& prices, int increment)
{
    if (level < 0 || level >= maximum || prices.empty()) return -1;
    int column = level / 5 + 1;
    if (column >= static_cast<int>(prices.size())) return -1;
    int price = prices[column];
    if (price < 0) price = prices[0] + (column - 1) * increment;
    return price >= 0 ? price : -1;
}

struct Context {
    bool started = false;
    bool main_menu = false;
    bool game_over = false;
    bool destroyed = false;
    bool mid_warp = false;
    bool pending_travel = false;
    // Arrival completion persists while idle; it is status, not pending travel.
    bool arrival_complete = false;
    bool pending_sector = false;
    bool waiting = false;
    bool modal = false;

    bool ready() const
    {
        return started && !main_menu && !game_over && !destroyed && !mid_warp &&
               !pending_travel && !pending_sector && !waiting && !modal;
    }
};

// StarMap accepts screen coordinates and forwards map-local coordinates to its
// Wait/distress buttons. Keep dispatch through native hover and active checks.
template<class Map, class Button>
void click_map_button(Map& map, Button& button)
{
    const auto& box = button.hitbox;
    const int x = map.position.x + box.x + box.w / 2;
    const int y = map.position.y + box.y + box.h / 2;
    map.MouseMove(x, y);
    map.MouseClick(x, y);
}
// UpgradeSystem can reject an upgrade through its native cap/hooks. Charge only
// after observing exactly the requested capacity change; no-op requests are free.
template<class Level, class Upgrade, class Spend>
bool purchase(bool allowed, int price, int scrap, Level level, Upgrade upgrade, Spend spend)
{
    if (!allowed || price < 0 || scrap < price) return false;
    const int before = level();
    upgrade();
    if (level() != before + 1) return false;
    spend(price);
    return true;
}
}
