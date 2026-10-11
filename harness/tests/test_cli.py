"""Unit tests for the `ftlbench` command-line entry point (`ftl_bench.cli`).

These exercise the pure-Python dispatch surface only: `_bench_root`, `_version`,
and `main()` for version / help / unknown-command / install-mod (no --url). They
deliberately never touch `run` or `play`, which would drive the real game; the
one install-mod path that would shell out to the network monkeypatches
`urllib.request.urlretrieve` so nothing leaves the machine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ftl_bench import cli


# --------------------------------------------------------------------------- #
# _bench_root
# --------------------------------------------------------------------------- #

def test_bench_root_returns_path():
    root = cli._bench_root()
    assert isinstance(root, Path)


def test_bench_root_contains_adapter_run_benchmark():
    # From a source checkout, _bench_root must point at the dir that actually
    # holds adapter/run_benchmark.py — that is the whole contract.
    root = cli._bench_root()
    assert (root / "adapter" / "run_benchmark.py").exists()


def test_bench_root_uses_checkout_or_adjacent_bundled_data():
    root = cli._bench_root()
    cli_file = Path(cli.__file__).resolve()
    assert root in cli_file.parents or root == cli_file.parent / "_bundled"


def test_bench_root_is_stable_across_calls():
    assert cli._bench_root() == cli._bench_root()


# --------------------------------------------------------------------------- #
# _version
# --------------------------------------------------------------------------- #

def test_version_returns_nonempty_str():
    v = cli._version()
    assert isinstance(v, str)
    assert v.strip()


def test_version_falls_back_when_metadata_missing(monkeypatch):
    # If importlib.metadata.version raises (package not installed, e.g. a raw
    # checkout), _version must degrade to the local sentinel rather than blow up.
    import importlib.metadata as md

    def _boom(_name):
        raise md.PackageNotFoundError("ftl-bench")

    monkeypatch.setattr(md, "version", _boom)
    assert cli._version() == "0.0.0+local"


# --------------------------------------------------------------------------- #
# main() — version
# --------------------------------------------------------------------------- #

def test_main_version_prints_banner(capsys):
    rv = cli.main(["version"])
    assert rv is None  # main returns None, never an exit code
    out = capsys.readouterr().out
    assert out.startswith("ftlbench ")
    assert cli._version() in out


def test_main_version_uses_version_helper(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_version", lambda: "9.9.9-test")
    cli.main(["version"])
    out = capsys.readouterr().out
    assert "ftlbench 9.9.9-test" in out


# --------------------------------------------------------------------------- #
# main() — usage banner (no args / -h / --help)
# --------------------------------------------------------------------------- #

def test_main_no_args_prints_usage(capsys):
    rv = cli.main([])
    assert rv is None
    out = capsys.readouterr().out
    assert out.strip() == cli.USAGE.strip()


def test_main_dash_h_prints_usage(capsys):
    cli.main(["-h"])
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "ftlbench" in out


def test_main_long_help_prints_usage(capsys):
    cli.main(["--help"])
    out = capsys.readouterr().out
    assert out.strip() == cli.USAGE.strip()


def test_help_lists_the_four_commands():
    # Sanity-check the banner advertises every dispatchable verb.
    for verb in ("run", "play", "install-mod", "version"):
        assert verb in cli.USAGE


def test_main_uses_argv_from_sys_when_none(monkeypatch, capsys):
    # main(None) must read sys.argv[1:].
    monkeypatch.setattr(cli.sys, "argv", ["ftlbench", "version"])
    cli.main(None)
    out = capsys.readouterr().out
    assert out.startswith("ftlbench ")


# --------------------------------------------------------------------------- #
# main() — unknown command
# --------------------------------------------------------------------------- #

def test_main_unknown_command_raises_systemexit_2(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["frobnicate"])
    assert exc.value.code == 2


def test_main_unknown_command_writes_to_stderr(capsys):
    with pytest.raises(SystemExit):
        cli.main(["frobnicate"])
    captured = capsys.readouterr()
    assert "unknown command" in captured.err
    assert "frobnicate" in captured.err
    # The usage banner is echoed alongside the error.
    assert "usage:" in captured.err
    # Nothing should land on stdout for an error.
    assert captured.out == ""


# --------------------------------------------------------------------------- #
# main() — install-mod (no --url): the safe, no-network path
# --------------------------------------------------------------------------- #

def test_install_mod_no_url_prints_folder_and_guidance(monkeypatch, capsys, tmp_path):
    # Point the FTL user folder at a throwaway dir so we never read the real one.
    fake = tmp_path / "FasterThanLight"
    monkeypatch.setenv("FTL_SAVE_DIR", str(fake))

    rv = cli.main(["install-mod"])
    assert rv is None  # exit 0, no SystemExit

    out = capsys.readouterr().out
    assert "FTL user folder:" in out
    assert str(fake) in out
    assert "exists: False" in out  # the throwaway dir does not exist
    # Guidance for the not-yet-published release asset path.
    assert "No --url given" in out
    assert "ftlbench install-mod --url" in out


def test_install_mod_no_url_does_not_create_folder(monkeypatch, capsys, tmp_path):
    # The no-url branch only *reports*; it must not create or download anything.
    fake = tmp_path / "FasterThanLight"
    monkeypatch.setenv("FTL_SAVE_DIR", str(fake))
    cli.main(["install-mod"])
    capsys.readouterr()
    assert not fake.exists()


def test_install_mod_no_url_reports_existing_folder(monkeypatch, capsys, tmp_path):
    fake = tmp_path / "FasterThanLight"
    fake.mkdir()
    monkeypatch.setenv("FTL_SAVE_DIR", str(fake))
    cli.main(["install-mod"])
    out = capsys.readouterr().out
    assert "exists: True" in out


def test_install_mod_never_downloads_on_no_url(monkeypatch, capsys, tmp_path):
    # Guard rail: assert urlretrieve is never reached on the no-url path.
    import urllib.request

    def _forbidden(*_a, **_k):  # pragma: no cover - must not be called
        raise AssertionError("urlretrieve must not run without --url")

    monkeypatch.setattr(urllib.request, "urlretrieve", _forbidden)
    monkeypatch.setenv("FTL_SAVE_DIR", str(tmp_path / "FasterThanLight"))
    cli.main(["install-mod"])
    capsys.readouterr()


def test_install_mod_unknown_flag_exits_2(monkeypatch, capsys, tmp_path):
    # argparse inside _install_mod rejects unknown flags with SystemExit(2).
    monkeypatch.setenv("FTL_SAVE_DIR", str(tmp_path / "FasterThanLight"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["install-mod", "--nope"])
    assert exc.value.code == 2


def test_install_mod_with_url_downloads_to_folder(monkeypatch, capsys, tmp_path):
    # The --url path: monkeypatch urlretrieve so nothing touches the network,
    # and verify the destination/url plumbing. The dest filename is the URL's
    # basename, dropped into the (created) FTL folder.
    fake = tmp_path / "FasterThanLight"
    monkeypatch.setenv("FTL_SAVE_DIR", str(fake))

    calls = {}

    def _fake_retrieve(url, dest):
        calls["url"] = url
        calls["dest"] = Path(dest)
        Path(dest).write_text("payload")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)

    url = "https://example.test/releases/bench-mod.ftl"
    cli.main(["install-mod", "--url", url])

    out = capsys.readouterr().out
    assert calls["url"] == url
    assert calls["dest"] == fake / "bench-mod.ftl"
    assert fake.exists()  # save.mkdir(parents=True) ran
    assert "downloading" in out
    assert "done." in out


# --------------------------------------------------------------------------- #
# Dispatch isolation: run/play must NOT execute under these tests.
# --------------------------------------------------------------------------- #

def test_run_and_play_are_not_invoked_by_other_commands(monkeypatch):
    # Belt-and-suspenders: stub the adapter-loading hook to fail loudly so any
    # accidental fall-through into the run/play branches is caught. version
    # must not trip it.
    def _boom():  # pragma: no cover - must not be called
        raise AssertionError("_adapter_on_path must not run for 'version'")

    monkeypatch.setattr(cli, "_adapter_on_path", _boom)
    cli.main(["version"])  # should not raise


def test_recover_protected_dispatch_and_json(monkeypatch, capsys, tmp_path):
    import json
    from ftl_bench import protected_game
    calls = []
    receipt = {"verified": True, "ownership_id": "owner-123"}
    def recover(backup, **kwargs):
        calls.append((backup, kwargs))
        return receipt
    monkeypatch.setattr(protected_game, "recover_protected", recover, raising=False)
    monkeypatch.setattr(cli, "_adapter_on_path", lambda: pytest.fail("Recovery must not load an action runner"))
    backup = tmp_path / "backup"
    cli.main(["recover-protected", "--backup", str(backup), "--ownership-id", "owner-123",
              "--confirm-pending-launch-cancelled"])
    assert calls == [(backup, {"ownership_id": "owner-123", "confirm_pending_launch_cancelled": True})]
    assert json.loads(capsys.readouterr().out) == receipt


@pytest.mark.parametrize("missing", ["acknowledgement", "ownership", "backup"])
def test_recover_protected_required_inputs_before_helper(monkeypatch, capsys, tmp_path, missing):
    from ftl_bench import protected_game
    monkeypatch.setattr(protected_game, "recover_protected", lambda *a, **k: pytest.fail("Recovery must not run"), raising=False)
    args = ["recover-protected"]
    if missing != "backup": args += ["--backup", str(tmp_path / "backup")]
    if missing != "ownership": args += ["--ownership-id", "owner-123"]
    if missing != "acknowledgement": args += ["--confirm-pending-launch-cancelled"]
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert "required" in capsys.readouterr().err


@pytest.mark.parametrize("failure", [OSError("read failed"), ValueError("bad ownership"), RuntimeError("FTL running")])
def test_recover_protected_helper_errors_exit_2(monkeypatch, capsys, tmp_path, failure):
    from ftl_bench import protected_game
    def recover(*args, **kwargs):
        raise failure
    monkeypatch.setattr(protected_game, "recover_protected", recover, raising=False)
    with pytest.raises(SystemExit) as error:
        cli.main(["recover-protected", "--backup", str(tmp_path / "backup"), "--ownership-id", "owner-123",
                  "--confirm-pending-launch-cancelled"])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert str(failure) in output.err and output.out == ""


def test_recover_protected_is_advertised():
    assert "recover-protected --backup <path> --ownership-id <ID> --confirm-pending-launch-cancelled" in cli.USAGE


def test_recover_protected_explicit_save_directory(monkeypatch, capsys, tmp_path):
    from ftl_bench import protected_game
    calls = []
    def recover(backup, **kwargs):
        calls.append((backup, kwargs))
        return {"verified": True}
    monkeypatch.setattr(protected_game, "recover_protected", recover, raising=False)
    backup, save = tmp_path / "incomplete-backup", tmp_path / "explicit-save"
    cli.main(["recover-protected", "--backup", str(backup), "--ownership-id", "owner-123",
              "--confirm-pending-launch-cancelled", "--save-dir", str(save)])
    assert calls == [(backup, {"ownership_id": "owner-123", "confirm_pending_launch_cancelled": True,
                              "save_directory": save})]
    assert "verified" in capsys.readouterr().out
