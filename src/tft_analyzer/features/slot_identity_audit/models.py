from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


IdentityTrainingTier = Literal[
    "primary",
    "secondary",
    "recovered_candidate",
]


@dataclass(frozen=True)
class SlotIdentityHumanAuditSettings:
    producer_version: str = "slot-identity-human-label-audit-0.21.7"

    # Human champion labels are semantic truth. Upstream occupancy evidence is
    # retained as a provenance/quality tier rather than being allowed to erase
    # a valid human champion label.
    primary_evidence_tiers: tuple[str, ...] = ("trusted",)
    secondary_evidence_tiers: tuple[str, ...] = ("supported",)
    recovered_candidate_tiers: tuple[str, ...] = ("raw_candidate",)

    # Human no_unit is direct occupancy QA evidence. The audit exports it
    # separately from champion-identity training data.
    export_all_human_no_unit_as_occupancy_hard_negative: bool = True

    hotspot_min_labeled_groups: int = 1
    hotspot_limit: int = 25
