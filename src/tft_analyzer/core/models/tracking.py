from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .base import SchemaModel


class TrackedField(SchemaModel):
    """
    One stable field inside a tracked state.

    `source_timestamp_s` is when the underlying perception observation was made;
    `timestamp_s` belongs to the enclosing state snapshot.
    """

    value: Any | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    source_observation_id: str | None = None
    source_evidence_id: str | None = None
    source_timestamp_s: float | None = Field(default=None, ge=0.0)

    age_s: float | None = Field(default=None, ge=0.0)
    status: Literal["observed", "carried", "stale", "unknown"] = "unknown"


class TrackedHUDState(SchemaModel):
    state_id: str
    match_id: str
    timestamp_s: float = Field(ge=0.0)
    evidence_id: str | None = None

    stage: TrackedField = TrackedField()
    gold: TrackedField = TrackedField()
    level: TrackedField = TrackedField()
    xp: TrackedField = TrackedField()
    hp: TrackedField = TrackedField()
    shop: TrackedField = TrackedField()

    tracker_version: str


class TrackingDecision(SchemaModel):
    decision_id: str
    match_id: str
    timestamp_s: float = Field(ge=0.0)

    field: Literal["stage", "gold", "level", "xp", "hp", "shop"]
    observation_id: str

    action: Literal[
        "accepted",
        "refreshed",
        "rejected",
        "pending",
    ]
    reason: str

    previous_value: Any | None = None
    observed_value: Any | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    tracker_version: str
