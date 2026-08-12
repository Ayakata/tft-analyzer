from pydantic import Field

from tft_analyzer.core.enums import EvidenceKind
from .base import SchemaModel


class EvidenceRef(SchemaModel):
    evidence_id: str
    match_id: str
    timestamp_s: float = Field(ge=0)
    kind: EvidenceKind
    uri: str
    sha256: str | None = None
    source: str = "screen"
