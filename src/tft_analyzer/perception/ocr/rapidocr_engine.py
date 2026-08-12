from __future__ import annotations

import numpy as np
from PIL import Image

from .models import OCRText


class RapidOCREngine:
    """
    Thin adapter around RapidOCR.

    TFT HUD ROIs already contain one text line, therefore detection and
    orientation classification are disabled and only text recognition is used.
    Import/initialization is lazy because loading the OCR model is comparatively
    expensive and should not happen for commands that do not use perception.
    """

    name = "rapidocr"

    def __init__(self) -> None:
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine

        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "RapidOCR is not installed. Run "
                '`python -m pip install -e ".[dev]"` to install Stage 2.1 '
                "dependencies."
            ) from exc

        self._engine = RapidOCR()
        return self._engine

    def recognize_line(self, image: Image.Image) -> OCRText:
        engine = self._get_engine()

        rgb = image.convert("RGB")
        image_np = np.asarray(rgb)

        result = engine(
            image_np,
            use_det=False,
            use_cls=False,
            use_rec=True,
        )

        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)

        if not txts:
            return OCRText(text="", score=0.0)

        text = " ".join(str(x) for x in txts if str(x).strip()).strip()
        if not text:
            return OCRText(text="", score=0.0)

        if scores:
            valid_scores = [float(x) for x in scores]
            score = sum(valid_scores) / len(valid_scores)
        else:
            score = 0.0

        return OCRText(text=text, score=max(0.0, min(score, 1.0)))
