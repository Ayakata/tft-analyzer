from __future__ import annotations

from typing import Any

from tft_analyzer.core.enums import ObservationKind


def canonical_hud_value(
    kind: ObservationKind,
    value: dict[str, Any],
) -> dict[str, Any]:
    """Return game semantics only; strip OCR/debug metadata."""
    if kind == ObservationKind.STAGE:
        return {"stage": int(value["stage"]), "round": int(value["round"])}
    if kind == ObservationKind.GOLD:
        return {"gold": int(value["gold"])}
    if kind == ObservationKind.LEVEL:
        return {"level": int(value["level"])}
    if kind == ObservationKind.XP:
        return {"current": int(value["current"]), "required": int(value["required"])}
    raise ValueError(f"Unsupported HUD observation kind: {kind}")
