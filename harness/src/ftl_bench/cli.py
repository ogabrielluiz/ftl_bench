"""`ftlbench` — the command-line entry point for the FTL agent benchmark.

Thin dispatcher over the existing runner/CLI so `pip install ftl-bench` gives a runnable
benchmark without anyone touching `adapter/`. The runnable pieces (the runner, the agents,
the per-turn play CLI) plus the `scenarios/` and `prompts/` data are bundled into the wheel
under `ftl_bench/_bundled/`, preserving the repo's `adapter/ + scenarios/ + prompts/` layout
so each module's own `REPO = __file__.parent.parent` path logic keeps working unchanged. When
run from a source checkout (no `_bundled/`), we fall back to the repo root.

Commands:
  ftlbench run   [args...]   run the scenario suite (forwards to run_benchmark)
  ftlbench play  <cmd> [..]  one turn-based action / observation (forwards to play_cli)
  ftlbench install-mod [..]  install the prebuilt bench Hyperspace mod into FTL (see below)
  ftlbench version           print the package version
  ftlbench doctor            check the local installation without changing it
  ftlbench dashboard         serve the read-only dashboard
  ftlbench report <run-dir>  recompute and export recorded results
  ftlbench deploy-bridge     deploy the bridge script, retaining a backup
"""
from __future__ import annotations

import sys
from pathlib import Path

USAGE = """ftlbench — FTL agent benchmark

usage:
  ftlbench run   [--agent scripted|random|llm] [--tier ...] [--max-instances N] ...
  ftlbench play  <obs|reset|jump|fire|...> [args...]
  ftlbench visual [--model gpt-6.1-sol] [--mode image|hybrid] [--seed 1] ...
  ftlbench install-mod [--url <release-asset>]
  ftlbench version
  ftlbench doctor [--backend anthropic|openai|jev|claude-cli|codex] [--live] [--full-game] [--json]
  ftlbench dashboard [--runs <directory>] [--suite <path>] [--port 8765]
  ftlbench report <run-directory> [--json] [--output <path>] [--legacy-suite <path>]
  ftlbench deploy-bridge
  ftlbench install-native --dll <built.dll> --manifest <native-build.json> [--game-dir <folder>]

`ftlbench run --help` / `ftlbench play` show the full per-command options.
"""


def _bench_root() -> Path:
    """The directory that holds `adapter/`, `scenarios/`, `prompts/`, `mod/`, `scripts/`. From a
    source checkout we prefer the live repo dirs (so edits show up with no rebuild); an installed
    wheel falls back to the copy vendored next to this package under `_bundled/`."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "adapter" / "run_benchmark.py").exists():
            return parent
    bundled = here.parent / "_bundled"
    if (bundled / "adapter" / "run_benchmark.py").exists():
        return bundled
    raise SystemExit(
        "ftlbench: cannot locate the bundled adapter/ — reinstall the package "
        "(`pip install --force-reinstall ftl-bench`) or run from a source checkout."
    )


def _adapter_on_path() -> Path:
    """Put the (bundled or source) adapter dir on sys.path so its modules import by bare name,
    exactly as they do under `uv run python ../adapter/...`. Returns the bench root."""
    root = _bench_root()
    adapter = str(root / "adapter")
    if adapter not in sys.path:
        sys.path.insert(0, adapter)
    return root


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("ftl-bench")
    except Exception:  # noqa: BLE001 — not installed (running from a raw checkout)
        return "0.0.0+local"


def _install_mod(rest: list[str]) -> None:
    """Place the prebuilt bench Hyperspace mod where FTL loads it. The prebuilt artifact is
    published as a GitHub release asset (so users never build); pass its URL with --url. Until
    that release exists, this reports the target locations and the build-from-source fallback."""
    import argparse
    from ftl_bench.session import ftl_user_folder

    ap = argparse.ArgumentParser(prog="ftlbench install-mod")
    ap.add_argument("--url", default=None,
                    help="URL of the prebuilt mod release asset to download into the FTL folder")
    args = ap.parse_args(rest)

    save = ftl_user_folder()
    print(f"FTL user folder: {save}")
    print(f"  exists: {save.exists()}")
    if not args.url:
        print(
            "\nNo --url given. The prebuilt bench mod is distributed as a GitHub release asset;\n"
            "once that release exists, run:\n"
            "  ftlbench install-mod --url <release-asset-url>\n"
            "Until then, build + install from source via scripts/setup_pc.sh."
        )
        return

    import urllib.request
    dest = save / Path(args.url).name
    print(f"\ndownloading {args.url}\n  -> {dest}")
    save.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(args.url, dest)  # noqa: S310 — user-supplied release URL
    print("done. (Hyperspace patching of FTLGame.exe is still handled by the installer/setup script.)")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--env-file" in argv:
        from ftl_bench.config import load_env_file
        at = argv.index("--env-file")
        if at + 1 >= len(argv):
            raise SystemExit("--env-file requires a path")
        try:
            load_env_file(argv[at + 1])
        except (OSError, ValueError) as error:
            raise SystemExit(str(error)) from error
        del argv[at:at + 2]
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return

    cmd, rest = argv[0], argv[1:]
    if cmd == "version":
        print(f"ftlbench {_version()}")
        return
    if cmd == "install-mod":
        _install_mod(rest)
        return
    if cmd == "report":
        import argparse
        from ftl_bench.reporting import load_run_report, render_run_report
        ap = argparse.ArgumentParser(prog="ftlbench report")
        ap.add_argument("run_directory")
        ap.add_argument("--json", action="store_true", help="print the complete machine-readable report")
        ap.add_argument("--output", help="write the report to this explicit path instead of stdout")
        ap.add_argument("--legacy-suite", help="explicit scenario fallback for legacy files without embedded definitions")
        args = ap.parse_args(rest)
        try:
            report = load_run_report(args.run_directory, legacy_suite=args.legacy_suite)
            rendered = render_run_report(report, as_json=args.json)
            if args.output:
                Path(args.output).write_text(rendered, encoding="utf-8")
            else:
                print(rendered, end="")
        except (OSError, ValueError, KeyError, TypeError) as error:
            ap.error(str(error))
        return
    if cmd == "doctor":
        import argparse
        import json
        from ftl_bench.doctor import inspect_installation
        ap = argparse.ArgumentParser(prog="ftlbench doctor")
        ap.add_argument("--backend", choices=["anthropic", "claude-cli", "codex", "openai", "jev"])
        ap.add_argument("--game-dir")
        ap.add_argument("--live", action="store_true")
        ap.add_argument("--full-game", action="store_true")
        ap.add_argument("--json", action="store_true")
        args = ap.parse_args(rest)
        result = inspect_installation(backend=args.backend, game_dir=args.game_dir,
                                     live=args.live, full_game=args.full_game)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for check in result["checks"]:
                print(f"{'OK' if check['ok'] else 'MISSING'} {check['name']}: {check['detail']}")
            print("Ready." if result["ready"] else "Resolve the missing checks before running.")
        if not result["ready"]:
            raise SystemExit(1)
        return
    if cmd == "dashboard":
        import argparse
        import os
        ap = argparse.ArgumentParser(prog="ftlbench dashboard")
        ap.add_argument("--runs")
        ap.add_argument("--suite")
        ap.add_argument("--port", type=int, default=8765)
        args = ap.parse_args(rest)
        if not 1 <= args.port <= 65535:
            ap.error("--port must be between 1 and 65535")
        if args.runs:
            os.environ["FTL_BENCH_DIR"] = str(Path(args.runs).resolve())
        if args.suite:
            os.environ["FTL_SUITE"] = str(Path(args.suite).resolve())
        os.environ["FTL_LIVE_PORT"] = str(args.port)
        _adapter_on_path()
        import ftl_live
        ftl_live.main()
        return
    if cmd == "deploy-bridge":
        if rest:
            raise SystemExit("ftlbench deploy-bridge takes no arguments")
        import shutil
        from datetime import datetime, timezone
        from uuid import uuid4
        from ftl_bench.session import ftl_user_folder
        source = _bench_root() / "mod/ftl_bench_bridge/dev/ftl_bench_dev.lua"
        save = ftl_user_folder()
        save.mkdir(parents=True, exist_ok=True)
        dest = save / source.name
        if dest.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = save / "ftlbench-backups" / f"{stamp}-{uuid4().hex[:8]}-{dest.name}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup)
            print(f"Previous bridge retained at {backup}")
        temporary = save / f"{dest.name}.{uuid4().hex}.tmp"
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(dest)
        finally:
            temporary.unlink(missing_ok=True)
        (save / "ftl_bench_reload").write_text("", encoding="utf-8")
        print(f"Bridge deployed to {dest}. FTL reloads it on the next bridge tick.")
        return

    if cmd == "install-native":
        import argparse
        from ftl_bench.installation import install_native
        ap = argparse.ArgumentParser(prog="ftlbench install-native")
        ap.add_argument("--dll", required=True)
        ap.add_argument("--manifest", required=True)
        ap.add_argument("--game-dir")
        args = ap.parse_args(rest)
        try:
            installed = install_native(args.dll, args.manifest, args.game_dir)
        except (OSError, ValueError) as error:
            ap.error(str(error))
        print(f"Native protocol {installed['native_protocol']} installed in {installed['game_dir']}.")
        print(f"Previous files retained at {installed['backup']}.")
        print("Deploy the bridge with ftlbench deploy-bridge, then launch FTL through Steam.")
        return

    if cmd == "visual":
        _adapter_on_path()
        import run_visual
        run_visual.main(rest)
    elif cmd == "run":
        _adapter_on_path()
        import run_benchmark
        sys.argv = ["ftlbench run", *rest]
        run_benchmark.main()
    elif cmd == "play":
        _adapter_on_path()
        import play_cli
        sys.argv = ["ftlbench play", *rest]
        play_cli.main()
    else:
        print(f"ftlbench: unknown command {cmd!r}\n\n{USAGE}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
