import json

from tft_analyzer.core.enums import EventType
from tft_analyzer.core.models import GameEvent
from tft_analyzer.events.hud.timeline import format_hud_event_timeline


def test_event_timeline_formats_gold_delta(tmp_path):
    event = GameEvent(
        event_id="ev1",
        match_id="m1",
        timestamp_s=20.0,
        event_type=EventType.GOLD_CHANGED,
        payload={
            "field": "gold",
            "from": {"gold": 50},
            "to": {"gold": 43},
            "delta": -7,
            "transition_window": {
                "start_s": 10.0,
                "end_s": 20.0,
                "width_s": 10.0,
            },
            "timing_warning": False,
        },
        confidence=0.95,
        producer_version="test",
    )

    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(event.model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )

    text = format_hud_event_timeline(path)
    assert "gold_changed" in text
    assert "50 -> 43 (-7)" in text
    assert "10.0s" in text
