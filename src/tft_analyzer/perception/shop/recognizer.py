from __future__ import annotations

import hashlib
from dataclasses import dataclass

from PIL import Image

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.perception.hud.preprocess import build_variants
from tft_analyzer.perception.layout import ROIRegistry
from tft_analyzer.perception.ocr import OCREngine

from .features import (
    occupancy_confidence,
    portrait_dhash,
    shop_presence_score,
    slot_occupancy_score,
)
from .identity import (
    HashConsensusEntry,
    ShopIdentityResolver,
)
from .models import (
    ShopNameAttempt,
    ShopRecognitionResult,
    ShopSlotResult,
)
from .parsers import normalize_shop_name


@dataclass(frozen=True, slots=True)
class ShopRecognizerSettings:
    producer_version: str = "shop-rapidocr-0.9.1"

    min_shop_presence_score: float = 0.25
    min_occupied_score: float = 0.30

    min_name_confidence: float = 0.55
    min_identity_confidence: float = 0.55
    min_observation_confidence: float = 0.55

    name_x0: float = 0.03
    name_x1: float = 0.72
    name_y0: float = 0.70
    name_y1: float = 0.91

    name_primary_upscale: int = 3
    name_fallback_upscale: int = 4
    name_binary_threshold: int = 150

    portrait_hash_size: int = 8


class ShopRecognizer:
    SLOT_COUNT = 5

    def __init__(
        self,
        *,
        registry: ROIRegistry,
        ocr_engine: OCREngine,
        settings: ShopRecognizerSettings,
        identity_resolver: ShopIdentityResolver,
    ) -> None:
        self.registry = registry
        self.ocr_engine = ocr_engine
        self.settings = settings
        self.identity_resolver = identity_resolver

    @staticmethod
    def _observation_id(evidence_id: str) -> str:
        digest = hashlib.sha1(
            f"{evidence_id}|shop".encode("utf-8")
        ).hexdigest()[:12]
        return f"obs-shop-{digest}"

    @staticmethod
    def _subbox(
        box: tuple[int, int, int, int],
        *,
        x0: float,
        x1: float,
        y0: float,
        y1: float,
    ) -> tuple[int, int, int, int]:
        left, top, right, bottom = box
        width = max(1, right - left)
        height = max(1, bottom - top)

        sx0 = left + round(width * x0)
        sx1 = left + round(width * x1)
        sy0 = top + round(height * y0)
        sy1 = top + round(height * y1)

        sx0 = max(left, min(sx0, right - 1))
        sx1 = max(sx0 + 1, min(sx1, right))
        sy0 = max(top, min(sy0, bottom - 1))
        sy1 = max(sy0 + 1, min(sy1, bottom))
        return (sx0, sy0, sx1, sy1)

    def _name_attempts(
        self,
        crop: Image.Image,
        *,
        slot_index: int,
    ) -> tuple[ShopNameAttempt, ...]:
        attempts = []
        variants = build_variants(
            crop,
            primary_upscale=self.settings.name_primary_upscale,
            fallback_upscale=self.settings.name_fallback_upscale,
            horizontal_padding_ratio=0.08,
            binary_threshold=self.settings.name_binary_threshold,
        )

        for variant in variants:
            ocr = self.ocr_engine.recognize_line(variant.image)
            normalized, parser_conf = normalize_shop_name(ocr.text)
            confidence = (
                ocr.normalized_score() * parser_conf
                if normalized is not None
                else 0.0
            )
            attempts.append(
                ShopNameAttempt(
                    slot_index=slot_index,
                    variant=variant.name,
                    raw_text=ocr.text,
                    normalized_name=normalized,
                    ocr_score=ocr.normalized_score(),
                    parser_confidence=parser_conf,
                    confidence=confidence,
                )
            )

            if normalized is not None and confidence >= 0.92:
                break

        return tuple(attempts)

    def recognize(
        self,
        image: Image.Image,
        *,
        match_id: str,
        timestamp_s: float,
        evidence_id: str,
    ) -> ShopRecognitionResult:
        """Run raw geometry/occupancy/OCR and single-frame lexicon resolution."""
        image = image.convert("RGB")
        width, height = image.size
        self.registry.assert_compatible(width, height)

        result = ShopRecognitionResult()

        shop_roi = self.registry.resolve("shop_region", width, height)
        shop_crop = image.crop(shop_roi.box)
        result.shop_presence_score = shop_presence_score(shop_crop)
        result.shop_present = (
            result.shop_presence_score
            >= self.settings.min_shop_presence_score
        )

        if not result.shop_present:
            return result

        for slot_index in range(self.SLOT_COUNT):
            card_roi = self.registry.resolve(
                f"shop_{slot_index}_card",
                width,
                height,
            )
            portrait_roi = self.registry.resolve(
                f"shop_{slot_index}_portrait",
                width,
                height,
            )

            card_box = card_roi.box
            portrait_box = portrait_roi.box
            name_box = self._subbox(
                card_box,
                x0=self.settings.name_x0,
                x1=self.settings.name_x1,
                y0=self.settings.name_y0,
                y1=self.settings.name_y1,
            )

            portrait = image.crop(portrait_box)
            occ_score = slot_occupancy_score(portrait)
            occupied = occ_score >= self.settings.min_occupied_score
            occ_conf = occupancy_confidence(
                occ_score,
                self.settings.min_occupied_score,
            )

            visual_hash = (
                portrait_dhash(
                    portrait,
                    hash_size=self.settings.portrait_hash_size,
                )
                if occupied
                else None
            )

            name_attempts = ()
            if occupied:
                name_attempts = self._name_attempts(
                    image.crop(name_box),
                    slot_index=slot_index,
                )

            result.slots.append(
                ShopSlotResult(
                    slot_index=slot_index,
                    card_box=card_box,
                    portrait_box=portrait_box,
                    name_box=name_box,
                    occupancy_score=occ_score,
                    occupied=occupied,
                    occupancy_confidence=occ_conf,
                    visual_hash=visual_hash,
                    name_attempts=name_attempts,
                )
            )

        observation = self.build_observation(
            result,
            match_id=match_id,
            timestamp_s=timestamp_s,
            evidence_id=evidence_id,
            hash_consensus=None,
        )
        if observation is not None:
            result.observations.append(observation)
        return result

    def build_observation(
        self,
        result: ShopRecognitionResult,
        *,
        match_id: str,
        timestamp_s: float,
        evidence_id: str,
        hash_consensus: dict[str, HashConsensusEntry] | None,
    ) -> Observation | None:
        if not result.shop_present:
            return None

        slot_payloads = []
        slot_confidences = []
        complete = True

        for slot in result.slots:
            best = slot.best_name_attempt
            ocr_token = (
                best.normalized_name
                if best is not None and best.valid
                and best.confidence >= self.settings.min_name_confidence
                else None
            )
            ocr_confidence = (
                float(best.confidence)
                if best is not None and ocr_token is not None
                else 0.0
            )

            resolution = None
            if slot.occupied:
                resolution = self.identity_resolver.resolve(
                    ocr_token,
                    ocr_confidence,
                    visual_hash=slot.visual_hash,
                    hash_consensus=hash_consensus,
                )

            identity_ok = (
                resolution is not None
                and resolution.identity_confidence
                >= self.settings.min_identity_confidence
            )
            resolved_name = (
                resolution.resolved_name if identity_ok else None
            )

            if slot.occupied and not identity_ok:
                complete = False

            slot_payloads.append(
                {
                    "index": slot.slot_index,
                    "occupied": slot.occupied,
                    # Compatibility alias. From 0.9.1 this is canonical lexicon
                    # identity, not an arbitrary OCR token.
                    "normalized_name": resolved_name,
                    "resolved_name": resolved_name,
                    "visual_hash": slot.visual_hash,
                    "occupancy_score": float(slot.occupancy_score),
                    "occupancy_confidence": float(
                        slot.occupancy_confidence
                    ),
                    "raw_text": (
                        best.raw_text if best is not None else ""
                    ),
                    "ocr_variant": (
                        best.variant if best is not None else None
                    ),
                    "ocr_token": ocr_token,
                    "ocr_confidence": ocr_confidence,
                    "identity_confidence": (
                        float(resolution.identity_confidence)
                        if identity_ok else 0.0
                    ),
                    "identity_method": (
                        resolution.identity_method
                        if identity_ok else None
                    ),
                    "identity_similarity": (
                        float(resolution.similarity)
                        if resolution is not None else 0.0
                    ),
                    "identity_fuzzy_margin": (
                        float(resolution.fuzzy_margin)
                        if resolution is not None else 0.0
                    ),
                    "hash_consensus_support": (
                        int(resolution.hash_support)
                        if resolution is not None else 0
                    ),
                    "hash_consensus_ratio": (
                        float(resolution.hash_ratio)
                        if resolution is not None else 0.0
                    ),
                }
            )

            if slot.occupied:
                slot_confidences.append(
                    min(
                        slot.occupancy_confidence,
                        resolution.identity_confidence
                        if identity_ok and resolution is not None
                        else 0.0,
                    )
                )
            else:
                slot_confidences.append(slot.occupancy_confidence)

        snapshot_conf = min(
            [result.shop_presence_score, *slot_confidences]
        ) if slot_confidences else result.shop_presence_score

        if not complete or snapshot_conf < self.settings.min_observation_confidence:
            return None

        return Observation(
            observation_id=self._observation_id(evidence_id),
            match_id=match_id,
            timestamp_s=max(0.0, float(timestamp_s)),
            kind=ObservationKind.SHOP,
            value={
                "slots": slot_payloads,
                "occupied_count": result.occupied_count,
                "complete": True,
                "shop_presence_score": float(
                    result.shop_presence_score
                ),
                "ocr_engine": self.ocr_engine.name,
                "identity_lexicon_size": len(
                    self.identity_resolver.lexicon.names
                ),
                "hash_consensus_enabled": hash_consensus is not None,
            },
            confidence=max(0.0, min(snapshot_conf, 1.0)),
            evidence_ids=(evidence_id,),
            producer_version=self.settings.producer_version,
        )
