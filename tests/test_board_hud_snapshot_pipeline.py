import json
from pathlib import Path

from tft_analyzer.tracking.board.pipeline import (
    BoardOccupancyTrackerSettings,
    track_match_board_occupancy,
)


FEATURES_EMPTY = {
    "contrast": 5.0,
    "edge_density": 0.0,
    "saturation": 0.08,
    "bright_fraction": 0.0,
    "center_edge_delta": 0.0,
    "center_saturation_delta": 0.0,
}
FEATURES_OCC = {
    "contrast": 50.0,
    "edge_density": 0.18,
    "saturation": 0.35,
    "bright_fraction": 0.20,
    "center_edge_delta": 0.08,
    "center_saturation_delta": 0.10,
}


def _cell(row, col, occupied):
    return {
        "row": row,
        "col": col,
        "score": 0.85 if occupied else 0.10,
        "features": (FEATURES_OCC if occupied else FEATURES_EMPTY).copy(),
    }


def _slot(i):
    return {
        "slot_index": i,
        "score": 0.10,
        "features": FEATURES_EMPTY.copy(),
    }


def _frame(ts, evidence_id, occupied_positions):
    occ = set(occupied_positions)
    return {
        "timestamp_s": ts,
        "evidence_id": evidence_id,
        "match_id": "m",
        "sampling_mode": "footprint",
        "board_cells": [
            _cell(r, c, (r, c) in occ)
            for r in range(4)
            for c in range(7)
        ],
        "bench_slots": [_slot(i) for i in range(9)],
    }


def _field(value, status="observed"):
    return {
        "value": value,
        "confidence": 1.0 if value is not None else 0.0,
        "source_observation_id": None,
        "source_evidence_id": None,
        "source_timestamp_s": None,
        "age_s": 0.0 if value is not None else None,
        "status": status,
    }


def _hud(ts, evidence_id, stage, level):
    return {
        "state_id": f"hud-{evidence_id}",
        "match_id": "m",
        "timestamp_s": ts,
        "evidence_id": evidence_id,
        "stage": _field({"stage": stage[0], "round": stage[1]}),
        "gold": _field(None, "unknown"),
        "level": _field({"level": level}),
        "xp": _field(None, "unknown"),
        "hp": _field(None, "unknown"),
        "shop": _field(None, "unknown"),
        "tracker_version": "hud-state-tracker-test",
    }


def test_full_level_snapshot_is_atomic_and_over_cap_rejected(tmp_path):
    match = tmp_path / "match"
    obs = match / "observations"
    tracking = match / "tracking"
    obs.mkdir(parents=True)
    tracking.mkdir(parents=True)

    frames = []
    hud = []

    # Background calibration.
    for i in range(12):
        frames.append(_frame(float(i), f"e{i}", []))
        hud.append(_hud(float(i), f"e{i}", (2, 1), 4))

    # New stage transition.
    frames.append(_frame(20.0, "round-start", []))
    hud.append(_hud(20.0, "round-start", (2, 2), 4))

    full = {(0, 0), (0, 1), (1, 0), (1, 1)}
    frames.append(_frame(30.0, "full", full))
    hud.append(_hud(30.0, "full", (2, 2), 4))

    over = set(full)
    over.add((2, 2))
    frames.append(_frame(31.0, "over", over))
    hud.append(_hud(31.0, "over", (2, 2), 4))

    attempts = obs / "board-bench-occupancy-0.12.0_attempts.jsonl"
    attempts.write_text(
        "\n".join(json.dumps(x) for x in frames) + "\n",
        encoding="utf-8",
    )
    hud_path = tracking / "hud-state-tracker-0.10.0.jsonl"
    hud_path.write_text(
        "\n".join(json.dumps(x) for x in hud) + "\n",
        encoding="utf-8",
    )

    summary = track_match_board_occupancy(
        match,
        BoardOccupancyTrackerSettings(
            use_arena_scene_guard=False,
        ),
        attempts_path=attempts,
        hud_states_path=hud_path,
    )

    states = [
        json.loads(line)
        for line in Path(summary["board_states_path"]).read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    full_state = next(x for x in states if x["evidence_id"] == "full")
    assert full_state["strong_snapshot"] is True
    assert full_state["gate_reason"] == "full_level_snapshot"
    assert full_state["hud_level"] == 4
    assert full_state["candidate_occupied_count"] == 4
    assert full_state["occupied_count"] == 4

    over_state = next(x for x in states if x["evidence_id"] == "over")
    assert over_state["usable"] is False
    assert over_state["gate_reason"] == "level_capacity_exceeded"
    assert over_state["candidate_occupied_count"] == 5
    assert over_state["occupied_count"] == 4

    assert summary["board_gate"]["tracked_over_level_frames"] == 0
