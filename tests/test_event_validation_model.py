from tft_analyzer.core.enums import EventQuality
from tft_analyzer.core.models import EventValidation


def test_validation_contract_supports_suspicious_but_applyable_target():
    validation = EventValidation(
        validation_id="v1",
        match_id="m1",
        event_id="e1",
        quality=EventQuality.SUSPICIOUS,
        reasons=("low_previous_confidence",),
        field="gold",
        event_timestamp_s=10.0,
        transition_window_s=5.0,
        from_confidence=0.5,
        to_confidence=0.99,
        apply_to_state=True,
        validator_version="test",
    )

    assert validation.quality == EventQuality.SUSPICIOUS
    assert validation.apply_to_state is True
