from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.tracking.hud.semantic import canonical_hud_value
from tft_analyzer.tracking.hud.tracker import (
    HUDStateTracker,
    HUDTrackerSettings,
)


def obs(hp, ts, oid, confidence=0.95):
    return Observation(
        observation_id=oid,
        match_id="m1",
        timestamp_s=ts,
        kind=ObservationKind.HP,
        value={
            "hp": hp,
            "row_index": 3,
            "ocr_variant": "rgb_tight",
        },
        confidence=confidence,
        evidence_ids=(f"e-{oid}",),
        producer_version="test",
    )


def test_hp_semantic_strips_player_perception_metadata():
    value = canonical_hud_value(
        ObservationKind.HP,
        {"hp": 84, "row_index": 2, "self_score": 0.9},
    )
    assert value == {"hp": 84}


def test_normal_hp_damage_is_accepted_immediately():
    tracker = HUDStateTracker(HUDTrackerSettings())

    first = tracker.ingest(obs(80, 10.0, "o1"))
    second = tracker.ingest(obs(67, 20.0, "o2"))

    assert first.action == "accepted"
    assert second.action == "accepted"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=20.0,
        evidence_id="e2",
    )
    assert state.hp.value == {"hp": 67}


def test_hp_increase_requires_confirmation():
    tracker = HUDStateTracker(
        HUDTrackerSettings(suspicious_confirmation_count=2)
    )

    tracker.ingest(obs(67, 10.0, "a"))
    first = tracker.ingest(obs(75, 20.0, "b"))
    assert first.action == "pending"
    assert first.reason == "hp_increase_requires_confirmation_awaiting_confirmation"

    second = tracker.ingest(obs(75, 30.0, "c"))
    assert second.action == "accepted"
    assert second.reason == "hp_increase_requires_confirmation_confirmed"


def test_large_hp_jump_requires_confirmation():
    tracker = HUDStateTracker(
        HUDTrackerSettings(
            suspicious_confirmation_count=2,
            hp_max_jump_without_confirmation=25,
        )
    )

    assert tracker.ingest(obs(100, 10.0, "a")).action == "accepted"

    first_jump = tracker.ingest(obs(50, 20.0, "b"))
    assert first_jump.action == "pending"
    assert first_jump.reason == (
        "hp_large_jump_requires_confirmation_awaiting_confirmation"
    )

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=20.0,
        evidence_id="e20",
    )
    assert state.hp.value == {"hp": 100}

    second_jump = tracker.ingest(obs(50, 30.0, "c"))
    assert second_jump.action == "accepted"
    assert second_jump.reason == (
        "hp_large_jump_requires_confirmation_confirmed"
    )


def test_low_confidence_single_digit_is_rejected():
    tracker = HUDStateTracker(
        HUDTrackerSettings(hp_single_digit_min_confidence=0.90)
    )

    tracker.ingest(obs(48, 10.0, "a"))
    decision = tracker.ingest(obs(4, 20.0, "b", confidence=0.71))

    assert decision.action == "rejected"
    assert decision.reason == "hp_single_digit_low_confidence"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=20.0,
        evidence_id="e20",
    )
    assert state.hp.value == {"hp": 48}


def test_high_confidence_single_digit_requires_confirmation():
    tracker = HUDStateTracker(
        HUDTrackerSettings(
            suspicious_confirmation_count=2,
            hp_single_digit_min_confidence=0.90,
        )
    )

    tracker.ingest(obs(17, 10.0, "a"))
    first = tracker.ingest(obs(6, 20.0, "b", confidence=0.96))
    assert first.action == "pending"
    assert first.reason == (
        "hp_single_digit_requires_confirmation_awaiting_confirmation"
    )

    second = tracker.ingest(obs(6, 30.0, "c", confidence=0.99))
    assert second.action == "accepted"
    assert second.reason == (
        "hp_single_digit_requires_confirmation_confirmed"
    )


def test_single_high_conf_glitch_then_old_value_does_not_change_hp():
    tracker = HUDStateTracker(
        HUDTrackerSettings(
            suspicious_confirmation_count=2,
            hp_single_digit_min_confidence=0.90,
        )
    )

    tracker.ingest(obs(35, 10.0, "a"))
    assert tracker.ingest(
        obs(1, 20.0, "b", confidence=0.95)
    ).action == "pending"

    back = tracker.ingest(obs(35, 30.0, "c"))
    assert back.action == "refreshed"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=30.0,
        evidence_id="e30",
    )
    assert state.hp.value == {"hp": 35}


def test_realistic_eighteen_hp_damage_is_accepted_immediately():
    tracker = HUDStateTracker(
        HUDTrackerSettings(
            hp_max_jump_without_confirmation=25,
        )
    )

    tracker.ingest(obs(35, 10.0, "a"))
    decision = tracker.ingest(obs(17, 20.0, "b"))

    assert decision.action == "accepted"
    assert decision.reason == "hp_changed"
