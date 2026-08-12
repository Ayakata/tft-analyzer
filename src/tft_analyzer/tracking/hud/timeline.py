from __future__ import annotations

import json
from pathlib import Path

from tft_analyzer.core.models import TrackedHUDState


def iter_tracked_states(path: Path | str):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield TrackedHUDState.model_validate(json.loads(line))


def _fmt(field, formatter):
    if field.value is None:
        if field.status == "stale":
            return "<stale>"
        return "?"

    text = formatter(field.value)

    if field.status == "carried":
        return f"{text}~"
    return text


def format_hud_timeline(
    states_path: Path | str,
    *,
    limit: int | None = None,
) -> str:
    lines = [
        " time(s)   stage    level      xp     gold",
        "------------------------------------------",
    ]

    count = 0
    for state in iter_tracked_states(states_path):
        if limit is not None and count >= limit:
            break

        stage = _fmt(
            state.stage,
            lambda v: f"{v['stage']}-{v['round']}",
        )
        level = _fmt(
            state.level,
            lambda v: f"L{v['level']}",
        )
        xp = _fmt(
            state.xp,
            lambda v: f"{v['current']}/{v['required']}",
        )
        gold = _fmt(
            state.gold,
            lambda v: str(v["gold"]),
        )

        lines.append(
            f"{state.timestamp_s:8.1f}  "
            f"{stage:>7}  "
            f"{level:>7}  "
            f"{xp:>7}  "
            f"{gold:>7}"
        )
        count += 1

    lines.append("")
    lines.append("~ = carried from a recent observation")
    return "\n".join(lines)
