from tft_analyzer.actions.models import InferredAction
from tft_analyzer.analyzers.economy_tempo import (
    EconomyTempoAnalyzerSettings,
    analyze_episode,
)
from tft_analyzer.core.enums import ActionType, DecisionType
from tft_analyzer.core.models.decisions import (
    DecisionActionGroup,
    DecisionBoundaryState,
    DecisionEconomySummary,
    DecisionEpisode,
    DecisionSamplingSummary,
)


def action(action_id, action_type, **params):
    return InferredAction(
        action_id=action_id,
        match_id="m",
        action_type=action_type,
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        confidence=0.8,
        quality="supported",
        params=params,
        signals={},
        evidence_ids=("e0", "e1"),
        producer_version="semantic-action-fusion-test",
    )


def episode(
    *,
    action_ids,
    before_gold=30,
    after_gold=10,
    before_level=6,
    after_level=6,
    spend=20,
    req_min=20,
    req_max=20,
    umin=0,
    umax=0,
    infeasible=0,
    deficit=0,
):
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
        window_indices=(1,),
        action_ids=tuple(action_ids),
        action_groups=(
            DecisionActionGroup(
                group_index=0,
                window_index=1,
                start_timestamp_s=0.0,
                end_timestamp_s=10.0,
                action_ids=tuple(action_ids),
                action_types=(),
                evidence_ids=("e0", "e1"),
            ),
        ),
        state_before=DecisionBoundaryState(
            timestamp_s=0.0,
            evidence_id="e0",
            stage="4-2",
            gold=before_gold,
            level=before_level,
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=10.0,
            evidence_id="e1",
            stage="4-2",
            gold=after_gold,
            level=after_level,
        ),
        economy=DecisionEconomySummary(
            observed_spend_total=spend,
            required_action_spend_min=req_min,
            required_action_spend_max=req_max,
            compatible_action_spend_min=(0 if infeasible else req_min),
            compatible_action_spend_max=(0 if infeasible else req_max),
            unallocated_spend_min=umin,
            unallocated_spend_max=umax,
            infeasible_window_count=infeasible,
            spend_deficit_min_total=deficit,
        ),
        sampling=DecisionSamplingSummary(
            source_window_count=1,
            span_seconds=10.0,
            max_source_window_seconds=10.0,
        ),
        confidence=0.8,
        extractor_version="decision-episode-builder-test",
    )


def codes(findings):
    return {item.finding_code for item in findings}


def test_infeasible_is_data_quality_not_decision_grade():
    ep = episode(
        action_ids=("buy",),
        spend=1,
        req_min=2,
        req_max=2,
        infeasible=1,
        deficit=1,
    )
    actions = {
        "buy": action(
            "buy",
            ActionType.BUY_UNIT,
            count=1,
            total_gold_cost=2,
            cost_validation="cost_conflict",
        )
    }
    findings = analyze_episode(
        ep,
        actions,
        EconomyTempoAnalyzerSettings(),
    )
    item = next(x for x in findings if x.finding_code == "economy_infeasible")
    assert item.interpretation == "data_quality"
    assert item.category == "data_quality.hard_conflict.economy"
    assert item.severity == "major"
    assert all(x.interpretation != "decision_grade" for x in findings)


def test_unresolved_economy_spend_is_reconstruction_uncertainty():
    ep = episode(
        action_ids=("roll",),
        spend=16,
        req_min=0,
        req_max=0,
        umin=16,
        umax=16,
    )
    findings = analyze_episode(
        ep,
        {"roll": action("roll", ActionType.UNKNOWN_ECON_ACTION)},
        EconomyTempoAnalyzerSettings(),
    )
    item = next(
        x for x in findings
        if x.finding_code == "unresolved_economy_spend"
    )
    assert item.interpretation == "reconstruction_uncertainty"
    assert item.category == "reconstruction_uncertainty.economy"
    assert item.severity == "info"
    assert "sparse" in (item.explanation or "").lower()


def test_level_and_roll_is_descriptive():
    ep = episode(
        action_ids=("xp", "roll"),
        before_level=6,
        after_level=7,
        spend=12,
        req_min=10,
        req_max=12,
        umin=0,
        umax=2,
    )
    actions = {
        "xp": action("xp", ActionType.PURCHASE_XP, count=2),
        "roll": action(
            "roll", ActionType.REFRESH_SHOP,
            count_min=1, count_max=2,
        ),
    }
    findings = analyze_episode(ep, actions, EconomyTempoAnalyzerSettings())
    assert "level_and_roll" in codes(findings)
    assert "roll_activity" in codes(findings) or "roll_burst_candidate" in codes(findings)


def test_xp_without_level_is_descriptive():
    ep = episode(
        action_ids=("xp",),
        before_level=5,
        after_level=5,
        spend=4,
        req_min=4,
        req_max=4,
    )
    findings = analyze_episode(
        ep,
        {"xp": action("xp", ActionType.PURCHASE_XP, count=1)},
        EconomyTempoAnalyzerSettings(),
    )
    assert "xp_investment_without_level" in codes(findings)


def test_large_spend_low_gold_is_review_candidate_not_grade():
    ep = episode(
        action_ids=("roll",),
        before_gold=35,
        after_gold=5,
        spend=30,
        req_min=20,
        req_max=30,
        umin=0,
        umax=10,
    )
    findings = analyze_episode(
        ep,
        {
            "roll": action(
                "roll", ActionType.REFRESH_SHOP,
                count_min=1, count_max=5,
            )
        },
        EconomyTempoAnalyzerSettings(),
    )
    review = next(
        x for x in findings
        if x.finding_code == "large_spend_low_gold_review"
    )
    assert review.interpretation == "review_candidate"
    assert all(x.interpretation != "decision_grade" for x in findings)


def test_positioning_only_finding():
    ep = episode(action_ids=("m1",), spend=0, req_min=0, req_max=0)
    findings = analyze_episode(
        ep,
        {"m1": action("m1", ActionType.MOVE_UNIT)},
        EconomyTempoAnalyzerSettings(),
    )
    assert "positioning_only" in codes(findings)



def test_bounded_uncertainty_is_not_data_quality():
    ep = episode(
        action_ids=("roll",),
        spend=10,
        req_min=2,
        req_max=10,
        umin=0,
        umax=8,
    )
    settings = EconomyTempoAnalyzerSettings(emit_uncertainty_only=True)
    findings = analyze_episode(
        ep,
        {"roll": action("roll", ActionType.REFRESH_SHOP, count_min=1, count_max=5)},
        settings,
    )
    item = next(
        x for x in findings
        if x.finding_code == "bounded_economy_uncertainty"
    )
    assert item.interpretation == "reconstruction_uncertainty"
    assert item.severity == "info"
    assert all(
        x.interpretation != "data_quality"
        for x in findings
    )
