import json

from tft_analyzer.core.models import TrackedHUDState
from tft_analyzer.storage.tracking_reader import (
    find_latest_tracked_hud_file,
    iter_tracked_hud_states,
)


def test_find_latest_tracker_uses_semantic_version(tmp_path):
    tracking_dir = tmp_path / "tracking"
    tracking_dir.mkdir()

    (tracking_dir / "hud-state-tracker-0.5.2.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    latest = tracking_dir / "hud-state-tracker-0.5.10.jsonl"
    latest.write_text("", encoding="utf-8")
    (tracking_dir / "hud-state-tracker-0.5.99_decisions.jsonl").write_text(
        "",
        encoding="utf-8",
    )

    assert find_latest_tracked_hud_file(tmp_path) == latest


def test_iter_tracked_states(tmp_path):
    state = TrackedHUDState(
        state_id="s1",
        match_id="m1",
        timestamp_s=1.0,
        evidence_id="e1",
        tracker_version="test",
    )

    path = tmp_path / "states.jsonl"
    path.write_text(
        json.dumps(state.model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )

    assert list(iter_tracked_hud_states(path)) == [state]
