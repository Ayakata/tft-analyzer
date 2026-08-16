from tft_analyzer.core.enums import EventType
from tft_analyzer.core.models import TrackedField, TrackedHUDState
from tft_analyzer.events.hud.detector import (
    HUDEventDetector,
    HUDEventDetectorSettings,
)


def state(sid, ts, slots, confidence=0.95):
    return TrackedHUDState(
        state_id=sid,
        match_id="m1",
        timestamp_s=ts,
        shop=TrackedField(
            value={"slots": slots},
            confidence=confidence,
            source_observation_id=f"o-{sid}",
            source_evidence_id=f"e-{sid}",
            source_timestamp_s=ts,
            age_s=0.0,
            status="observed",
        ),
        tracker_version="test",
    )


def test_shop_change_emits_primitive_slot_diff_only():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    assert detector.ingest_state(
        state("s1", 10.0, ["a", "b", "c", "d", "e"])
    ) == []

    events = detector.ingest_state(
        state("s2", 20.0, ["a", None, "x", "d", "e"])
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == EventType.SHOP_CHANGED
    assert event.payload["field"] == "shop"
    assert event.payload["changed_slots"] == [1, 2]
    assert event.payload["slot_change_count"] == 2
    assert event.payload["slot_changes"] == [
        {"index": 1, "from": "b", "to": None},
        {"index": 2, "from": "c", "to": "x"},
    ]
    assert "cause" not in event.payload
