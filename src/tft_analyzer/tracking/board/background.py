from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import ceil
from statistics import median

from .models import BackgroundPositionModel


FEATURE_NAMES = (
    "contrast",
    "edge_density",
    "saturation",
    "bright_fraction",
    "center_edge_delta",
    "center_saturation_delta",
)

FEATURE_WEIGHTS = {
    "contrast": 0.22,
    "edge_density": 0.30,
    "saturation": 0.10,
    "bright_fraction": 0.08,
    "center_edge_delta": 0.20,
    "center_saturation_delta": 0.10,
}

FEATURE_SCALE_FLOORS = {
    "contrast": 3.0,
    "edge_density": 0.008,
    "saturation": 0.020,
    "bright_fraction": 0.025,
    "center_edge_delta": 0.004,
    "center_saturation_delta": 0.004,
}


def _quantile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    x = p * (len(ordered) - 1)
    lo = int(x)
    hi = min(lo + 1, len(ordered) - 1)
    frac = x - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _mad_scale(values: list[float], floor: float) -> float:
    if not values:
        return float(floor)
    center = median(values)
    mad = median(abs(v - center) for v in values) * 1.4826
    return max(float(mad), float(floor))


def fit_background_models(
    samples_by_position: dict[str, list[dict]],
    *,
    source_quantile: float = 0.22,
    min_candidates: int = 12,
) -> dict[str, BackgroundPositionModel]:
    """
    Build one match-local background prototype per logical board/bench position.

    Candidate background samples are selected from the low raw-occupancy-score
    tail *for that same position*. This avoids comparing e.g. b0 foliage/UI
    texture to b7's very different empty-slot background.
    """
    if not 0.05 <= source_quantile <= 0.45:
        raise ValueError("source_quantile must be between 0.05 and 0.45")

    models = {}
    for position, samples in samples_by_position.items():
        valid = [
            s for s in samples
            if isinstance(s.get("features"), dict)
            and all(name in s["features"] for name in FEATURE_NAMES)
        ]
        if not valid:
            continue

        ordered = sorted(valid, key=lambda s: float(s.get("score", 0.0)))
        count = min(
            len(ordered),
            max(int(min_candidates), ceil(len(ordered) * source_quantile)),
        )
        background = ordered[:count]

        raw_scores = [float(s["score"]) for s in background]
        raw_med = float(median(raw_scores))
        raw_scale = _mad_scale(raw_scores, 0.040)

        medians = {}
        scales = {}
        for name in FEATURE_NAMES:
            values = [float(s["features"][name]) for s in background]
            medians[name] = float(median(values))
            scales[name] = _mad_scale(values, FEATURE_SCALE_FLOORS[name])

        models[position] = BackgroundPositionModel(
            position=position,
            candidate_count=len(background),
            total_count=len(valid),
            source_quantile=source_quantile,
            raw_score_median=raw_med,
            raw_score_scale=raw_scale,
            feature_medians=medians,
            feature_scales=scales,
        )

    return models


def foreground_score(sample: dict, model: BackgroundPositionModel) -> float:
    """Return 0..1 match-local deviation from this position's background."""
    features = sample.get("features") or {}

    feature_distance = 0.0
    for name, weight in FEATURE_WEIGHTS.items():
        value = float(features.get(name, model.feature_medians[name]))
        z = abs(value - model.feature_medians[name]) / model.feature_scales[name]
        # Smooth robust z into [0,1]. z=2 -> .5, z=6 -> .75.
        evidence = z / (z + 2.0)
        feature_distance += weight * evidence

    raw_score = float(sample.get("score", model.raw_score_median))
    raw_z = max(0.0, (raw_score - model.raw_score_median) / model.raw_score_scale)
    raw_evidence = raw_z / (raw_z + 3.0)

    return max(0.0, min(1.0, 0.65 * feature_distance + 0.35 * raw_evidence))


def classify_foreground(
    score: float,
    *,
    empty_below: float = 0.34,
    occupied_above: float = 0.58,
) -> tuple[str, float]:
    if empty_below >= occupied_above:
        raise ValueError("empty_below must be < occupied_above")

    score = max(0.0, min(float(score), 1.0))
    if score <= empty_below:
        confidence = 0.60 + 0.40 * (empty_below - score) / max(empty_below, 1e-6)
        return "empty", max(0.0, min(confidence, 1.0))
    if score >= occupied_above:
        confidence = 0.60 + 0.40 * (score - occupied_above) / max(1.0 - occupied_above, 1e-6)
        return "occupied", max(0.0, min(confidence, 1.0))

    middle = 0.5 * (empty_below + occupied_above)
    half = 0.5 * (occupied_above - empty_below)
    distance = abs(score - middle) / max(half, 1e-6)
    return "uncertain", max(0.0, min(0.72 - 0.16 * distance, 1.0))
