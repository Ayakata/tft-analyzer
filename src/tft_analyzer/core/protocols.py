from collections.abc import Iterable
from typing import Protocol

from tft_analyzer.core.models import (
    Finding,
    GameEvent,
    GameState,
    Observation,
    SemanticAction,
)


class PerceptionModule(Protocol):
    def observe(self, evidence_uri: str) -> Iterable[Observation]:
        ...


class EventDetector(Protocol):
    def detect(
        self,
        previous_state: GameState | None,
        observations: Iterable[Observation],
    ) -> Iterable[GameEvent]:
        ...


class StateReducer(Protocol):
    def reduce(
        self,
        previous_state: GameState | None,
        events: Iterable[GameEvent],
    ) -> GameState:
        ...


class Analyzer(Protocol):
    def analyze(self, states: Iterable[GameState]) -> Iterable[Finding]:
        ...


class ValueModel(Protocol):
    def evaluate(self, state: GameState) -> float:
        ...


class TransitionModel(Protocol):
    def expected_next_states(
        self,
        state: GameState,
        action: SemanticAction,
    ) -> Iterable[tuple[GameState, float]]:
        """Yield (possible_next_state, probability)."""
        ...
