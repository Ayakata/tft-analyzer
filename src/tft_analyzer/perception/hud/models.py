from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tft_analyzer.core.models import Observation


@dataclass(frozen=True, slots=True)
class ParsedHUDValue:
    value: dict[str, Any]
    normalized_text: str
    parser_confidence: float


@dataclass(frozen=True, slots=True)
class FieldAttempt:
    field: str
    roi_name: str
    variant: str
    raw_text: str
    ocr_score: float
    parsed: ParsedHUDValue | None
    confidence: float

    presence_passed: bool = True
    presence_score: float = 1.0
    presence_reason: str | None = None

    candidate_name: str | None = None
    candidate_box: tuple[int, int, int, int] | None = None

    @property
    def valid(self) -> bool:
        return self.parsed is not None and self.presence_passed


@dataclass(slots=True)
class HUDRecognitionResult:
    observations: list[Observation] = field(default_factory=list)
    attempts: list[FieldAttempt] = field(default_factory=list)

    def best_attempt(self, field: str) -> FieldAttempt | None:
        matching = [a for a in self.attempts if a.field == field]
        if not matching:
            return None
        return max(
            matching,
            key=lambda a: (
                a.valid,
                a.confidence,
                a.presence_score,
            ),
        )
