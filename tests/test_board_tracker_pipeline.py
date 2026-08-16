import json
from pathlib import Path

from tft_analyzer.tracking.board.pipeline import (
    BoardOccupancyTrackerSettings,
    track_match_board_occupancy,
)


FEATURES = {
    "contrast": 8.0,
    "edge_density": 0.002,
    "saturation": 0.10,
    "bright_fraction": 0.0,
    "center_edge_delta": 0.0,
    "center_saturation_delta": 0.0,
}


def item(score, *, row=None, col=None, slot=None, occupied=False):
    f = dict(FEATURES)
    if occupied:
        f.update(contrast=45.0, edge_density=.16, saturation=.28, bright_fraction=.2)
    value = {"score": score, "features": f}
    if slot is not None:
        value["slot_index"] = slot
    else:
        value["row"] = row
        value["col"] = col
    return value


def test_pipeline_builds_37_background_models_and_outputs_tracking(tmp_path):
    match = tmp_path / "match"
    obs = match / "observations"
    obs.mkdir(parents=True)
    attempts = obs / "board-bench-occupancy-0.12.0_attempts.jsonl"

    rows=[]
    for frame in range(16):
        occupied = frame >= 12
        rows.append({
            "sequence": frame,
            "timestamp_s": float(frame),
            "evidence_id": f"e{frame}",
            "sampling_mode": "footprint",
            "board_cells": [
                item(.75 if occupied and r == 0 and c == 0 else .15, row=r, col=c, occupied=occupied and r == 0 and c == 0)
                for r in range(4) for c in range(7)
            ],
            "bench_slots": [
                item(.75 if occupied and i == 0 else .15, slot=i, occupied=occupied and i == 0)
                for i in range(9)
            ],
        })
    attempts.write_text("\n".join(json.dumps(x) for x in rows)+"\n",encoding="utf-8")

    summary = track_match_board_occupancy(
        match,
        BoardOccupancyTrackerSettings(
            background_min_candidates=3,
            board_stable_frames_required=1,
            board_max_motion_cells=28,
            board_max_candidate_changes=28,
            use_arena_scene_guard=False,
        ),
        attempts_path=attempts,
    )

    assert summary["background_model_counts"] == {"board": 28, "bench": 9}
    assert summary["bench_scene_guard"] == {
        "blocked_frames": 0,
        "blocked_positions": 0,
    }
    assert Path(summary["background_path"]).exists()
    assert Path(summary["board_states_path"]).exists()
    assert Path(summary["bench_states_path"]).exists()
    assert summary["accepted_semantic_changes"]["bench"] >= 1
