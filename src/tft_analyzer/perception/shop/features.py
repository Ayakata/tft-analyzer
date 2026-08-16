from __future__ import annotations

import numpy as np
from PIL import Image


def clamp01(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def shop_presence_score(image: Image.Image) -> float:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    if gray.size == 0:
        return 0.0

    contrast = float(gray.std())
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    edge = 0.5 * (
        (float((dx > 18).mean()) if dx.size else 0.0)
        + (float((dy > 18).mean()) if dy.size else 0.0)
    )
    bright = float((gray > 70).mean())

    return clamp01(
        0.45 * min(1.0, contrast / 40.0)
        + 0.40 * min(1.0, edge / 0.070)
        + 0.15 * min(1.0, bright / 0.12)
    )


def slot_occupancy_score(portrait: Image.Image) -> float:
    arr = np.asarray(portrait.convert("RGB"), dtype=np.float32)
    if arr.size == 0:
        return 0.0

    gray = arr.mean(axis=2)
    contrast = float(gray.std())

    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    edge = 0.5 * (
        (float((dx > 18).mean()) if dx.size else 0.0)
        + (float((dy > 18).mean()) if dy.size else 0.0)
    )

    saturation = float(
        (arr.max(axis=2) - arr.min(axis=2)).mean() / 255.0
    )

    return clamp01(
        0.45 * min(1.0, contrast / 32.0)
        + 0.40 * min(1.0, edge / 0.075)
        + 0.15 * min(1.0, saturation / 0.10)
    )


def occupancy_confidence(score: float, threshold: float) -> float:
    threshold = clamp01(threshold)
    score = clamp01(score)

    if score >= threshold:
        span = max(1e-6, 1.0 - threshold)
        return clamp01(0.55 + 0.45 * (score - threshold) / span)

    span = max(1e-6, threshold)
    return clamp01(0.55 + 0.45 * (threshold - score) / span)


def portrait_dhash(image: Image.Image, hash_size: int = 8) -> str:
    hash_size = max(4, int(hash_size))
    gray = image.convert("L").resize(
        (hash_size + 1, hash_size),
        Image.Resampling.LANCZOS,
    )
    arr = np.asarray(gray, dtype=np.int16)
    bits = arr[:, 1:] > arr[:, :-1]

    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bool(bit))

    width = (hash_size * hash_size + 3) // 4
    return f"{value:0{width}x}"
