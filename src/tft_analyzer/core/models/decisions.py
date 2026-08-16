from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from tft_analyzer.core.enums import DecisionType
from .base import SchemaModel


class DecisionBoundaryState(SchemaModel):
    timestamp_s: float = Field(ge=0.0)
    evidence_id: str

    stage: str | None = None
    gold: int | None = None
    level: int | None = None
    xp_absolute: int | None = None

    board_count: int | None = Field(default=None, ge=0)
    bench_count: int | None = Field(default=None, ge=0)


class DecisionActionGroup(SchemaModel):
    """Actions inferred from one sparse observation window.

    The group position is ordered relative to other windows. Actions inside the
    same group are intentionally unordered because screenshots do not expose
    their click sequence.
    """

    group_index: int = Field(ge=0)
    window_index: int = Field(ge=0)
    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)

    action_ids: tuple[str, ...] = ()
    action_types: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    exact_intra_group_order_known: bool = False


class DecisionEconomySummary(SchemaModel):
    observed_spend_total: int = Field(default=0, ge=0)

    required_action_spend_min: int = Field(default=0, ge=0)
    required_action_spend_max: int | None = Field(default=0, ge=0)

    compatible_action_spend_min: int = Field(default=0, ge=0)
    compatible_action_spend_max: int = Field(default=0, ge=0)

    unallocated_spend_min: int = Field(default=0, ge=0)
    unallocated_spend_max: int = Field(default=0, ge=0)

    infeasible_window_count: int = Field(default=0, ge=0)
    spend_deficit_min_total: int = Field(default=0, ge=0)

    required_unknown_window_count: int = Field(default=0, ge=0)
    uncertainty_only_window_count: int = Field(default=0, ge=0)


class DecisionSamplingSummary(SchemaModel):
    mode: Literal["sparse_snapshots"] = "sparse_snapshots"

    source_window_count: int = Field(default=0, ge=0)
    span_seconds: float = Field(default=0.0, ge=0.0)
    max_source_window_seconds: float = Field(default=0.0, ge=0.0)

    exact_action_timestamps_known: bool = False
    exact_intra_window_order_known: bool = False

    ordering_guarantee: Literal["window_partial_order"] = (
        "window_partial_order"
    )


class DecisionEpisode(SchemaModel):
    """A bounded observed decision episode, not a reconstructed click trace.

    Stage 4.1 intentionally treats semantic actions inside a sparse evidence
    window as an unordered set. Only the ordering between non-overlapping
    source windows is retained.
    """

    schema_version: int = Field(default=2, ge=2)

    decision_id: str
    match_id: str
    decision_type: DecisionType

    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)

    state_before_id: str
    state_after_id: str | None = None

    stage_start: str | None = None
    stage_end: str | None = None

    window_indices: tuple[int, ...] = ()
    event_ids: tuple[str, ...] = ()
    action_ids: tuple[str, ...] = ()
    action_groups: tuple[DecisionActionGroup, ...] = ()

    state_before: DecisionBoundaryState | None = None
    state_after: DecisionBoundaryState | None = None
    economy: DecisionEconomySummary = Field(
        default_factory=DecisionEconomySummary
    )
    sampling: DecisionSamplingSummary = Field(
        default_factory=DecisionSamplingSummary
    )

    summary: dict[str, Any] = Field(default_factory=dict)

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extractor_version: str
