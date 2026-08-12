from pydantic import Field

from .actions import SemanticAction
from .base import SchemaModel


class TransitionSample(SchemaModel):
    """Canonical sample for future BC/offline-RL datasets."""

    match_id: str
    state_id: str
    action: SemanticAction
    next_state_id: str | None

    timestamp_s: float = Field(ge=0)
    done: bool = False
    final_placement: int | None = Field(default=None, ge=1, le=8)

    action_mask: tuple[str, ...] = ()
    behavior_rank: str | None = None

    state_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    action_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
