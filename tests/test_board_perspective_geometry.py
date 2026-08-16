from pathlib import Path

from PIL import Image

from tft_analyzer.perception.board import (
    BoardBenchRecognizer,
    BoardBenchRecognizerSettings,
)
from tft_analyzer.perception.layout import ROIRegistry


def make_registry(tmp_path: Path) -> ROIRegistry:
    layout = tmp_path / "layout.yaml"
    layout.write_text(
        "schema_version: 1\n"
        "profile_id: test\n"
        "aspect_ratio: 1.7777777778\n"
        "aspect_ratio_tolerance: 0.03\n"
        "reference_width: 1920\n"
        "reference_height: 1080\n"
        "rois:\n"
        "  board_region: {x: 0.2, y: 0.2, w: 0.6, h: 0.5}\n"
        "  bench_region: {x: 0.2, y: 0.72, w: 0.6, h: 0.15}\n",
        encoding="utf-8",
    )
    return ROIRegistry.from_yaml(layout)


def test_board_crop_width_grows_with_perspective(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(
            min_board_presence_score=0.0,
            min_bench_presence_score=0.0,
        ),
    )

    geoms = [
        recognizer.board_box_geometry_at_reference(row)
        for row in range(4)
    ]

    assert geoms == [
        (50, 68, 26),
        (56, 72, 28),
        (62, 78, 30),
        (68, 84, 32),
    ]
    assert [g[0] for g in geoms] == sorted(g[0] for g in geoms)


def test_real_reference_boxes_follow_row_specific_sizes(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(
            min_board_presence_score=0.0,
            min_bench_presence_score=0.0,
        ),
    )
    image = Image.new("RGB", (1920, 1080), (80, 100, 120))

    result = recognizer.recognize(
        image,
        match_id="m",
        timestamp_s=1.0,
        evidence_id="e",
    )

    first_by_row = {
        row: next(c for c in result.board_cells if c.row == row and c.col == 0)
        for row in range(4)
    }

    widths = [
        first_by_row[row].box[2] - first_by_row[row].box[0]
        for row in range(4)
    ]
    heights = [
        first_by_row[row].box[3] - first_by_row[row].box[1]
        for row in range(4)
    ]

    assert widths == [100, 112, 124, 136]
    assert heights == [94, 100, 108, 116]


def test_custom_short_row_geometry_falls_back_to_scalar(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(
            board_half_width_px_at_1920=60,
            board_up_px_at_1080=70,
            board_down_px_at_1080=30,
            board_half_width_px_at_1920_by_row=(48,),
            board_up_px_at_1080_by_row=(64,),
            board_down_px_at_1080_by_row=(24,),
        ),
    )

    assert recognizer.board_box_geometry_at_reference(0) == (48, 64, 24)
    assert recognizer.board_box_geometry_at_reference(3) == (60, 70, 30)



def test_bench_geometry_shifts_left_and_uses_separate_context_and_footprint(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(
            min_board_presence_score=0.0,
            min_bench_presence_score=0.0,
        ),
    )

    centers = recognizer._bench_geometry(1920, 1080)
    assert centers[0] == (0, 442, 805)
    assert centers[-1] == (8, 1373, 805)

    context = recognizer.bench_context_box((442, 805), 1920, 1080)
    footprint = recognizer.bench_footprint_box((442, 805), 1920, 1080)

    assert context == (382, 663, 502, 817)
    assert footprint == (406, 741, 478, 821)
    assert (context[2] - context[0]) > (footprint[2] - footprint[0])
    assert (context[3] - context[1]) > (footprint[3] - footprint[1])



def test_bench_0113_changes_vertical_anchor_without_horizontal_drift(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(),
    )

    centers = recognizer._bench_geometry(1920, 1080)

    assert [centers[0][1], centers[-1][1]] == [442, 1373]
    assert {center[2] for center in centers} == {805}
