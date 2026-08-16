from __future__ import annotations

import json
from pathlib import Path

from tft_analyzer.core.models.decisions import DecisionEpisode


def _iter_episodes(path):
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield DecisionEpisode.model_validate_json(line)


def _group_label(group):
    counts = {}
    for action_type in group.action_types:
        counts[action_type] = counts.get(action_type, 0) + 1

    labels = []
    aliases = {
        "buy_unit": "BUY",
        "refresh_shop": "ROLL",
        "purchase_xp": "XP",
        "move_unit": "MOVE",
        "bench_to_board": "B->F",
        "board_to_bench": "F->B",
        "sell_unit": "SELL",
        "unknown_econ_action": "ECON?",
    }
    for action_type, count in counts.items():
        label = aliases.get(action_type, action_type.upper())
        labels.append(f"{label}x{count}" if count > 1 else label)

    return "+".join(labels) if labels else "-"


def _state_label(state):
    if state is None:
        return "?"
    parts = []
    if state.gold is not None:
        parts.append(f"G{state.gold}")
    if state.level is not None:
        parts.append(f"L{state.level}")
    if state.xp_absolute is not None:
        parts.append(f"XP{state.xp_absolute}")
    if state.board_count is not None:
        parts.append(f"B{state.board_count}")
    if state.bench_count is not None:
        parts.append(f"H{state.bench_count}")
    return "/".join(parts) if parts else "?"


def _economy_label(episode):
    econ = episode.economy
    if econ.infeasible_window_count:
        return (
            f"S{econ.observed_spend_total} "
            f"REQ>={econ.required_action_spend_min} "
            f"!d{econ.spend_deficit_min_total}"
        )

    req_max = econ.required_action_spend_max
    req = (
        str(econ.required_action_spend_min)
        if req_max == econ.required_action_spend_min
        else (
            f"{econ.required_action_spend_min}..{req_max}"
            if req_max is not None
            else f">={econ.required_action_spend_min}"
        )
    )
    return (
        f"S{econ.observed_spend_total} "
        f"K[{req}] U[{econ.unallocated_spend_min}..{econ.unallocated_spend_max}]"
    )


def format_decision_episode_timeline(
    episodes_path,
    *,
    limit=None,
):
    lines = [
        " # stage       start-end(s)  dt   win  conf  state before -> state after        economy                    | window-ordered action groups",
        "------------------------------------------------------------------------------------------------------------------------------------------",
    ]

    for index, episode in enumerate(_iter_episodes(episodes_path), start=1):
        if limit is not None and index > limit:
            break

        stage = episode.stage_end or episode.stage_start or "?"
        groups = " -> ".join(
            "{" + _group_label(group) + "}"
            for group in episode.action_groups
        )
        state = (
            f"{_state_label(episode.state_before)} -> "
            f"{_state_label(episode.state_after)}"
        )
        duration = episode.end_timestamp_s - episode.start_timestamp_s

        lines.append(
            f"{index:2d} {stage:>5} "
            f"{episode.start_timestamp_s:7.1f}-{episode.end_timestamp_s:7.1f} "
            f"{duration:5.1f}s "
            f"{episode.sampling.source_window_count:3d} "
            f"{episode.confidence:5.2f} "
            f"{state:<34.34} "
            f"{_economy_label(episode):<26.26} | "
            f"{groups}"
        )

    lines.append("")
    lines.append(
        "Ordering contract: groups are ordered only by non-overlapping source windows; "
        "actions inside {...} are unordered. Exact click timestamps/sequences are never reconstructed from sparse screenshots."
    )
    return "\n".join(lines)
