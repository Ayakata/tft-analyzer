from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tft_analyzer.core.models.analysis import Finding


def _iter_findings(path):
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield Finding.model_validate_json(line)


def _metric_label(item: Finding) -> str:
    m = item.metrics
    pieces = []
    if m.get("observed_spend") is not None:
        pieces.append(f"S{m['observed_spend']}")
    if m.get("gold_after") is not None:
        pieces.append(f"G->{m['gold_after']}")
    if m.get("reroll_count_min", 0):
        rmax = m.get("reroll_count_max")
        pieces.append(
            f"R{m['reroll_count_min']}..{rmax if rmax is not None else '?'}"
        )
    if m.get("unallocated_spend_min", 0):
        pieces.append(
            f"U>={m['unallocated_spend_min']}"
        )
    if m.get("spend_deficit_min_total", 0):
        pieces.append(
            f"!d{m['spend_deficit_min_total']}"
        )
    return " ".join(pieces) if pieces else "-"


def format_economy_tempo_findings_timeline(
    findings_path,
    *,
    limit=None,
):
    lines = [
        " # stage       start-end(s)  sev    interpretation                 code                              metrics              | finding",
        "------------------------------------------------------------------------------------------------------------------------------------------------",
    ]
    for index, item in enumerate(_iter_findings(findings_path), start=1):
        if limit is not None and index > limit:
            break
        stage = item.stage or "?"
        start = item.start_timestamp_s or 0.0
        end = item.end_timestamp_s or start
        lines.append(
            f"{index:2d} {stage:>5} "
            f"{start:7.1f}-{end:7.1f} "
            f"{item.severity:<6} "
            f"{item.interpretation:<30.30} "
            f"{(item.finding_code or '-'): <33.33} "
            f"{_metric_label(item):<20.20} | "
            f"{item.title}"
        )
    lines.append("")
    lines.append(
        "Policy: 0.16.1 separates expected sparse reconstruction uncertainty from hard data-quality conflicts. "
        "It emits descriptive facts and review candidates, but does not grade player decisions without board-strength/lobby/meta context."
    )
    return "\n".join(lines)
