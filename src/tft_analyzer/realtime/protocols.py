from collections.abc import Iterable
from typing import Protocol

from tft_analyzer.core.models import Finding, GameState, SemanticAction


class RealtimeAdvisor(Protocol):
    """Optional, independently gated consumer of canonical state."""

    def advise(
        self,
        state: GameState,
        findings: Iterable[Finding],
    ) -> Iterable[SemanticAction]:
        ...
