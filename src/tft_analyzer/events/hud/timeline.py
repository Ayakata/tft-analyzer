from __future__ import annotations

from pathlib import Path

from tft_analyzer.core.enums import EventType
from tft_analyzer.core.models import GameEvent
from tft_analyzer.storage import iter_game_events


def _change_text(event: GameEvent) -> str:
    payload = event.payload
    before = payload.get("from")
    after = payload.get("to")

    if event.event_type == EventType.ROUND_START:
        if before is None:
            return f"-> {after['stage']}-{after['round']}"
        return (
            f"{before['stage']}-{before['round']}"
            f" -> {after['stage']}-{after['round']}"
        )

    if event.event_type == EventType.LEVEL_CHANGED:
        if before is None:
            return f"-> L{after['level']}"
        return f"L{before['level']} -> L{after['level']}"

    if event.event_type == EventType.XP_CHANGED:
        def xp(v):
            return f"{v['current']}/{v['required']}"

        if before is None:
            return f"-> {xp(after)}"
        return f"{xp(before)} -> {xp(after)}"

    if event.event_type == EventType.GOLD_CHANGED:
        if before is None:
            return f"-> {after['gold']}"
        delta = payload.get("delta")
        delta_text = f" ({delta:+d})" if isinstance(delta, int) else ""
        return f"{before['gold']} -> {after['gold']}{delta_text}"

    return f"{before!r} -> {after!r}"


def format_hud_event_timeline(
    events_path: Path | str,
    *,
    limit: int | None = None,
) -> str:
    lines = [
        " time(s)   event            change                         conf  window",
        "-----------------------------------------------------------------------",
    ]

    count = 0
    for event in iter_game_events(events_path):
        if limit is not None and count >= limit:
            break

        window = event.payload.get("transition_window", {})
        width_s = float(window.get("width_s", 0.0))
        warning = "!" if event.payload.get("timing_warning") else ""

        lines.append(
            f"{event.timestamp_s:8.1f}  "
            f"{event.event_type.value:<16} "
            f"{_change_text(event):<30} "
            f"{event.confidence:5.3f}  "
            f"{width_s:5.1f}s{warning}"
        )
        count += 1

    lines.append("")
    lines.append("! = transition window exceeds configured timing warning threshold")
    return "\n".join(lines)
