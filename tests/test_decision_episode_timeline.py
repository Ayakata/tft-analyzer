from tft_analyzer.core.enums import DecisionType
from tft_analyzer.core.models.decisions import (
    DecisionActionGroup,
    DecisionBoundaryState,
    DecisionEconomySummary,
    DecisionEpisode,
    DecisionSamplingSummary,
)


def test_decision_episode_contract_is_explicitly_partial_order():
    episode = DecisionEpisode(
        decision_id="d",
        match_id="m",
        decision_type=DecisionType.OTHER,
        start_timestamp_s=0,
        end_timestamp_s=10,
        state_before_id="a",
        state_after_id="b",
        window_indices=(0,),
        action_ids=("x", "y"),
        action_groups=(
            DecisionActionGroup(
                group_index=0,
                window_index=0,
                start_timestamp_s=0,
                end_timestamp_s=10,
                action_ids=("x", "y"),
                action_types=("buy_unit", "purchase_xp"),
                exact_intra_group_order_known=False,
            ),
        ),
        state_before=DecisionBoundaryState(
            timestamp_s=0,
            evidence_id="a",
            stage="4-2",
        ),
        state_after=DecisionBoundaryState(
            timestamp_s=10,
            evidence_id="b",
            stage="4-2",
        ),
        economy=DecisionEconomySummary(),
        sampling=DecisionSamplingSummary(
            source_window_count=1,
            span_seconds=10,
            max_source_window_seconds=10,
        ),
        summary={"exact_sequence_reconstructed": False},
        confidence=0.7,
        extractor_version="decision-episode-builder-0.15.0",
    )

    assert episode.schema_version == 2
    assert episode.sampling.ordering_guarantee == "window_partial_order"
    assert episode.sampling.exact_intra_window_order_known is False
    assert episode.action_groups[0].exact_intra_group_order_known is False
