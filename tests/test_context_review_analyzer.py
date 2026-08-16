from tft_analyzer.actions.models import (
    ActionInferenceQuality,
    InferredAction,
)
from tft_analyzer.analyzers.context_review import (
    ContextReviewAnalyzerSettings,
    analyze_context_episode,
)
from tft_analyzer.core.enums import ActionType, DecisionType
from tft_analyzer.core.models.decisions import (
    DecisionBoundaryState,
    DecisionEconomySummary,
    DecisionEpisode,
)
from tft_analyzer.features.episode_context.models import (
    EpisodeBoundaryTrust,
    EpisodeContextFeatureTrust,
    EpisodeContextQuality,
    EpisodeFeatureTrust,
    EpisodePlayerContext,
    EpisodePlayerStateDelta,
    EpisodePlayerStateFeature,
)


def trust(
    *,
    semantics="exact",
    usable=True,
    known=True,
    reason="test",
    source="test",
):
    return EpisodeFeatureTrust(
        known=known,
        semantics=semantics,
        usable_for_strategy=usable,
        reason=reason,
        source=source,
    )


def boundary_trust(
    *,
    board_semantics="lower_bound",
    board_usable=False,
):
    exact = trust()
    board = trust(
        semantics=board_semantics,
        usable=board_usable,
    )
    return EpisodeBoundaryTrust(
        hp=exact,
        gold=exact,
        level=exact,
        xp_absolute=exact,
        board_count=board,
        board_utilization=board,
        bench_count=trust(
            semantics="lower_bound",
            usable=False,
        ),
    )


def make_context(
    *,
    hp=17,
    gold_before=42,
    gold_after=32,
    level_before=8,
    level_after=8,
    board_before=5,
    board_after=5,
    board_capacity_after=8,
    board_after_semantics="lower_bound",
    board_after_usable=False,
    economy_feasible=True,
):
    before = EpisodePlayerStateFeature(
        timestamp_s=0.0,
        evidence_id="e0",
        stage="5-6",
        hp=hp,
        gold=gold_before,
        level=level_before,
        xp_absolute=140,
        board_count=board_before,
        board_capacity=level_before,
        board_utilization=(
            board_before / level_before
        ),
        bench_count=7,
        board_scene_valid=True,
    )
    after = EpisodePlayerStateFeature(
        timestamp_s=10.0,
        evidence_id="e1",
        stage="5-6",
        hp=hp,
        gold=gold_after,
        level=level_after,
        xp_absolute=142,
        board_count=board_after,
        board_capacity=board_capacity_after,
        board_utilization=(
            board_after / board_capacity_after
        ),
        bench_count=7,
        board_scene_valid=True,
    )

    before_trust = boundary_trust()
    after_trust = boundary_trust(
        board_semantics=board_after_semantics,
        board_usable=board_after_usable,
    )

    return EpisodePlayerContext(
        context_id="c1",
        decision_id="d1",
        match_id="m",
        stage_start="5-6",
        stage_end="5-6",
        before=before,
        after=after,
        delta=EpisodePlayerStateDelta(
            hp=0,
            gold=gold_after - gold_before,
            level=level_after - level_before,
            xp_absolute=2,
            board_count=board_after - board_before,
            bench_count=0,
        ),
        quality=EpisodeContextQuality(
            before_exact_alignment=True,
            after_exact_alignment=True,
            hp_known_before=True,
            hp_known_after=True,
            board_known_before=True,
            board_known_after=True,
            bench_known_before=True,
            bench_known_after=True,
            board_utilization_known_before=True,
            board_utilization_known_after=True,
            scene_valid_before=True,
            scene_valid_after=True,
            economy_feasible=economy_feasible,
            reconstruction_uncertainty=True,
        ),
        feature_trust=EpisodeContextFeatureTrust(
            before=before_trust,
            after=after_trust,
        ),
        source_episode_producer_version="decision-episode-builder-0.15.0",
        producer_version="episode-context-builder-0.17.1",
    )


def make_episode(
    *,
    spend=10,
    infeasible=False,
    level_before=8,
    level_after=8,
    action_ids=("a-roll",),
):
    return DecisionEpisode(
        decision_id="d1",
        match_id="m",
        decision_type=DecisionType.OTHER,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        state_before_id="e0",
        state_after_id="e1",
        stage_start="5-6",
        stage_end="5-6",
        action_ids=action_ids,
        state_before=DecisionBoundaryState(
            timestamp_s=0.0,
            evidence_id="e0",
            stage="5-6",
            gold=42,
            level=level_before,
            xp_absolute=140,
            board_count=5,
            bench_count=7,
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=10.0,
            evidence_id="e1",
            stage="5-6",
            gold=32,
            level=level_after,
            xp_absolute=142,
            board_count=5,
            bench_count=7,
        ),
        economy=DecisionEconomySummary(
            observed_spend_total=spend,
            required_action_spend_min=2,
            required_action_spend_max=spend,
            compatible_action_spend_min=2,
            compatible_action_spend_max=spend,
            unallocated_spend_min=0,
            unallocated_spend_max=max(0, spend - 2),
            infeasible_window_count=1 if infeasible else 0,
            spend_deficit_min_total=1 if infeasible else 0,
        ),
        confidence=0.84,
        extractor_version="decision-episode-builder-0.15.0",
    )


def roll_action():
    return InferredAction(
        action_id="a-roll",
        match_id="m",
        action_type=ActionType.REFRESH_SHOP,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        confidence=0.84,
        quality=ActionInferenceQuality.SUPPORTED,
        params={
            "count_min": 1,
            "count_max": 5,
        },
        producer_version="semantic-action-fusion-0.14.6",
    )


def xp_action():
    return InferredAction(
        action_id="a-xp",
        match_id="m",
        action_type=ActionType.PURCHASE_XP,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        confidence=0.95,
        quality=ActionInferenceQuality.STRONG,
        params={"count": 2},
        producer_version="semantic-action-fusion-0.14.6",
    )


def test_low_hp_roll_and_gold_pressure_are_review_candidates_not_grades():
    episode = make_episode(spend=10)
    context = make_context(
        hp=17,
        gold_before=42,
        gold_after=32,
    )

    findings, stats = analyze_context_episode(
        episode,
        context,
        {"a-roll": roll_action()},
        ContextReviewAnalyzerSettings(),
    )
    codes = {item.finding_code for item in findings}

    assert "economy_commitment_under_pressure" in codes
    assert "low_hp_roll_activity" in codes
    assert "high_gold_under_pressure" in codes
    assert all(
        item.interpretation == "review_candidate"
        for item in findings
    )
    assert all(
        item.interpretation != "decision_grade"
        for item in findings
    )
    assert stats["strategic_episode_blocked_infeasible"] == 0


def test_low_hp_level_up_is_context_review_landmark():
    episode = make_episode(
        spend=13,
        level_before=7,
        level_after=8,
        action_ids=("a-xp", "a-roll"),
    )
    context = make_context(
        hp=17,
        gold_before=33,
        gold_after=20,
        level_before=7,
        level_after=8,
        board_before=7,
        board_after=7,
        board_capacity_after=8,
    )

    findings, _ = analyze_context_episode(
        episode,
        context,
        {
            "a-xp": xp_action(),
            "a-roll": roll_action(),
        },
        ContextReviewAnalyzerSettings(),
    )
    codes = {item.finding_code for item in findings}

    assert "low_hp_level_up" in codes
    assert "low_hp_roll_activity" in codes
    assert "economy_commitment_under_pressure" in codes


def test_infeasible_economy_hard_blocks_strategic_findings():
    episode = make_episode(
        spend=1,
        infeasible=True,
    )
    context = make_context(
        hp=17,
        gold_before=42,
        gold_after=41,
        economy_feasible=False,
    )

    findings, stats = analyze_context_episode(
        episode,
        context,
        {"a-roll": roll_action()},
        ContextReviewAnalyzerSettings(),
    )

    assert [item.finding_code for item in findings] == [
        "context_review_blocked_infeasible"
    ]
    assert findings[0].interpretation == "data_quality"
    assert stats["strategic_episode_blocked_infeasible"] == 1


def test_lower_bound_board_is_never_used_for_capacity_review():
    episode = make_episode(spend=0, action_ids=())
    context = make_context(
        hp=48,
        gold_before=50,
        gold_after=50,
        board_before=4,
        board_after=4,
        board_capacity_after=7,
        board_after_semantics="lower_bound",
        board_after_usable=False,
    )

    findings, stats = analyze_context_episode(
        episode,
        context,
        {},
        ContextReviewAnalyzerSettings(),
    )

    assert "trusted_board_below_capacity" not in {
        item.finding_code
        for item in findings
    }
    assert stats["board_rule_eligible"] == 0
    assert stats["board_rule_skipped_untrusted"] == 1


def test_exact_trusted_board_can_enable_capacity_review():
    episode = make_episode(spend=0, action_ids=())
    context = make_context(
        hp=48,
        gold_before=50,
        gold_after=50,
        board_before=6,
        board_after=6,
        board_capacity_after=7,
        board_after_semantics="exact",
        board_after_usable=True,
    )

    findings, stats = analyze_context_episode(
        episode,
        context,
        {},
        ContextReviewAnalyzerSettings(),
    )

    assert "trusted_board_below_capacity" in {
        item.finding_code
        for item in findings
    }
    assert stats["board_rule_eligible"] == 1


def test_near_elimination_activity_is_review_candidate():
    episode = make_episode(
        spend=0,
        action_ids=("a-roll",),
    )
    context = make_context(
        hp=6,
        gold_before=42,
        gold_after=42,
    )

    findings, _ = analyze_context_episode(
        episode,
        context,
        {"a-roll": roll_action()},
        ContextReviewAnalyzerSettings(),
    )

    by_code = {
        item.finding_code: item
        for item in findings
    }
    assert "near_elimination_activity" in by_code
    assert (
        by_code["near_elimination_activity"].interpretation
        == "review_candidate"
    )
