from __future__ import annotations

from collections import Counter
import hashlib

from tft_analyzer.actions.models import InferredAction
from tft_analyzer.core.enums import ActionType
from tft_analyzer.core.models.analysis import Finding
from tft_analyzer.core.models.decisions import DecisionEpisode

from .models import EconomyTempoAnalyzerSettings


def _finding_id(
    episode: DecisionEpisode,
    code: str,
    producer_version: str,
) -> str:
    key = (
        f"{episode.match_id}|{episode.decision_id}|"
        f"{code}|{producer_version}"
    )
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"finding-{digest}"


def _evidence_ids(episode: DecisionEpisode) -> tuple[str, ...]:
    values: list[str] = []
    for group in episode.action_groups:
        for value in group.evidence_ids:
            if value and value not in values:
                values.append(value)
    for boundary in (episode.state_before, episode.state_after):
        if boundary is not None and boundary.evidence_id not in values:
            values.append(boundary.evidence_id)
    return tuple(values)


def _base(
    episode: DecisionEpisode,
    *,
    code: str,
    category: str,
    title: str,
    interpretation: str,
    severity: str,
    confidence: float,
    settings: EconomyTempoAnalyzerSettings,
    metrics: dict,
    explanation: str,
    limitations: tuple[str, ...] = (),
) -> Finding:
    return Finding(
        finding_id=_finding_id(
            episode,
            code,
            settings.producer_version,
        ),
        match_id=episode.match_id,
        decision_id=episode.decision_id,
        finding_code=code,
        producer_version=settings.producer_version,
        category=category,
        title=title,
        interpretation=interpretation,
        stage=episode.stage_end or episode.stage_start,
        start_timestamp_s=episode.start_timestamp_s,
        end_timestamp_s=episode.end_timestamp_s,
        severity=severity,
        confidence=max(0.0, min(1.0, confidence)),
        evidence_type="rule",
        metrics=metrics,
        explanation=explanation,
        limitations=limitations,
        evidence_ids=_evidence_ids(episode),
    )


def _action_metrics(
    episode: DecisionEpisode,
    actions_by_id: dict[str, InferredAction],
) -> dict[str, object]:
    actions = [
        actions_by_id[action_id]
        for action_id in episode.action_ids
        if action_id in actions_by_id
    ]
    counts = Counter(action.action_type.value for action in actions)

    reroll_min = 0
    reroll_max = 0
    reroll_open_max = False
    xp_count = 0
    buy_count = 0
    priced_buy_spend = 0
    buy_cost_conflicts = 0

    for action in actions:
        p = action.params
        if action.action_type == ActionType.REFRESH_SHOP:
            reroll_min += int(p.get("count_min", 1) or 0)
            raw_max = p.get("count_max")
            if raw_max is None:
                reroll_open_max = True
            else:
                reroll_max += int(raw_max)
        elif action.action_type == ActionType.PURCHASE_XP:
            xp_count += int(
                p.get("count", p.get("count_min", 1)) or 0
            )
        elif action.action_type == ActionType.BUY_UNIT:
            buy_count += int(
                p.get("count", p.get("count_min", 1)) or 0
            )
            cost = p.get("total_gold_cost")
            if cost is not None:
                priced_buy_spend += int(cost)
            if p.get("cost_validation") == "cost_conflict":
                buy_cost_conflicts += 1

    return {
        "action_type_counts": dict(counts),
        "reroll_action_count": counts.get(ActionType.REFRESH_SHOP.value, 0),
        "reroll_count_min": reroll_min,
        "reroll_count_max": None if reroll_open_max else reroll_max,
        "xp_purchase_count": xp_count,
        "buy_unit_count": buy_count,
        "priced_buy_spend": priced_buy_spend,
        "buy_cost_conflict_count": buy_cost_conflicts,
    }


def analyze_episode(
    episode: DecisionEpisode,
    actions_by_id: dict[str, InferredAction],
    settings: EconomyTempoAnalyzerSettings,
) -> list[Finding]:
    findings: list[Finding] = []
    econ = episode.economy
    metrics = _action_metrics(episode, actions_by_id)

    gold_before = (
        episode.state_before.gold
        if episode.state_before is not None
        else None
    )
    gold_after = (
        episode.state_after.gold
        if episode.state_after is not None
        else None
    )
    level_before = (
        episode.state_before.level
        if episode.state_before is not None
        else None
    )
    level_after = (
        episode.state_after.level
        if episode.state_after is not None
        else None
    )
    level_delta = (
        level_after - level_before
        if level_before is not None and level_after is not None
        else None
    )

    common = {
        **metrics,
        "gold_before": gold_before,
        "gold_after": gold_after,
        "level_before": level_before,
        "level_after": level_after,
        "level_delta": level_delta,
        "observed_spend": econ.observed_spend_total,
        "required_action_spend_min": econ.required_action_spend_min,
        "required_action_spend_max": econ.required_action_spend_max,
        "unallocated_spend_min": econ.unallocated_spend_min,
        "unallocated_spend_max": econ.unallocated_spend_max,
        "infeasible_window_count": econ.infeasible_window_count,
        "spend_deficit_min_total": econ.spend_deficit_min_total,
        "source_window_count": episode.sampling.source_window_count,
        "span_seconds": episode.sampling.span_seconds,
    }

    # 1. Hard data-quality contradiction. This is intentionally NOT a player
    # decision grade.
    if econ.infeasible_window_count > 0:
        findings.append(
            _base(
                episode,
                code="economy_infeasible",
                category="data_quality.hard_conflict.economy",
                title="Economy constraints are infeasible",
                interpretation="data_quality",
                severity="major",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    "Trusted action requirements exceed the observed gold "
                    "spend in at least one source window. Review upstream "
                    "shop/gold/action evidence before grading this episode."
                ),
                limitations=(
                    "This finding describes reconstruction inconsistency, not player error.",
                ),
            )
        )

    # 2. Sparse-capture reconstruction uncertainty. A positive unallocated
    # minimum means some spend definitely happened between observations but the
    # available screenshots do not identify enough semantic actions to name it.
    # This is expected with sparse evidence and is NOT a hard data-quality fault.
    if (
        settings.emit_unresolved_economy_spend
        and econ.unallocated_spend_min > 0
    ):
        findings.append(
            _base(
                episode,
                code="unresolved_economy_spend",
                category="reconstruction_uncertainty.economy",
                title="Observed spend is only partially reconstructed",
                interpretation="reconstruction_uncertainty",
                severity="info",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"At least {econ.unallocated_spend_min} gold of observed "
                    "spend is not assigned to named semantic actions in the "
                    "available sparse snapshots. The gold transition can still "
                    "be valid; one or more actions may simply be unobserved."
                ),
                limitations=(
                    "Sparse capture can omit multiple purchases, rerolls, XP purchases or other actions between screenshots.",
                    "This finding is reconstruction uncertainty, not evidence of bad source data or player error.",
                ),
            )
        )
    elif (
        settings.emit_uncertainty_only
        and econ.unallocated_spend_min == 0
        and econ.unallocated_spend_max > 0
    ):
        findings.append(
            _base(
                episode,
                code="bounded_economy_uncertainty",
                category="reconstruction_uncertainty.economy",
                title="Economy decomposition remains bounded",
                interpretation="reconstruction_uncertainty",
                severity="info",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    "Known actions are compatible with the observed spend, but "
                    "additional unobserved spend remains possible because the "
                    "capture is sparse."
                ),
                limitations=(
                    "This uncertainty is expected when exact actions between screenshots are not observed.",
                ),
            )
        )

    reroll_action_count = int(metrics["reroll_action_count"])
    reroll_min = int(metrics["reroll_count_min"])
    reroll_max = metrics["reroll_count_max"]
    xp_count = int(metrics["xp_purchase_count"])

    # 3. Level + roll is a useful tempo shape, but not a judgment of whether it
    # was optimal.
    if level_delta is not None and level_delta > 0:
        if reroll_action_count > 0:
            findings.append(
                _base(
                    episode,
                    code="level_and_roll",
                    category="tempo.activity",
                    title="Level-up followed by/combined with roll activity",
                    interpretation="descriptive",
                    severity="info",
                    confidence=episode.confidence,
                    settings=settings,
                    metrics=common,
                    explanation=(
                        f"The observed episode moves from level {level_before} "
                        f"to {level_after} and also contains shop refresh activity. "
                        "Sparse screenshots preserve only window-level partial order."
                    ),
                    limitations=(
                        "This does not label the episode as a correct or incorrect rolldown.",
                    ),
                )
            )
        else:
            findings.append(
                _base(
                    episode,
                    code="level_up",
                    category="tempo.activity",
                    title="Level-up observed",
                    interpretation="descriptive",
                    severity="info",
                    confidence=episode.confidence,
                    settings=settings,
                    metrics=common,
                    explanation=(
                        f"The observed episode moves from level {level_before} "
                        f"to {level_after}."
                    ),
                )
            )
    elif settings.emit_xp_investment and xp_count > 0:
        findings.append(
            _base(
                episode,
                code="xp_investment_without_level",
                category="tempo.activity",
                title="XP investment without an observed level-up",
                interpretation="descriptive",
                severity="info",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"At least {xp_count} XP purchase action(s) were inferred, "
                    "while the boundary level did not increase in this episode."
                ),
            )
        )

    # 4. Bounded roll activity. We only call it a 'burst candidate' when the
    # upper bound or number of refresh observations is large enough.
    if settings.emit_roll_activity and reroll_action_count > 0:
        burst_candidate = (
            reroll_action_count >= 2
            or reroll_max is None
            or (
                reroll_max is not None
                and int(reroll_max)
                >= settings.roll_burst_max_count_threshold
            )
        )
        code = "roll_burst_candidate" if burst_candidate else "roll_activity"
        title = (
            "Bounded roll burst candidate"
            if burst_candidate
            else "Shop refresh activity observed"
        )
        findings.append(
            _base(
                episode,
                code=code,
                category="tempo.roll",
                title=title,
                interpretation="descriptive",
                severity="info",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"Refresh activity is bounded at rerolls>={reroll_min}"
                    + (
                        " with an open upper bound."
                        if reroll_max is None
                        else f" and <= {int(reroll_max)} from observed gold constraints."
                    )
                    + " This is not automatically classified as rolldown/slow-roll."
                ),
            )
        )

    # 5. Large spend is descriptive. If it also leaves very low observed gold,
    # create a review candidate, but explicitly avoid calling it a mistake.
    if (
        settings.emit_large_spend
        and econ.observed_spend_total >= settings.large_spend_threshold
    ):
        findings.append(
            _base(
                episode,
                code="large_spend",
                category="economy.activity",
                title="Large observed spend episode",
                interpretation="descriptive",
                severity="info",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"The episode contains {econ.observed_spend_total} gold of "
                    "observed spend. This is surfaced as an analysis landmark."
                ),
            )
        )

        if (
            settings.emit_low_gold_review_candidate
            and gold_after is not None
            and gold_after <= settings.low_gold_after_threshold
        ):
            findings.append(
                _base(
                    episode,
                    code="large_spend_low_gold_review",
                    category="review.economy",
                    title="Large spend leaves low observed gold",
                    interpretation="review_candidate",
                    severity="minor",
                    confidence=episode.confidence,
                    settings=settings,
                    metrics=common,
                    explanation=(
                        f"The episode spends {econ.observed_spend_total} gold and "
                        f"ends at observed gold={gold_after}. This is worth reviewing "
                        "once HP, board strength, streak and lobby context are available."
                    ),
                    limitations=(
                        "Not graded as a mistake without board-strength/lobby/meta context.",
                    ),
                )
            )

    # 6. Pure positioning episode is safe to identify from action types.
    action_types = set(metrics["action_type_counts"])
    position_types = {
        ActionType.MOVE_UNIT.value,
        ActionType.BENCH_TO_BOARD.value,
        ActionType.BOARD_TO_BENCH.value,
    }
    if (
        settings.emit_positioning_only
        and action_types
        and action_types <= position_types
    ):
        findings.append(
            _base(
                episode,
                code="positioning_only",
                category="tempo.positioning",
                title="Positioning-only activity episode",
                interpretation="descriptive",
                severity="info",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    "The observed semantic actions in this episode are limited "
                    "to board/bench positioning changes."
                ),
            )
        )

    return findings


def analyze_episodes(
    episodes: list[DecisionEpisode],
    actions: list[InferredAction],
    settings: EconomyTempoAnalyzerSettings,
) -> list[Finding]:
    actions_by_id = {action.action_id: action for action in actions}
    findings: list[Finding] = []
    for episode in episodes:
        findings.extend(
            analyze_episode(
                episode,
                actions_by_id,
                settings,
            )
        )
    return findings
