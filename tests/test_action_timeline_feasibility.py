from tft_analyzer.actions.timeline import _ledger_label


def test_infeasible_timeline_has_required_and_deficit_no_u():
    ledger = {
        "observed_spend": 1, "required_action_spend_min": 2,
        "required_action_spend_max": 2, "feasible": False,
        "spend_deficit_min": 1, "spend_deficit_max": 1,
        "components": [{"kind": "buy_unit", "count_min": 1, "exact_spend": True}],
    }
    label = _ledger_label(ledger)
    assert label == "1g ! K[2] deficit[1]"
    assert "U[" not in label
    assert "buy?" not in label


def test_priced_buy_has_no_question_marker():
    ledger = {
        "observed_spend": 3, "required_action_spend_min": 3,
        "required_action_spend_max": 3, "compatible_action_spend_min": 3,
        "compatible_action_spend_max": 3, "feasible": True,
        "unallocated_spend_min": 0, "unallocated_spend_max": 0,
        "components": [{"kind": "buy_unit", "count_min": 1, "exact_spend": True}],
    }
    assert _ledger_label(ledger) == "3=K[3]+U[0]"
