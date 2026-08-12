from tft_analyzer.core.enums import EventType
from tft_analyzer.core.models import TrackedField, TrackedHUDState
from tft_analyzer.events.hud.detector import (
    HUDEventDetector,
    HUDEventDetectorSettings,
)


def field(value, *, ts, oid, eid, conf=0.99, status="observed"):
    return TrackedField(
        value=value,
        confidence=conf,
        source_observation_id=oid,
        source_evidence_id=eid,
        source_timestamp_s=ts,
        age_s=0.0,
        status=status,
    )


def state(
    *,
    sid,
    ts,
    stage=None,
    level=None,
    xp=None,
    gold=None,
):
    kwargs = {}
    for name, value in (
        ("stage", stage),
        ("level", level),
        ("xp", xp),
        ("gold", gold),
    ):
        if isinstance(value, TrackedField):
            kwargs[name] = value

    return TrackedHUDState(
        state_id=sid,
        match_id="m1",
        timestamp_s=ts,
        evidence_id=f"frame-{sid}",
        tracker_version="test",
        **kwargs,
    )


def test_first_observation_establishes_baseline_without_event():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    events = detector.ingest_state(
        state(
            sid="s1",
            ts=1.0,
            gold=field(
                {"gold": 10},
                ts=1.0,
                oid="g1",
                eid="e1",
            ),
        )
    )

    assert events == []


def test_repeated_semantic_value_does_not_emit_event():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    detector.ingest_state(
        state(
            sid="s1",
            ts=1.0,
            gold=field({"gold": 10}, ts=1.0, oid="g1", eid="e1"),
        )
    )
    events = detector.ingest_state(
        state(
            sid="s2",
            ts=2.0,
            gold=field({"gold": 10}, ts=2.0, oid="g2", eid="e2"),
        )
    )

    assert events == []


def test_gold_change_emits_delta_and_provenance():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    detector.ingest_state(
        state(
            sid="s1",
            ts=10.0,
            gold=field(
                {"gold": 50},
                ts=10.0,
                oid="g1",
                eid="e1",
                conf=0.97,
            ),
        )
    )

    events = detector.ingest_state(
        state(
            sid="s2",
            ts=20.0,
            gold=field(
                {"gold": 43},
                ts=20.0,
                oid="g2",
                eid="e2",
                conf=0.95,
            ),
        )
    )

    assert len(events) == 1
    event = events[0]

    assert event.event_type == EventType.GOLD_CHANGED
    assert event.payload["from"] == {"gold": 50}
    assert event.payload["to"] == {"gold": 43}
    assert event.payload["delta"] == -7
    assert event.payload["transition_window"]["width_s"] == 10.0
    assert event.confidence == 0.95
    assert event.observation_ids == ("g1", "g2")
    assert event.evidence_ids == ("e1", "e2")
    assert event.source_state_ids == ("s1", "s2")


def test_carried_state_never_emits_event():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    detector.ingest_state(
        state(
            sid="s1",
            ts=10.0,
            xp=field(
                {"current": 4, "required": 20},
                ts=10.0,
                oid="x1",
                eid="e1",
            ),
        )
    )

    carried = field(
        {"current": 6, "required": 20},
        ts=10.0,
        oid="x1",
        eid="e1",
        status="carried",
    )

    events = detector.ingest_state(
        state(
            sid="s2",
            ts=15.0,
            xp=carried,
        )
    )

    assert events == []


def test_xp_requirement_change_is_preserved():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    detector.ingest_state(
        state(
            sid="s1",
            ts=100.0,
            xp=field(
                {"current": 54, "required": 60},
                ts=100.0,
                oid="x1",
                eid="e1",
            ),
        )
    )

    events = detector.ingest_state(
        state(
            sid="s2",
            ts=110.0,
            xp=field(
                {"current": 2, "required": 68},
                ts=110.0,
                oid="x2",
                eid="e2",
            ),
        )
    )

    event = events[0]
    assert event.event_type == EventType.XP_CHANGED
    assert event.payload["requirement_changed"] is True
    assert event.payload["current_delta"] is None


def test_stage_change_uses_round_start_contract():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    detector.ingest_state(
        state(
            sid="s1",
            ts=100.0,
            stage=field(
                {"stage": 3, "round": 7},
                ts=100.0,
                oid="sobs1",
                eid="e1",
            ),
        )
    )

    events = detector.ingest_state(
        state(
            sid="s2",
            ts=110.0,
            stage=field(
                {"stage": 4, "round": 1},
                ts=110.0,
                oid="sobs2",
                eid="e2",
            ),
        )
    )

    event = events[0]
    assert event.event_type == EventType.ROUND_START
    assert event.payload["stage_changed"] is True
    assert event.payload["round_changed"] is True


def test_same_value_refreshes_transition_window_baseline():
    detector = HUDEventDetector(HUDEventDetectorSettings())

    detector.ingest_state(
        state(
            sid="s1",
            ts=10.0,
            gold=field({"gold": 10}, ts=10.0, oid="g1", eid="e1"),
        )
    )
    detector.ingest_state(
        state(
            sid="s2",
            ts=19.0,
            gold=field({"gold": 10}, ts=19.0, oid="g2", eid="e2"),
        )
    )
    events = detector.ingest_state(
        state(
            sid="s3",
            ts=29.0,
            gold=field({"gold": 15}, ts=29.0, oid="g3", eid="e3"),
        )
    )

    assert events[0].payload["transition_window"]["start_s"] == 19.0
    assert events[0].payload["transition_window"]["width_s"] == 10.0


def test_long_window_warns_without_lowering_confidence():
    detector = HUDEventDetector(
        HUDEventDetectorSettings(
            warn_transition_window_seconds=20.0,
        )
    )

    detector.ingest_state(
        state(
            sid="s1",
            ts=10.0,
            level=field(
                {"level": 6},
                ts=10.0,
                oid="l1",
                eid="e1",
                conf=0.98,
            ),
        )
    )

    events = detector.ingest_state(
        state(
            sid="s2",
            ts=40.0,
            level=field(
                {"level": 7},
                ts=40.0,
                oid="l2",
                eid="e2",
                conf=0.97,
            ),
        )
    )

    event = events[0]
    assert event.payload["timing_warning"] is True
    assert event.confidence == 0.97
