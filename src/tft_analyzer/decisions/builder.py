from __future__ import annotations

from collections import Counter
import hashlib
from statistics import mean

from tft_analyzer.actions.models import (
    EconomyLedgerWindow,
    InferredAction,
)
from tft_analyzer.core.enums import ActionType, DecisionType
from tft_analyzer.core.models.decisions import (
    DecisionActionGroup,
    DecisionBoundaryState,
    DecisionEconomySummary,
    DecisionEpisode,
    DecisionSamplingSummary,
)

from .models import DecisionEpisodeSettings


_POSITION_ACTIONS = {
    ActionType.MOVE_UNIT,
    ActionType.BENCH_TO_BOARD,
    ActionType.BOARD_TO_BENCH,
}


def _stage_of(window) -> str | None:
    return window.stage_after or window.stage_before


def _same_stage(left, right) -> bool:
    a = _stage_of(left)
    b = _stage_of(right)
    return a is not None and a == b


def _episode_id(
    match_id: str,
    window_indices: tuple[int, ...],
    producer_version: str,
) -> str:
    key = (
        f"{match_id}|{producer_version}|"
        + ",".join(str(value) for value in window_indices)
    )
    digest = hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]
    return f"decision-{window_indices[0]:04d}-{window_indices[-1]:04d}-{digest}"


def _boundary_before(window) -> DecisionBoundaryState:
    return DecisionBoundaryState(
        timestamp_s=float(window.start_timestamp_s),
        evidence_id=str(window.start_evidence_id),
        stage=window.stage_before,
        gold=window.gold_before,
        level=window.level_before,
        xp_absolute=window.xp_absolute_before,
        board_count=window.board_before,
        bench_count=window.bench_before,
    )


def _boundary_after(window) -> DecisionBoundaryState:
    return DecisionBoundaryState(
        timestamp_s=float(window.end_timestamp_s),
        evidence_id=str(window.end_evidence_id),
        stage=window.stage_after,
        gold=window.gold_after,
        level=window.level_after,
        xp_absolute=window.xp_absolute_after,
        board_count=window.board_after,
        bench_count=window.bench_after,
    )


def _decision_type(
    actions: list[InferredAction],
    before: DecisionBoundaryState,
    after: DecisionBoundaryState,
) -> DecisionType:
    types = {action.action_type for action in actions}

    if types and types <= _POSITION_ACTIONS:
        return DecisionType.POSITIONING_CHANGE

    if (
        ActionType.PURCHASE_XP in types
        and before.level is not None
        and after.level is not None
        and after.level > before.level
    ):
        return DecisionType.LEVEL_UP

    # Stage 4.1 deliberately does not call a burst "rolldown", "slow roll",
    # "stabilize", etc. Those are strategic interpretations for analyzers.
    return DecisionType.OTHER


def _economy_summary(
    ledgers: list[EconomyLedgerWindow],
) -> DecisionEconomySummary:
    observed = sum(item.observed_spend or 0 for item in ledgers)
    required_min = sum(item.required_action_spend_min for item in ledgers)

    open_required_max = any(
        item.required_action_spend_max is None and bool(item.components)
        for item in ledgers
    )
    required_max = (
        None
        if open_required_max
        else sum(item.required_action_spend_max or 0 for item in ledgers)
    )

    compatible_min = sum(
        item.compatible_action_spend_min or 0
        for item in ledgers
    )
    compatible_max = sum(
        item.compatible_action_spend_max or 0
        for item in ledgers
    )
    unallocated_min = sum(
        item.unallocated_spend_min or 0
        for item in ledgers
    )
    unallocated_max = sum(
        item.unallocated_spend_max or 0
        for item in ledgers
    )

    return DecisionEconomySummary(
        observed_spend_total=observed,
        required_action_spend_min=required_min,
        required_action_spend_max=required_max,
        compatible_action_spend_min=compatible_min,
        compatible_action_spend_max=compatible_max,
        unallocated_spend_min=unallocated_min,
        unallocated_spend_max=unallocated_max,
        infeasible_window_count=sum(
            item.feasible is False for item in ledgers
        ),
        spend_deficit_min_total=sum(
            item.spend_deficit_min or 0
            for item in ledgers
            if item.feasible is False
        ),
        required_unknown_window_count=sum(
            (item.unallocated_spend_min or 0) > 0
            for item in ledgers
        ),
        uncertainty_only_window_count=sum(
            (item.unallocated_spend_min or 0) == 0
            and (item.unallocated_spend_max or 0) > 0
            for item in ledgers
        ),
    )


def _should_join(
    current: list,
    candidate,
    settings: DecisionEpisodeSettings,
) -> bool:
    if not current:
        return True

    first = current[0]
    previous = current[-1]

    if settings.split_on_stage_change:
        if not _same_stage(previous, candidate):
            return False
        if bool(previous.stage_changed) or bool(candidate.stage_changed):
            return False

    idle_gap = max(
        0.0,
        float(candidate.start_timestamp_s)
        - float(previous.end_timestamp_s),
    )
    if idle_gap > settings.max_idle_gap_seconds:
        return False

    duration = (
        float(candidate.end_timestamp_s)
        - float(first.start_timestamp_s)
    )
    return duration <= settings.max_episode_duration_seconds


def group_active_windows(
    windows: list,
    settings: DecisionEpisodeSettings,
) -> list[list]:
    active = [window for window in windows if window.action_ids]
    active.sort(key=lambda item: (item.start_timestamp_s, item.window_index))

    groups: list[list] = []
    current: list = []

    for window in active:
        if not current or _should_join(current, window, settings):
            current.append(window)
            continue

        groups.append(current)
        current = [window]

    if current:
        groups.append(current)

    return groups


def build_decision_episodes(
    *,
    actions: list[InferredAction],
    windows: list,
    ledgers: list[EconomyLedgerWindow],
    settings: DecisionEpisodeSettings,
) -> list[DecisionEpisode]:
    if not windows:
        return []

    actions_by_id = {action.action_id: action for action in actions}
    ledger_by_window = {item.window_index: item for item in ledgers}

    episodes: list[DecisionEpisode] = []

    for source_windows in group_active_windows(windows, settings):
        episode_actions: list[InferredAction] = []
        action_groups: list[DecisionActionGroup] = []
        evidence_ids: list[str] = []

        for group_index, window in enumerate(source_windows):
            group_actions = [
                actions_by_id[action_id]
                for action_id in window.action_ids
                if action_id in actions_by_id
            ]
            episode_actions.extend(group_actions)

            group_evidence = []
            for value in (
                window.start_evidence_id,
                window.end_evidence_id,
            ):
                if value and value not in group_evidence:
                    group_evidence.append(str(value))
            for action in group_actions:
                for value in action.evidence_ids:
                    if value and value not in group_evidence:
                        group_evidence.append(str(value))
                    if value and value not in evidence_ids:
                        evidence_ids.append(str(value))
            for value in group_evidence:
                if value not in evidence_ids:
                    evidence_ids.append(value)

            action_groups.append(
                DecisionActionGroup(
                    group_index=group_index,
                    window_index=int(window.window_index),
                    start_timestamp_s=float(window.start_timestamp_s),
                    end_timestamp_s=float(window.end_timestamp_s),
                    action_ids=tuple(action.action_id for action in group_actions),
                    action_types=tuple(
                        action.action_type.value for action in group_actions
                    ),
                    evidence_ids=tuple(group_evidence),
                    exact_intra_group_order_known=False,
                )
            )

        if not episode_actions:
            continue

        if (
            not settings.include_unknown_economy_only
            and all(
                action.action_type == ActionType.UNKNOWN_ECON_ACTION
                for action in episode_actions
            )
        ):
            continue

        first = source_windows[0]
        last = source_windows[-1]
        before = _boundary_before(first)
        after = _boundary_after(last)
        source_ledgers = [
            ledger_by_window[index]
            for index in (window.window_index for window in source_windows)
            if index in ledger_by_window
        ]

        action_type_counts = Counter(
            action.action_type.value for action in episode_actions
        )
        action_quality_counts = Counter(
            action.quality.value for action in episode_actions
        )

        confidence = min(
            action.confidence for action in episode_actions
        )
        if any(item.feasible is False for item in source_ledgers):
            confidence = min(confidence, 0.45)

        widths = [
            float(window.end_timestamp_s) - float(window.start_timestamp_s)
            for window in source_windows
        ]
        window_indices = tuple(
            int(window.window_index) for window in source_windows
        )

        summary = {
            "action_type_counts": dict(action_type_counts),
            "action_quality_counts": dict(action_quality_counts),
            "action_count": len(episode_actions),
            "action_group_count": len(action_groups),
            "compound_action_group_count": sum(
                len(group.action_ids) > 1 for group in action_groups
            ),
            "contains_unknown_economy": any(
                action.action_type == ActionType.UNKNOWN_ECON_ACTION
                for action in episode_actions
            ),
            "contains_infeasible_economy": any(
                item.feasible is False for item in source_ledgers
            ),
            "exact_sequence_reconstructed": False,
            "interpretation_policy": "observed_bounded_activity_only",
        }

        episodes.append(
            DecisionEpisode(
                decision_id=_episode_id(
                    episode_actions[0].match_id,
                    window_indices,
                    settings.producer_version,
                ),
                match_id=episode_actions[0].match_id,
                decision_type=_decision_type(
                    episode_actions,
                    before,
                    after,
                ),
                start_timestamp_s=float(first.start_timestamp_s),
                end_timestamp_s=float(last.end_timestamp_s),
                state_before_id=str(first.start_evidence_id),
                state_after_id=str(last.end_evidence_id),
                stage_start=before.stage,
                stage_end=after.stage,
                window_indices=window_indices,
                action_ids=tuple(action.action_id for action in episode_actions),
                action_groups=tuple(action_groups),
                state_before=before,
                state_after=after,
                economy=_economy_summary(source_ledgers),
                sampling=DecisionSamplingSummary(
                    source_window_count=len(source_windows),
                    span_seconds=(
                        float(last.end_timestamp_s)
                        - float(first.start_timestamp_s)
                    ),
                    max_source_window_seconds=max(widths) if widths else 0.0,
                    exact_action_timestamps_known=False,
                    exact_intra_window_order_known=False,
                    ordering_guarantee="window_partial_order",
                ),
                summary=summary,
                confidence=confidence,
                extractor_version=settings.producer_version,
            )
        )

    return episodes
