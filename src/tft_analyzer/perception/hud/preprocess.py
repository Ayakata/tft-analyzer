from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageOps


@dataclass(frozen=True, slots=True)
class PreprocessedVariant:
    name: str
    image: Image.Image


def _pad(
    image: Image.Image,
    horizontal_ratio: float,
    *,
    fill: tuple[int, int, int],
) -> Image.Image:
    pad_x = max(5, round(image.width * horizontal_ratio))
    pad_y = max(5, round(image.height * 0.18))
    return ImageOps.expand(
        image,
        border=(pad_x, pad_y, pad_x, pad_y),
        fill=fill,
    )


def build_variants(
    crop: Image.Image,
    *,
    primary_upscale: int = 4,
    fallback_upscale: int = 5,
    horizontal_padding_ratio: float = 0.16,
    binary_threshold: int = 150,
) -> list[PreprocessedVariant]:
    """
    Build OCR variants for an already-tight HUD text ROI.

    Variant 1 keeps the original appearance.
    Variant 2 removes color and expands contrast.
    Variant 3 turns bright TFT glyphs into dark text on a white background,
    which removes most remaining HUD texture/background information.
    """
    crop = crop.convert("RGB")

    rgb = crop.resize(
        (
            max(1, crop.width * primary_upscale),
            max(1, crop.height * primary_upscale),
        ),
        Image.Resampling.LANCZOS,
    )
    rgb = _pad(rgb, horizontal_padding_ratio, fill=(0, 0, 0))

    gray_base = ImageOps.grayscale(crop)
    gray_base = ImageOps.autocontrast(gray_base)
    gray_base = ImageEnhance.Contrast(gray_base).enhance(1.45)

    gray = gray_base.convert("RGB").resize(
        (
            max(1, crop.width * fallback_upscale),
            max(1, crop.height * fallback_upscale),
        ),
        Image.Resampling.LANCZOS,
    )
    gray = _pad(gray, horizontal_padding_ratio, fill=(0, 0, 0))

    threshold = max(0, min(int(binary_threshold), 255))
    binary = gray_base.point(
        lambda p: 0 if p >= threshold else 255,
        mode="1",
    ).convert("RGB")
    binary = binary.resize(
        (
            max(1, crop.width * fallback_upscale),
            max(1, crop.height * fallback_upscale),
        ),
        Image.Resampling.NEAREST,
    )
    binary = _pad(binary, horizontal_padding_ratio, fill=(255, 255, 255))

    return [
        PreprocessedVariant(name="rgb_tight", image=rgb),
        PreprocessedVariant(name="gray_tight", image=gray),
        PreprocessedVariant(name="binary_tight", image=binary),
    ]
