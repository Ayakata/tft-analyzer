from tft_analyzer.analyzers.economy_tempo.timeline import (
    format_economy_tempo_findings_timeline,
)
from tft_analyzer.core.models.analysis import Finding


def test_timeline_states_no_meta_grade_policy(tmp_path):
    path = tmp_path / "findings.jsonl"
    item = Finding(
        finding_id="f1",
        match_id="m",
        decision_id="d1",
        finding_code="large_spend",
        producer_version="economy-tempo-analyzer-0.16.1",
        category="economy.activity",
        title="Large observed spend episode",
        interpretation="descriptive",
        stage="4-2",
        start_timestamp_s=10.0,
        end_timestamp_s=20.0,
        metrics={"observed_spend": 30, "gold_after": 5},
    )
    path.write_text(item.model_dump_json() + "\n", encoding="utf-8")
    text = format_economy_tempo_findings_timeline(path)
    assert "large_spend" in text
    assert "does not grade player decisions" in text
    assert "reconstruction uncertainty" in text
    assert "hard data-quality conflicts" in text
