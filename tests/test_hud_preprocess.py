from PIL import Image

from tft_analyzer.perception.hud.preprocess import build_variants


def test_tight_preprocess_builds_three_distinct_variants():
    image = Image.new("RGB", (40, 22), (15, 20, 25))
    variants = build_variants(
        image,
        primary_upscale=4,
        fallback_upscale=5,
        binary_threshold=150,
    )

    assert [v.name for v in variants] == [
        "rgb_tight",
        "gray_tight",
        "binary_tight",
    ]
    assert all(v.image.width > image.width for v in variants)
    assert all(v.image.height > image.height for v in variants)
