from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OCRText:
    text: str
    score: float

    def normalized_score(self) -> float:
        return max(0.0, min(float(self.score), 1.0))
