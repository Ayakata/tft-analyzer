from __future__ import annotations

import json
import re
from pathlib import Path

from tft_analyzer.core.models import TrackedHUDState


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def iter_tracked_hud_states(path: Path | str):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tracked HUD state file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield TrackedHUDState.model_validate(json.loads(line))


def _version_key(path: Path) -> tuple[int, int, int, float]:
    matches = list(_VERSION_RE.finditer(path.name))
    if matches:
        version = tuple(int(x) for x in matches[-1].groups())
    else:
        version = (0, 0, 0)
    return (*version, path.stat().st_mtime)


def find_latest_tracked_hud_file(
    match_dir: Path | str,
    *,
    pattern: str = "hud-state-tracker-*.jsonl",
) -> Path:
    match_dir = Path(match_dir)
    tracking_dir = match_dir / "tracking"

    candidates = [
        p
        for p in tracking_dir.glob(pattern)
        if "_decisions" not in p.name
        and "_summary" not in p.name
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No tracked HUD states matching {pattern!r} in {tracking_dir}"
        )

    return max(candidates, key=_version_key)
