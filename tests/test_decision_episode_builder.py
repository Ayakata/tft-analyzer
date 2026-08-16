from tft_analyzer.actions.models import (
    ActionInferenceQuality,
    ActionWindowDiagnostic,
    EconomyLedgerWindow,
    InferredAction,
)
from tft_analyzer.core.enums import ActionType, DecisionType
from tft_analyzer.decisions import (
    DecisionEpisodeSettings,
    build_decision_episodes,
)


def action(action_id, kind, start, end, confidence=0.8):
    return InferredAction(
        action_id=action_id,
        match_id="m",
        action_type=kind,
        start_timestamp_s=start,
        end_timestamp_s=end,
        confidence=confidence,
        quality=(
            ActionInferenceQuality.SUPPORTED
            if confidence >= 0.65
            else ActionInferenceQuality.AMBIGUOUS
        ),
        params={},
        signals={},
        evidence_ids=(f"e{start}", f"e{end}"),
        producer_version="semantic-action-fusion-0.14.6",
    )


def window(index, start, end, stage, action_ids, *, gold_before=20, gold_after=18, level=5, stage_changed=False):
    return ActionWindowDiagnostic(
        window_index=index,
        match_id="m",
        start_timestamp_s=start,
        end_timestamp_s=end,
        start_evidence_id=f"e{start}",
        end_evidence_id=f"e{end}",
        stage_before=stage,
        stage_after=stage,
        stage_changed=stage_changed,
        gold_before=gold_before,
        gold_after=gold_after,
        gold_delta=(gold_after - gold_before),
        level_before=level,
        level_after=level,
        xp_absolute_before=10,
        xp_absolute_after=10,
        board_before=5,
        board_after=5,
        bench_before=4,
        bench_after=4,
        action_ids=tuple(action_ids),
    )


def ledger(index, start, end, spend=2, *, feasible=True, deficit=0):
    return EconomyLedgerWindow(
        window_index=index,
        match_id="m",
        start_timestamp_s=start,
        end_timestamp_s=end,
        start_evidence_id=f"e{start}",
        end_evidence_id=f"e{end}",
        observed_gold_delta=-spend,
        observed_spend=spend,
        required_action_spend_min=(spend + deficit),
        required_action_spend_max=(spend + deficit),
        action_spend_min=(spend + deficit),
        action_spend_max=(spend + deficit),
        compatible_action_spend_min=(spend if feasible else None),
        compatible_action_spend_max=(spend if feasible else None),
        feasible=feasible,
        spend_deficit_min=(0 if feasible else deficit),
        spend_deficit_max=(0 if feasible else deficit),
        unallocated_spend_min=(0 if feasible else None),
        unallocated_spend_max=(0 if feasible else None),
        status=("fully_explained" if feasible else "infeasible"),
    )


def settings(**kwargs):
    values = dict(
        producer_version="decision-episode-builder-0.15.0",
        max_idle_gap_seconds=15.0,
        max_episode_duration_seconds=45.0,
        split_on_stage_change=True,
        include_unknown_economy_only=True,
    )
    values.update(kwargs)
    return DecisionEpisodeSettings(**values)


def test_same_stage_nearby_windows_merge_but_actions_inside_window_are_unordered():
    actions = [
        action("a1", ActionType.BUY_UNIT, 0, 10),
        action("a2", ActionType.PURCHASE_XP, 0, 10),
        action("a3", ActionType.REFRESH_SHOP, 10, 20),
    ]
    windows = [
        window(0, 0, 10, "4-2", ("a1", "a2")),
        window(1, 10, 20, "4-2", ("a3",)),
    ]
    ledgers = [ledger(0, 0, 10, 6), ledger(1, 10, 20, 2)]

    episodes = build_decision_episodes(
        actions=actions,
        windows=windows,
        ledgers=ledgers,
        settings=settings(),
    )

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.window_indices == (0, 1)
    assert len(episode.action_groups) == 2
    assert episode.action_groups[0].action_ids == ("a1", "a2")
    assert episode.action_groups[0].exact_intra_group_order_known is False
    assert episode.sampling.ordering_guarantee == "window_partial_order"
    assert episode.sampling.exact_action_timestamps_known is False
    assert episode.summary["exact_sequence_reconstructed"] is False


def test_stage_change_splits_episodes():
    actions = [
        action("a1", ActionType.BUY_UNIT, 0, 10),
        action("a2", ActionType.REFRESH_SHOP, 10, 20),
    ]
    windows = [
        window(0, 0, 10, "3-5", ("a1",)),
        window(1, 10, 20, "3-6", ("a2",)),
    ]
    ledgers = [ledger(0, 0, 10), ledger(1, 10, 20)]

    episodes = build_decision_episodes(
        actions=actions,
        windows=windows,
        ledgers=ledgers,
        settings=settings(),
    )
    assert len(episodes) == 2


def test_large_idle_gap_splits_same_stage():
    actions = [
        action("a1", ActionType.BUY_UNIT, 0, 10),
        action("a2", ActionType.REFRESH_SHOP, 30, 40),
    ]
    windows = [
        window(0, 0, 10, "4-2", ("a1",)),
        window(3, 30, 40, "4-2", ("a2",)),
    ]
    ledgers = [ledger(0, 0, 10), ledger(3, 30, 40)]

    episodes = build_decision_episodes(
        actions=actions,
        windows=windows,
        ledgers=ledgers,
        settings=settings(max_idle_gap_seconds=15.0),
    )
    assert len(episodes) == 2


def test_position_only_episode_gets_only_safe_strategic_label():
    actions = [action("a1", ActionType.MOVE_UNIT, 0, 10)]
    windows = [window(0, 0, 10, "6-1", ("a1",))]
    episodes = build_decision_episodes(
        actions=actions,
        windows=windows,
        ledgers=[ledger(0, 0, 10, 0)],
        settings=settings(),
    )
    assert episodes[0].decision_type == DecisionType.POSITIONING_CHANGE


def test_reroll_burst_is_not_called_rolldown_in_stage_4_1():
    actions = [
        action("a1", ActionType.REFRESH_SHOP, 0, 10),
        action("a2", ActionType.REFRESH_SHOP, 10, 20),
    ]
    windows = [
        window(0, 0, 10, "4-6", ("a1",)),
        window(1, 10, 20, "4-6", ("a2",)),
    ]
    episodes = build_decision_episodes(
        actions=actions,
        windows=windows,
        ledgers=[ledger(0, 0, 10), ledger(1, 10, 20)],
        settings=settings(),
    )
    assert episodes[0].decision_type == DecisionType.OTHER


def test_infeasible_source_window_is_preserved_at_episode_level():
    actions = [action("a1", ActionType.BUY_UNIT, 0, 10, confidence=0.72)]
    windows = [window(0, 0, 10, "2-6", ("a1",), gold_before=10, gold_after=9)]
    episodes = build_decision_episodes(
        actions=actions,
        windows=windows,
        ledgers=[ledger(0, 0, 10, 1, feasible=False, deficit=1)],
        settings=settings(),
    )
    episode = episodes[0]
    assert episode.economy.infeasible_window_count == 1
    assert episode.economy.spend_deficit_min_total == 1
    assert episode.confidence == 0.45


def test_episode_id_is_deterministic():
    actions = [action("a1", ActionType.BUY_UNIT, 0, 10)]
    windows = [window(0, 0, 10, "2-3", ("a1",))]
    ledgers = [ledger(0, 0, 10)]

    a = build_decision_episodes(actions=actions, windows=windows, ledgers=ledgers, settings=settings())
    b = build_decision_episodes(actions=actions, windows=windows, ledgers=ledgers, settings=settings())
    assert a[0].decision_id == b[0].decision_id
