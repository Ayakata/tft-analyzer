import json
from pathlib import Path

from tft_analyzer.actions import (
    ActionFusionSettings,
    infer_match_actions,
)


def field(value, status="carried"):
    return {
        "value": value,
        "confidence": 1.0 if value is not None else 0.0,
        "source_observation_id": None,
        "source_evidence_id": None,
        "source_timestamp_s": None,
        "age_s": 0.0 if value is not None else None,
        "status": status,
    }


def hud(t, eid, *, gold, gold_status, shop, shop_status):
    return {
        "state_id": f"hud-{eid}",
        "match_id": "m",
        "timestamp_s": t,
        "evidence_id": eid,
        "stage": field({"stage": 3, "round": 2}),
        "gold": field({"gold": gold}, gold_status),
        "level": field({"level": 4}),
        "xp": field({"current": 0, "required": 20}),
        "hp": field({"hp": 100}),
        "shop": field({"slots": list(shop)}, shop_status),
        "tracker_version": "hud-state-tracker-test",
    }


def position(pos, occupied):
    return {
        "position": pos,
        "status": "occupied" if occupied else "empty",
        "confidence": 1.0,
        "foreground_score": 0.8 if occupied else 0.1,
        "raw_score": 0.8 if occupied else 0.1,
        "source_timestamp_s": 0.0,
        "source_evidence_id": "x",
        "pending_status": None,
        "pending_count": 0,
    }


def board(t, eid, count):
    occupied = {
        f"{i // 7},{i % 7}"
        for i in range(count)
    }
    cells = [
        position(f"{r},{c}", f"{r},{c}" in occupied)
        for r in range(4)
        for c in range(7)
    ]
    return {
        "match_id": "m",
        "timestamp_s": t,
        "evidence_id": eid,
        "usable": False,
        "stability": "unstable",
        "gate_reason": "planning_visual_unstable",
        "motion_count": 0,
        "candidate_change_count": 0,
        "uncertain_count": 0,
        "candidate_occupied_count": count,
        "occupied_count": count,
        "hud_level": 4,
        "hud_stage": "3-2",
        "round_age_s": 10.0,
        "capacity_status": "at",
        "strong_snapshot": False,
        "inferred_empty_count": 0,
        "scene_valid": True,
        "scene_score": 0.01,
        "scene_anchor_pass_count": 4,
        "cells": cells,
        "tracker_version": "board-test",
    }


def bench(t, eid, count):
    occupied = {str(i) for i in range(count)}
    slots = [
        position(str(i), str(i) in occupied)
        for i in range(9)
    ]
    return {
        "match_id": "m",
        "timestamp_s": t,
        "evidence_id": eid,
        "uncertain_count": 0,
        "occupied_count": count,
        "slots": slots,
        "tracker_version": "bench-test",
    }


def write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(x) for x in rows) + "\n",
        encoding="utf-8",
    )


def test_pipeline_aligns_streams_and_writes_actions(tmp_path):
    match = tmp_path / "match"
    tracking = match / "tracking"
    tracking.mkdir(parents=True)

    hud_path = tracking / "hud-state-tracker-0.10.0.jsonl"
    board_path = tracking / "board-occupancy-tracker-0.13.5.jsonl"
    bench_path = tracking / "bench-occupancy-tracker-0.13.5.jsonl"

    e0, e1, e2 = "e0", "e1", "e2"

    write_jsonl(
        hud_path,
        [
            hud(
                0.0, e0,
                gold=20,
                gold_status="observed",
                shop=("a", "b", "c", "d", "e"),
                shop_status="observed",
            ),
            hud(
                10.0, e1,
                gold=18,
                gold_status="observed",
                shop=("f", "g", "h", "i", "j"),
                shop_status="observed",
            ),
            hud(
                20.0, e2,
                gold=17,
                gold_status="observed",
                shop=(None, "g", "h", "i", "j"),
                shop_status="observed",
            ),
        ],
    )

    write_jsonl(
        board_path,
        [board(0.0, e0, 4), board(10.0, e1, 4), board(20.0, e2, 4)],
    )
    write_jsonl(
        bench_path,
        [bench(0.0, e0, 2), bench(10.0, e1, 2), bench(20.0, e2, 3)],
    )

    summary = infer_match_actions(
        match,
        ActionFusionSettings(),
        hud_states_path=hud_path,
        board_states_path=board_path,
        bench_states_path=bench_path,
    )

    assert summary["aligned_snapshot_count"] == 3
    assert summary["window_count"] == 2
    assert summary["action_type_counts"]["refresh_shop"] == 1
    assert summary["action_type_counts"]["buy_unit"] == 1

    actions_path = Path(summary["actions_path"])
    windows_path = Path(summary["windows_path"])
    ledger_path = Path(summary["ledger_path"])
    assert actions_path.exists()
    assert windows_path.exists()
    assert ledger_path.exists()
    assert summary["xp_progress"]["absolute_snapshot_count"] == 3
    ledger_summary = summary["economy_ledger"]
    assert "action_spend_min_total" in ledger_summary
    assert "action_spend_max_total" in ledger_summary
    assert "unallocated_spend_min_total" in ledger_summary
    assert "unallocated_spend_max_total" in ledger_summary
    assert "required_action_spend_min_total" in ledger_summary
    assert "compatible_action_spend_min_total" in ledger_summary
    assert "infeasible_spend_window_count" in ledger_summary
    assert "spend_deficit_min_total" in ledger_summary
    assert "buy_cost_validation_counts" in summary["game_data"]
    assert "required_unknown_window_count" in ledger_summary
    assert "uncertainty_only_window_count" in ledger_summary
