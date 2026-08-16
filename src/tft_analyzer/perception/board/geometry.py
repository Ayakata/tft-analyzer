from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    x: float
    y: float


def _px(point: NormalizedPoint, width: int, height: int) -> tuple[int, int]:
    return (round(point.x * width), round(point.y * height))


def board_centers(
    *,
    width: int,
    height: int,
    row_left: tuple[NormalizedPoint, ...],
    row_right: tuple[NormalizedPoint, ...],
    cols: int = 7,
) -> list[tuple[int, int, int, int]]:
    if len(row_left) != len(row_right):
        raise ValueError("row_left and row_right must have the same size")
    if cols < 2:
        raise ValueError("cols must be >= 2")
    result = []
    for row, (left, right) in enumerate(zip(row_left, row_right)):
        lx, ly = _px(left, width, height)
        rx, ry = _px(right, width, height)
        for col in range(cols):
            t = col / (cols - 1)
            x = round(lx + (rx - lx) * t)
            y = round(ly + (ry - ly) * t)
            result.append((row, col, x, y))
    return result


def bench_centers(
    *,
    width: int,
    height: int,
    left: NormalizedPoint,
    right: NormalizedPoint,
    slots: int = 9,
) -> list[tuple[int, int, int]]:
    if slots < 2:
        raise ValueError("slots must be >= 2")
    lx, ly = _px(left, width, height)
    rx, ry = _px(right, width, height)
    return [
        (
            index,
            round(lx + (rx - lx) * index / (slots - 1)),
            round(ly + (ry - ly) * index / (slots - 1)),
        )
        for index in range(slots)
    ]


def centered_box(
    center: tuple[int, int],
    *,
    width: int,
    height: int,
    half_width: int,
    up: int,
    down: int,
) -> tuple[int, int, int, int]:
    cx, cy = center
    left = max(0, cx - half_width)
    right = min(width, cx + half_width)
    top = max(0, cy - up)
    bottom = min(height, cy + down)
    return (left, top, max(left + 1, right), max(top + 1, bottom))
