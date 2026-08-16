from __future__ import annotations

import numpy as np
from PIL import Image

from .models import OccupancyFeatures


def clamp01(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def region_presence_score(image: Image.Image) -> float:
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    if arr.size == 0:
        return 0.0
    gray = arr.mean(axis=2)
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    edge = 0.5 * (
        (float((dx > 16).mean()) if dx.size else 0.0)
        + (float((dy > 16).mean()) if dy.size else 0.0)
    )
    contrast = float(gray.std())
    saturation = float((arr.max(axis=2) - arr.min(axis=2)).mean() / 255.0)
    return clamp01(
        0.42 * min(1.0, contrast / 38.0)
        + 0.38 * min(1.0, edge / 0.065)
        + 0.20 * min(1.0, saturation / 0.15)
    )


def _edge_density(gray: np.ndarray, *, valid_mask: np.ndarray | None = None, threshold: float = 20.0) -> float:
    if gray.size == 0:
        return 0.0
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    if valid_mask is None:
        xs = float((dx > threshold).mean()) if dx.size else 0.0
        ys = float((dy > threshold).mean()) if dy.size else 0.0
        return 0.5 * (xs + ys)
    valid = np.asarray(valid_mask, dtype=bool)
    xv = valid[:,1:] & valid[:,:-1]
    yv = valid[1:,:] & valid[:-1,:]
    xc = int(xv.sum()); yc = int(yv.sum())
    xs = float(((dx > threshold) & xv).sum()) / xc if xc else 0.0
    ys = float(((dy > threshold) & yv).sum()) / yc if yc else 0.0
    return 0.5 * (xs + ys)


def occupancy_features(image: Image.Image, *, mask: Image.Image | np.ndarray | None = None) -> OccupancyFeatures:
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    if arr.size == 0:
        return OccupancyFeatures(0,0,0,0,0,0)
    gray = arr.mean(axis=2)
    sat_map = (arr.max(axis=2) - arr.min(axis=2)) / 255.0
    h,w = gray.shape
    if mask is None:
        valid = np.ones((h,w), dtype=bool)
    else:
        m = np.asarray(mask.convert('L') if isinstance(mask,Image.Image) else mask)
        if m.shape != (h,w):
            raise ValueError('occupancy mask must have same HxW as image crop')
        valid = m > 0
    if not valid.any():
        return OccupancyFeatures(0,0,0,0,0,0)

    x0,x1=int(w*.22),max(int(w*.78),int(w*.22)+1)
    y0,y1=int(h*.16),max(int(h*.84),int(h*.16)+1)
    center_valid=np.zeros_like(valid)
    center_valid[y0:y1,x0:x1]=True
    center_valid &= valid

    vg=gray[valid]; vs=sat_map[valid]
    edge=_edge_density(gray, valid_mask=valid)
    if center_valid.any():
        ce=_edge_density(gray[y0:y1,x0:x1], valid_mask=center_valid[y0:y1,x0:x1])
    else: ce=0.0
    sat=float(vs.mean())
    cs=float(sat_map[center_valid].mean()) if center_valid.any() else 0.0
    return OccupancyFeatures(
        contrast=float(vg.std()),
        edge_density=edge,
        saturation=sat,
        bright_fraction=float((vg>150).mean()),
        center_edge_delta=max(0.0,ce-edge),
        center_saturation_delta=max(0.0,cs-sat),
    )


def occupancy_score(features: OccupancyFeatures) -> float:
    return clamp01(
        0.26 * min(1.0, features.contrast / 48.0)
        + 0.30 * min(1.0, features.edge_density / 0.12)
        + 0.20 * min(1.0, features.saturation / 0.22)
        + 0.08 * min(1.0, features.bright_fraction / 0.18)
        + 0.10 * min(1.0, features.center_edge_delta / 0.06)
        + 0.06 * min(1.0, features.center_saturation_delta / 0.10)
    )


def classify_occupancy(score: float, *, empty_below: float, occupied_above: float) -> tuple[str,float]:
    score=clamp01(score); empty_below=clamp01(empty_below); occupied_above=clamp01(occupied_above)
    if empty_below >= occupied_above: raise ValueError('empty_below must be < occupied_above')
    if score <= empty_below:
        confidence=0.55+0.45*(empty_below-score)/max(empty_below,1e-6)
        return 'empty',clamp01(confidence)
    if score >= occupied_above:
        confidence=0.55+0.45*(score-occupied_above)/max(1.0-occupied_above,1e-6)
        return 'occupied',clamp01(confidence)
    middle=.5*(empty_below+occupied_above); half=.5*(occupied_above-empty_below)
    distance=abs(score-middle)/max(half,1e-6)
    return 'uncertain',clamp01(.75-.20*distance)
