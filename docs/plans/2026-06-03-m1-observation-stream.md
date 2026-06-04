
# ftl_bench Milestone 1 — Observation Stream: Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a read-only, end-to-end observation pipeline where an extended FTL-Hyperspace writes a throttled JSON snapshot of live game state to a known file each tick, and a Python `ftl_bench` harness reads + validates the latest snapshot.

**Architecture:** A single new C++ extension (`Benchmark_Extend`) exposes one Lua free function `Hyperspace.write_json_observation(string)` that atomically writes (temp-then-rename) to `{getUserFolder()}/ftl_agent_observation.json`. Three Lua scripts loaded in order via `hyperspace.xml` (`json.lua` → `observation.lua` → `bridge.lua`) build a real observation table from verified ShipManager/world getters, encode it with a sandbox-safe pure-Lua JSON encoder, and write it on a throttled `ON_TICK` hook. A decoupled Python harness reads + schema-validates the JSON, TDD'd against a recorded fixture so it never needs a running game during unit tests.

**Tech Stack:** C++14 + SWIG/Lua (FTL-Hyperspace, CMake + Ninja + vcpkg, macOS `amd64-darwin-ftl` triplet); Lua 5.3 (sandboxed: only `_G/table/string/math/utf8/bit32`); Python 3.14 + `uv` + `pytest` for the harness.

---

## Execution status — 2026-06-03

**Done & committed (code-verified without the game):**
- **Tasks 2–3 (C++ binding + SWIG)** — `Benchmark_Extend.{h,cpp}` + `hyperspace.i` edits committed to the Hyperspace fork (`5c53212f`). **As-built change vs. this draft:** implemented as **free functions** (`bool hs_benchmark_write_observation(const char* json_str)`), *not* static struct methods — the codebase exposes free functions (`srandom32→setRandomSeed`), and only that style yields the top-level `Hyperspace.write_json_observation(...)` the bridge calls. `const char*`/`bool` signature avoids `std_string.i` (not `%include`d). Anchors confirmed: include after `hyperspace.i:32`; binding after the `srandom32` block at `hyperspace.i:455`. `read`/`set` are implemented in C++ but **not** SWIG-bound yet (M2). CMake auto-globs root `*.cpp` — no CMake edit needed.
- **Tasks 4–6 (mod)** — `json.lua`, `observation.lua`, `bridge.lua`, `hyperspace.xml`, `metadata.xml` committed (`3b61220`). All pass `luac -p`; XML well-formed; `json.lua` **encode+decode round-trips** under real Lua.
- **Task 7 (harness)** — `ObservationClient` committed (`c2a2f5e`); **`7 passed`**. Cross-language contract verified: real `json.lua` encode → Python `ObservationClient` parse/validate.

- **Task 1 (build) — DONE.** After the human ran the one-time `arch -x86_64 … Homebrew` install, `setup-macos.sh` completed (x86 SDL2 + vcpkg) and the Release build produced **`build-darwin-1.6.13-release/Hyperspace.1.6.13.amd64.dylib`** (12.1 MB, `BUILD_EXIT=0`). **Our binding is verified in the generated wrapper** (`hyperspaceLUA_wrap.cxx`): `{ "write_json_observation", _wrap_write_json_observation }` is registered, the wrapper marshals `char const *` → `hs_benchmark_write_observation` → bool, and the symbol is exported in the dylib (`T __Z30hs_benchmark_write_observationPKc`). So Tasks 2–3 are proven on-platform.

**Staged for Task 8 (install assets in `dist/`, gitignored; helpers in `scripts/`):**
- `dist/Hyperspace.1.6.13.amd64.dylib`, `dist/Hyperspace.command`, `dist/hyperspace.ftl` (Hyperspace data mod, 391 files), `dist/ftl_bench_bridge.ftl` (our mod).
- `scripts/install_macos.sh` — copies dylib+command into `FTL.app`, patches `Info.plist` (`CFBundleExecutable`→`Hyperspace.command`), codesigns. (FTLMan mod-apply is the one manual GUI step it prints.)
- `scripts/verify_observation.sh` — waits for `ftl_agent_observation.json`, confirms `tick` advances, runs `ObservationClient` on the live file.

- **Task 8 (in-game verification) — DONE & PASSED** on FTL 1.6.13 + Hyperspace 1.22.2 (Steam, macOS). Installed via `install_macos.sh` (app-side) + **FTLMan CLI** `patch hyperspace.ftl ftl_bench_bridge.ftl` (no GUI needed; FTLMan keeps `ftl.dat.vanilla` so patch is idempotent) + codesign. Launched → `ftl_agent_observation.json` appeared at **`~/Library/Application Support/FasterThanLight/`** (this resolved the real `getUserFolder()` path — it's `FasterThanLight`, not `FTL`), `tick` advanced live (e.g. 890→1080), `ObservationClient` read + validated the live file, and `gui.bPaused` correctly reflected the window-unfocused auto-pause. The HS log shows `[Lua]: Hyperspace SWIG Lua loaded` and `Hyperspace.write_json_observation` working end-to-end.

  **Bug found & fixed during Task 8:** the bridge originally shipped `data/hyperspace.xml` (plain), which **replaced** Hyperspace's own `hyperspace.xml` and dropped its `<version>` tag → "Wrong version of Hyperspace detected" warning. Fixed by switching to **`data/hyperspace.xml.append`** (bare `<scripts>` node), which merges instead of clobbering. Re-patched from vanilla and re-verified: version check now logs `Mod requests '^1.22.2' vs Hyperspace '1.22.2'`, no warning, stream intact.

  **Still open (needs a started game, GUI click):** the `std::pair` access form (`.first/.second` vs `[0]/[1]`) in `observation.lua` — only exercised once `game_started=true` (i.e. a New Game is started and player-ship fields are read). The menu-level stream (`game_started=false`) is fully verified.

**🎉 Milestone 1 is functionally complete** — the read-only observation pipeline works live end-to-end (game → C++ binding → Lua bridge → file → Python harness). The only remaining check is the in-combat pair-access form (Task 8.4), which needs a started game.

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `/Users/ogabrielluiz/Projects/FTL-Hyperspace/Benchmark_Extend.h` | **Create.** Declares `Benchmark_Extend` struct with `write_json_observation`, `read_json_observation` (reserved for M2), `set_observation_path`. |
| `/Users/ogabrielluiz/Projects/FTL-Hyperspace/Benchmark_Extend.cpp` | **Create.** Implements atomic temp-then-rename file write to `{getUserFolder()}/ftl_agent_observation.json`; auto-globbed into the Hyperspace target. |
| `/Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/hyperspace.i` | **Modify.** Add `#include "Benchmark_Extend.h"` to the `%{ %}` block and `%rename`+declarations exposing the three functions to Lua. |
| `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/json.lua` | **Create.** Pure-Lua JSON encoder, loaded as global `_G.json` (no `require`/`package`). |
| `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/observation.lua` | **Create.** Builds the observation table from verified getters with nil-guards; exposes `_G.ftl_bench.build_observation()`. |
| `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/bridge.lua` | **Create.** Registers the throttled `ON_TICK` hook: serialize → encode → `write_json_observation`. |
| `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/hyperspace.xml` | **Create.** Declares the three `<script>` entries in load order. |
| `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/mod-appendix/metadata.xml` | **Create.** Slipstream mod metadata (title/author/version/description). |
| `/Users/ogabrielluiz/Projects/ftl_bench/harness/pyproject.toml` | **Create.** `ftl_bench` Python package metadata + pytest config (managed by `uv`). |
| `/Users/ogabrielluiz/Projects/ftl_bench/harness/src/ftl_bench/__init__.py` | **Create.** Package marker exporting `ObservationClient`, `Observation`. |
| `/Users/ogabrielluiz/Projects/ftl_bench/harness/src/ftl_bench/observation.py` | **Create.** `ObservationClient` (read + validate latest JSON) and `Observation` dataclass + validation errors. |
| `/Users/ogabrielluiz/Projects/ftl_bench/harness/tests/fixtures/observation_sample.json` | **Create.** Recorded observation fixture for decoupled TDD. |
| `/Users/ogabrielluiz/Projects/ftl_bench/harness/tests/test_observation_client.py` | **Create.** pytest suite driving `ObservationClient` against the fixture. |

---

## Tasks

### Task 1: Establish the macOS build toolchain and a clean baseline build of Hyperspace

**Files:**
- Modify (verify only, no edit): `/Users/ogabrielluiz/Projects/FTL-Hyperspace/CMakeLists.txt`

This task establishes the toolchain and surfaces the macOS-reality risk flagged by grounding (Apple Silicon vs. the `amd64-darwin-ftl` / x86_64 target) **before** any code is written.

1. - [ ] **FLAGGED VERIFICATION (grounding openItem: Apple Silicon build support).** Detect host architecture, because grounding warns the only triplet is `amd64-darwin-ftl` (Intel x86_64) and there is no native arm64 triplet:
   ```bash
   uname -m
   ```
   Expected output: `arm64` (Apple Silicon) or `x86_64` (Intel). If `arm64`, the Release build below targets x86_64 and will run under Rosetta 2 — proceed but note it; if the native build fails in step 5, fall back to the Docker devcontainer (Task 1a).

2. - [ ] **FLAGGED VERIFICATION (grounding risk: Xcode CLT required).** Confirm command-line tools are present:
   ```bash
   xcode-select -p
   ```
   Expected output: a path like `/Library/Developer/CommandLineTools` or `/Applications/Xcode.app/Contents/Developer`. If it errors, run `xcode-select --install` and re-run.

3. - [ ] Run the one-time macOS setup script (installs dual Homebrew arm64+x86, clones vcpkg into the repo, copies the triplet/toolchain files). This is the grounded setup entry point:
   ```bash
   cd /Users/ogabrielluiz/Projects/FTL-Hyperspace && buildscripts/ci/setup-macos.sh
   ```
   Expected: completes without error; `/Users/ogabrielluiz/Projects/FTL-Hyperspace/vcpkg/` now exists. (Grounding notes ~10–20 min first run.)

4. - [ ] Verify the vcpkg root and toolchain files landed:
   ```bash
   ls /Users/ogabrielluiz/Projects/FTL-Hyperspace/vcpkg/scripts/buildsystems/vcpkg.cmake \
      /Users/ogabrielluiz/Projects/FTL-Hyperspace/vcpkg/scripts/toolchains/amd64-darwin-ftl.cmake
   ```
   Expected output: both paths printed (no "No such file").

5. - [ ] Run the grounded single-variant Release build (FTL 1.6.13). This is the canonical baseline command from grounding:
   ```bash
   cd /Users/ogabrielluiz/Projects/FTL-Hyperspace && \
   buildscripts/build-one-variant.sh build-darwin-1.6.13-release amd64-darwin-ftl ON Release "${PWD}/vcpkg"
   ```
   Expected: CMake configures, `ninja` compiles, exits 0. (Grounding notes vcpkg first-time bootstrap can take 20–30 min.)

6. - [ ] **VERIFY ARTIFACT.** Confirm the baseline `.dylib` was produced with the grounded name:
   ```bash
   ls -la /Users/ogabrielluiz/Projects/FTL-Hyperspace/build-darwin-1.6.13-release/Hyperspace.1.6.13.amd64.dylib
   ```
   Expected output: the file exists with non-zero size. **This is the Definition-of-Done gate for the toolchain.**

7. - [ ] Commit the established baseline so later C++ diffs are isolated. (No source changed yet; commit only build-config artifacts that the repo tracks — if `git status` is clean, skip this and record the commit-of-record from upstream instead.)
   ```bash
   cd /Users/ogabrielluiz/Projects/FTL-Hyperspace && git rev-parse HEAD
   ```
   Expected output: a commit SHA. Record it as the pre-change baseline.

### Task 1a: (Fallback only) Docker devcontainer build if native macOS build fails

**Files:** none created/modified.

Execute this task **only if Task 1 step 5 or 6 fails** on Apple Silicon (grounding openItem).

1. - [ ] **FLAGGED VERIFICATION (grounding openItem: devcontainer image accessibility).** Confirm the image pulls:
   ```bash
   docker pull ghcr.io/ftl-hyperspace/hs-devcontainer
   ```
   Expected: image downloads. If it 404s/auth-fails, the devcontainer fallback is unavailable — escalate the macOS-build blocker to the user.

2. - [ ] Run the grounded Linux Release build in the container (produces a `.so`, useful only for proving compilation; the `.dylib` is still required to run on the Mac):
   ```bash
   cd /Users/ogabrielluiz/Projects/FTL-Hyperspace && \
   docker run -it --rm -v $PWD:/ftl ghcr.io/ftl-hyperspace/hs-devcontainer bash -c \
     "cd /ftl && cmake -DCMAKE_TOOLCHAIN_FILE=/vcpkg/scripts/buildsystems/vcpkg.cmake \
      -DVCPKG_HOST_TRIPLET=amd64-linux-ftl -DVCPKG_TARGET_TRIPLET=amd64-linux-ftl \
      -DVCPKG_CHAINLOAD_TOOLCHAIN_FILE=/vcpkg/scripts/toolchains/amd64-linux-ftl.cmake \
      -DCMAKE_BUILD_TYPE=Release -DSTEAM_1_6_13_BUILD=ON \
      -S . -B build-linux-1.6.13-release -G Ninja && ninja -C build-linux-1.6.13-release"
   ```
   Expected: `build-linux-1.6.13-release/Hyperspace.1.6.13.amd64.so` is produced. If even this fails, the build itself (not the platform) is broken — debug with superpowers:systematic-debugging before proceeding.

### Task 2: Add the `Benchmark_Extend` C++ transport binding (atomic file write)

**Files:**
- Create: `/Users/ogabrielluiz/Projects/FTL-Hyperspace/Benchmark_Extend.h`
- Create: `/Users/ogabrielluiz/Projects/FTL-Hyperspace/Benchmark_Extend.cpp`

1. - [ ] Create the header `/Users/ogabrielluiz/Projects/FTL-Hyperspace/Benchmark_Extend.h` with exactly:
   ```cpp
   #pragma once
   #include <string>
   #include <fstream>

   struct Benchmark_Extend
   {
       // Write a JSON observation string to disk atomically.
       // Path: {getUserFolder()}ftl_agent_observation.json
       //   (FileHelper::getUserFolder() returns a path WITH a trailing separator,
       //    so the filename is concatenated directly — matches SaveFile.cpp usage.)
       // Uses temp-file-then-rename to ensure consistency.
       // Returns true on success, false on write error (logged via C++ hs_log_file).
       static bool write_json_observation(const std::string& json_str);

       // Reserved for M2 (action read path). Not used in M1.
       static std::string read_json_observation();

       // Override the output directory (used by harness fixtures / tests).
       static void set_observation_path(const std::string& path);
   };
   ```

2. - [ ] Create the implementation `/Users/ogabrielluiz/Projects/FTL-Hyperspace/Benchmark_Extend.cpp` with exactly (POSIX `std::rename` is atomic on macOS per grounding; the `_WIN32` branch keeps it portable):
   ```cpp
   #include "Benchmark_Extend.h"
   #include "Global.h"
   #include <cstdio>
   #include <iterator>
   #ifdef _WIN32
   #include <windows.h>
   #endif

   namespace {
       std::string observation_directory = "";

       std::string get_observation_dir()
       {
           if (!observation_directory.empty()) {
               return observation_directory;
           }
           return FileHelper::getUserFolder();
       }
   }

   bool Benchmark_Extend::write_json_observation(const std::string& json_str)
   {
       std::string dir = get_observation_dir();
       std::string final_path = dir + "ftl_agent_observation.json";
       std::string temp_path = dir + "ftl_agent_observation.json.tmp";

       try {
           std::ofstream temp_file(temp_path, std::ios::binary);
           if (!temp_file.is_open()) {
               hs_log_file("[Benchmark] Failed to open temp file: %s\n", temp_path.c_str());
               return false;
           }
           temp_file.write(json_str.c_str(), json_str.size());
           if (!temp_file) {
               hs_log_file("[Benchmark] Failed to write temp file: %s\n", temp_path.c_str());
               temp_file.close();
               return false;
           }
           temp_file.close();

   #ifdef _WIN32
           if (!ReplaceFileA(final_path.c_str(), temp_path.c_str(), NULL, 0, NULL, NULL)) {
               if (std::rename(temp_path.c_str(), final_path.c_str()) != 0) {
                   hs_log_file("[Benchmark] Rename failed: %s -> %s\n", temp_path.c_str(), final_path.c_str());
                   return false;
               }
           }
   #else
           if (std::rename(temp_path.c_str(), final_path.c_str()) != 0) {
               hs_log_file("[Benchmark] Rename failed: %s -> %s\n", temp_path.c_str(), final_path.c_str());
               return false;
           }
   #endif
           return true;
       } catch (const std::exception& e) {
           hs_log_file("[Benchmark] Exception in write_json_observation: %s\n", e.what());
           return false;
       }
   }

   std::string Benchmark_Extend::read_json_observation()
   {
       std::string dir = get_observation_dir();
       std::string path = dir + "ftl_agent_observation.json";
       std::ifstream file(path, std::ios::binary);
       if (!file.is_open()) {
           return "";
       }
       std::string content((std::istreambuf_iterator<char>(file)),
                           std::istreambuf_iterator<char>());
       return content;
   }

   void Benchmark_Extend::set_observation_path(const std::string& path)
   {
       observation_directory = path;
   }
   ```

3. - [ ] **CONFIRM THE INCLUDE CHAIN (resolved during planning — this just records evidence).** `#include "Global.h"` alone is sufficient for both symbols: `hs_log_file` is declared directly in `Global.h:92`, and `FileHelper::getUserFolder()` is declared in the platform header `FTLGameMacOSAMD64.h:6542`, which `Global.h:7` pulls in transitively via `#include "FTLGame.h"`. Verify:
   ```bash
   grep -n 'hs_log_file' /Users/ogabrielluiz/Projects/FTL-Hyperspace/Global.h
   grep -n '#include "FTLGame.h"' /Users/ogabrielluiz/Projects/FTL-Hyperspace/Global.h
   grep -n 'getUserFolder' /Users/ogabrielluiz/Projects/FTL-Hyperspace/FTLGameMacOSAMD64.h
   ```
   Expected: `hs_log_file` at `Global.h:92-93`; `#include "FTLGame.h"` at `Global.h:7`; `getUserFolder` at `FTLGameMacOSAMD64.h:6542`. **Do not** add a direct `#include "FTLGameMacOSAMD64.h"` — that header is platform-specific and is selected by `FTLGame.h`; including it directly breaks non-macOS builds.

4. - [ ] Commit the C++ transport files:
   ```bash
   cd /Users/ogabrielluiz/Projects/FTL-Hyperspace && \
   git add Benchmark_Extend.h Benchmark_Extend.cpp && \
   git commit -m "Add Benchmark_Extend: atomic JSON observation file write (ftl_bench M1)"
   ```
   Expected output: one commit created.

### Task 3: Expose the binding to Lua via SWIG and rebuild

**Files:**
- Modify: `/Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/hyperspace.i` (the `%{ %}` include block near lines 6–34; and a declarations block near the global renames around lines 450–456)

1. - [ ] Find the exact line of the last `#include` in the `%{ %}` block to anchor the edit:
   ```bash
   grep -n '#include "CustomLockdowns.h"' /Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/hyperspace.i
   ```
   Expected output: a single line number (the grounded anchor inside `%{ %}`).

2. - [ ] Immediately after that `#include "CustomLockdowns.h"` line, add:
   ```cpp
   #include "Benchmark_Extend.h"
   ```

3. - [ ] Find the global-rename anchor (the grounded `srandom32` region where free functions are exposed):
   ```bash
   grep -n 'srandom32' /Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/hyperspace.i | head
   ```
   Expected output: at least one line number in the renames region (~line 450+).

4. - [ ] After that `srandom32` declaration block, add the SWIG bindings so the functions appear as `Hyperspace.write_json_observation` / `Hyperspace.read_json_observation` / `Hyperspace.set_observation_path`:
   ```cpp
   %rename("write_json_observation") Benchmark_Extend::write_json_observation;
   %rename("read_json_observation") Benchmark_Extend::read_json_observation;
   %rename("set_observation_path") Benchmark_Extend::set_observation_path;

   bool Benchmark_Extend::write_json_observation(const std::string& json_str);
   std::string Benchmark_Extend::read_json_observation();
   void Benchmark_Extend::set_observation_path(const std::string& path);
   ```

5. - [ ] Rebuild (CMake auto-globs the new `.cpp`/`.h`; SWIG regenerates the wrapper). Reuse the configured build dir from Task 1:
   ```bash
   cd /Users/ogabrielluiz/Projects/FTL-Hyperspace && ninja -C build-darwin-1.6.13-release
   ```
   Expected: SWIG re-runs, the new TU compiles, link succeeds, exits 0. The refreshed artifact is `build-darwin-1.6.13-release/Hyperspace.1.6.13.amd64.dylib`.

6. - [ ] **VERIFY BINDING IS IN THE WRAPPER.** Confirm SWIG emitted the function into the generated Lua wrapper:
   ```bash
   grep -rn "write_json_observation" /Users/ogabrielluiz/Projects/FTL-Hyperspace/build-darwin-1.6.13-release/ | head
   ```
   Expected output: at least one match in a generated `*wrap*.c`/`.cxx` file. (Confirms the binding compiled into the dylib; the live in-game console check happens in Task 8.)

7. - [ ] Commit the SWIG change:
   ```bash
   cd /Users/ogabrielluiz/Projects/FTL-Hyperspace && \
   git add lua/modules/hyperspace.i && \
   git commit -m "Expose Benchmark_Extend write/read/set to Lua via SWIG (ftl_bench M1)"
   ```
   Expected output: one commit created.

### Task 4: Author the sandbox-safe pure-Lua JSON encoder (`json.lua`)

**Files:**
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/json.lua`

This uses only grounded-available functions (`_G/table/string/math/pairs/ipairs/type/tostring`). M1 needs only `encode`; a minimal `decode` is included for M2 readiness but is not invoked in M1.

1. - [ ] Create the mod data directory:
   ```bash
   mkdir -p /Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data \
            /Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/mod-appendix
   ```
   Expected: directories created (no output).

2. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/json.lua` with exactly (note: it installs `_G.json` directly — no `require`, no trailing `return` needed because Hyperspace runs each file as a chunk in shared `_G`):
   ```lua
   -- ftl_bench pure-Lua JSON encoder. Sandbox-safe: uses only
   -- string/table/math/pairs/ipairs/type/tostring. Installs _G.json.
   local json = {}

   local function escape_string(s)
     local result = {}
     for i = 1, #s do
       local c = string.byte(s, i)
       if c == 34 then result[#result+1] = '\\"'
       elseif c == 92 then result[#result+1] = '\\\\'
       elseif c == 8 then result[#result+1] = '\\b'
       elseif c == 12 then result[#result+1] = '\\f'
       elseif c == 10 then result[#result+1] = '\\n'
       elseif c == 13 then result[#result+1] = '\\r'
       elseif c == 9 then result[#result+1] = '\\t'
       elseif c < 32 or c > 126 then result[#result+1] = string.format('\\u%04x', c)
       else result[#result+1] = string.sub(s, i, i)
       end
     end
     return table.concat(result)
   end

   local function encode_value(v, seen)
     seen = seen or {}
     local vtype = type(v)
     if vtype == 'nil' then
       return 'null'
     elseif vtype == 'boolean' then
       return v and 'true' or 'false'
     elseif vtype == 'number' then
       if v ~= v then return 'null' end
       if v == math.huge or v == -math.huge then return 'null' end
       if math.floor(v) == v then return string.format('%d', v) end
       return string.format('%.14g', v)
     elseif vtype == 'string' then
       return '"' .. escape_string(v) .. '"'
     elseif vtype == 'table' then
       if seen[v] then return 'null' end
       seen[v] = true
       local is_array = true
       local len = 0
       for k in pairs(v) do
         if type(k) ~= 'number' or k < 1 or math.floor(k) ~= k then
           is_array = false
           break
         end
         if k > len then len = k end
       end
       if is_array then
         for i = 1, len do
           if v[i] == nil then is_array = false break end
         end
       end
       local parts = {}
       if is_array then
         for i = 1, len do parts[i] = encode_value(v[i], seen) end
         seen[v] = nil
         return '[' .. table.concat(parts, ',') .. ']'
       else
         for k in pairs(v) do
           local ktype = type(k)
           if ktype == 'string' then
             parts[#parts+1] = '"' .. escape_string(k) .. '":' .. encode_value(v[k], seen)
           elseif ktype == 'number' then
             parts[#parts+1] = '"' .. tostring(k) .. '":' .. encode_value(v[k], seen)
           end
         end
         seen[v] = nil
         return '{' .. table.concat(parts, ',') .. '}'
       end
     else
       return 'null'
     end
   end

   function json.encode(value)
     return encode_value(value, {})
   end

   -- Minimal decoder reserved for M2 (not used in M1).
   function json.decode(str)
     local pos = 1
     local parse_value
     local function skip_ws()
       while pos <= #str and string.match(string.sub(str, pos, pos), '[\r\n\t ]') do pos = pos + 1 end
     end
     local function parse_string()
       pos = pos + 1
       local start = pos
       while pos <= #str do
         local c = string.sub(str, pos, pos)
         if c == '"' then local r = string.sub(str, start, pos - 1) pos = pos + 1 return r
         elseif c == '\\' then pos = pos + 2
         else pos = pos + 1 end
       end
       return ''
     end
     local function parse_number()
       local start = pos
       while pos <= #str and string.match(string.sub(str, pos, pos), '[0-9eE%+%-%.]') do pos = pos + 1 end
       return tonumber(string.sub(str, start, pos - 1))
     end
     local function parse_array()
       pos = pos + 1 skip_ws()
       local r = {}
       if string.sub(str, pos, pos) ~= ']' then
         repeat
           r[#r+1] = parse_value() skip_ws()
           if string.sub(str, pos, pos) == ',' then pos = pos + 1 end
         until string.sub(str, pos, pos) == ']'
       end
       pos = pos + 1 return r
     end
     local function parse_object()
       pos = pos + 1 skip_ws()
       local r = {}
       if string.sub(str, pos, pos) ~= '}' then
         repeat
           skip_ws() local key = parse_string() skip_ws()
           pos = pos + 1 r[key] = parse_value() skip_ws()
           if string.sub(str, pos, pos) == ',' then pos = pos + 1 end
         until string.sub(str, pos, pos) == '}'
       end
       pos = pos + 1 return r
     end
     parse_value = function()
       skip_ws()
       local c = string.sub(str, pos, pos)
       if c == '"' then return parse_string()
       elseif c == '{' then return parse_object()
       elseif c == '[' then return parse_array()
       elseif c == 't' then pos = pos + 4 return true
       elseif c == 'f' then pos = pos + 5 return false
       elseif c == 'n' then pos = pos + 4 return nil
       else return parse_number() end
     end
     return parse_value()
   end

   _G.json = json
   ```

3. - [ ] **SYNTAX CHECK.** Validate the Lua compiles with stock Lua (the encoder uses only standard 5.3 functions, so a host `luac`/`lua` check is a faithful proxy). If `luac`/`lua` is unavailable, skip this and rely on the in-game verification in Task 8:
   ```bash
   luac -p /Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/json.lua && echo "JSON_LUA_OK"
   ```
   Expected output: `JSON_LUA_OK` (no syntax errors).

4. - [ ] Commit:
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench && \
   git add mod/ftl_bench_bridge/data/json.lua && \
   git commit -m "Add sandbox-safe pure-Lua JSON encoder for observation stream (M1)"
   ```
   Expected output: one commit created.

### Task 5: Author the observation serializer (`observation.lua`)

**Files:**
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/observation.lua`

Only **grounding-VERIFIED** getters are populated. Fields that grounding marked `inferred`/`likely`/openItem (per-system `IsSystemHacked`, `GetSkillLevel` index mapping, `Projectile:GetType`, augment list) are **intentionally excluded** from M1 to avoid asserting unverified symbols. Every populated field below is `verified` in grounding.

1. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/observation.lua` with exactly:
   ```lua
   -- ftl_bench observation serializer. Builds a minimal-but-REAL observation
   -- table from VERIFIED Hyperspace getters, with nil-guards for not-in-game.
   -- Installs _G.ftl_bench.build_observation().
   _G.ftl_bench = _G.ftl_bench or {}

   local function ship_snapshot(mgr)
     if not mgr then return nil end
     local pwr = mgr:GetAvailablePower()      -- {max, available}; verified i:1585
     local snap = {
       hull = {
         current = mgr.ship.hullIntegrity.first,   -- verified i:2573
         max = mgr.ship.hullIntegrity.second,
       },
       reactor = { total = pwr.first, available = pwr.second },
       resources = {
         scrap = mgr.currentScrap,               -- verified i:1711
         fuel = mgr.fuel_count,                   -- verified i:1702
         missiles = mgr:GetMissileCount(),        -- verified i:1618
         drone_parts = mgr:GetDroneCount(),       -- verified i:1617
       },
       oxygen_pct = mgr:GetOxygenPercentage(),    -- verified i:1621
       systems = {},
       crew = {},
       weapons = {},
       shields = {},
     }

     local sys_list = mgr.vSystemList             -- verified i:1660
     if sys_list then
       for i = 0, sys_list:size() - 1 do
         local sys = sys_list[i]
         snap.systems[#snap.systems + 1] = {
           id = sys:GetId(),                      -- verified i:2143
           power = sys.powerState.first,          -- verified i:2195 (Pair: current/max)
           power_max = sys.powerState.second,
           damage = sys.fDamage,                  -- verified i:2184
           max_damage = sys.fMaxDamage,           -- verified i:2186
           powered = sys:Powered(),               -- verified i:2163
         }
       end
     end

     local crew_list = mgr.vCrewList              -- verified i:1690
     if crew_list then
       for i = 0, crew_list:size() - 1 do
         local crew = crew_list[i]
         snap.crew[#snap.crew + 1] = {
           id = i,
           room = crew.iRoomId,                   -- verified i:3451
           health_current = crew.health.first,    -- verified i:3439 (Pair)
           health_max = crew.health.second,
           dead = crew.bDead,                     -- verified i:3481
           mind_controlled = crew.bMindControlled,-- verified i:3494
         }
       end
     end

     local weapon_list = mgr:GetWeaponList()      -- verified i:1630
     if weapon_list then
       for i = 0, weapon_list:size() - 1 do
         local w = weapon_list[i]
         snap.weapons[#snap.weapons + 1] = {
           slot = i,
           cooldown = w.cooldown,                 -- verified i:2408
           base_cooldown = w.baseCooldown,        -- verified i:2410
           powered = w.powered,                   -- verified i:2416
         }
       end
     end

     local shield_sys = mgr.shieldSystem          -- verified i:1678
     if shield_sys then
       local shields = shield_sys.shields         -- verified i:2057
       if shields then
         for i = 0, shields:size() - 1 do
           local s = shields[i]
           snap.shields[#snap.shields + 1] = {
             charger = s.charger,                 -- verified i:2029
             power = s.power,                     -- verified i:2030
           }
         end
       end
     end

     return snap
   end

   function _G.ftl_bench.build_observation(tick)
     local app = Hyperspace.App
     local world = app and app.world
     local gui = app and app.gui

     -- Seed is always readable; verified i:497.
     local obs = {
       schema_version = 1,
       tick = tick,
       seed = Hyperspace.Global.currentSeed,
       game_started = world and world.bStartedGame or false,   -- verified i:1232
       paused = gui and gui.bPaused or false,                  -- verified i:876
     }

     if not obs.game_started then
       obs.player_ship = nil
       obs.enemy_ship = nil
       return obs
     end

     obs.player_ship = ship_snapshot(Hyperspace.ships.player)  -- verified i:518
     obs.enemy_ship = ship_snapshot(Hyperspace.ships.enemy)    -- verified i:520

     -- Map state (verified i:1352/1338).
     local star_map = world.starMap
     if star_map then
       obs.map = {
         sector = star_map.worldLevel,
         current_sector = star_map.currentSector,
       }
     end

     -- Event/choice flag (verified i:909).
     obs.choice_box_open = gui and gui.choiceBoxOpen or false

     return obs
   end
   ```

2. - [ ] **FLAGGED VERIFICATION (grounding openItem: `Pair` access form `.first/.second` vs `[0]/[1]`).** Grounding's artifacts show both `hullIntegrity[0]` and `GetAvailablePower()[1]` *and* describe these as C++ `std::pair`. SWIG-Lua typically exposes `std::pair` as `.first/.second`. This file uses `.first/.second`. Confirm against the SWIG `%template` for the relevant pairs:
   ```bash
   grep -n "pair\|hullIntegrity\|powerState\|GetAvailablePower" /Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/modules/hyperspace.i | head -20
   ```
   Expected: shows whether these are `std::pair` (use `.first/.second`) or bound as a 2-element vector (use `[0]/[1]`). **If they are vectors/`Point`-like with `[0]/[1]`, fix this file accordingly in Task 8 step 4 when the in-game console reveals the real access form.** Record the resolved form.

3. - [ ] **SYNTAX CHECK** (proxy; same caveat as Task 4 — Hyperspace globals like `Hyperspace`/`script` are undefined under host Lua, so use `luac -p` which checks syntax only, not symbol resolution):
   ```bash
   luac -p /Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/observation.lua && echo "OBS_LUA_OK"
   ```
   Expected output: `OBS_LUA_OK`.

4. - [ ] Commit:
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench && \
   git add mod/ftl_bench_bridge/data/observation.lua && \
   git commit -m "Add observation serializer from verified Hyperspace getters (M1)"
   ```
   Expected output: one commit created.

### Task 6: Author the throttled ON_TICK bridge and mod packaging

**Files:**
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/bridge.lua`
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/hyperspace.xml`
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/mod-appendix/metadata.xml`

1. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/bridge.lua` with exactly (Lua-local frame counter per grounding recommendation; `ON_TICK` registration is the grounded pattern; `pcall` guards a single bad tick from crashing the game loop):
   ```lua
   -- ftl_bench bridge: throttled ON_TICK -> build observation -> json -> write file.
   local THROTTLE_INTERVAL = 10   -- write every N ticks (~6 Hz at 60 FPS)
   local frame_counter = 0

   local function on_tick_handler()
     frame_counter = frame_counter + 1
     if frame_counter % THROTTLE_INTERVAL ~= 0 then return end

     local ok, result = pcall(function()
       local obs = _G.ftl_bench.build_observation(frame_counter)
       local payload = _G.json.encode(obs)
       return Hyperspace.write_json_observation(payload)
     end)

     if not ok then
       print("[ftl_bench] observation tick error: " .. tostring(result))
     elseif result == false then
       print("[ftl_bench] write_json_observation returned false")
     end
   end

   script.on_internal_event(Defines.InternalEvents.ON_TICK, on_tick_handler)
   ```

   > **Note (resolved during planning):** `hs_log_file` is a C++-only symbol (`Global.h:92`) and is **not** bound to Lua, so the bridge logs via `print(...)`, which **is** available — `lua/linit.c:40` enables the base library (`{"_G", luaopen_base}`) and `hyperspace.i:680` itself calls `print`. Never use `hs_log_file` in a `.lua` file (it is fine in C++).

2. - [ ] **CONFIRM `print` IS LIVE (1-line evidence check).** Verify the base library that provides `print` is enabled while file/OS libs are not:
   ```bash
   grep -n 'luaopen_base\|luaopen_io\|luaopen_os' /Users/ogabrielluiz/Projects/FTL-Hyperspace/lua/linit.c
   ```
   Expected: `{"_G", luaopen_base}` is **uncommented** (line ~40) while `luaopen_io`/`luaopen_os` are **commented out** — confirming `print` works and file/OS libs do not (which is exactly why the Task 2 C++ transport binding is required).

3. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/hyperspace.xml` with exactly (load order matters: `json` then `observation` then `bridge`, all sharing `_G` per grounding):
   ```xml
   <FTL>
     <scripts>
       <script>data/json.lua</script>
       <script>data/observation.lua</script>
       <script>data/bridge.lua</script>
     </scripts>
   </FTL>
   ```

4. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/mod-appendix/metadata.xml` with exactly:
   ```xml
   <metadata>
     <title>ftl_bench Observation Bridge</title>
     <threadUrl></threadUrl>
     <author>ftl_bench</author>
     <version>0.1.0 (M1)</version>
     <description>Read-only observation stream: writes a throttled JSON snapshot of live FTL game state to ftl_agent_observation.json each tick.</description>
   </metadata>
   ```

5. - [ ] **SYNTAX CHECK** the bridge Lua and the XML well-formedness:
   ```bash
   luac -p /Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/bridge.lua && echo "BRIDGE_OK"
   python3 -c "import xml.dom.minidom,sys; [xml.dom.minidom.parse(p) for p in sys.argv[1:]]; print('XML_OK')" \
     /Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/data/hyperspace.xml \
     /Users/ogabrielluiz/Projects/ftl_bench/mod/ftl_bench_bridge/mod-appendix/metadata.xml
   ```
   Expected output: `BRIDGE_OK` then `XML_OK`.

6. - [ ] Commit the packaged mod:
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench && \
   git add mod/ftl_bench_bridge/data/bridge.lua \
           mod/ftl_bench_bridge/data/hyperspace.xml \
           mod/ftl_bench_bridge/mod-appendix/metadata.xml && \
   git commit -m "Package ftl_bench_bridge mod: throttled ON_TICK observation writer (M1)"
   ```
   Expected output: one commit created.

### Task 7: Build the Python `ftl_bench` harness with real pytest TDD against a recorded fixture

**Files:**
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/harness/pyproject.toml`
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/harness/src/ftl_bench/__init__.py`
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/harness/src/ftl_bench/observation.py`
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/harness/tests/fixtures/observation_sample.json`
- Create: `/Users/ogabrielluiz/Projects/ftl_bench/harness/tests/test_observation_client.py`

This is **real TDD**: write the fixture + failing tests, run (FAIL), implement, run (PASS), commit. The harness is decoupled from the game — it reads a JSON file path.

1. - [ ] Scaffold the package layout:
   ```bash
   mkdir -p /Users/ogabrielluiz/Projects/ftl_bench/harness/src/ftl_bench \
            /Users/ogabrielluiz/Projects/ftl_bench/harness/tests/fixtures
   ```
   Expected: directories created.

2. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/harness/pyproject.toml` with exactly:
   ```toml
   [project]
   name = "ftl_bench"
   version = "0.1.0"
   description = "FTL agent benchmark harness — observation stream client (M1)"
   requires-python = ">=3.11"
   dependencies = []

   [project.optional-dependencies]
   dev = ["pytest>=8.0"]

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [tool.hatch.build.targets.wheel]
   packages = ["src/ftl_bench"]

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   pythonpath = ["src"]
   ```

3. - [ ] Create the recorded fixture `/Users/ogabrielluiz/Projects/ftl_bench/harness/tests/fixtures/observation_sample.json` with exactly (this is the contract the Lua serializer produces; field shapes match `observation.lua`):
   ```json
   {
     "schema_version": 1,
     "tick": 120,
     "seed": 1234567,
     "game_started": true,
     "paused": false,
     "choice_box_open": false,
     "map": { "sector": 0, "current_sector": 0 },
     "player_ship": {
       "hull": { "current": 30, "max": 30 },
       "reactor": { "total": 8, "available": 5 },
       "resources": { "scrap": 10, "fuel": 16, "missiles": 8, "drone_parts": 0 },
       "oxygen_pct": 100.0,
       "systems": [
         { "id": 0, "power": 2, "power_max": 3, "damage": 0.0, "max_damage": 0.0, "powered": true }
       ],
       "crew": [
         { "id": 0, "room": 0, "health_current": 100.0, "health_max": 100.0, "dead": false, "mind_controlled": false }
       ],
       "weapons": [
         { "slot": 0, "cooldown": 0.0, "base_cooldown": 11.0, "powered": true }
       ],
       "shields": [
         { "charger": 0, "power": 4 }
       ]
     },
     "enemy_ship": null
   }
   ```

4. - [ ] Write the **failing** test suite `/Users/ogabrielluiz/Projects/ftl_bench/harness/tests/test_observation_client.py` with exactly:
   ```python
   import json
   from pathlib import Path

   import pytest

   from ftl_bench.observation import (
       ObservationClient,
       Observation,
       ObservationValidationError,
   )

   FIXTURE = Path(__file__).parent / "fixtures" / "observation_sample.json"


   def test_read_latest_returns_observation():
       client = ObservationClient(FIXTURE)
       obs = client.read_latest()
       assert isinstance(obs, Observation)
       assert obs.tick == 120
       assert obs.seed == 1234567
       assert obs.game_started is True


   def test_player_ship_hull_parsed():
       obs = ObservationClient(FIXTURE).read_latest()
       assert obs.player_ship["hull"]["current"] == 30
       assert obs.player_ship["hull"]["max"] == 30


   def test_enemy_ship_is_none_when_null():
       obs = ObservationClient(FIXTURE).read_latest()
       assert obs.enemy_ship is None


   def test_missing_file_raises():
       client = ObservationClient(Path("/nonexistent/observation.json"))
       with pytest.raises(FileNotFoundError):
           client.read_latest()


   def test_schema_version_mismatch_raises(tmp_path):
       bad = tmp_path / "obs.json"
       bad.write_text(json.dumps({"schema_version": 999, "tick": 1, "seed": 0,
                                  "game_started": False}))
       client = ObservationClient(bad)
       with pytest.raises(ObservationValidationError):
           client.read_latest()


   def test_missing_required_field_raises(tmp_path):
       bad = tmp_path / "obs.json"
       bad.write_text(json.dumps({"schema_version": 1, "tick": 1}))
       client = ObservationClient(bad)
       with pytest.raises(ObservationValidationError):
           client.read_latest()


   def test_changing_state_detected(tmp_path):
       p = tmp_path / "obs.json"
       p.write_text(json.dumps({"schema_version": 1, "tick": 10, "seed": 1,
                                "game_started": True}))
       client = ObservationClient(p)
       first = client.read_latest()
       p.write_text(json.dumps({"schema_version": 1, "tick": 20, "seed": 1,
                                "game_started": True}))
       second = client.read_latest()
       assert first.tick == 10
       assert second.tick == 20
   ```

5. - [ ] **RUN THE TESTS — EXPECT FAILURE** (no implementation yet; import of `ftl_bench.observation` fails):
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench/harness && uv run --with pytest pytest -q
   ```
   Expected output: collection error / `ModuleNotFoundError: No module named 'ftl_bench.observation'` — **tests FAIL (red).**

6. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/harness/src/ftl_bench/__init__.py` with exactly:
   ```python
   from ftl_bench.observation import (
       Observation,
       ObservationClient,
       ObservationValidationError,
   )

   __all__ = ["Observation", "ObservationClient", "ObservationValidationError"]
   ```

7. - [ ] Create `/Users/ogabrielluiz/Projects/ftl_bench/harness/src/ftl_bench/observation.py` with exactly:
   ```python
   """ftl_bench observation client: read + validate the latest observation JSON.

   Decoupled from the running game — operates purely on a JSON file path.
   """
   from __future__ import annotations

   import json
   from dataclasses import dataclass
   from pathlib import Path
   from typing import Any, Optional

   SCHEMA_VERSION = 1
   REQUIRED_FIELDS = ("schema_version", "tick", "seed", "game_started")


   class ObservationValidationError(ValueError):
       """Raised when an observation JSON fails schema validation."""


   @dataclass
   class Observation:
       schema_version: int
       tick: int
       seed: int
       game_started: bool
       paused: bool = False
       choice_box_open: bool = False
       player_ship: Optional[dict[str, Any]] = None
       enemy_ship: Optional[dict[str, Any]] = None
       map: Optional[dict[str, Any]] = None
       raw: Optional[dict[str, Any]] = None

       @classmethod
       def from_dict(cls, data: dict[str, Any]) -> "Observation":
           for field in REQUIRED_FIELDS:
               if field not in data:
                   raise ObservationValidationError(
                       f"missing required field: {field!r}"
                   )
           version = data["schema_version"]
           if version != SCHEMA_VERSION:
               raise ObservationValidationError(
                   f"schema_version mismatch: expected {SCHEMA_VERSION}, got {version}"
               )
           return cls(
               schema_version=version,
               tick=data["tick"],
               seed=data["seed"],
               game_started=data["game_started"],
               paused=data.get("paused", False),
               choice_box_open=data.get("choice_box_open", False),
               player_ship=data.get("player_ship"),
               enemy_ship=data.get("enemy_ship"),
               map=data.get("map"),
               raw=data,
           )


   class ObservationClient:
       """Reads the latest observation snapshot from a JSON file on disk."""

       def __init__(self, path: Path | str) -> None:
           self.path = Path(path)

       def read_latest(self) -> Observation:
           if not self.path.exists():
               raise FileNotFoundError(f"observation file not found: {self.path}")
           text = self.path.read_text(encoding="utf-8")
           try:
               data = json.loads(text)
           except json.JSONDecodeError as exc:
               raise ObservationValidationError(f"invalid JSON: {exc}") from exc
           if not isinstance(data, dict):
               raise ObservationValidationError("observation root must be a JSON object")
           return Observation.from_dict(data)
   ```

8. - [ ] **RUN THE TESTS — EXPECT PASS (green):**
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench/harness && uv run --with pytest pytest -q
   ```
   Expected output: `7 passed` (no failures).

9. - [ ] Commit the harness:
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench && \
   git add harness/pyproject.toml harness/src/ftl_bench/__init__.py \
           harness/src/ftl_bench/observation.py \
           harness/tests/test_observation_client.py \
           harness/tests/fixtures/observation_sample.json && \
   git commit -m "Add ftl_bench ObservationClient with pytest TDD against fixture (M1)"
   ```
   Expected output: one commit created.

### Task 8: In-game verification — install the mod, confirm the binding works, confirm live changing state

**Files:** none created/modified (install + manual verification only).

This task exercises the pieces that cannot be unit-tested: the live SWIG binding, the sandbox Lua, and the end-to-end stream. Use the in-game Lua console (`LuaScriptInit::runLuaString`, grounded).

1. - [ ] Install the rebuilt dylib into the FTL app and configure the launcher per the grounded macOS install steps. Locate the FTL app and copy the artifact:
   ```bash
   ls -d "/Users/ogabrielluiz/Library/Application Support/Steam/steamapps/common/FTL Faster Than Light/FTL.app" 2>/dev/null || \
   find ~/Library -maxdepth 6 -name "FTL.app" -type d 2>/dev/null | head
   ```
   Expected output: the path to `FTL.app`. Record it as `$FTL_APP`. Then follow `/Users/ogabrielluiz/Projects/FTL-Hyperspace/Release Files/MacOS/README.txt` steps 2–7: copy `build-darwin-1.6.13-release/Hyperspace.1.6.13.amd64.dylib` and `Hyperspace.command` into `$FTL_APP/Contents/MacOS/`, edit `Info.plist` to launch `Hyperspace.command`, then sign:
   ```bash
   codesign -f -s - --timestamp=none --all-architectures --deep "$FTL_APP"
   ```
   Expected: `replacing existing signature` / no error.

2. - [ ] Install the `ftl_bench_bridge` mod with Slipstream/FTLMan per README. Confirm the mod's data folder is the one packaged in Task 6 (the `data/hyperspace.xml` + three `.lua` files + `mod-appendix/metadata.xml`). Launch FTL via the patched app.

3. - [ ] **VERIFY THE C++ BINDING LIVE** (in-game Lua console). Run exactly:
   ```lua
   local ok = Hyperspace.write_json_observation('{"test":"data"}')
   print("write ok:", ok)
   ```
   Expected console output: `write ok:   true`. Then confirm the file landed:
   ```bash
   ls -la "$HOME/Library/Application Support/FTL/ftl_agent_observation.json" && \
   cat "$HOME/Library/Application Support/FTL/ftl_agent_observation.json"
   ```
   Expected output: the file exists and contains `{"test":"data"}`. (This resolves the grounding openItem about the actual `getUserFolder()` path on macOS — record the real path.)

4. - [ ] **RESOLVE THE PAIR-ACCESS OPENITEM (Task 5 step 2).** Start a New Game, then in the console run exactly:
   ```lua
   local obs = _G.ftl_bench.build_observation(0)
   print("hull:", obs.player_ship.hull.current, obs.player_ship.hull.max)
   print("json:", _G.json.encode(obs):sub(1, 120))
   ```
   Expected: prints real hull numbers (e.g. `hull: 30  30`) and a JSON prefix. **If `obs.player_ship.hull.current` is `nil`**, the `Pair` access form is `[0]/[1]`, not `.first/.second` — edit `observation.lua` to use `mgr.ship.hullIntegrity[0]`/`[1]`, `pwr[0]`/`pwr[1]`, `sys.powerState[0]`/`[1]`, `crew.health[0]`/`[1]`, rebuild nothing (Lua only), reinstall the mod data, and re-run. Commit any fix:
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench && git add mod/ftl_bench_bridge/data/observation.lua && \
   git commit -m "Fix Pair access form in observation serializer per in-game verification (M1)"
   ```

5. - [ ] **VERIFY THE LIVE THROTTLED STREAM IS CHANGING.** With a game running (combat preferred so hull/cooldowns move), watch the observation file update and confirm `tick` advances:
   ```bash
   F="$HOME/Library/Application Support/FTL/ftl_agent_observation.json"
   python3 -c "import json,time; \
   a=json.load(open('$F')); print('tick A:', a['tick']); time.sleep(3); \
   b=json.load(open('$F')); print('tick B:', b['tick']); \
   assert b['tick'] > a['tick'], 'tick did not advance'; print('STREAM_LIVE_OK')"
   ```
   Expected output: two increasing tick values and `STREAM_LIVE_OK`.

6. - [ ] **VERIFY THE HARNESS READS LIVE STATE.** Point `ObservationClient` at the live file (decoupled API, real game data):
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench/harness && \
   uv run python -c "from pathlib import Path; from ftl_bench import ObservationClient; \
   o=ObservationClient(Path.home()/'Library/Application Support/FTL/ftl_agent_observation.json').read_latest(); \
   print('tick', o.tick, 'started', o.game_started, 'hull', (o.player_ship or {}).get('hull'))"
   ```
   Expected output: a line with a real tick, `started True`, and a real hull dict — proving the end-to-end pipeline (live game → C++ write → harness read+validate).

7. - [ ] **RECORD A REAL FIXTURE (close the loop).** Copy a live snapshot over the recorded fixture so the TDD fixture reflects the true serializer output, then re-run the suite to confirm the real shape still validates:
   ```bash
   cp "$HOME/Library/Application Support/FTL/ftl_agent_observation.json" \
      /Users/ogabrielluiz/Projects/ftl_bench/harness/tests/fixtures/observation_sample.json
   cd /Users/ogabrielluiz/Projects/ftl_bench/harness && uv run --with pytest pytest -q
   ```
   Expected output: `7 passed`. If a test fails because the real shape differs from the hand-written fixture, reconcile `observation.py`/tests with the real schema, re-run to green, then commit.

8. - [ ] Commit the recorded real fixture (and any reconciliation):
   ```bash
   cd /Users/ogabrielluiz/Projects/ftl_bench && \
   git add harness/tests/fixtures/observation_sample.json && \
   git commit -m "Record real live observation fixture from in-game run (M1 verification)"
   ```
   Expected output: one commit created.

---

## Milestone self-test (Definition of Done)

- [ ] Hyperspace builds natively on this Mac (or via the Task 1a devcontainer fallback) and produces `build-darwin-1.6.13-release/Hyperspace.1.6.13.amd64.dylib` (Task 1 step 6).
- [ ] `Hyperspace.write_json_observation('{"test":"data"}')` returns `true` in the live in-game console and writes `{"test":"data"}` to `{getUserFolder()}/ftl_agent_observation.json` (Task 8 step 3).
- [ ] `_G.json.encode` and `_G.ftl_bench.build_observation` are loaded as globals (no `require`/`package`) and produce a real observation table from live ShipManager state (Task 8 step 4).
- [ ] The throttled `ON_TICK` hook writes the observation file and `tick` provably advances over time during a live game (Task 8 step 5).
- [ ] `pytest -q` in `harness/` is green (`7 passed`) against the recorded fixture, decoupled from the game (Task 7 step 8; re-confirmed Task 8 step 7).
- [ ] `ObservationClient.read_latest()` reads + validates the **live** observation file and surfaces real changing state (Task 8 step 6).
- [ ] Every flagged-verification openItem is resolved and recorded: Apple-Silicon build path (Task 1.1), `getUserFolder()` real macOS runtime path (Task 8.3), `Pair` access form `.first/.second` vs `[0]/[1]` (Task 8.4). (Resolved during planning: `hs_log_file` is C++-only → bridge uses `print`; include chain is `Global.h` alone.)
- [ ] All work is committed in small, frequent commits across both repos.

## Follow-on milestones

- **M2 — Pause-gating + action dispatch.** Use the M2-reserved `read_json_observation`/`set_observation_path` bindings plus `CommandGui.bPaused` (verified writable, `hyperspace.i:876`) to add a turn-based gate and an action-read channel. Note on `FPS.SpeedFactor`: the `%immutable` at `hyperspace.i:442` applies to the **`FPS` global handle** (you can't reassign `Hyperspace.FPS`), not necessarily the struct member `CFPS::SpeedFactor` (`i:546`, declared without `%immutable`) — so member-write `Hyperspace.FPS.SpeedFactor = 0` may work. M2 spike: confirm whether `SpeedFactor=0` is settable and whether `bPaused=true` cleanly halts mid-animation; pick whichever cleanly freezes the sim.
- **M3 — Action-gap bindings.** Add the C++/SWIG bindings for the actions not yet exposed: weapon target+fire, event-choice confirm, jump trigger, and store interactions.
- **M4 — Seed-setter + determinism harness.** Add a seed-setter binding (seed is read-only today via `currentSeed`) and a Python determinism harness that replays a seed and diffs observation streams.
- **M5 — MCP/agent adapter.** Wrap `ObservationClient` (and M2/M3 action dispatch) behind an MCP/agent adapter in `adapter/`.
- **M6 — Scenario library + metrics.** Build the `scenarios/` library and scoring/metrics on top of the observation+action loop.