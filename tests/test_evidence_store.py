from datetime import datetime, timezone
from io import BytesIO
from PIL import Image

from tft_analyzer.capture.types import CapturedFrame
from tft_analyzer.storage import EvidenceStore


def make_frame():
    image = Image.new("RGB", (64, 32), (10, 20, 30))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return CapturedFrame(
        timestamp_s=123.0,
        wall_time_iso=datetime.now(timezone.utc).isoformat(),
        width=64,
        height=32,
        png_bytes=buf.getvalue(),
    )


def test_evidence_store_is_append_only(tmp_path):
    match_dir = tmp_path / "match"
    store = EvidenceStore(match_dir, "m-1")
    a = store.append_frame(
        make_frame(), elapsed_s=0, reason="session_start", scene_change_score=1
    )
    b = store.append_frame(
        make_frame(), elapsed_s=10, reason="periodic_keyframe", scene_change_score=0
    )
    assert (a.sequence, b.sequence) == (0, 1)
    assert len(list((match_dir / "evidence" / "frames").glob("*.png"))) == 2
    assert len(
        (match_dir / "evidence" / "evidence_index.jsonl")
        .read_text(encoding="utf-8").strip().splitlines()
    ) == 2
