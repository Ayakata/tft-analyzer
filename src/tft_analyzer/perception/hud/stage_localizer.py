from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from tft_analyzer.perception.layout import ROIRegistry


@dataclass(frozen=True, slots=True)
class StageCandidate:
    name: str
    box: tuple[int, int, int, int]
    image: Image.Image
    x_offset_px: int


class StageLocalizer:
    """
    Generate horizontally shifted OCR windows inside stage_search_region.

    Early 1-x rounds are rendered a little farther right than later stages.
    The caller evaluates all candidates and selects the best valid N-N parse.
    """

    def __init__(
        self,
        *,
        candidate_width_px_at_1920: int = 56,
        candidate_height_px_at_1080: int = 28,
        x_offsets_px_at_1920: tuple[int, ...] = (-20, -10, 0, 10, 20, 30),
        y_offset_px_at_1080: int = 0,
    ) -> None:
        self.candidate_width_px_at_1920 = int(candidate_width_px_at_1920)
        self.candidate_height_px_at_1080 = int(candidate_height_px_at_1080)
        self.x_offsets_px_at_1920 = tuple(int(x) for x in x_offsets_px_at_1920)
        self.y_offset_px_at_1080 = int(y_offset_px_at_1080)

    def candidates(
        self,
        image: Image.Image,
        registry: ROIRegistry,
    ) -> list[StageCandidate]:
        width, height = image.size
        region = registry.resolve("stage_search_region", width, height)

        sx = width / 1920.0
        sy = height / 1080.0

        cand_w = max(16, round(self.candidate_width_px_at_1920 * sx))
        cand_h = max(12, round(self.candidate_height_px_at_1080 * sy))
        y_offset = round(self.y_offset_px_at_1080 * sy)

        center_x = (region.left + region.right) // 2
        center_y = (region.top + region.bottom) // 2 + y_offset

        result: list[StageCandidate] = []

        for idx, offset_1920 in enumerate(self.x_offsets_px_at_1920):
            offset = round(offset_1920 * sx)

            left = center_x - cand_w // 2 + offset
            top = center_y - cand_h // 2
            right = left + cand_w
            bottom = top + cand_h

            # Clamp candidate to declared search region.
            if left < region.left:
                right += region.left - left
                left = region.left
            if right > region.right:
                left -= right - region.right
                right = region.right
            if top < region.top:
                bottom += region.top - top
                top = region.top
            if bottom > region.bottom:
                top -= bottom - region.bottom
                bottom = region.bottom

            left = max(region.left, left)
            top = max(region.top, top)
            right = min(region.right, right)
            bottom = min(region.bottom, bottom)

            if right <= left or bottom <= top:
                continue

            box = (left, top, right, bottom)
            result.append(
                StageCandidate(
                    name=f"stage_candidate_{idx}",
                    box=box,
                    image=image.crop(box),
                    x_offset_px=offset,
                )
            )

        return result
