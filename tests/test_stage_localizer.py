from PIL import Image

from tft_analyzer.perception.hud.stage_localizer import StageLocalizer
from tft_analyzer.perception.layout import ROIRegistry


def test_stage_localizer_generates_shifted_candidates():
    registry = ROIRegistry.from_yaml(
        "configs/layouts/tft_16_9_default.yaml"
    )
    image = Image.new("RGB", (1920, 1080), "black")
    localizer = StageLocalizer(
        x_offsets_px_at_1920=(-20, 0, 20),
    )
    candidates = localizer.candidates(image, registry)

    assert len(candidates) == 3
    assert len({c.box for c in candidates}) == 3

    region = registry.resolve("stage_search_region", 1920, 1080)
    for c in candidates:
        l, t, r, b = c.box
        assert region.left <= l < r <= region.right
        assert region.top <= t < b <= region.bottom
