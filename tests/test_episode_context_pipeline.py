import json
from pathlib import Path

from tft_analyzer.core.enums import DecisionType
from tft_analyzer.core.models.decisions import (
    DecisionBoundaryState,
    DecisionEpisode,
)
from tft_analyzer.core.models.tracking import TrackedField, TrackedHUDState
from tft_analyzer.features import (
    EpisodeContextSettings,
    build_match_episode_context,
)
from tft_analyzer.tracking.board.models import (
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)


def write_jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for value in values:
            f.write(value.model_dump_json() + "\n")


def tf(value, evidence, t):
    return TrackedField(
        value=value,
        confidence=0.95,
        source_observation_id="o",
        source_evidence_id=evidence,
        source_timestamp_s=t,
        age_s=0.0,
        status="observed",
    )


def make_hud(evidence, t, hp, gold):
    return TrackedHUDState(
        state_id=f"h-{evidence}", match_id="m", timestamp_s=t, evidence_id=evidence,
        stage=tf({"stage": 4, "round": 2}, evidence, t),
        gold=tf({"gold": gold}, evidence, t),
        level=tf({"level": 6}, evidence, t),
        xp=tf({"current": 10, "required": 36}, evidence, t),
        hp=tf({"hp": hp}, evidence, t), shop=TrackedField(),
        tracker_version="hud-test",
    )


def make_board(evidence, t):
    return TrackedBoardOccupancyState(
        match_id="m", timestamp_s=t, evidence_id=evidence,
        usable=True, stability="stable", gate_reason="stable", motion_count=0,
        candidate_change_count=0, uncertain_count=0, candidate_occupied_count=6,
        occupied_count=6, hud_level=6, hud_stage="4-2", capacity_status="at",
        strong_snapshot=True, inferred_empty_count=0, scene_valid=True,
        scene_score=0.02, scene_anchor_pass_count=4, cells=(), tracker_version="board-test",
    )


def make_bench(evidence, t):
    return TrackedBenchOccupancyState(
        match_id="m", timestamp_s=t, evidence_id=evidence,
        uncertain_count=0, occupied_count=3, slots=(), tracker_version="bench-test",
    )


def test_pipeline_resolves_tracking_inputs_from_action_summary(tmp_path):
    match = tmp_path / "match"
    decisions = match / "decisions"
    actions = match / "actions"
    tracking = match / "tracking"
    decisions.mkdir(parents=True)
    actions.mkdir()
    tracking.mkdir()

    ep = DecisionEpisode(
        decision_id="d1", match_id="m", decision_type=DecisionType.OTHER,
        start_timestamp_s=0.0, end_timestamp_s=10.0,
        state_before_id="e0", state_after_id="e1", stage_start="4-2", stage_end="4-2",
        state_before=DecisionBoundaryState(
            timestamp_s=0.0, evidence_id="e0", stage="4-2", gold=40,
            level=6, xp_absolute=100, board_count=6, bench_count=3,
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=10.0, evidence_id="e1", stage="4-2", gold=20,
            level=6, xp_absolute=104, board_count=6, bench_count=3,
        ),
        confidence=0.8,
        extractor_version="decision-episode-builder-0.15.0",
    )
    episodes_path = decisions / "decision-episode-builder-0.15.0.jsonl"
    write_jsonl(episodes_path, [ep])

    hud_path = tracking / "hud-state-tracker-0.10.0.jsonl"
    board_path = tracking / "board-occupancy-tracker-0.13.5.jsonl"
    bench_path = tracking / "bench-occupancy-tracker-0.13.5.jsonl"
    write_jsonl(hud_path, [make_hud("e0", 0.0, 35, 40), make_hud("e1", 10.0, 28, 20)])
    write_jsonl(board_path, [make_board("e0", 0.0), make_board("e1", 10.0)])
    write_jsonl(bench_path, [make_bench("e0", 0.0), make_bench("e1", 10.0)])

    action_summary_path = actions / "semantic-action-fusion-0.14.6_summary.json"
    action_summary_path.write_text(
        json.dumps({
            "input_hud_states_path": str(hud_path),
            "input_board_states_path": str(board_path),
            "input_bench_states_path": str(bench_path),
        }),
        encoding="utf-8",
    )
    episode_summary_path = decisions / "decision-episode-builder-0.15.0_summary.json"
    episode_summary_path.write_text(
        json.dumps({
            "producer_version": "decision-episode-builder-0.15.0",
            "episodes_path": str(episodes_path),
            "input_action_summary_path": str(action_summary_path),
        }),
        encoding="utf-8",
    )

    summary = build_match_episode_context(
        match,
        EpisodeContextSettings(),
        episode_summary_path=episode_summary_path,
    )

    assert summary["context_count"] == 1
    assert summary["fully_exact_context_count"] == 1
    assert summary["hp_known_both_count"] == 1
    assert summary["board_utilization_known_both_count"] == 1
    assert summary["trust_semantics_version"] == 1
    assert summary["hp_strategy_usable_both_count"] == 1
    assert summary["board_exact_both_count"] == 1
    assert summary["board_strategy_usable_both_count"] == 1
    assert summary["boundary_gold_delta_semantics"] == (
        "observed_state_delta_not_action_accounting"
    )
    assert summary["economy_source_for_action_spend"] == "episode_economy"
    assert Path(summary["contexts_path"]).exists()
    assert Path(summary["summary_path"]).exists()
