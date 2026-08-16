from __future__ import annotations

from collections import Counter, defaultdict
import hashlib

from tft_analyzer.actions.models import InferredAction
from tft_analyzer.core.enums import ActionType
from tft_analyzer.core.models.decisions import DecisionEpisode
from tft_analyzer.game_data import normalize_champion_name

from .models import (
    EpisodeRosterEvidence,
    RosterActionEvidence,
    RosterChampionEvidence,
    RosterEpisodeDelta,
    RosterEvidenceSettings,
    RosterEvidenceSnapshot,
)


_RELEVANT_TYPES = {
    ActionType.BUY_UNIT,
    ActionType.SELL_UNIT,
    ActionType.UNKNOWN_ECON_ACTION,
}


class _Accumulator:
    def __init__(
        self,
        settings: RosterEvidenceSettings,
    ) -> None:
        self.settings = settings

        self.confirmed_acquired = Counter()
        self.candidate_acquired = Counter()
        self.identified_sell_units = Counter()

        self.unidentified_confirmed_buys = 0
        self.unidentified_candidate_buys = 0

        self.unidentified_sell_units = 0

        self.unresolved_economy_actions = 0
        self.unresolved_spend_min = 0
        self.unresolved_spend_max = 0

    def snapshot(self) -> RosterEvidenceSnapshot:
        champions = sorted(
            set(self.confirmed_acquired)
            | set(self.candidate_acquired)
            | set(self.identified_sell_units)
        )

        items = []
        for champion in champions:
            confirmed = int(
                self.confirmed_acquired[champion]
            )
            candidate = int(
                self.candidate_acquired[champion]
            )
            identified_sell_units = int(
                self.identified_sell_units[champion]
            )

            items.append(
                RosterChampionEvidence(
                    champion=champion,
                    confirmed_acquired_copy_lower_bound=confirmed,
                    candidate_acquired_copy_count=candidate,
                    identified_sell_unit_count=identified_sell_units,
                    current_ownership_status="not_established",
                )
            )

        confirmed_identity = sum(
            self.confirmed_acquired.values()
        )
        candidate_identity = sum(
            self.candidate_acquired.values()
        )
        observed_buy_copies = (
            confirmed_identity
            + candidate_identity
            + self.unidentified_confirmed_buys
            + self.unidentified_candidate_buys
        )
        coverage = (
            confirmed_identity / observed_buy_copies
            if observed_buy_copies
            else 1.0
        )

        return RosterEvidenceSnapshot(
            acquisition_semantics="confirmed_history_lower_bound",
            complete_roster_known=False,
            complete_sell_history_known=False,
            current_ownership_status="not_established",
            champions=tuple(items),
            confirmed_identity_buy_copy_count=confirmed_identity,
            candidate_identity_buy_copy_count=candidate_identity,
            unidentified_confirmed_buy_copy_count=(
                self.unidentified_confirmed_buys
            ),
            unidentified_candidate_buy_copy_count=(
                self.unidentified_candidate_buys
            ),
            identified_sell_unit_count=sum(
                self.identified_sell_units.values()
            ),
            unidentified_sell_unit_count_lower_bound=(
                self.unidentified_sell_units
            ),
            unresolved_economy_action_count=(
                self.unresolved_economy_actions
            ),
            unresolved_economy_spend_min_total=(
                self.unresolved_spend_min
            ),
            unresolved_economy_spend_max_total=(
                self.unresolved_spend_max
            ),
            confirmed_buy_identity_coverage=coverage,
        )


def _normalized_champions(
    action: InferredAction,
) -> tuple[str, ...]:
    raw = action.params.get("champions")
    values = []

    if isinstance(raw, (list, tuple)):
        values.extend(raw)

    single = action.params.get("champion")
    if single and not values:
        values.append(single)

    result = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = normalize_champion_name(value)
        if normalized:
            result.append(normalized)
    return tuple(result)


def _count(
    action: InferredAction,
    *,
    fallback: int,
) -> int:
    for key in (
        "count",
        "count_min",
        "count_lower_bound",
    ):
        value = action.params.get(key)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            pass
    return max(0, int(fallback))


def _classify_buy(
    action: InferredAction,
    settings: RosterEvidenceSettings,
) -> tuple[
    RosterActionEvidence,
    dict[str, int],
    dict[str, int],
    int,
    int,
]:
    champions = _normalized_champions(action)
    count = _count(
        action,
        fallback=len(champions),
    )
    count = max(count, len(champions))

    cost_validation = action.params.get(
        "cost_validation"
    )
    cost_conflict = (
        str(cost_validation) == "cost_conflict"
    )

    confirmed = (
        action.confidence
        >= settings.min_confirmed_buy_confidence
        and not (
            settings.exclude_cost_conflict_from_confirmed
            and cost_conflict
        )
    )

    identified_counts = Counter(
        champions[:count]
    )
    unidentified = max(
        0,
        count - len(champions[:count]),
    )

    if confirmed:
        status = (
            "confirmed_identity_buy"
            if identified_counts
            else "unidentified_buy"
        )
        reason = "supported_buy_identity"
        confirmed_counts = dict(
            identified_counts
        )
        candidate_counts = {}
        unidentified_confirmed = unidentified
        unidentified_candidate = 0
    else:
        status = (
            "candidate_identity_buy"
            if identified_counts
            else "unidentified_buy"
        )
        if cost_conflict:
            reason = "buy_cost_conflict"
        elif (
            action.confidence
            < settings.min_confirmed_buy_confidence
        ):
            reason = "buy_confidence_below_confirmed_threshold"
        else:
            reason = "buy_identity_not_confirmed"
        confirmed_counts = {}
        candidate_counts = dict(
            identified_counts
        )
        unidentified_confirmed = 0
        unidentified_candidate = unidentified

    evidence = RosterActionEvidence(
        action_id=action.action_id,
        action_type=action.action_type.value,
        status=status,
        confidence=action.confidence,
        champions=champions,
        count=count,
        cost_validation=(
            str(cost_validation)
            if cost_validation is not None
            else None
        ),
        reason=reason,
        evidence_ids=action.evidence_ids,
    )
    return (
        evidence,
        confirmed_counts,
        candidate_counts,
        unidentified_confirmed,
        unidentified_candidate,
    )


def _classify_sell(
    action: InferredAction,
) -> tuple[
    RosterActionEvidence,
    dict[str, int],
    int,
]:
    champions = _normalized_champions(action)
    count = _count(
        action,
        fallback=max(1, len(champions)),
    )

    identity_available = bool(
        action.params.get("identity_available")
    )
    identified = (
        identity_available
        and bool(champions)
    )

    if identified:
        # Current upstream SELL_UNIT has no identity, but keep the contract
        # future-ready. Count denotes sold unit objects, not copy equivalents.
        counts = Counter(
            champions[:count]
        )
        if sum(counts.values()) < count and champions:
            counts[champions[0]] += (
                count - sum(counts.values())
            )

        evidence = RosterActionEvidence(
            action_id=action.action_id,
            action_type=action.action_type.value,
            status="identified_sell",
            confidence=action.confidence,
            champions=champions,
            count=count,
            reason="sell_identity_available",
            evidence_ids=action.evidence_ids,
        )
        return evidence, dict(counts), 0

    evidence = RosterActionEvidence(
        action_id=action.action_id,
        action_type=action.action_type.value,
        status="unidentified_sell",
        confidence=action.confidence,
        champions=(),
        count=count,
        reason="sell_identity_unavailable",
        evidence_ids=action.evidence_ids,
    )
    return evidence, {}, count


def _classify_unknown_economy(
    action: InferredAction,
) -> tuple[
    RosterActionEvidence,
    int,
    int,
]:
    params = action.params
    spend_min = int(
        params.get(
            "unallocated_spend_min",
            0,
        )
        or 0
    )
    spend_max = int(
        params.get(
            "unallocated_spend_max",
            spend_min,
        )
        or spend_min
    )
    spend_max = max(
        spend_min,
        spend_max,
    )

    evidence = RosterActionEvidence(
        action_id=action.action_id,
        action_type=action.action_type.value,
        status="unresolved_economy",
        confidence=action.confidence,
        count=1,
        reason=(
            "required_unresolved_spend_can_hide_unobserved_roster_changes"
        ),
        evidence_ids=action.evidence_ids,
    )
    return evidence, spend_min, spend_max


def _context_id(
    decision_id: str,
    producer_version: str,
) -> str:
    raw = f"{decision_id}|{producer_version}"
    digest = hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:14]
    return f"roster-{digest}"


def build_episode_roster_evidence(
    episode: DecisionEpisode,
    *,
    actions_by_id: dict[str, InferredAction],
    accumulator: _Accumulator,
    settings: RosterEvidenceSettings,
    source_action_producer_version: str | None,
) -> EpisodeRosterEvidence:
    before = accumulator.snapshot()

    confirmed_buys = Counter()
    candidate_buys = Counter()
    identified_sells = Counter()

    unidentified_confirmed = 0
    unidentified_candidate = 0
    unidentified_sells = 0

    unknown_econ_count = 0
    unresolved_min = 0
    unresolved_max = 0
    action_evidence = []

    # Episode action groups preserve only partial order. Roster delta semantics
    # intentionally aggregate the whole episode; no exact intra-window purchase
    # sequence is reconstructed.
    for action_id in episode.action_ids:
        action = actions_by_id.get(
            action_id
        )
        if action is None:
            continue

        if action.action_type == ActionType.BUY_UNIT:
            (
                evidence,
                confirmed,
                candidate,
                missing_confirmed,
                missing_candidate,
            ) = _classify_buy(
                action,
                settings,
            )
            action_evidence.append(
                evidence
            )
            confirmed_buys.update(
                confirmed
            )
            candidate_buys.update(
                candidate
            )
            unidentified_confirmed += (
                missing_confirmed
            )
            unidentified_candidate += (
                missing_candidate
            )

        elif action.action_type == ActionType.SELL_UNIT:
            (
                evidence,
                identified,
                unidentified,
            ) = _classify_sell(
                action
            )
            action_evidence.append(
                evidence
            )
            identified_sells.update(
                identified
            )
            unidentified_sells += (
                unidentified
            )

        elif (
            action.action_type
            == ActionType.UNKNOWN_ECON_ACTION
        ):
            (
                evidence,
                spend_min,
                spend_max,
            ) = _classify_unknown_economy(
                action
            )
            action_evidence.append(
                evidence
            )
            unknown_econ_count += 1
            unresolved_min += spend_min
            unresolved_max += spend_max

    accumulator.confirmed_acquired.update(
        confirmed_buys
    )
    accumulator.candidate_acquired.update(
        candidate_buys
    )
    accumulator.identified_sell_units.update(
        identified_sells
    )

    accumulator.unidentified_confirmed_buys += (
        unidentified_confirmed
    )
    accumulator.unidentified_candidate_buys += (
        unidentified_candidate
    )
    accumulator.unidentified_sell_units += (
        unidentified_sells
    )
    accumulator.unresolved_economy_actions += (
        unknown_econ_count
    )
    accumulator.unresolved_spend_min += (
        unresolved_min
    )
    accumulator.unresolved_spend_max += (
        unresolved_max
    )

    after = accumulator.snapshot()

    return EpisodeRosterEvidence(
        roster_context_id=_context_id(
            episode.decision_id,
            settings.producer_version,
        ),
        match_id=episode.match_id,
        decision_id=episode.decision_id,
        stage_start=episode.stage_start,
        stage_end=episode.stage_end,
        start_timestamp_s=(
            episode.start_timestamp_s
        ),
        end_timestamp_s=(
            episode.end_timestamp_s
        ),
        before=before,
        delta=RosterEpisodeDelta(
            confirmed_buys=dict(
                sorted(
                    confirmed_buys.items()
                )
            ),
            candidate_buys=dict(
                sorted(
                    candidate_buys.items()
                )
            ),
            unidentified_confirmed_buy_copy_count=(
                unidentified_confirmed
            ),
            unidentified_candidate_buy_copy_count=(
                unidentified_candidate
            ),
            identified_sells=dict(
                sorted(
                    identified_sells.items()
                )
            ),
            unidentified_sell_unit_count_lower_bound=(
                unidentified_sells
            ),
            unresolved_economy_action_count=(
                unknown_econ_count
            ),
            unresolved_economy_spend_min=(
                unresolved_min
            ),
            unresolved_economy_spend_max=(
                unresolved_max
            ),
            action_evidence=tuple(
                action_evidence
            ),
        ),
        after=after,
        source_episode_producer_version=(
            episode.extractor_version
        ),
        source_action_producer_version=(
            source_action_producer_version
        ),
        producer_version=(
            settings.producer_version
        ),
    )


def build_roster_evidence(
    episodes: list[DecisionEpisode],
    actions: list[InferredAction],
    settings: RosterEvidenceSettings,
    *,
    source_action_producer_version: str | None = None,
) -> tuple[
    list[EpisodeRosterEvidence],
    dict[str, int],
]:
    actions_by_id = {
        action.action_id: action
        for action in actions
    }

    relevant_action_ids = {
        action.action_id
        for action in actions
        if action.action_type in _RELEVANT_TYPES
    }
    covered_action_ids = {
        action_id
        for episode in episodes
        for action_id in episode.action_ids
    }
    uncovered_relevant = (
        relevant_action_ids
        - covered_action_ids
    )

    if (
        settings.require_relevant_action_coverage
        and uncovered_relevant
    ):
        preview = ", ".join(
            sorted(uncovered_relevant)[:8]
        )
        raise ValueError(
            "Roster evidence requires all BUY/SELL/"
            "UNKNOWN_ECON actions to belong to "
            f"DecisionEpisodes. Uncovered: {preview}"
        )

    accumulator = _Accumulator(
        settings
    )
    contexts = []

    for episode in sorted(
        episodes,
        key=lambda item: (
            item.start_timestamp_s,
            item.end_timestamp_s,
            item.decision_id,
        ),
    ):
        contexts.append(
            build_episode_roster_evidence(
                episode,
                actions_by_id=actions_by_id,
                accumulator=accumulator,
                settings=settings,
                source_action_producer_version=(
                    source_action_producer_version
                ),
            )
        )

    stats = {
        "roster_relevant_action_count": len(
            relevant_action_ids
        ),
        "covered_roster_relevant_action_count": len(
            relevant_action_ids
            & covered_action_ids
        ),
        "uncovered_roster_relevant_action_count": len(
            uncovered_relevant
        ),
    }
    return contexts, stats
