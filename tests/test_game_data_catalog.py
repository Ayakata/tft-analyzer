import json

from tft_analyzer.game_data import (
    ChampionCostCatalog,
    build_champion_catalog_snapshot,
)


def raw_payload(entries):
    return json.dumps(
        {
            "type": "tft-champion",
            "version": "0.0.0",
            "data": {
                entry["id"]: entry
                for entry in entries
            },
        }
    ).encode("utf-8")


def catalog(entries):
    snapshot = build_champion_catalog_snapshot(
        raw_payload(entries),
        version="16.16.1",
        locale="en_US",
        source_url="test://riot-ddragon",
        fetched_at_utc="2026-08-14T00:00:00+00:00",
    )
    return ChampionCostCatalog(snapshot)


def test_unique_champion_resolves_tier_as_cost():
    c = catalog(
        [
            {
                "id": "TFT16_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            }
        ]
    )

    resolution = c.resolve_cost("rhaast")

    assert resolution.status == "resolved_unique"
    assert resolution.cost == 3
    assert resolution.candidate_tiers == (3,)


def test_duplicate_name_with_same_tier_resolves_consensus():
    c = catalog(
        [
            {
                "id": "TFT16_Zoe",
                "name": "Zoe",
                "tier": 1,
            },
            {
                "id": "TFTSpecial_Zoe",
                "name": "Zoe",
                "tier": 1,
            },
        ]
    )

    resolution = c.resolve_cost("ZOE")

    assert resolution.status == "resolved_consensus"
    assert resolution.cost == 1
    assert len(resolution.candidate_ids) == 2


def test_duplicate_name_with_conflicting_tiers_is_ambiguous():
    c = catalog(
        [
            {
                "id": "TFTA_Briar",
                "name": "Briar",
                "tier": 1,
            },
            {
                "id": "TFTB_Briar",
                "name": "Briar",
                "tier": 4,
            },
        ]
    )

    resolution = c.resolve_cost("briar")

    assert resolution.status == "ambiguous"
    assert resolution.cost is None
    assert resolution.candidate_tiers == (1, 4)


def test_missing_name_is_not_guessed():
    c = catalog(
        [
            {
                "id": "TFT16_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            }
        ]
    )

    resolution = c.resolve_cost("unknownchamp")

    assert resolution.status == "missing"
    assert resolution.cost is None
