from tft_analyzer.actions.models import EconomyLedgerWindow


def test_uncertainty_interval_can_include_zero_without_unknown_action():
    ledger = EconomyLedgerWindow(
        window_index=0,
        match_id="m",
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        start_evidence_id="a",
        end_evidence_id="b",
        observed_gold_delta=-10,
        observed_spend=10,
        action_spend_min=2,
        action_spend_max=10,
        unallocated_spend_min=0,
        unallocated_spend_max=8,
        status="unallocated_bounded",
        unknown_action_id=None,
    )

    assert ledger.unallocated_spend_min == 0
    assert ledger.unallocated_spend_max == 8
    assert ledger.unknown_action_id is None


def test_required_unknown_has_positive_lower_bound():
    ledger = EconomyLedgerWindow(
        window_index=0,
        match_id="m",
        start_timestamp_s=0.0,
        end_timestamp_s=10.0,
        start_evidence_id="a",
        end_evidence_id="b",
        observed_gold_delta=-19,
        observed_spend=19,
        action_spend_min=2,
        action_spend_max=18,
        unallocated_spend_min=1,
        unallocated_spend_max=17,
        status="unallocated_bounded",
        unknown_action_id="action-unknown",
    )

    assert ledger.unallocated_spend_min > 0
    assert ledger.unknown_action_id is not None
