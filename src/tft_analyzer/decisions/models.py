from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionEpisodeSettings:
    producer_version: str = "decision-episode-builder-0.15.0"

    # Merge active action windows only inside the same TFT stage and only when
    # the unobserved gap is short enough to plausibly represent one planning
    # burst. These do NOT imply exact action continuity.
    max_idle_gap_seconds: float = 15.0
    max_episode_duration_seconds: float = 45.0

    split_on_stage_change: bool = True
    include_unknown_economy_only: bool = True
