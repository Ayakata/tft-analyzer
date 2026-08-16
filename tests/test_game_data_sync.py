import json
from pathlib import Path

from tft_analyzer.game_data import (
    ChampionCatalogSnapshot,
    find_active_catalog_path,
    sync_riot_ddragon_catalog,
)


def test_sync_from_local_ddragon_file_is_versioned_and_activated(tmp_path):
    source = tmp_path / "tft-champion.json"
    source.write_text(
        json.dumps(
            {
                "data": {
                    "TFT16_Rhaast": {
                        "id": "TFT16_Rhaast",
                        "name": "Rhaast",
                        "tier": 3,
                        "image": {
                            "full": "rhaast.png",
                        },
                    },
                    "TFT16_Zoe": {
                        "id": "TFT16_Zoe",
                        "name": "Zoe",
                        "tier": 1,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    root = tmp_path / "game_data"
    result = sync_riot_ddragon_catalog(
        root,
        version="16.16.1",
        locale="en_US",
        source_file=source,
    )

    catalog_path = Path(result["catalog_path"])
    assert catalog_path.exists()
    assert result["champion_count"] == 2
    assert result["tiers"] == [1, 3]

    active = find_active_catalog_path(root)
    assert active == catalog_path

    snapshot = ChampionCatalogSnapshot.model_validate_json(
        catalog_path.read_text(encoding="utf-8")
    )
    assert snapshot.provider == "riot_ddragon"
    assert snapshot.version == "16.16.1"
    assert snapshot.source_field_for_cost == "tier"
    assert len(snapshot.champions) == 2
