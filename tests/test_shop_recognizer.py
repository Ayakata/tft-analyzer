import numpy as np
from PIL import Image

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.ocr.models import OCRText
from tft_analyzer.perception.shop.identity import (
    ShopIdentityLexicon,
    ShopIdentityResolver,
)
from tft_analyzer.perception.shop.recognizer import (
    ShopRecognizer,
    ShopRecognizerSettings,
)


class FakeOCR:
    name = "fake"

    def __init__(self):
        self.values = iter(["Pantheon", "Samira", "Ezreal", "Pyke"])

    def recognize_line(self, image):
        return OCRText(next(self.values), 0.99)


def test_shop_recognizer_emits_resolved_slots_for_synthetic_frame():
    registry = ROIRegistry.from_yaml(
        "configs/layouts/tft_16_9_default.yaml"
    )
    image = Image.new("RGB", (1920, 1080), (8, 15, 15))
    arr = np.asarray(image).copy()

    for i in range(1, 5):
        roi = registry.resolve(f"shop_{i}_portrait", 1920, 1080)
        l, t, r, b = roi.box
        arr[t:b, l:r, 0] = 210
        arr[t:b, l:r, 1] = (40 + i * 30)
        arr[t:b, l:r, 2] = 25
        arr[t:b:4, l:r] = 245

    shop = registry.resolve("shop_region", 1920, 1080)
    l, t, r, b = shop.box
    arr[t:t+2, l:r] = 180
    image = Image.fromarray(arr)

    recognizer = ShopRecognizer(
        registry=registry,
        ocr_engine=FakeOCR(),
        settings=ShopRecognizerSettings(
            min_shop_presence_score=0.05,
            min_observation_confidence=0.40,
        ),
        identity_resolver=ShopIdentityResolver(
            ShopIdentityLexicon(
                ["pantheon", "samira", "ezreal", "pyke"]
            )
        ),
    )

    result = recognizer.recognize(
        image,
        match_id="m1",
        timestamp_s=1.0,
        evidence_id="e1",
    )

    assert result.shop_present
    assert result.occupied_count == 4
    assert len(result.observations) == 1

    obs = result.observations[0]
    assert obs.kind == ObservationKind.SHOP
    assert [
        s["resolved_name"] if s["occupied"] else None
        for s in obs.value["slots"]
    ] == [None, "pantheon", "samira", "ezreal", "pyke"]
    assert all(
        s["identity_method"] == "exact_lexicon"
        for s in obs.value["slots"] if s["occupied"]
    )
