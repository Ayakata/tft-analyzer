from __future__ import annotations

import hashlib
from dataclasses import dataclass

from PIL import Image

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.ocr import OCREngine

from .models import FieldAttempt, HUDRecognitionResult
from .parsers import PARSER_BY_FIELD
from .preprocess import build_variants
from .presence import HUDPresenceGate
from .stage_localizer import StageLocalizer


@dataclass(frozen=True, slots=True)
class HUDFieldSpec:
    field: str
    roi_name: str
    context_roi_name: str
    kind: ObservationKind


DEFAULT_FIELDS = (
    HUDFieldSpec("gold", "gold_number", "gold_value", ObservationKind.GOLD),
    HUDFieldSpec("level", "level_text", "level_value", ObservationKind.LEVEL),
    HUDFieldSpec("xp", "xp_text", "xp_value", ObservationKind.XP),
)


class HUDRecognizer:
    def __init__(
        self,
        *,
        registry: ROIRegistry,
        ocr_engine: OCREngine,
        producer_version: str = "hud-rapidocr-0.4.2",
        min_observation_confidence: float = 0.45,
        primary_upscale: int = 4,
        fallback_upscale: int = 5,
        horizontal_padding_ratio: float = 0.16,
        binary_threshold: int = 150,
        presence_gate: HUDPresenceGate | None = None,
        stage_localizer: StageLocalizer | None = None,
    ) -> None:
        self.registry = registry
        self.ocr_engine = ocr_engine
        self.producer_version = producer_version
        self.min_observation_confidence = float(min_observation_confidence)

        self.primary_upscale = int(primary_upscale)
        self.fallback_upscale = int(fallback_upscale)
        self.horizontal_padding_ratio = float(horizontal_padding_ratio)
        self.binary_threshold = int(binary_threshold)

        self.presence_gate = presence_gate
        self.stage_localizer = stage_localizer or StageLocalizer()

    @staticmethod
    def _observation_id(evidence_id: str, field: str) -> str:
        digest = hashlib.sha1(
            f"{evidence_id}|{field}".encode("utf-8")
        ).hexdigest()[:12]
        return f"obs-{field}-{digest}"

    def _variants(self, crop: Image.Image):
        return build_variants(
            crop,
            primary_upscale=self.primary_upscale,
            fallback_upscale=self.fallback_upscale,
            horizontal_padding_ratio=self.horizontal_padding_ratio,
            binary_threshold=self.binary_threshold,
        )

    def _presence(self, field: str, context: Image.Image):
        if self.presence_gate is None:
            return True, 1.0, "disabled"
        decision = self.presence_gate.check(field, context)
        return decision.present, decision.score, decision.reason

    def _recognize_stage(
        self,
        image: Image.Image,
        result: HUDRecognitionResult,
    ) -> FieldAttempt | None:
        parser = PARSER_BY_FIELD["stage"]
        width, height = image.size

        context_roi = self.registry.resolve("stage_value", width, height)
        context_crop = image.crop(context_roi.box)
        present, presence_score, presence_reason = self._presence(
            "stage", context_crop
        )

        if not present:
            result.attempts.append(
                FieldAttempt(
                    field="stage",
                    roi_name="stage_search_region",
                    variant="presence_only",
                    raw_text="",
                    ocr_score=0.0,
                    parsed=None,
                    confidence=0.0,
                    presence_passed=False,
                    presence_score=presence_score,
                    presence_reason=presence_reason,
                )
            )
            return None

        best: FieldAttempt | None = None

        for candidate in self.stage_localizer.candidates(image, self.registry):
            for variant in self._variants(candidate.image):
                ocr = self.ocr_engine.recognize_line(variant.image)
                parsed = parser(ocr.text)
                confidence = (
                    ocr.normalized_score() * parsed.parser_confidence
                    if parsed is not None
                    else 0.0
                )

                attempt = FieldAttempt(
                    field="stage",
                    roi_name="stage_search_region",
                    variant=variant.name,
                    raw_text=ocr.text,
                    ocr_score=ocr.normalized_score(),
                    parsed=parsed,
                    confidence=confidence,
                    presence_passed=True,
                    presence_score=presence_score,
                    presence_reason=presence_reason,
                    candidate_name=candidate.name,
                    candidate_box=candidate.box,
                )
                result.attempts.append(attempt)

                if best is None or (attempt.valid, attempt.confidence) > (
                    best.valid,
                    best.confidence,
                ):
                    best = attempt

                if parsed is not None and confidence >= 0.92:
                    break

        return best

    def _recognize_fixed_field(
        self,
        image: Image.Image,
        spec: HUDFieldSpec,
        result: HUDRecognitionResult,
    ) -> FieldAttempt | None:
        parser = PARSER_BY_FIELD[spec.field]
        width, height = image.size

        context_roi = self.registry.resolve(
            spec.context_roi_name, width, height
        )
        context_crop = image.crop(context_roi.box)
        present, presence_score, presence_reason = self._presence(
            spec.field, context_crop
        )

        if not present:
            result.attempts.append(
                FieldAttempt(
                    field=spec.field,
                    roi_name=spec.roi_name,
                    variant="presence_only",
                    raw_text="",
                    ocr_score=0.0,
                    parsed=None,
                    confidence=0.0,
                    presence_passed=False,
                    presence_score=presence_score,
                    presence_reason=presence_reason,
                )
            )
            return None

        pixel_roi = self.registry.resolve(spec.roi_name, width, height)
        crop = image.crop(pixel_roi.box)

        best: FieldAttempt | None = None

        for variant in self._variants(crop):
            ocr = self.ocr_engine.recognize_line(variant.image)
            parsed = parser(ocr.text)
            confidence = (
                ocr.normalized_score() * parsed.parser_confidence
                if parsed is not None
                else 0.0
            )

            attempt = FieldAttempt(
                field=spec.field,
                roi_name=spec.roi_name,
                variant=variant.name,
                raw_text=ocr.text,
                ocr_score=ocr.normalized_score(),
                parsed=parsed,
                confidence=confidence,
                presence_passed=True,
                presence_score=presence_score,
                presence_reason=presence_reason,
            )
            result.attempts.append(attempt)

            if best is None or (attempt.valid, attempt.confidence) > (
                best.valid,
                best.confidence,
            ):
                best = attempt

            if parsed is not None and confidence >= 0.82:
                break

        return best

    def _append_observation(
        self,
        result: HUDRecognitionResult,
        *,
        field: str,
        kind: ObservationKind,
        best: FieldAttempt | None,
        match_id: str,
        timestamp_s: float,
        evidence_id: str,
    ) -> None:
        if (
            best is None
            or not best.valid
            or best.parsed is None
            or best.confidence < self.min_observation_confidence
        ):
            return

        value = dict(best.parsed.value)
        value.update(
            {
                "raw_text": best.raw_text,
                "normalized_text": best.parsed.normalized_text,
                "ocr_engine": self.ocr_engine.name,
                "ocr_variant": best.variant,
                "ocr_roi": best.roi_name,
                "presence_score": best.presence_score,
            }
        )

        if best.candidate_name is not None:
            value["ocr_candidate"] = best.candidate_name
            value["ocr_candidate_box"] = best.candidate_box

        result.observations.append(
            Observation(
                observation_id=self._observation_id(evidence_id, field),
                match_id=match_id,
                timestamp_s=max(0.0, float(timestamp_s)),
                kind=kind,
                value=value,
                confidence=max(0.0, min(best.confidence, 1.0)),
                evidence_ids=(evidence_id,),
                producer_version=self.producer_version,
            )
        )

    def recognize(
        self,
        image: Image.Image,
        *,
        match_id: str,
        timestamp_s: float,
        evidence_id: str,
    ) -> HUDRecognitionResult:
        image = image.convert("RGB")
        width, height = image.size
        self.registry.assert_compatible(width, height)

        result = HUDRecognitionResult()

        best_stage = self._recognize_stage(image, result)
        self._append_observation(
            result,
            field="stage",
            kind=ObservationKind.STAGE,
            best=best_stage,
            match_id=match_id,
            timestamp_s=timestamp_s,
            evidence_id=evidence_id,
        )

        for spec in DEFAULT_FIELDS:
            best = self._recognize_fixed_field(image, spec, result)
            self._append_observation(
                result,
                field=spec.field,
                kind=spec.kind,
                best=best,
                match_id=match_id,
                timestamp_s=timestamp_s,
                evidence_id=evidence_id,
            )

        return result
