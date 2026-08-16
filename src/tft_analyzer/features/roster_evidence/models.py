from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from tft_analyzer.core.models.base import SchemaModel


RosterEvidenceStatus = Literal[
    "confirmed_identity_buy",
    "candidate_identity_buy",
    "unidentified_buy",
    "identified_sell",
    "unidentified_sell",
    "unresolved_economy",
]


@dataclass(frozen=True)
class RosterEvidenceSettings:
    producer_version: str = "roster-evidence-builder-0.20.1"

    # BUY identity becomes confirmed acquisition evidence only when the semantic
    # action itself is sufficiently supported. Cost-conflicted BUY remains
    # candidate evidence even if the shop identity is readable.
    min_confirmed_buy_confidence: float = 0.68
    exclude_cost_conflict_from_confirmed: bool = True

    # DecisionEpisodes are the sparse temporal envelope for this stage. Failing
    # coverage is safer than silently building incomplete acquisition history.
    require_relevant_action_coverage: bool = True


class RosterActionEvidence(SchemaModel):
    action_id: str
    action_type: str
    status: RosterEvidenceStatus

    confidence: float = Field(ge=0.0, le=1.0)
    champions: tuple[str, ...] = ()
    count: int = Field(default=0, ge=0)

    cost_validation: str | None = None
    reason: str
    evidence_ids: tuple[str, ...] = ()


class RosterChampionEvidence(SchemaModel):
    champion: str

    # Historical acquisition fact. It is never decremented by SELL evidence:
    # seeing a later sell does not erase the fact that these copies were
    # previously acquired.
    confirmed_acquired_copy_lower_bound: int = Field(
        default=0,
        ge=0,
    )
    candidate_acquired_copy_count: int = Field(
        default=0,
        ge=0,
    )

    # SELL is retained as historical evidence only. Current upstream SELL
    # identity/star coverage is insufficient to infer present ownership.
    identified_sell_unit_count: int = Field(
        default=0,
        ge=0,
    )

    current_ownership_status: Literal[
        "not_established"
    ] = "not_established"


class RosterEvidenceSnapshot(SchemaModel):
    acquisition_semantics: Literal[
        "confirmed_history_lower_bound"
    ] = "confirmed_history_lower_bound"

    complete_roster_known: bool = False
    complete_sell_history_known: bool = False

    current_ownership_status: Literal[
        "not_established"
    ] = "not_established"

    champions: tuple[RosterChampionEvidence, ...] = ()

    confirmed_identity_buy_copy_count: int = Field(
        default=0,
        ge=0,
    )
    candidate_identity_buy_copy_count: int = Field(
        default=0,
        ge=0,
    )

    unidentified_confirmed_buy_copy_count: int = Field(
        default=0,
        ge=0,
    )
    unidentified_candidate_buy_copy_count: int = Field(
        default=0,
        ge=0,
    )

    identified_sell_unit_count: int = Field(
        default=0,
        ge=0,
    )
    unidentified_sell_unit_count_lower_bound: int = Field(
        default=0,
        ge=0,
    )

    unresolved_economy_action_count: int = Field(
        default=0,
        ge=0,
    )
    unresolved_economy_spend_min_total: int = Field(
        default=0,
        ge=0,
    )
    unresolved_economy_spend_max_total: int = Field(
        default=0,
        ge=0,
    )

    # Fraction of observed BUY copy count whose identity is confirmed.
    # Candidate and unidentified copies remain in the denominator.
    confirmed_buy_identity_coverage: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )


class RosterEpisodeDelta(SchemaModel):
    confirmed_buys: dict[str, int] = Field(
        default_factory=dict
    )
    candidate_buys: dict[str, int] = Field(
        default_factory=dict
    )

    unidentified_confirmed_buy_copy_count: int = Field(
        default=0,
        ge=0,
    )
    unidentified_candidate_buy_copy_count: int = Field(
        default=0,
        ge=0,
    )

    identified_sells: dict[str, int] = Field(
        default_factory=dict
    )
    unidentified_sell_unit_count_lower_bound: int = Field(
        default=0,
        ge=0,
    )

    unresolved_economy_action_count: int = Field(
        default=0,
        ge=0,
    )
    unresolved_economy_spend_min: int = Field(
        default=0,
        ge=0,
    )
    unresolved_economy_spend_max: int = Field(
        default=0,
        ge=0,
    )

    action_evidence: tuple[RosterActionEvidence, ...] = ()


class EpisodeRosterEvidence(SchemaModel):
    schema_version: int = Field(default=2, ge=1)

    roster_context_id: str
    match_id: str
    decision_id: str

    stage_start: str | None = None
    stage_end: str | None = None
    start_timestamp_s: float = Field(ge=0.0)
    end_timestamp_s: float = Field(ge=0.0)

    before: RosterEvidenceSnapshot
    delta: RosterEpisodeDelta
    after: RosterEvidenceSnapshot

    source_episode_producer_version: str
    source_action_producer_version: str | None = None
    producer_version: str
