from tft_analyzer.core.models import TrackingDecision


def test_value_change_requires_accepted_semantic_difference():
    decisions = [
        TrackingDecision(
            decision_id="d1", match_id="m1", timestamp_s=1.0,
            field="level", observation_id="o1", action="accepted",
            reason="initial", previous_value=None, observed_value={"level": 4},
            confidence=0.9, tracker_version="test",
        ),
        TrackingDecision(
            decision_id="d2", match_id="m1", timestamp_s=2.0,
            field="level", observation_id="o2", action="refreshed",
            reason="same_level", previous_value={"level": 4}, observed_value={"level": 4},
            confidence=0.9, tracker_version="test",
        ),
        TrackingDecision(
            decision_id="d3", match_id="m1", timestamp_s=3.0,
            field="level", observation_id="o3", action="accepted",
            reason="level_forward", previous_value={"level": 4}, observed_value={"level": 5},
            confidence=0.9, tracker_version="test",
        ),
    ]
    changes = sum(
        1 for d in decisions
        if d.action == "accepted" and d.previous_value is not None and d.previous_value != d.observed_value
    )
    assert changes == 1
