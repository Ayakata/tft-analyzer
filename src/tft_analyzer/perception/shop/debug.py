from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from .recognizer import ShopRecognizer


def build_shop_debug(
    image_path: Path | str,
    output_dir: Path | str,
    recognizer: ShopRecognizer,
) -> dict[str, object]:
    image_path = Path(image_path)
    output_dir = Path(output_dir)

    cards_dir = output_dir / "cards"
    portraits_dir = output_dir / "portraits"
    names_dir = output_dir / "names"

    cards_dir.mkdir(parents=True, exist_ok=True)
    portraits_dir.mkdir(parents=True, exist_ok=True)
    names_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as src:
        image = src.convert("RGB")

    result = recognizer.recognize(
        image,
        match_id="debug",
        timestamp_s=0.0,
        evidence_id=f"debug-{image_path.stem}",
    )

    width, height = image.size
    shop_roi = recognizer.registry.resolve("shop_region", width, height)
    image.crop(shop_roi.box).save(output_dir / "shop_region.png")

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    for slot in result.slots:
        color = (70, 230, 110) if slot.occupied else (90, 180, 255)
        draw.rectangle(slot.card_box, outline=color, width=3)
        draw.rectangle(slot.name_box, outline=(255, 220, 60), width=2)
        draw.text(
            (slot.card_box[0] + 4, slot.card_box[1] + 3),
            (
                f"{slot.slot_index} "
                f"{'OCC' if slot.occupied else 'EMPTY'} "
                f"{slot.occupancy_score:.2f}"
            ),
            fill=color,
        )

        image.crop(slot.card_box).save(
            cards_dir / f"slot_{slot.slot_index}.png"
        )
        image.crop(slot.portrait_box).save(
            portraits_dir / f"slot_{slot.slot_index}.png"
        )
        image.crop(slot.name_box).save(
            names_dir / f"slot_{slot.slot_index}.png"
        )

    overlay_path = output_dir / "overlay.png"
    overlay.save(overlay_path)

    payload = {
        "schema_version": 1,
        "source_image": str(image_path),
        "profile_id": recognizer.registry.profile.profile_id,
        "producer_version": recognizer.settings.producer_version,
        "shop_present": result.shop_present,
        "shop_presence_score": result.shop_presence_score,
        "occupied_count": result.occupied_count,
        "raw_complete": result.complete,
        "resolved_complete": bool(result.observations),
        "slots": [
            {
                "slot_index": slot.slot_index,
                "card_box": slot.card_box,
                "portrait_box": slot.portrait_box,
                "name_box": slot.name_box,
                "occupancy_score": slot.occupancy_score,
                "occupied": slot.occupied,
                "occupancy_confidence": slot.occupancy_confidence,
                "visual_hash": slot.visual_hash,
                "name_attempts": [
                    {
                        "variant": a.variant,
                        "raw_text": a.raw_text,
                        "normalized_name": a.normalized_name,
                        "ocr_score": a.ocr_score,
                        "parser_confidence": a.parser_confidence,
                        "confidence": a.confidence,
                    }
                    for a in slot.name_attempts
                ],
            }
            for slot in result.slots
        ],
        "observations": [
            observation.model_dump(mode="json")
            for observation in result.observations
        ],
    }

    result_path = output_dir / "result.json"
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "result": result,
        "result_path": str(result_path),
        "overlay": str(overlay_path),
        "shop_region": str(output_dir / "shop_region.png"),
        "cards_dir": str(cards_dir),
        "portraits_dir": str(portraits_dir),
        "names_dir": str(names_dir),
    }
