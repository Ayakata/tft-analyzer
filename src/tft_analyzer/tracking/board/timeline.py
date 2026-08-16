from __future__ import annotations

import json
from pathlib import Path


def _iter(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _short_reason(
    reason: str,
) -> str:
    mapping = {
        "full_level_snapshot": "full-cap",
        "planning_visual_stable": "plan-ok",
        "planning_visual_unstable": "plan-vis",
        "level_capacity_exceeded": "over-cap",
        "outside_planning_window": "outside",
        "visual_fallback_stable": "visual",
        "visual_fallback_unstable": "vis-bad",
        "scene_invalid": "scene-bad",
    }
    return mapping.get(
        reason,
        reason[:8],
    )


def format_board_occupancy_timeline(
    board_path,
    bench_path,
    *,
    limit=None,
) -> str:
    boards = list(
        _iter(board_path)
    )
    benches = list(
        _iter(bench_path)
    )

    lines = [
        " time(s)  gate      why       lvl cand board  bench   board rows / bench",
        "--------------------------------------------------------------------------------------",
    ]

    for i, (b, x) in enumerate(
        zip(
            boards,
            benches,
        )
    ):
        if (
            limit is not None
            and i >= limit
        ):
            break

        cells = b["cells"]
        rows = []
        for r in range(4):
            vals = cells[
                r * 7:
                (r + 1) * 7
            ]
            rows.append(
                "".join(
                    "O"
                    if c["status"]
                    == "occupied"
                    else "."
                    if c["status"]
                    == "empty"
                    else "?"
                    for c in vals
                )
            )

        slots = "".join(
            "O"
            if c["status"]
            == "occupied"
            else "."
            if c["status"]
            == "empty"
            else "?"
            for c in x["slots"]
        )

        level = b.get(
            "hud_level"
        )
        level_text = (
            f"L{level}"
            if level is not None
            else "L?"
        )

        marker = (
            "*"
            if b.get(
                "strong_snapshot"
            )
            else " "
        )

        lines.append(
            f"{b['timestamp_s']:8.1f}  "
            f"{b['stability']:<8} "
            f"{_short_reason(b.get('gate_reason','')):<8} "
            f"{level_text:>3} "
            f"{b.get('candidate_occupied_count',0):2d} "
            f"{b['occupied_count']:2d}/28 "
            f"{x['occupied_count']:2d}/9   "
            f"{' '.join(rows)} / {slots}"
            f"{marker}"
        )

    lines.append("")
    lines.append(
        "* = atomic full-level snapshot; "
        "over-cap/outside-planning frames never update canonical board"
    )
    lines.append(
        "O=occupied .=empty ?=unknown"
    )
    return "\n".join(lines)
