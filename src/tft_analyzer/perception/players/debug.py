from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from .recognizer import PlayerListRecognizer


def build_players_debug(
    image_path: Path | str,
    output_dir: Path | str,
    recognizer: PlayerListRecognizer,
    *,
    manual_row_index: int | None = None,
    player_name: str | None = None,
) -> dict[str, object]:
    image_path = Path(image_path)
    output_dir = Path(output_dir)

    rows_dir = output_dir / "rows"
    hp_dir = output_dir / "hp_candidates"

    rows_dir.mkdir(parents=True, exist_ok=True)
    hp_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as src:
        image = src.convert("RGB")

    width, height = image.size
    recognizer.registry.assert_compatible(width, height)

    panel_roi = recognizer.registry.resolve(
        "players_panel",
        width,
        height,
    )
    image.crop(panel_roi.box).save(output_dir / "players_panel.png")

    result = recognizer.recognize(
        image,
        match_id="debug",
        timestamp_s=0.0,
        evidence_id=f"debug-{image_path.stem}",
        manual_row_index=manual_row_index,
        player_name=player_name,
    )

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    for row in result.rows:
        selected = row.row_index == result.selected_row_index
        color = (255, 220, 40) if selected else (80, 220, 255)
        width_px = 4 if selected else 2

        draw.rectangle(row.box, outline=color, width=width_px)
        draw.text(
            (row.box[0] + 4, row.box[1] + 3),
            (
                f"row={row.row_index} "
                f"hl={row.highlight_score:.3f} "
                f"no_name={row.no_name_score:.3f}"
            ),
            fill=color,
        )

        image.crop(row.box).save(
            rows_dir / f"row_{row.row_index}.png"
        )

    for attempt in result.hp_attempts:
        image.crop(attempt.candidate_box).save(
            hp_dir
            / (
                f"row_{attempt.row_index}_"
                f"{attempt.candidate_name}_"
                f"{attempt.variant}.png"
            )
        )

    overlay_path = output_dir / "overlay.png"
    overlay.save(overlay_path)

    result_path = output_dir / "result.json"
    payload = {
        "schema_version": 1,
        "source_image": str(image_path),
        "profile_id": recognizer.registry.profile.profile_id,
        "producer_version": recognizer.settings.producer_version,
        "panel_present": result.panel_present,
        "panel_score": result.panel_score,
        "selected_row_index": result.selected_row_index,
        "self_method": result.self_method,
        "self_score": result.self_score,
        "self_margin": result.self_margin,
        "rows": [
            {
                "row_index": row.row_index,
                "box": row.box,
                "highlight_score": row.highlight_score,
                "name_presence_score": row.name_presence_score,
                "no_name_score": row.no_name_score,
                "name_text": row.name_text,
                "name_ocr_score": row.name_ocr_score,
                "name_match_score": row.name_match_score,
                "combined_self_score": row.combined_self_score,
            }
            for row in result.rows
        ],
        "hp_attempts": [
            {
                "row_index": attempt.row_index,
                "candidate_name": attempt.candidate_name,
                "candidate_box": attempt.candidate_box,
                "variant": attempt.variant,
                "raw_text": attempt.raw_text,
                "ocr_score": attempt.ocr_score,
                "hp": attempt.hp,
                "parser_confidence": attempt.parser_confidence,
                "confidence": attempt.confidence,
            }
            for attempt in result.hp_attempts
        ],
        "observations": [
            obs.model_dump(mode="json")
            for obs in result.observations
        ],
    }
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "result": result,
        "result_path": str(result_path),
        "overlay": str(overlay_path),
        "panel": str(output_dir / "players_panel.png"),
        "rows_dir": str(rows_dir),
        "hp_candidates_dir": str(hp_dir),
    }
