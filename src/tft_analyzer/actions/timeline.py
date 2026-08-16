from __future__ import annotations

import json
from pathlib import Path

from .models import InferredAction


def _iter_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _action_label(action):
    kind = action.action_type.value
    p = action.params

    if kind == "buy_unit":
        champs = ",".join(p.get("champions", []))
        base = f"BUY[{champs or p.get('count', '?')}]"
        total = p.get("total_gold_cost")
        if total is not None:
            base = f"{base}@{total}g"

        validation = p.get("cost_validation")
        suffix = {
            "cost_consistent": "✓",
            "cost_possible": "~",
            "cost_conflict": "!",
            "unpriced": "?",
            "unobserved": "?",
            "pending": "",
        }.get(validation, "")

        return f"{base}{suffix}"

    if kind == "refresh_shop":
        lo = p.get("count_min", p.get("count_lower_bound", 1))
        hi = p.get("count_max", p.get("count_upper_bound_from_gold", lo))
        return f"REROLL[x{lo}..{hi}]"

    if kind == "purchase_xp":
        return f"BUY_XP[x{p.get('count', '?')}]"

    if kind == "sell_unit":
        return f"SELL[x>={p.get('count_lower_bound', '?')}]"

    if kind == "bench_to_board":
        return f"BENCH->BOARD[x{p.get('count', '?')}]"

    if kind == "board_to_bench":
        return f"BOARD->BENCH[x{p.get('count', '?')}]"

    if kind == "move_unit":
        return f"MOVE[{p.get('subtype', 'unit')}]"

    if kind == "unknown_econ_action":
        lo = p.get("unallocated_spend_min", "?")
        hi = p.get("unallocated_spend_max", "?")
        return (
            f"ECON?[={lo}g]"
            if lo == hi
            else f"ECON?[{lo}..{hi}g]"
        )

    return kind.upper()


def _format_interval(minimum, maximum):
    if maximum is None:
        return f">={minimum}"
    minimum = int(minimum)
    maximum = int(maximum)
    return str(minimum) if minimum == maximum else f"{minimum}..{maximum}"


def _ledger_label(ledger):
    if not ledger or ledger.get("observed_spend") is None:
        return "-"

    spend = int(ledger["observed_spend"])
    required_min = int(ledger.get("required_action_spend_min", ledger.get("action_spend_min", 0)))
    required_max = ledger.get("required_action_spend_max", ledger.get("action_spend_max"))
    if required_max is not None:
        required_max = int(required_max)

    if ledger.get("feasible") is False:
        deficit_min = int(ledger.get("spend_deficit_min") or 0)
        deficit_max = ledger.get("spend_deficit_max")
        if deficit_max is not None:
            deficit_max = int(deficit_max)
        return f"{spend}g ! K[{_format_interval(required_min, required_max)}] deficit[{_format_interval(deficit_min, deficit_max)}]"

    compatible_min = ledger.get("compatible_action_spend_min")
    compatible_max = ledger.get("compatible_action_spend_max")
    if compatible_min is None:
        compatible_min = required_min
    if compatible_max is None:
        compatible_max = required_max
    known = _format_interval(int(compatible_min), int(compatible_max) if compatible_max is not None else None)

    umin_raw = ledger.get("unallocated_spend_min")
    umax_raw = ledger.get("unallocated_spend_max")
    if umin_raw is None or umax_raw is None:
        umin = umax = None
        unknown = "?"
    else:
        umin = int(umin_raw); umax = int(umax_raw)
        unknown = _format_interval(umin, umax)

    unpriced_buy_count = sum(
        int(c.get("count_min", 0))
        for c in ledger.get("components", [])
        if c.get("kind") == "buy_unit" and not bool(c.get("exact_spend"))
    )
    suffix = f",buy?x{unpriced_buy_count}" if unpriced_buy_count else ""
    uncertainty_suffix = ",uncertainty-only" if umin == 0 and umax is not None and umax > 0 else ""
    return f"{spend}=K[{known}]+U[{unknown}]{suffix}{uncertainty_suffix}"


def format_action_timeline(
    actions_path,
    windows_path,
    ledger_path,
    *,
    limit=None,
):
    actions = [
        InferredAction.model_validate(item)
        for item in _iter_json(actions_path)
    ]
    actions_by_id = {
        action.action_id: action
        for action in actions
    }
    ledgers = {
        int(item["window_index"]): item
        for item in _iter_json(ledger_path)
    }

    lines = [
        " start-end(s) stage   Gd shop Bd  Hd  Td ledger                     | inferred actions",
        "---------------------------------------------------------------------------------------------------",
    ]

    shown = 0
    for window in _iter_json(windows_path):
        ids = window.get("action_ids", [])
        if not ids:
            continue
        if limit is not None and shown >= limit:
            break
        shown += 1

        labels = []
        for action_id in ids:
            action = actions_by_id.get(action_id)
            if action is None:
                continue
            quality = {
                "strong": "STR",
                "supported": "SUP",
                "ambiguous": "AMB",
            }[action.quality.value]
            labels.append(
                f"{_action_label(action)} {quality}={action.confidence:.2f}"
            )

        stage = window.get("stage_after") or "?"
        gd = window.get("gold_delta")
        gd_text = f"{gd:+d}" if isinstance(gd, int) else " ? "
        shop = int(window.get("shop_change_count", 0))
        bd = int(window.get("board_delta", 0))
        hd = int(window.get("bench_delta", 0))
        td = int(window.get("total_units_delta", 0))
        ledger = ledgers.get(int(window["window_index"]))

        notes = window.get("notes", [])
        note_text = f" [{','.join(notes)}]" if notes else ""

        lines.append(
            f"{float(window['start_timestamp_s']):6.1f}-"
            f"{float(window['end_timestamp_s']):6.1f} "
            f"{stage:>5} "
            f"{gd_text:>4} "
            f"{shop:>4} "
            f"{bd:+3d} "
            f"{hd:+3d} "
            f"{td:+3d} "
            f"{_ledger_label(ledger):<27} | "
            + "; ".join(labels)
            + note_text
        )

    lines.append("")
    lines.append(
        "ledger: feasible windows use spend=K[compatible action spend]+U[unallocated]. "
        "Infeasible windows use `spend ! K[required] deficit[...]` and have no U interval. "
        "buy? appears only for BUY_UNIT without an exact trusted price."
    )
    lines.append(
        "Quality: STR=strong, SUP=supported, AMB=ambiguous. "
        "Actions are bounded-window inferences, not exact click timestamps."
    )
    return "\n".join(lines)
