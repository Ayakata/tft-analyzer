from __future__ import annotations

from .models import MatchReviewCard


def _pair(before, after):
    if before is None and after is None:
        return "?"
    if before == after:
        return str(before)
    left = "?" if before is None else str(before)
    right = "?" if after is None else str(after)
    return f"{left}->{right}"


def _state_line(card: MatchReviewCard) -> str:
    state = card.state
    parts = []
    for label, before_key, after_key in (
        ("HP", "hp_before", "hp_after"),
        ("Gold", "gold_before", "gold_after"),
        ("Level", "level_before", "level_after"),
        ("XPabs", "xp_absolute_before", "xp_absolute_after"),
    ):
        value = _pair(state.get(before_key), state.get(after_key))
        if value != "?":
            parts.append(f"{label} {value}")
    board = state.get("board_after")
    capacity = state.get("board_capacity_after")
    if board is not None and capacity is not None:
        parts.append(f"Board {board}/{capacity} trusted")
    return " | ".join(parts) if parts else "State unavailable"


def format_review_cards_timeline(
    cards: list[MatchReviewCard],
    *,
    limit: int | None = None,
) -> str:
    values = cards if limit is None else cards[:limit]
    lines = [
        " # stage       start-end(s)  priority  type             metrics                                  | review card",
        "-" * 145,
    ]
    for index, card in enumerate(values, 1):
        activity = card.activity
        metrics = []
        if activity.get("pressure_hp") is not None:
            metrics.append(f"HP{activity['pressure_hp']}")
        if activity.get("observed_spend") is not None:
            metrics.append(f"S{activity['observed_spend']}")
        if activity.get("reroll_count_min"):
            upper = (
                "?"
                if activity.get("reroll_count_max") is None
                else activity.get("reroll_count_max")
            )
            metrics.append(f"R{activity['reroll_count_min']}..{upper}")
        if card.state.get("gold_after") is not None:
            metrics.append(f"G->{card.state['gold_after']}")
        level_before = card.state.get("level_before")
        level_after = card.state.get("level_after")
        if (
            level_before is not None
            and level_after is not None
            and level_before != level_after
        ):
            metrics.append(f"L{level_before}->{level_after}")

        lines.append(
            f"{index:2d} {(card.stage or '?'):>5} "
            f"{card.start_timestamp_s:7.1f}-{card.end_timestamp_s:7.1f} "
            f"{card.priority:<9} {card.card_type:<16.16} "
            f"{' '.join(metrics) or '-':<40.40} | {card.title}"
        )

    lines.extend(
        [
            "",
            "priority: review importance only; not decision quality, mistake probability or strategy score.",
            "data_quality cards are reconstruction blockers and remain separate from gameplay review.",
            "board values are surfaced as facts only when feature_trust.usable_for_strategy=true.",
        ]
    )
    return "\n".join(lines)


def render_review_markdown(
    cards: list[MatchReviewCard],
    *,
    match_id: str,
    game_context: dict,
    producer_version: str,
) -> str:
    lines = [
        "# TFT Match Review",
        "",
        f"- Match: `{match_id}`",
        f"- Report: `{producer_version}`",
        f"- Set: `{game_context.get('set_id')}`",
        f"- Patch: `{game_context.get('patch')}`",
        "",
        "> Review priority measures how useful a moment is to inspect. It is not a decision grade or mistake probability.",
        "",
    ]

    for index, card in enumerate(cards, 1):
        prefix = "QA" if card.card_type == "data_quality" else "REVIEW"
        lines.extend(
            [
                f"## {index}. [{prefix} / {card.priority.upper()}] {card.stage or '?'} — {card.title}",
                "",
                f"Time: `{card.start_timestamp_s:.1f}–{card.end_timestamp_s:.1f}s`",
                "",
                f"State: {_state_line(card)}",
                "",
                card.summary,
                "",
                "### Observed",
                "",
            ]
        )
        lines.extend(f"- {fact}" for fact in card.observed_facts)
        if card.why_review:
            lines.extend(["", "### Why review", ""])
            lines.extend(f"- {reason}" for reason in card.why_review)
        if card.limitations:
            lines.extend(["", "### Not established yet", ""])
            lines.extend(f"- {limitation}" for limitation in card.limitations)
        lines.extend(
            [
                "",
                "Source finding codes: "
                + ", ".join(f"`{code}`" for code in card.source_finding_codes),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"
