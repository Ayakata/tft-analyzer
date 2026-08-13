from tft_analyzer.core.models import PlayerState


def test_player_state_can_store_xp_requirement():
    state = PlayerState(
        level=8,
        xp=2,
        xp_required=68,
    )

    assert state.xp == 2
    assert state.xp_required == 68
