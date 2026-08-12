from tft_analyzer.capture.clock import elapsed_seconds


def test_elapsed_seconds_normal_case():
    assert elapsed_seconds(100.25, 100.0) == 0.25


def test_elapsed_seconds_never_negative():
    # Regression: the first asynchronous WGC frame used to precede session_start.
    assert elapsed_seconds(99.859, 100.0) == 0.0
