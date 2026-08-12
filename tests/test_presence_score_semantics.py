from tft_analyzer.perception.hud.presence import HUDPresenceGate


def test_criterion_score_is_clamped_and_monotonic():
    score = HUDPresenceGate._criterion_score

    assert score(0.0, 0.5) == 0.0
    assert score(0.25, 0.5) == 0.5
    assert score(0.5, 0.5) == 1.0
    assert score(2.0, 0.5) == 1.0
