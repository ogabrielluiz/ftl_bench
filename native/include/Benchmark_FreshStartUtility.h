#pragma once
#include <string>
// Candidate v3: provenance scope only around the known utility blueprint lookup.
namespace BenchmarkFreshStartSeed {
struct UtilityNameScope {
    bool finished=false;
    UtilityNameScope();
    ~UtilityNameScope();
    void complete(const std::string& captured_name);
};
}

// Read-only private SaveFile dialog state; no event dispatch.
namespace BenchmarkFreshStartSeed { bool save_transfer_dialog_open(); }
