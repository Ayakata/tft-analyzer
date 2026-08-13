from tft_analyzer.core.enums import EventType
from tft_analyzer.core.models import GameEvent
from tft_analyzer.reducers.hud.pipeline import event_target_state_id


def test_event_routes_by_target_source_state_not_timestamp():
    event = GameEvent(
        event_id="e1",
        match_id="m1",
        timestamp_s=100.0000001,
        event_type=EventType.GOLD_CHANGED,
        payload={
            "field": "gold",
            "from": {"gold": 10},
            "to": {"gold": 12},
        },
        confidence=0.99,
        source_state_ids=("old-state", "target-state"),
        producer_version="test",
    )

    assert event_target_state_id(event) == "target-state"


def test_event_without_source_state_cannot_be_routed():
    event = GameEvent(
        event_id="e2",
        match_id="m1",
        timestamp_s=100.0,
        event_type=EventType.GOLD_CHANGED,
        payload={
            "field": "gold",
            "from": {"gold": 10},
            "to": {"gold": 12},
        },
        confidence=0.99,
        producer_version="test",
    )

    try:
        event_target_state_id(event)
    except ValueError as exc:
        assert "source_state_ids" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
