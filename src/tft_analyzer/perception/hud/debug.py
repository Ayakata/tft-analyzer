from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .recognizer import DEFAULT_FIELDS, HUDRecognizer


def build_hud_debug(
    image_path: Path | str,
    output_dir: Path | str,
    recognizer: HUDRecognizer,
) -> dict[str, object]:
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    crops_dir = output_dir / "crops"
    preprocessed_dir = output_dir / "preprocessed"
    stage_candidates_dir = output_dir / "stage_candidates"

    crops_dir.mkdir(parents=True, exist_ok=True)
    preprocessed_dir.mkdir(parents=True, exist_ok=True)
    stage_candidates_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as src:
        image = src.convert("RGB")

    width, height = image.size
    recognizer.registry.assert_compatible(width, height)

    stage_context = recognizer.registry.resolve("stage_value", width, height)
    stage_search = recognizer.registry.resolve(
        "stage_search_region", width, height
    )
    image.crop(stage_context.box).save(crops_dir / "stage_context.png")
    image.crop(stage_search.box).save(crops_dir / "stage_search_region.png")

    for candidate in recognizer.stage_localizer.candidates(
        image, recognizer.registry
    ):
        candidate.image.save(
            stage_candidates_dir / f"{candidate.name}.png"
        )
        for variant in recognizer._variants(candidate.image):
            variant.image.save(
                stage_candidates_dir
                / f"{candidate.name}_{variant.name}.png"
            )

    for spec in DEFAULT_FIELDS:
        context_roi = recognizer.registry.resolve(
            spec.context_roi_name, width, height
        )
        ocr_roi = recognizer.registry.resolve(
            spec.roi_name, width, height
        )

        context_crop = image.crop(context_roi.box)
        ocr_crop = image.crop(ocr_roi.box)

        context_crop.save(crops_dir / f"{spec.field}_context.png")
        ocr_crop.save(crops_dir / f"{spec.field}_ocr.png")

        for variant in recognizer._variants(ocr_crop):
            variant.image.save(
                preprocessed_dir / f"{spec.field}_{variant.name}.png"
            )

    result = recognizer.recognize(
        image,
        match_id="debug",
        timestamp_s=0.0,
        evidence_id=f"debug-{image_path.stem}",
    )

    payload = {
        "schema_version": 2,
        "source_image": str(image_path),
        "profile_id": recognizer.registry.profile.profile_id,
        "producer_version": recognizer.producer_version,
        "attempts": [
            {
                "field": a.field,
                "roi_name": a.roi_name,
                "variant": a.variant,
                "raw_text": a.raw_text,
                "ocr_score": a.ocr_score,
                "confidence": a.confidence,
                "presence_passed": a.presence_passed,
                "presence_score": a.presence_score,
                "presence_reason": a.presence_reason,
                "candidate_name": a.candidate_name,
                "candidate_box": a.candidate_box,
                "parsed": (
                    {
                        "value": a.parsed.value,
                        "normalized_text": a.parsed.normalized_text,
                        "parser_confidence": a.parsed.parser_confidence,
                    }
                    if a.parsed is not None
                    else None
                ),
            }
            for a in result.attempts
        ],
        "observations": [
            o.model_dump(mode="json")
            for o in result.observations
        ],
    }

    result_path = output_dir / "hud_result.json"
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "output_dir": output_dir,
        "result_path": result_path,
        "crops_dir": crops_dir,
        "preprocessed_dir": preprocessed_dir,
        "stage_candidates_dir": stage_candidates_dir,
        "result": result,
    }
