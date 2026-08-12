import json

from tft_analyzer.core.enums import EvidenceKind
from tft_analyzer.core.models import EvidenceRef
from tft_analyzer.storage import iter_evidence_records


def test_iter_evidence_records(tmp_path):
    match_dir = tmp_path / "m1"
    evidence_dir = match_dir / "evidence"
    evidence_dir.mkdir(parents=True)

    ref = EvidenceRef(
        evidence_id="e1",
        match_id="m1",
        timestamp_s=1.25,
        kind=EvidenceKind.FRAME,
        uri="evidence/frames/a.png",
        source="screen",
    )

    payload = {
        "sequence": 7,
        "reason": "scene_change",
        "scene_change_score": 0.1,
        "wall_time_iso": "2026-01-01T00:00:00+00:00",
        "width": 1920,
        "height": 1080,
        "evidence": ref.model_dump(mode="json"),
    }

    (evidence_dir / "evidence_index.jsonl").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )

    records = list(iter_evidence_records(match_dir))
    assert len(records) == 1
    assert records[0].sequence == 7
    assert records[0].evidence.evidence_id == "e1"
