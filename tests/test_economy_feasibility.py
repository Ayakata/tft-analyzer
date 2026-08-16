from tft_analyzer.actions.models import EconomyLedgerWindow


def test_infeasible_ledger_has_no_unallocated_interval():
    ledger = EconomyLedgerWindow(
        window_index=0, match_id="m", start_timestamp_s=0.0, end_timestamp_s=1.0,
        start_evidence_id="a", end_evidence_id="b", observed_gold_delta=-1,
        observed_spend=1, required_action_spend_min=2, required_action_spend_max=2,
        action_spend_min=2, action_spend_max=2, compatible_action_spend_min=None,
        compatible_action_spend_max=None, feasible=False, spend_deficit_min=1,
        spend_deficit_max=1, unallocated_spend_min=None, unallocated_spend_max=None,
        status="infeasible",
    )
    assert ledger.required_action_spend_min == 2
    assert ledger.feasible is False
    assert ledger.unallocated_spend_min is None
