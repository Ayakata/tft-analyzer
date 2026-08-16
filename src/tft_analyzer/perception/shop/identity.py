from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


def _clamp01(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (ca != cb),
                )
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True, slots=True)
class ShopIdentityResolution:
    resolved_name: str
    identity_method: str
    identity_confidence: float

    ocr_token: str | None = None
    ocr_confidence: float = 0.0

    similarity: float = 1.0
    fuzzy_margin: float = 1.0

    hash_support: int = 0
    hash_ratio: float = 0.0


@dataclass(frozen=True, slots=True)
class HashConsensusEntry:
    visual_hash: str
    resolved_name: str
    support: int
    total_votes: int
    winner_ratio: float
    confidence: float


class ShopIdentityLexicon:
    def __init__(self, names: Iterable[str]) -> None:
        cleaned = sorted({str(name).strip().lower() for name in names if str(name).strip()})
        if not cleaned:
            raise ValueError("Shop identity lexicon is empty")
        self.names = tuple(cleaned)
        self._set = frozenset(cleaned)

    @classmethod
    def from_file(cls, path: Path | str) -> "ShopIdentityLexicon":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Shop identity lexicon not found: {path}")
        names = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line)
        return cls(names)

    def __contains__(self, value: str) -> bool:
        return value in self._set


@dataclass(frozen=True, slots=True)
class ShopIdentityResolverSettings:
    min_fuzzy_similarity: float = 0.82
    min_fuzzy_margin: float = 0.06
    min_hash_support: int = 2
    min_hash_ratio: float = 0.75
    min_consensus_seed_confidence: float = 0.70
    min_hash_identity_confidence: float = 0.72


class ShopIdentityResolver:
    def __init__(
        self,
        lexicon: ShopIdentityLexicon,
        settings: ShopIdentityResolverSettings | None = None,
    ) -> None:
        self.lexicon = lexicon
        self.settings = settings or ShopIdentityResolverSettings()

    def resolve_ocr(
        self,
        token: str | None,
        ocr_confidence: float,
    ) -> ShopIdentityResolution | None:
        token = str(token or "").strip().lower()
        ocr_confidence = _clamp01(ocr_confidence)
        if not token:
            return None

        if token in self.lexicon:
            return ShopIdentityResolution(
                resolved_name=token,
                identity_method="exact_lexicon",
                identity_confidence=ocr_confidence,
                ocr_token=token,
                ocr_confidence=ocr_confidence,
            )

        ranked = []
        for candidate in self.lexicon.names:
            similarity = SequenceMatcher(None, token, candidate).ratio()
            distance = _levenshtein(token, candidate)
            ranked.append((similarity, -distance, candidate, distance))
        ranked.sort(reverse=True)

        best_similarity, _, best_name, best_distance = ranked[0]
        second_similarity = ranked[1][0] if len(ranked) > 1 else 0.0
        margin = best_similarity - second_similarity

        # Very short OCR tokens are dangerous, but a one-character truncation
        # such as orn -> ornn is still resolvable if it is a prefix match and
        # clearly separated from the next lexicon candidate.
        if len(token) <= 3:
            short_ok = (
                best_distance == 1
                and (best_name.startswith(token) or token.startswith(best_name))
                and best_similarity >= 0.85
                and margin >= self.settings.min_fuzzy_margin
            )
            if not short_ok:
                return None
        else:
            max_distance = max(1, min(2, round(len(best_name) * 0.22)))
            if (
                best_similarity < self.settings.min_fuzzy_similarity
                or margin < self.settings.min_fuzzy_margin
                or best_distance > max_distance
            ):
                return None

        identity_confidence = _clamp01(ocr_confidence * best_similarity)
        return ShopIdentityResolution(
            resolved_name=best_name,
            identity_method="fuzzy_lexicon",
            identity_confidence=identity_confidence,
            ocr_token=token,
            ocr_confidence=ocr_confidence,
            similarity=best_similarity,
            fuzzy_margin=margin,
        )

    def build_hash_consensus(
        self,
        samples: Iterable[tuple[str | None, str | None, float]],
    ) -> dict[str, HashConsensusEntry]:
        """
        Build exact-dHash consensus using only lexicon-resolved OCR seeds.

        samples: (visual_hash, normalized OCR token, OCR confidence)
        """
        votes: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

        for visual_hash, token, ocr_confidence in samples:
            if not visual_hash:
                continue
            resolution = self.resolve_ocr(token, ocr_confidence)
            if resolution is None:
                continue
            if resolution.identity_confidence < self.settings.min_consensus_seed_confidence:
                continue
            votes[visual_hash][resolution.resolved_name].append(
                resolution.identity_confidence
            )

        consensus: dict[str, HashConsensusEntry] = {}
        for visual_hash, by_name in votes.items():
            total_votes = sum(len(values) for values in by_name.values())
            ranked = sorted(
                (
                    (sum(values), len(values), name, values)
                    for name, values in by_name.items()
                ),
                reverse=True,
            )
            winner_weight, support, winner, values = ranked[0]
            if support < self.settings.min_hash_support:
                continue

            ratio = support / max(total_votes, 1)
            if ratio < self.settings.min_hash_ratio:
                continue

            mean_confidence = sum(values) / len(values)
            # Consensus is intentionally conservative. More support improves
            # confidence slightly, but does not turn mediocre OCR into 0.99.
            support_bonus = min(0.06, 0.015 * max(0, support - 1))
            confidence = _clamp01(mean_confidence * ratio + support_bonus)
            if confidence < self.settings.min_hash_identity_confidence:
                continue

            consensus[visual_hash] = HashConsensusEntry(
                visual_hash=visual_hash,
                resolved_name=winner,
                support=support,
                total_votes=total_votes,
                winner_ratio=ratio,
                confidence=confidence,
            )

        return consensus

    def resolve(
        self,
        token: str | None,
        ocr_confidence: float,
        *,
        visual_hash: str | None = None,
        hash_consensus: dict[str, HashConsensusEntry] | None = None,
    ) -> ShopIdentityResolution | None:
        direct = self.resolve_ocr(token, ocr_confidence)
        entry = (
            hash_consensus.get(visual_hash)
            if hash_consensus is not None and visual_hash
            else None
        )

        if entry is None:
            return direct

        hash_resolution = ShopIdentityResolution(
            resolved_name=entry.resolved_name,
            identity_method="hash_consensus",
            identity_confidence=entry.confidence,
            ocr_token=(str(token).lower() if token else None),
            ocr_confidence=_clamp01(ocr_confidence),
            hash_support=entry.support,
            hash_ratio=entry.winner_ratio,
        )

        if direct is None:
            return hash_resolution

        if direct.resolved_name == entry.resolved_name:
            # Preserve how the current frame was resolved, while exposing hash
            # support in provenance and allowing consensus to strengthen the
            # identity confidence.
            return ShopIdentityResolution(
                resolved_name=direct.resolved_name,
                identity_method=direct.identity_method,
                identity_confidence=max(
                    direct.identity_confidence,
                    entry.confidence,
                ),
                ocr_token=direct.ocr_token,
                ocr_confidence=direct.ocr_confidence,
                similarity=direct.similarity,
                fuzzy_margin=direct.fuzzy_margin,
                hash_support=entry.support,
                hash_ratio=entry.winner_ratio,
            )

        # Strong exact-hash consensus may override a conflicting current OCR,
        # especially a fuzzy match. Requiring >=3 supporting frames avoids a
        # two-frame feedback loop.
        if (
            entry.support >= max(3, self.settings.min_hash_support)
            and entry.winner_ratio >= max(0.80, self.settings.min_hash_ratio)
            and (
                direct.identity_method == "fuzzy_lexicon"
                or entry.confidence >= direct.identity_confidence + 0.05
            )
        ):
            return hash_resolution

        return direct
