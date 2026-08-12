from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .registry import ROIRegistry


_PALETTE = [
    (255, 90, 90),
    (255, 210, 70),
    (80, 220, 255),
    (220, 100, 255),
    (80, 235, 125),
    (255, 155, 60),
    (120, 150, 255),
]


def _color_for(name: str) -> tuple[int, int, int]:
    digest = hashlib.sha1(name.encode("utf-8")).digest()
    return _PALETTE[digest[0] % len(_PALETTE)]


def _font(size: int = 18):
    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def build_roi_debug(
    image_path: Path | str,
    registry: ROIRegistry,
    output_dir: Path | str,
    *,
    selected_names: list[str] | None = None,
) -> dict[str, object]:
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    crops_dir = output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as src:
        image = src.convert("RGB")

    width, height = image.size
    registry.assert_compatible(width, height)

    available = registry.names(enabled_only=True)
    names = selected_names or available
    unknown = sorted(set(names) - set(available))
    if unknown:
        raise KeyError(f"Unknown or disabled ROI(s): {', '.join(unknown)}")

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    font = _font(max(13, round(height / 60)))
    line_width = max(2, round(min(width, height) / 450))

    manifest_rois: dict[str, object] = {}

    for name in names:
        cfg = registry.normalized(name)
        pixel = registry.resolve(name, width, height)
        color = _color_for(name)

        crop = image.crop(pixel.box)
        crop_path = crops_dir / f"{_safe_filename(name)}.png"
        crop.save(crop_path, format="PNG")

        draw.rectangle(pixel.box, outline=color, width=line_width)

        label = name
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = pixel.left + 3
        ty = max(0, pixel.top - th - 5)
        if ty == 0 or ty + th + 4 > pixel.top:
            ty = pixel.top + 3
        draw.rectangle(
            (tx - 2, ty - 2, tx + tw + 3, ty + th + 3),
            fill=(0, 0, 0),
        )
        draw.text((tx, ty), label, fill=color, font=font)

        manifest_rois[name] = {
            "group": cfg.group,
            "purpose": cfg.purpose,
            "normalized": {
                "x": cfg.x,
                "y": cfg.y,
                "w": cfg.w,
                "h": cfg.h,
            },
            "pixels": pixel.model_dump(),
            "crop": crop_path.relative_to(output_dir).as_posix(),
        }

    overlay_path = output_dir / "overlay.png"
    overlay.save(overlay_path, format="PNG")

    manifest = {
        "schema_version": 1,
        "source_image": str(image_path),
        "image_width": width,
        "image_height": height,
        "profile_id": registry.profile.profile_id,
        "profile_aspect_ratio": registry.profile.aspect_ratio,
        "rois": manifest_rois,
    }
    manifest_path = output_dir / "roi_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "output_dir": output_dir,
        "overlay": overlay_path,
        "manifest": manifest_path,
        "crops_dir": crops_dir,
        "roi_count": len(names),
    }
