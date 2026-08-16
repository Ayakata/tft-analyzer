from __future__ import annotations

from dataclasses import dataclass, field

from tft_analyzer.core.models import Observation


@dataclass(frozen=True, slots=True)
class ShopNameAttempt:
    slot_index: int
    variant: str
    raw_text: str
    normalized_name: str | None
    ocr_score: float
    parser_confidence: float
    confidence: float

    @property
    def valid(self) -> bool:
        return self.normalized_name is not None


@dataclass(frozen=True, slots=True)
class ShopSlotResult:
    slot_index: int
    card_box: tuple[int, int, int, int]
    portrait_box: tuple[int, int, int, int]
    name_box: tuple[int, int, int, int]

    occupancy_score: float
    occupied: bool
    occupancy_confidence: float

    visual_hash: str | None = None
    name_attempts: tuple[ShopNameAttempt, ...] = ()

    @property
    def best_name_attempt(self) -> ShopNameAttempt | None:
        if not self.name_attempts:
            return None
        return max(
            self.name_attempts,
            key=lambda a: (a.valid, a.confidence),
        )

    @property
    def normalized_name(self) -> str | None:
        best = self.best_name_attempt
        return best.normalized_name if best and best.valid else None


@dataclass(slots=True)
class ShopRecognitionResult:
    observations: list[Observation] = field(default_factory=list)

    shop_present: bool = False
    shop_presence_score: float = 0.0

    slots: list[ShopSlotResult] = field(default_factory=list)

    @property
    def occupied_count(self) -> int:
        return sum(1 for slot in self.slots if slot.occupied)

    @property
    def complete(self) -> bool:
        return bool(self.slots) and all(
            (not slot.occupied) or slot.normalized_name is not None
            for slot in self.slots
        )
