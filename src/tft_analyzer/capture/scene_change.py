from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image


class SceneChangeDetector:
    """Cheap generic whole-frame visual-change detector for Stage 1."""

    def __init__(self, *, width=160, height=90, threshold=0.045) -> None:
        self.width = width
        self.height = height
        self.threshold = threshold
        self._previous = None

    def signature(self, png_bytes: bytes) -> np.ndarray:
        with Image.open(BytesIO(png_bytes)) as image:
            gray = image.convert("L").resize((self.width, self.height))
            return np.asarray(gray, dtype=np.float32) / 255.0

    def changed(self, png_bytes: bytes) -> tuple[bool, float]:
        current = self.signature(png_bytes)
        if self._previous is None:
            self._previous = current
            return True, 1.0

        score = float(np.mean(np.abs(current - self._previous)))
        self._previous = current
        return score >= self.threshold, score

    def reset(self) -> None:
        self._previous = None
