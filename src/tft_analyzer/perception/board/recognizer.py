from __future__ import annotations

import hashlib
from dataclasses import dataclass
from statistics import mean

from PIL import Image, ImageDraw

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.perception.layout import ROIRegistry

from .features import (
    classify_occupancy,
    occupancy_features,
    occupancy_score,
    region_presence_score,
)
from .geometry import NormalizedPoint, bench_centers, board_centers, centered_box
from .models import BoardBenchRecognitionResult, BoardCellResult, BenchSlotResult


@dataclass(frozen=True, slots=True)
class BoardBenchRecognizerSettings:
    board_producer_version: str = "board-occupancy-0.12.0"
    bench_producer_version: str = "bench-occupancy-0.12.0"
    board_rows: int = 4
    board_cols: int = 7
    bench_slots: int = 9

    min_board_presence_score: float = 0.20
    min_bench_presence_score: float = 0.16

    board_empty_below: float = 0.38
    board_occupied_above: float = 0.58
    bench_empty_below: float = 0.34
    bench_occupied_above: float = 0.54

    # Legacy scalar geometry is retained as a fallback for custom configs.
    board_half_width_px_at_1920: int = 58
    board_up_px_at_1080: int = 72
    board_down_px_at_1080: int = 30

    # Perspective-aware sampling windows calibrated from the real 1920x1080
    # frame. Upper board rows are visually narrower; lower rows are wider and
    # champion sprites occupy progressively more vertical area.
    board_half_width_px_at_1920_by_row: tuple[int, ...] = (50, 56, 62, 68)
    board_up_px_at_1080_by_row: tuple[int, ...] = (68, 72, 78, 84)
    board_down_px_at_1080_by_row: tuple[int, ...] = (26, 28, 30, 32)

    # Logical native-cell footprint used for debug and future slot semantics.
    # This is intentionally independent from the taller rectangular context
    # crop used by occupancy features: champions may extend far above the hex.
    board_hex_half_width_px_at_1920_by_row: tuple[int, ...] = (52, 55, 58, 61)
    board_hex_half_height_px_at_1080_by_row: tuple[int, ...] = (38, 41, 45, 48)

    # Bench geometry is calibrated from real planning-phase frames.
    # Unlike board cells, bench occupancy benefits from separating the logical
    # slot footprint (where the unit stands) from the taller context crop
    # (where the recognizer samples the champion body).
    bench_half_width_px_at_1920: int = 60
    bench_up_px_at_1080: int = 142
    bench_down_px_at_1080: int = 12
    bench_footprint_half_width_px_at_1920: int = 36
    bench_footprint_up_px_at_1080: int = 64
    bench_footprint_down_px_at_1080: int = 16

    # Native TFT board calibration from the cyan placement grid.
    # Rows alternate horizontal offset and widen slightly toward the camera.
    # The values describe the center of c0/c6 for each of the four rows.
    board_row_left: tuple[tuple[float, float], ...] = (
        (0.293, 0.414),
        (0.319, 0.478),
        (0.278, 0.549),
        (0.304, 0.625),
    )
    board_row_right: tuple[tuple[float, float], ...] = (
        (0.651, 0.414),
        (0.688, 0.478),
        (0.663, 0.549),
        (0.701, 0.625),
    )
    bench_left: tuple[float, float] = (0.230, 0.745)
    bench_right: tuple[float, float] = (0.715, 0.745)


class BoardBenchRecognizer:
    def __init__(self, *, registry: ROIRegistry, settings: BoardBenchRecognizerSettings) -> None:
        self.registry = registry
        self.settings = settings

    @staticmethod
    def _observation_id(evidence_id: str, kind: str) -> str:
        digest = hashlib.sha1(f"{evidence_id}|{kind}".encode()).hexdigest()[:12]
        return f"obs-{kind}-{digest}"

    def _board_geometry(self, width: int, height: int):
        return board_centers(
            width=width,
            height=height,
            row_left=tuple(NormalizedPoint(*p) for p in self.settings.board_row_left),
            row_right=tuple(NormalizedPoint(*p) for p in self.settings.board_row_right),
            cols=self.settings.board_cols,
        )

    def _bench_geometry(self, width: int, height: int):
        return bench_centers(
            width=width,
            height=height,
            left=NormalizedPoint(*self.settings.bench_left),
            right=NormalizedPoint(*self.settings.bench_right),
            slots=self.settings.bench_slots,
        )

    @staticmethod
    def _row_value(
        values: tuple[int, ...],
        row: int,
        fallback: int,
    ) -> int:
        if row < len(values):
            return int(values[row])
        return int(fallback)

    def board_box_geometry_at_reference(
        self,
        row: int,
    ) -> tuple[int, int, int]:
        return (
            self._row_value(
                self.settings.board_half_width_px_at_1920_by_row,
                row,
                self.settings.board_half_width_px_at_1920,
            ),
            self._row_value(
                self.settings.board_up_px_at_1080_by_row,
                row,
                self.settings.board_up_px_at_1080,
            ),
            self._row_value(
                self.settings.board_down_px_at_1080_by_row,
                row,
                self.settings.board_down_px_at_1080,
            ),
        )

    def board_footprint_geometry_at_reference(
        self,
        row: int,
    ) -> tuple[int, int, int]:
        # Compatibility rectangle: bounding box around the native hex footprint.
        half_width, half_height = self.board_hex_geometry_at_reference(row)
        return (half_width, half_height, half_height)

    def board_hex_geometry_at_reference(
        self,
        row: int,
    ) -> tuple[int, int]:
        return (
            self._row_value(
                self.settings.board_hex_half_width_px_at_1920_by_row,
                row,
                55,
            ),
            self._row_value(
                self.settings.board_hex_half_height_px_at_1080_by_row,
                row,
                40,
            ),
        )

    def board_hex_polygon(
        self,
        row: int,
        center: tuple[int, int],
        width: int,
        height: int,
    ) -> tuple[tuple[int, int], ...]:
        half_width_ref, half_height_ref = self.board_hex_geometry_at_reference(row)
        sx = width / 1920.0
        sy = height / 1080.0
        hw = max(8, round(half_width_ref * sx))
        hh = max(6, round(half_height_ref * sy))
        shoulder = max(4, round(hw * 0.50))
        cx, cy = center
        return (
            (cx - shoulder, cy - hh),
            (cx + shoulder, cy - hh),
            (cx + hw, cy),
            (cx + shoulder, cy + hh),
            (cx - shoulder, cy + hh),
            (cx - hw, cy),
        )

    def bench_context_geometry_at_reference(self) -> tuple[int, int, int]:
        return (
            int(self.settings.bench_half_width_px_at_1920),
            int(self.settings.bench_up_px_at_1080),
            int(self.settings.bench_down_px_at_1080),
        )

    def bench_footprint_geometry_at_reference(self) -> tuple[int, int, int]:
        return (
            int(self.settings.bench_footprint_half_width_px_at_1920),
            int(self.settings.bench_footprint_up_px_at_1080),
            int(self.settings.bench_footprint_down_px_at_1080),
        )

    @staticmethod
    def _scaled_box(
        center: tuple[int, int],
        *,
        width: int,
        height: int,
        half_width_ref: int,
        up_ref: int,
        down_ref: int,
    ) -> tuple[int, int, int, int]:
        sx = width / 1920.0
        sy = height / 1080.0
        return centered_box(
            center,
            width=width,
            height=height,
            half_width=max(8, round(half_width_ref * sx)),
            up=max(8, round(up_ref * sy)),
            down=max(6, round(down_ref * sy)),
        )

    def board_context_box(
        self, row: int, center: tuple[int, int], width: int, height: int
    ) -> tuple[int, int, int, int]:
        half_width_ref, up_ref, down_ref = self.board_box_geometry_at_reference(row)
        return self._scaled_box(
            center,
            width=width,
            height=height,
            half_width_ref=half_width_ref,
            up_ref=up_ref,
            down_ref=down_ref,
        )

    def board_footprint_box(
        self, row: int, center: tuple[int, int], width: int, height: int
    ) -> tuple[int, int, int, int]:
        half_width_ref, up_ref, down_ref = self.board_footprint_geometry_at_reference(row)
        return self._scaled_box(
            center,
            width=width,
            height=height,
            half_width_ref=half_width_ref,
            up_ref=up_ref,
            down_ref=down_ref,
        )

    def bench_context_box(
        self, center: tuple[int, int], width: int, height: int
    ) -> tuple[int, int, int, int]:
        half_width_ref, up_ref, down_ref = self.bench_context_geometry_at_reference()
        return self._scaled_box(
            center,
            width=width,
            height=height,
            half_width_ref=half_width_ref,
            up_ref=up_ref,
            down_ref=down_ref,
        )

    def bench_footprint_box(
        self, center: tuple[int, int], width: int, height: int
    ) -> tuple[int, int, int, int]:
        half_width_ref, up_ref, down_ref = self.bench_footprint_geometry_at_reference()
        return self._scaled_box(
            center,
            width=width,
            height=height,
            half_width_ref=half_width_ref,
            up_ref=up_ref,
            down_ref=down_ref,
        )

    def board_footprint_mask(self, row:int, center:tuple[int,int], footprint_box:tuple[int,int,int,int], width:int, height:int) -> Image.Image:
        left,top,right,bottom=footprint_box
        poly=self.board_hex_polygon(row,center,width,height)
        local=[(x-left,y-top) for x,y in poly]
        mask=Image.new('L',(right-left,bottom-top),0)
        ImageDraw.Draw(mask).polygon(local,fill=255)
        return mask

    def recognize(self, image: Image.Image, *, match_id: str, timestamp_s: float, evidence_id: str) -> BoardBenchRecognitionResult:
        image = image.convert("RGB")
        width, height = image.size
        self.registry.assert_compatible(width, height)
        result = BoardBenchRecognitionResult()

        board_roi = self.registry.resolve("board_region", width, height)
        bench_roi = self.registry.resolve("bench_region", width, height)
        result.board_presence_score = region_presence_score(image.crop(board_roi.box))
        result.bench_presence_score = region_presence_score(image.crop(bench_roi.box))
        result.board_present = result.board_presence_score >= self.settings.min_board_presence_score
        result.bench_present = result.bench_presence_score >= self.settings.min_bench_presence_score

        if result.board_present:
            for row,col,cx,cy in self._board_geometry(width,height):
                center=(cx,cy)
                context_box=self.board_context_box(row,center,width,height)
                footprint_box=self.board_footprint_box(row,center,width,height)
                crop=image.crop(footprint_box)
                mask=self.board_footprint_mask(row,center,footprint_box,width,height)
                features=occupancy_features(crop,mask=mask)
                score=occupancy_score(features)
                status,confidence=classify_occupancy(score,empty_below=self.settings.board_empty_below,occupied_above=self.settings.board_occupied_above)
                result.board_cells.append(BoardCellResult(row,col,center,context_box,footprint_box,score,confidence,status,features))

        if result.bench_present:
            for slot_index,cx,cy in self._bench_geometry(width,height):
                center=(cx,cy)
                context_box=self.bench_context_box(center,width,height)
                footprint_box=self.bench_footprint_box(center,width,height)
                features=occupancy_features(image.crop(footprint_box))
                score=occupancy_score(features)
                status,confidence=classify_occupancy(score,empty_below=self.settings.bench_empty_below,occupied_above=self.settings.bench_occupied_above)
                result.bench_slots.append(BenchSlotResult(slot_index,center,context_box,footprint_box,score,confidence,status,features))

        if result.board_present and len(result.board_cells) == self.settings.board_rows * self.settings.board_cols:
            conf = mean(c.confidence for c in result.board_cells)
            result.observations.append(Observation(
                observation_id=self._observation_id(evidence_id, "board"),
                match_id=match_id, timestamp_s=max(0.0, float(timestamp_s)), kind=ObservationKind.BOARD,
                value={
                    "rows": self.settings.board_rows,
                    "cols": self.settings.board_cols,
                    "cells": [
                        {"row":c.row,"col":c.col,"status":c.status,"occupied":c.occupied,"score":c.score,"confidence":c.confidence,"center":c.center,"box":c.box,"footprint_box":c.footprint_box,"sampling_mode":"footprint"}
                        for c in result.board_cells
                    ],
                    "occupied_count": result.board_occupied_count,
                    "uncertain_count": result.board_uncertain_count,
                    "presence_score": result.board_presence_score,
                },
                confidence=conf, evidence_ids=(evidence_id,), producer_version=self.settings.board_producer_version,
            ))

        if result.bench_present and len(result.bench_slots) == self.settings.bench_slots:
            conf = mean(c.confidence for c in result.bench_slots)
            result.observations.append(Observation(
                observation_id=self._observation_id(evidence_id, "bench"),
                match_id=match_id, timestamp_s=max(0.0, float(timestamp_s)), kind=ObservationKind.BENCH,
                value={
                    "slot_count": self.settings.bench_slots,
                    "slots": [
                        {"index":c.slot_index,"status":c.status,"occupied":c.occupied,"score":c.score,"confidence":c.confidence,"center":c.center,"box":c.box,"footprint_box":c.footprint_box,"sampling_mode":"footprint"}
                        for c in result.bench_slots
                    ],
                    "occupied_count": result.bench_occupied_count,
                    "uncertain_count": result.bench_uncertain_count,
                    "presence_score": result.bench_presence_score,
                },
                confidence=conf, evidence_ids=(evidence_id,), producer_version=self.settings.bench_producer_version,
            ))

        return result
