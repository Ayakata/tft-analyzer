from tft_analyzer.tracking.hud.constraints import (
    check_level,
    check_stage,
    check_xp,
)


def test_stage_regression_is_rejected():
    result = check_stage(
        {"stage": 3, "round": 2},
        {"stage": 2, "round": 7},
        reject_regression=True,
        max_jump_without_confirmation=12,
    )
    assert not result.valid
    assert result.reason == "stage_regression"


def test_large_stage_jump_is_suspicious():
    result = check_stage(
        {"stage": 2, "round": 1},
        {"stage": 7, "round": 5},
        reject_regression=True,
        max_jump_without_confirmation=12,
    )
    assert result.valid
    assert result.suspicious


def test_level_regression_is_rejected():
    result = check_level(
        {"level": 5},
        {"level": 4},
        reject_regression=True,
        max_jump_without_confirmation=2,
    )
    assert not result.valid
    assert result.reason == "level_regression"


def test_xp_can_reset_when_requirement_changes():
    result = check_xp(
        {"current": 5, "required": 6},
        {"current": 0, "required": 10},
        reject_regression_same_requirement=True,
    )
    assert result.valid
    assert result.reason == "xp_requirement_changed"


def test_xp_regression_same_requirement_is_rejected():
    result = check_xp(
        {"current": 4, "required": 10},
        {"current": 2, "required": 10},
        reject_regression_same_requirement=True,
    )
    assert not result.valid
