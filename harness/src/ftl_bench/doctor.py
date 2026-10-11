"""Read-only installation checks; never start a game, modify saves, or call a model."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from ftl_bench.observation import ObservationClient
from ftl_bench.session import ftl_process_alive, ftl_user_folder


def inspect_installation(*, user_folder=None, game_dir=None, backend=None,
                         live=False, full_game=False) -> dict:
    save = Path(user_folder) if user_folder is not None else ftl_user_folder()
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    check("save_folder", save.is_dir(), save)
    check("bridge_script", (save / "ftl_bench_dev.lua").is_file(),
          "Deploy the bridge with ftlbench deploy-bridge." if not (save / "ftl_bench_dev.lua").is_file() else save / "ftl_bench_dev.lua")
    configured_game = game_dir or os.environ.get("FTL_GAME_DIR")
    if configured_game:
        game = Path(configured_game)
    elif os.name == "nt":
        game = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam/steamapps/common/FTL Faster Than Light"
    else:
        game = None
    if game is not None:
        for filename in ("FTLGame.exe", "Hyperspace.dll", "xinput1_4.dll", "lua-5.3.dll"):
            check(filename, (game / filename).is_file(), game / filename)

    if backend in {"anthropic", "openai", "jev"}:
        name = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "jev": "TYPESAFE_API_KEY"}[backend]
        if backend == "jev" and not os.environ.get(name) and os.environ.get("JEV_API_KEY"):
            name = "JEV_API_KEY"
        key = (os.environ.get(name) or "").strip().strip('"').strip("'")
        check("model_backend", bool(key), f"{name} configured" if key else f"Set {name} or select --env-file.")
    elif backend in {"codex", "claude-cli"}:
        command = "codex" if backend == "codex" else "claude"
        executable = shutil.which(command)
        if command == "codex":
            explicit = os.environ.get("CODEX_BIN")
            fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/OpenAI/Codex/bin/codex.exe"
            executable = explicit if explicit and Path(explicit).is_file() else executable
            executable = executable or (str(fallback) if fallback.is_file() else None)
        check("model_backend", executable is not None,
              executable or f"Install {command} and sign in before running this backend.")
    elif backend is not None:
        raise ValueError(f"unknown backend: {backend}")

    capabilities = {}
    economy = {}
    if live or full_game:
        check("game_process", ftl_process_alive(), "Launch FTL through Steam.")
        try:
            obs = ObservationClient(save / "ftl_agent_observation.json").read_latest()
            capabilities = (obs.raw or {}).get("capabilities") or {}
            economy = (obs.raw or {}).get("economy") or {}
            check("observation", True, f"schema {obs.schema_version}, tick {obs.tick}")
        except (OSError, ValueError) as error:
            check("observation", False, f"No valid bridge observation: {error}")
        for name in ("manual_fire", "global_autofire_control"):
            check(name, capabilities.get(name) is True, "Rebuild/install the native benchmark patch if unavailable.")
        protocol = capabilities.get("native_protocol")
        check("native_protocol", type(protocol) is int and protocol >= 5,
              "Benchmark protocol 5 or later is required for exact upgrades and fuel recovery.")
        check("setup_identity", capabilities.get("setup_identity") is True,
              "Rebuild/install the current native ship and difficulty getters if unavailable.")
        check("live_score", capabilities.get("live_score") is True,
              "Rebuild/install the native live score getter if unavailable.")
        for name in ("crew_control_guard", "crew_ownership"):
            check(name, capabilities.get(name) is True,
                  "Deploy the current Lua bridge to restrict movement to owned, controllable crew.")
        check("event_choice_state", capabilities.get("event_choice_state") is True,
              "Deploy the current Lua bridge to expose native event availability and selection feedback.")
        check("enemy_hostility", capabilities.get("enemy_hostility") is True,
              "Deploy the current Lua bridge to expose native hostility and reject non-hostile weapon targets.")
        for name in ("upgrade_rules", "fuel_recovery"):
            check(name, capabilities.get(name) is True,
                  "Build/install native protocol 5 and deploy the current Lua bridge.")
        check("sector_navigation", capabilities.get("sector_navigation") is True,
              "Install the native neighboring-sector routing repair and current Lua bridge.")
        check("sector_navigation_version", type(economy.get("sector_navigation_version")) is int
              and economy["sector_navigation_version"] == 1,
              "Native economy must identify sector navigation version 1 for ruleset v5.")
        check("beacon_navigation", capabilities.get("beacon_navigation") is True,
              "Install the native beacon readiness repair and current Lua bridge.")
        check("beacon_navigation_version", type(economy.get("beacon_navigation_version")) is int
              and economy["beacon_navigation_version"] == 1,
              "Native economy must identify beacon navigation version 1 for ruleset v6.")
        navigation = economy.get("navigation") or {}
        for name in ("can_jump", "enemy_defeat_pending"):
            check(f"navigation.{name}", isinstance(navigation.get(name), bool),
                  "Native navigation readiness and pending defeat state must be recorded.")
        if full_game:
            check("victory", capabilities.get("victory") is True,
                  "Full-game win reporting requires the native victory binding.")

    return {"ready": all(c["ok"] for c in checks), "user_folder": str(save),
            "game_dir": str(game) if game else None,
            "capabilities": capabilities, "checks": checks}
