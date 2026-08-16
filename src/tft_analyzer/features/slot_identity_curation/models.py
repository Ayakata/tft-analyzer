from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from tft_analyzer.core.models.base import SchemaModel


CurationQueueType = Literal[
    "identity_label",
    "occupancy_qa",
]


@dataclass(frozen=True)
class SlotIdentityCurationSettings:
    producer_version: str = "slot-identity-curator-0.21.2"

    # Conservative temporal de-duplication. The canonical match is sampled
    # roughly every 10s, so 15s permits immediate adjacent observations while
    # avoiding long chains across distinct planning phases.
    max_temporal_gap_s: float = 15.0

    # 64-bit dHash Hamming distance. This is intentionally conservative:
    # grouping means "near-duplicate visual observation", not same champion.
    dhash_size: int = 8
    max_dhash_distance: int = 6

    split_on_stage_change: bool = True

    # trusted + supported form the identity-labeling pool. raw_candidate is
    # kept separate for occupancy/hard-negative QA so evidence quality cannot
    # contaminate a clean identity queue.
    identity_tiers: tuple[str, ...] = (
        "trusted",
        "supported",
    )
    occupancy_qa_tiers: tuple[str, ...] = (
        "raw_candidate",
    )


class CuratedSlotVisualGroup(SchemaModel):
    schema_version: int = Field(default=1, ge=1)

    visual_group_id: str
    match_id: str
    queue_type: CurationQueueType

    location: str
    slot_id: str

    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)
    duration_s: float = Field(ge=0.0)

    stage_start: str | None = None
    stage_end: str | None = None
    stages: tuple[str, ...] = ()

    member_count: int = Field(ge=1)
    member_sample_ids: tuple[str, ...]
    member_tier_counts: dict[str, int] = Field(
        default_factory=dict
    )

    representative_sample_id: str
    representative_timestamp_s: float = Field(ge=0.0)
    representative_crop_uri: str
    representative_source_crop_uri: str
    representative_tier: str
    representative_raw_occupancy_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    representative_tracked_source: Literal[
        "current",
        "carry",
        "none",
    ]
    representative_dhash_hex: str

    recommended_for_identity_labeling: bool = False
    recommended_for_identity_training_after_label: bool = False
    recommended_for_occupancy_review: bool = False

    # ML split contract: every temporal observation from one recorded match
    # must remain in the same split.
    split_key: str
    split_unit: Literal["match_id"] = "match_id"

    source_dataset_producer_version: str
    source_manifest_path: str
    producer_version: str
