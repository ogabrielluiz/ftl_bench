"""Package subprocesses must not inherit another interpreter's library selectors."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import ftl_bench

from ftl_bench.cli import _bench_root


def script(name):
    path = _bench_root() / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["smoke_package.py", "smoke_sdist.py"])
def test_actual_smoke_dispatch_removes_parent_interpreter_overrides(tmp_path, monkeypatch, name):
    module = script(name)
    resource_root = _bench_root()
    root = tmp_path / "synthetic-checkout"
    (root / "dashboard/dist/assets").mkdir(parents=True)
    monkeypatch.setattr(module, "__file__", str(root / "scripts" / name))
    monkeypatch.setenv("PYTHONHOME", "foreign-python-home")
    monkeypatch.setenv("PYTHONPATH", "foreign-checkout-path")
    monkeypatch.setenv("VIRTUAL_ENV", "foreign-venv")
    monkeypatch.setenv("__PYVENV_LAUNCHER__", "foreign-launcher")
    monkeypatch.setenv("PYTHONEXECUTABLE", "foreign-python")
    monkeypatch.setenv("UV_PYTHON", "3.14")
    artifact = tmp_path / ("release.whl" if name == "smoke_package.py" else "release.tar.gz")
    artifact.touch()

    class Archive:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, path):
            if path.startswith("ftl_bench/_bundled/"):
                relative = path.removeprefix("ftl_bench/_bundled/")
                data = (resource_root / relative).read_bytes()
                destination = root / relative
            else:
                data = (Path(ftl_bench.__file__).parent / path.removeprefix("ftl_bench/")).read_bytes()
                destination = root / "harness/src" / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            return data
        def extractall(self, destination, **kwargs):
            project = Path(destination) / "project"
            project.mkdir()
            (project / "pyproject.toml").touch()

    if name == "smoke_package.py":
        monkeypatch.setattr(module.zipfile, "ZipFile", Archive)
    else:
        monkeypatch.setattr(module.tarfile, "open", Archive)

    class CheckedDispatch(Exception):
        pass

    def dispatch(argv, **kwargs):
        assert argv[0] == "uv"
        environment = kwargs.get("env", os.environ)
        assert all(key not in environment for key in (
            "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__", "PYTHONEXECUTABLE"))
        assert environment.get("UV_PYTHON") == "3.14"
        assert environment.get("PATH") == os.environ.get("PATH")
        raise CheckedDispatch

    monkeypatch.setattr(module.subprocess, "run", dispatch)
    monkeypatch.setattr(sys, "argv", [name, "--wheel" if name == "smoke_package.py" else "--sdist", str(artifact)])
    with pytest.raises(CheckedDispatch):
        module.main()
    assert os.environ["PYTHONHOME"] == "foreign-python-home"


@pytest.mark.parametrize("name", ["smoke_package.py", "smoke_sdist.py"])
def test_real_child_and_grandchild_import_ctypes_with_clean_library_environment(tmp_path, name):
    module = script(name)
    shadow = tmp_path / "foreign-library"
    shadow.mkdir()
    (shadow / "ctypes.py").write_text("raise RuntimeError('foreign ctypes must never be imported')")
    inherited = dict(os.environ, PYTHONHOME=str(tmp_path / "absent-python-home"),
                     PYTHONPATH=str(shadow), VIRTUAL_ENV=str(tmp_path / "absent-venv"))
    cleaned = module.isolated_python_environment(inherited)
    child = """
import ctypes, json, subprocess, sys
result = subprocess.run([sys.executable, '-c', 'import ctypes,json,sys; print(json.dumps({"version":sys.version_info[:2],"ctypes":ctypes.__file__}))'], check=True, capture_output=True, text=True)
print(json.dumps({'child_version': sys.version_info[:2], 'child_ctypes': ctypes.__file__, 'grandchild': json.loads(result.stdout)}))
"""
    result = subprocess.run([sys.executable, "-c", child], env=cleaned, cwd=tmp_path,
                            capture_output=True, text=True, check=True)
    evidence = json.loads(result.stdout)
    assert evidence["child_version"] == evidence["grandchild"]["version"] == list(sys.version_info[:2])
    assert "foreign-library" not in evidence["child_ctypes"]
    assert "foreign-library" not in evidence["grandchild"]["ctypes"]
    assert inherited["PYTHONHOME"].endswith("absent-python-home")
