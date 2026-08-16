from .debug import build_board_debug
from .features import classify_occupancy, occupancy_features, occupancy_score, region_presence_score
from .geometry import NormalizedPoint, bench_centers, board_centers, centered_box
from .models import BoardBenchRecognitionResult, BoardCellResult, BenchSlotResult, OccupancyFeatures
from .pipeline import process_match_board_bench
from .recognizer import BoardBenchRecognizer, BoardBenchRecognizerSettings

__all__ = [
    "BoardBenchRecognizer", "BoardBenchRecognizerSettings", "BoardBenchRecognitionResult",
    "BoardCellResult", "BenchSlotResult", "OccupancyFeatures", "NormalizedPoint",
    "board_centers", "bench_centers", "centered_box", "region_presence_score",
    "occupancy_features", "occupancy_score", "classify_occupancy", "build_board_debug",
    "process_match_board_bench",
]
