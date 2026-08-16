from tft_analyzer.core.enums import (
    EventQuality,
    EventType,
    ReductionAction,
)
from tft_analyzer.core.models import (
    EventValidation,
    GameEvent,
    TrackedField,
    TrackedHUDState,
)
from tft_analyzer.events.hud.detector import (
    HUDEventDetector,
    HUDEventDetectorSettings,
)
from tft_analyzer.reducers.hud.reducer import (
    HUDGameStateReducer,
    HUDGameStateReducerSettings,
)


def tracked_state(sid, ts, hp):
    return TrackedHUDState(
        state_id=sid,
        match_id="m1",
        timestamp_s=ts,
        hp=TrackedField(
            value={"hp": hp},
            confidence=0.99,
            source_observation_id=f"o-{sid}",
            source_evidence_id=f"e-{sid}",
            source_timestamp_s=ts,
            age_s=0.0,
            status="observed",
        ),
        tracker_version="test",
    )


def test_hp_change_becomes_primitive_event():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    assert detector.ingest_state(
        tracked_state("s1", 10.0, 90)
    ) == []

    events = detector.ingest_state(
        tracked_state("s2", 20.0, 76)
    )

    assert len(events) == 1
    assert events[0].event_type == EventType.HP_CHANGED
    assert events[0].payload["delta"] == -14


def test_reducer_applies_hp_event():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.hp = 90

    event = GameEvent(
        event_id="hp1",
        match_id="m1",
        timestamp_s=20.0,
        event_type=EventType.HP_CHANGED,
        payload={
            "field": "hp",
            "from": {"hp": 90},
            "to": {"hp": 76},
            "delta": -14,
        },
        confidence=0.99,
        source_state_ids=("s1", "s2"),
        producer_version="test",
    )
    validation = EventValidation(
        validation_id="v1",
        match_id="m1",
        event_id="hp1",
        quality=EventQuality.TRUSTED,
        reasons=("validated",),
        field="hp",
        event_timestamp_s=20.0,
        transition_window_s=10.0,
        from_confidence=0.99,
        to_confidence=0.99,
        apply_to_state=True,
        source_state_ids=("s1", "s2"),
        validator_version="test",
    )

    decision = reducer.apply_event(event, validation)

    assert decision.action == ReductionAction.APPLIED
    assert reducer.hp == 76

    state = reducer.snapshot(
        timestamp_s=20.0,
        source_token="s2",
        parent_state_id=None,
        applied_event_ids=("hp1",),
        source_state_ids=("s1", "s2"),
    )
    assert state.player.hp == 76
