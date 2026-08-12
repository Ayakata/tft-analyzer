from typing import Any

from pydantic import Field

from tft_analyzer.core.enums import ObservationKind
from .base import SchemaModel


class Observation(SchemaModel):
    observation_id: str
    match_id: str
    timestamp_s: float = Field(ge=0)

    kind: ObservationKind
    value: dict[str, Any]

    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: tuple[str, ...] = ()
    producer_version: str
