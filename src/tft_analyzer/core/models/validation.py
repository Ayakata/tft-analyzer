from __future__ import annotations

from pydantic import Field

from tft_analyzer.core.enums import EventQuality

from .base import SchemaModel


class EventValidation(SchemaModel):
    validation_id: str
    match_id: str
    event_id: str

    quality: EventQuality
    reasons: tuple[str, ...] = ()

    field: str
    event_timestamp_s: float = Field(ge=0.0)
    transition_window_s: float = Field(default=0.0, ge=0.0)

    from_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    to_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    # Recommendation for the canonical reducer. A transition can be suspicious
    # because its old side is weak while its new target is still trustworthy.
    apply_to_state: bool

    source_state_ids: tuple[str, ...] = ()
    validator_version: str
