from typing import Any, Literal

from pydantic import Field

from .base import SchemaModel


class Finding(SchemaModel):
    finding_id: str
    match_id: str
    decision_id: str | None = None

    category: str
    title: str

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

    metrics: dict[str, Any] = {}
    explanation: str | None = None
    evidence_ids: tuple[str, ...] = ()
