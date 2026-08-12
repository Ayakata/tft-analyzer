from typing import Any

from tft_analyzer.core.enums import ActionType
from .base import SchemaModel


class SemanticAction(SchemaModel):
    action_id: str
    action_type: ActionType
    params: dict[str, Any] = {}
    legal: bool | None = None
