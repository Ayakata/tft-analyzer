from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextReviewAnalyzerSettings:
    producer_version: str = "context-review-analyzer-0.18.0"

    # These are conservative review thresholds, not TFT meta prescriptions.
    pressure_hp_threshold: int = 35
    critical_hp_threshold: int = 20
    near_elimination_hp_threshold: int = 10

    economy_commitment_spend_threshold: int = 10
    large_spend_under_pressure_threshold: int = 20
    high_gold_under_pressure_threshold: int = 30

    emit_economy_commitment_under_pressure: bool = True
    emit_low_hp_roll_activity: bool = True
    emit_low_hp_level_up: bool = True
    emit_high_gold_under_pressure: bool = True
    emit_near_elimination_activity: bool = True
    emit_trusted_board_below_capacity: bool = True
