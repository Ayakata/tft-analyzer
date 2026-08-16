import json
from pathlib import Path

from tft_analyzer.actions.models import (
    ActionInferenceQuality,
    ActionWindowDiagnostic,
    EconomyLedgerWindow,
    InferredAction,
)
from tft_analyzer.core.enums import ActionType
from tft_analyzer.decisions import (
    DecisionEpisodeSettings,
    build_match_decision_episodes,
)


def write_jsonl(path, values):
    with path.open("w", encoding="utf-8") as f:
        for value in values:
            f.write(value.model_dump_json() + "\n")


def test_pipeline_covers_every_action_once(tmp_path):
    match = tmp_path / "match"
    actions_dir = match / "actions"
    actions_dir.mkdir(parents=True)

    action = InferredAction(
        action_id="a1",
        match_id="m",
        action_type=ActionType.BUY_UNIT,
        start_timestamp_s=0,
        end_timestamp_s=10,
        confidence=0.72,
        quality=ActionInferenceQuality.SUPPORTED,
        params={},
        signals={},
        evidence_ids=("e0", "e1"),
        producer_version="semantic-action-fusion-0.14.6",
    )
    window = ActionWindowDiagnostic(
        window_index=0,
        match_id="m",
        start_timestamp_s=0,
        end_timestamp_s=10,
        start_evidence_id="e0",
        end_evidence_id="e1",
        stage_before="2-3",
        stage_after="2-3",
        gold_before=10,
        gold_after=9,
        gold_delta=-1,
        level_before=4,
        level_after=4,
        board_before=4,
        board_after=4,
        bench_before=2,
        bench_after=3,
        action_ids=("a1",),
    )
    ledger = EconomyLedgerWindow(
        window_index=0,
        match_id="m",
        start_timestamp_s=0,
        end_timestamp_s=10,
        start_evidence_id="e0",
        end_evidence_id="e1",
        observed_gold_delta=-1,
        observed_spend=1,
        required_action_spend_min=1,
        required_action_spend_max=1,
        action_spend_min=1,
        action_spend_max=1,
        compatible_action_spend_min=1,
        compatible_action_spend_max=1,
        feasible=True,
        spend_deficit_min=0,
        spend_deficit_max=0,
        unallocated_spend_min=0,
        unallocated_spend_max=0,
        status="fully_explained",
    )

    actions_path = actions_dir / "semantic-action-fusion-0.14.6.jsonl"
    windows_path = actions_dir / "semantic-action-fusion-0.14.6_windows.jsonl"
    ledger_path = actions_dir / "semantic-action-fusion-0.14.6_ledger.jsonl"
    summary_path = actions_dir / "semantic-action-fusion-0.14.6_summary.json"
    write_jsonl(actions_path, [action])
    write_jsonl(windows_path, [window])
    write_jsonl(ledger_path, [ledger])
    summary_path.write_text(
        json.dumps(
            {
                "producer_version": "semantic-action-fusion-0.14.6",
                "actions_path": str(actions_path),
                "windows_path": str(windows_path),
                "ledger_path": str(ledger_path),
            }
        ),
        encoding="utf-8",
    )

    result = build_match_decision_episodes(
        match,
        DecisionEpisodeSettings(),
        action_summary_path=summary_path,
    )

    assert result["episode_count"] == 1
    assert result["covered_action_count"] == 1
    assert result["uncovered_action_count"] == 0
    assert result["action_coverage_ratio"] == 1.0
    assert Path(result["episodes_path"]).exists()
    assert Path(result["summary_path"]).exists()
