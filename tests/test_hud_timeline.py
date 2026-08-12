import json

from tft_analyzer.core.models import (
    TrackedField,
    TrackedHUDState,
)
from tft_analyzer.tracking.hud.timeline import (
    format_hud_timeline,
)


def test_timeline_marks_carried_values(tmp_path):
    state = TrackedHUDState(
        state_id="s1",
        match_id="m1",
        timestamp_s=10.0,
        evidence_id="e1",
        stage=TrackedField(
            value={"stage": 2, "round": 1},
            confidence=0.9,
            status="carried",
            age_s=2.0,
        ),
        gold=TrackedField(
            value={"gold": 10},
            confidence=0.9,
            status="observed",
            age_s=0.0,
        ),
        tracker_version="test",
    )

    path = tmp_path / "states.jsonl"
    path.write_text(
        json.dumps(state.model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )

    text = format_hud_timeline(path)
    assert "2-1~" in text
    assert "10" in text
