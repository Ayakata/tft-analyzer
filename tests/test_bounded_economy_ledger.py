from tft_analyzer.actions.models import (
    EconomyLedgerComponent,
    EconomyLedgerWindow,
)


def test_unpriced_buy_component_can_have_open_spend_max():
    component = EconomyLedgerComponent(
        kind="buy_unit",
        count_min=1,
        count_max=1,
        unit_cost=None,
        spend_min=0,
        spend_max=None,
        exact_count=True,
        exact_spend=False,
        champions=("rhaast",),
    )
    assert component.spend_max is None
    assert component.champions == ("rhaast",)


def test_bounded_ledger_serializes_interval():
    ledger = EconomyLedgerWindow(
        window_index=1,
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
    )
    payload = ledger.model_dump(mode="json")
    assert payload["action_spend_min"] == 2
    assert payload["action_spend_max"] == 18
    assert payload["unallocated_spend_min"] == 1
    assert payload["unallocated_spend_max"] == 17
