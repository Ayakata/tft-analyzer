from __future__ import annotations

from typing import Any

from pydantic import Field

from tft_analyzer.core.enums import ReductionAction

from .base import SchemaModel


class StateReductionDecision(SchemaModel):
    decision_id: str
    match_id: str
    timestamp_s: float = Field(ge=0.0)

    action: ReductionAction
    field: str

    event_id: str | None = None
    validation_id: str | None = None
    source_state_id: str | None = None

    previous_value: dict[str, Any] | None = None
    event_from: dict[str, Any] | None = None
    applied_value: dict[str, Any] | None = None

    reason: str
    reducer_version: str
