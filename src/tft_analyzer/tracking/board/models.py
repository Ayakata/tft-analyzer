from __future__ import annotations

from typing import Literal
from pydantic import Field

from tft_analyzer.core.models.base import (
    SchemaModel,
)


OccupancyStatus = Literal[
    "occupied",
    "empty",
    "uncertain",
    "unknown",
]


class BackgroundPositionModel(SchemaModel):
    position: str
    candidate_count: int = Field(ge=1)
    total_count: int = Field(ge=1)
    source_quantile: float = Field(
        gt=0.0,
        lt=1.0,
    )
    raw_score_median: float
    raw_score_scale: float = Field(gt=0.0)
    feature_medians: dict[str, float]
    feature_scales: dict[str, float]


class OccupancyPositionState(SchemaModel):
    position: str
    status: OccupancyStatus = "unknown"
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    foreground_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    raw_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    source_timestamp_s: float | None = Field(
        default=None,
        ge=0.0,
    )
    source_evidence_id: str | None = None
    pending_status: (
        Literal["occupied", "empty"] | None
    ) = None
    pending_count: int = Field(
        default=0,
        ge=0,
    )


class TrackedBoardOccupancyState(SchemaModel):
    match_id: str
    timestamp_s: float = Field(ge=0.0)
    evidence_id: str

    usable: bool
    stability: Literal[
        "warming",
        "stable",
        "unstable",
    ]
    gate_reason: str

    motion_count: int = Field(ge=0)
    candidate_change_count: int = Field(ge=0)
    uncertain_count: int = Field(ge=0)
    candidate_occupied_count: int = Field(ge=0)
    occupied_count: int = Field(ge=0)

    hud_level: int | None = Field(
        default=None,
        ge=1,
        le=10,
    )
    hud_stage: str | None = None
    round_age_s: float | None = Field(
        default=None,
        ge=0.0,
    )
    capacity_status: Literal[
        "unknown",
        "under",
        "at",
        "over",
    ] = "unknown"
    strong_snapshot: bool = False
    inferred_empty_count: int = Field(
        default=0,
        ge=0,
    )

    scene_valid: bool = True
    scene_score: float | None = Field(
        default=None,
        ge=0.0,
    )
    scene_anchor_pass_count: int | None = Field(
        default=None,
        ge=0,
    )

    cells: tuple[
        OccupancyPositionState,
        ...,
    ]
    tracker_version: str


class TrackedBenchOccupancyState(SchemaModel):
    match_id: str
    timestamp_s: float = Field(ge=0.0)
    evidence_id: str
    uncertain_count: int = Field(ge=0)
    occupied_count: int = Field(ge=0)
    slots: tuple[
        OccupancyPositionState,
        ...,
    ]
    tracker_version: str
