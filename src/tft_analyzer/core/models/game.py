from __future__ import annotations

from pydantic import Field

from tft_analyzer.core.enums import GamePhase
from .base import SchemaModel


class BoardPosition(SchemaModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class UnitInstance(SchemaModel):
    instance_id: str
    champion_id: str | None = None
    stars: int | None = Field(default=None, ge=1, le=4)
    position: BoardPosition | None = None
    items: tuple[str, ...] = ()
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PlayerState(SchemaModel):
    hp: int | None = Field(default=None, ge=0)
    gold: int | None = Field(default=None, ge=0)
    level: int | None = Field(default=None, ge=1)
    xp: int | None = Field(default=None, ge=0)
    xp_required: int | None = Field(default=None, ge=1)


class ShopState(SchemaModel):
    slots: tuple[str | None, ...] = ()
    locked: bool | None = None


class OpponentSnapshot(SchemaModel):
    player_id: str
    hp: int | None = Field(default=None, ge=0)
    level: int | None = Field(default=None, ge=1)
    board: tuple[UnitInstance, ...] = ()
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class StateFieldMeta(SchemaModel):
    """
    Confidence/freshness of the current canonical value for one field.

    This metadata may be refreshed by repeated tracked observations without
    creating a new semantic GameState.
    """

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    last_observed_at_s: float | None = Field(default=None, ge=0.0)
    age_s: float | None = Field(default=None, ge=0.0)

    source_observation_id: str | None = None
    source_evidence_id: str | None = None
    source_tracked_state_id: str | None = None


class GameState(SchemaModel):
    state_id: str
    match_id: str
    timestamp_s: float = Field(ge=0)

    patch: str | None = None
    set_id: str | None = None

    stage: int | None = Field(default=None, ge=1)
    round: int | None = Field(default=None, ge=1)
    phase: GamePhase = GamePhase.UNKNOWN

    player: PlayerState = PlayerState()
    shop: ShopState = ShopState()

    board: tuple[UnitInstance, ...] = ()
    bench: tuple[UnitInstance, ...] = ()
    inventory: tuple[str, ...] = ()
    augments: tuple[str, ...] = ()
    active_traits: tuple[str, ...] = ()
    observed_opponents: tuple[OpponentSnapshot, ...] = ()

    # Bounded lineage: follow parent_state_id to reconstruct full history.
    parent_state_id: str | None = None
    applied_event_ids: tuple[str, ...] = ()
    source_state_ids: tuple[str, ...] = ()

    field_meta: dict[str, StateFieldMeta] = Field(default_factory=dict)

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reducer_version: str
