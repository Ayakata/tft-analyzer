from tft_analyzer.core.enums import (
    EventQuality,
    EventType,
    ReductionAction,
)
from tft_analyzer.core.models import EventValidation, GameEvent
from tft_analyzer.reducers.hud.reducer import (
    HUDGameStateReducer,
    HUDGameStateReducerSettings,
)


def test_reducer_applies_shop_changed_to_game_state():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.shop_slots = ("a", "b", "c", "d", "e")

    event = GameEvent(
        event_id="shop1",
        match_id="m1",
        timestamp_s=20.0,
        event_type=EventType.SHOP_CHANGED,
        payload={
            "field": "shop",
            "from": {"slots": ["a", "b", "c", "d", "e"]},
            "to": {"slots": ["a", None, "c", "d", "e"]},
        },
        confidence=0.95,
        source_state_ids=("s1", "s2"),
        producer_version="test",
    )
    validation = EventValidation(
        validation_id="v1",
        match_id="m1",
        event_id="shop1",
        quality=EventQuality.TRUSTED,
        reasons=("validated",),
        field="shop",
        event_timestamp_s=20.0,
        transition_window_s=10.0,
        from_confidence=0.95,
        to_confidence=0.95,
        apply_to_state=True,
        source_state_ids=("s1", "s2"),
        validator_version="test",
    )

    decision = reducer.apply_event(event, validation)

    assert decision.action == ReductionAction.APPLIED
    assert reducer.shop_slots == ("a", None, "c", "d", "e")

    state = reducer.snapshot(
        timestamp_s=20.0,
        source_token="s2",
        parent_state_id=None,
        applied_event_ids=("shop1",),
        source_state_ids=("s1", "s2"),
    )
    assert state.shop.slots == ("a", None, "c", "d", "e")
    assert state.shop.locked is None
