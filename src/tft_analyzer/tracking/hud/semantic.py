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
    if kind == ObservationKind.HP:
        return {"hp": int(value["hp"])}
    if kind == ObservationKind.SHOP:
        raw_slots = value.get("slots", [])
        slots = []
        for slot in raw_slots:
            if bool(slot.get("occupied", False)):
                slots.append(slot.get("resolved_name"))
            else:
                slots.append(None)
        return {"slots": slots}
    raise ValueError(f"Unsupported HUD observation kind: {kind}")
