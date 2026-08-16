from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal
from pydantic import Field
from tft_analyzer.core.models.base import SchemaModel

ReviewCardType = Literal["gameplay_review", "data_quality"]
ReviewPriority = Literal["critical", "high", "medium", "low"]

@dataclass(frozen=True)
class MatchReviewReportSettings:
    producer_version: str = "match-review-report-0.19.0"
    include_data_quality_cards: bool = True

class MatchReviewCard(SchemaModel):
    schema_version: int = Field(default=1, ge=1)
    card_id: str
    match_id: str
    decision_id: str
    card_type: ReviewCardType
    priority: ReviewPriority
    priority_reason: str
    stage: str | None = None
    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)
    title: str
    summary: str
    state: dict[str, Any] = Field(default_factory=dict)
    activity: dict[str, Any] = Field(default_factory=dict)
    observed_facts: tuple[str, ...] = ()
    why_review: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    source_finding_ids: tuple[str, ...] = ()
    source_finding_codes: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    decision_grade: None = None
    producer_version: str
