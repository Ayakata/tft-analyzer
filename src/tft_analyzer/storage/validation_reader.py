from __future__ import annotations

import json
import re
from pathlib import Path

from tft_analyzer.core.models import EventValidation


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def iter_event_validations(path: Path | str):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Event validation file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield EventValidation.model_validate(json.loads(line))


def _version_key(path: Path) -> tuple[int, int, int, float]:
    matches = list(_VERSION_RE.finditer(path.name))
    if matches:
        version = tuple(int(x) for x in matches[-1].groups())
    else:
        version = (0, 0, 0)
    return (*version, path.stat().st_mtime)


def find_latest_validation_file(
    match_dir: Path | str,
    *,
    pattern: str = "hud-event-validator-*.jsonl",
) -> Path:
    validation_dir = Path(match_dir) / "validation"

    candidates = [
        p
        for p in validation_dir.glob(pattern)
        if "_summary" not in p.name
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No validation files matching {pattern!r} in {validation_dir}"
        )

    return max(candidates, key=_version_key)
