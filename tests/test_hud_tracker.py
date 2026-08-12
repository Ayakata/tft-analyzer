from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.tracking.hud.tracker import (
    HUDStateTracker,
    HUDTrackerSettings,
)


def obs(
    *,
    oid,
    kind,
    value,
    ts,
    confidence=0.99,
):
    return Observation(
        observation_id=oid,
        match_id="m1",
        timestamp_s=ts,
        kind=kind,
        value=value,
        confidence=confidence,
        evidence_ids=(f"e-{ts}",),
        producer_version="test",
    )


def test_missing_observation_is_carried_then_becomes_stale():
    tracker = HUDStateTracker(
        HUDTrackerSettings(
            max_age_seconds={
                "stage": 30,
                "gold": 8,
                "level": 20,
                "xp": 8,
            }
        )
    )

    tracker.ingest(
        obs(
            oid="g1",
            kind=ObservationKind.GOLD,
            value={"gold": 10},
            ts=1.0,
        )
    )

    s1 = tracker.snapshot(
        match_id="m1",
        timestamp_s=1.0,
        evidence_id="e1",
    )
    assert s1.gold.status == "observed"
    assert s1.gold.value["gold"] == 10

    s2 = tracker.snapshot(
        match_id="m1",
        timestamp_s=5.0,
        evidence_id="e2",
    )
    assert s2.gold.status == "carried"
    assert s2.gold.value["gold"] == 10
    assert 0 < s2.gold.confidence < s1.gold.confidence

    s3 = tracker.snapshot(
        match_id="m1",
        timestamp_s=10.0,
        evidence_id="e3",
    )
    assert s3.gold.status == "stale"
    assert s3.gold.value is None


def test_level_regression_does_not_replace_stable_value():
    tracker = HUDStateTracker(HUDTrackerSettings())

    d1 = tracker.ingest(
        obs(
            oid="l1",
            kind=ObservationKind.LEVEL,
            value={"level": 5},
            ts=1.0,
        )
    )
    assert d1.action == "accepted"

    d2 = tracker.ingest(
        obs(
            oid="l2",
            kind=ObservationKind.LEVEL,
            value={"level": 4},
            ts=2.0,
        )
    )
    assert d2.action == "rejected"
    assert d2.reason == "level_regression"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=2.0,
        evidence_id="e2",
    )
    assert state.level.value["level"] == 5


def test_large_stage_jump_needs_confirmation():
    tracker = HUDStateTracker(
        HUDTrackerSettings(
            suspicious_confirmation_count=2,
        )
    )

    tracker.ingest(
        obs(
            oid="s1",
            kind=ObservationKind.STAGE,
            value={"stage": 2, "round": 1},
            ts=1.0,
        )
    )

    first = tracker.ingest(
        obs(
            oid="s2",
            kind=ObservationKind.STAGE,
            value={"stage": 7, "round": 5},
            ts=2.0,
        )
    )
    assert first.action == "pending"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=2.0,
        evidence_id="e2",
    )
    assert state.stage.value["stage"] == 2

    second = tracker.ingest(
        obs(
            oid="s3",
            kind=ObservationKind.STAGE,
            value={"stage": 7, "round": 5},
            ts=3.0,
        )
    )
    assert second.action == "accepted"
    assert second.reason == "large_stage_jump_confirmed"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=3.0,
        evidence_id="e3",
    )
    assert state.stage.value["stage"] == 7


def test_same_semantic_value_with_different_ocr_metadata_is_refreshed():
    tracker = HUDStateTracker(HUDTrackerSettings())

    first = obs(
        oid="l-meta-1",
        kind=ObservationKind.LEVEL,
        value={
            "level": 5,
            "raw_text": "Lvl.5",
            "ocr_variant": "rgb_tight",
            "presence_score": 1.0,
        },
        ts=10.0,
    )
    second = obs(
        oid="l-meta-2",
        kind=ObservationKind.LEVEL,
        value={
            "level": 5,
            "raw_text": "5",
            "ocr_variant": "gray_tight",
            "presence_score": 0.91,
        },
        ts=20.0,
    )

    d1 = tracker.ingest(first)
    d2 = tracker.ingest(second)

    assert d1.action == "accepted"
    assert d2.action == "refreshed"
    assert d2.reason == "same_level"

    state = tracker.snapshot(match_id="m1", timestamp_s=20.0, evidence_id="e20")
    assert state.level.value == {"level": 5}
    assert "ocr_variant" not in state.level.value


def test_default_gold_ttl_covers_normal_ten_second_capture_gap():
    tracker = HUDStateTracker(HUDTrackerSettings())
    tracker.ingest(
        obs(
            oid="g-gap",
            kind=ObservationKind.GOLD,
            value={"gold": 53},
            ts=100.0,
        )
    )
    state = tracker.snapshot(match_id="m1", timestamp_s=110.0, evidence_id="e110")
    assert state.gold.status == "carried"
    assert state.gold.value == {"gold": 53}
    assert state.gold.confidence > 0.0


def test_default_xp_ttl_covers_normal_ten_second_capture_gap():
    tracker = HUDStateTracker(HUDTrackerSettings())
    tracker.ingest(
        obs(
            oid="xp-gap",
            kind=ObservationKind.XP,
            value={"current": 4, "required": 60},
            ts=100.0,
        )
    )
    state = tracker.snapshot(match_id="m1", timestamp_s=110.0, evidence_id="e110")
    assert state.xp.status == "carried"
    assert state.xp.value == {"current": 4, "required": 60}
