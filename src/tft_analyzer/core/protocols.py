from collections.abc import Iterable
from typing import Protocol

from tft_analyzer.core.models import (
    EventValidation,
    Finding,
    GameEvent,
    GameState,
    Observation,
    SemanticAction,
    TrackedHUDState,
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


class TrackedStateEventDetector(Protocol):
    def ingest_state(
        self,
        state: TrackedHUDState,
    ) -> Iterable[GameEvent]:
        ...



class EventValidator(Protocol):
    def validate(
        self,
        event: GameEvent,
    ) -> EventValidation:
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
