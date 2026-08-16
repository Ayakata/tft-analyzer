from __future__ import annotations

from pathlib import Path

from .models import EpisodePlayerContext


def _iter(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield EpisodePlayerContext.model_validate_json(line)


def _pair(a, b, unknown="?"):
    left = unknown if a is None else str(a)
    right = unknown if b is None else str(b)
    return f"{left}->{right}"


def _util(a, b):
    def one(value):
        return "?" if value is None else f"{value * 100:.0f}%"
    return f"{one(a)}->{one(b)}"


def _scene(value):
    if value is True:
        return "Y"
    if value is False:
        return "N"
    return "?"


def _trust_symbol(trust):
    if trust.semantics == "exact":
        return "E"
    if trust.semantics == "lower_bound":
        return "L"
    if trust.semantics == "carried":
        return "C"
    if trust.semantics == "unusable":
        return "X"
    return "?"


def _board_trust_pair(item):
    return (
        f"{_trust_symbol(item.feature_trust.before.board_count)}/"
        f"{_trust_symbol(item.feature_trust.after.board_count)}"
    )


def _econ(item):
    if item.quality.economy_feasible is False:
        return "!"
    if item.quality.reconstruction_uncertainty:
        return "U"
    return "OK"


def format_episode_context_timeline(
    contexts_path: Path | str,
    *,
    limit: int | None = 120,
) -> str:
    values = list(_iter(Path(contexts_path)))
    if limit is not None:
        values = values[:limit]

    lines = [
        " # stage       start-end(s)    HP       gold      lvl    XPabs      board/cap      util      bench    scene align Btrust econ | deltas",
        "-" * 151,
    ]

    for i, item in enumerate(values, 1):
        b = item.before
        a = item.after
        stage = item.stage_start or b.stage or "-"
        board_pair = (
            f"{b.board_count if b.board_count is not None else '?'}/{b.board_capacity if b.board_capacity is not None else '?'}"
            f"->{a.board_count if a.board_count is not None else '?'}/{a.board_capacity if a.board_capacity is not None else '?'}"
        )
        align = (
            ("E" if item.quality.before_exact_alignment else "F")
            + "/"
            + ("E" if item.quality.after_exact_alignment else "F")
        )
        scene = (
            f"{_scene(item.quality.scene_valid_before)}/"
            f"{_scene(item.quality.scene_valid_after)}"
        )
        delta_parts = []
        for name, value in (
            ("HP", item.delta.hp),
            ("G", item.delta.gold),
            ("L", item.delta.level),
            ("B", item.delta.board_count),
            ("N", item.delta.bench_count),
        ):
            if value is not None and value != 0:
                delta_parts.append(f"d{name}{value:+d}")
        delta_text = " ".join(delta_parts) or "-"

        lines.append(
            f"{i:>2} {stage:>5} "
            f"{b.timestamp_s:>7.1f}-{a.timestamp_s:>7.1f} "
            f"{_pair(b.hp, a.hp):>9} "
            f"{_pair(b.gold, a.gold):>9} "
            f"{_pair(b.level, a.level):>7} "
            f"{_pair(b.xp_absolute, a.xp_absolute):>10} "
            f"{board_pair:>15} "
            f"{_util(b.board_utilization, a.board_utilization):>11} "
            f"{_pair(b.bench_count, a.bench_count):>8} "
            f"{scene:>5} {align:>5} {_board_trust_pair(item):>6} {_econ(item):>4} | {delta_text}"
        )

    lines.extend(
        [
            "",
            "align: E=exact evidence-aligned HUD+board+bench boundary, F=episode-boundary fallback.",
            "Btrust: E=exact strong board snapshot, L=confirmed lower bound, C=carried, X=unusable scene, ?=unknown.",
            "econ: OK=no unresolved spend, U=sparse reconstruction uncertainty, !=infeasible economy constraints.",
            "Boundary gold delta is an observed state delta, not action accounting; use episode.economy for action spend.",
            "HP/gold/level/board/bench deltas describe observed episode boundaries; they do not reconstruct hidden intra-window actions.",
        ]
    )
    return "\n".join(lines)
