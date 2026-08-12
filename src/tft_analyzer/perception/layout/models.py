from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NormalizedROI(BaseModel):
    """Rectangle in normalized image coordinates [0, 1]."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)
    group: str = "default"
    purpose: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_bounds(self) -> "NormalizedROI":
        eps = 1e-9
        if self.x + self.w > 1.0 + eps:
            raise ValueError("ROI x + w must be <= 1")
        if self.y + self.h > 1.0 + eps:
            raise ValueError("ROI y + h must be <= 1")
        return self


class PixelROI(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left: int = Field(ge=0)
    top: int = Field(ge=0)
    right: int = Field(gt=0)
    bottom: int = Field(gt=0)

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


class LayoutProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    profile_id: str
    description: str | None = None

    aspect_ratio: float = Field(gt=0)
    aspect_ratio_tolerance: float = Field(default=0.03, gt=0)

    reference_width: int = Field(gt=0)
    reference_height: int = Field(gt=0)
    ui_scale_hint: str | None = None

    rois: dict[str, NormalizedROI]
    metadata: dict[str, Any] = {}

    def matches(self, width: int, height: int) -> bool:
        if width <= 0 or height <= 0:
            return False
        actual = width / height
        relative_error = abs(actual - self.aspect_ratio) / self.aspect_ratio
        return relative_error <= self.aspect_ratio_tolerance
