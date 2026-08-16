from __future__ import annotations

from dataclasses import dataclass

from .models import OccupancyPositionState


@dataclass(slots=True)
class _MutablePosition:
    status: str = "unknown"
    confidence: float = 0.0
    foreground_score: float | None = None
    raw_score: float | None = None
    source_timestamp_s: float | None = None
    source_evidence_id: str | None = None
    pending_status: str | None = None
    pending_count: int = 0


@dataclass(frozen=True, slots=True)
class PositionDecision:
    position: str
    action: str
    reason: str
    previous_status: str
    candidate_status: str
    resulting_status: str
    confidence: float


class TemporalOccupancyTracker:
    def __init__(
        self,
        *,
        confirmation_count: int = 2,
    ) -> None:
        self.confirmation_count = max(
            1,
            int(confirmation_count),
        )
        self.positions: dict[
            str,
            _MutablePosition,
        ] = {}

    def _state(
        self,
        position: str,
    ) -> _MutablePosition:
        return self.positions.setdefault(
            position,
            _MutablePosition(),
        )

    def force_status(
        self,
        *,
        position: str,
        status: str,
        confidence: float,
        foreground_score: float,
        raw_score: float,
        timestamp_s: float,
        evidence_id: str,
        reason: str,
    ) -> PositionDecision:
        """
        Replace one canonical position immediately.

        This is intentionally separate from temporal confirmation. It is used
        only when a higher-level board invariant makes the entire snapshot
        stronger evidence than a collection of independent stale cells.
        """
        if status not in ("empty", "occupied"):
            raise ValueError(
                "force_status requires empty/occupied"
            )

        state = self._state(position)
        previous = state.status

        state.status = status
        state.confidence = float(confidence)
        state.foreground_score = float(
            foreground_score
        )
        state.raw_score = float(raw_score)
        state.source_timestamp_s = float(
            timestamp_s
        )
        state.source_evidence_id = evidence_id
        state.pending_status = None
        state.pending_count = 0

        action = (
            "refreshed"
            if previous == status
            else "accepted"
        )
        return PositionDecision(
            position=position,
            action=action,
            reason=reason,
            previous_status=previous,
            candidate_status=status,
            resulting_status=status,
            confidence=float(confidence),
        )

    def carry(
        self,
        *,
        position: str,
        candidate_status: str,
        confidence: float,
        reason: str,
    ) -> PositionDecision:
        """
        Record that an observation was deliberately ignored.

        Unlike ingest(... allow_change=False), this is a strict no-op:
        - canonical status is not changed;
        - provenance/timestamp is not refreshed;
        - pending confirmation is not advanced or cleared.

        This is required for frames where the semantic scene is invalid and
        the slot is therefore not observable at all.
        """
        state = self._state(position)
        return PositionDecision(
            position=position,
            action="carried",
            reason=reason,
            previous_status=state.status,
            candidate_status=candidate_status,
            resulting_status=state.status,
            confidence=float(confidence),
        )

    def ingest(
        self,
        *,
        position: str,
        candidate_status: str,
        confidence: float,
        foreground_score: float,
        raw_score: float,
        timestamp_s: float,
        evidence_id: str,
        allow_change: bool = True,
        blocked_reason: str = "board_frame_unstable",
    ) -> PositionDecision:
        state = self._state(position)
        previous = state.status

        if candidate_status == "uncertain":
            state.pending_status = None
            state.pending_count = 0
            return PositionDecision(
                position,
                "carried",
                "candidate_uncertain",
                previous,
                candidate_status,
                state.status,
                confidence,
            )

        if state.status == candidate_status:
            state.confidence = float(confidence)
            state.foreground_score = float(
                foreground_score
            )
            state.raw_score = float(raw_score)
            state.source_timestamp_s = float(
                timestamp_s
            )
            state.source_evidence_id = evidence_id
            state.pending_status = None
            state.pending_count = 0
            return PositionDecision(
                position,
                "refreshed",
                "same_status",
                previous,
                candidate_status,
                state.status,
                confidence,
            )

        if (
            not allow_change
            and state.status != "unknown"
        ):
            state.pending_status = None
            state.pending_count = 0
            return PositionDecision(
                position,
                "carried",
                blocked_reason,
                previous,
                candidate_status,
                state.status,
                confidence,
            )

        if state.pending_status == candidate_status:
            state.pending_count += 1
        else:
            state.pending_status = candidate_status
            state.pending_count = 1

        if (
            state.pending_count
            < self.confirmation_count
        ):
            return PositionDecision(
                position,
                "pending",
                "awaiting_confirmation",
                previous,
                candidate_status,
                state.status,
                confidence,
            )

        state.status = candidate_status
        state.confidence = float(confidence)
        state.foreground_score = float(
            foreground_score
        )
        state.raw_score = float(raw_score)
        state.source_timestamp_s = float(
            timestamp_s
        )
        state.source_evidence_id = evidence_id
        state.pending_status = None
        state.pending_count = 0

        reason = (
            "initialized"
            if previous == "unknown"
            else "confirmed_change"
        )
        return PositionDecision(
            position,
            "accepted",
            reason,
            previous,
            candidate_status,
            state.status,
            confidence,
        )

    def snapshot(
        self,
        position: str,
    ) -> OccupancyPositionState:
        state = self._state(position)
        return OccupancyPositionState(
            position=position,
            status=state.status,
            confidence=state.confidence,
            foreground_score=(
                state.foreground_score
            ),
            raw_score=state.raw_score,
            source_timestamp_s=(
                state.source_timestamp_s
            ),
            source_evidence_id=(
                state.source_evidence_id
            ),
            pending_status=state.pending_status,
            pending_count=state.pending_count,
        )
