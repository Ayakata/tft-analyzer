from __future__ import annotations

from pathlib import Path

import yaml

from .models import LayoutProfile, NormalizedROI, PixelROI


class LayoutMismatchError(ValueError):
    pass


class ROIRegistry:
    def __init__(self, profile: LayoutProfile) -> None:
        self.profile = profile

    @classmethod
    def from_yaml(cls, path: Path | str) -> "ROIRegistry":
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            payload = yaml.safe_load(f)
        if not isinstance(payload, dict):
            raise ValueError(f"Layout profile must be a YAML mapping: {path}")
        return cls(LayoutProfile.model_validate(payload))

    def assert_compatible(self, width: int, height: int) -> None:
        if self.profile.matches(width, height):
            return
        actual = width / height
        raise LayoutMismatchError(
            f"Image aspect ratio {actual:.5f} ({width}x{height}) does not match "
            f"profile {self.profile.profile_id!r} ratio "
            f"{self.profile.aspect_ratio:.5f} ± "
            f"{self.profile.aspect_ratio_tolerance * 100:.1f}%"
        )

    def names(self, *, enabled_only: bool = True) -> list[str]:
        items = []
        for name, roi in self.profile.rois.items():
            if enabled_only and not roi.enabled:
                continue
            items.append(name)
        return items

    def normalized(self, name: str) -> NormalizedROI:
        try:
            return self.profile.rois[name]
        except KeyError as exc:
            raise KeyError(f"Unknown ROI {name!r}") from exc

    def resolve(self, name: str, width: int, height: int) -> PixelROI:
        self.assert_compatible(width, height)
        roi = self.normalized(name)

        left = int(round(roi.x * width))
        top = int(round(roi.y * height))
        right = int(round((roi.x + roi.w) * width))
        bottom = int(round((roi.y + roi.h) * height))

        left = max(0, min(left, width - 1))
        top = max(0, min(top, height - 1))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))

        return PixelROI(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
        )

    def resolve_all(
        self,
        width: int,
        height: int,
        *,
        enabled_only: bool = True,
    ) -> dict[str, PixelROI]:
        return {
            name: self.resolve(name, width, height)
            for name in self.names(enabled_only=enabled_only)
        }
