"""Load explicitly selected local environment files without evaluating their contents."""
from __future__ import annotations

import os
import re
from pathlib import Path


def load_env_file(path: str | Path, *, override: bool = False) -> list[str]:
    """Load simple KEY=value or KEY="value" lines; return names only, never secrets.

    Values are literal: no shell execution or variable interpolation. Existing process
    environment wins unless the caller explicitly requests an override.
    """
    source = Path(path).expanduser()
    values = {}
    for number, original in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid environment assignment at {source}:{number}")
        if value.startswith(('"', "'")):
            quote = value[0]
            close = value.find(quote, 1)
            if close < 0 or (value[close + 1:].strip() and not value[close + 1:].strip().startswith("#")):
                raise ValueError(f"Invalid quoted value at {source}:{number}")
            value = value[1:close]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        values[name] = value
    for name, value in values.items():
        if override or name not in os.environ:
            os.environ[name] = value
    return list(values)
