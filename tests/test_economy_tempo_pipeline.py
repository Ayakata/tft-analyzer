import json
from pathlib import Path

from tft_analyzer.actions.models import InferredAction
from tft_analyzer.analyzers.economy_tempo import (
    EconomyTempoAnalyzerSettings,
    analyze_match_episodes,
)
from tft_analyzer.core.enums import ActionType, DecisionType
from tft_analyzer.core.models.decisions import (
    DecisionBoundaryState,
    DecisionEconomySummary,
    DecisionEpisode,
    DecisionSamplingSummary,
)


def write_jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for value in values:
            f.write(value.model_dump_json() + "\n")


def test_pipeline_writes_findings_and_zero_decision_grades(tmp_path):
    match = tmp_path / "match"
    decisions = match / "decisions"
    actions_dir = match / "actions"
    decisions.mkdir(parents=True)
    actions_dir.mkdir(parents=True)

    action = InferredAction(
        action_id="a1",
        match_id="m",
        action_type=ActionType.PURCHASE_XP,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        confidence=0.9,
        quality="strong",
        params={"count": 1},
        signals={},
        evidence_ids=("e0", "e1"),
        producer_version="semantic-action-fusion-test",
    )
    action_path = actions_dir / "semantic-action-fusion-test.jsonl"
    write_jsonl(action_path, [action])

    ep = DecisionEpisode(
        decision_id="d1",
        match_id="m",
        decision_type=DecisionType.OTHER,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        state_before_id="e0",
        state_after_id="e1",
        stage_start="3-5",
        stage_end="3-5",
        window_indices=(1,),
        action_ids=("a1",),
        state_before=DecisionBoundaryState(
            timestamp_s=0.0, evidence_id="e0", stage="3-5", gold=10, level=5,
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=10.0, evidence_id="e1", stage="3-5", gold=6, level=5,
        ),
        economy=DecisionEconomySummary(
            observed_spend_total=4,
            required_action_spend_min=4,
            required_action_spend_max=4,
            compatible_action_spend_min=4,
            compatible_action_spend_max=4,
        ),
        sampling=DecisionSamplingSummary(source_window_count=1, span_seconds=10.0),
        confidence=0.9,
        extractor_version="decision-episode-builder-0.15.0",
    )
    episode_path = decisions / "decision-episode-builder-0.15.0.jsonl"
    write_jsonl(episode_path, [ep])

    action_summary_path = actions_dir / "semantic-action-fusion-test_summary.json"
    action_summary_path.write_text(
        json.dumps({
            "producer_version": "semantic-action-fusion-test",
            "game_data": {"set_id": "TFT17", "patch": "16.16", "version": "16.16.1"},
        }),
        encoding="utf-8",
    )

    episode_summary = decisions / "decision-episode-builder-0.15.0_summary.json"
    episode_summary.write_text(
        json.dumps({
            "producer_version": "decision-episode-builder-0.15.0",
            "episodes_path": str(episode_path),
            "input_actions_path": str(action_path),
            "input_action_summary_path": str(action_summary_path),
            "ordering_policy": "window_partial_order",
        }),
        encoding="utf-8",
    )

    summary = analyze_match_episodes(
        match,
        EconomyTempoAnalyzerSettings(),
    )

    assert summary["finding_count"] >= 1
    assert summary["decision_grade_count"] == 0
    assert summary["hard_data_quality_episode_count"] == 0
    assert summary["data_quality_episode_count"] == 0
    assert summary["reconstruction_uncertainty_episode_count"] == 0
    assert summary["game_context"]["set_id"] == "TFT17"
    assert Path(summary["findings_path"]).exists()
    assert Path(summary["summary_path"]).exists()



def test_pipeline_separates_hard_conflict_from_sparse_uncertainty(tmp_path):
    match = tmp_path / "match2"
    decisions = match / "decisions"
    actions_dir = match / "actions"
    decisions.mkdir(parents=True)
    actions_dir.mkdir(parents=True)

    action = InferredAction(
        action_id="a1",
        match_id="m",
        action_type=ActionType.UNKNOWN_ECON_ACTION,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        confidence=0.8,
        quality="supported",
        params={},
        signals={},
        evidence_ids=("e0", "e1"),
        producer_version="semantic-action-fusion-test",
    )
    action_path = actions_dir / "semantic-action-fusion-test.jsonl"
    write_jsonl(action_path, [action])

    ep = DecisionEpisode(
        decision_id="d1",
        match_id="m",
        decision_type=DecisionType.OTHER,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        state_before_id="e0",
        state_after_id="e1",
        stage_start="4-1",
        stage_end="4-1",
        window_indices=(1,),
        action_ids=("a1",),
        state_before=DecisionBoundaryState(
            timestamp_s=0.0, evidence_id="e0", stage="4-1", gold=17, level=6,
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=10.0, evidence_id="e1", stage="4-1", gold=1, level=6,
        ),
        economy=DecisionEconomySummary(
            observed_spend_total=16,
            required_action_spend_min=0,
            required_action_spend_max=0,
            compatible_action_spend_min=0,
            compatible_action_spend_max=0,
            unallocated_spend_min=16,
            unallocated_spend_max=16,
            infeasible_window_count=0,
            spend_deficit_min_total=0,
        ),
        sampling=DecisionSamplingSummary(source_window_count=1, span_seconds=10.0),
        confidence=0.8,
        extractor_version="decision-episode-builder-0.15.0",
    )
    episode_path = decisions / "decision-episode-builder-0.15.0.jsonl"
    write_jsonl(episode_path, [ep])

    episode_summary = decisions / "decision-episode-builder-0.15.0_summary.json"
    episode_summary.write_text(
        json.dumps({
            "producer_version": "decision-episode-builder-0.15.0",
            "episodes_path": str(episode_path),
            "input_actions_path": str(action_path),
            "ordering_policy": "window_partial_order",
        }),
        encoding="utf-8",
    )

    summary = analyze_match_episodes(match, EconomyTempoAnalyzerSettings())
    assert summary["hard_data_quality_episode_count"] == 0
    assert summary["reconstruction_uncertainty_episode_count"] == 1
    assert summary["interpretation_counts"]["reconstruction_uncertainty"] == 1
