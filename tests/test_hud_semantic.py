from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.tracking.hud.semantic import canonical_hud_value


def test_canonical_level_strips_ocr_metadata():
    value = {
        "level": 5,
        "raw_text": "Lvl.5",
        "normalized_text": "5",
        "ocr_engine": "rapidocr",
        "ocr_variant": "gray_tight",
        "presence_score": 1.0,
    }
    assert canonical_hud_value(ObservationKind.LEVEL, value) == {"level": 5}


def test_canonical_stage_keeps_only_game_semantics():
    value = {
        "stage": 3,
        "round": 4,
        "raw_text": "3-4",
        "ocr_candidate": "stage_candidate_1",
        "ocr_candidate_box": [760, 6, 816, 34],
    }
    assert canonical_hud_value(ObservationKind.STAGE, value) == {
        "stage": 3,
        "round": 4,
    }
