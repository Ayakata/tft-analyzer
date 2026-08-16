from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from tft_analyzer.core.models.base import SchemaModel


SlotLocation = Literal["board", "bench"]

IdentityLabelStatus = Literal[
    "unlabeled",
    "human_labeled",
    "model_candidate",
    "confirmed",
]

IdentityTargetType = Literal[
    "champion",
    "no_unit",
    "uncertain",
    "unusable",
]

OccupancyEvidenceTier = Literal[
    "trusted",
    "supported",
    "raw_candidate",
]


@dataclass(frozen=True)
class SlotIdentityDatasetSettings:
    producer_version: str = "slot-identity-dataset-exporter-0.21.1"

    export_board: bool = True
    export_bench: bool = True

    # Keep the 0.21.0 observation-pool selection. 0.21.1 does not silently
    # discard disputed crops; it classifies their occupancy evidence quality.
    selected_occupancy_statuses: tuple[str, ...] = ("occupied",)
    min_raw_occupancy_confidence: float = 0.55

    # Scene-invalid samples are excluded by default. If explicitly exported,
    # they can never become trusted/supported identity-training samples.
    require_scene_valid: bool = True

    image_format: Literal["png"] = "png"


class AcquisitionIdentityPrior(SchemaModel):
    champion: str
    confirmed_acquired_copy_lower_bound: int = Field(
        default=0,
        ge=0,
    )
    candidate_acquired_copy_count: int = Field(
        default=0,
        ge=0,
    )


class SlotIdentityObservation(SchemaModel):
    schema_version: int = Field(default=2, ge=1)

    sample_id: str
    match_id: str
    timestamp_s: float = Field(ge=0.0)
    evidence_id: str
    stage: str | None = None

    location: SlotLocation
    slot_id: str

    board_row: int | None = Field(default=None, ge=0)
    board_col: int | None = Field(default=None, ge=0)
    bench_slot_index: int | None = Field(default=None, ge=0)

    source_frame_uri: str
    crop_uri: str
    crop_sha256: str
    crop_width: int = Field(gt=0)
    crop_height: int = Field(gt=0)

    # Pixel coordinates in the original source frame.
    context_box: tuple[int, int, int, int]
    footprint_box: tuple[int, int, int, int]

    raw_occupancy_status: str
    raw_occupancy_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    raw_occupancy_score: float

    tracked_occupancy_status: str | None = None
    tracked_occupancy_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    tracked_foreground_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    tracked_source_evidence_id: str | None = None
    tracked_is_current_evidence: bool = False

    scene_valid: bool | None = None
    scene_score: float | None = Field(
        default=None,
        ge=0.0,
    )

    board_usable: bool | None = None
    board_strong_snapshot: bool | None = None
    board_gate_reason: str | None = None
    hud_level: int | None = Field(
        default=None,
        ge=1,
        le=10,
    )
    board_capacity_status: str | None = None

    # 0.21.1 explicitly separates the full raw observation pool from the clean
    # champion-identity training subset.
    occupancy_evidence_tier: OccupancyEvidenceTier
    occupancy_evidence_reason: str

    # trusted: suitable for identity labeling and clean identity training.
    # supported: useful for identity labeling, but not clean training by
    # default because occupancy support is temporal/carry rather than current.
    # raw_candidate: retain for occupancy QA/hard negatives/manual review.
    recommended_for_identity_labeling: bool = False
    recommended_for_identity_training: bool = False
    recommended_for_occupancy_review: bool = False

    # Causal historical priors only: latest roster-evidence snapshot whose
    # episode END is <= this frame timestamp. Never use future acquisitions.
    acquisition_priors: tuple[AcquisitionIdentityPrior, ...] = ()
    acquisition_prior_source_decision_id: str | None = None
    acquisition_prior_source_end_timestamp_s: float | None = Field(
        default=None,
        ge=0.0,
    )
    acquisition_prior_age_s: float | None = Field(
        default=None,
        ge=0.0,
    )

    acquisition_prior_semantics: Literal[
        "historical_non_exhaustive_not_current_ownership"
    ] = "historical_non_exhaustive_not_current_ownership"

    identity_search_space_exhaustive: bool = False
    current_ownership_established: bool = False

    # Observation is unlabeled until a human/model workflow explicitly fills
    # target_type. `no_unit` is a first-class hard-negative target.
    label_status: IdentityLabelStatus = "unlabeled"
    target_type: IdentityTargetType | None = None
    champion_label: str | None = None

    source_board_tracker_version: str | None = None
    source_bench_tracker_version: str | None = None
    source_roster_producer_version: str | None = None
    producer_version: str

    @model_validator(mode="after")
    def validate_identity_target(self):
        if (
            self.target_type == "champion"
            and self.label_status in {
                "human_labeled",
                "confirmed",
            }
            and not self.champion_label
        ):
            raise ValueError(
                "A human/confirmed champion target requires champion_label."
            )

        if (
            self.target_type in {
                "no_unit",
                "uncertain",
                "unusable",
            }
            and self.champion_label is not None
        ):
            raise ValueError(
                "Non-champion target_type cannot carry champion_label."
            )

        return self
