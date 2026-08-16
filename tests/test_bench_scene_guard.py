from tft_analyzer.tracking.board.tracker import TemporalOccupancyTracker


def test_carry_is_strict_noop_for_canonical_and_pending_state():
    tracker = TemporalOccupancyTracker(confirmation_count=2)

    # Establish canonical occupied.
    tracker.force_status(
        position="0",
        status="occupied",
        confidence=0.9,
        foreground_score=0.8,
        raw_score=0.8,
        timestamp_s=10.0,
        evidence_id="good",
        reason="seed",
    )

    # Start an empty transition but do not confirm it yet.
    pending = tracker.ingest(
        position="0",
        candidate_status="empty",
        confidence=0.8,
        foreground_score=0.2,
        raw_score=0.2,
        timestamp_s=20.0,
        evidence_id="good2",
        allow_change=True,
    )
    assert pending.action == "pending"
    before = tracker.snapshot("0")
    assert before.status == "occupied"
    assert before.pending_status == "empty"
    assert before.pending_count == 1
    assert before.source_timestamp_s == 10.0
    assert before.source_evidence_id == "good"

    # Scene-invalid observation must not alter *anything* in tracker state.
    d = tracker.carry(
        position="0",
        candidate_status="occupied",
        confidence=0.99,
        reason="scene_invalid",
    )
    after = tracker.snapshot("0")

    assert d.action == "carried"
    assert d.reason == "scene_invalid"
    assert after.status == before.status
    assert after.pending_status == before.pending_status
    assert after.pending_count == before.pending_count
    assert after.source_timestamp_s == before.source_timestamp_s
    assert after.source_evidence_id == before.source_evidence_id


def test_carry_unknown_position_stays_unknown():
    tracker = TemporalOccupancyTracker(confirmation_count=2)
    d = tracker.carry(
        position="8",
        candidate_status="empty",
        confidence=0.8,
        reason="scene_invalid",
    )
    state = tracker.snapshot("8")

    assert d.action == "carried"
    assert state.status == "unknown"
    assert state.pending_status is None
    assert state.pending_count == 0
    assert state.source_timestamp_s is None
