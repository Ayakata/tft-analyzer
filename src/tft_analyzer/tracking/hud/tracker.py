from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import (
    Observation,
    TrackedField,
    TrackedHUDState,
    TrackingDecision,
)

from .constraints import (
    ConstraintResult,
    check_gold,
    check_level,
    check_stage,
    check_xp,
)
from .types import AcceptedValue, PendingCandidate
from .semantic import canonical_hud_value


FIELD_BY_KIND = {
    ObservationKind.STAGE: "stage",
    ObservationKind.GOLD: "gold",
    ObservationKind.LEVEL: "level",
    ObservationKind.XP: "xp",
}


@dataclass(frozen=True, slots=True)
class HUDTrackerSettings:
    producer_version: str = "hud-state-tracker-0.5.1"

    max_age_seconds: dict[str, float] = field(
        default_factory=lambda: {
            "stage": 45.0,
            "gold": 15.0,
            "level": 45.0,
            "xp": 15.0,
        }
    )

    reject_stage_regression: bool = True
    max_stage_code_jump_without_confirmation: int = 12

    reject_level_regression: bool = True
    max_level_jump_without_confirmation: int = 2

    reject_xp_regression_same_requirement: bool = True

    suspicious_confirmation_count: int = 2


class HUDStateTracker:
    def __init__(self, settings: HUDTrackerSettings) -> None:
        self.settings = settings
        self.accepted: dict[str, AcceptedValue] = {}
        self.pending: dict[str, PendingCandidate] = {}

    @staticmethod
    def _decision_id(observation_id: str, action: str) -> str:
        digest = hashlib.sha1(
            f"{observation_id}|{action}".encode("utf-8")
        ).hexdigest()[:12]
        return f"trkdec-{digest}"

    @staticmethod
    def _state_id(match_id: str, timestamp_s: float) -> str:
        digest = hashlib.sha1(
            f"{match_id}|{timestamp_s:.6f}".encode("utf-8")
        ).hexdigest()[:12]
        return f"hudstate-{digest}"

    def _check_constraint(
        self,
        field: str,
        previous: dict[str, Any] | None,
        observed: dict[str, Any],
    ) -> ConstraintResult:
        if field == "stage":
            return check_stage(
                previous,
                observed,
                reject_regression=self.settings.reject_stage_regression,
                max_jump_without_confirmation=(
                    self.settings.max_stage_code_jump_without_confirmation
                ),
            )
        if field == "gold":
            return check_gold(previous, observed)
        if field == "level":
            return check_level(
                previous,
                observed,
                reject_regression=self.settings.reject_level_regression,
                max_jump_without_confirmation=(
                    self.settings.max_level_jump_without_confirmation
                ),
            )
        if field == "xp":
            return check_xp(
                previous,
                observed,
                reject_regression_same_requirement=(
                    self.settings.reject_xp_regression_same_requirement
                ),
            )
        raise ValueError(f"Unsupported HUD field: {field}")

    def _accept(
        self,
        field: str,
        observation: Observation,
    ) -> None:
        canonical = canonical_hud_value(
            observation.kind,
            observation.value,
        )
        self.accepted[field] = AcceptedValue(
            value=canonical,
            confidence=float(observation.confidence),
            observation_id=observation.observation_id,
            evidence_id=(
                observation.evidence_ids[0]
                if observation.evidence_ids
                else None
            ),
            timestamp_s=float(observation.timestamp_s),
        )
        self.pending.pop(field, None)

    def _pending_confirmation(
        self,
        field: str,
        observation: Observation,
    ) -> bool:
        value = canonical_hud_value(
            observation.kind,
            observation.value,
        )
        existing = self.pending.get(field)

        if existing is None or existing.value != value:
            self.pending[field] = PendingCandidate(
                value=value,
                count=1,
                first_timestamp_s=float(observation.timestamp_s),
                last_timestamp_s=float(observation.timestamp_s),
                latest_observation=observation,
            )
            return False

        existing.count += 1
        existing.last_timestamp_s = float(observation.timestamp_s)
        existing.latest_observation = observation

        if existing.count >= max(
            1,
            self.settings.suspicious_confirmation_count,
        ):
            self._accept(field, observation)
            return True

        return False

    def ingest(
        self,
        observation: Observation,
    ) -> TrackingDecision | None:
        field = FIELD_BY_KIND.get(observation.kind)
        if field is None:
            return None

        observed_value = canonical_hud_value(
            observation.kind,
            observation.value,
        )
        previous = self.accepted.get(field)
        previous_value = (
            dict(previous.value)
            if previous is not None
            else None
        )

        constraint = self._check_constraint(
            field,
            previous_value,
            observed_value,
        )

        if not constraint.valid:
            self.pending.pop(field, None)
            action = "rejected"
            reason = constraint.reason

        elif constraint.suspicious:
            confirmed = self._pending_confirmation(
                field,
                observation,
            )
            if confirmed:
                action = "accepted"
                reason = f"{constraint.reason}_confirmed"
            else:
                action = "pending"
                reason = f"{constraint.reason}_awaiting_confirmation"

        else:
            same = previous_value == observed_value
            self._accept(field, observation)
            action = "refreshed" if same else "accepted"
            reason = constraint.reason

        return TrackingDecision(
            decision_id=self._decision_id(
                observation.observation_id,
                action,
            ),
            match_id=observation.match_id,
            timestamp_s=max(0.0, float(observation.timestamp_s)),
            field=field,
            observation_id=observation.observation_id,
            action=action,
            reason=reason,
            previous_value=previous_value,
            observed_value=observed_value,
            confidence=float(observation.confidence),
            tracker_version=self.settings.producer_version,
        )

    def _tracked_field(
        self,
        field: str,
        timestamp_s: float,
    ) -> TrackedField:
        accepted = self.accepted.get(field)
        if accepted is None:
            return TrackedField(
                value=None,
                confidence=0.0,
                status="unknown",
            )

        age_s = max(0.0, float(timestamp_s) - accepted.timestamp_s)
        max_age = float(
            self.settings.max_age_seconds.get(field, 0.0)
        )

        if max_age <= 0 or age_s > max_age:
            return TrackedField(
                value=None,
                confidence=0.0,
                source_observation_id=accepted.observation_id,
                source_evidence_id=accepted.evidence_id,
                source_timestamp_s=accepted.timestamp_s,
                age_s=age_s,
                status="stale",
            )

        if age_s <= 1e-9:
            status = "observed"
            effective_confidence = accepted.confidence
        else:
            status = "carried"
            effective_confidence = accepted.confidence * max(
                0.0,
                1.0 - age_s / max_age,
            )

        return TrackedField(
            value=accepted.value,
            confidence=max(
                0.0,
                min(float(effective_confidence), 1.0),
            ),
            source_observation_id=accepted.observation_id,
            source_evidence_id=accepted.evidence_id,
            source_timestamp_s=accepted.timestamp_s,
            age_s=age_s,
            status=status,
        )

    def snapshot(
        self,
        *,
        match_id: str,
        timestamp_s: float,
        evidence_id: str | None,
    ) -> TrackedHUDState:
        timestamp_s = max(0.0, float(timestamp_s))

        return TrackedHUDState(
            state_id=self._state_id(match_id, timestamp_s),
            match_id=match_id,
            timestamp_s=timestamp_s,
            evidence_id=evidence_id,
            stage=self._tracked_field("stage", timestamp_s),
            gold=self._tracked_field("gold", timestamp_s),
            level=self._tracked_field("level", timestamp_s),
            xp=self._tracked_field("xp", timestamp_s),
            tracker_version=self.settings.producer_version,
        )
