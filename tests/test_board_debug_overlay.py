from pathlib import Path
import json

from PIL import Image

from tft_analyzer.perception.board import (
    BoardBenchRecognizer,
    BoardBenchRecognizerSettings,
    build_board_debug,
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


def test_debug_payload_contains_footprint_boxes(tmp_path):
    recognizer = BoardBenchRecognizer(
        registry=make_registry(tmp_path),
        settings=BoardBenchRecognizerSettings(
            min_board_presence_score=0.0,
            min_bench_presence_score=0.0,
        ),
    )
    image = Image.new("RGB", (1920, 1080), (80, 100, 120))
    image_path = tmp_path / "frame.png"
    image.save(image_path)

    debug = build_board_debug(image_path, tmp_path / "out", recognizer)
    payload_path = Path(debug["result_path"])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    assert payload["board_cells"][0]["hex_points"]
    assert payload["bench_slots"][0]["footprint_box"]
    assert payload["geometry"]["bench"]["footprint_half_width_px_at_1920"] == 36
