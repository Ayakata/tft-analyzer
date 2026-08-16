from tft_analyzer.tracking.board.pipeline import (
    BoardOccupancyTrackerSettings,
    _capacity_status,
    _level_value,
    _stage_key,
)
from tft_analyzer.tracking.board.tracker import TemporalOccupancyTracker


def test_stage_and_level_normalization():
    assert _stage_key({"stage": 5, "round": 7}) == "5-7"
    assert _stage_key("6-1") == "6-1"
    assert _stage_key(None) is None
    assert _level_value({"level": 8}) == 8
    assert _level_value({"level": 3}) == 3
    assert _level_value(8) == 8
    assert _level_value(8.0) == 8
    assert _level_value({"level": 0}) is None
    assert _level_value({"level": 11}) is None
    assert _level_value({}) is None
    assert _level_value(0) is None
    assert _level_value(11) is None
    assert _level_value(True) is None


def test_capacity_status():
    assert _capacity_status(occupied_count=7, level=8) == "under"
    assert _capacity_status(occupied_count=8, level=8) == "at"
    assert _capacity_status(occupied_count=9, level=8) == "over"
    assert _capacity_status(occupied_count=9, level=None) == "unknown"


def test_force_status_replaces_stale_cell():
    tracker = TemporalOccupancyTracker(confirmation_count=2)
    d1 = tracker.force_status(
        position="0,0",
        status="occupied",
        confidence=0.8,
        foreground_score=0.7,
        raw_score=0.6,
        timestamp_s=10.0,
        evidence_id="e1",
        reason="full_level_snapshot",
    )
    assert d1.action == "accepted"
    assert tracker.snapshot("0,0").status == "occupied"

    d2 = tracker.force_status(
        position="0,0",
        status="empty",
        confidence=0.55,
        foreground_score=0.4,
        raw_score=0.4,
        timestamp_s=20.0,
        evidence_id="e2",
        reason="level_cap_inferred_empty",
    )
    assert d2.action == "accepted"
    assert d2.reason == "level_cap_inferred_empty"
    assert tracker.snapshot("0,0").status == "empty"


def test_blocked_reason_is_preserved():
    tracker = TemporalOccupancyTracker(confirmation_count=1)
    tracker.force_status(
        position="0,0",
        status="occupied",
        confidence=0.8,
        foreground_score=0.7,
        raw_score=0.6,
        timestamp_s=1.0,
        evidence_id="e1",
        reason="seed",
    )
    d = tracker.ingest(
        position="0,0",
        candidate_status="empty",
        confidence=0.7,
        foreground_score=0.2,
        raw_score=0.2,
        timestamp_s=2.0,
        evidence_id="e2",
        allow_change=False,
        blocked_reason="outside_planning_window",
    )
    assert d.action == "carried"
    assert d.reason == "outside_planning_window"
    assert tracker.snapshot("0,0").status == "occupied"


def test_hud_gate_defaults():
    s = BoardOccupancyTrackerSettings()
    assert s.use_hud_board_context is True
    assert s.planning_min_round_age_s == 2.5
    assert s.planning_max_round_age_s == 32.0
    assert s.full_level_snapshot_max_uncertain == 14
    assert s.full_level_snapshot_min_mean_fg == 0.60
