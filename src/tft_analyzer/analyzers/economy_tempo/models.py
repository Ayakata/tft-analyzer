from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EconomyTempoAnalyzerSettings:
    producer_version: str = "economy-tempo-analyzer-0.16.1"

    # Descriptive thresholds only. These do not encode TFT meta or prescribe
    # optimal play.
    large_spend_threshold: int = 20
    low_gold_after_threshold: int = 10
    roll_burst_max_count_threshold: int = 3

    # Sparse-capture reconstruction uncertainty. This is intentionally NOT a
    # data-quality failure: several unobserved actions may occur between saved
    # screenshots while the observed gold delta remains perfectly valid.
    emit_unresolved_economy_spend: bool = True
    emit_uncertainty_only: bool = False

    emit_large_spend: bool = True
    emit_low_gold_review_candidate: bool = True
    emit_roll_activity: bool = True
    emit_xp_investment: bool = True
    emit_positioning_only: bool = True
