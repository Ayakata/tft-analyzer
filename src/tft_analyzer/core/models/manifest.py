from datetime import datetime

from .base import SchemaModel


class PipelineVersions(SchemaModel):
    capture: str = "0.1.0"
    perception: str = "0.1.0"
    tracking: str = "0.1.0"
    reducer: str = "0.1.0"
    decision_extractor: str = "0.1.0"
    analyzer: str = "0.1.0"
    game_data: str = "unknown"


class MatchManifest(SchemaModel):
    match_id: str
    started_at: datetime
    ended_at: datetime | None = None

    patch: str | None = None
    set_id: str | None = None
    client_resolution: tuple[int, int] | None = None

    versions: PipelineVersions = PipelineVersions()

    final_placement: int | None = None
    notes: str | None = None
