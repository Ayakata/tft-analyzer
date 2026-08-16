from __future__ import annotations

from dataclasses import dataclass, field

from tft_analyzer.core.models import Observation


@dataclass(frozen=True, slots=True)
class PlayerRowCandidate:
    row_index: int
    box: tuple[int, int, int, int]

    highlight_score: float
    name_presence_score: float = 0.0
    no_name_score: float = 0.0

    name_text: str = ""
    name_ocr_score: float = 0.0
    name_match_score: float = 0.0

    combined_self_score: float = 0.0


@dataclass(frozen=True, slots=True)
class HPAttempt:
    row_index: int
    candidate_name: str
    candidate_box: tuple[int, int, int, int]

    variant: str
    raw_text: str
    ocr_score: float

    hp: int | None
    parser_confidence: float
    confidence: float

    @property
    def valid(self) -> bool:
        return self.hp is not None


@dataclass(slots=True)
class PlayerRecognitionResult:
    observations: list[Observation] = field(default_factory=list)

    panel_present: bool = False
    panel_score: float = 0.0

    rows: list[PlayerRowCandidate] = field(default_factory=list)

    selected_row_index: int | None = None
    self_method: str | None = None
    self_score: float = 0.0
    self_margin: float = 0.0

    hp_attempts: list[HPAttempt] = field(default_factory=list)

    @property
    def best_hp_attempt(self) -> HPAttempt | None:
        if not self.hp_attempts:
            return None

        if self.observations:
            candidate = self.observations[0].value.get("ocr_candidate")
            variant = self.observations[0].value.get("ocr_variant")
            matching = [
                attempt
                for attempt in self.hp_attempts
                if attempt.candidate_name == candidate
                and attempt.variant == variant
            ]
            if matching:
                return max(matching, key=lambda attempt: attempt.confidence)

        return max(
            self.hp_attempts,
            key=lambda attempt: (attempt.valid, attempt.confidence),
        )
