from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from tft_analyzer.core.enums import ActionType
from tft_analyzer.game_data import ChampionCostCatalog

from .models import (
    ActionInferenceQuality,
    ActionWindowDiagnostic,
    EconomyLedgerComponent,
    EconomyLedgerWindow,
    InferredAction,
)


@dataclass(frozen=True, slots=True)
class ActionFusionSettings:
    producer_version: str = "semantic-action-fusion-0.14.6"

    reroll_gold_cost: int = 2
    xp_purchase_gold_cost: int = 4
    xp_purchase_amount: int = 4

    shop_refresh_min_changed_slots: int = 4
    shop_refresh_min_occupied_slots: int = 4

    max_window_seconds: float = 20.0
    emit_unknown_negative_econ: bool = True


@dataclass(frozen=True, slots=True)
class FusionSnapshot:
    match_id: str
    timestamp_s: float
    evidence_id: str

    stage: str | None
    stage_status: str

    gold: int | None
    gold_status: str

    level: int | None
    level_status: str

    xp_current: int | None
    xp_required: int | None
    xp_status: str
    xp_absolute: int | None = None

    shop_slots: tuple[str | None, ...] = ()
    shop_status: str = "unknown"

    board_count: int = 0
    board_cells: frozenset[str] = frozenset()
    board_usable: bool = False
    scene_valid: bool = False

    bench_count: int = 0
    bench_slots: frozenset[str] = frozenset()


@dataclass(slots=True)
class ActionFusionResult:
    actions: list[InferredAction] = field(default_factory=list)
    diagnostic: ActionWindowDiagnostic | None = None
    ledger: EconomyLedgerWindow | None = None


class ActionFusionEngine:
    def __init__(
        self,
        settings: ActionFusionSettings,
        *,
        champion_cost_catalog: ChampionCostCatalog | None = None,
        set_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.champion_cost_catalog = champion_cost_catalog
        self.set_id = (
            str(set_id).upper()
            if set_id is not None
            else None
        )

    def _price_buy_champions(
        self,
        champions: list[str],
    ) -> dict[str, Any]:
        if self.champion_cost_catalog is None:
            return {
                "status": "catalog_unavailable",
                "costs": [None for _ in champions],
                "spend_min": 0,
                "spend_max": None,
                "resolved_count": 0,
                "unresolved_champions": list(champions),
                "resolutions": [],
                "provider": None,
                "version": None,
                "set_id": self.set_id,
            }

        resolutions = [
            self.champion_cost_catalog.resolve_cost(
                champion,
                set_id=self.set_id,
            )
            for champion in champions
        ]
        costs = [
            resolution.cost
            for resolution in resolutions
        ]
        resolved_costs = [
            int(cost)
            for cost in costs
            if cost is not None
        ]
        unresolved = [
            champion
            for champion, resolution in zip(
                champions,
                resolutions,
            )
            if resolution.cost is None
        ]

        spend_min = sum(resolved_costs)
        fully_priced = not unresolved

        if fully_priced:
            status = "priced"
            spend_max = spend_min
        elif resolved_costs:
            status = "partial"
            spend_max = None
        else:
            status = "unresolved"
            spend_max = None

        snapshot = self.champion_cost_catalog.snapshot

        return {
            "status": status,
            "costs": costs,
            "spend_min": spend_min,
            "spend_max": spend_max,
            "resolved_count": len(resolved_costs),
            "unresolved_champions": unresolved,
            "resolutions": [
                resolution.model_dump(mode="json")
                for resolution in resolutions
            ],
            "provider": snapshot.provider,
            "version": snapshot.version,
            "locale": snapshot.locale,
            "set_id": self.set_id,
        }

    @staticmethod
    def _quality(confidence: float) -> ActionInferenceQuality:
        if confidence >= 0.85:
            return ActionInferenceQuality.STRONG
        if confidence >= 0.65:
            return ActionInferenceQuality.SUPPORTED
        return ActionInferenceQuality.AMBIGUOUS

    @staticmethod
    def _stable_json(value: dict[str, Any]) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _action(
        self,
        *,
        prev: FusionSnapshot,
        curr: FusionSnapshot,
        action_type: ActionType,
        confidence: float,
        params: dict[str, Any],
        signals: dict[str, Any],
        ordinal: int,
    ) -> InferredAction:
        confidence = max(0.0, min(float(confidence), 1.0))
        raw = "|".join(
            [
                prev.match_id,
                action_type.value,
                prev.evidence_id,
                curr.evidence_id,
                str(ordinal),
                self._stable_json(params),
            ]
        )
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

        return InferredAction(
            action_id=f"action-{action_type.value}-{digest}",
            match_id=prev.match_id,
            action_type=action_type,
            start_timestamp_s=float(prev.timestamp_s),
            end_timestamp_s=float(curr.timestamp_s),
            confidence=confidence,
            quality=self._quality(confidence),
            params=params,
            signals=signals,
            evidence_ids=tuple(
                dict.fromkeys([prev.evidence_id, curr.evidence_id])
            ),
            producer_version=self.settings.producer_version,
        )

    @staticmethod
    def _shop_changes(before, after):
        size = max(len(before), len(after))
        b = list(before) + [None] * (size - len(before))
        a = list(after) + [None] * (size - len(after))

        cleared = []
        filled = []
        replaced = []

        for index, (old, new) in enumerate(zip(b, a)):
            if old == new:
                continue
            if old is not None and new is None:
                cleared.append({"index": index, "champion": old})
            elif old is None and new is not None:
                filled.append({"index": index, "champion": new})
            elif old is not None and new is not None:
                replaced.append({"index": index, "from": old, "to": new})

        return cleared, filled, replaced

    @staticmethod
    def _stage_changed(prev, curr):
        return (
            prev.stage is not None
            and curr.stage is not None
            and prev.stage != curr.stage
        )

    @staticmethod
    def _observed_delta(before, after, current_status):
        if (
            before is None
            or after is None
            or current_status != "observed"
            or before == after
        ):
            return None
        return int(after - before)

    @staticmethod
    def _xp_delta(prev, curr):
        if curr.xp_status != "observed":
            return None, "none"

        if (
            prev.xp_absolute is not None
            and curr.xp_absolute is not None
            and prev.xp_absolute != curr.xp_absolute
        ):
            return (
                int(curr.xp_absolute - prev.xp_absolute),
                "absolute_progress",
            )

        if (
            prev.level == curr.level
            and prev.xp_current is not None
            and curr.xp_current is not None
            and prev.xp_current != curr.xp_current
        ):
            return (
                int(curr.xp_current - prev.xp_current),
                "same_level_current",
            )

        return None, "none"

    @staticmethod
    def _build_bounded_ledger(
        *,
        window_index,
        prev,
        curr,
        stage_changed,
        gold_delta,
        components,
    ):
        observed_spend = (
            -gold_delta
            if gold_delta is not None and gold_delta < 0
            else None
        )

        required_min = sum(component.spend_min for component in components)
        has_open_max = any(component.spend_max is None for component in components)
        required_max = (
            None
            if has_open_max
            else sum(int(component.spend_max or 0) for component in components)
        )

        common = dict(
            window_index=window_index,
            match_id=prev.match_id,
            start_timestamp_s=prev.timestamp_s,
            end_timestamp_s=curr.timestamp_s,
            start_evidence_id=prev.evidence_id,
            end_evidence_id=curr.evidence_id,
            stage_changed=stage_changed,
            observed_gold_delta=gold_delta,
            observed_spend=observed_spend,
            components=tuple(components),
            required_action_spend_min=required_min,
            required_action_spend_max=required_max,
            action_spend_min=required_min,
            action_spend_max=required_max,
        )

        if observed_spend is None:
            return EconomyLedgerWindow(
                **common,
                compatible_action_spend_min=None,
                compatible_action_spend_max=None,
                feasible=None,
                spend_deficit_min=None,
                spend_deficit_max=None,
                unallocated_spend_min=None,
                unallocated_spend_max=None,
                status=(
                    "income_or_flat"
                    if gold_delta is not None
                    else "unobserved"
                ),
            )

        if required_min > observed_spend:
            deficit_min = required_min - observed_spend
            deficit_max = (
                None
                if required_max is None
                else max(deficit_min, required_max - observed_spend)
            )
            return EconomyLedgerWindow(
                **common,
                compatible_action_spend_min=None,
                compatible_action_spend_max=None,
                feasible=False,
                spend_deficit_min=deficit_min,
                spend_deficit_max=deficit_max,
                unallocated_spend_min=None,
                unallocated_spend_max=None,
                status="infeasible",
            )

        compatible_min = required_min
        compatible_max = (
            observed_spend
            if required_max is None
            else min(observed_spend, required_max)
        )
        compatible_max = max(compatible_min, compatible_max)
        unallocated_min = max(0, observed_spend - compatible_max)
        unallocated_max = max(0, observed_spend - compatible_min)

        if unallocated_max == 0:
            status = "fully_explained"
        elif unallocated_min == unallocated_max:
            status = "unallocated_exact"
        else:
            status = "unallocated_bounded"

        return EconomyLedgerWindow(
            **common,
            compatible_action_spend_min=compatible_min,
            compatible_action_spend_max=compatible_max,
            feasible=True,
            spend_deficit_min=0,
            spend_deficit_max=0,
            unallocated_spend_min=unallocated_min,
            unallocated_spend_max=unallocated_max,
            status=status,
        )

    def infer_pair(self, prev, curr, *, window_index):
        if prev.match_id != curr.match_id:
            raise ValueError("Cannot fuse snapshots from different matches")
        if curr.timestamp_s < prev.timestamp_s:
            raise ValueError("Action snapshots are not time ordered")

        window_s = float(curr.timestamp_s - prev.timestamp_s)
        stage_changed = self._stage_changed(prev, curr)
        scene_valid_pair = bool(prev.scene_valid and curr.scene_valid)

        gold_delta = self._observed_delta(
            prev.gold, curr.gold, curr.gold_status
        )
        observed_spend = (
            -gold_delta
            if gold_delta is not None and gold_delta < 0
            else None
        )
        level_delta = self._observed_delta(
            prev.level, curr.level, curr.level_status
        )
        xp_delta, xp_delta_source = self._xp_delta(prev, curr)

        shop_changed = (
            curr.shop_status == "observed"
            and prev.shop_slots != curr.shop_slots
        )
        cleared, filled, replaced = ([], [], [])
        if shop_changed:
            cleared, filled, replaced = self._shop_changes(
                prev.shop_slots, curr.shop_slots
            )
        shop_change_count = len(cleared) + len(filled) + len(replaced)

        board_delta = int(curr.board_count - prev.board_count)
        bench_delta = int(curr.bench_count - prev.bench_count)
        total_delta = board_delta + bench_delta

        board_removed = prev.board_cells - curr.board_cells
        board_added = curr.board_cells - prev.board_cells
        board_cell_change_count = len(board_removed) + len(board_added)

        common_signals = {
            "window_s": window_s,
            "stage_changed": stage_changed,
            "scene_valid_pair": scene_valid_pair,
            "gold_delta": gold_delta,
            "level_delta": level_delta,
            "xp_delta": xp_delta,
            "xp_delta_source": xp_delta_source,
            "shop_change_count": shop_change_count,
            "board_delta": board_delta,
            "bench_delta": bench_delta,
            "total_units_delta": total_delta,
        }

        actions = []
        components = []
        notes = []
        ordinal = 0

        if window_s > self.settings.max_window_seconds:
            notes.append("long_window")

        # XP purchase.
        if (
            not stage_changed
            and gold_delta is not None
            and gold_delta <= -self.settings.xp_purchase_gold_cost
            and xp_delta is not None
            and xp_delta > 0
            and self.settings.xp_purchase_amount > 0
        ):
            purchase_count = max(
                1,
                xp_delta // self.settings.xp_purchase_amount,
            )
            expected_xp = purchase_count * self.settings.xp_purchase_amount
            fixed_cost = purchase_count * self.settings.xp_purchase_gold_cost

            if xp_delta == expected_xp and -gold_delta >= fixed_cost:
                exact_gold_match = (-gold_delta == fixed_cost)
                confidence = 0.95 if exact_gold_match else 0.88
                reason = (
                    "absolute_xp_and_gold_exact"
                    if xp_delta_source == "absolute_progress"
                    else "xp_and_gold_exact"
                )
                if not exact_gold_match:
                    reason += "_plus_other_spend"

                action = self._action(
                    prev=prev,
                    curr=curr,
                    action_type=ActionType.PURCHASE_XP,
                    confidence=confidence,
                    params={
                        "count": purchase_count,
                        "count_min": purchase_count,
                        "count_max": purchase_count,
                        "gold_cost_each": self.settings.xp_purchase_gold_cost,
                        "xp_each": self.settings.xp_purchase_amount,
                        # Compatibility alias retained from 0.14.1.
                        "fixed_gold_cost": fixed_cost,
                        "spend_min": fixed_cost,
                        "spend_max": fixed_cost,
                        "aggregate_window": purchase_count > 1,
                    },
                    signals={
                        **common_signals,
                        "reason": reason,
                        "xp_absolute_before": prev.xp_absolute,
                        "xp_absolute_after": curr.xp_absolute,
                    },
                    ordinal=ordinal,
                )
                actions.append(action)
                ordinal += 1
                components.append(
                    EconomyLedgerComponent(
                        kind="purchase_xp",
                        count_min=purchase_count,
                        count_max=purchase_count,
                        unit_cost=self.settings.xp_purchase_gold_cost,
                        spend_min=fixed_cost,
                        spend_max=fixed_cost,
                        exact_count=True,
                        exact_spend=True,
                        action_id=action.action_id,
                    )
                )

        occupied_before = sum(
            x is not None
            for x in prev.shop_slots
        )
        occupied_after = sum(
            x is not None
            for x in curr.shop_slots
        )
        refresh_signature = (
            shop_change_count
            >= self.settings.shop_refresh_min_changed_slots
            and occupied_before
            >= self.settings.shop_refresh_min_occupied_slots
            and occupied_after
            >= self.settings.shop_refresh_min_occupied_slots
        )

        # BUY_UNIT: identity from shop, cost from trusted catalog when
        # available. Missing/ambiguous catalog entries remain unpriced.
        if (
            cleared
            and not stage_changed
            and curr.shop_status == "observed"
        ):
            likely_buy = False
            confidence = 0.0
            reason = None

            if (
                scene_valid_pair
                and total_delta > 0
                and shop_change_count <= 3
            ):
                likely_buy = True
                confidence = (
                    0.94
                    if total_delta == len(cleared)
                    else 0.84
                )
                reason = "shop_clear_plus_unit_gain"
            elif (
                gold_delta is not None
                and gold_delta < 0
                and shop_change_count <= 2
            ):
                likely_buy = True
                confidence = 0.72
                reason = "shop_clear_plus_gold_spend"
            elif (
                scene_valid_pair
                and total_delta > 0
                and refresh_signature
            ):
                likely_buy = True
                confidence = 0.68
                reason = "compound_refresh_plus_unit_gain"

            if likely_buy:
                count = (
                    min(len(cleared), total_delta)
                    if total_delta > 0
                    else len(cleared)
                )
                count = max(1, count)
                champions = [
                    item["champion"]
                    for item in cleared[:count]
                ]

                pricing = self._price_buy_champions(
                    champions
                )

                exact_buy_spend = (
                    pricing["spend_max"]
                    if pricing["status"] == "priced"
                    else None
                )

                action = self._action(
                    prev=prev,
                    curr=curr,
                    action_type=ActionType.BUY_UNIT,
                    confidence=confidence,
                    params={
                        "count": count,
                        "count_min": count,
                        "count_max": count,
                        "champions": champions,
                        "source_shop_slots": [
                            item["index"]
                            for item in cleared[:count]
                        ],
                        "gold_cost_known": (
                            pricing["status"] == "priced"
                        ),
                        "unit_costs": pricing["costs"],
                        "total_gold_cost": exact_buy_spend,
                        "spend_min": pricing["spend_min"],
                        "spend_max": pricing["spend_max"],
                        "pricing_status": pricing["status"],
                        "pricing_provider": pricing["provider"],
                        "pricing_version": pricing["version"],
                        "pricing_set": pricing["set_id"],
                        "cost_validation": "pending",
                        "unresolved_champions": (
                            pricing["unresolved_champions"]
                        ),
                        "aggregate_window": True,
                    },
                    signals={
                        **common_signals,
                        "reason": reason,
                        "shop_cleared_count": len(cleared),
                        "pricing_resolutions": (
                            pricing["resolutions"]
                        ),
                        "buy_cost_le_observed_spend": (
                            None
                            if observed_spend is None
                            else (
                                pricing["spend_min"]
                                <= observed_spend
                            )
                        ),
                    },
                    ordinal=ordinal,
                )
                actions.append(action)
                ordinal += 1

                concrete_costs = [
                    int(cost)
                    if cost is not None
                    else None
                    for cost in pricing["costs"]
                ]
                unique_known_costs = {
                    cost
                    for cost in concrete_costs
                    if cost is not None
                }

                components.append(
                    EconomyLedgerComponent(
                        kind="buy_unit",
                        count_min=count,
                        count_max=count,
                        unit_cost=(
                            next(iter(unique_known_costs))
                            if len(unique_known_costs) == 1
                            and len(concrete_costs) == count
                            and all(
                                cost is not None
                                for cost in concrete_costs
                            )
                            else None
                        ),
                        unit_costs=tuple(concrete_costs),
                        spend_min=int(pricing["spend_min"]),
                        spend_max=(
                            int(pricing["spend_max"])
                            if pricing["spend_max"]
                            is not None
                            else None
                        ),
                        exact_count=True,
                        exact_spend=(
                            pricing["status"] == "priced"
                        ),
                        pricing_status=pricing["status"],
                        pricing_provider=pricing["provider"],
                        pricing_version=pricing["version"],
                        unresolved_champions=tuple(
                            pricing["unresolved_champions"]
                        ),
                        action_id=action.action_id,
                        champions=tuple(champions),
                    )
                )

        # Reroll. The upper bound is calculated after BUY pricing, so
        # mandatory spend from XP and priced champion purchases cannot also be
        # allocated to rerolls.
        if (
            refresh_signature
            and not stage_changed
            and observed_spend is not None
            and observed_spend >= self.settings.reroll_gold_cost
        ):
            mandatory_other_spend = sum(
                component.spend_min
                for component in components
            )
            available = max(
                0,
                observed_spend - mandatory_other_spend,
            )

            count_min = 1
            count_max = max(
                count_min,
                available // self.settings.reroll_gold_cost,
            )
            spend_min = (
                count_min * self.settings.reroll_gold_cost
            )
            spend_max = (
                count_max * self.settings.reroll_gold_cost
            )

            action = self._action(
                prev=prev,
                curr=curr,
                action_type=ActionType.REFRESH_SHOP,
                confidence=(
                    0.95
                    if count_min == count_max == 1
                    else 0.84
                ),
                params={
                    "count_min": count_min,
                    "count_max": count_max,
                    "count_lower_bound": count_min,
                    "count_upper_bound_from_gold": count_max,
                    "gold_cost_each": self.settings.reroll_gold_cost,
                    "spend_min": spend_min,
                    "spend_max": spend_max,
                    "changed_slots": shop_change_count,
                    "aggregate_window": True,
                },
                signals={
                    **common_signals,
                    "occupied_shop_before": occupied_before,
                    "occupied_shop_after": occupied_after,
                    "replaced_slots": len(replaced),
                    "mandatory_other_spend_before_reroll": (
                        mandatory_other_spend
                    ),
                },
                ordinal=ordinal,
            )
            actions.append(action)
            ordinal += 1
            components.append(
                EconomyLedgerComponent(
                    kind="reroll",
                    count_min=count_min,
                    count_max=count_max,
                    unit_cost=self.settings.reroll_gold_cost,
                    unit_costs=(),
                    spend_min=spend_min,
                    spend_max=spend_max,
                    exact_count=(count_min == count_max),
                    exact_spend=(spend_min == spend_max),
                    action_id=action.action_id,
                )
            )
        elif refresh_signature and stage_changed:
            notes.append(
                "automatic_round_shop_refresh_candidate"
            )

        # Transfers / board move.
        if (
            scene_valid_pair
            and curr.board_usable
            and total_delta == 0
            and board_delta > 0
            and bench_delta < 0
        ):
            count = min(board_delta, -bench_delta)
            actions.append(
                self._action(
                    prev=prev,
                    curr=curr,
                    action_type=ActionType.BENCH_TO_BOARD,
                    confidence=(0.94 if board_delta == -bench_delta else 0.82),
                    params={"count": count, "aggregate_window": count > 1},
                    signals=common_signals,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
        elif (
            scene_valid_pair
            and curr.board_usable
            and total_delta == 0
            and board_delta < 0
            and bench_delta > 0
        ):
            count = min(-board_delta, bench_delta)
            actions.append(
                self._action(
                    prev=prev,
                    curr=curr,
                    action_type=ActionType.BOARD_TO_BENCH,
                    confidence=(0.94 if -board_delta == bench_delta else 0.82),
                    params={"count": count, "aggregate_window": count > 1},
                    signals=common_signals,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
        elif (
            scene_valid_pair
            and curr.board_usable
            and prev.board_count == curr.board_count
            and board_cell_change_count > 0
            and bench_delta == 0
        ):
            moved_estimate = max(len(board_removed), len(board_added))
            actions.append(
                self._action(
                    prev=prev,
                    curr=curr,
                    action_type=ActionType.MOVE_UNIT,
                    confidence=0.76,
                    params={
                        "subtype": "board_reposition",
                        "moved_estimate": moved_estimate,
                        "from_cells": sorted(board_removed),
                        "to_cells": sorted(board_added),
                        "aggregate_window": moved_estimate > 1,
                    },
                    signals=common_signals,
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        # Sell.
        if (
            scene_valid_pair
            and not stage_changed
            and total_delta < 0
            and gold_delta is not None
            and gold_delta > 0
        ):
            actions.append(
                self._action(
                    prev=prev,
                    curr=curr,
                    action_type=ActionType.SELL_UNIT,
                    confidence=0.74,
                    params={
                        "count_lower_bound": abs(total_delta),
                        "champion": None,
                        "identity_available": False,
                        "aggregate_window": abs(total_delta) > 1,
                    },
                    signals={
                        **common_signals,
                        "reason": "unit_loss_plus_gold_gain",
                    },
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        # Bounded economy ledger.
        ledger = self._build_bounded_ledger(
            window_index=window_index,
            prev=prev,
            curr=curr,
            stage_changed=stage_changed,
            gold_delta=gold_delta,
            components=components,
        )

        lower_unallocated = (
            int(ledger.unallocated_spend_min or 0)
            if ledger.unallocated_spend_min is not None
            else 0
        )
        upper_unallocated = (
            int(ledger.unallocated_spend_max or 0)
            if ledger.unallocated_spend_max is not None
            else 0
        )

        # 0.14.3 existence semantics:
        #
        # U[min..max] is a ledger uncertainty interval. It becomes an
        # UNKNOWN_ECON_ACTION only when min > 0, because only then do all
        # compatible explanations require additional spend beyond the
        # recognized action classes.
        #
        # U[0..N] must remain diagnostic-only: a recognized reroll/buy/etc.
        # may already explain the whole observed spend.
        if (
            self.settings.emit_unknown_negative_econ
            and not stage_changed
            and ledger.feasible is True
            and ledger.observed_spend is not None
            and lower_unallocated > 0
        ):
            exact = lower_unallocated == upper_unallocated

            unknown = self._action(
                prev=prev,
                curr=curr,
                action_type=ActionType.UNKNOWN_ECON_ACTION,
                confidence=(0.58 if exact else 0.50),
                params={
                    "observed_spend": ledger.observed_spend,
                    "action_spend_min": ledger.action_spend_min,
                    "action_spend_max": ledger.action_spend_max,
                    "unallocated_spend_min": lower_unallocated,
                    "unallocated_spend_max": upper_unallocated,
                    "unallocated_is_exact": exact,
                    "existence_required": True,
                    "direction": "spend",
                    "aggregate_window": True,
                },
                signals={
                    **common_signals,
                    "reason": (
                        "exact_required_unallocated_spend"
                        if exact
                        else "bounded_required_unallocated_spend"
                    ),
                },
                ordinal=ordinal,
            )
            actions.append(unknown)
            ordinal += 1
            ledger = ledger.model_copy(
                update={"unknown_action_id": unknown.action_id}
            )

        # BUY cost validation runs only after the complete ledger exists.
        # This lets a priced BUY be validated jointly with XP/reroll instead of
        # requiring observed_gold_delta == buy_cost in isolation.
        validated_actions = []
        for action in actions:
            if action.action_type != ActionType.BUY_UNIT:
                validated_actions.append(action)
                continue

            total_buy_cost = action.params.get(
                "total_gold_cost"
            )
            if total_buy_cost is None:
                status = "unpriced"
            elif ledger.observed_spend is None:
                status = "unobserved"
            elif int(ledger.observed_spend) < int(
                total_buy_cost
            ):
                status = "cost_conflict"
            elif (
                ledger.unallocated_spend_min == 0
                and ledger.unallocated_spend_max == 0
            ):
                status = "cost_consistent"
            else:
                status = "cost_possible"

            params = dict(action.params)
            params["cost_validation"] = status
            params["observed_window_spend"] = (
                ledger.observed_spend
            )

            signals = dict(action.signals)
            signals["cost_validation"] = status
            signals["ledger_required_action_spend_min"] = (
                ledger.required_action_spend_min
            )
            signals["ledger_required_action_spend_max"] = (
                ledger.required_action_spend_max
            )
            signals["ledger_compatible_action_spend_min"] = (
                ledger.compatible_action_spend_min
            )
            signals["ledger_compatible_action_spend_max"] = (
                ledger.compatible_action_spend_max
            )
            signals["ledger_feasible"] = ledger.feasible
            signals["ledger_spend_deficit_min"] = ledger.spend_deficit_min
            signals["ledger_spend_deficit_max"] = ledger.spend_deficit_max
            signals["ledger_unallocated_min"] = ledger.unallocated_spend_min
            signals["ledger_unallocated_max"] = ledger.unallocated_spend_max

            confidence = action.confidence
            quality = action.quality
            if status == "cost_conflict":
                signals["pre_cost_confidence"] = (
                    action.confidence
                )
                confidence = min(
                    action.confidence,
                    0.45,
                )
                quality = self._quality(confidence)
                notes.append("buy_cost_conflict")

            validated_actions.append(
                action.model_copy(
                    update={
                        "params": params,
                        "signals": signals,
                        "confidence": confidence,
                        "quality": quality,
                    }
                )
            )

        actions = validated_actions

        if len(actions) > 1:
            notes.append("compound_window")

        if ledger.feasible is False:
            notes.append("economy_infeasible")
        elif upper_unallocated > 0:
            notes.append("economy_interval")
            if lower_unallocated == 0:
                notes.append("economy_uncertainty_only")
            else:
                notes.append("economy_required_unknown")

        diagnostic = ActionWindowDiagnostic(
            window_index=window_index,
            match_id=prev.match_id,
            start_timestamp_s=prev.timestamp_s,
            end_timestamp_s=curr.timestamp_s,
            start_evidence_id=prev.evidence_id,
            end_evidence_id=curr.evidence_id,
            stage_before=prev.stage,
            stage_after=curr.stage,
            stage_changed=stage_changed,
            scene_valid_pair=scene_valid_pair,
            gold_before=prev.gold,
            gold_after=curr.gold,
            gold_delta=gold_delta,
            level_before=prev.level,
            level_after=curr.level,
            level_delta=level_delta,
            xp_before=(
                {"current": prev.xp_current, "required": prev.xp_required}
                if prev.xp_current is not None and prev.xp_required is not None
                else None
            ),
            xp_after=(
                {"current": curr.xp_current, "required": curr.xp_required}
                if curr.xp_current is not None and curr.xp_required is not None
                else None
            ),
            xp_delta=xp_delta,
            xp_absolute_before=prev.xp_absolute,
            xp_absolute_after=curr.xp_absolute,
            xp_delta_source=xp_delta_source,
            shop_change_count=shop_change_count,
            shop_cleared_slots=tuple(cleared),
            shop_filled_slots=tuple(filled),
            shop_replaced_slots=tuple(replaced),
            board_before=prev.board_count,
            board_after=curr.board_count,
            board_delta=board_delta,
            bench_before=prev.bench_count,
            bench_after=curr.bench_count,
            bench_delta=bench_delta,
            total_units_delta=total_delta,
            board_cell_change_count=board_cell_change_count,
            action_ids=tuple(action.action_id for action in actions),
            ledger_status=ledger.status,
            ledger_feasible=ledger.feasible,
            ledger_required_action_spend_min=ledger.required_action_spend_min,
            ledger_required_action_spend_max=ledger.required_action_spend_max,
            ledger_compatible_action_spend_min=ledger.compatible_action_spend_min,
            ledger_compatible_action_spend_max=ledger.compatible_action_spend_max,
            ledger_spend_deficit_min=ledger.spend_deficit_min,
            ledger_spend_deficit_max=ledger.spend_deficit_max,
            ledger_action_spend_min=ledger.action_spend_min,
            ledger_action_spend_max=ledger.action_spend_max,
            ledger_unallocated_min=ledger.unallocated_spend_min,
            ledger_unallocated_max=ledger.unallocated_spend_max,
            notes=tuple(notes),
        )

        return ActionFusionResult(
            actions=actions,
            diagnostic=diagnostic,
            ledger=ledger,
        )
