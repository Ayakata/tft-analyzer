from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tft_analyzer.storage import (
    find_latest_tracked_hud_file,
    iter_tracked_hud_states,
)

from .detector import HUDEventDetector, HUDEventDetectorSettings


def detect_match_hud_events(
    match_dir: Path | str,
    settings: HUDEventDetectorSettings,
    *,
    states_path: Path | str | None = None,
    states_glob: str = "hud-state-tracker-*.jsonl",
) -> dict[str, object]:
    match_dir = Path(match_dir)

    if states_path is None:
        states_path = find_latest_tracked_hud_file(
            match_dir,
            pattern=states_glob,
        )
    states_path = Path(states_path)

    detector = HUDEventDetector(settings)

    events = []
    state_count = 0

    for state in iter_tracked_hud_states(states_path):
        state_count += 1
        events.extend(detector.ingest_state(state))

    out_dir = match_dir / "events"
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_version = (
        settings.producer_version.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )

    events_path = out_dir / f"{safe_version}.jsonl"
    summary_path = out_dir / f"{safe_version}_summary.json"

    tmp_events = events_path.with_suffix(events_path.suffix + ".tmp")
    with tmp_events.open("w", encoding="utf-8", newline="\n") as f:
        for event in events:
            f.write(
                json.dumps(
                    event.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp_events.replace(events_path)

    type_counts: dict[str, int] = defaultdict(int)
    field_counts: dict[str, int] = defaultdict(int)
    field_window_sum: dict[str, float] = defaultdict(float)
    field_window_max: dict[str, float] = defaultdict(float)
    field_conf_sum: dict[str, float] = defaultdict(float)
    timing_warning_counts: dict[str, int] = defaultdict(int)

    for event in events:
        event_type = event.event_type.value
        field = str(event.payload.get("field", "unknown"))
        window = event.payload.get("transition_window", {})
        width_s = float(window.get("width_s", 0.0))

        type_counts[event_type] += 1
        field_counts[field] += 1
        field_window_sum[field] += width_s
        field_window_max[field] = max(
            field_window_max[field],
            width_s,
        )
        field_conf_sum[field] += float(event.confidence)

        if bool(event.payload.get("timing_warning", False)):
            timing_warning_counts[field] += 1

    field_stats = {}
    for field in ("stage", "level", "xp", "gold", "hp", "shop"):
        count = field_counts[field]
        field_stats[field] = {
            "event_count": count,
            "mean_confidence": (
                field_conf_sum[field] / count if count else 0.0
            ),
            "mean_transition_window_s": (
                field_window_sum[field] / count if count else 0.0
            ),
            "max_transition_window_s": field_window_max[field],
            "timing_warning_count": timing_warning_counts[field],
        }

    summary = {
        "schema_version": 1,
        "producer_version": settings.producer_version,
        "input_states_path": str(states_path),
        "input_state_count": state_count,
        "event_count": len(events),
        "event_type_counts": dict(type_counts),
        "field_stats": field_stats,
        "events_path": str(events_path),
    }

    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_summary.replace(summary_path)

    summary["summary_path"] = str(summary_path)
    return summary
