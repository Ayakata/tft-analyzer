import json

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.storage.observation_reader import (
    find_latest_observation_file,
    iter_observations,
)


def test_latest_observation_file_uses_semantic_version(tmp_path):
    obs_dir = tmp_path / "observations"
    obs_dir.mkdir()

    (obs_dir / "hud-rapidocr-0.4.2.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    latest = obs_dir / "hud-rapidocr-0.4.10.jsonl"
    latest.write_text("", encoding="utf-8")

    found = find_latest_observation_file(tmp_path)
    assert found == latest


def test_iter_observations(tmp_path):
    path = tmp_path / "obs.jsonl"

    observation = Observation(
        observation_id="o1",
        match_id="m1",
        timestamp_s=1.0,
        kind=ObservationKind.GOLD,
        value={"gold": 10},
        confidence=0.9,
        evidence_ids=("e1",),
        producer_version="test",
    )

    path.write_text(
        json.dumps(
            observation.model_dump(mode="json")
        )
        + "\n",
        encoding="utf-8",
    )

    restored = list(iter_observations(path))
    assert restored == [observation]
