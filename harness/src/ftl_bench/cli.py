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
"""
from __future__ import annotations

import sys
from pathlib import Path

USAGE = """ftlbench — FTL agent benchmark

usage:
  ftlbench run   [--agent scripted|random|llm] [--tier ...] [--max-instances N] ...
  ftlbench play  <obs|reset|jump|fire|...> [args...]
  ftlbench install-mod [--url <release-asset>]
  ftlbench version

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

    if cmd == "run":
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
