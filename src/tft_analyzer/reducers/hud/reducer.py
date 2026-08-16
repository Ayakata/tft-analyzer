from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from tft_analyzer.core.enums import (
    GamePhase,
    ReductionAction,
)
from tft_analyzer.core.models import (
    EventValidation,
    GameEvent,
    GameState,
    PlayerState,
    ShopState,
    StateFieldMeta,
    StateReductionDecision,
    TrackedField,
    TrackedHUDState,
)


@dataclass(frozen=True, slots=True)
class HUDGameStateReducerSettings:
    producer_version: str = "hud-game-state-reducer-0.10.0"
    bootstrap_from_tracked_states: bool = True


class HUDGameStateReducer:
    """
    Build canonical HUD-backed GameState.

    Semantic values change only through bootstrap or validated events.

    Repeated tracked observations of the *same canonical value* are allowed to
    refresh field confidence/freshness metadata without creating a new
    semantic state.
    """

    def __init__(
        self,
        settings: HUDGameStateReducerSettings,
        *,
        match_id: str,
    ) -> None:
        self.settings = settings
        self.match_id = match_id

        self.stage: int | None = None
        self.round: int | None = None
        self.gold: int | None = None
        self.level: int | None = None
        self.xp: int | None = None
        self.xp_required: int | None = None
        self.hp: int | None = None
        self.shop_slots: tuple[str | None, ...] | None = None

        self.field_meta: dict[str, StateFieldMeta] = {}

    @staticmethod
    def _decision_id(
        token: str,
        action: ReductionAction,
        version: str,
    ) -> str:
        digest = hashlib.sha1(
            f"{token}|{action.value}|{version}".encode("utf-8")
        ).hexdigest()[:16]
        return f"reducerdec-{digest}"

    @staticmethod
    def _state_id(
        match_id: str,
        timestamp_s: float,
        version: str,
        source_token: str,
    ) -> str:
        digest = hashlib.sha1(
            f"{match_id}|{timestamp_s:.6f}|{version}|{source_token}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return f"gamestate-{digest}"

    def _field_value(self, field: str) -> dict[str, Any] | None:
        if field == "stage":
            if self.stage is None or self.round is None:
                return None
            return {"stage": self.stage, "round": self.round}

        if field == "hp":
            return None if self.hp is None else {"hp": self.hp}

        if field == "shop":
            if self.shop_slots is None:
                return None
            return {"slots": list(self.shop_slots)}

        if field == "gold":
            return None if self.gold is None else {"gold": self.gold}

        if field == "level":
            return None if self.level is None else {"level": self.level}

        if field == "xp":
            if self.xp is None or self.xp_required is None:
                return None
            return {
                "current": self.xp,
                "required": self.xp_required,
            }

        raise ValueError(f"Unsupported reducer field: {field}")

    def _set_field_value(
        self,
        field: str,
        value: dict[str, Any],
    ) -> None:
        if field == "stage":
            self.stage = int(value["stage"])
            self.round = int(value["round"])

        elif field == "hp":
            self.hp = int(value["hp"])

        elif field == "shop":
            self.shop_slots = tuple(value["slots"])

        elif field == "gold":
            self.gold = int(value["gold"])

        elif field == "level":
            self.level = int(value["level"])

        elif field == "xp":
            self.xp = int(value["current"])
            self.xp_required = int(value["required"])

        else:
            raise ValueError(f"Unsupported reducer field: {field}")

    @staticmethod
    def _tracked_value(tracked: TrackedField) -> dict[str, Any]:
        if tracked.value is None:
            raise ValueError("Tracked field has no value")
        return dict(tracked.value)

    @staticmethod
    def _clamp_confidence(value: float) -> float:
        return max(0.0, min(float(value), 1.0))

    def _set_meta_from_tracked(
        self,
        field: str,
        tracked: TrackedField,
        *,
        tracked_state_id: str,
    ) -> None:
        self.field_meta[field] = StateFieldMeta(
            confidence=self._clamp_confidence(tracked.confidence),
            last_observed_at_s=tracked.source_timestamp_s,
            age_s=0.0,
            source_observation_id=tracked.source_observation_id,
            source_evidence_id=tracked.source_evidence_id,
            source_tracked_state_id=tracked_state_id,
        )

    def _set_meta_from_event(
        self,
        field: str,
        event: GameEvent,
        validation: EventValidation,
    ) -> None:
        confidence = (
            validation.to_confidence
            if validation.to_confidence is not None
            else event.confidence
        )

        self.field_meta[field] = StateFieldMeta(
            confidence=self._clamp_confidence(confidence),
            last_observed_at_s=float(event.timestamp_s),
            age_s=0.0,
            source_observation_id=(
                event.observation_ids[-1]
                if event.observation_ids
                else None
            ),
            source_evidence_id=(
                event.evidence_ids[-1]
                if event.evidence_ids
                else None
            ),
            source_tracked_state_id=(
                event.source_state_ids[-1]
                if event.source_state_ids
                else None
            ),
        )

    def initialize_from_tracked_state(
        self,
        state: TrackedHUDState,
    ) -> list[StateReductionDecision]:
        if not self.settings.bootstrap_from_tracked_states:
            return []

        decisions: list[StateReductionDecision] = []

        for field in ("stage", "level", "xp", "gold", "hp", "shop"):
            if self._field_value(field) is not None:
                continue

            tracked: TrackedField = getattr(state, field)

            if tracked.status != "observed" or tracked.value is None:
                continue

            value = self._tracked_value(tracked)
            self._set_field_value(field, value)
            self._set_meta_from_tracked(
                field,
                tracked,
                tracked_state_id=state.state_id,
            )

            decisions.append(
                StateReductionDecision(
                    decision_id=self._decision_id(
                        f"{state.state_id}|{field}",
                        ReductionAction.INITIALIZED,
                        self.settings.producer_version,
                    ),
                    match_id=self.match_id,
                    timestamp_s=float(state.timestamp_s),
                    action=ReductionAction.INITIALIZED,
                    field=field,
                    source_state_id=state.state_id,
                    previous_value=None,
                    event_from=None,
                    applied_value=value,
                    reason="first_observed_tracked_value",
                    reducer_version=self.settings.producer_version,
                )
            )

        return decisions

    def apply_event(
        self,
        event: GameEvent,
        validation: EventValidation,
    ) -> StateReductionDecision:
        field = validation.field
        previous = self._field_value(field)

        event_from = event.payload.get("from")
        event_to = event.payload.get("to")

        if not validation.apply_to_state:
            return StateReductionDecision(
                decision_id=self._decision_id(
                    event.event_id,
                    ReductionAction.SKIPPED_VALIDATION,
                    self.settings.producer_version,
                ),
                match_id=self.match_id,
                timestamp_s=float(event.timestamp_s),
                action=ReductionAction.SKIPPED_VALIDATION,
                field=field,
                event_id=event.event_id,
                validation_id=validation.validation_id,
                previous_value=previous,
                event_from=(
                    dict(event_from)
                    if isinstance(event_from, dict)
                    else None
                ),
                applied_value=None,
                reason="validation_recommended_skip",
                reducer_version=self.settings.producer_version,
            )

        if not isinstance(event_to, dict):
            return StateReductionDecision(
                decision_id=self._decision_id(
                    event.event_id,
                    ReductionAction.SKIPPED_VALIDATION,
                    self.settings.producer_version,
                ),
                match_id=self.match_id,
                timestamp_s=float(event.timestamp_s),
                action=ReductionAction.SKIPPED_VALIDATION,
                field=field,
                event_id=event.event_id,
                validation_id=validation.validation_id,
                previous_value=previous,
                event_from=(
                    dict(event_from)
                    if isinstance(event_from, dict)
                    else None
                ),
                applied_value=None,
                reason="event_missing_target",
                reducer_version=self.settings.producer_version,
            )

        target = dict(event_to)

        if previous == target:
            return StateReductionDecision(
                decision_id=self._decision_id(
                    event.event_id,
                    ReductionAction.IGNORED_NO_CHANGE,
                    self.settings.producer_version,
                ),
                match_id=self.match_id,
                timestamp_s=float(event.timestamp_s),
                action=ReductionAction.IGNORED_NO_CHANGE,
                field=field,
                event_id=event.event_id,
                validation_id=validation.validation_id,
                previous_value=previous,
                event_from=(
                    dict(event_from)
                    if isinstance(event_from, dict)
                    else None
                ),
                applied_value=target,
                reason="target_already_canonical",
                reducer_version=self.settings.producer_version,
            )

        mismatch = (
            previous is not None
            and isinstance(event_from, dict)
            and previous != dict(event_from)
        )

        self._set_field_value(field, target)
        self._set_meta_from_event(
            field,
            event,
            validation,
        )

        action = (
            ReductionAction.APPLIED_WITH_MISMATCH
            if mismatch
            else ReductionAction.APPLIED
        )
        reason = (
            "trusted_target_recovery_from_source_mismatch"
            if mismatch
            else "validated_event_applied"
        )

        return StateReductionDecision(
            decision_id=self._decision_id(
                event.event_id,
                action,
                self.settings.producer_version,
            ),
            match_id=self.match_id,
            timestamp_s=float(event.timestamp_s),
            action=action,
            field=field,
            event_id=event.event_id,
            validation_id=validation.validation_id,
            source_state_id=(
                event.source_state_ids[-1]
                if event.source_state_ids
                else None
            ),
            previous_value=previous,
            event_from=(
                dict(event_from)
                if isinstance(event_from, dict)
                else None
            ),
            applied_value=target,
            reason=reason,
            reducer_version=self.settings.producer_version,
        )

    def refresh_from_tracked_state(
        self,
        state: TrackedHUDState,
    ) -> list[StateReductionDecision]:
        """
        Refresh confidence/provenance for equal canonical values.

        This is metadata-only and must never cause a new semantic GameState.
        Weak observations of a *different* value are ignored here; they remain
        governed by event validation.
        """
        decisions: list[StateReductionDecision] = []

        for field in ("stage", "level", "xp", "gold", "hp", "shop"):
            canonical = self._field_value(field)
            if canonical is None:
                continue

            tracked: TrackedField = getattr(state, field)

            if tracked.status != "observed" or tracked.value is None:
                continue

            tracked_value = self._tracked_value(tracked)
            if tracked_value != canonical:
                continue

            previous_meta = self.field_meta.get(field)

            # Avoid a duplicate metadata decision for the exact source already
            # installed by bootstrap/event application.
            if (
                previous_meta is not None
                and previous_meta.source_observation_id
                == tracked.source_observation_id
            ):
                continue

            self._set_meta_from_tracked(
                field,
                tracked,
                tracked_state_id=state.state_id,
            )

            decisions.append(
                StateReductionDecision(
                    decision_id=self._decision_id(
                        f"{state.state_id}|{field}|metadata",
                        ReductionAction.METADATA_REFRESHED,
                        self.settings.producer_version,
                    ),
                    match_id=self.match_id,
                    timestamp_s=float(state.timestamp_s),
                    action=ReductionAction.METADATA_REFRESHED,
                    field=field,
                    source_state_id=state.state_id,
                    previous_value=canonical,
                    event_from=None,
                    applied_value=canonical,
                    reason="same_value_observation_refreshed_metadata",
                    reducer_version=self.settings.producer_version,
                )
            )

        return decisions

    def _snapshot_field_meta(
        self,
        timestamp_s: float,
    ) -> dict[str, StateFieldMeta]:
        result: dict[str, StateFieldMeta] = {}

        for field, meta in self.field_meta.items():
            age_s = (
                max(0.0, float(timestamp_s) - meta.last_observed_at_s)
                if meta.last_observed_at_s is not None
                else None
            )

            result[field] = meta.model_copy(
                update={"age_s": age_s}
            )

        return result

    def snapshot(
        self,
        *,
        timestamp_s: float,
        source_token: str,
        parent_state_id: str | None,
        applied_event_ids: tuple[str, ...],
        source_state_ids: tuple[str, ...],
    ) -> GameState:
        field_meta = self._snapshot_field_meta(timestamp_s)

        known_confidences = [
            field_meta[field].confidence
            for field in ("stage", "level", "xp", "gold", "hp", "shop")
            if self._field_value(field) is not None
            and field in field_meta
        ]
        confidence = min(known_confidences) if known_confidences else 0.0

        return GameState(
            state_id=self._state_id(
                self.match_id,
                float(timestamp_s),
                self.settings.producer_version,
                source_token,
            ),
            match_id=self.match_id,
            timestamp_s=max(0.0, float(timestamp_s)),
            stage=self.stage,
            round=self.round,
            phase=GamePhase.UNKNOWN,
            player=PlayerState(
                gold=self.gold,
                level=self.level,
                xp=self.xp,
                xp_required=self.xp_required,
                hp=self.hp,
            ),
            shop=ShopState(
                slots=(
                    self.shop_slots
                    if self.shop_slots is not None
                    else ()
                ),
                locked=None,
            ),
            parent_state_id=parent_state_id,
            applied_event_ids=tuple(applied_event_ids),
            source_state_ids=tuple(source_state_ids),
            field_meta=field_meta,
            confidence=max(0.0, min(confidence, 1.0)),
            reducer_version=self.settings.producer_version,
        )
