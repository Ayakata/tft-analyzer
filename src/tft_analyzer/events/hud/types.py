from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class EventBaseline:
    value: dict[str, Any]
    confidence: float
    source_observation_id: str | None
    source_evidence_id: str | None
    source_timestamp_s: float
    source_state_id: str
