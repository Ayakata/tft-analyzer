from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from PIL import Image


SCENE_GUARD_VERSION = "arena-scene-guard-0.13.4"

# These anchors deliberately avoid the shop/bench/lower-choice UI and the
# playable board centre where units, spell effects and portals are expected.
#
# Coordinates are normalized to the captured TFT window.
DEFAULT_ARENA_ANCHORS: tuple[
    tuple[str, tuple[float, float, float, float]],
    ...,
] = (
    ("top_left", (0.24, 0.10, 0.34, 0.22)),
    ("top_right", (0.66, 0.10, 0.76, 0.22)),
    ("left_wall", (0.20, 0.28, 0.27, 0.58)),
    ("right_wall", (0.73, 0.28, 0.80, 0.58)),
)


@dataclass(frozen=True, slots=True)
class ArenaSceneGuardSettings:
    descriptor_size: int = 48
    reference_fraction: float = 0.60
    score_threshold: float = 0.12
    anchor_threshold: float = 0.15
    min_anchor_pass: int = 3


@dataclass(frozen=True, slots=True)
class ArenaSceneFrameResult:
    evidence_id: str
    valid: bool
    score: float
    anchor_pass_count: int
    anchor_scores: dict[str, float]


@dataclass(slots=True)
class ArenaSceneGuardModel:
    settings: ArenaSceneGuardSettings
    anchors: tuple[
        tuple[str, tuple[float, float, float, float]],
        ...,
    ]
    references: dict[str, np.ndarray]
    fit_frame_count: int
    reference_frame_count: int
    fit_score_stats: dict[str, float]

    def score_descriptors(
        self,
        evidence_id: str,
        descriptors: dict[str, np.ndarray],
    ) -> ArenaSceneFrameResult:
        anchor_scores: dict[str, float] = {}

        for name, _ in self.anchors:
            reference = self.references[name]
            current = descriptors[name]
            distance = float(
                np.mean(
                    np.abs(
                        current.astype(np.float32)
                        - reference.astype(np.float32)
                    )
                )
                / 255.0
            )
            anchor_scores[name] = distance

        ordered = sorted(anchor_scores.values())
        score = float(np.median(ordered))
        anchor_pass_count = sum(
            value <= self.settings.anchor_threshold
            for value in anchor_scores.values()
        )

        valid = (
            score <= self.settings.score_threshold
            and anchor_pass_count >= self.settings.min_anchor_pass
        )

        return ArenaSceneFrameResult(
            evidence_id=evidence_id,
            valid=valid,
            score=score,
            anchor_pass_count=anchor_pass_count,
            anchor_scores=anchor_scores,
        )


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "mean": 0.0,
            "q10": 0.0,
            "q50": 0.0,
            "q90": 0.0,
            "max": 0.0,
        }

    arr = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(arr.mean()),
        "q10": float(np.quantile(arr, 0.10)),
        "q50": float(np.quantile(arr, 0.50)),
        "q90": float(np.quantile(arr, 0.90)),
        "max": float(arr.max()),
    }


def _crop_descriptor(
    image: Image.Image,
    box: tuple[float, float, float, float],
    *,
    size: int,
) -> np.ndarray:
    width, height = image.size
    x0, y0, x1, y1 = box

    left = max(0, min(width - 1, int(round(x0 * width))))
    top = max(0, min(height - 1, int(round(y0 * height))))
    right = max(left + 1, min(width, int(round(x1 * width))))
    bottom = max(top + 1, min(height, int(round(y1 * height))))

    crop = image.crop((left, top, right, bottom)).convert("RGB")
    crop = crop.resize(
        (size, size),
        Image.Resampling.BILINEAR,
    )
    return np.asarray(crop, dtype=np.uint8)


def extract_arena_descriptors(
    image_path: Path | str,
    *,
    settings: ArenaSceneGuardSettings,
    anchors=DEFAULT_ARENA_ANCHORS,
) -> dict[str, np.ndarray]:
    with Image.open(image_path) as src:
        image = src.convert("RGB")

    return {
        name: _crop_descriptor(
            image,
            box,
            size=settings.descriptor_size,
        )
        for name, box in anchors
    }


def _median_references(
    rows: list[dict[str, np.ndarray]],
    indices: list[int],
    anchors,
) -> dict[str, np.ndarray]:
    references: dict[str, np.ndarray] = {}

    for name, _ in anchors:
        stack = np.stack(
            [rows[i][name] for i in indices],
            axis=0,
        )
        references[name] = np.median(
            stack,
            axis=0,
        ).astype(np.uint8)

    return references


def fit_arena_scene_guard(
    evidence_paths: list[tuple[str, Path]],
    *,
    settings: ArenaSceneGuardSettings | None = None,
    anchors=DEFAULT_ARENA_ANCHORS,
) -> tuple[ArenaSceneGuardModel, dict[str, ArenaSceneFrameResult]]:
    settings = settings or ArenaSceneGuardSettings()

    if settings.descriptor_size < 8:
        raise ValueError("descriptor_size must be >= 8")
    if not 0.25 <= settings.reference_fraction <= 1.0:
        raise ValueError("reference_fraction must be in [0.25, 1.0]")
    if settings.min_anchor_pass < 1:
        raise ValueError("min_anchor_pass must be >= 1")
    if settings.min_anchor_pass > len(anchors):
        raise ValueError("min_anchor_pass exceeds anchor count")
    if not evidence_paths:
        raise ValueError("Cannot fit arena scene guard without evidence frames")

    evidence_ids: list[str] = []
    rows: list[dict[str, np.ndarray]] = []

    for evidence_id, path in evidence_paths:
        if not Path(path).exists():
            continue
        evidence_ids.append(str(evidence_id))
        rows.append(
            extract_arena_descriptors(
                path,
                settings=settings,
                anchors=anchors,
            )
        )

    if not rows:
        raise ValueError("No readable evidence frames for arena scene guard")

    # Pass 1: median across all frames. Normal TFT arena frames are expected to
    # dominate a match; the median is robust to a minority of full-screen
    # overlays and special choice scenes.
    all_indices = list(range(len(rows)))
    initial_refs = _median_references(
        rows,
        all_indices,
        anchors,
    )
    initial_model = ArenaSceneGuardModel(
        settings=settings,
        anchors=tuple(anchors),
        references=initial_refs,
        fit_frame_count=len(rows),
        reference_frame_count=len(rows),
        fit_score_stats={},
    )

    initial_scores: list[tuple[float, int]] = []
    for i, (evidence_id, descriptors) in enumerate(
        zip(evidence_ids, rows)
    ):
        result = initial_model.score_descriptors(
            evidence_id,
            descriptors,
        )
        initial_scores.append((result.score, i))

    # Pass 2: recompute the reference only from the most arena-like fraction.
    # This removes residual influence from loading/choice/full-screen scenes.
    initial_scores.sort(key=lambda item: item[0])
    reference_count = max(
        1,
        int(round(len(rows) * settings.reference_fraction)),
    )
    reference_indices = [
        index
        for _, index in initial_scores[:reference_count]
    ]
    references = _median_references(
        rows,
        reference_indices,
        anchors,
    )

    model = ArenaSceneGuardModel(
        settings=settings,
        anchors=tuple(anchors),
        references=references,
        fit_frame_count=len(rows),
        reference_frame_count=reference_count,
        fit_score_stats={},
    )

    results: dict[str, ArenaSceneFrameResult] = {}
    scores: list[float] = []

    for evidence_id, descriptors in zip(
        evidence_ids,
        rows,
    ):
        result = model.score_descriptors(
            evidence_id,
            descriptors,
        )
        results[evidence_id] = result
        scores.append(result.score)

    model.fit_score_stats = _quantiles(scores)
    return model, results


def save_arena_scene_guard(
    model: ArenaSceneGuardModel,
    frame_results: dict[str, ArenaSceneFrameResult],
    output_dir: Path | str,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    anchors_dir = output_dir / "anchors"
    anchors_dir.mkdir(parents=True, exist_ok=True)

    reference_paths: dict[str, str] = {}
    for name, _ in model.anchors:
        path = anchors_dir / f"{name}_reference.png"
        Image.fromarray(
            model.references[name],
            mode="RGB",
        ).save(path)
        reference_paths[name] = str(path)

    valid_count = sum(
        result.valid
        for result in frame_results.values()
    )
    invalid_count = len(frame_results) - valid_count

    payload = {
        "schema_version": 1,
        "scene_guard_version": SCENE_GUARD_VERSION,
        "settings": {
            "descriptor_size": model.settings.descriptor_size,
            "reference_fraction": model.settings.reference_fraction,
            "score_threshold": model.settings.score_threshold,
            "anchor_threshold": model.settings.anchor_threshold,
            "min_anchor_pass": model.settings.min_anchor_pass,
        },
        "anchors": {
            name: list(box)
            for name, box in model.anchors
        },
        "fit_frame_count": model.fit_frame_count,
        "reference_frame_count": model.reference_frame_count,
        "fit_score_stats": model.fit_score_stats,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "reference_paths": reference_paths,
        "frames": {
            evidence_id: {
                "valid": result.valid,
                "score": result.score,
                "anchor_pass_count": result.anchor_pass_count,
                "anchor_scores": result.anchor_scores,
            }
            for evidence_id, result in frame_results.items()
        },
    }

    model_path = output_dir / "scene_guard.json"
    model_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "scene_guard_dir": str(output_dir),
        "scene_guard_path": str(model_path),
    }
