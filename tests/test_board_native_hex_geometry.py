from pathlib import Path

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


def test_native_grid_is_staggered_and_perspective_calibrated(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(),
    )
    centers = recognizer._board_geometry(1920, 1080)
    rows = {
        row: [(x, y) for r, c, x, y in centers if r == row]
        for row in range(4)
    }

    assert rows[0][0] == (563, 447)
    assert rows[0][-1] == (1250, 447)
    assert rows[1][0] == (612, 516)
    assert rows[1][-1] == (1321, 516)
    assert rows[2][0] == (534, 593)
    assert rows[2][-1] == (1273, 593)
    assert rows[3][0] == (584, 675)
    assert rows[3][-1] == (1346, 675)

    # Alternating native row offset is preserved instead of monotonic drift.
    assert rows[0][0][0] < rows[1][0][0]
    assert rows[2][0][0] < rows[3][0][0]


def test_hex_polygon_is_six_point_slot_footprint(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(),
    )
    points = recognizer.board_hex_polygon(2, (960, 517), 1920, 1080)

    assert len(points) == 6
    assert points[0][1] == points[1][1]
    assert points[2] == (1018, 517)
    assert points[5] == (902, 517)


def test_hex_footprint_grows_toward_camera(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(),
    )
    sizes = [recognizer.board_hex_geometry_at_reference(row) for row in range(4)]
    assert sizes == [(52, 38), (55, 41), (58, 45), (61, 48)]
