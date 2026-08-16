import numpy as np
from PIL import Image

from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.players.localizer import (
    PlayerRowLocalizer,
    normalize_player_name,
)


def test_normalize_player_name():
    assert normalize_player_name("My Name#EUW") == "mynameeuw"


def test_row_boxes_are_eight_ordered_slots():
    registry = ROIRegistry.from_yaml(
        "configs/layouts/tft_16_9_default.yaml"
    )
    image = Image.new("RGB", (1920, 1080))

    localizer = PlayerRowLocalizer(row_count=8)
    boxes = localizer.row_boxes(image, registry)

    assert len(boxes) == 8
    assert all(a[1] < a[3] for a in boxes)
    assert [box[1] for box in boxes] == sorted(
        box[1] for box in boxes
    )


def test_gold_highlight_scores_above_neutral_row():
    localizer = PlayerRowLocalizer()

    neutral = Image.new("RGB", (220, 60), (35, 40, 45))

    arr = np.zeros((60, 220, 3), dtype=np.uint8)
    arr[:] = (35, 40, 45)
    arr[2:6, 10:210] = (240, 190, 40)
    arr[54:58, 10:210] = (240, 190, 40)
    highlighted = Image.fromarray(arr)

    assert (
        localizer.highlight_score(highlighted)
        > localizer.highlight_score(neutral)
    )



def test_name_ocr_cues_distinguish_nickname_from_numeric_own_row():
    localizer = PlayerRowLocalizer()

    name_presence, no_name = localizer._name_ocr_cues("KQs 92", 0.95)
    assert name_presence == 0.95
    assert no_name == 0.0

    name_presence, no_name = localizer._name_ocr_cues("93", 0.99)
    assert name_presence == 0.0
    assert no_name == 0.99

    name_presence, no_name = localizer._name_ocr_cues("", 0.0)
    assert name_presence == 0.0
    assert no_name == 0.0
