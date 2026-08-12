from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tft_analyzer.core.models import Observation


@dataclass(slots=True)
class AcceptedValue:
    value: Any
    confidence: float
    observation_id: str
    evidence_id: str | None
    timestamp_s: float


@dataclass(slots=True)
class PendingCandidate:
    value: Any
    count: int
    first_timestamp_s: float
    last_timestamp_s: float
    latest_observation: Observation
