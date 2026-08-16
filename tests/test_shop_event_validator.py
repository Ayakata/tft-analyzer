from tft_analyzer.core.enums import EventQuality, EventType
from tft_analyzer.core.models import (
    GameEvent,
    TrackedField,
    TrackedHUDState,
)
from tft_analyzer.validation.hud.validator import (
    HUDEventValidator,
    HUDEventValidatorSettings,
)


def tracked(sid, ts, slots, confidence):
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


def event(target):
    return GameEvent(
        event_id="ev1",
        match_id="m1",
        timestamp_s=20.0,
        event_type=EventType.SHOP_CHANGED,
        payload={
            "field": "shop",
            "from": {"slots": ["a", "b", "c", "d", "e"]},
            "to": target,
            "transition_window": {
                "start_s": 10.0,
                "end_s": 20.0,
                "width_s": 10.0,
            },
        },
        confidence=0.90,
        source_state_ids=("s1", "s2"),
        producer_version="test",
    )


def test_valid_shop_target_is_trusted():
    states = {
        "s1": tracked(
            "s1", 10.0, ["a", "b", "c", "d", "e"], 0.91
        ),
        "s2": tracked(
            "s2", 20.0, ["a", None, "c", "d", "e"], 0.92
        ),
    }
    validator = HUDEventValidator(
        HUDEventValidatorSettings(),
        states_by_id=states,
    )

    result = validator.validate(
        event({"slots": ["a", None, "c", "d", "e"]})
    )

    assert result.quality == EventQuality.TRUSTED
    assert result.apply_to_state is True


def test_invalid_shop_target_is_rejected():
    states = {
        "s1": tracked(
            "s1", 10.0, ["a", "b", "c", "d", "e"], 0.91
        ),
        "s2": tracked(
            "s2", 20.0, ["a", None, "c", "d", "e"], 0.92
        ),
    }
    validator = HUDEventValidator(
        HUDEventValidatorSettings(),
        states_by_id=states,
    )

    result = validator.validate(
        event({"slots": ["a", "b"]})
    )

    assert result.quality == EventQuality.SUSPICIOUS
    assert result.apply_to_state is False
    assert "invalid_target_semantics" in result.reasons
