from __future__ import annotations

from pathlib import Path

from .models import EpisodeRosterEvidence


def _iter(path: Path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                yield EpisodeRosterEvidence.model_validate_json(
                    line
                )


def _counts(
    values: dict[str, int],
    *,
    prefix: str = "",
) -> str:
    if not values:
        return "-"
    return ",".join(
        f"{prefix}{name}x{count}"
        for name, count in sorted(
            values.items()
        )
    )


def _acquired(
    item: EpisodeRosterEvidence,
) -> str:
    values = [
        (
            champion.champion,
            champion.confirmed_acquired_copy_lower_bound,
        )
        for champion in item.after.champions
        if champion.confirmed_acquired_copy_lower_bound > 0
    ]
    if not values:
        return "-"
    return ",".join(
        f"{name} acquired>={count}"
        for name, count in values
    )


def format_roster_evidence_timeline(
    contexts_path: Path | str,
    *,
    limit: int | None = 120,
    changes_only: bool = False,
) -> str:
    values = list(
        _iter(
            Path(contexts_path)
        )
    )
    if changes_only:
        values = [
            item
            for item in values
            if (
                item.delta.confirmed_buys
                or item.delta.candidate_buys
                or item.delta.identified_sells
                or item.delta.unidentified_confirmed_buy_copy_count
                or item.delta.unidentified_candidate_buy_copy_count
                or item.delta.unidentified_sell_unit_count_lower_bound
                or item.delta.unresolved_economy_action_count
            )
        ]
    if limit is not None:
        values = values[:limit]

    lines = [
        " # stage       start-end(s)  confirmed buys            candidate buys            sells       econ?       | confirmed acquisition copy lower bounds",
        "-" * 164,
    ]

    for index, item in enumerate(
        values,
        start=1,
    ):
        confirmed = _counts(
            item.delta.confirmed_buys
        )
        candidate = _counts(
            item.delta.candidate_buys,
            prefix="?",
        )

        sell_parts = []
        if item.delta.identified_sells:
            sell_parts.append(
                _counts(
                    item.delta.identified_sells,
                    prefix="-",
                )
            )
        if (
            item.delta.unidentified_sell_unit_count_lower_bound
            > 0
        ):
            sell_parts.append(
                f"-?x{item.delta.unidentified_sell_unit_count_lower_bound}"
            )
        sells = (
            ",".join(sell_parts)
            if sell_parts
            else "-"
        )

        econ = (
            "-"
            if item.delta.unresolved_economy_action_count == 0
            else (
                f"U{item.delta.unresolved_economy_action_count}"
                f"[{item.delta.unresolved_economy_spend_min}.."
                f"{item.delta.unresolved_economy_spend_max}]"
            )
        )

        lines.append(
            f"{index:2d} "
            f"{(item.stage_start or '?'):>5} "
            f"{item.start_timestamp_s:7.1f}-"
            f"{item.end_timestamp_s:7.1f} "
            f"{confirmed:<25.25} "
            f"{candidate:<25.25} "
            f"{sells:<11.11} "
            f"{econ:<11.11} | "
            f"{_acquired(item)}"
        )

    lines.extend(
        [
            "",
            "semantics: champion acquired>=N is a historical base-copy acquisition lower bound from confirmed BUY identity evidence.",
            "?championxN is candidate acquisition evidence (for example a low-confidence or cost-conflicted BUY).",
            "SELL evidence is historical only. Sparse capture does not prove a complete sell history, so current ownership is not established.",
            "U#[min..max] is unresolved economy spend. It can hide roster changes but is not converted into invented champion acquisitions.",
            "current ownership, complete roster, board/bench assignment and stars are not established in 0.20.1.",
        ]
    )
    return "\n".join(lines)
