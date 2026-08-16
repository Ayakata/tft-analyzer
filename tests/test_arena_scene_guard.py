from pathlib import Path

from PIL import Image, ImageDraw

from tft_analyzer.tracking.board.scene_guard import (
    ArenaSceneGuardSettings,
    fit_arena_scene_guard,
)


def _arena(path: Path, *, lower_overlay: bool = False):
    image = Image.new("RGB", (640, 360), (85, 120, 70))
    draw = ImageDraw.Draw(image)

    # Fixed arena-like structure in the four guard anchors.
    draw.rectangle((154, 36, 218, 79), fill=(115, 145, 100))
    draw.rectangle((422, 36, 486, 79), fill=(100, 135, 95))
    draw.rectangle((128, 101, 173, 209), fill=(85, 90, 70))
    draw.rectangle((467, 101, 512, 209), fill=(95, 100, 75))

    # Variable board centre content must not matter.
    draw.ellipse((250, 120, 390, 260), fill=(160, 80, 120))

    if lower_overlay:
        draw.rectangle((80, 255, 560, 359), fill=(25, 30, 45))

    image.save(path)


def _special_scene(path: Path):
    image = Image.new("RGB", (640, 360), (20, 18, 50))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 639, 359), fill=(28, 20, 65))
    draw.ellipse((180, 30, 460, 330), fill=(80, 55, 130))
    image.save(path)


def test_match_local_guard_rejects_full_screen_scene_but_keeps_lower_overlay(tmp_path):
    paths = []

    for i in range(8):
        path = tmp_path / f"arena_{i}.png"
        _arena(path, lower_overlay=(i == 7))
        paths.append((f"a{i}", path))

    for i in range(2):
        path = tmp_path / f"special_{i}.png"
        _special_scene(path)
        paths.append((f"s{i}", path))

    model, results = fit_arena_scene_guard(
        paths,
        settings=ArenaSceneGuardSettings(
            descriptor_size=32,
            reference_fraction=0.60,
            score_threshold=0.12,
            anchor_threshold=0.15,
            min_anchor_pass=3,
        ),
    )

    assert model.reference_frame_count == 6
    assert all(results[f"a{i}"].valid for i in range(8))
    assert results["a7"].valid is True
    assert results["s0"].valid is False
    assert results["s1"].valid is False


def test_scene_guard_requires_three_anchor_matches(tmp_path):
    paths = []
    for i in range(5):
        path = tmp_path / f"arena_{i}.png"
        _arena(path)
        paths.append((f"a{i}", path))

    model, results = fit_arena_scene_guard(paths)
    assert all(x.valid for x in results.values())
    assert model.settings.min_anchor_pass == 3
