from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import re

import numpy as np
from PIL import Image

from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.ocr import OCREngine

from .models import PlayerRowCandidate


@dataclass(frozen=True, slots=True)
class SelfRowSelection:
    row_index: int | None
    method: str | None
    score: float
    margin: float


def _clamp01(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def normalize_player_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


class PlayerRowLocalizer:
    def __init__(
        self,
        *,
        row_count: int = 8,
        row_vertical_inset_ratio: float = 0.06,
        name_x0: float = 0.05,
        name_x1: float = 0.68,
        highlight_x0: float = 0.02,
        highlight_x1: float = 0.98,
    ) -> None:
        self.row_count = max(1, int(row_count))
        self.row_vertical_inset_ratio = max(
            0.0,
            min(float(row_vertical_inset_ratio), 0.40),
        )
        self.name_x0 = float(name_x0)
        self.name_x1 = float(name_x1)
        self.highlight_x0 = float(highlight_x0)
        self.highlight_x1 = float(highlight_x1)

    def row_boxes(
        self,
        image: Image.Image,
        registry: ROIRegistry,
    ) -> list[tuple[int, int, int, int]]:
        width, height = image.size
        panel = registry.resolve("players_panel", width, height)

        total_h = panel.height
        result = []

        for i in range(self.row_count):
            top = panel.top + round(total_h * i / self.row_count)
            bottom = panel.top + round(total_h * (i + 1) / self.row_count)

            slot_h = max(1, bottom - top)
            inset = round(slot_h * self.row_vertical_inset_ratio)

            top = min(bottom - 1, top + inset)
            bottom = max(top + 1, bottom - inset)

            result.append((panel.left, top, panel.right, bottom))

        return result

    @staticmethod
    def panel_presence_score(panel: Image.Image) -> float:
        arr = np.asarray(panel.convert("L"), dtype=np.float32)
        if arr.size == 0:
            return 0.0

        contrast = float(arr.std()) / 64.0

        dx = np.abs(np.diff(arr, axis=1))
        dy = np.abs(np.diff(arr, axis=0))
        edges = 0.5 * (
            float((dx > 18.0).mean())
            + float((dy > 18.0).mean())
        )

        return _clamp01(
            0.55 * min(1.0, contrast)
            + 0.45 * min(1.0, edges / 0.08)
        )

    def highlight_score(self, row: Image.Image) -> float:
        arr = np.asarray(row.convert("RGB"), dtype=np.float32)
        if arr.size == 0:
            return 0.0

        _, w, _ = arr.shape
        x0 = max(0, min(w - 1, int(round(w * self.highlight_x0))))
        x1 = max(x0 + 1, min(w, int(round(w * self.highlight_x1))))
        arr = arr[:, x0:x1]

        r = arr[..., 0]
        g = arr[..., 1]
        b = arr[..., 2]

        warm = (
            (r >= 125)
            & (g >= 75)
            & (g <= r * 1.10)
            & (b <= g * 0.82)
            & ((r - b) >= 45)
        )
        bright_warm = warm & (r >= 175) & (g >= 115)

        warm_ratio = float(warm.mean())
        bright_ratio = float(bright_warm.mean())

        warm_f = warm.astype(np.float32)
        dx = np.abs(np.diff(warm_f, axis=1))
        dy = np.abs(np.diff(warm_f, axis=0))
        edge_ratio = 0.5 * (
            float((dx > 0.5).mean()) if dx.size else 0.0
        ) + 0.5 * (
            float((dy > 0.5).mean()) if dy.size else 0.0
        )

        return _clamp01(
            0.45 * min(1.0, warm_ratio / 0.055)
            + 0.35 * min(1.0, bright_ratio / 0.020)
            + 0.20 * min(1.0, edge_ratio / 0.080)
        )

    def _name_crop(
        self,
        image: Image.Image,
        box: tuple[int, int, int, int],
    ) -> Image.Image:
        left, top, right, bottom = box
        width = right - left

        x0 = left + round(width * self.name_x0)
        x1 = left + round(width * self.name_x1)

        return image.crop((x0, top, x1, bottom))

    @staticmethod
    def _name_ocr_cues(text: str, score: float) -> tuple[float, float]:
        """Return (name_presence, no_name) from an ambiguous-row OCR crop.

        Own row normally contains only the HP number in this area. Opponent
        rows contain a nickname plus HP. Empty/weak OCR is treated as unknown,
        not as evidence that a nickname is absent.
        """
        text = str(text or "").strip()
        score = _clamp01(score)
        if not text:
            return 0.0, 0.0

        has_alpha = any(ch.isalpha() for ch in text)
        has_digit = any(ch.isdigit() for ch in text)

        if has_alpha:
            return score, 0.0

        if has_digit and score >= 0.60:
            return 0.0, score

        return 0.0, 0.0

    def enrich_no_name_ocr(
        self,
        image: Image.Image,
        rows: list[PlayerRowCandidate],
        ocr_engine: OCREngine,
        *,
        top_k: int = 3,
    ) -> list[PlayerRowCandidate]:
        """OCR only top ambiguous highlight candidates.

        This is intentionally lazy: normal frames need no nickname OCR at all.
        """
        target_ids = {
            row.row_index
            for row in sorted(
                rows,
                key=lambda row: row.highlight_score,
                reverse=True,
            )[:max(1, int(top_k))]
        }

        result = []
        for row in rows:
            if row.row_index not in target_ids:
                result.append(row)
                continue

            ocr = ocr_engine.recognize_line(
                self._name_crop(image, row.box)
            )
            score = ocr.normalized_score()
            name_presence, no_name = self._name_ocr_cues(
                ocr.text,
                score,
            )
            combined = _clamp01(
                0.80 * row.highlight_score
                + 0.20 * no_name
            )

            result.append(
                replace(
                    row,
                    name_presence_score=name_presence,
                    no_name_score=no_name,
                    name_text=ocr.text,
                    name_ocr_score=score,
                    combined_self_score=combined,
                )
            )

        return result

    def candidates(
        self,
        image: Image.Image,
        registry: ROIRegistry,
        *,
        ocr_engine: OCREngine | None = None,
        player_name: str | None = None,
    ) -> list[PlayerRowCandidate]:
        normalized_target = normalize_player_name(player_name or "")
        result = []

        for row_index, box in enumerate(self.row_boxes(image, registry)):
            row = image.crop(box)
            highlight = self.highlight_score(row)

            name_crop = self._name_crop(image, box)
            name_presence = 0.0
            no_name = 0.0

            name_text = ""
            name_ocr_score = 0.0
            name_match_score = 0.0

            if ocr_engine is not None and normalized_target:
                name_ocr = ocr_engine.recognize_line(name_crop)
                name_text = name_ocr.text
                name_ocr_score = name_ocr.normalized_score()

                normalized_ocr = normalize_player_name(name_text)
                if normalized_ocr:
                    similarity = SequenceMatcher(
                        None,
                        normalized_target,
                        normalized_ocr,
                    ).ratio()
                    name_match_score = float(similarity) * name_ocr_score

            combined = (
                0.80 * name_match_score + 0.20 * highlight
                if normalized_target
                else highlight
            )

            result.append(
                PlayerRowCandidate(
                    row_index=row_index,
                    box=box,
                    highlight_score=highlight,
                    name_presence_score=name_presence,
                    no_name_score=no_name,
                    name_text=name_text,
                    name_ocr_score=name_ocr_score,
                    name_match_score=name_match_score,
                    combined_self_score=_clamp01(combined),
                )
            )

        return result

    @staticmethod
    def select_self_row(
        rows: list[PlayerRowCandidate],
        *,
        manual_row_index: int | None = None,
        player_name: str | None = None,
        min_name_match_score: float = 0.60,
        min_highlight_score: float = 0.24,
        min_highlight_margin: float = 0.035,
        min_combined_score: float = 0.40,
        min_combined_margin: float = 0.025,
    ) -> SelfRowSelection:
        if manual_row_index is not None:
            if not any(r.row_index == manual_row_index for r in rows):
                return SelfRowSelection(None, None, 0.0, 0.0)
            return SelfRowSelection(
                row_index=int(manual_row_index),
                method="manual",
                score=1.0,
                margin=1.0,
            )

        if not rows:
            return SelfRowSelection(None, None, 0.0, 0.0)

        if normalize_player_name(player_name or ""):
            ordered = sorted(
                rows,
                key=lambda r: r.name_match_score,
                reverse=True,
            )
            top = ordered[0]
            second = ordered[1] if len(ordered) > 1 else None
            margin = top.name_match_score - (
                second.name_match_score if second is not None else 0.0
            )

            if top.name_match_score >= float(min_name_match_score):
                return SelfRowSelection(
                    row_index=top.row_index,
                    method="player_name",
                    score=_clamp01(top.name_match_score),
                    margin=max(0.0, margin),
                )

        ordered = sorted(
            rows,
            key=lambda r: r.highlight_score,
            reverse=True,
        )
        top = ordered[0]
        second = ordered[1] if len(ordered) > 1 else None
        margin = top.highlight_score - (
            second.highlight_score if second is not None else 0.0
        )

        if (
            top.highlight_score >= float(min_highlight_score)
            and margin >= float(min_highlight_margin)
        ):
            return SelfRowSelection(
                row_index=top.row_index,
                method="highlight",
                score=_clamp01(top.highlight_score),
                margin=max(0.0, margin),
            )

        combined = sorted(
            rows,
            key=lambda r: r.combined_self_score,
            reverse=True,
        )
        ctop = combined[0]
        csecond = combined[1] if len(combined) > 1 else None
        cmargin = ctop.combined_self_score - (
            csecond.combined_self_score if csecond is not None else 0.0
        )

        if (
            ctop.highlight_score >= float(min_highlight_score)
            and ctop.no_name_score >= 0.60
            and ctop.combined_self_score >= float(min_combined_score)
            and cmargin >= float(min_combined_margin)
        ):
            return SelfRowSelection(
                row_index=ctop.row_index,
                method="highlight_no_name",
                score=_clamp01(ctop.combined_self_score),
                margin=max(0.0, cmargin),
            )

        return SelfRowSelection(
            row_index=None,
            method=None,
            score=_clamp01(top.highlight_score),
            margin=max(0.0, margin),
        )
