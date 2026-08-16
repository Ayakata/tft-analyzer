from tft_analyzer.actions import (
    ActionFusionEngine,
    ActionFusionSettings,
    FusionSnapshot,
)
from tft_analyzer.core.enums import ActionType
from tft_analyzer.game_data import (
    ChampionCostCatalog,
    build_champion_catalog_snapshot,
)
import json


def snap(
    *,
    t,
    eid,
    stage="3-2",
    gold=20,
    gold_status="carried",
    level=4,
    level_status="carried",
    xp=0,
    xp_req=20,
    xp_status="carried",
    xp_absolute=None,
    shop=("a", "b", "c", "d", "e"),
    shop_status="carried",
    board=4,
    board_cells=frozenset({"0,0", "0,1", "1,0", "1,1"}),
    board_usable=False,
    scene=True,
    bench=3,
    bench_slots=frozenset({"0", "1", "2"}),
):
    return FusionSnapshot(
        match_id="m",
        timestamp_s=float(t),
        evidence_id=eid,
        stage=stage,
        stage_status="carried",
        gold=gold,
        gold_status=gold_status,
        level=level,
        level_status=level_status,
        xp_current=xp,
        xp_required=xp_req,
        xp_status=xp_status,
        xp_absolute=xp_absolute,
        shop_slots=tuple(shop),
        shop_status=shop_status,
        board_count=board,
        board_cells=board_cells,
        board_usable=board_usable,
        scene_valid=scene,
        bench_count=bench,
        bench_slots=bench_slots,
    )


def types(result):
    return [x.action_type for x in result.actions]


def test_exact_reroll_from_shop_and_gold():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=20)
    curr = snap(
        t=10,
        eid="b",
        gold=18,
        gold_status="observed",
        shop=("f", "g", "h", "i", "j"),
        shop_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert ActionType.REFRESH_SHOP in types(result)
    reroll = next(
        x for x in result.actions
        if x.action_type == ActionType.REFRESH_SHOP
    )
    assert reroll.confidence == 0.95
    assert reroll.params["count_lower_bound"] == 1
    assert reroll.params["count_upper_bound_from_gold"] == 1


def test_round_shop_refresh_is_not_called_reroll():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", stage="3-2", gold=20)
    curr = snap(
        t=10,
        eid="b",
        stage="3-3",
        gold=25,
        gold_status="observed",
        shop=("f", "g", "h", "i", "j"),
        shop_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert ActionType.REFRESH_SHOP not in types(result)
    assert "automatic_round_shop_refresh_candidate" in result.diagnostic.notes


def test_buy_from_cleared_shop_slot_and_unit_gain():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=20, bench=3)
    curr = snap(
        t=10,
        eid="b",
        gold=17,
        gold_status="observed",
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    buy = next(
        x for x in result.actions
        if x.action_type == ActionType.BUY_UNIT
    )
    assert buy.params["champions"] == ["a"]
    assert buy.params["count"] == 1
    assert buy.confidence == 0.94


def test_purchase_xp_exact_cost_and_gain():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=20, xp=4)
    curr = snap(
        t=10,
        eid="b",
        gold=16,
        gold_status="observed",
        xp=8,
        xp_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    action = next(
        x for x in result.actions
        if x.action_type == ActionType.PURCHASE_XP
    )
    assert action.params["count"] == 1
    assert action.confidence == 0.95


def test_bench_to_board_transfer():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(
        t=0,
        eid="a",
        board=4,
        bench=3,
    )
    curr = snap(
        t=10,
        eid="b",
        board=5,
        board_cells=frozenset({"0,0", "0,1", "1,0", "1,1", "2,2"}),
        board_usable=True,
        bench=2,
        bench_slots=frozenset({"0", "1"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    action = next(
        x for x in result.actions
        if x.action_type == ActionType.BENCH_TO_BOARD
    )
    assert action.params["count"] == 1
    assert action.confidence == 0.94


def test_unknown_negative_spend_when_no_other_signal():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=20)
    curr = snap(
        t=10,
        eid="b",
        gold=17,
        gold_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert types(result) == [ActionType.UNKNOWN_ECON_ACTION]



def test_absolute_xp_cross_level_counts_multiple_purchases():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        level=5,
        level_status="carried",
        xp=18,
        xp_req=20,
        xp_status="carried",
        xp_absolute=50,
    )
    curr = snap(
        t=10,
        eid="b",
        gold=12,
        gold_status="observed",
        level=6,
        level_status="observed",
        xp=6,
        xp_req=36,
        xp_status="observed",
        xp_absolute=58,
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    xp_action = next(
        action
        for action in result.actions
        if action.action_type == ActionType.PURCHASE_XP
    )
    assert xp_action.params["count"] == 2
    assert xp_action.params["fixed_gold_cost"] == 8
    assert xp_action.confidence == 0.95
    assert result.diagnostic.xp_delta == 8
    assert result.diagnostic.xp_delta_source == "absolute_progress"
    assert result.ledger.action_spend_min == 8
    assert result.ledger.action_spend_max == 8
    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 0


def test_ledger_bounds_residual_after_reroll():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=20)
    curr = snap(
        t=10,
        eid="b",
        gold=15,
        gold_status="observed",
        shop=("f", "g", "h", "i", "j"),
        shop_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.observed_spend == 5
    assert result.ledger.action_spend_min == 2
    assert result.ledger.action_spend_max == 4
    assert result.ledger.unallocated_spend_min == 1
    assert result.ledger.unallocated_spend_max == 3
    assert result.ledger.status == "unallocated_bounded"

    reroll = next(
        component
        for component in result.ledger.components
        if component.kind == "reroll"
    )
    assert reroll.count_min == 1
    assert reroll.count_max == 2
    assert reroll.spend_min == 2
    assert reroll.spend_max == 4

    unknown = next(
        action
        for action in result.actions
        if action.action_type == ActionType.UNKNOWN_ECON_ACTION
    )
    assert unknown.params["unallocated_spend_min"] == 1
    assert unknown.params["unallocated_spend_max"] == 3
    assert unknown.params["unallocated_is_exact"] is False


def test_ledger_marks_residual_upper_bound_when_buy_cost_unknown():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        bench=3,
    )
    curr = snap(
        t=10,
        eid="b",
        gold=15,
        gold_status="observed",
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.observed_spend == 5
    assert result.ledger.action_spend_min == 0
    assert result.ledger.action_spend_max is None
    assert result.ledger.compatible_action_spend_min == 0
    assert result.ledger.compatible_action_spend_max == 5
    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 5

    buy = next(
        component
        for component in result.ledger.components
        if component.kind == "buy_unit"
    )
    assert buy.count_min == 1
    assert buy.count_max == 1
    assert buy.champions == ("a",)
    assert buy.spend_min == 0
    assert buy.spend_max is None

    assert all(
        action.action_type != ActionType.UNKNOWN_ECON_ACTION
        for action in result.actions
    )
    assert result.ledger.unknown_action_id is None



def test_minus_19_reroll_becomes_known_2_18_unknown_1_17():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=30)
    curr = snap(
        t=10,
        eid="b",
        gold=11,
        gold_status="observed",
        shop=("f", "g", "h", "i", "j"),
        shop_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.observed_spend == 19
    assert result.ledger.action_spend_min == 2
    assert result.ledger.action_spend_max == 18
    assert result.ledger.unallocated_spend_min == 1
    assert result.ledger.unallocated_spend_max == 17

    reroll = next(
        c for c in result.ledger.components
        if c.kind == "reroll"
    )
    assert reroll.count_min == 1
    assert reroll.count_max == 9


def test_xp32_plus_unpriced_buy_gives_unknown_0_3():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(
        t=0,
        eid="a",
        gold=40,
        level=6,
        xp=0,
        xp_req=36,
        xp_status="carried",
        xp_absolute=100,
        bench=3,
    )
    curr = snap(
        t=10,
        eid="b",
        gold=5,
        gold_status="observed",
        level=6,
        xp=32,
        xp_req=36,
        xp_status="observed",
        xp_absolute=132,
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.observed_spend == 35
    assert result.ledger.action_spend_min == 32
    assert result.ledger.action_spend_max is None
    assert result.ledger.compatible_action_spend_min == 32
    assert result.ledger.compatible_action_spend_max == 35
    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 3

    xp = next(
        c for c in result.ledger.components
        if c.kind == "purchase_xp"
    )
    assert xp.count_min == 8
    assert xp.count_max == 8
    assert xp.spend_min == 32
    assert xp.spend_max == 32

    buy = next(
        c for c in result.ledger.components
        if c.kind == "buy_unit"
    )
    assert buy.champions == ("a",)
    assert buy.spend_max is None


def test_no_known_action_is_exact_unallocated_interval():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=20)
    curr = snap(
        t=10,
        eid="b",
        gold=13,
        gold_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.action_spend_min == 0
    assert result.ledger.action_spend_max == 0
    assert result.ledger.unallocated_spend_min == 7
    assert result.ledger.unallocated_spend_max == 7
    assert result.ledger.status == "unallocated_exact"



def test_u_zero_to_three_is_uncertainty_only_not_unknown_action():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(
        t=0,
        eid="a",
        gold=40,
        level=6,
        xp=0,
        xp_req=36,
        xp_status="carried",
        xp_absolute=100,
        bench=3,
    )
    curr = snap(
        t=10,
        eid="b",
        gold=5,
        gold_status="observed",
        level=6,
        xp=32,
        xp_req=36,
        xp_status="observed",
        xp_absolute=132,
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 3
    assert result.ledger.unknown_action_id is None
    assert all(
        action.action_type != ActionType.UNKNOWN_ECON_ACTION
        for action in result.actions
    )
    assert "economy_uncertainty_only" in result.diagnostic.notes
    assert "economy_required_unknown" not in result.diagnostic.notes


def test_u_zero_to_eight_after_rerolls_is_not_unknown_action():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=20)
    curr = snap(
        t=10,
        eid="b",
        gold=10,
        gold_status="observed",
        shop=("f", "g", "h", "i", "j"),
        shop_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.action_spend_min == 2
    assert result.ledger.action_spend_max == 10
    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 8
    assert all(
        action.action_type != ActionType.UNKNOWN_ECON_ACTION
        for action in result.actions
    )


def test_u_one_to_seventeen_still_requires_unknown_action():
    engine = ActionFusionEngine(ActionFusionSettings())
    prev = snap(t=0, eid="a", gold=30)
    curr = snap(
        t=10,
        eid="b",
        gold=11,
        gold_status="observed",
        shop=("f", "g", "h", "i", "j"),
        shop_status="observed",
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.unallocated_spend_min == 1
    assert result.ledger.unallocated_spend_max == 17

    unknown = next(
        action
        for action in result.actions
        if action.action_type == ActionType.UNKNOWN_ECON_ACTION
    )
    assert unknown.params["existence_required"] is True
    assert unknown.params["unallocated_spend_min"] == 1
    assert unknown.params["unallocated_spend_max"] == 17
    assert result.ledger.unknown_action_id == unknown.action_id
    assert "economy_required_unknown" in result.diagnostic.notes



def priced_catalog(entries):
    raw = json.dumps(
        {
            "data": {
                entry["id"]: entry
                for entry in entries
            }
        }
    ).encode("utf-8")
    snapshot = build_champion_catalog_snapshot(
        raw,
        version="16.16.1",
        locale="en_US",
        source_url="test://riot-ddragon",
        fetched_at_utc="2026-08-14T00:00:00+00:00",
    )
    return ChampionCostCatalog(snapshot)


def test_priced_rhaast_buy_collapses_3g_window():
    c = priced_catalog(
        [
            {
                "id": "TFT16_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            }
        ]
    )
    engine = ActionFusionEngine(
        ActionFusionSettings(),
        champion_cost_catalog=c,
    )
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        shop=("rhaast", "b", "c", "d", "e"),
        bench=3,
    )
    curr = snap(
        t=10,
        eid="b",
        gold=17,
        gold_status="observed",
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    buy = next(
        action
        for action in result.actions
        if action.action_type == ActionType.BUY_UNIT
    )
    assert buy.params["pricing_status"] == "priced"
    assert buy.params["unit_costs"] == [3]
    assert buy.params["total_gold_cost"] == 3

    component = next(
        c for c in result.ledger.components
        if c.kind == "buy_unit"
    )
    assert component.spend_min == 3
    assert component.spend_max == 3
    assert component.exact_spend is True

    assert result.ledger.action_spend_min == 3
    assert result.ledger.action_spend_max == 3
    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 0
    assert all(
        action.action_type != ActionType.UNKNOWN_ECON_ACTION
        for action in result.actions
    )


def test_two_priced_buys_sum_costs():
    c = priced_catalog(
        [
            {
                "id": "TFT16_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            },
            {
                "id": "TFT16_Briar",
                "name": "Briar",
                "tier": 1,
            },
        ]
    )
    engine = ActionFusionEngine(
        ActionFusionSettings(),
        champion_cost_catalog=c,
    )
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        shop=("rhaast", "briar", "c", "d", "e"),
        bench=3,
    )
    curr = snap(
        t=1,
        eid="b",
        gold=16,
        gold_status="observed",
        shop=(None, None, "c", "d", "e"),
        shop_status="observed",
        bench=5,
        bench_slots=frozenset({"0", "1", "2", "3", "4"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    buy = next(
        action
        for action in result.actions
        if action.action_type == ActionType.BUY_UNIT
    )
    assert buy.params["unit_costs"] == [3, 1]
    assert buy.params["total_gold_cost"] == 4
    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 0


def test_conflicting_catalog_tiers_leave_buy_unpriced():
    c = priced_catalog(
        [
            {
                "id": "TFTA_Rhaast",
                "name": "Rhaast",
                "tier": 2,
            },
            {
                "id": "TFTB_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            },
        ]
    )
    engine = ActionFusionEngine(
        ActionFusionSettings(),
        champion_cost_catalog=c,
    )
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        shop=("rhaast", "b", "c", "d", "e"),
        bench=3,
    )
    curr = snap(
        t=1,
        eid="b",
        gold=17,
        gold_status="observed",
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    buy = next(
        action
        for action in result.actions
        if action.action_type == ActionType.BUY_UNIT
    )
    assert buy.params["pricing_status"] == "unresolved"
    assert buy.params["total_gold_cost"] is None
    assert buy.params["unresolved_champions"] == ["rhaast"]


def test_xp32_plus_priced_rhaast_fully_explains_35g():
    c = priced_catalog(
        [
            {
                "id": "TFT16_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            }
        ]
    )
    engine = ActionFusionEngine(
        ActionFusionSettings(),
        champion_cost_catalog=c,
    )
    prev = snap(
        t=0,
        eid="a",
        gold=40,
        level=6,
        xp=0,
        xp_req=36,
        xp_status="carried",
        xp_absolute=100,
        shop=("rhaast", "b", "c", "d", "e"),
        bench=3,
    )
    curr = snap(
        t=10,
        eid="b",
        gold=5,
        gold_status="observed",
        level=6,
        xp=32,
        xp_req=36,
        xp_status="observed",
        xp_absolute=132,
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    assert result.ledger.observed_spend == 35
    assert result.ledger.action_spend_min == 35
    assert result.ledger.action_spend_max == 35
    assert result.ledger.unallocated_spend_min == 0
    assert result.ledger.unallocated_spend_max == 0
    assert all(
        action.action_type != ActionType.UNKNOWN_ECON_ACTION
        for action in result.actions
    )



def test_tft17_zoe_minus_one_is_cost_conflict_and_degraded():
    c = priced_catalog(
        [
            {
                "id": "TFT16_Zoe",
                "name": "Zoe",
                "tier": 3,
            },
            {
                "id": "TFT17_Zoe",
                "name": "Zoe",
                "tier": 2,
            },
        ]
    )
    engine = ActionFusionEngine(
        ActionFusionSettings(),
        champion_cost_catalog=c,
        set_id="TFT17",
    )
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        shop=("zoe", "b", "c", "d", "e"),
        bench=3,
    )
    curr = snap(
        t=1,
        eid="b",
        gold=19,
        gold_status="observed",
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    buy = next(
        action
        for action in result.actions
        if action.action_type == ActionType.BUY_UNIT
    )
    assert buy.params["unit_costs"] == [2]
    assert buy.params["total_gold_cost"] == 2
    assert buy.params["cost_validation"] == "cost_conflict"
    assert buy.confidence == 0.45
    assert buy.quality.value == "ambiguous"
    assert result.ledger.required_action_spend_min == 2
    assert result.ledger.required_action_spend_max == 2
    assert result.ledger.action_spend_min == 2
    assert result.ledger.action_spend_max == 2
    assert result.ledger.feasible is False
    assert result.ledger.compatible_action_spend_min is None
    assert result.ledger.compatible_action_spend_max is None
    assert result.ledger.spend_deficit_min == 1
    assert result.ledger.spend_deficit_max == 1
    assert result.ledger.unallocated_spend_min is None
    assert result.ledger.unallocated_spend_max is None
    assert "buy_cost_conflict" in result.diagnostic.notes
    assert "economy_infeasible" in result.diagnostic.notes


def test_tft17_rhaast_minus_three_is_cost_consistent():
    c = priced_catalog(
        [
            {
                "id": "TFT17_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            }
        ]
    )
    engine = ActionFusionEngine(
        ActionFusionSettings(),
        champion_cost_catalog=c,
        set_id="TFT17",
    )
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        shop=("rhaast", "b", "c", "d", "e"),
        bench=3,
    )
    curr = snap(
        t=1,
        eid="b",
        gold=17,
        gold_status="observed",
        shop=(None, "b", "c", "d", "e"),
        shop_status="observed",
        bench=4,
        bench_slots=frozenset({"0", "1", "2", "3"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    buy = next(
        action
        for action in result.actions
        if action.action_type == ActionType.BUY_UNIT
    )
    assert buy.params["cost_validation"] == "cost_consistent"
    assert result.ledger.unallocated_spend_max == 0


def test_tft17_lissandra_two_copies_cost_two_total():
    c = priced_catalog(
        [
            {
                "id": "TFT16_Lissandra",
                "name": "Lissandra",
                "tier": 4,
            },
            {
                "id": "TFT17_Lissandra",
                "name": "Lissandra",
                "tier": 1,
            },
        ]
    )
    engine = ActionFusionEngine(
        ActionFusionSettings(),
        champion_cost_catalog=c,
        set_id="TFT17",
    )
    prev = snap(
        t=0,
        eid="a",
        gold=20,
        shop=("lissandra", "lissandra", "c", "d", "e"),
        bench=3,
    )
    curr = snap(
        t=1,
        eid="b",
        gold=18,
        gold_status="observed",
        shop=(None, None, "c", "d", "e"),
        shop_status="observed",
        bench=5,
        bench_slots=frozenset({"0", "1", "2", "3", "4"}),
    )

    result = engine.infer_pair(prev, curr, window_index=0)

    buy = next(
        action
        for action in result.actions
        if action.action_type == ActionType.BUY_UNIT
    )
    assert buy.params["unit_costs"] == [1, 1]
    assert buy.params["total_gold_cost"] == 2
    assert buy.params["cost_validation"] == "cost_consistent"


def test_required_spend_is_not_clamped_to_observation():
    c = priced_catalog([{"id": "TFT17_Rhaast", "name": "Rhaast", "tier": 3}])
    engine = ActionFusionEngine(ActionFusionSettings(), champion_cost_catalog=c, set_id="TFT17")
    prev = snap(t=0, eid="a", gold=10, shop=("rhaast", "b", "c", "d", "e"), bench=3)
    curr = snap(t=1, eid="b", gold=8, gold_status="observed", shop=(None, "b", "c", "d", "e"), shop_status="observed", bench=4, bench_slots=frozenset({"0", "1", "2", "3"}))
    result = engine.infer_pair(prev, curr, window_index=0)
    assert result.ledger.observed_spend == 2
    assert result.ledger.required_action_spend_min == 3
    assert result.ledger.action_spend_min == 3
    assert result.ledger.feasible is False
    assert result.ledger.spend_deficit_min == 1
