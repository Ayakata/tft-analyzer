import json
from pathlib import Path

from PIL import Image

from tft_analyzer.tracking.board.qa import (
    QA_VERSION,
    export_board_formation_qa,
    find_latest_board_states,
)


def _cell(status):
    return {
        "position": "0,0",
        "status": status,
        "confidence": 1.0,
        "foreground_score": 0.8 if status == "occupied" else 0.1,
        "raw_score": 0.8 if status == "occupied" else 0.1,
        "source_timestamp_s": 10.0,
        "source_evidence_id": "frame-e1",
        "pending_status": None,
        "pending_count": 0,
    }


def test_board_qa_exports_selected_frames_and_gallery(tmp_path):
    match = tmp_path / "match"
    frames = match / "evidence" / "frames"
    tracking = match / "tracking"
    frames.mkdir(parents=True)
    tracking.mkdir(parents=True)

    image_path = frames / "frame.png"
    Image.new("RGB", (640, 360), (90, 110, 80)).save(image_path)

    evidence = {
        "sequence": 42,
        "reason": "scene_change",
        "scene_change_score": 0.5,
        "wall_time_iso": None,
        "width": 640,
        "height": 360,
        "evidence": {
            "evidence_id": "frame-e1",
            "match_id": "m",
            "timestamp_s": 10.0,
            "kind": "frame",
            "uri": "evidence/frames/frame.png",
            "sha256": None,
            "source": "screen",
        },
    }
    (match / "evidence" / "evidence_index.jsonl").write_text(
        json.dumps(evidence) + "\n",
        encoding="utf-8",
    )

    cells = []
    for i in range(28):
        cell = _cell("occupied" if i < 4 else "empty")
        cell["position"] = f"{i // 7},{i % 7}"
        cells.append(cell)

    state = {
        "match_id": "m",
        "timestamp_s": 10.0,
        "evidence_id": "frame-e1",
        "usable": True,
        "stability": "stable",
        "gate_reason": "full_level_snapshot",
        "motion_count": 1,
        "candidate_change_count": 4,
        "uncertain_count": 3,
        "candidate_occupied_count": 4,
        "occupied_count": 4,
        "hud_level": 4,
        "hud_stage": "3-2",
        "round_age_s": 12.5,
        "capacity_status": "at",
        "strong_snapshot": True,
        "inferred_empty_count": 2,
        "cells": cells,
        "tracker_version": "board-bench-occupancy-tracker-0.13.5",
    }
    board_path = tracking / "board-occupancy-tracker-0.13.5.jsonl"
    board_path.write_text(
        json.dumps(state) + "\n",
        encoding="utf-8",
    )

    result = export_board_formation_qa(
        match,
        kinds=("full-cap", "plan-ok", "scene-invalid"),
    )

    assert result["qa_version"] == QA_VERSION
    assert result["exported_count"] == 1
    assert result["kind_counts"]["full-cap"] == 1
    assert result["kind_counts"]["plan-ok"] == 0
    assert result["kind_counts"]["scene-invalid"] == 0
    assert Path(result["manifest_path"]).exists()
    assert Path(result["gallery_path"]).exists()

    manifest = json.loads(
        Path(result["manifest_path"]).read_text(encoding="utf-8")
    )
    assert manifest["items"][0]["stage"] == "3-2"
    assert manifest["items"][0]["level"] == 4
    assert manifest["items"][0]["canonical_occupied_count"] == 4
    assert Path(manifest["items"][0]["image_path"]).exists()


def test_latest_board_states_prefers_highest_version(tmp_path):
    tracking = tmp_path / "tracking"
    tracking.mkdir()
    older = tracking / "board-occupancy-tracker-0.13.1.jsonl"
    newer = tracking / "board-occupancy-tracker-0.13.5.jsonl"
    older.write_text("", encoding="utf-8")
    newer.write_text("", encoding="utf-8")
    assert find_latest_board_states(tmp_path) == newer
