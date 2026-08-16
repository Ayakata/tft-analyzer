from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from tft_analyzer.core.enums import ActionType
from tft_analyzer.core.models.base import SchemaModel


class ActionInferenceQuality(StrEnum):
    STRONG = "strong"
    SUPPORTED = "supported"
    AMBIGUOUS = "ambiguous"


class InferredAction(SchemaModel):
    action_id: str
    match_id: str
    action_type: ActionType

    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)

    confidence: float = Field(ge=0.0, le=1.0)
    quality: ActionInferenceQuality

    params: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, Any] = Field(default_factory=dict)

    evidence_ids: tuple[str, ...] = ()
    producer_version: str


class EconomyLedgerComponent(SchemaModel):
    kind: Literal["reroll", "purchase_xp", "buy_unit"]

    count_min: int = Field(ge=0)
    count_max: int | None = Field(default=None, ge=0)

    unit_cost: int | None = Field(default=None, ge=0)
    unit_costs: tuple[int | None, ...] = ()

    spend_min: int = Field(default=0, ge=0)
    spend_max: int | None = Field(default=None, ge=0)

    exact_count: bool = False
    exact_spend: bool = False

    pricing_status: str | None = None
    pricing_provider: str | None = None
    pricing_version: str | None = None
    unresolved_champions: tuple[str, ...] = ()

    action_id: str | None = None
    champions: tuple[str, ...] = ()


class EconomyLedgerWindow(SchemaModel):
    window_index: int = Field(ge=0)
    match_id: str
    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)
    start_evidence_id: str
    end_evidence_id: str

    stage_changed: bool = False
    observed_gold_delta: int | None = None
    observed_spend: int | None = Field(default=None, ge=0)

    components: tuple[EconomyLedgerComponent, ...] = ()

    # Spend required by recognized action components. Never clamped to observation.
    required_action_spend_min: int = Field(default=0, ge=0)
    required_action_spend_max: int | None = Field(default=None, ge=0)

    # Backward-compatible aliases. From 0.14.6 they mirror required spend.
    action_spend_min: int = Field(default=0, ge=0)
    action_spend_max: int | None = Field(default=None, ge=0)

    # Intersection of required action spend with the observed spend budget.
    # None means the constraint system is infeasible.
    compatible_action_spend_min: int | None = Field(default=None, ge=0)
    compatible_action_spend_max: int | None = Field(default=None, ge=0)

    feasible: bool | None = None
    spend_deficit_min: int | None = Field(default=None, ge=0)
    spend_deficit_max: int | None = Field(default=None, ge=0)

    # Exists only for feasible observed-spend windows.
    unallocated_spend_min: int | None = Field(default=None, ge=0)
    unallocated_spend_max: int | None = Field(default=None, ge=0)

    status: Literal[
        "unobserved",
        "income_or_flat",
        "fully_explained",
        "unallocated_exact",
        "unallocated_bounded",
        "infeasible",
    ]

    unknown_action_id: str | None = None


class ActionWindowDiagnostic(SchemaModel):
    window_index: int = Field(ge=0)
    match_id: str
    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)
    start_evidence_id: str
    end_evidence_id: str

    stage_before: str | None = None
    stage_after: str | None = None
    stage_changed: bool = False
    scene_valid_pair: bool = False

    gold_before: int | None = None
    gold_after: int | None = None
    gold_delta: int | None = None

    level_before: int | None = None
    level_after: int | None = None
    level_delta: int | None = None

    xp_before: dict[str, int] | None = None
    xp_after: dict[str, int] | None = None
    xp_delta: int | None = None
    xp_absolute_before: int | None = None
    xp_absolute_after: int | None = None
    xp_delta_source: Literal[
        "none",
        "same_level_current",
        "absolute_progress",
    ] = "none"

    shop_change_count: int = 0
    shop_cleared_slots: tuple[dict[str, Any], ...] = ()
    shop_filled_slots: tuple[dict[str, Any], ...] = ()
    shop_replaced_slots: tuple[dict[str, Any], ...] = ()

    board_before: int = 0
    board_after: int = 0
    board_delta: int = 0
    bench_before: int = 0
    bench_after: int = 0
    bench_delta: int = 0
    total_units_delta: int = 0

    board_cell_change_count: int = 0
    action_ids: tuple[str, ...] = ()

    ledger_status: str | None = None
    ledger_feasible: bool | None = None
    ledger_required_action_spend_min: int | None = None
    ledger_required_action_spend_max: int | None = None
    ledger_compatible_action_spend_min: int | None = None
    ledger_compatible_action_spend_max: int | None = None
    ledger_spend_deficit_min: int | None = None
    ledger_spend_deficit_max: int | None = None
    ledger_action_spend_min: int | None = None
    ledger_action_spend_max: int | None = None
    ledger_unallocated_min: int | None = None
    ledger_unallocated_max: int | None = None

    notes: tuple[str, ...] = ()
