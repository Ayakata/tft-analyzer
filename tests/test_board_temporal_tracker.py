from tft_analyzer.tracking.board.tracker import TemporalOccupancyTracker


def ingest(tracker, status, ts, allow=True):
    return tracker.ingest(
        position="0",
        candidate_status=status,
        confidence=.9,
        foreground_score=.8 if status == "occupied" else .1,
        raw_score=.7 if status == "occupied" else .2,
        timestamp_s=ts,
        evidence_id=f"e{ts}",
        allow_change=allow,
    )


def test_two_observations_required_for_initialization_and_change():
    tracker = TemporalOccupancyTracker(confirmation_count=2)
    assert ingest(tracker, "empty", 1).action == "pending"
    assert ingest(tracker, "empty", 2).action == "accepted"
    assert tracker.snapshot("0").status == "empty"

    assert ingest(tracker, "occupied", 3).action == "pending"
    assert tracker.snapshot("0").status == "empty"
    assert ingest(tracker, "occupied", 4).action == "accepted"
    assert tracker.snapshot("0").status == "occupied"


def test_uncertain_does_not_mutate_stable_state():
    tracker = TemporalOccupancyTracker(confirmation_count=1)
    ingest(tracker, "empty", 1)
    decision = ingest(tracker, "uncertain", 2)
    assert decision.action == "carried"
    assert tracker.snapshot("0").status == "empty"


def test_unstable_board_frame_cannot_change_existing_state():
    tracker = TemporalOccupancyTracker(confirmation_count=1)
    ingest(tracker, "empty", 1)
    decision = ingest(tracker, "occupied", 2, allow=False)
    assert decision.reason == "board_frame_unstable"
    assert tracker.snapshot("0").status == "empty"
