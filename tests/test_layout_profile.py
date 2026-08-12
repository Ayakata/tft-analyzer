from pathlib import Path

import pytest
from PIL import Image

from tft_analyzer.perception.layout import (
    LayoutMismatchError,
    ROIRegistry,
    build_roi_debug,
)


PROFILE = Path("configs/layouts/tft_16_9_default.yaml")


def test_16_9_profile_loads_and_matches_reference():
    registry = ROIRegistry.from_yaml(PROFILE)
    assert registry.profile.profile_id == "tft_16_9_default_v4"
    assert registry.profile.matches(1920, 1080)
    assert registry.profile.matches(1600, 900)
    assert "gold_value" in registry.names()
    assert "gold_number" in registry.names()
    assert "stage_text" in registry.names()
    assert "stage_search_region" in registry.names()
    assert "level_text" in registry.names()
    assert "xp_text" in registry.names()
    assert "shop_4_portrait" in registry.names()
    assert "players_panel" in registry.names()
    assert "player_hp" not in registry.names()


def test_reference_pixel_resolution_is_stable():
    registry = ROIRegistry.from_yaml(PROFILE)

    gold = registry.resolve("gold_value", 1920, 1080)
    assert gold.box == (949, 870, 1019, 914)

    shop0 = registry.resolve("shop_0_card", 1920, 1080)
    assert shop0.box == (480, 929, 674, 1079)


def test_normalized_roi_scales_to_1600x900():
    registry = ROIRegistry.from_yaml(PROFILE)
    shop0 = registry.resolve("shop_0_card", 1600, 900)
    assert shop0.left == 400
    assert shop0.top == 774
    assert shop0.width in {161, 162}
    assert shop0.height == 125


def test_wrong_aspect_ratio_is_rejected():
    registry = ROIRegistry.from_yaml(PROFILE)
    with pytest.raises(LayoutMismatchError):
        registry.resolve("gold_value", 1600, 1200)


def test_roi_debug_writes_overlay_crops_and_manifest(tmp_path):
    image_path = tmp_path / "frame.png"
    Image.new("RGB", (1920, 1080), (20, 30, 40)).save(image_path)

    registry = ROIRegistry.from_yaml(PROFILE)
    result = build_roi_debug(
        image_path,
        registry,
        tmp_path / "debug",
        selected_names=["stage_value", "gold_value", "shop_0_card"],
    )

    assert result["roi_count"] == 3
    assert Path(result["overlay"]).exists()
    assert Path(result["manifest"]).exists()
    assert (Path(result["crops_dir"]) / "gold_value.png").exists()


def test_players_panel_covers_dynamic_player_list():
    registry = ROIRegistry.from_yaml(PROFILE)
    panel = registry.resolve("players_panel", 1920, 1080)
    assert panel.left == 1670
    assert panel.top == 167
    assert panel.right == 1920
    assert panel.bottom == 805


def test_tight_hud_ocr_rois_exclude_decorative_borders():
    registry = ROIRegistry.from_yaml(PROFILE)

    assert registry.resolve("stage_text", 1920, 1080).box == (770, 7, 810, 31)
    assert registry.resolve("level_text", 1920, 1080).box == (274, 880, 336, 904)
    assert registry.resolve("xp_text", 1920, 1080).box == (410, 884, 450, 906)
    assert registry.resolve("gold_number", 1920, 1080).box == (962, 884, 1006, 906)

    # Tight OCR areas must be strictly smaller than their context ROIs.
    for tight, context in (
        ("stage_text", "stage_value"),
        ("level_text", "level_value"),
        ("xp_text", "xp_value"),
        ("gold_number", "gold_value"),
    ):
        a = registry.resolve(tight, 1920, 1080)
        b = registry.resolve(context, 1920, 1080)
        assert a.width < b.width
        assert a.height < b.height


def test_stage_search_region_covers_early_and_later_positions():
    registry = ROIRegistry.from_yaml(PROFILE)
    region = registry.resolve("stage_search_region", 1920, 1080)
    assert region.width >= 100
    assert region.left <= 750
    assert region.right >= 850
