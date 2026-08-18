import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from PIL import Image
import pytest
import yaml

from tft_analyzer.features.board_geometry_editor import (
    BoardGeometryDraftStore,
    create_board_geometry_editor_server,
)


def _workspace(tmp_path):
    match = tmp_path / "match"
    frames = match / "evidence" / "frames"
    frames.mkdir(parents=True)
    for name, color in (
        ("0001.png", (10, 20, 30)),
        ("0002.png", (40, 50, 60)),
    ):
        Image.new("RGB", (320, 180), color).save(frames / name)

    config = tmp_path / "default.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "perception": {
                    "board_bench": {
                        "board_rows": 4,
                        "board_cols": 7,
                        "bench_slots": 9,
                        "board_row_left": [
                            [0.29, 0.41],
                            [0.31, 0.48],
                            [0.28, 0.55],
                            [0.30, 0.63],
                        ],
                        "board_row_right": [
                            [0.65, 0.41],
                            [0.69, 0.48],
                            [0.66, 0.55],
                            [0.70, 0.63],
                        ],
                        "board_half_width_px_at_1920_by_row": [50, 56, 62, 68],
                        "board_up_px_at_1080_by_row": [68, 72, 78, 84],
                        "board_down_px_at_1080_by_row": [26, 28, 30, 32],
                        "board_hex_half_width_px_at_1920_by_row": [52, 55, 58, 61],
                        "board_hex_half_height_px_at_1080_by_row": [38, 41, 45, 48],
                        "bench_left": [0.23, 0.745],
                        "bench_right": [0.715, 0.745],
                        "bench_half_width_px_at_1920": 60,
                        "bench_up_px_at_1080": 142,
                        "bench_down_px_at_1080": 12,
                        "bench_footprint_half_width_px_at_1920": 36,
                        "bench_footprint_up_px_at_1080": 64,
                        "bench_footprint_down_px_at_1080": 16,
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return match, config


def test_store_loads_match_frames_and_saves_validated_draft(tmp_path):
    match, config = _workspace(tmp_path)
    store = BoardGeometryDraftStore(
        match,
        config_path=config,
        initial_frame=str(match / "evidence" / "frames" / "0002.png"),
    )

    assert store.frame_names == ["0001.png", "0002.png"]
    assert store.initial_frame == "0002.png"
    assert store.state()["draft_loaded"] is False

    geometry = json.loads(json.dumps(store.geometry))
    geometry["board_up_px_at_1080_by_row"][2] = 111
    result = store.save(geometry, frame_name="0002.png")

    assert result["saved"] is True
    payload = json.loads(store.draft_path.read_text(encoding="utf-8"))
    assert payload["preview_frame"] == "0002.png"
    assert payload["geometry"]["board_up_px_at_1080_by_row"][2] == 111

    reloaded = BoardGeometryDraftStore(match, config_path=config)
    assert reloaded.state()["draft_loaded"] is True
    assert reloaded.geometry["board_up_px_at_1080_by_row"][2] == 111


def test_store_rejects_unknown_frames_and_invalid_geometry(tmp_path):
    match, config = _workspace(tmp_path)
    store = BoardGeometryDraftStore(match, config_path=config)

    with pytest.raises(FileNotFoundError, match="Unknown match frame"):
        store.frame_path("../secret.png")

    geometry = json.loads(json.dumps(store.geometry))
    geometry["board_row_left"][0] = [1.2, 0.4]
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        store.save(geometry)


def test_http_editor_serves_state_frame_and_saves_draft(tmp_path):
    match, config = _workspace(tmp_path)
    store = BoardGeometryDraftStore(match, config_path=config)
    server = create_board_geometry_editor_server(store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(base + "/api/state") as response:
            state = json.loads(response.read().decode("utf-8"))
        assert state["frames"] == ["0001.png", "0002.png"]

        with opener.open(base + "/frame?name=0001.png") as response:
            assert response.headers.get_content_type() == "image/png"
            assert response.read().startswith(b"\x89PNG")

        payload = json.dumps(
            {
                "geometry": state["geometry"],
                "frame_name": "0001.png",
            }
        ).encode("utf-8")
        request = Request(
            base + "/api/draft",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request) as response:
            saved = json.loads(response.read().decode("utf-8"))
        assert saved["saved"] is True

        with pytest.raises(HTTPError) as exc_info:
            opener.open(base + "/frame?name=..%2Fsecret.png")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
