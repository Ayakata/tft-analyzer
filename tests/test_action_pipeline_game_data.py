import json
from pathlib import Path

from tft_analyzer.game_data import (
    sync_riot_ddragon_catalog,
)


def test_synced_catalog_can_be_loaded_from_active_pointer(tmp_path):
    source = tmp_path / "tft-champion.json"
    source.write_text(
        json.dumps(
            {
                "data": {
                    "TFT16_Rhaast": {
                        "id": "TFT16_Rhaast",
                        "name": "Rhaast",
                        "tier": 3,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    root = tmp_path / "game_data"
    summary = sync_riot_ddragon_catalog(
        root,
        version="16.16.1",
        source_file=source,
    )

    assert Path(summary["catalog_path"]).exists()
    assert Path(summary["active_pointer_path"]).exists()
