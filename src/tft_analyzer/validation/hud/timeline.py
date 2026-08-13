from __future__ import annotations

from pathlib import Path

from tft_analyzer.storage import iter_event_validations, iter_game_events


def format_validation_timeline(
    events_path: Path | str,
    validations_path: Path | str,
    *,
    limit: int | None = None,
) -> str:
    events = {
        event.event_id: event
        for event in iter_game_events(events_path)
    }

    lines = [
        " time(s)   event            quality            apply  from/to conf   reasons",
        "----------------------------------------------------------------------------",
    ]

    count = 0
    for validation in iter_event_validations(validations_path):
        if limit is not None and count >= limit:
            break

        event = events.get(validation.event_id)
        event_type = event.event_type.value if event else "unknown"

        fc = (
            f"{validation.from_confidence:.3f}"
            if validation.from_confidence is not None
            else "?"
        )
        tc = (
            f"{validation.to_confidence:.3f}"
            if validation.to_confidence is not None
            else "?"
        )

        lines.append(
            f"{validation.event_timestamp_s:8.1f}  "
            f"{event_type:<16} "
            f"{validation.quality.value:<18} "
            f"{('YES' if validation.apply_to_state else 'NO'):<6} "
            f"{fc}/{tc:<7} "
            f"{','.join(validation.reasons)}"
        )
        count += 1

    return "\n".join(lines)
