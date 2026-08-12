from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tft_analyzer.capture.types import CapturedFrame
from tft_analyzer.core.enums import EvidenceKind
from tft_analyzer.core.models import EvidenceRef


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    ref: EvidenceRef
    sequence: int
    reason: str
    scene_change_score: float | None


class EvidenceStore:
    """Append-only raw evidence and capture-status storage."""

    def __init__(self, match_dir: Path, match_id: str) -> None:
        self.match_dir = Path(match_dir)
        self.match_id = match_id
        self.frames_dir = self.match_dir / "evidence" / "frames"
        self.index_path = self.match_dir / "evidence" / "evidence_index.jsonl"
        self.status_path = self.match_dir / "evidence" / "capture_status.jsonl"

        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence = self._discover_next_sequence()

    @property
    def count(self) -> int:
        return self._sequence

    def _discover_next_sequence(self) -> int:
        if not self.index_path.exists():
            return 0
        with self.index_path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def append_status(
        self,
        *,
        elapsed_s: float,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "match_id": self.match_id,
            "timestamp_s": float(elapsed_s),
            "status": status,
            "details": details or {},
        }
        with self.status_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def append_frame(
        self,
        frame: CapturedFrame,
        *,
        elapsed_s: float,
        reason: str,
        scene_change_score: float | None = None,
    ) -> StoredEvidence:
        digest = hashlib.sha256(frame.png_bytes).hexdigest()
        evidence_id = f"frame-{self._sequence:08d}-{digest[:12]}"
        filename = f"{self._sequence:08d}_{elapsed_s:012.3f}_{digest[:12]}.png"
        frame_path = self.frames_dir / filename

        with frame_path.open("xb") as f:
            f.write(frame.png_bytes)

        ref = EvidenceRef(
            evidence_id=evidence_id,
            match_id=self.match_id,
            timestamp_s=elapsed_s,
            kind=EvidenceKind.FRAME,
            uri=frame_path.relative_to(self.match_dir).as_posix(),
            sha256=digest,
            source="screen",
        )

        record = {
            "sequence": self._sequence,
            "reason": reason,
            "scene_change_score": scene_change_score,
            "wall_time_iso": frame.wall_time_iso,
            "width": frame.width,
            "height": frame.height,
            "evidence": ref.model_dump(mode="json"),
        }
        with self.index_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        stored = StoredEvidence(
            ref=ref,
            sequence=self._sequence,
            reason=reason,
            scene_change_score=scene_change_score,
        )
        self._sequence += 1
        return stored
