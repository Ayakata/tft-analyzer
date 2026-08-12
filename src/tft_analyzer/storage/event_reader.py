from __future__ import annotations

import json
from pathlib import Path

from tft_analyzer.core.models import GameEvent


def iter_game_events(path: Path | str):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Game event file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield GameEvent.model_validate(json.loads(line))
