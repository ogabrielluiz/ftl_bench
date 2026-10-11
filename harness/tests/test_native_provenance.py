import hashlib
import importlib.util
from pathlib import Path
import subprocess

import pytest


def _helper():
    from ftl_bench.cli import _bench_root

    spec = importlib.util.spec_from_file_location(
        "write_native_provenance", _bench_root() / "scripts/write_native_provenance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_covers_untracked_patched_header_and_exact_file_bytes(tmp_path):
    source = tmp_path / "native"
    source.mkdir()
    tracked = source / "tracked.cpp"
    tracked.write_bytes(b"base\n")
    for args in (["init", "--quiet"], ["add", "tracked.cpp"],
                 ["-c", "user.name=Benchmark Test", "-c", "user.email=test@example.invalid",
                  "commit", "--quiet", "-m", "base"]):
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True)
    tracked.write_bytes(b"changed\n")
    header = source / "Benchmark_Routing.h"
    header.write_bytes(b"actual neighbor indices\n")
    patch = tmp_path / "source.patch"
    patch.write_text("diff --git a/tracked.cpp b/tracked.cpp\n"
                     "diff --git a/Benchmark_Routing.h b/Benchmark_Routing.h\n")

    diff, hashes = _helper().source_snapshot(source, patch)
    assert b"+changed" in diff
    assert b"diff --git a/Benchmark_Routing.h b/Benchmark_Routing.h" in diff
    assert b"+actual neighbor indices" in diff
    assert hashes == {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (tracked, header)}
    header.write_bytes(b"different native behavior\n")
    new_diff, new_hashes = _helper().source_snapshot(source, patch)
    assert new_diff != diff
    assert new_hashes[header.name] != hashes[header.name]


def test_snapshot_refuses_patch_path_outside_source(tmp_path):
    source = tmp_path / "native"
    source.mkdir()
    (tmp_path / "outside.h").write_bytes(b"outside\n")
    patch = tmp_path / "source.patch"
    patch.write_text("diff --git a/../outside.h b/../outside.h\n")
    with pytest.raises(ValueError, match="invalid patched source path"):
        _helper().source_snapshot(source, patch)


def _run_provenance_cli(tmp_path, monkeypatch, *, capabilities=None, built_at=None):
    import json
    import sys
    from datetime import datetime, timezone

    helper = _helper()
    root = tmp_path / "repo"
    (root / "native").mkdir(parents=True)
    patch = root / "native/source.patch"
    patch.write_bytes(b"exact distributed patch\n")
    manifest = {"repository": "https://example.invalid/native", "patch": "native/source.patch",
                "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(), "native_protocol": 5}
    manifest.update(capabilities or {})
    (root / "native/manifest.json").write_text(json.dumps(manifest))
    dll = tmp_path / "produced.dll"
    dll.write_bytes(b"exact produced DLL")
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "provenance.json"
    monkeypatch.setattr(helper, "__file__", str(root / "scripts/write_native_provenance.py"))
    source_calls = []

    def snapshot(actual_source, actual_patch):
        source_calls.append((actual_source, actual_patch))
        return b"canonical tracked plus untracked source diff", {"header.h": "exact-header-hash"}

    monkeypatch.setattr(helper, "source_snapshot", snapshot)

    def checked_command(argv, **kwargs):
        if argv == ["git", "rev-parse", "HEAD"]:
            assert kwargs["cwd"] == source
            return "original-source-commit\n"
        assert argv == ["docker", "image", "inspect", "ghcr.io/ftl-hyperspace/hs-devcontainer:v2",
                        "--format", "{{.Id}}"]
        return "sha256:original-toolchain-image\n"

    monkeypatch.setattr(helper.subprocess, "check_output", checked_command)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(helper, "datetime", FixedDatetime)
    argv = ["write_native_provenance.py", "--source", str(source), "--dll", str(dll),
            "--output", str(output), "--build-command", "original tested build command"]
    if built_at is not None:
        argv += ["--built-at", built_at]
    monkeypatch.setattr(sys, "argv", argv)
    helper.main()
    result = json.loads(output.read_text())
    assert source_calls == [(source, patch)]
    assert result["source_diff_sha256"] == hashlib.sha256(b"canonical tracked plus untracked source diff").hexdigest()
    assert result["source_files_sha256"] == {"header.h": "exact-header-hash"}
    assert result["dll_sha256"] == hashlib.sha256(dll.read_bytes()).hexdigest()
    assert result["toolchain"]["build_command"] == "original tested build command"
    return result


def test_cli_retains_original_build_time_and_copies_manifest_capabilities(tmp_path, monkeypatch):
    capabilities = {"visual_io_version": 1, "visual_clock_version": 2,
                    "fixed_step_numerator": 1, "fixed_step_denominator": 60,
                    "fresh_start_seed": True, "fresh_seed_contract_version": 3,
                    "fresh_seed_contract": "fresh-start-seed-v3"}
    result = _run_provenance_cli(tmp_path, monkeypatch, capabilities=capabilities,
                                 built_at="2026-10-10T23:51:44.240528+00:00")
    assert result["built_at"] == "2026-10-10T23:51:44.240528+00:00"
    assert result["provenance_generated_at"] == "2026-10-11T12:00:00+00:00"
    assert {key: result[key] for key in capabilities} == capabilities
    assert not any(key in result for key in ("classification", "not_installed", "no_live_execution", "benchmark_eligible"))


def test_default_cli_records_build_now_and_does_not_invent_seed_capability(tmp_path, monkeypatch):
    result = _run_provenance_cli(tmp_path, monkeypatch, capabilities={"visual_clock_version": 2})
    assert result["built_at"] == result["provenance_generated_at"] == "2026-10-11T12:00:00+00:00"
    assert result["visual_clock_version"] == 2
    assert not any(key in result for key in ("fresh_start_seed", "fresh_seed_contract_version", "fresh_seed_contract"))


def test_original_build_offset_is_normalized_without_changing_the_instant():
    assert _helper().original_build_timestamp("2026-10-10T20:51:44.240528-03:00") == "2026-10-10T23:51:44.240528+00:00"


@pytest.mark.parametrize("value", ["", "yesterday", "2026-10-10", "2026-10-10T23:51:44", "2026-13-10T00:00:00Z"])
def test_original_build_timestamp_rejects_invalid_or_ambiguous_time(value):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="ISO 8601|timezone"):
        _helper().original_build_timestamp(value)


def test_cli_invalid_build_time_fails_before_snapshot_commands_or_output(tmp_path, monkeypatch):
    import sys

    helper = _helper()
    output = tmp_path / "provenance.json"
    monkeypatch.setattr(sys, "argv", ["write_native_provenance.py", "--source", str(tmp_path),
                                     "--dll", str(tmp_path / "absent.dll"), "--output", str(output),
                                     "--built-at", "2026-10-10T23:51:44"])
    monkeypatch.setattr(helper.subprocess, "check_output", lambda *args, **kwargs: pytest.fail("unexpected command"))
    monkeypatch.setattr(helper, "source_snapshot", lambda *args: pytest.fail("unexpected source snapshot"))
    with pytest.raises(SystemExit) as error:
        helper.main()
    assert error.value.code == 2
    assert not output.exists()
