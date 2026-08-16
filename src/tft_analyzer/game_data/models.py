from __future__ import annotations

from typing import Literal

from pydantic import Field

from tft_analyzer.core.models.base import SchemaModel


class ChampionCatalogEntry(SchemaModel):
    champion_id: str
    name: str
    normalized_name: str

    # Riot Data Dragon names this field `tier`. The analyzer preserves that
    # source field and uses it as the TFT shop-cost tier when uniquely resolved.
    tier: int | None = Field(default=None, ge=0)

    image_full: str | None = None


class ChampionCatalogSnapshot(SchemaModel):
    provider: Literal["riot_ddragon"] = "riot_ddragon"
    version: str
    locale: str

    source_url: str
    source_sha256: str
    fetched_at_utc: str

    source_field_for_cost: Literal["tier"] = "tier"

    champions: tuple[ChampionCatalogEntry, ...] = ()


class ChampionCostResolution(SchemaModel):
    query: str
    normalized_query: str

    status: Literal[
        "resolved_unique",
        "resolved_consensus",
        "missing",
        "ambiguous",
    ]

    cost: int | None = Field(default=None, ge=0)

    candidate_ids: tuple[str, ...] = ()
    candidate_names: tuple[str, ...] = ()
    candidate_tiers: tuple[int, ...] = ()

    provider: str
    version: str
    locale: str



class SetInferenceScore(SchemaModel):
    set_id: str
    score: float = Field(ge=0.0)
    supporting_names: tuple[str, ...] = ()
    unique_anchor_names: tuple[str, ...] = ()


class GameContext(SchemaModel):
    set_id: str
    patch: str
    data_dragon_version: str

    resolution_source: Literal[
        "explicit_cli",
        "match_metadata",
        "config",
        "auto_inferred",
    ]

    catalog_provider: str
    catalog_locale: str
    catalog_source_sha256: str

    scoped_champion_count: int = Field(ge=0)

    observed_roster_name_count: int = Field(ge=0)
    set_support_score: float | None = Field(default=None, ge=0.0)
    set_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    set_margin: float | None = Field(default=None, ge=0.0)
    set_candidates: tuple[SetInferenceScore, ...] = ()

    created_at_utc: str
