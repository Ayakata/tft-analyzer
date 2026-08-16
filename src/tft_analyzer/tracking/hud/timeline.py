from __future__ import annotations

from pathlib import Path

from tft_analyzer.storage import iter_tracked_hud_states


def _format_field(field, formatter):
    if field.status == "unknown":
        return "?"
    if field.status == "stale":
        return "<stale>"

    text = formatter(field.value)
    if field.status == "carried":
        text += "~"
    return text


def _compact_shop(value) -> str:
    slots = list((value or {}).get("slots", []))
    if not slots:
        return "?"
    parts = []
    for name in slots:
        if name is None:
            parts.append("-")
        else:
            parts.append(str(name)[:4])
    return "[" + "/".join(parts) + "]"


def format_hud_timeline(
    states_path: Path | str,
    *,
    limit: int | None = None,
) -> str:
    lines = [
        " time(s)   stage    level      xp     gold    hp  shop",
        "--------------------------------------------------------------------------",
    ]

    count = 0
    for state in iter_tracked_hud_states(states_path):
        if limit is not None and count >= limit:
            break

        stage = _format_field(
            state.stage,
            lambda v: f"{v['stage']}-{v['round']}",
        )
        level = _format_field(
            state.level,
            lambda v: f"L{v['level']}",
        )
        xp = _format_field(
            state.xp,
            lambda v: f"{v['current']}/{v['required']}",
        )
        gold = _format_field(
            state.gold,
            lambda v: str(v["gold"]),
        )
        hp = _format_field(
            state.hp,
            lambda v: str(v["hp"]),
        )
        shop = _format_field(
            state.shop,
            _compact_shop,
        )

        lines.append(
            f"{state.timestamp_s:8.1f} "
            f"{stage:>8} "
            f"{level:>8} "
            f"{xp:>8} "
            f"{gold:>8} "
            f"{hp:>6}  "
            f"{shop}"
        )
        count += 1

    lines.append("")
    lines.append("~ = carried from a recent observation")
    lines.append("shop uses four-character identity prefixes; '-' = empty slot")
    return "\n".join(lines)
