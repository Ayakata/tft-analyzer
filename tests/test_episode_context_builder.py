from tft_analyzer.core.enums import DecisionType
from tft_analyzer.core.models.decisions import (
    DecisionBoundaryState,
    DecisionEconomySummary,
    DecisionEpisode,
)
from tft_analyzer.core.models.tracking import (
    TrackedField,
    TrackedHUDState,
)
from tft_analyzer.features import (
    EpisodeContextSettings,
    build_episode_player_context,
)
from tft_analyzer.tracking.board.models import (
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)


def field(value, *, status="observed", confidence=0.95, evidence="e0", t=0.0):
    return TrackedField(
        value=value,
        confidence=confidence,
        source_observation_id=f"o-{evidence}",
        source_evidence_id=evidence,
        source_timestamp_s=t,
        age_s=0.0,
        status=status,
    )


def hud(evidence, t, *, hp, gold, level, xp, stage="4-2"):
    s, r = stage.split("-")
    return TrackedHUDState(
        state_id=f"h-{evidence}",
        match_id="m",
        timestamp_s=t,
        evidence_id=evidence,
        stage=field({"stage": int(s), "round": int(r)}, evidence=evidence, t=t),
        gold=field({"gold": gold}, evidence=evidence, t=t),
        level=field({"level": level}, evidence=evidence, t=t),
        xp=field({"current": xp, "required": 36}, evidence=evidence, t=t),
        hp=field({"hp": hp}, evidence=evidence, t=t),
        shop=TrackedField(),
        tracker_version="hud-state-tracker-test",
    )


def board(evidence, t, *, count, level, scene=True):
    return TrackedBoardOccupancyState(
        match_id="m",
        timestamp_s=t,
        evidence_id=evidence,
        usable=True,
        stability="stable",
        gate_reason="stable",
        motion_count=0,
        candidate_change_count=0,
        uncertain_count=0,
        candidate_occupied_count=count,
        occupied_count=count,
        hud_level=level,
        hud_stage="4-2",
        capacity_status=("at" if count == level else "under"),
        strong_snapshot=True,
        inferred_empty_count=0,
        scene_valid=scene,
        scene_score=0.02,
        scene_anchor_pass_count=4,
        cells=(),
        tracker_version="board-test",
    )


def bench(evidence, t, *, count):
    return TrackedBenchOccupancyState(
        match_id="m",
        timestamp_s=t,
        evidence_id=evidence,
        uncertain_count=0,
        occupied_count=count,
        slots=(),
        tracker_version="bench-test",
    )


def episode():
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
            level=7,
            xp_absolute=132,
            board_count=7,
            bench_count=4,
        ),
        economy=DecisionEconomySummary(
            observed_spend_total=20,
            unallocated_spend_min=0,
            unallocated_spend_max=0,
        ),
        confidence=0.8,
        extractor_version="decision-episode-builder-test",
    )


def test_context_joins_exact_evidence_and_exposes_hp_board_utilization():
    ep = episode()
    result = build_episode_player_context(
        ep,
        hud_by_evidence={
            "e0": hud("e0", 0.0, hp=35, gold=40, level=6, xp=10),
            "e1": hud("e1", 10.0, hp=28, gold=20, level=7, xp=6),
        },
        board_by_evidence={
            "e0": board("e0", 0.0, count=6, level=6),
            "e1": board("e1", 10.0, count=7, level=7),
        },
        bench_by_evidence={
            "e0": bench("e0", 0.0, count=3),
            "e1": bench("e1", 10.0, count=4),
        },
        settings=EpisodeContextSettings(),
    )

    assert result.before.hp == 35
    assert result.after.hp == 28
    assert result.delta.hp == -7
    assert result.before.board_capacity == 6
    assert result.before.board_utilization == 1.0
    assert result.after.board_utilization == 1.0
    assert result.delta.level == 1
    assert result.delta.xp_absolute == 32
    assert result.quality.before_exact_alignment is True
    assert result.quality.after_exact_alignment is True
    assert result.quality.scene_valid_before is True
    assert result.before.hud_fields["hp"].status == "observed"


def test_missing_tracker_boundary_falls_back_without_inventing_hp():
    ep = episode()
    result = build_episode_player_context(
        ep,
        hud_by_evidence={
            "e0": hud("e0", 0.0, hp=35, gold=40, level=6, xp=10),
        },
        board_by_evidence={
            "e0": board("e0", 0.0, count=6, level=6),
        },
        bench_by_evidence={
            "e0": bench("e0", 0.0, count=3),
        },
        settings=EpisodeContextSettings(),
    )

    assert result.before.source_alignment == "exact_evidence"
    assert result.after.source_alignment == "episode_boundary_fallback"
    assert result.after.hp is None
    assert result.after.gold == 20
    assert result.after.level == 7
    assert result.after.board_count == 7
    assert result.quality.after_exact_alignment is False
    assert "hp" in result.quality.missing_after_fields


def test_economy_uncertainty_propagates_as_context_quality_not_player_grade():
    ep = episode().model_copy(
        update={
            "economy": DecisionEconomySummary(
                observed_spend_total=20,
                unallocated_spend_min=1,
                unallocated_spend_max=5,
            )
        }
    )
    result = build_episode_player_context(
        ep,
        hud_by_evidence={},
        board_by_evidence={},
        bench_by_evidence={},
        settings=EpisodeContextSettings(),
    )
    assert result.quality.economy_feasible is True
    assert result.quality.reconstruction_uncertainty is True



def test_strong_board_boundary_is_strategy_usable_exact():
    ep = episode()
    result = build_episode_player_context(
        ep,
        hud_by_evidence={
            "e0": hud("e0", 0.0, hp=35, gold=40, level=6, xp=10),
            "e1": hud("e1", 10.0, hp=28, gold=20, level=7, xp=6),
        },
        board_by_evidence={
            "e0": board("e0", 0.0, count=6, level=6),
            "e1": board("e1", 10.0, count=7, level=7),
        },
        bench_by_evidence={
            "e0": bench("e0", 0.0, count=3),
            "e1": bench("e1", 10.0, count=4),
        },
        settings=EpisodeContextSettings(),
    )

    assert result.feature_trust.before.board_count.semantics == "exact"
    assert result.feature_trust.before.board_count.usable_for_strategy is True
    assert result.feature_trust.after.board_utilization.semantics == "exact"
    assert (
        result.feature_trust.boundary_gold_delta_semantics
        == "observed_state_delta_not_action_accounting"
    )
    assert (
        result.feature_trust.economy_source_for_action_spend
        == "episode_economy"
    )


def test_non_strong_board_count_is_lower_bound_not_literal_exact():
    ep = episode()

    weak_before = board("e0", 0.0, count=4, level=6).model_copy(
        update={
            "strong_snapshot": False,
            "gate_reason": "canonical_carry",
        }
    )
    weak_after = board("e1", 10.0, count=4, level=7).model_copy(
        update={
            "strong_snapshot": False,
            "gate_reason": "stable",
        }
    )

    result = build_episode_player_context(
        ep,
        hud_by_evidence={
            "e0": hud("e0", 0.0, hp=35, gold=40, level=6, xp=10),
            "e1": hud("e1", 10.0, hp=28, gold=20, level=7, xp=6),
        },
        board_by_evidence={
            "e0": weak_before,
            "e1": weak_after,
        },
        bench_by_evidence={
            "e0": bench("e0", 0.0, count=3),
            "e1": bench("e1", 10.0, count=4),
        },
        settings=EpisodeContextSettings(),
    )

    assert result.before.board_count == 4
    assert result.before.board_utilization == 4 / 6
    assert result.feature_trust.before.board_count.semantics == "carried"
    assert result.feature_trust.after.board_count.semantics == "lower_bound"
    assert (
        result.feature_trust.before.board_utilization.usable_for_strategy
        is False
    )


def test_scene_invalid_board_is_unusable_even_when_evidence_aligned():
    ep = episode()
    invalid = board(
        "e0",
        0.0,
        count=4,
        level=6,
        scene=False,
    )

    result = build_episode_player_context(
        ep,
        hud_by_evidence={
            "e0": hud("e0", 0.0, hp=35, gold=40, level=6, xp=10),
        },
        board_by_evidence={"e0": invalid},
        bench_by_evidence={
            "e0": bench("e0", 0.0, count=3),
        },
        settings=EpisodeContextSettings(),
    )

    assert result.quality.before_exact_alignment is True
    assert result.feature_trust.before.board_count.semantics == "unusable"
    assert (
        result.feature_trust.before.board_count.usable_for_strategy
        is False
    )
