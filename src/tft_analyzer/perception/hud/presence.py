from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True, slots=True)
class PresenceFeatures:
    dark_fraction: float
    bright_fraction: float
    edge_density: float


@dataclass(frozen=True, slots=True)
class PresenceDecision:
    present: bool
    score: float
    features: PresenceFeatures
    reason: str


class HUDPresenceGate:
    """
    Permissive non-ML gate that rejects obvious non-HUD crops before OCR.

    `score` is the degree to which ALL required presence criteria are satisfied.
    Therefore an absent field cannot have score=1.0 simply because some other
    features are very strong.
    """

    def __init__(
        self,
        *,
        min_dark_fraction: float = 0.20,
        min_edge_density: float = 0.015,
        min_bright_fraction: float = 0.002,
        stage_min_edge_density: float = 0.010,
    ) -> None:
        self.min_dark_fraction = float(min_dark_fraction)
        self.min_edge_density = float(min_edge_density)
        self.min_bright_fraction = float(min_bright_fraction)
        self.stage_min_edge_density = float(stage_min_edge_density)

    @staticmethod
    def features(image: Image.Image) -> PresenceFeatures:
        gray = np.asarray(ImageOps.grayscale(image), dtype=np.float32) / 255.0

        dark_fraction = float(np.mean(gray < 0.25))
        bright_fraction = float(np.mean(gray > 0.72))

        if gray.shape[0] < 2 or gray.shape[1] < 2:
            edge_density = 0.0
        else:
            gx = np.abs(np.diff(gray, axis=1))
            gy = np.abs(np.diff(gray, axis=0))
            edge_density = 0.5 * (
                float(np.mean(gx > 0.12))
                + float(np.mean(gy > 0.12))
            )

        return PresenceFeatures(
            dark_fraction=dark_fraction,
            bright_fraction=bright_fraction,
            edge_density=edge_density,
        )

    @staticmethod
    def _criterion_score(value: float, threshold: float) -> float:
        if threshold <= 0:
            return 1.0
        return max(0.0, min(float(value) / float(threshold), 1.0))

    def check(self, field: str, image: Image.Image) -> PresenceDecision:
        f = self.features(image)

        if field == "stage":
            edge_score = self._criterion_score(
                f.edge_density,
                self.stage_min_edge_density,
            )
            bright_score = self._criterion_score(
                f.bright_fraction,
                self.min_bright_fraction,
            )

            # Conjunctive semantics: the weakest required criterion determines
            # the confidence that the stage HUD is actually present.
            score = min(edge_score, bright_score)
            present = score >= 1.0

            return PresenceDecision(
                present=present,
                score=score,
                features=f,
                reason=(
                    "stage_structure"
                    if present
                    else "stage_structure_missing"
                ),
            )

        dark_score = self._criterion_score(
            f.dark_fraction,
            self.min_dark_fraction,
        )
        edge_score = self._criterion_score(
            f.edge_density,
            self.min_edge_density,
        )
        bright_score = self._criterion_score(
            f.bright_fraction,
            self.min_bright_fraction,
        )

        # All three criteria are required, so the weakest criterion is the
        # meaningful presence confidence.
        score = min(dark_score, edge_score, bright_score)
        present = score >= 1.0

        return PresenceDecision(
            present=present,
            score=score,
            features=f,
            reason=(
                "hud_structure"
                if present
                else "hud_structure_missing"
            ),
        )
