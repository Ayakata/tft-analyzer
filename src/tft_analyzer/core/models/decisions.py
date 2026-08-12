from typing import Any

from pydantic import Field

from tft_analyzer.core.enums import DecisionType
from .base import SchemaModel


class DecisionEpisode(SchemaModel):
    decision_id: str
    match_id: str
    decision_type: DecisionType

    start_timestamp_s: float = Field(ge=0)
    end_timestamp_s: float = Field(ge=0)

    state_before_id: str
    state_after_id: str | None = None

    event_ids: tuple[str, ...] = ()
    action_ids: tuple[str, ...] = ()
    summary: dict[str, Any] = {}

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extractor_version: str
