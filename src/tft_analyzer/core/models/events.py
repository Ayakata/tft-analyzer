from typing import Any

from pydantic import Field

from tft_analyzer.core.enums import EventType
from .base import SchemaModel


class GameEvent(SchemaModel):
    event_id: str
    match_id: str
    timestamp_s: float = Field(ge=0)

    event_type: EventType
    payload: dict[str, Any] = {}

    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    producer_version: str
