from PIL import Image, ImageDraw

from tft_analyzer.perception.hud.presence import HUDPresenceGate


def test_presence_gate_rejects_uniform_crop_with_low_score():
    gate = HUDPresenceGate()
    image = Image.new("RGB", (120, 40), (90, 120, 90))

    decision = gate.check("gold", image)

    assert not decision.present
    assert 0.0 <= decision.score < 1.0


def test_presence_gate_accepts_hud_like_crop_with_full_score():
    gate = HUDPresenceGate(
        min_dark_fraction=0.20,
        min_edge_density=0.005,
        min_bright_fraction=0.002,
    )

    image = Image.new("RGB", (120, 40), (15, 20, 22))
    draw = ImageDraw.Draw(image)
    draw.rectangle((45, 8, 52, 32), fill=(235, 235, 220))
    draw.rectangle((60, 8, 67, 32), fill=(235, 235, 220))

    decision = gate.check("gold", image)

    assert decision.present
    assert decision.score == 1.0


def test_weakest_required_feature_controls_presence_score():
    gate = HUDPresenceGate(
        min_dark_fraction=0.20,
        min_edge_density=0.005,
        min_bright_fraction=0.50,  # deliberately impossible-ish
    )

    image = Image.new("RGB", (120, 40), (15, 20, 22))
    draw = ImageDraw.Draw(image)
    draw.rectangle((45, 8, 52, 32), fill=(235, 235, 220))
    draw.rectangle((60, 8, 67, 32), fill=(235, 235, 220))

    decision = gate.check("gold", image)

    assert not decision.present
    assert decision.score < 1.0
    assert decision.reason == "hud_structure_missing"


def test_stage_absent_cannot_report_full_presence_score():
    gate = HUDPresenceGate(
        stage_min_edge_density=0.01,
        min_bright_fraction=0.50,
    )

    image = Image.new("RGB", (120, 40), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    draw.line((0, 20, 119, 20), fill=(255, 255, 255), width=2)

    decision = gate.check("stage", image)

    assert not decision.present
    assert decision.score < 1.0
