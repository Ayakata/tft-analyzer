from __future__ import annotations

import json
import re
from pathlib import Path

from tft_analyzer.core.models import Observation


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def iter_observations(path: Path | str):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Observation file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield Observation.model_validate(json.loads(line))


def _version_key(path: Path) -> tuple[int, int, int, float]:
    matches = list(_VERSION_RE.finditer(path.name))
    if matches:
        m = matches[-1]
        version = tuple(int(x) for x in m.groups())
    else:
        version = (0, 0, 0)
    return (*version, path.stat().st_mtime)


def find_latest_observation_file(
    match_dir: Path | str,
    *,
    pattern: str = "hud-rapidocr-*.jsonl",
) -> Path:
    match_dir = Path(match_dir)
    observations_dir = match_dir / "observations"

    candidates = [
        p
        for p in observations_dir.glob(pattern)
        if "_attempts" not in p.name
        and "_summary" not in p.name
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No observation files matching {pattern!r} in {observations_dir}"
        )

    return max(candidates, key=_version_key)
