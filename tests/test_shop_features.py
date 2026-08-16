import numpy as np
from PIL import Image

from tft_analyzer.perception.shop.features import (
    portrait_dhash,
    slot_occupancy_score,
)


def test_textured_portrait_scores_above_empty_slot():
    empty = Image.new("RGB", (120, 80), (7, 20, 20))

    arr = np.zeros((80, 120, 3), dtype=np.uint8)
    arr[:, :40] = (220, 80, 25)
    arr[:, 40:80] = (30, 170, 220)
    arr[:, 80:] = (180, 180, 40)
    arr[::4, :] = 245
    textured = Image.fromarray(arr)

    assert slot_occupancy_score(textured) > 0.30
    assert slot_occupancy_score(empty) < 0.30


def test_dhash_is_deterministic():
    image = Image.new("RGB", (64, 64), (30, 80, 120))
    assert portrait_dhash(image) == portrait_dhash(image)
    assert len(portrait_dhash(image)) == 16
