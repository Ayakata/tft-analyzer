from PIL import Image

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.ocr.models import OCRText
from tft_analyzer.perception.players.localizer import PlayerRowLocalizer
from tft_analyzer.perception.players.models import PlayerRowCandidate
from tft_analyzer.perception.players.recognizer import (
    PlayerListRecognizer,
    PlayerListRecognizerSettings,
)


class FakeOCR:
    name = "fake"

    def recognize_line(self, image):
        return OCRText("87", 0.99)


class DeterministicLocalizer(PlayerRowLocalizer):
    def panel_presence_score(self, panel):
        return 1.0

    def candidates(
        self,
        image,
        registry,
        *,
        ocr_engine=None,
        player_name=None,
    ):
        boxes = self.row_boxes(image, registry)
        return [
            PlayerRowCandidate(
                row_index=i,
                box=box,
                highlight_score=0.90 if i == 3 else 0.10,
                combined_self_score=0.90 if i == 3 else 0.10,
            )
            for i, box in enumerate(boxes)
        ]


def test_recognizer_emits_hp_observation():
    registry = ROIRegistry.from_yaml(
        "configs/layouts/tft_16_9_default.yaml"
    )
    recognizer = PlayerListRecognizer(
        registry=registry,
        ocr_engine=FakeOCR(),
        settings=PlayerListRecognizerSettings(),
        localizer=DeterministicLocalizer(row_count=8),
    )

    result = recognizer.recognize(
        Image.new("RGB", (1920, 1080), (30, 30, 30)),
        match_id="m1",
        timestamp_s=10.0,
        evidence_id="e1",
    )

    assert result.selected_row_index == 3
    assert len(result.observations) == 1

    obs = result.observations[0]
    assert obs.kind == ObservationKind.HP
    assert obs.value["hp"] == 87
    assert obs.value["row_index"] == 3
