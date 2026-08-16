from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata

from .models import (
    ChampionCatalogSnapshot,
    ChampionCostResolution,
    SetInferenceScore,
)


_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
_SET_ID_RE = re.compile(r"^(TFT\d+)_")


def normalize_champion_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    text = text.casefold()
    text = text.replace("&", " and ")
    return _NON_ALNUM_RE.sub("", text)


class ChampionCostCatalog:
    def __init__(self, snapshot: ChampionCatalogSnapshot) -> None:
        self.snapshot = snapshot
        by_name = defaultdict(list)

        for entry in snapshot.champions:
            if entry.normalized_name:
                by_name[entry.normalized_name].append(entry)

        self._by_name = dict(by_name)

    @classmethod
    def from_file(cls, path: Path | str) -> "ChampionCostCatalog":
        path = Path(path)
        snapshot = ChampionCatalogSnapshot.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        return cls(snapshot)

    @staticmethod
    def entry_set_id(champion_id: str) -> str | None:
        match = _SET_ID_RE.match(str(champion_id))
        return match.group(1) if match else None

    def entries_for_set(self, set_id: str):
        set_id = str(set_id).upper()
        return tuple(
            entry
            for entry in self.snapshot.champions
            if self.entry_set_id(entry.champion_id) == set_id
        )

    def scoped_champion_count(self, set_id: str) -> int:
        return len(self.entries_for_set(set_id))

    def candidate_sets(self, name: str) -> tuple[str, ...]:
        normalized = normalize_champion_name(name)
        values = {
            set_id
            for entry in self._by_name.get(normalized, ())
            if (
                set_id := self.entry_set_id(
                    entry.champion_id
                )
            ) is not None
        }
        return tuple(sorted(values))

    def resolve_cost(
        self,
        name: str,
        *,
        set_id: str | None = None,
    ) -> ChampionCostResolution:
        normalized = normalize_champion_name(name)
        candidates = list(self._by_name.get(normalized, ()))

        if set_id is not None:
            normalized_set = str(set_id).upper()
            candidates = [
                entry
                for entry in candidates
                if self.entry_set_id(entry.champion_id)
                == normalized_set
            ]

        if not candidates:
            return ChampionCostResolution(
                query=str(name),
                normalized_query=normalized,
                status="missing",
                cost=None,
                provider=self.snapshot.provider,
                version=self.snapshot.version,
                locale=self.snapshot.locale,
            )

        candidate_ids = tuple(
            entry.champion_id
            for entry in candidates
        )
        candidate_names = tuple(
            entry.name
            for entry in candidates
        )
        tiers = tuple(
            sorted(
                {
                    int(entry.tier)
                    for entry in candidates
                    if entry.tier is not None
                    and int(entry.tier) > 0
                }
            )
        )

        if len(tiers) == 1:
            return ChampionCostResolution(
                query=str(name),
                normalized_query=normalized,
                status=(
                    "resolved_unique"
                    if len(candidates) == 1
                    else "resolved_consensus"
                ),
                cost=tiers[0],
                candidate_ids=candidate_ids,
                candidate_names=candidate_names,
                candidate_tiers=tiers,
                provider=self.snapshot.provider,
                version=self.snapshot.version,
                locale=self.snapshot.locale,
            )

        return ChampionCostResolution(
            query=str(name),
            normalized_query=normalized,
            status="ambiguous",
            cost=None,
            candidate_ids=candidate_ids,
            candidate_names=candidate_names,
            candidate_tiers=tiers,
            provider=self.snapshot.provider,
            version=self.snapshot.version,
            locale=self.snapshot.locale,
        )


def load_champion_cost_catalog(
    path: Path | str,
) -> ChampionCostCatalog:
    return ChampionCostCatalog.from_file(path)



def infer_set_from_roster(
    catalog: ChampionCostCatalog,
    names: list[str] | tuple[str, ...] | set[str],
) -> tuple[
    str | None,
    float | None,
    float | None,
    tuple[SetInferenceScore, ...],
]:
    """
    Fallback-only set inference from observed champion names.

    Each observed name gives one vote distributed across every TFT<N> set in
    which that exact normalized display name exists. Names unique to one set
    therefore act as strong anchors; common names are weak evidence.
    """
    unique_names = sorted(
        {
            str(name).strip()
            for name in names
            if str(name).strip()
        }
    )

    score_by_set: dict[str, float] = {}
    support_by_set: dict[str, list[str]] = {}
    unique_by_set: dict[str, list[str]] = {}

    for name in unique_names:
        sets = catalog.candidate_sets(name)
        if not sets:
            continue

        weight = 1.0 / len(sets)
        for set_id in sets:
            score_by_set[set_id] = (
                score_by_set.get(set_id, 0.0)
                + weight
            )
            support_by_set.setdefault(
                set_id,
                [],
            ).append(name)

        if len(sets) == 1:
            unique_by_set.setdefault(
                sets[0],
                [],
            ).append(name)

    ranked = sorted(
        score_by_set,
        key=lambda set_id: (
            score_by_set[set_id],
            len(unique_by_set.get(set_id, ())),
            set_id,
        ),
        reverse=True,
    )

    scores = tuple(
        SetInferenceScore(
            set_id=set_id,
            score=score_by_set[set_id],
            supporting_names=tuple(
                sorted(
                    set(support_by_set.get(set_id, ()))
                )
            ),
            unique_anchor_names=tuple(
                sorted(
                    set(unique_by_set.get(set_id, ()))
                )
            ),
        )
        for set_id in ranked
    )

    if not ranked:
        return None, None, None, scores

    top = ranked[0]
    top_score = score_by_set[top]
    second_score = (
        score_by_set[ranked[1]]
        if len(ranked) > 1
        else 0.0
    )
    total = sum(score_by_set.values())
    confidence = (
        top_score / total
        if total > 0
        else 0.0
    )
    margin = top_score - second_score

    # Fallback must be conservative. Require at least two champion names that
    # are unique anchors for the winning TFT set plus a positive weighted
    # margin. Explicit context always bypasses this heuristic.
    unique_anchor_count = len(
        unique_by_set.get(top, ())
    )
    accepted = (
        unique_anchor_count >= 2
        and confidence >= 0.45
        and margin >= 0.75
    )

    return (
        top if accepted else None,
        confidence,
        margin,
        scores,
    )
