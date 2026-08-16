import pytest

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
    build_roster_evidence,
)


def action(
    action_id,
    action_type,
    *,
    params=None,
    confidence=0.90,
    t0=0.0,
    t1=1.0,
):
    return InferredAction(
        action_id=action_id,
        match_id="m",
        action_type=action_type,
        start_timestamp_s=t0,
        end_timestamp_s=t1,
        confidence=confidence,
        quality=(
            ActionInferenceQuality.SUPPORTED
            if confidence >= 0.65
            else ActionInferenceQuality.AMBIGUOUS
        ),
        params=params or {},
        evidence_ids=(f"e-{action_id}",),
        producer_version="semantic-action-fusion-0.14.6",
    )


def episode(
    decision_id,
    action_ids,
    *,
    stage="4-2",
    t0=0.0,
    t1=10.0,
):
    return DecisionEpisode(
        decision_id=decision_id,
        match_id="m",
        decision_type=DecisionType.OTHER,
        start_timestamp_s=t0,
        end_timestamp_s=t1,
        state_before_id=f"{decision_id}-b",
        state_after_id=f"{decision_id}-a",
        stage_start=stage,
        stage_end=stage,
        action_ids=tuple(action_ids),
        state_before=DecisionBoundaryState(
            timestamp_s=t0,
            evidence_id=f"{decision_id}-b",
            stage=stage,
            gold=40,
            level=6,
            xp_absolute=100,
            board_count=6,
            bench_count=3,
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=t1,
            evidence_id=f"{decision_id}-a",
            stage=stage,
            gold=20,
            level=6,
            xp_absolute=104,
            board_count=6,
            bench_count=3,
        ),
        confidence=0.8,
        extractor_version="decision-episode-builder-0.15.0",
    )


def test_confirmed_buy_identities_accumulate_as_copy_lower_bounds():
    actions = [
        action(
            "b1",
            ActionType.BUY_UNIT,
            params={
                "count": 2,
                "champions": ["Lissandra", "Lissandra"],
                "cost_validation": "cost_consistent",
            },
        ),
        action(
            "b2",
            ActionType.BUY_UNIT,
            params={
                "count": 3,
                "champions": ["Rek'Sai", "Rek'Sai", "Rek'Sai"],
                "cost_validation": "cost_possible",
            },
            t0=11.0,
            t1=12.0,
        ),
        action(
            "b3",
            ActionType.BUY_UNIT,
            params={
                "count": 4,
                "champions": ["Rhaast", "Rhaast", "Rhaast", "Rhaast"],
                "cost_validation": "cost_consistent",
            },
            t0=21.0,
            t1=22.0,
        ),
    ]
    episodes = [
        episode("d1", ["b1"], t0=0.0, t1=10.0),
        episode("d2", ["b2"], t0=10.0, t1=20.0),
        episode("d3", ["b3"], t0=20.0, t1=30.0),
    ]

    contexts, stats = build_roster_evidence(
        episodes,
        actions,
        RosterEvidenceSettings(),
        source_action_producer_version="semantic-action-fusion-0.14.6",
    )

    final = {
        item.champion: item
        for item in contexts[-1].after.champions
    }

    assert final["lissandra"].confirmed_acquired_copy_lower_bound == 2
    assert final["reksai"].confirmed_acquired_copy_lower_bound == 3
    assert final["rhaast"].confirmed_acquired_copy_lower_bound == 4
    assert contexts[-1].after.confirmed_identity_buy_copy_count == 9
    assert contexts[-1].after.confirmed_buy_identity_coverage == 1.0
    assert contexts[-1].after.acquisition_semantics == "confirmed_history_lower_bound"
    assert contexts[-1].after.current_ownership_status == "not_established"
    assert stats["uncovered_roster_relevant_action_count"] == 0


def test_cost_conflicted_buy_is_candidate_not_confirmed():
    actions = [
        action(
            "zoe",
            ActionType.BUY_UNIT,
            params={
                "count": 1,
                "champions": ["Zoe"],
                "cost_validation": "cost_conflict",
            },
            confidence=0.45,
        )
    ]
    contexts, _ = build_roster_evidence(
        [episode("d1", ["zoe"])],
        actions,
        RosterEvidenceSettings(),
    )

    final = contexts[-1].after
    zoe = next(
        item
        for item in final.champions
        if item.champion == "zoe"
    )

    assert zoe.confirmed_acquired_copy_lower_bound == 0
    assert zoe.candidate_acquired_copy_count == 1
    assert zoe.current_ownership_status == "not_established"
    assert final.confirmed_identity_buy_copy_count == 0
    assert final.candidate_identity_buy_copy_count == 1
    assert final.confirmed_buy_identity_coverage == 0.0
    assert (
        contexts[-1].delta.action_evidence[0].reason
        == "buy_cost_conflict"
    )


def test_unknown_sell_does_not_erase_historical_acquisition_evidence():
    actions = [
        action(
            "buy",
            ActionType.BUY_UNIT,
            params={
                "count": 4,
                "champions": ["Rhaast"] * 4,
                "cost_validation": "cost_consistent",
            },
        ),
        action(
            "sell",
            ActionType.SELL_UNIT,
            params={
                "count_lower_bound": 1,
                "champion": None,
                "identity_available": False,
            },
            t0=11.0,
            t1=12.0,
        ),
    ]
    contexts, _ = build_roster_evidence(
        [
            episode("d1", ["buy"], t0=0.0, t1=10.0),
            episode("d2", ["sell"], t0=10.0, t1=20.0),
        ],
        actions,
        RosterEvidenceSettings(),
    )

    rhaast = next(
        item
        for item in contexts[-1].after.champions
        if item.champion == "rhaast"
    )
    assert rhaast.confirmed_acquired_copy_lower_bound == 4
    assert rhaast.current_ownership_status == "not_established"
    assert (
        contexts[-1].after.unidentified_sell_unit_count_lower_bound
        == 1
    )
    assert contexts[-1].after.complete_sell_history_known is False
    assert contexts[-1].after.current_ownership_status == "not_established"


def test_unknown_economy_is_uncertainty_not_invented_acquisition():
    unknown = action(
        "u1",
        ActionType.UNKNOWN_ECON_ACTION,
        params={
            "unallocated_spend_min": 3,
            "unallocated_spend_max": 8,
            "existence_required": True,
        },
        confidence=0.5,
    )

    contexts, _ = build_roster_evidence(
        [episode("d1", ["u1"])],
        [unknown],
        RosterEvidenceSettings(),
    )
    final = contexts[-1].after

    assert final.champions == ()
    assert final.confirmed_identity_buy_copy_count == 0
    assert final.unresolved_economy_action_count == 1
    assert final.unresolved_economy_spend_min_total == 3
    assert final.unresolved_economy_spend_max_total == 8
    assert final.complete_roster_known is False


def test_relevant_action_coverage_guard_rejects_uncovered_buy():
    buy = action(
        "b1",
        ActionType.BUY_UNIT,
        params={
            "count": 1,
            "champions": ["Briar"],
            "cost_validation": "cost_consistent",
        },
    )

    with pytest.raises(
        ValueError,
        match="Uncovered",
    ):
        build_roster_evidence(
            [episode("d1", [])],
            [buy],
            RosterEvidenceSettings(
                require_relevant_action_coverage=True,
            ),
        )
