from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tft_analyzer.core.models import EvidenceRef


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    sequence: int
    reason: str
    scene_change_score: float | None
    wall_time_iso: str | None
    width: int | None
    height: int | None
    evidence: EvidenceRef


def iter_evidence_records(match_dir: Path | str):
    match_dir = Path(match_dir)
    index_path = match_dir / "evidence" / "evidence_index.jsonl"

    if not index_path.exists():
        raise FileNotFoundError(f"Evidence index not found: {index_path}")

    with index_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            payload = json.loads(line)
            yield EvidenceRecord(
                sequence=int(payload["sequence"]),
                reason=str(payload.get("reason", "")),
                scene_change_score=payload.get("scene_change_score"),
                wall_time_iso=payload.get("wall_time_iso"),
                width=payload.get("width"),
                height=payload.get("height"),
                evidence=EvidenceRef.model_validate(payload["evidence"]),
            )
