from __future__ import annotations

from collections import Counter
import hashlib

from tft_analyzer.actions.models import InferredAction
from tft_analyzer.core.enums import ActionType
from tft_analyzer.core.models.analysis import Finding
from tft_analyzer.core.models.decisions import DecisionEpisode
from tft_analyzer.features.episode_context.models import EpisodePlayerContext

from .models import ContextReviewAnalyzerSettings


def _finding_id(
    episode: DecisionEpisode,
    code: str,
    producer_version: str,
) -> str:
    raw = (
        f"{episode.match_id}|{episode.decision_id}|"
        f"{code}|{producer_version}"
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"finding-{digest}"


def _evidence_ids(
    episode: DecisionEpisode,
    context: EpisodePlayerContext,
) -> tuple[str, ...]:
    values: list[str] = []
    for group in episode.action_groups:
        for value in group.evidence_ids:
            if value and value not in values:
                values.append(value)
    for value in (
        context.before.evidence_id,
        context.after.evidence_id,
    ):
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _base(
    episode: DecisionEpisode,
    context: EpisodePlayerContext,
    *,
    code: str,
    category: str,
    title: str,
    interpretation: str,
    severity: str,
    confidence: float,
    settings: ContextReviewAnalyzerSettings,
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
        evidence_ids=_evidence_ids(episode, context),
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
    counts = Counter(
        action.action_type.value
        for action in actions
    )

    reroll_min = 0
    reroll_max = 0
    reroll_open_max = False
    xp_purchase_count = 0

    for action in actions:
        params = action.params
        if action.action_type == ActionType.REFRESH_SHOP:
            reroll_min += int(
                params.get("count_min", 1) or 0
            )
            raw_max = params.get("count_max")
            if raw_max is None:
                reroll_open_max = True
            else:
                reroll_max += int(raw_max)
        elif action.action_type == ActionType.PURCHASE_XP:
            xp_purchase_count += int(
                params.get(
                    "count",
                    params.get("count_min", 1),
                )
                or 0
            )

    return {
        "action_type_counts": dict(counts),
        "action_count": len(actions),
        "reroll_action_count": counts.get(
            ActionType.REFRESH_SHOP.value,
            0,
        ),
        "reroll_count_min": reroll_min,
        "reroll_count_max": (
            None
            if reroll_open_max
            else reroll_max
        ),
        "xp_purchase_count": xp_purchase_count,
    }


def _usable_hp(
    context: EpisodePlayerContext,
) -> tuple[int | None, int | None, int | None]:
    before = (
        context.before.hp
        if context.feature_trust.before.hp.usable_for_strategy
        else None
    )
    after = (
        context.after.hp
        if context.feature_trust.after.hp.usable_for_strategy
        else None
    )
    known = [
        value
        for value in (before, after)
        if value is not None
    ]
    pressure_hp = min(known) if known else None
    return before, after, pressure_hp


def _usable_gold(
    context: EpisodePlayerContext,
) -> tuple[int | None, int | None]:
    before = (
        context.before.gold
        if context.feature_trust.before.gold.usable_for_strategy
        else None
    )
    after = (
        context.after.gold
        if context.feature_trust.after.gold.usable_for_strategy
        else None
    )
    return before, after


def _usable_level(
    context: EpisodePlayerContext,
) -> tuple[int | None, int | None, int | None]:
    before = (
        context.before.level
        if context.feature_trust.before.level.usable_for_strategy
        else None
    )
    after = (
        context.after.level
        if context.feature_trust.after.level.usable_for_strategy
        else None
    )
    delta = (
        after - before
        if before is not None and after is not None
        else None
    )
    return before, after, delta


def _common_metrics(
    episode: DecisionEpisode,
    context: EpisodePlayerContext,
    action_metrics: dict[str, object],
) -> dict[str, object]:
    hp_before, hp_after, pressure_hp = _usable_hp(context)
    gold_before, gold_after = _usable_gold(context)
    level_before, level_after, level_delta = _usable_level(context)

    return {
        **action_metrics,
        "hp_before": hp_before,
        "hp_after": hp_after,
        "pressure_hp": pressure_hp,
        "gold_before": gold_before,
        "gold_after": gold_after,
        "level_before": level_before,
        "level_after": level_after,
        "level_delta": level_delta,
        "observed_spend": episode.economy.observed_spend_total,
        "unallocated_spend_min": episode.economy.unallocated_spend_min,
        "unallocated_spend_max": episode.economy.unallocated_spend_max,
        "economy_infeasible": (
            episode.economy.infeasible_window_count > 0
            or context.quality.economy_feasible is False
        ),
        "reconstruction_uncertainty": (
            context.quality.reconstruction_uncertainty
        ),
        "board_after": context.after.board_count,
        "board_capacity_after": context.after.board_capacity,
        "board_after_semantics": (
            context.feature_trust.after.board_count.semantics
        ),
        "board_after_usable_for_strategy": (
            context.feature_trust.after.board_count.usable_for_strategy
        ),
        "boundary_gold_delta_semantics": (
            context.feature_trust.boundary_gold_delta_semantics
        ),
        "economy_source_for_action_spend": (
            context.feature_trust.economy_source_for_action_spend
        ),
    }


def analyze_context_episode(
    episode: DecisionEpisode,
    context: EpisodePlayerContext,
    actions_by_id: dict[str, InferredAction],
    settings: ContextReviewAnalyzerSettings,
) -> tuple[list[Finding], dict[str, int]]:
    findings: list[Finding] = []
    stats = {
        "strategic_episode_blocked_infeasible": 0,
        "board_rule_eligible": 0,
        "board_rule_skipped_untrusted": 0,
    }

    action_metrics = _action_metrics(
        episode,
        actions_by_id,
    )
    common = _common_metrics(
        episode,
        context,
        action_metrics,
    )

    # Hard reconstruction contradiction blocks context-aware strategic review.
    # It cannot be repaired by adding context around the episode.
    if bool(common["economy_infeasible"]):
        stats["strategic_episode_blocked_infeasible"] = 1
        findings.append(
            _base(
                episode,
                context,
                code="context_review_blocked_infeasible",
                category="data_quality.context_review_block",
                title="Context review blocked by infeasible economy",
                interpretation="data_quality",
                severity="major",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    "This episode contains an economy constraint contradiction. "
                    "Context-aware strategic review is intentionally suppressed "
                    "until the upstream reconstruction is resolved."
                ),
                limitations=(
                    "This is a reconstruction-quality block, not a player decision grade.",
                ),
            )
        )
        return findings, stats

    hp_before = common["hp_before"]
    hp_after = common["hp_after"]
    pressure_hp = common["pressure_hp"]
    gold_before = common["gold_before"]
    gold_after = common["gold_after"]
    level_before = common["level_before"]
    level_after = common["level_after"]
    level_delta = common["level_delta"]

    spend = int(common["observed_spend"] or 0)
    reroll_count = int(common["reroll_action_count"] or 0)
    action_count = int(common["action_count"] or 0)

    under_pressure = (
        pressure_hp is not None
        and pressure_hp <= settings.pressure_hp_threshold
    )
    critical_hp = (
        pressure_hp is not None
        and pressure_hp <= settings.critical_hp_threshold
    )
    near_elimination = (
        pressure_hp is not None
        and pressure_hp <= settings.near_elimination_hp_threshold
    )

    common.update(
        {
            "under_pressure": under_pressure,
            "critical_hp": critical_hp,
            "near_elimination": near_elimination,
            "pressure_hp_threshold": settings.pressure_hp_threshold,
            "critical_hp_threshold": settings.critical_hp_threshold,
            "near_elimination_hp_threshold": (
                settings.near_elimination_hp_threshold
            ),
        }
    )

    limitations = (
        "This is a review candidate, not a claim that the decision was wrong.",
        "Board strength, opponent boards, streak, traits, items and meta policy are not yet modeled.",
        "Sparse screenshots preserve only window-level partial order.",
    )

    # Economy commitment under low HP. Large spend gets a distinct stronger
    # landmark instead of emitting both generic and large-spend findings.
    if (
        settings.emit_economy_commitment_under_pressure
        and under_pressure
        and spend >= settings.economy_commitment_spend_threshold
    ):
        if spend >= settings.large_spend_under_pressure_threshold:
            code = "large_spend_under_pressure"
            title = "Large economy commitment under HP pressure"
            severity = "major" if critical_hp else "minor"
        else:
            code = "economy_commitment_under_pressure"
            title = "Economy commitment under HP pressure"
            severity = "minor"

        findings.append(
            _base(
                episode,
                context,
                code=code,
                category="review.context.economy_pressure",
                title=title,
                interpretation="review_candidate",
                severity=severity,
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"The episode occurs at pressure HP={pressure_hp} and "
                    f"contains {spend} gold of observed action spend. "
                    "This is a useful post-game review landmark; no optimality "
                    "claim is made."
                ),
                limitations=limitations,
            )
        )

    if (
        settings.emit_low_hp_roll_activity
        and under_pressure
        and reroll_count > 0
    ):
        findings.append(
            _base(
                episode,
                context,
                code="low_hp_roll_activity",
                category="review.context.roll_pressure",
                title="Roll activity under HP pressure",
                interpretation="review_candidate",
                severity="major" if critical_hp else "minor",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"Shop refresh activity is observed while pressure HP="
                    f"{pressure_hp}. Review this episode together with board "
                    "strength and upgrade targets when those features become available."
                ),
                limitations=limitations,
            )
        )

    if (
        settings.emit_low_hp_level_up
        and under_pressure
        and level_delta is not None
        and level_delta > 0
    ):
        findings.append(
            _base(
                episode,
                context,
                code="low_hp_level_up",
                category="review.context.level_pressure",
                title="Level-up under HP pressure",
                interpretation="review_candidate",
                severity="major" if critical_hp else "minor",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"The observed state moves from level {level_before} to "
                    f"{level_after} at pressure HP={pressure_hp}. This identifies "
                    "a tempo commitment worth reviewing, without asserting that "
                    "the level-up was correct or incorrect."
                ),
                limitations=limitations,
            )
        )

    # Holding substantial gold while critically low is a review landmark only.
    # We use the trusted boundary value, never derive it from action spend.
    if (
        settings.emit_high_gold_under_pressure
        and critical_hp
        and gold_after is not None
        and gold_after >= settings.high_gold_under_pressure_threshold
    ):
        findings.append(
            _base(
                episode,
                context,
                code="high_gold_under_pressure",
                category="review.context.gold_pressure",
                title="Substantial gold remains under critical HP pressure",
                interpretation="review_candidate",
                severity="major",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"The trusted post-episode HUD shows gold={gold_after} at "
                    f"pressure HP={pressure_hp}. This is surfaced for review, "
                    "not labeled as greed or a mistake without board/lobby context."
                ),
                limitations=limitations + (
                    "Boundary gold is an observed state value; action accounting still comes from episode.economy.",
                ),
            )
        )

    if (
        settings.emit_near_elimination_activity
        and near_elimination
        and action_count > 0
    ):
        findings.append(
            _base(
                episode,
                context,
                code="near_elimination_activity",
                category="review.context.near_elimination",
                title="Observed activity near elimination",
                interpretation="review_candidate",
                severity="major",
                confidence=episode.confidence,
                settings=settings,
                metrics=common,
                explanation=(
                    f"Semantic activity is observed at HP={pressure_hp}, inside "
                    "the near-elimination threshold. This episode should be kept "
                    "as a high-priority review landmark."
                ),
                limitations=limitations,
            )
        )

    # Board-dependent review rule demonstrates the trust contract. It may only
    # run when the exact boundary itself is certified usable_for_strategy.
    if settings.emit_trusted_board_below_capacity:
        board_trust = context.feature_trust.after.board_count
        if (
            board_trust.usable_for_strategy
            and context.after.board_count is not None
            and context.after.board_capacity is not None
        ):
            stats["board_rule_eligible"] = 1
            if context.after.board_count < context.after.board_capacity:
                findings.append(
                    _base(
                        episode,
                        context,
                        code="trusted_board_below_capacity",
                        category="review.context.board_capacity",
                        title="Trusted board snapshot is below level capacity",
                        interpretation="review_candidate",
                        severity="minor",
                        confidence=episode.confidence,
                        settings=settings,
                        metrics=common,
                        explanation=(
                            f"A strong trusted board boundary contains "
                            f"{context.after.board_count}/"
                            f"{context.after.board_capacity} units. Because this "
                            "boundary is certified exact, the capacity gap may be "
                            "reviewed literally."
                        ),
                        limitations=(
                            "This still does not grade the choice without unit identities, traits, items and tactical context.",
                        ),
                    )
                )
        else:
            stats["board_rule_skipped_untrusted"] = 1

    return findings, stats


def analyze_context_episodes(
    episodes: list[DecisionEpisode],
    contexts: list[EpisodePlayerContext],
    actions: list[InferredAction],
    settings: ContextReviewAnalyzerSettings,
) -> tuple[list[Finding], dict[str, int]]:
    actions_by_id = {
        action.action_id: action
        for action in actions
    }
    contexts_by_decision = {
        context.decision_id: context
        for context in contexts
    }

    findings: list[Finding] = []
    totals = {
        "strategic_episode_blocked_infeasible": 0,
        "board_rule_eligible": 0,
        "board_rule_skipped_untrusted": 0,
        "missing_context_episode_count": 0,
    }

    for episode in episodes:
        context = contexts_by_decision.get(episode.decision_id)
        if context is None:
            totals["missing_context_episode_count"] += 1
            continue

        episode_findings, stats = analyze_context_episode(
            episode,
            context,
            actions_by_id,
            settings,
        )
        findings.extend(episode_findings)
        for key, value in stats.items():
            totals[key] += value

    return findings, totals
