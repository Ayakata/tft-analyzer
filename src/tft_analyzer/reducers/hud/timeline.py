from __future__ import annotations

from pathlib import Path

from tft_analyzer.storage import iter_game_states


def _meta_conf(state, field):
    meta = state.field_meta.get(field)
    return f"{meta.confidence:.3f}" if meta is not None else "?"


def format_game_state_timeline(
    states_path: Path | str,
    *,
    limit: int | None = None,
) -> str:
    lines = [
        " time(s)   stage level      xp  gold  conf   field_conf(s/l/x/g)",
        "------------------------------------------------------------------",
    ]

    count = 0
    for state in iter_game_states(states_path):
        if limit is not None and count >= limit:
            break

        stage = (
            f"{state.stage}-{state.round}"
            if state.stage is not None and state.round is not None
            else "?"
        )
        level = (
            f"L{state.player.level}"
            if state.player.level is not None
            else "?"
        )
        xp = (
            f"{state.player.xp}/{state.player.xp_required}"
            if (
                state.player.xp is not None
                and state.player.xp_required is not None
            )
            else "?"
        )
        gold = (
            str(state.player.gold)
            if state.player.gold is not None
            else "?"
        )

        field_conf = "/".join(
            _meta_conf(state, field)
            for field in ("stage", "level", "xp", "gold")
        )

        lines.append(
            f"{state.timestamp_s:8.1f}  "
            f"{stage:>6} "
            f"{level:>5} "
            f"{xp:>7} "
            f"{gold:>5} "
            f"{state.confidence:5.3f}   "
            f"{field_conf}"
        )
        count += 1

    return "\n".join(lines)
