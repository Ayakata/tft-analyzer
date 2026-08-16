from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from tft_analyzer.core.enums import EventQuality, EventType
from tft_analyzer.core.models import (
    EventValidation,
    GameEvent,
    TrackedHUDState,
)


@dataclass(frozen=True, slots=True)
class HUDEventValidatorSettings:
    producer_version: str = "hud-event-validator-0.10.0"

    min_previous_confidence: dict[str, float] = field(
        default_factory=lambda: {
            "stage": 0.90,
            "level": 0.90,
            "xp": 0.85,
            "gold": 0.85,
            "hp": 0.85,
            "shop": 0.80,
        }
    )
    min_target_confidence: dict[str, float] = field(
        default_factory=lambda: {
            "stage": 0.90,
            "level": 0.90,
            "xp": 0.85,
            "gold": 0.85,
            "hp": 0.85,
            "shop": 0.80,
        }
    )

    timing_uncertain_after_seconds: float = 20.0
    flag_non_adjacent_stage_transition: bool = True


class HUDEventValidator:
    """
    Validate primitive events without rewriting them.

    Source tracked states are used to recover side-specific confidence. This is
    intentionally richer than GameEvent.confidence=min(from,to): a transition
    may have a weak old side but a strong new target, which matters to the
    canonical reducer.
    """

    def __init__(
        self,
        settings: HUDEventValidatorSettings,
        *,
        states_by_id: dict[str, TrackedHUDState],
    ) -> None:
        self.settings = settings
        self.states_by_id = states_by_id

    @staticmethod
    def _validation_id(event_id: str, version: str) -> str:
        digest = hashlib.sha1(
            f"{event_id}|{version}".encode("utf-8")
        ).hexdigest()[:16]
        return f"eventval-{digest}"

    @staticmethod
    def _tracked_field_for_event(
        state: TrackedHUDState,
        field: str,
    ):
        return getattr(state, field)

    def _side_confidences(
        self,
        event: GameEvent,
        field: str,
    ) -> tuple[float | None, float | None]:
        ids = tuple(event.source_state_ids)

        from_conf = None
        to_conf = None

        if len(ids) >= 1:
            state = self.states_by_id.get(ids[0])
            if state is not None:
                tracked = self._tracked_field_for_event(state, field)
                from_conf = float(tracked.confidence)

        if len(ids) >= 2:
            state = self.states_by_id.get(ids[-1])
            if state is not None:
                tracked = self._tracked_field_for_event(state, field)
                to_conf = float(tracked.confidence)

        # Graceful fallback for old/partial event files.
        if from_conf is None:
            from_conf = float(event.confidence)
        if to_conf is None:
            to_conf = float(event.confidence)

        return from_conf, to_conf

    @staticmethod
    def _stage_is_adjacent(
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> bool:
        bs = int(before["stage"])
        br = int(before["round"])
        as_ = int(after["stage"])
        ar = int(after["round"])

        if as_ == bs:
            return ar == br + 1

        if as_ == bs + 1:
            return ar == 1

        return False

    def validate(self, event: GameEvent) -> EventValidation:
        field = str(event.payload.get("field", "unknown"))

        from_conf, to_conf = self._side_confidences(event, field)

        reasons: list[str] = []
        suspicious = False
        timing_uncertain = False

        min_prev = float(
            self.settings.min_previous_confidence.get(field, 0.0)
        )
        min_target = float(
            self.settings.min_target_confidence.get(field, 0.0)
        )

        if from_conf < min_prev:
            suspicious = True
            reasons.append("low_previous_confidence")

        if to_conf < min_target:
            suspicious = True
            reasons.append("low_target_confidence")

        window = event.payload.get("transition_window", {})
        window_s = float(window.get("width_s", 0.0))

        if window_s > self.settings.timing_uncertain_after_seconds:
            timing_uncertain = True
            reasons.append("wide_transition_window")

        if (
            self.settings.flag_non_adjacent_stage_transition
            and event.event_type == EventType.ROUND_START
        ):
            before = event.payload.get("from")
            after = event.payload.get("to")
            if (
                isinstance(before, dict)
                and isinstance(after, dict)
                and not self._stage_is_adjacent(before, after)
            ):
                timing_uncertain = True
                reasons.append("non_adjacent_stage_transition")

        # Semantic target validity. Tracker should already guarantee these,
        # but validator keeps a defensive boundary.
        target = event.payload.get("to")

        if not isinstance(target, dict):
            suspicious = True
            reasons.append("missing_target_value")
            target_semantically_valid = False
        else:
            target_semantically_valid = True

            if field == "shop":
                slots = target.get("slots")
                if (
                    not isinstance(slots, (list, tuple))
                    or len(slots) != 5
                    or any(
                        value is not None
                        and (
                            not isinstance(value, str)
                            or not value.strip()
                        )
                        for value in slots
                    )
                ):
                    target_semantically_valid = False

            elif field == "hp":
                hp = int(target.get("hp", -1))
                if hp < 0 or hp > 250:
                    target_semantically_valid = False

            elif field == "gold":
                gold = int(target.get("gold", -1))
                if gold < 0:
                    target_semantically_valid = False

            elif field == "level":
                level = int(target.get("level", 0))
                if level < 1:
                    target_semantically_valid = False

            elif field == "xp":
                current = int(target.get("current", -1))
                required = int(target.get("required", 0))
                if current < 0 or required <= 0 or current > required:
                    target_semantically_valid = False

            elif field == "stage":
                stage = int(target.get("stage", 0))
                round_ = int(target.get("round", 0))
                if stage < 1 or round_ < 1:
                    target_semantically_valid = False

            else:
                target_semantically_valid = False

            if not target_semantically_valid:
                suspicious = True
                reasons.append("invalid_target_semantics")

        if suspicious:
            quality = EventQuality.SUSPICIOUS
        elif timing_uncertain:
            quality = EventQuality.TIMING_UNCERTAIN
        else:
            quality = EventQuality.TRUSTED

        # The target itself may still be safe to apply even when the transition
        # is suspicious because only the old side was weak.
        apply_to_state = bool(
            target_semantically_valid
            and to_conf >= min_target
        )

        if not reasons:
            reasons.append("validated")

        return EventValidation(
            validation_id=self._validation_id(
                event.event_id,
                self.settings.producer_version,
            ),
            match_id=event.match_id,
            event_id=event.event_id,
            quality=quality,
            reasons=tuple(reasons),
            field=field,
            event_timestamp_s=float(event.timestamp_s),
            transition_window_s=window_s,
            from_confidence=from_conf,
            to_confidence=to_conf,
            apply_to_state=apply_to_state,
            source_state_ids=tuple(event.source_state_ids),
            validator_version=self.settings.producer_version,
        )
