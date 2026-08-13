from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from tft_analyzer.core.enums import ReductionAction
from tft_analyzer.core.models import GameEvent
from tft_analyzer.storage import (
    find_latest_tracked_hud_file,
    find_latest_validation_file,
    iter_event_validations,
    iter_game_events,
    iter_tracked_hud_states,
)

from .reducer import HUDGameStateReducer, HUDGameStateReducerSettings


def _latest_versioned_file(
    directory: Path,
    pattern: str,
) -> Path:
    candidates = [
        p
        for p in directory.glob(pattern)
        if "_summary" not in p.name
        and "_decisions" not in p.name
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No files matching {pattern!r} in {directory}"
        )

    def key(path: Path):
        matches = list(re.finditer(r"(\d+)\.(\d+)\.(\d+)", path.name))
        version = (
            tuple(int(x) for x in matches[-1].groups())
            if matches
            else (0, 0, 0)
        )
        return (*version, path.stat().st_mtime)

    return max(candidates, key=key)


def event_target_state_id(event: GameEvent) -> str:
    """
    The last source state is the tracked state carrying the new target value.

    Routing by this ID avoids relying on exact float timestamp equality.
    """
    if not event.source_state_ids:
        raise ValueError(
            f"Event {event.event_id} has no source_state_ids; "
            "cannot route canonically"
        )
    return event.source_state_ids[-1]


def _unique(values):
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def reduce_match_game_state(
    match_dir: Path | str,
    settings: HUDGameStateReducerSettings,
    *,
    events_path: Path | str | None = None,
    validations_path: Path | str | None = None,
    tracked_states_path: Path | str | None = None,
    events_glob: str = "hud-event-detector-*.jsonl",
    validations_glob: str = "hud-event-validator-*.jsonl",
    tracked_states_glob: str = "hud-state-tracker-*.jsonl",
) -> dict[str, object]:
    match_dir = Path(match_dir)

    if events_path is None:
        events_path = _latest_versioned_file(
            match_dir / "events",
            events_glob,
        )
    events_path = Path(events_path)

    if validations_path is None:
        validations_path = find_latest_validation_file(
            match_dir,
            pattern=validations_glob,
        )
    validations_path = Path(validations_path)

    if tracked_states_path is None:
        tracked_states_path = find_latest_tracked_hud_file(
            match_dir,
            pattern=tracked_states_glob,
        )
    tracked_states_path = Path(tracked_states_path)

    events = list(iter_game_events(events_path))
    validations = list(iter_event_validations(validations_path))
    tracked_states = list(iter_tracked_hud_states(tracked_states_path))

    if not tracked_states:
        raise ValueError("Tracked state stream is empty")

    match_id = tracked_states[0].match_id

    validation_by_event = {
        validation.event_id: validation
        for validation in validations
    }

    tracked_ids = {state.state_id for state in tracked_states}

    events_by_target_state_id: dict[str, list[GameEvent]] = defaultdict(list)
    for event in events:
        target_state_id = event_target_state_id(event)
        if target_state_id not in tracked_ids:
            raise ValueError(
                f"Event {event.event_id} targets unknown tracked state "
                f"{target_state_id}"
            )
        events_by_target_state_id[target_state_id].append(event)

    reducer = HUDGameStateReducer(
        settings,
        match_id=match_id,
    )

    states = []
    decisions = []
    emitted_signature = None

    for tracked_state in tracked_states:
        semantic_changed = False
        direct_event_ids: list[str] = []
        direct_source_state_ids: list[str] = []

        init_decisions = reducer.initialize_from_tracked_state(
            tracked_state
        )
        if init_decisions:
            decisions.extend(init_decisions)
            semantic_changed = True
            direct_source_state_ids.append(tracked_state.state_id)

        for event in events_by_target_state_id.get(
            tracked_state.state_id,
            [],
        ):
            validation = validation_by_event.get(event.event_id)
            if validation is None:
                raise ValueError(
                    f"Missing validation for event {event.event_id}"
                )

            decision = reducer.apply_event(
                event,
                validation,
            )
            decisions.append(decision)

            if decision.action in {
                ReductionAction.APPLIED,
                ReductionAction.APPLIED_WITH_MISMATCH,
            }:
                semantic_changed = True
                direct_event_ids.append(event.event_id)
                direct_source_state_ids.extend(event.source_state_ids)

        # Repeated equal observations refresh current-state confidence and
        # provenance, but do not create semantic states.
        refresh_decisions = reducer.refresh_from_tracked_state(
            tracked_state
        )
        decisions.extend(refresh_decisions)

        if semantic_changed:
            parent_state_id = states[-1].state_id if states else None

            state = reducer.snapshot(
                timestamp_s=tracked_state.timestamp_s,
                source_token=tracked_state.state_id,
                parent_state_id=parent_state_id,
                applied_event_ids=_unique(direct_event_ids),
                source_state_ids=_unique(direct_source_state_ids),
            )

            signature = (
                state.stage,
                state.round,
                state.player.level,
                state.player.xp,
                state.player.xp_required,
                state.player.gold,
            )

            if signature != emitted_signature:
                states.append(state)
                emitted_signature = signature

    out_dir = match_dir / "states"
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_version = (
        settings.producer_version.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )

    states_path = out_dir / f"{safe_version}.jsonl"
    decisions_path = out_dir / f"{safe_version}_decisions.jsonl"
    summary_path = out_dir / f"{safe_version}_summary.json"

    tmp_states = states_path.with_suffix(states_path.suffix + ".tmp")
    with tmp_states.open("w", encoding="utf-8", newline="\n") as f:
        for state in states:
            f.write(
                json.dumps(
                    state.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp_states.replace(states_path)

    tmp_decisions = decisions_path.with_suffix(
        decisions_path.suffix + ".tmp"
    )
    with tmp_decisions.open("w", encoding="utf-8", newline="\n") as f:
        for decision in decisions:
            f.write(
                json.dumps(
                    decision.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp_decisions.replace(decisions_path)

    action_counts: dict[str, int] = defaultdict(int)
    field_actions = {
        field: defaultdict(int)
        for field in ("stage", "level", "xp", "gold")
    }

    for decision in decisions:
        action_counts[decision.action.value] += 1
        if decision.field in field_actions:
            field_actions[decision.field][decision.action.value] += 1

    final_state = (
        states[-1].model_dump(mode="json")
        if states
        else None
    )

    # A non-persisted current view captures metadata confirmations after the
    # last semantic transition without polluting the semantic state timeline.
    latest_state_view = None
    if states:
        last_tracked = tracked_states[-1]
        latest_state_view = reducer.snapshot(
            timestamp_s=last_tracked.timestamp_s,
            source_token=f"latest-view|{last_tracked.state_id}",
            parent_state_id=states[-1].state_id,
            applied_event_ids=(),
            source_state_ids=(last_tracked.state_id,),
        ).model_dump(mode="json")

    max_direct_events = max(
        (len(state.applied_event_ids) for state in states),
        default=0,
    )
    max_direct_sources = max(
        (len(state.source_state_ids) for state in states),
        default=0,
    )

    summary = {
        "schema_version": 2,
        "reducer_version": settings.producer_version,
        "input_events_path": str(events_path),
        "input_validations_path": str(validations_path),
        "input_tracked_states_path": str(tracked_states_path),
        "event_count": len(events),
        "validation_count": len(validations),
        "tracked_state_count": len(tracked_states),
        "canonical_state_count": len(states),
        "decision_count": len(decisions),
        "decision_actions": dict(action_counts),
        "field_decision_actions": {
            field: dict(counts)
            for field, counts in field_actions.items()
        },
        "metadata_refresh_count": action_counts[
            ReductionAction.METADATA_REFRESHED.value
        ],
        "max_direct_event_ids_per_state": max_direct_events,
        "max_direct_source_state_ids_per_state": max_direct_sources,
        "final_state": final_state,
        "latest_state_view": latest_state_view,
        "states_path": str(states_path),
        "decisions_path": str(decisions_path),
    }

    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_summary.replace(summary_path)

    summary["summary_path"] = str(summary_path)
    return summary
