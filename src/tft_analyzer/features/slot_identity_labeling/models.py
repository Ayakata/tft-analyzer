from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from tft_analyzer.core.models.base import SchemaModel


IdentityTargetType = Literal[
    "champion",
    "no_unit",
    "uncertain",
    "unusable",
]

IdentityAnnotationStatus = Literal[
    "human_labeled",
    "confirmed",
]


@dataclass(frozen=True)
class SlotIdentityLabelingSettings:
    package_producer_version: str = (
        "slot-identity-label-package-0.21.3"
    )
    import_producer_version: str = (
        "slot-identity-label-importer-0.21.3"
    )

    # Incremental labeling is the normal workflow. Empty target_type rows are
    # retained as unlabeled queue entries and ignored by import unless a
    # complete pass is explicitly requested.
    allow_partial_import: bool = True

    # Champion labels should resolve against the pinned match set when a
    # trusted Data Dragon catalog is available.
    require_catalog_for_champion_labels: bool = True


class IdentityLabelAssignment(SchemaModel):
    visual_group_id: str

    target_type: IdentityTargetType
    champion_label: str | None = None

    label_status: IdentityAnnotationStatus = "human_labeled"
    annotator: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_target(self):
        if (
            self.target_type == "champion"
            and not self.champion_label
        ):
            raise ValueError(
                "target_type=champion requires champion_label"
            )

        if (
            self.target_type != "champion"
            and self.champion_label
        ):
            raise ValueError(
                "non-champion target_type cannot carry champion_label"
            )

        return self


class LabeledSlotVisualGroup(SchemaModel):
    schema_version: int = Field(default=1, ge=1)

    visual_group_id: str
    match_id: str
    queue_type: str

    location: str
    slot_id: str

    stage_start: str | None = None
    stage_end: str | None = None
    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)

    member_count: int = Field(ge=1)
    representative_crop_uri: str
    representative_tier: str
    representative_tracked_source: str

    recommended_for_identity_training_after_label: bool

    target_type: IdentityTargetType
    champion_label: str | None = None
    champion_normalized_name: str | None = None
    champion_id: str | None = None
    champion_catalog_validated: bool = False

    label_status: IdentityAnnotationStatus
    annotator: str | None = None
    notes: str | None = None

    # Downstream-ready flags. These remain descriptive artifacts rather than
    # automatic train/val/test assignment.
    eligible_visual_champion_training_group: bool = False
    eligible_occupancy_negative_group: bool = False

    split_key: str
    split_unit: Literal["match_id"] = "match_id"

    source_curation_producer_version: str
    source_visual_groups_path: str
    producer_version: str

    @model_validator(mode="after")
    def validate_target(self):
        if (
            self.target_type == "champion"
            and not self.champion_label
        ):
            raise ValueError(
                "champion target requires champion_label"
            )

        if (
            self.target_type != "champion"
            and self.champion_label
        ):
            raise ValueError(
                "non-champion target cannot carry champion_label"
            )

        return self
