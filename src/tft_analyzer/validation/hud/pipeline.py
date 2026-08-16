from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tft_analyzer.core.enums import EventQuality
from tft_analyzer.storage import (
    find_latest_tracked_hud_file,
    iter_game_events,
    iter_tracked_hud_states,
)

from .validator import HUDEventValidator, HUDEventValidatorSettings


def _find_latest_event_file(
    match_dir: Path,
    pattern: str,
) -> Path:
    events_dir = match_dir / "events"
    candidates = [
        p
        for p in events_dir.glob(pattern)
        if "_summary" not in p.name
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No event files matching {pattern!r} in {events_dir}"
        )

    def key(path: Path):
        import re
        matches = list(re.finditer(r"(\d+)\.(\d+)\.(\d+)", path.name))
        version = (
            tuple(int(x) for x in matches[-1].groups())
            if matches
            else (0, 0, 0)
        )
        return (*version, path.stat().st_mtime)

    return max(candidates, key=key)


def validate_match_hud_events(
    match_dir: Path | str,
    settings: HUDEventValidatorSettings,
    *,
    events_path: Path | str | None = None,
    states_path: Path | str | None = None,
    events_glob: str = "hud-event-detector-*.jsonl",
    states_glob: str = "hud-state-tracker-*.jsonl",
) -> dict[str, object]:
    match_dir = Path(match_dir)

    if events_path is None:
        events_path = _find_latest_event_file(
            match_dir,
            events_glob,
        )
    events_path = Path(events_path)

    if states_path is None:
        states_path = find_latest_tracked_hud_file(
            match_dir,
            pattern=states_glob,
        )
    states_path = Path(states_path)

    states = list(iter_tracked_hud_states(states_path))
    states_by_id = {state.state_id: state for state in states}

    validator = HUDEventValidator(
        settings,
        states_by_id=states_by_id,
    )

    events = list(iter_game_events(events_path))
    validations = [
        validator.validate(event)
        for event in events
    ]

    out_dir = match_dir / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_version = (
        settings.producer_version.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )

    validations_path = out_dir / f"{safe_version}.jsonl"
    summary_path = out_dir / f"{safe_version}_summary.json"

    tmp = validations_path.with_suffix(validations_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for validation in validations:
            f.write(
                json.dumps(
                    validation.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp.replace(validations_path)

    quality_counts: dict[str, int] = defaultdict(int)
    reason_counts: dict[str, int] = defaultdict(int)
    field_quality = {
        field: defaultdict(int)
        for field in ("stage", "level", "xp", "gold", "hp", "shop")
    }
    field_apply = {
        field: {"apply": 0, "skip": 0}
        for field in ("stage", "level", "xp", "gold", "hp", "shop")
    }

    for validation in validations:
        q = validation.quality.value
        quality_counts[q] += 1
        field_quality[validation.field][q] += 1

        for reason in validation.reasons:
            reason_counts[reason] += 1

        if validation.field in field_apply:
            key = "apply" if validation.apply_to_state else "skip"
            field_apply[validation.field][key] += 1

    summary = {
        "schema_version": 1,
        "validator_version": settings.producer_version,
        "input_events_path": str(events_path),
        "input_states_path": str(states_path),
        "event_count": len(events),
        "validation_count": len(validations),
        "quality_counts": dict(quality_counts),
        "reason_counts": dict(reason_counts),
        "field_quality_counts": {
            field: dict(counts)
            for field, counts in field_quality.items()
        },
        "field_apply_recommendations": field_apply,
        "validations_path": str(validations_path),
    }

    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_summary.replace(summary_path)

    summary["summary_path"] = str(summary_path)
    return summary
