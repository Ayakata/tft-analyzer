from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from tft_analyzer.core.models import Observation


def write_observations_atomic(
    path: Path | str,
    observations: Iterable[Observation],
) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")

    count = 0
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for observation in observations:
            f.write(
                json.dumps(
                    observation.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1

    tmp.replace(path)
    return count
