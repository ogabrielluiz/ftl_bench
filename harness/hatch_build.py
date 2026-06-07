"""Hatchling build hook: vendor the repo's sibling data dirs INTO the package tree so that the
wheel AND the sdist are both self-contained.

The runnable benchmark needs files that live in repo top-level dirs (adapter/, scenarios/,
prompts/, mod/, scripts/) and the README, all OUTSIDE this package root (harness/). A wheel-only
`force-include "../adapter"` can reach them when building from the repo, but the sdist cannot
(paths above the project root are not shipped, and the sdist->wheel rebuild then fails trying to
reach a `../adapter` sibling that no longer exists). So instead we copy them under
`src/ftl_bench/_bundled/` at build time and ship that as package data (declared via `artifacts`),
which both targets include cleanly without reaching above the project root.

Idempotent: when building from an unpacked sdist the siblings are absent but `_bundled/` was
already shipped, so we keep it as-is.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# repo top-level entries to vendor under src/ftl_bench/_bundled/ (preserving names so each
# module's own `REPO = __file__.parent.parent` path logic keeps resolving them).
_VENDOR = ["adapter", "scenarios", "prompts", "mod", "scripts", "README.md", "LICENSE"]
_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "runs", "dist", "build", ".venv", "node_modules", "*.log"
)


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        root = Path(self.root)                  # project root = harness/
        repo = root.parent                      # repo root: the siblings live here
        bundled = root / "src" / "ftl_bench" / "_bundled"

        if (repo / "adapter").is_dir():
            # building from the repo working tree: refresh a clean vendored copy
            if bundled.exists():
                shutil.rmtree(bundled)
            bundled.mkdir(parents=True)
            for name in _VENDOR:
                src, dst = repo / name, bundled / name
                if src.is_dir():
                    shutil.copytree(src, dst, ignore=_IGNORE)
                elif src.is_file():
                    shutil.copy2(src, dst)
        elif not (bundled / "adapter" / "run_benchmark.py").exists():
            # not in the repo and nothing was pre-vendored: cannot produce a runnable package
            raise RuntimeError(
                "ftl_bench build: neither the repo data dirs nor a pre-vendored "
                "src/ftl_bench/_bundled/ are present — build from the repo or a complete sdist."
            )
