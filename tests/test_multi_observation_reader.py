from tft_analyzer.storage.observation_reader import (
    find_latest_observation_files,
)


def test_find_latest_for_each_observation_stream(tmp_path):
    obs = tmp_path / "observations"
    obs.mkdir()

    (obs / "hud-rapidocr-0.4.3.jsonl").write_text("", encoding="utf-8")
    (obs / "hud-rapidocr-0.4.10.jsonl").write_text("", encoding="utf-8")
    (obs / "players-rapidocr-0.8.1.jsonl").write_text("", encoding="utf-8")

    paths = find_latest_observation_files(
        tmp_path,
        patterns=(
            "hud-rapidocr-*.jsonl",
            "players-rapidocr-*.jsonl",
        ),
    )

    assert [p.name for p in paths] == [
        "hud-rapidocr-0.4.10.jsonl",
        "players-rapidocr-0.8.1.jsonl",
    ]
