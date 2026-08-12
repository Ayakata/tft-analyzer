from PIL import Image

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.perception.hud.presence import (
    PresenceDecision,
    PresenceFeatures,
)
from tft_analyzer.perception.hud.recognizer import HUDRecognizer
from tft_analyzer.perception.hud.stage_localizer import StageCandidate
from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.ocr.models import OCRText


class AlwaysPresentGate:
    def check(self, field, image):
        return PresenceDecision(
            present=True,
            score=1.0,
            features=PresenceFeatures(1.0, 1.0, 1.0),
            reason="test",
        )


class FakeStageLocalizer:
    def candidates(self, image, registry):
        return [
            StageCandidate(
                "left",
                (0, 0, 30, 20),
                Image.new("RGB", (30, 20), "black"),
                -10,
            ),
            StageCandidate(
                "right",
                (30, 0, 60, 20),
                Image.new("RGB", (30, 20), "black"),
                10,
            ),
        ]


class SequenceOCR:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def recognize_line(self, image):
        self.calls += 1
        # Candidate 1: three invalid preprocessing variants.
        if self.calls <= 3:
            return OCRText("garbage", 0.95)
        # Candidate 2: stage succeeds on first variant.
        if self.calls == 4:
            return OCRText("1-2", 0.99)
        # Fixed fields are intentionally invalid.
        return OCRText("", 0.0)


def test_stage_localization_selects_valid_shifted_candidate():
    registry = ROIRegistry.from_yaml(
        "configs/layouts/tft_16_9_default.yaml"
    )
    recognizer = HUDRecognizer(
        registry=registry,
        ocr_engine=SequenceOCR(),
        presence_gate=AlwaysPresentGate(),
        stage_localizer=FakeStageLocalizer(),
        min_observation_confidence=0.45,
    )

    result = recognizer.recognize(
        Image.new("RGB", (1920, 1080), "black"),
        match_id="m1",
        timestamp_s=1.0,
        evidence_id="e1",
    )

    stage = next(
        o for o in result.observations
        if o.kind == ObservationKind.STAGE
    )
    assert stage.value["stage"] == 1
    assert stage.value["round"] == 2
    assert stage.value["ocr_candidate"] == "right"


class RejectGoldGate(AlwaysPresentGate):
    def check(self, field, image):
        if field == "gold":
            return PresenceDecision(
                False,
                0.0,
                PresenceFeatures(0.0, 0.0, 0.0),
                "missing",
            )
        return super().check(field, image)


class GoldOCR:
    name = "fake"

    def recognize_line(self, image):
        return OCRText("7", 0.99)


def test_presence_gate_blocks_gold_observation():
    registry = ROIRegistry.from_yaml(
        "configs/layouts/tft_16_9_default.yaml"
    )
    recognizer = HUDRecognizer(
        registry=registry,
        ocr_engine=GoldOCR(),
        presence_gate=RejectGoldGate(),
        stage_localizer=FakeStageLocalizer(),
    )

    result = recognizer.recognize(
        Image.new("RGB", (1920, 1080), "black"),
        match_id="m1",
        timestamp_s=1.0,
        evidence_id="e1",
    )

    assert not any(
        o.kind == ObservationKind.GOLD
        for o in result.observations
    )
