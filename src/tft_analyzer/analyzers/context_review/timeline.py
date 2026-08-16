from __future__ import annotations

from pathlib import Path

from tft_analyzer.core.models.analysis import Finding


def _iter_findings(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                yield Finding.model_validate_json(line)


def _metrics(item: Finding) -> str:
    m = item.metrics
    pieces = []

    hp = m.get("pressure_hp")
    if hp is not None:
        pieces.append(f"HP{hp}")

    spend = m.get("observed_spend")
    if spend is not None:
        pieces.append(f"S{spend}")

    gold_after = m.get("gold_after")
    if gold_after is not None:
        pieces.append(f"G->{gold_after}")

    level_before = m.get("level_before")
    level_after = m.get("level_after")
    if (
        level_before is not None
        and level_after is not None
        and level_before != level_after
    ):
        pieces.append(
            f"L{level_before}->{level_after}"
        )

    rerolls = m.get("reroll_count_min", 0)
    if rerolls:
        rmax = m.get("reroll_count_max")
        pieces.append(
            f"R{rerolls}.."
            f"{rmax if rmax is not None else '?'}"
        )

    board = m.get("board_after")
    capacity = m.get("board_capacity_after")
    if (
        board is not None
        and capacity is not None
        and m.get("board_after_usable_for_strategy")
    ):
        pieces.append(f"B{board}/{capacity}✓")

    return " ".join(pieces) if pieces else "-"


def format_context_review_timeline(
    findings_path,
    *,
    limit=None,
):
    lines = [
        " # stage       start-end(s)  sev    interpretation      code                                metrics                     | finding",
        "-" * 151,
    ]

    for index, item in enumerate(
        _iter_findings(findings_path),
        start=1,
    ):
        if limit is not None and index > limit:
            break

        stage = item.stage or "?"
        start = item.start_timestamp_s or 0.0
        end = item.end_timestamp_s or start

        lines.append(
            f"{index:2d} {stage:>5} "
            f"{start:7.1f}-{end:7.1f} "
            f"{item.severity:<6} "
            f"{item.interpretation:<19.19} "
            f"{(item.finding_code or '-'): <35.35} "
            f"{_metrics(item):<27.27} | "
            f"{item.title}"
        )

    lines.extend(
        [
            "",
            "Policy: review_candidate means 'worth reviewing', never 'player mistake'. decision_grade is not emitted in 0.18.0.",
            "Trust: board/bench-dependent rules may run only when feature_trust.usable_for_strategy=true.",
            "Economy: action spend comes from episode.economy; boundary gold delta is not action accounting.",
            "Infeasible economy: hard-blocks context-aware strategic review for that episode.",
        ]
    )
    return "\n".join(lines)
