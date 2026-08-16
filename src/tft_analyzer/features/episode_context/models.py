from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from tft_analyzer.core.models.base import SchemaModel


HUDFieldStatus = Literal[
    "observed",
    "carried",
    "stale",
    "unknown",
]


@dataclass(frozen=True)
class EpisodeContextSettings:
    producer_version: str = "episode-context-builder-0.17.1"


class EpisodeTrackedFieldMeta(SchemaModel):
    status: HUDFieldStatus = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    age_s: float | None = Field(default=None, ge=0.0)
    source_evidence_id: str | None = None
    source_timestamp_s: float | None = Field(default=None, ge=0.0)


FeatureTrustSemantics = Literal[
    "exact",
    "lower_bound",
    "carried",
    "unusable",
    "unknown",
]


class EpisodeFeatureTrust(SchemaModel):
    known: bool
    semantics: FeatureTrustSemantics
    usable_for_strategy: bool
    reason: str
    source: str | None = None


class EpisodeBoundaryTrust(SchemaModel):
    hp: EpisodeFeatureTrust
    gold: EpisodeFeatureTrust
    level: EpisodeFeatureTrust
    xp_absolute: EpisodeFeatureTrust

    board_count: EpisodeFeatureTrust
    board_utilization: EpisodeFeatureTrust
    bench_count: EpisodeFeatureTrust


class EpisodeContextFeatureTrust(SchemaModel):
    before: EpisodeBoundaryTrust
    after: EpisodeBoundaryTrust

    boundary_gold_delta_semantics: Literal[
        "observed_state_delta_not_action_accounting"
    ] = "observed_state_delta_not_action_accounting"

    economy_source_for_action_spend: Literal[
        "episode_economy"
    ] = "episode_economy"


class EpisodePlayerStateFeature(SchemaModel):
    timestamp_s: float = Field(ge=0.0)
    evidence_id: str

    stage: str | None = None
    hp: int | None = Field(default=None, ge=0)
    gold: int | None = Field(default=None, ge=0)
    level: int | None = Field(default=None, ge=1, le=10)

    xp_current: int | None = Field(default=None, ge=0)
    xp_required: int | None = Field(default=None, ge=0)
    xp_absolute: int | None = Field(default=None, ge=0)

    board_count: int | None = Field(default=None, ge=0)
    board_capacity: int | None = Field(default=None, ge=1, le=10)
    board_utilization: float | None = Field(default=None, ge=0.0)

    bench_count: int | None = Field(default=None, ge=0)
    bench_capacity: int = Field(default=9, ge=1)
    bench_utilization: float | None = Field(default=None, ge=0.0)

    board_usable: bool | None = None
    board_stability: str | None = None
    board_gate_reason: str | None = None
    board_scene_valid: bool | None = None
    board_scene_score: float | None = Field(default=None, ge=0.0)
    board_capacity_status: str | None = None
    board_strong_snapshot: bool | None = None
    board_uncertain_count: int | None = Field(default=None, ge=0)
    bench_uncertain_count: int | None = Field(default=None, ge=0)

    hud_fields: dict[str, EpisodeTrackedFieldMeta] = Field(default_factory=dict)

    source_alignment: Literal[
        "exact_evidence",
        "episode_boundary_fallback",
    ] = "exact_evidence"


class EpisodePlayerStateDelta(SchemaModel):
    hp: int | None = None
    gold: int | None = None
    level: int | None = None
    xp_absolute: int | None = None
    board_count: int | None = None
    bench_count: int | None = None
    board_utilization: float | None = None


class EpisodeContextQuality(SchemaModel):
    before_exact_alignment: bool = False
    after_exact_alignment: bool = False

    hp_known_before: bool = False
    hp_known_after: bool = False
    board_known_before: bool = False
    board_known_after: bool = False
    bench_known_before: bool = False
    bench_known_after: bool = False
    board_utilization_known_before: bool = False
    board_utilization_known_after: bool = False

    scene_valid_before: bool | None = None
    scene_valid_after: bool | None = None
    board_usable_before: bool | None = None
    board_usable_after: bool | None = None

    economy_feasible: bool | None = None
    reconstruction_uncertainty: bool = False

    missing_before_fields: tuple[str, ...] = ()
    missing_after_fields: tuple[str, ...] = ()


class EpisodePlayerContext(SchemaModel):
    schema_version: int = Field(default=2, ge=1)

    context_id: str
    decision_id: str
    match_id: str

    stage_start: str | None = None
    stage_end: str | None = None

    before: EpisodePlayerStateFeature
    after: EpisodePlayerStateFeature
    delta: EpisodePlayerStateDelta
    quality: EpisodeContextQuality
    feature_trust: EpisodeContextFeatureTrust

    source_episode_producer_version: str
    source_hud_tracker_version: str | None = None
    source_board_tracker_version: str | None = None
    source_bench_tracker_version: str | None = None

    producer_version: str
