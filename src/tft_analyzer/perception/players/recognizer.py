from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import sqrt

from PIL import Image

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.perception.hud.preprocess import build_variants
from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.ocr import OCREngine

from .localizer import PlayerRowLocalizer
from .models import HPAttempt, PlayerRecognitionResult
from .parsers import parse_player_hp


@dataclass(frozen=True, slots=True)
class PlayerListRecognizerSettings:
    producer_version: str = "players-rapidocr-0.8.1"

    min_observation_confidence: float = 0.55

    row_count: int = 8
    min_panel_score: float = 0.22

    player_name: str | None = None
    min_name_match_score: float = 0.60

    min_highlight_score: float = 0.24
    min_highlight_margin: float = 0.035
    min_combined_self_score: float = 0.40
    min_combined_self_margin: float = 0.025

    hp_max_value: int = 250
    hp_primary_upscale: int = 4
    hp_fallback_upscale: int = 6
    hp_binary_threshold: int = 150

    hp_primary_candidate_min_confidence: float = 0.60
    hp_fallback_min_confidence: float = 0.72
    hp_candidate_priors: tuple[float, ...] = (
        1.00,
        0.70,
        0.45,
        0.30,
        0.20,
    )

    hp_candidate_x_starts: tuple[float, ...] = (
        0.48,
        0.56,
        0.64,
        0.72,
        0.80,
    )
    hp_candidate_width_ratio: float = 0.18
    hp_y0: float = 0.14
    hp_y1: float = 0.86


class PlayerListRecognizer:
    def __init__(
        self,
        *,
        registry: ROIRegistry,
        ocr_engine: OCREngine,
        settings: PlayerListRecognizerSettings,
        localizer: PlayerRowLocalizer | None = None,
    ) -> None:
        self.registry = registry
        self.ocr_engine = ocr_engine
        self.settings = settings
        self.localizer = localizer or PlayerRowLocalizer(
            row_count=settings.row_count,
        )

    @staticmethod
    def _observation_id(evidence_id: str) -> str:
        digest = hashlib.sha1(
            f"{evidence_id}|player_hp".encode("utf-8")
        ).hexdigest()[:12]
        return f"obs-hp-{digest}"

    def _hp_candidates(
        self,
        row_box: tuple[int, int, int, int],
    ):
        left, top, right, bottom = row_box
        width = right - left
        height = bottom - top

        y0 = top + round(height * self.settings.hp_y0)
        y1 = top + round(height * self.settings.hp_y1)

        for index, x_start in enumerate(
            self.settings.hp_candidate_x_starts
        ):
            x0 = left + round(width * float(x_start))
            x1 = x0 + round(
                width * self.settings.hp_candidate_width_ratio
            )

            x0 = max(left, min(x0, right - 1))
            x1 = max(x0 + 1, min(x1, right))
            y0c = max(top, min(y0, bottom - 1))
            y1c = max(y0c + 1, min(y1, bottom))

            yield (
                index,
                f"hp_candidate_{index}",
                (x0, y0c, x1, y1c),
            )

    def _variants(self, crop: Image.Image):
        return build_variants(
            crop,
            primary_upscale=self.settings.hp_primary_upscale,
            fallback_upscale=self.settings.hp_fallback_upscale,
            horizontal_padding_ratio=0.12,
            binary_threshold=self.settings.hp_binary_threshold,
        )

    def _candidate_attempts(
        self,
        image: Image.Image,
        *,
        row_index: int,
        candidate_name: str,
        box: tuple[int, int, int, int],
    ) -> list[HPAttempt]:
        attempts = []
        crop = image.crop(box)

        for variant in self._variants(crop):
            ocr = self.ocr_engine.recognize_line(variant.image)
            hp, parser_conf = parse_player_hp(
                ocr.text,
                max_hp=self.settings.hp_max_value,
            )
            confidence = (
                ocr.normalized_score() * parser_conf
                if hp is not None
                else 0.0
            )

            attempt = HPAttempt(
                row_index=row_index,
                candidate_name=candidate_name,
                candidate_box=box,
                variant=variant.name,
                raw_text=ocr.text,
                ocr_score=ocr.normalized_score(),
                hp=hp,
                parser_confidence=parser_conf,
                confidence=confidence,
            )
            attempts.append(attempt)

            if hp is not None and confidence >= 0.92:
                break

        return attempts

    def _recognize_hp(
        self,
        image: Image.Image,
        *,
        row_index: int,
        row_box: tuple[int, int, int, int],
    ) -> list[HPAttempt]:
        """
        Candidate 0 is the calibrated HP geometry.

        If it yields a usable value, later windows cannot replace it solely
        because OCR reports a slightly higher confidence for unrelated digits.
        """
        all_attempts: list[HPAttempt] = []
        candidates = list(self._hp_candidates(row_box))
        if not candidates:
            return all_attempts

        _, primary_name, primary_box = candidates[0]
        primary_attempts = self._candidate_attempts(
            image,
            row_index=row_index,
            candidate_name=primary_name,
            box=primary_box,
        )
        all_attempts.extend(primary_attempts)

        best_primary = max(
            primary_attempts,
            key=lambda attempt: (attempt.valid, attempt.confidence),
            default=None,
        )

        if (
            best_primary is not None
            and best_primary.valid
            and best_primary.confidence
            >= self.settings.hp_primary_candidate_min_confidence
        ):
            return all_attempts

        for _, candidate_name, box in candidates[1:]:
            all_attempts.extend(
                self._candidate_attempts(
                    image,
                    row_index=row_index,
                    candidate_name=candidate_name,
                    box=box,
                )
            )

        return all_attempts

    def _best_hp_attempt(
        self,
        attempts: list[HPAttempt],
    ) -> HPAttempt | None:
        if not attempts:
            return None

        primary = [
            attempt
            for attempt in attempts
            if attempt.candidate_name == "hp_candidate_0"
            and attempt.valid
            and attempt.confidence
            >= self.settings.hp_primary_candidate_min_confidence
        ]
        if primary:
            return max(primary, key=lambda attempt: attempt.confidence)

        priors = self.settings.hp_candidate_priors
        valid_fallbacks = []

        for attempt in attempts:
            if not attempt.valid:
                continue

            try:
                index = int(attempt.candidate_name.rsplit("_", 1)[-1])
            except ValueError:
                index = 0

            prior = priors[index] if index < len(priors) else 0.10
            adjusted = attempt.confidence * float(prior)

            if attempt.confidence >= self.settings.hp_fallback_min_confidence:
                valid_fallbacks.append(
                    (adjusted, attempt.confidence, attempt)
                )

        if valid_fallbacks:
            return max(
                valid_fallbacks,
                key=lambda item: (item[0], item[1]),
            )[-1]

        return max(
            attempts,
            key=lambda attempt: (attempt.valid, attempt.confidence),
        )

    def recognize(
        self,
        image: Image.Image,
        *,
        match_id: str,
        timestamp_s: float,
        evidence_id: str,
        manual_row_index: int | None = None,
        player_name: str | None = None,
    ) -> PlayerRecognitionResult:
        image = image.convert("RGB")
        width, height = image.size
        self.registry.assert_compatible(width, height)

        result = PlayerRecognitionResult()

        panel_roi = self.registry.resolve(
            "players_panel",
            width,
            height,
        )
        panel = image.crop(panel_roi.box)

        result.panel_score = self.localizer.panel_presence_score(panel)
        result.panel_present = (
            result.panel_score >= self.settings.min_panel_score
        )

        if not result.panel_present:
            return result

        effective_player_name = (
            player_name
            if player_name is not None
            else self.settings.player_name
        )

        rows = self.localizer.candidates(
            image,
            self.registry,
            ocr_engine=self.ocr_engine,
            player_name=effective_player_name,
        )
        # Nickname OCR is a lazy tie-breaker only. If highlight has a clear
        # winner, no additional OCR is needed.
        ordered_by_highlight = sorted(
            rows,
            key=lambda row: row.highlight_score,
            reverse=True,
        )
        if len(ordered_by_highlight) >= 2:
            highlight_margin = (
                ordered_by_highlight[0].highlight_score
                - ordered_by_highlight[1].highlight_score
            )
            if (
                ordered_by_highlight[0].highlight_score
                >= self.settings.min_highlight_score
                and highlight_margin
                < self.settings.min_highlight_margin
                and not effective_player_name
            ):
                rows = self.localizer.enrich_no_name_ocr(
                    image,
                    rows,
                    self.ocr_engine,
                    top_k=3,
                )

        result.rows.extend(rows)

        selection = self.localizer.select_self_row(
            rows,
            manual_row_index=manual_row_index,
            player_name=effective_player_name,
            min_name_match_score=self.settings.min_name_match_score,
            min_highlight_score=self.settings.min_highlight_score,
            min_highlight_margin=self.settings.min_highlight_margin,
            min_combined_score=self.settings.min_combined_self_score,
            min_combined_margin=self.settings.min_combined_self_margin,
        )

        result.selected_row_index = selection.row_index
        result.self_method = selection.method
        result.self_score = selection.score
        result.self_margin = selection.margin

        if selection.row_index is None:
            return result

        selected = next(
            row for row in rows
            if row.row_index == selection.row_index
        )

        result.hp_attempts.extend(
            self._recognize_hp(
                image,
                row_index=selected.row_index,
                row_box=selected.box,
            )
        )

        best = self._best_hp_attempt(result.hp_attempts)
        if best is None or not best.valid or best.hp is None:
            return result

        identity_confidence = (
            1.0
            if selection.method == "manual"
            else max(0.0, min(selection.score, 1.0))
        )
        combined_confidence = sqrt(
            max(0.0, identity_confidence)
            * max(0.0, best.confidence)
        )

        if combined_confidence < self.settings.min_observation_confidence:
            return result

        result.observations.append(
            Observation(
                observation_id=self._observation_id(evidence_id),
                match_id=match_id,
                timestamp_s=max(0.0, float(timestamp_s)),
                kind=ObservationKind.HP,
                value={
                    "hp": int(best.hp),
                    "row_index": int(selected.row_index),
                    "self_method": selection.method,
                    "self_score": float(selection.score),
                    "self_margin": float(selection.margin),
                    "panel_score": float(result.panel_score),
                    "name_presence_score": float(
                        selected.name_presence_score
                    ),
                    "no_name_score": float(selected.no_name_score),
                    "raw_text": best.raw_text,
                    "ocr_engine": self.ocr_engine.name,
                    "ocr_variant": best.variant,
                    "ocr_candidate": best.candidate_name,
                    "ocr_candidate_box": best.candidate_box,
                    "player_name_query": effective_player_name,
                    "row_name_text": selected.name_text,
                    "row_name_match_score": selected.name_match_score,
                },
                confidence=max(
                    0.0,
                    min(float(combined_confidence), 1.0),
                ),
                evidence_ids=(evidence_id,),
                producer_version=self.settings.producer_version,
            )
        )

        return result
