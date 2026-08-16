from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.tracking.hud.semantic import canonical_hud_value
from tft_analyzer.tracking.hud.tracker import (
    HUDStateTracker,
    HUDTrackerSettings,
)


def shop_obs(slots, ts, oid, confidence=0.90):
    payload_slots = []
    for index, name in enumerate(slots):
        payload_slots.append(
            {
                "index": index,
                "occupied": name is not None,
                "resolved_name": name,
                "ocr_confidence": confidence if name else 0.0,
                "identity_confidence": confidence if name else 0.0,
            }
        )

    return Observation(
        observation_id=oid,
        match_id="m1",
        timestamp_s=ts,
        kind=ObservationKind.SHOP,
        value={
            "slots": payload_slots,
            "complete": True,
        },
        confidence=confidence,
        evidence_ids=(f"e-{oid}",),
        producer_version="test",
    )


def test_shop_semantic_strips_ocr_metadata():
    value = canonical_hud_value(
        ObservationKind.SHOP,
        shop_obs(
            ["pyke", None, "ezreal", "ornn", "nami"],
            1.0,
            "o",
        ).value,
    )

    assert value == {
        "slots": ["pyke", None, "ezreal", "ornn", "nami"]
    }


def test_same_shop_refreshes_and_real_change_is_accepted():
    tracker = HUDStateTracker(HUDTrackerSettings())

    first = tracker.ingest(
        shop_obs(["a", "b", "c", "d", "e"], 10.0, "o1")
    )
    same = tracker.ingest(
        shop_obs(["a", "b", "c", "d", "e"], 20.0, "o2")
    )
    changed = tracker.ingest(
        shop_obs(["a", None, "c", "d", "e"], 30.0, "o3")
    )

    assert first.action == "accepted"
    assert same.action == "refreshed"
    assert changed.action == "accepted"
    assert changed.reason == "shop_changed"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=30.0,
        evidence_id="e3",
    )
    assert state.shop.value == {
        "slots": ["a", None, "c", "d", "e"]
    }


def test_low_confidence_shop_change_requires_confirmation():
    tracker = HUDStateTracker(
        HUDTrackerSettings(
            suspicious_confirmation_count=2,
            shop_change_min_confidence=0.80,
        )
    )

    tracker.ingest(
        shop_obs(["a", "b", "c", "d", "e"], 10.0, "o1", 0.95)
    )

    first = tracker.ingest(
        shop_obs(["x", "b", "c", "d", "e"], 20.0, "o2", 0.70)
    )
    assert first.action == "pending"
    assert first.reason == "shop_low_confidence_change_awaiting_confirmation"

    state = tracker.snapshot(
        match_id="m1",
        timestamp_s=20.0,
        evidence_id="e2",
    )
    assert state.shop.value == {
        "slots": ["a", "b", "c", "d", "e"]
    }

    second = tracker.ingest(
        shop_obs(["x", "b", "c", "d", "e"], 30.0, "o3", 0.70)
    )
    assert second.action == "accepted"
    assert second.reason == "shop_low_confidence_change_confirmed"
