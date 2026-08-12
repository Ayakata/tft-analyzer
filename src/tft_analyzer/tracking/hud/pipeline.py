from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tft_analyzer.core.models import Observation
from tft_analyzer.storage import (
    find_latest_observation_file,
    iter_evidence_records,
    iter_observations,
)

from .tracker import HUDStateTracker, HUDTrackerSettings


def _group_observations(
    observations: list[Observation],
) -> dict[str, list[Observation]]:
    grouped: dict[str, list[Observation]] = defaultdict(list)

    for obs in observations:
        if obs.evidence_ids:
            grouped[obs.evidence_ids[0]].append(obs)

    for values in grouped.values():
        values.sort(
            key=lambda x: (
                x.timestamp_s,
                x.kind.value,
                -x.confidence,
            )
        )

    return grouped


def track_match_hud(
    match_dir: Path | str,
    settings: HUDTrackerSettings,
    *,
    observations_path: Path | str | None = None,
    observation_glob: str = "hud-rapidocr-*.jsonl",
) -> dict[str, object]:
    match_dir = Path(match_dir)

    if observations_path is None:
        observations_path = find_latest_observation_file(
            match_dir,
            pattern=observation_glob,
        )
    observations_path = Path(observations_path)

    observations = list(iter_observations(observations_path))
    by_evidence = _group_observations(observations)

    tracker = HUDStateTracker(settings)

    states = []
    decisions = []

    for record in iter_evidence_records(match_dir):
        evidence_id = record.evidence.evidence_id

        for observation in by_evidence.get(evidence_id, []):
            decision = tracker.ingest(observation)
            if decision is not None:
                decisions.append(decision)

        states.append(
            tracker.snapshot(
                match_id=record.evidence.match_id,
                timestamp_s=record.evidence.timestamp_s,
                evidence_id=evidence_id,
            )
        )

    out_dir = match_dir / "tracking"
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
    with tmp_decisions.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        for decision in decisions:
            f.write(
                json.dumps(
                    decision.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp_decisions.replace(decisions_path)

    decision_counts: dict[str, int] = defaultdict(int)
    decision_reasons: dict[str, int] = defaultdict(int)
    field_decision_actions = {field: defaultdict(int) for field in ("stage", "gold", "level", "xp")}
    field_decision_reasons = {field: defaultdict(int) for field in ("stage", "gold", "level", "xp")}
    field_value_changes = defaultdict(int)

    for d in decisions:
        decision_counts[d.action] += 1
        decision_reasons[d.reason] += 1
        field_decision_actions[d.field][d.action] += 1
        field_decision_reasons[d.field][d.reason] += 1
        if d.action == "accepted" and d.previous_value is not None and d.previous_value != d.observed_value:
            field_value_changes[d.field] += 1

    field_status_counts = {
        field: defaultdict(int)
        for field in ("stage", "gold", "level", "xp")
    }

    for state in states:
        for field in field_status_counts:
            tracked = getattr(state, field)
            field_status_counts[field][tracked.status] += 1

    summary = {
        "schema_version": 1,
        "tracker_version": settings.producer_version,
        "input_observations_path": str(observations_path),
        "input_observation_count": len(observations),
        "state_count": len(states),
        "decision_count": len(decisions),
        "decision_actions": dict(decision_counts),
        "decision_reasons": dict(decision_reasons),
        "field_decision_actions": {field: dict(counts) for field, counts in field_decision_actions.items()},
        "field_decision_reasons": {field: dict(counts) for field, counts in field_decision_reasons.items()},
        "field_value_changes": {field: int(field_value_changes[field]) for field in ("stage", "gold", "level", "xp")},
        "field_status_counts": {
            field: dict(counts)
            for field, counts in field_status_counts.items()
        },
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
