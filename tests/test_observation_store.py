import json

from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.core.models import Observation
from tft_analyzer.storage import write_observations_atomic


def test_write_observations_atomic(tmp_path):
    path = tmp_path / "observations.jsonl"
    obs = Observation(
        observation_id="o1",
        match_id="m1",
        timestamp_s=1.0,
        kind=ObservationKind.GOLD,
        value={"gold": 10},
        confidence=0.9,
        evidence_ids=("e1",),
        producer_version="test",
    )

    count = write_observations_atomic(path, [obs])
    assert count == 1

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["value"]["gold"] == 10
