import json

from tft_analyzer.storage import EvidenceStore


def test_capture_status_is_append_only_jsonl(tmp_path):
    store = EvidenceStore(tmp_path / "match", "m-1")
    store.append_status(
        elapsed_s=1.5,
        status="capture_gap_start",
        details={"reason": "window_minimized"},
    )
    store.append_status(elapsed_s=3.5, status="capture_gap_end")

    lines = store.status_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["status"] == "capture_gap_start"
    assert first["details"]["reason"] == "window_minimized"
    assert second["status"] == "capture_gap_end"
