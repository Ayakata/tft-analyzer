from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from tft_analyzer.core.models import Observation

OccupancyStatus=Literal['occupied','empty','uncertain']

@dataclass(frozen=True, slots=True)
class OccupancyFeatures:
    contrast: float
    edge_density: float
    saturation: float
    bright_fraction: float
    center_edge_delta: float
    center_saturation_delta: float

@dataclass(frozen=True, slots=True)
class BoardCellResult:
    row:int; col:int; center:tuple[int,int]
    box:tuple[int,int,int,int]  # legacy/context crop
    footprint_box:tuple[int,int,int,int]
    score:float; confidence:float; status:OccupancyStatus; features:OccupancyFeatures
    @property
    def context_box(self): return self.box
    @property
    def occupied(self):
        return True if self.status=='occupied' else False if self.status=='empty' else None

@dataclass(frozen=True, slots=True)
class BenchSlotResult:
    slot_index:int; center:tuple[int,int]
    box:tuple[int,int,int,int]  # legacy/context crop
    footprint_box:tuple[int,int,int,int]
    score:float; confidence:float; status:OccupancyStatus; features:OccupancyFeatures
    @property
    def context_box(self): return self.box
    @property
    def occupied(self):
        return True if self.status=='occupied' else False if self.status=='empty' else None

@dataclass(slots=True)
class BoardBenchRecognitionResult:
    observations:list[Observation]=field(default_factory=list)
    board_present:bool=False; board_presence_score:float=0.0
    bench_present:bool=False; bench_presence_score:float=0.0
    board_cells:list[BoardCellResult]=field(default_factory=list)
    bench_slots:list[BenchSlotResult]=field(default_factory=list)
    @property
    def board_occupied_count(self): return sum(c.status=='occupied' for c in self.board_cells)
    @property
    def board_uncertain_count(self): return sum(c.status=='uncertain' for c in self.board_cells)
    @property
    def bench_occupied_count(self): return sum(c.status=='occupied' for c in self.bench_slots)
    @property
    def bench_uncertain_count(self): return sum(c.status=='uncertain' for c in self.bench_slots)
