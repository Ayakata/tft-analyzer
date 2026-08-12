from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from tft_analyzer.core.enums import EventType
from tft_analyzer.core.models import (
    GameEvent,
    TrackedField,
    TrackedHUDState,
)

from .types import EventBaseline


@dataclass(frozen=True, slots=True)
class HUDEventDetectorSettings:
    producer_version: str = "hud-event-detector-0.6.0"
    warn_transition_window_seconds: float = 20.0
    emit_initial_values: bool = False


_FIELD_ORDER = ("stage", "level", "xp", "gold")

_EVENT_TYPE = {
    "stage": EventType.ROUND_START,
    "level": EventType.LEVEL_CHANGED,
    "xp": EventType.XP_CHANGED,
    "gold": EventType.GOLD_CHANGED,
}


class HUDEventDetector:
    """
    Convert stable HUD state changes into primitive semantic events.

    Only fields with status='observed' may create/update event baselines.
    Carried/stale states are useful for state consumers but must not manufacture
    new events.

    First observation establishes the baseline by default. A later differing
    observed value produces exactly one event.
    """

    def __init__(self, settings: HUDEventDetectorSettings) -> None:
        self.settings = settings
        self.baselines: dict[str, EventBaseline] = {}

    @staticmethod
    def _stable_json(value: dict[str, Any]) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _event_id(
        self,
        *,
        match_id: str,
        field: str,
        previous: EventBaseline,
        current: TrackedField,
    ) -> str:
        raw = "|".join(
            [
                match_id,
                field,
                previous.source_observation_id or "",
                current.source_observation_id or "",
                self._stable_json(previous.value),
                self._stable_json(dict(current.value or {})),
            ]
        )
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        return f"hudevent-{field}-{digest}"

    @staticmethod
    def _provenance_pair(
        first: str | None,
        second: str | None,
    ) -> tuple[str, ...]:
        values: list[str] = []
        for value in (first, second):
            if value and value not in values:
                values.append(value)
        return tuple(values)

    @staticmethod
    def _baseline_from(
        state: TrackedHUDState,
        field: TrackedField,
    ) -> EventBaseline:
        if field.value is None or field.source_timestamp_s is None:
            raise ValueError("Observed tracked field lacks source value/timestamp")

        return EventBaseline(
            value=dict(field.value),
            confidence=float(field.confidence),
            source_observation_id=field.source_observation_id,
            source_evidence_id=field.source_evidence_id,
            source_timestamp_s=float(field.source_timestamp_s),
            source_state_id=state.state_id,
        )

    def _payload(
        self,
        *,
        field_name: str,
        previous: EventBaseline,
        current: TrackedField,
    ) -> dict[str, Any]:
        current_value = dict(current.value or {})
        start_s = float(previous.source_timestamp_s)
        end_s = float(current.source_timestamp_s or start_s)
        window_s = max(0.0, end_s - start_s)

        payload: dict[str, Any] = {
            "field": field_name,
            "from": dict(previous.value),
            "to": current_value,
            "transition_window": {
                "start_s": start_s,
                "end_s": end_s,
                "width_s": window_s,
            },
            "timing_warning": (
                window_s > self.settings.warn_transition_window_seconds
            ),
        }

        if field_name == "gold":
            payload["delta"] = (
                int(current_value["gold"])
                - int(previous.value["gold"])
            )

        elif field_name == "level":
            payload["delta"] = (
                int(current_value["level"])
                - int(previous.value["level"])
            )

        elif field_name == "xp":
            same_requirement = (
                int(current_value["required"])
                == int(previous.value["required"])
            )
            payload["requirement_changed"] = not same_requirement
            payload["current_delta"] = (
                int(current_value["current"])
                - int(previous.value["current"])
                if same_requirement
                else None
            )

        elif field_name == "stage":
            payload["stage_changed"] = (
                int(current_value["stage"])
                != int(previous.value["stage"])
            )
            payload["round_changed"] = (
                int(current_value["round"])
                != int(previous.value["round"])
            )

        return payload

    def _initial_event(
        self,
        *,
        state: TrackedHUDState,
        field_name: str,
        current: TrackedField,
    ) -> GameEvent:
        current_value = dict(current.value or {})
        timestamp_s = float(
            current.source_timestamp_s
            if current.source_timestamp_s is not None
            else state.timestamp_s
        )

        raw = "|".join(
            [
                state.match_id,
                field_name,
                "initial",
                current.source_observation_id or "",
                self._stable_json(current_value),
            ]
        )
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

        return GameEvent(
            event_id=f"hudevent-{field_name}-{digest}",
            match_id=state.match_id,
            timestamp_s=timestamp_s,
            event_type=_EVENT_TYPE[field_name],
            payload={
                "field": field_name,
                "from": None,
                "to": current_value,
                "initial": True,
            },
            confidence=float(current.confidence),
            evidence_ids=self._provenance_pair(
                None,
                current.source_evidence_id,
            ),
            observation_ids=self._provenance_pair(
                None,
                current.source_observation_id,
            ),
            source_state_ids=(state.state_id,),
            producer_version=self.settings.producer_version,
        )

    def ingest_state(
        self,
        state: TrackedHUDState,
    ) -> list[GameEvent]:
        events: list[GameEvent] = []

        for field_name in _FIELD_ORDER:
            current: TrackedField = getattr(state, field_name)

            # Carried values are continuity, not new evidence. Stale/unknown
            # obviously cannot establish a semantic transition either.
            if current.status != "observed" or current.value is None:
                continue

            previous = self.baselines.get(field_name)

            if previous is None:
                if self.settings.emit_initial_values:
                    events.append(
                        self._initial_event(
                            state=state,
                            field_name=field_name,
                            current=current,
                        )
                    )
                self.baselines[field_name] = self._baseline_from(
                    state,
                    current,
                )
                continue

            current_value = dict(current.value)

            if current_value == previous.value:
                # Refresh provenance/timestamp so that a later event window
                # starts at the most recent observation of the old value.
                self.baselines[field_name] = self._baseline_from(
                    state,
                    current,
                )
                continue

            payload = self._payload(
                field_name=field_name,
                previous=previous,
                current=current,
            )

            timestamp_s = float(
                current.source_timestamp_s
                if current.source_timestamp_s is not None
                else state.timestamp_s
            )

            event = GameEvent(
                event_id=self._event_id(
                    match_id=state.match_id,
                    field=field_name,
                    previous=previous,
                    current=current,
                ),
                match_id=state.match_id,
                timestamp_s=timestamp_s,
                event_type=_EVENT_TYPE[field_name],
                payload=payload,
                confidence=max(
                    0.0,
                    min(
                        float(previous.confidence),
                        float(current.confidence),
                        1.0,
                    ),
                ),
                evidence_ids=self._provenance_pair(
                    previous.source_evidence_id,
                    current.source_evidence_id,
                ),
                observation_ids=self._provenance_pair(
                    previous.source_observation_id,
                    current.source_observation_id,
                ),
                source_state_ids=self._provenance_pair(
                    previous.source_state_id,
                    state.state_id,
                ),
                producer_version=self.settings.producer_version,
            )
            events.append(event)

            self.baselines[field_name] = self._baseline_from(
                state,
                current,
            )

        return events
