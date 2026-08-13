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


def state(sid, *, gold=None, gold_conf=1.0):
    kwargs = {}
    if gold is not None:
        kwargs["gold"] = TrackedField(
            value={"gold": gold},
            confidence=gold_conf,
            source_observation_id=f"obs-{sid}",
            source_evidence_id=f"ev-{sid}",
            source_timestamp_s=1.0,
            age_s=0.0,
            status="observed",
        )
    return TrackedHUDState(
        state_id=sid,
        match_id="m1",
        timestamp_s=1.0,
        evidence_id=f"frame-{sid}",
        tracker_version="test",
        **kwargs,
    )


def event(
    *,
    eid="e1",
    before=41,
    after=17,
    source=("s1", "s2"),
    width=5.0,
):
    return GameEvent(
        event_id=eid,
        match_id="m1",
        timestamp_s=10.0,
        event_type=EventType.GOLD_CHANGED,
        payload={
            "field": "gold",
            "from": {"gold": before},
            "to": {"gold": after},
            "delta": after - before,
            "transition_window": {
                "start_s": 5.0,
                "end_s": 10.0,
                "width_s": width,
            },
            "timing_warning": width > 20.0,
        },
        confidence=0.5,
        source_state_ids=source,
        producer_version="test",
    )


def test_low_target_confidence_is_suspicious_and_skipped():
    states = {
        "s1": state("s1", gold=41, gold_conf=1.0),
        "s2": state("s2", gold=17, gold_conf=0.48),
    }

    validator = HUDEventValidator(
        HUDEventValidatorSettings(),
        states_by_id=states,
    )

    result = validator.validate(event())

    assert result.quality == EventQuality.SUSPICIOUS
    assert "low_target_confidence" in result.reasons
    assert result.apply_to_state is False
    assert result.from_confidence == 1.0
    assert result.to_confidence == 0.48


def test_low_previous_but_strong_target_is_suspicious_but_applyable():
    states = {
        "s1": state("s1", gold=1, gold_conf=0.59),
        "s2": state("s2", gold=52, gold_conf=0.99),
    }

    validator = HUDEventValidator(
        HUDEventValidatorSettings(),
        states_by_id=states,
    )

    result = validator.validate(
        event(before=1, after=52)
    )

    assert result.quality == EventQuality.SUSPICIOUS
    assert "low_previous_confidence" in result.reasons
    assert "low_target_confidence" not in result.reasons
    assert result.apply_to_state is True


def test_wide_window_is_timing_uncertain_but_applyable():
    states = {
        "s1": state("s1", gold=10, gold_conf=0.99),
        "s2": state("s2", gold=20, gold_conf=0.99),
    }

    validator = HUDEventValidator(
        HUDEventValidatorSettings(),
        states_by_id=states,
    )

    result = validator.validate(
        event(before=10, after=20, width=30.0)
    )

    assert result.quality == EventQuality.TIMING_UNCERTAIN
    assert result.apply_to_state is True
    assert "wide_transition_window" in result.reasons


def test_non_adjacent_stage_is_timing_uncertain():
    s1 = TrackedHUDState(
        state_id="s1",
        match_id="m1",
        timestamp_s=1.0,
        stage=TrackedField(
            value={"stage": 1, "round": 2},
            confidence=0.99,
            source_observation_id="o1",
            source_evidence_id="e1",
            source_timestamp_s=1.0,
            age_s=0.0,
            status="observed",
        ),
        tracker_version="test",
    )
    s2 = TrackedHUDState(
        state_id="s2",
        match_id="m1",
        timestamp_s=2.0,
        stage=TrackedField(
            value={"stage": 1, "round": 4},
            confidence=0.99,
            source_observation_id="o2",
            source_evidence_id="e2",
            source_timestamp_s=2.0,
            age_s=0.0,
            status="observed",
        ),
        tracker_version="test",
    )

    ev = GameEvent(
        event_id="stage-event",
        match_id="m1",
        timestamp_s=2.0,
        event_type=EventType.ROUND_START,
        payload={
            "field": "stage",
            "from": {"stage": 1, "round": 2},
            "to": {"stage": 1, "round": 4},
            "transition_window": {
                "start_s": 1.0,
                "end_s": 2.0,
                "width_s": 1.0,
            },
            "timing_warning": False,
        },
        confidence=0.99,
        source_state_ids=("s1", "s2"),
        producer_version="test",
    )

    validator = HUDEventValidator(
        HUDEventValidatorSettings(),
        states_by_id={"s1": s1, "s2": s2},
    )
    result = validator.validate(ev)

    assert result.quality == EventQuality.TIMING_UNCERTAIN
    assert "non_adjacent_stage_transition" in result.reasons
    assert result.apply_to_state is True
