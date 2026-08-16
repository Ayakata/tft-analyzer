from __future__ import annotations

import hashlib

from tft_analyzer.core.models.decisions import (
    DecisionBoundaryState,
    DecisionEpisode,
)
from tft_analyzer.core.models.tracking import TrackedHUDState
from tft_analyzer.tracking.board.models import (
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)

from .models import (
    EpisodeBoundaryTrust,
    EpisodeContextFeatureTrust,
    EpisodeContextQuality,
    EpisodeContextSettings,
    EpisodeFeatureTrust,
    EpisodePlayerContext,
    EpisodePlayerStateDelta,
    EpisodePlayerStateFeature,
    EpisodeTrackedFieldMeta,
)


_HUD_FIELDS = ("stage", "gold", "level", "xp", "hp")


def _dict_int(field, key: str) -> int | None:
    value = field.value
    if not isinstance(value, dict):
        return None
    raw = value.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _stage(field) -> str | None:
    value = field.value
    if not isinstance(value, dict):
        return None
    stage = value.get("stage")
    round_ = value.get("round")
    if stage is None or round_ is None:
        return None
    try:
        return f"{int(stage)}-{int(round_)}"
    except (TypeError, ValueError):
        return None


def _xp(field) -> tuple[int | None, int | None]:
    return _dict_int(field, "current"), _dict_int(field, "required")


def _field_meta(field) -> EpisodeTrackedFieldMeta:
    return EpisodeTrackedFieldMeta(
        status=field.status,
        confidence=float(field.confidence),
        age_s=field.age_s,
        source_evidence_id=field.source_evidence_id,
        source_timestamp_s=field.source_timestamp_s,
    )


def _ratio(value: int | None, capacity: int | None) -> float | None:
    if value is None or capacity is None or capacity <= 0:
        return None
    return float(value) / float(capacity)


def _fallback_state(boundary: DecisionBoundaryState) -> EpisodePlayerStateFeature:
    capacity = boundary.level
    return EpisodePlayerStateFeature(
        timestamp_s=float(boundary.timestamp_s),
        evidence_id=str(boundary.evidence_id),
        stage=boundary.stage,
        hp=None,
        gold=boundary.gold,
        level=boundary.level,
        xp_absolute=boundary.xp_absolute,
        board_count=boundary.board_count,
        board_capacity=capacity,
        board_utilization=_ratio(boundary.board_count, capacity),
        bench_count=boundary.bench_count,
        bench_utilization=_ratio(boundary.bench_count, 9),
        source_alignment="episode_boundary_fallback",
    )


def build_boundary_feature(
    boundary: DecisionBoundaryState,
    *,
    hud: TrackedHUDState | None,
    board: TrackedBoardOccupancyState | None,
    bench: TrackedBenchOccupancyState | None,
) -> EpisodePlayerStateFeature:
    if hud is None or board is None or bench is None:
        # Preserve the already accepted Stage 4.1 boundary rather than dropping
        # the whole episode. Missing tracker streams remain explicit in quality.
        fallback = _fallback_state(boundary)

        # Fill any exact streams that are available without pretending the
        # boundary has full evidence alignment.
        update = fallback.model_dump()
        if hud is not None:
            xp_current, xp_required = _xp(hud.xp)
            update.update(
                stage=_stage(hud.stage) or fallback.stage,
                hp=_dict_int(hud.hp, "hp"),
                gold=_dict_int(hud.gold, "gold") if _dict_int(hud.gold, "gold") is not None else fallback.gold,
                level=_dict_int(hud.level, "level") if _dict_int(hud.level, "level") is not None else fallback.level,
                xp_current=xp_current,
                xp_required=xp_required,
                hud_fields={name: _field_meta(getattr(hud, name)) for name in _HUD_FIELDS},
            )
        if board is not None:
            update.update(
                board_count=int(board.occupied_count),
                board_usable=bool(board.usable),
                board_stability=board.stability,
                board_gate_reason=board.gate_reason,
                board_scene_valid=bool(board.scene_valid),
                board_scene_score=board.scene_score,
                board_capacity_status=board.capacity_status,
                board_strong_snapshot=bool(board.strong_snapshot),
                board_uncertain_count=int(board.uncertain_count),
            )
        if bench is not None:
            update.update(
                bench_count=int(bench.occupied_count),
                bench_uncertain_count=int(bench.uncertain_count),
            )
        level = update.get("level")
        update["board_capacity"] = level
        update["board_utilization"] = _ratio(update.get("board_count"), level)
        update["bench_utilization"] = _ratio(update.get("bench_count"), 9)
        update["source_alignment"] = "episode_boundary_fallback"
        return EpisodePlayerStateFeature.model_validate(update)

    xp_current, xp_required = _xp(hud.xp)
    level = _dict_int(hud.level, "level")
    # The action/episode layer already has match-local absolute XP. Reuse that
    # accepted value instead of deriving a second progression model here.
    return EpisodePlayerStateFeature(
        timestamp_s=float(boundary.timestamp_s),
        evidence_id=str(boundary.evidence_id),
        stage=_stage(hud.stage) or boundary.stage,
        hp=_dict_int(hud.hp, "hp"),
        gold=_dict_int(hud.gold, "gold"),
        level=level,
        xp_current=xp_current,
        xp_required=xp_required,
        xp_absolute=boundary.xp_absolute,
        board_count=int(board.occupied_count),
        board_capacity=level,
        board_utilization=_ratio(int(board.occupied_count), level),
        bench_count=int(bench.occupied_count),
        bench_utilization=_ratio(int(bench.occupied_count), 9),
        board_usable=bool(board.usable),
        board_stability=board.stability,
        board_gate_reason=board.gate_reason,
        board_scene_valid=bool(board.scene_valid),
        board_scene_score=board.scene_score,
        board_capacity_status=board.capacity_status,
        board_strong_snapshot=bool(board.strong_snapshot),
        board_uncertain_count=int(board.uncertain_count),
        bench_uncertain_count=int(bench.uncertain_count),
        hud_fields={name: _field_meta(getattr(hud, name)) for name in _HUD_FIELDS},
        source_alignment="exact_evidence",
    )



def _exact_trust(
    value,
    *,
    source: str,
    reason: str = "evidence_aligned_observed_value",
) -> EpisodeFeatureTrust:
    known = value is not None
    return EpisodeFeatureTrust(
        known=known,
        semantics="exact" if known else "unknown",
        usable_for_strategy=known,
        reason=reason if known else "value_missing",
        source=source,
    )


def _board_feature_trust(
    state: EpisodePlayerStateFeature,
) -> tuple[EpisodeFeatureTrust, EpisodeFeatureTrust]:
    count_known = state.board_count is not None
    util_known = state.board_utilization is not None

    if state.board_scene_valid is False:
        return (
            EpisodeFeatureTrust(
                known=count_known,
                semantics="unusable" if count_known else "unknown",
                usable_for_strategy=False,
                reason="scene_invalid",
                source=state.source_alignment,
            ),
            EpisodeFeatureTrust(
                known=util_known,
                semantics="unusable" if util_known else "unknown",
                usable_for_strategy=False,
                reason="scene_invalid",
                source=state.source_alignment,
            ),
        )

    # Literal board count is certified only by a strong, usable snapshot.
    if (
        count_known
        and state.board_usable is True
        and state.board_strong_snapshot is True
    ):
        reason = "strong_board_snapshot"
        if state.board_capacity_status:
            reason += f":{state.board_capacity_status}"
        return (
            EpisodeFeatureTrust(
                known=True,
                semantics="exact",
                usable_for_strategy=True,
                reason=reason,
                source=state.source_alignment,
            ),
            EpisodeFeatureTrust(
                known=util_known,
                semantics="exact" if util_known else "unknown",
                usable_for_strategy=util_known,
                reason=reason if util_known else "board_utilization_missing",
                source=state.source_alignment,
            ),
        )

    gate_reason = str(state.board_gate_reason or "")
    carried = "carry" in gate_reason.lower()
    count_semantics = "carried" if carried else "lower_bound"

    count_reason = "conservative_tracker_not_strong_snapshot"
    if state.board_usable is False:
        count_reason = "board_gate_not_usable"
    if gate_reason:
        count_reason += f":{gate_reason}"

    return (
        EpisodeFeatureTrust(
            known=count_known,
            semantics=count_semantics if count_known else "unknown",
            usable_for_strategy=False,
            reason=count_reason if count_known else "board_count_missing",
            source=state.source_alignment,
        ),
        EpisodeFeatureTrust(
            known=util_known,
            semantics=(
                count_semantics
                if util_known
                else "unknown"
            ),
            usable_for_strategy=False,
            reason=(
                "derived_from_non_exact_board_count"
                if util_known
                else "board_utilization_missing"
            ),
            source=state.source_alignment,
        ),
    )


def _bench_feature_trust(
    state: EpisodePlayerStateFeature,
) -> EpisodeFeatureTrust:
    known = state.bench_count is not None
    if state.board_scene_valid is False:
        return EpisodeFeatureTrust(
            known=known,
            semantics="unusable" if known else "unknown",
            usable_for_strategy=False,
            reason="scene_invalid",
            source=state.source_alignment,
        )

    # 0.17.1 intentionally does not certify exact bench occupancy: the current
    # temporal bench tracker can carry state across guarded frames.
    return EpisodeFeatureTrust(
        known=known,
        semantics="lower_bound" if known else "unknown",
        usable_for_strategy=False,
        reason=(
            "bench_count_not_certified_exact"
            if known
            else "bench_count_missing"
        ),
        source=state.source_alignment,
    )


def build_boundary_trust(
    state: EpisodePlayerStateFeature,
) -> EpisodeBoundaryTrust:
    board_count, board_utilization = _board_feature_trust(state)

    return EpisodeBoundaryTrust(
        hp=_exact_trust(state.hp, source="hud"),
        gold=_exact_trust(state.gold, source="hud"),
        level=_exact_trust(state.level, source="hud"),
        xp_absolute=_exact_trust(
            state.xp_absolute,
            source="accepted_match_local_xp_progression",
        ),
        board_count=board_count,
        board_utilization=board_utilization,
        bench_count=_bench_feature_trust(state),
    )


def build_context_feature_trust(
    before: EpisodePlayerStateFeature,
    after: EpisodePlayerStateFeature,
) -> EpisodeContextFeatureTrust:
    return EpisodeContextFeatureTrust(
        before=build_boundary_trust(before),
        after=build_boundary_trust(after),
    )


def _delta(after, before):
    if after is None or before is None:
        return None
    return after - before


def _missing(state: EpisodePlayerStateFeature) -> tuple[str, ...]:
    fields = {
        "stage": state.stage,
        "hp": state.hp,
        "gold": state.gold,
        "level": state.level,
        "xp_absolute": state.xp_absolute,
        "board_count": state.board_count,
        "bench_count": state.bench_count,
    }
    return tuple(name for name, value in fields.items() if value is None)


def _context_id(decision_id: str, producer_version: str) -> str:
    raw = f"{decision_id}|{producer_version}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]
    return f"context-{digest}"


def build_episode_player_context(
    episode: DecisionEpisode,
    *,
    hud_by_evidence: dict[str, TrackedHUDState],
    board_by_evidence: dict[str, TrackedBoardOccupancyState],
    bench_by_evidence: dict[str, TrackedBenchOccupancyState],
    settings: EpisodeContextSettings,
) -> EpisodePlayerContext:
    if episode.state_before is None or episode.state_after is None:
        raise ValueError(
            f"DecisionEpisode {episode.decision_id} has no boundary states"
        )

    before_id = str(episode.state_before.evidence_id)
    after_id = str(episode.state_after.evidence_id)

    before_hud = hud_by_evidence.get(before_id)
    before_board = board_by_evidence.get(before_id)
    before_bench = bench_by_evidence.get(before_id)
    after_hud = hud_by_evidence.get(after_id)
    after_board = board_by_evidence.get(after_id)
    after_bench = bench_by_evidence.get(after_id)

    before_exact = all(
        value is not None
        for value in (before_hud, before_board, before_bench)
    )
    after_exact = all(
        value is not None
        for value in (after_hud, after_board, after_bench)
    )

    before = build_boundary_feature(
        episode.state_before,
        hud=before_hud,
        board=before_board,
        bench=before_bench,
    )
    after = build_boundary_feature(
        episode.state_after,
        hud=after_hud,
        board=after_board,
        bench=after_bench,
    )

    delta = EpisodePlayerStateDelta(
        hp=_delta(after.hp, before.hp),
        gold=_delta(after.gold, before.gold),
        level=_delta(after.level, before.level),
        xp_absolute=_delta(after.xp_absolute, before.xp_absolute),
        board_count=_delta(after.board_count, before.board_count),
        bench_count=_delta(after.bench_count, before.bench_count),
        board_utilization=_delta(
            after.board_utilization,
            before.board_utilization,
        ),
    )

    economy_feasible = (
        False
        if episode.economy.infeasible_window_count > 0
        else True
    )
    reconstruction_uncertainty = (
        episode.economy.unallocated_spend_max > 0
    )

    quality = EpisodeContextQuality(
        before_exact_alignment=before_exact,
        after_exact_alignment=after_exact,
        hp_known_before=before.hp is not None,
        hp_known_after=after.hp is not None,
        board_known_before=before.board_count is not None,
        board_known_after=after.board_count is not None,
        bench_known_before=before.bench_count is not None,
        bench_known_after=after.bench_count is not None,
        board_utilization_known_before=(before.board_utilization is not None),
        board_utilization_known_after=(after.board_utilization is not None),
        scene_valid_before=before.board_scene_valid,
        scene_valid_after=after.board_scene_valid,
        board_usable_before=before.board_usable,
        board_usable_after=after.board_usable,
        economy_feasible=economy_feasible,
        reconstruction_uncertainty=reconstruction_uncertainty,
        missing_before_fields=_missing(before),
        missing_after_fields=_missing(after),
    )

    return EpisodePlayerContext(
        context_id=_context_id(
            episode.decision_id,
            settings.producer_version,
        ),
        decision_id=episode.decision_id,
        match_id=episode.match_id,
        stage_start=episode.stage_start,
        stage_end=episode.stage_end,
        before=before,
        after=after,
        delta=delta,
        quality=quality,
        feature_trust=build_context_feature_trust(before, after),
        source_episode_producer_version=episode.extractor_version,
        source_hud_tracker_version=(
            before_hud.tracker_version
            if before_hud is not None
            else (
                after_hud.tracker_version
                if after_hud is not None
                else None
            )
        ),
        source_board_tracker_version=(
            before_board.tracker_version
            if before_board is not None
            else (
                after_board.tracker_version
                if after_board is not None
                else None
            )
        ),
        source_bench_tracker_version=(
            before_bench.tracker_version
            if before_bench is not None
            else (
                after_bench.tracker_version
                if after_bench is not None
                else None
            )
        ),
        producer_version=settings.producer_version,
    )
