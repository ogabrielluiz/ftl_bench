"""Unit and replay tests must never call paid providers or rely on the network."""
import urllib.request
import sys

import pytest
from ftl_bench.cli import _bench_root


# The sdist ships the adapter/bridge under _bundled instead of repo siblings.
# Resolve exactly as the installed CLI does so source-package tests remain runnable.
sys.path.insert(0, str(_bench_root() / "adapter"))


@pytest.fixture(autouse=True)
def block_unmocked_http(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Unexpected network request: mock the HTTP boundary in this test.")
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
