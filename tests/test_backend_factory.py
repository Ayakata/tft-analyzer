import importlib.util

import pytest

from tft_analyzer.capture.backends.factory import create_capture_backend


def test_backend_factory_constructs_wgc_without_starting_platform_capture():
    wgc = create_capture_backend(
        "wgc",
        target_fps=4,
        first_frame_timeout_seconds=4,
        cursor_capture=False,
        draw_border=False,
    )
    assert wgc.name == "wgc"


def test_backend_factory_constructs_mss_when_dependency_available():
    if importlib.util.find_spec("mss") is None:
        pytest.skip("mss is not installed in the artifact test environment")

    mss = create_capture_backend(
        "mss",
        target_fps=4,
        first_frame_timeout_seconds=4,
        cursor_capture=False,
        draw_border=False,
    )
    assert mss.name == "mss"


def test_backend_factory_rejects_unknown_backend():
    with pytest.raises(ValueError):
        create_capture_backend(
            "magic",
            target_fps=4,
            first_frame_timeout_seconds=4,
            cursor_capture=False,
            draw_border=False,
        )
