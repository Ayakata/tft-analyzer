from datetime import datetime, timezone
from io import BytesIO
from PIL import Image

from tft_analyzer.capture.types import CapturedFrame
from tft_analyzer.replay import build_replay_html
from tft_analyzer.storage import EvidenceStore


def test_replay_html_created(tmp_path):
    match_dir = tmp_path / "m-1"
    image = Image.new("RGB", (32, 16), (1, 2, 3))
    buf = BytesIO()
    image.save(buf, format="PNG")
    frame = CapturedFrame(
        timestamp_s=0,
        wall_time_iso=datetime.now(timezone.utc).isoformat(),
        width=32,
        height=16,
        png_bytes=buf.getvalue(),
    )
    EvidenceStore(match_dir, "m-1").append_frame(
        frame, elapsed_s=0, reason="session_start", scene_change_score=1
    )
    replay = build_replay_html(match_dir)
    text = replay.read_text(encoding="utf-8")
    assert "session_start" in text
    assert "evidence/frames/" in text
