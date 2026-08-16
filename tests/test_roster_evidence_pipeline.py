import json
from pathlib import Path

from tft_analyzer.actions.models import (
    ActionInferenceQuality,
    InferredAction,
)
from tft_analyzer.core.enums import (
    ActionType,
    DecisionType,
)
from tft_analyzer.core.models.decisions import (
    DecisionBoundaryState,
    DecisionEpisode,
)
from tft_analyzer.features.roster_evidence import (
    RosterEvidenceSettings,
    build_match_roster_evidence,
)


def write_jsonl(path, values):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        for value in values:
            f.write(
                value.model_dump_json()
                + "\n"
            )


def buy(
    action_id,
    champions,
    *,
    confidence=0.9,
    cost_validation="cost_consistent",
):
    return InferredAction(
        action_id=action_id,
        match_id="m",
        action_type=ActionType.BUY_UNIT,
        start_timestamp_s=0.0,
        end_timestamp_s=1.0,
        confidence=confidence,
        quality=(
            ActionInferenceQuality.SUPPORTED
            if confidence >= 0.65
            else ActionInferenceQuality.AMBIGUOUS
        ),
        params={
            "count": len(champions),
            "champions": champions,
            "cost_validation": cost_validation,
        },
        producer_version="semantic-action-fusion-0.14.6",
    )


def decision(action_ids):
    return DecisionEpisode(
        decision_id="d1",
        match_id="m",
        decision_type=DecisionType.OTHER,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        state_before_id="e0",
        state_after_id="e1",
        stage_start="4-2",
        stage_end="4-2",
        action_ids=tuple(action_ids),
        state_before=DecisionBoundaryState(
            timestamp_s=0.0,
            evidence_id="e0",
            stage="4-2",
            gold=40,
            level=6,
            xp_absolute=100,
            board_count=6,
            bench_count=3,
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=10.0,
            evidence_id="e1",
            stage="4-2",
            gold=20,
            level=6,
            xp_absolute=104,
            board_count=6,
            bench_count=3,
        ),
        extractor_version="decision-episode-builder-0.15.0",
    )


def test_pipeline_builds_final_lower_bounds_and_game_context(tmp_path):
    match = tmp_path / "match"
    decisions_dir = match / "decisions"
    actions_dir = match / "actions"
    decisions_dir.mkdir(parents=True)
    actions_dir.mkdir()

    actions = [
        buy(
            "b1",
            ["Rhaast", "Rhaast", "Briar"],
        ),
        buy(
            "b2",
            ["Zoe"],
            confidence=0.45,
            cost_validation="cost_conflict",
        ),
    ]
    actions_path = (
        actions_dir
        / "semantic-action-fusion-0.14.6.jsonl"
    )
    write_jsonl(
        actions_path,
        actions,
    )

    action_summary_path = (
        actions_dir
        / "semantic-action-fusion-0.14.6_summary.json"
    )
    action_summary_path.write_text(
        json.dumps(
            {
                "producer_version": "semantic-action-fusion-0.14.6",
                "actions_path": str(actions_path),
                "game_data": {
                    "set_id": "TFT17",
                    "patch": "16.16",
                    "version": "16.16.1",
                },
            }
        ),
        encoding="utf-8",
    )

    episodes_path = (
        decisions_dir
        / "decision-episode-builder-0.15.0.jsonl"
    )
    write_jsonl(
        episodes_path,
        [decision(["b1", "b2"])],
    )

    episode_summary_path = (
        decisions_dir
        / "decision-episode-builder-0.15.0_summary.json"
    )
    episode_summary_path.write_text(
        json.dumps(
            {
                "producer_version": "decision-episode-builder-0.15.0",
                "input_action_summary_path": str(action_summary_path),
                "input_action_producer_version": "semantic-action-fusion-0.14.6",
                "input_actions_path": str(actions_path),
                "episodes_path": str(episodes_path),
            }
        ),
        encoding="utf-8",
    )

    summary = build_match_roster_evidence(
        match,
        RosterEvidenceSettings(),
        episode_summary_path=episode_summary_path,
    )

    assert summary["context_count"] == 1
    assert summary["roster_relevant_action_count"] == 2
    assert summary["covered_roster_relevant_action_count"] == 2
    assert summary["confirmed_identity_buy_copy_count"] == 3
    assert summary["candidate_identity_buy_copy_count"] == 1
    assert summary["confirmed_buy_identity_coverage"] == 0.75
    assert summary[
        "final_confirmed_acquisition_copy_lower_bounds"
    ] == {
        "briar": 1,
        "rhaast": 2,
    }
    assert summary["final_candidate_acquisitions"] == {
        "zoe": 1,
    }
    assert summary["game_context"]["set_id"] == "TFT17"
    assert summary["game_context"]["patch"] == "16.16"
    assert summary["acquisition_semantics"] == "confirmed_history_lower_bound"
    assert summary["current_ownership_status"] == "not_established"
    assert summary["complete_sell_history_known"] is False
    assert Path(summary["contexts_path"]).exists()
    assert Path(summary["summary_path"]).exists()
