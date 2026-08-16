from typing import Any, Literal

from pydantic import Field

from .base import SchemaModel


class Finding(SchemaModel):
    schema_version: int = Field(default=2, ge=1)

    finding_id: str
    match_id: str
    decision_id: str | None = None

    finding_code: str | None = None
    producer_version: str | None = None

    category: str
    title: str

    # Stage 4.2 keeps four different semantics separate:
    # - descriptive: observed activity/landmark;
    # - reconstruction_uncertainty: expected ambiguity caused by sparse evidence;
    # - data_quality: hard contradiction/inconsistency in reconstructed evidence;
    # - review_candidate / decision_grade: progressively stronger analysis layers.
    # A review candidate is NOT automatically a player mistake.
    interpretation: Literal[
        "descriptive",
        "reconstruction_uncertainty",
        "review_candidate",
        "data_quality",
        "decision_grade",
    ] = "descriptive"

    stage: str | None = None
    start_timestamp_s: float | None = Field(default=None, ge=0.0)
    end_timestamp_s: float | None = Field(default=None, ge=0.0)

    score: float | None = None
    severity: Literal["info", "minor", "major", "critical"] = "info"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    evidence_type: Literal[
        "rule",
        "descriptive_statistics",
        "value_model",
        "counterfactual_model",
        "offline_rl",
    ] = "rule"

    metrics: dict[str, Any] = Field(default_factory=dict)
    explanation: str | None = None
    recommendation: str | None = None
    limitations: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
