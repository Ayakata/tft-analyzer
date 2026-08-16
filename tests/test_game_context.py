import json

import pytest

from tft_analyzer.game_data import (
    ChampionCostCatalog,
    build_champion_catalog_snapshot,
    infer_set_from_roster,
    load_game_context,
    resolve_game_context,
)


def catalog(entries):
    raw = json.dumps(
        {
            "data": {
                entry["id"]: entry
                for entry in entries
            }
        }
    ).encode("utf-8")
    snapshot = build_champion_catalog_snapshot(
        raw,
        version="16.16.1",
        locale="en_US",
        source_url="test://ddragon",
        fetched_at_utc="2026-08-14T00:00:00+00:00",
    )
    return ChampionCostCatalog(snapshot)


def test_explicit_set_scopes_ambiguous_display_name():
    c = catalog(
        [
            {
                "id": "TFT16_Zoe",
                "name": "Zoe",
                "tier": 3,
            },
            {
                "id": "TFT17_Zoe",
                "name": "Zoe",
                "tier": 2,
            },
        ]
    )

    assert c.resolve_cost("zoe").cost is None
    assert c.resolve_cost(
        "zoe",
        set_id="TFT17",
    ).cost == 2


def test_auto_set_inference_uses_unique_roster_anchors():
    c = catalog(
        [
            {
                "id": "TFT17_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            },
            {
                "id": "TFT17_Aurora",
                "name": "Aurora",
                "tier": 3,
            },
            {
                "id": "TFT17_Zoe",
                "name": "Zoe",
                "tier": 2,
            },
            {
                "id": "TFT16_Zoe",
                "name": "Zoe",
                "tier": 3,
            },
        ]
    )

    set_id, confidence, margin, scores = infer_set_from_roster(
        c,
        ["Rhaast", "Aurora", "Zoe"],
    )

    assert set_id == "TFT17"
    assert confidence is not None
    assert margin is not None
    assert scores[0].set_id == "TFT17"
    assert set(scores[0].unique_anchor_names) == {
        "Aurora",
        "Rhaast",
    }


def test_explicit_game_context_persists_and_wins(tmp_path):
    c = catalog(
        [
            {
                "id": "TFT17_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            }
        ]
    )
    match = tmp_path / "match"
    match.mkdir()

    context = resolve_game_context(
        match_dir=match,
        catalog=c,
        observed_roster_names=["Rhaast"],
        explicit_set="TFT17",
        explicit_patch="16.16",
    )

    assert context.set_id == "TFT17"
    assert context.patch == "16.16"
    assert context.resolution_source == "explicit_cli"

    loaded = load_game_context(match)
    assert loaded is not None
    assert loaded.set_id == "TFT17"


def test_conflicting_explicit_set_requires_force(tmp_path):
    c = catalog(
        [
            {
                "id": "TFT17_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            },
            {
                "id": "TFT16_Rhaast",
                "name": "Rhaast",
                "tier": 2,
            },
        ]
    )
    match = tmp_path / "match"
    match.mkdir()

    resolve_game_context(
        match_dir=match,
        catalog=c,
        observed_roster_names=["Rhaast"],
        explicit_set="TFT17",
        explicit_patch="16.16",
    )

    with pytest.raises(ValueError):
        resolve_game_context(
            match_dir=match,
            catalog=c,
            observed_roster_names=["Rhaast"],
            explicit_set="TFT16",
            explicit_patch="16.16",
        )


def test_patch_must_match_catalog(tmp_path):
    c = catalog(
        [
            {
                "id": "TFT17_Rhaast",
                "name": "Rhaast",
                "tier": 3,
            }
        ]
    )
    match = tmp_path / "match"
    match.mkdir()

    with pytest.raises(ValueError):
        resolve_game_context(
            match_dir=match,
            catalog=c,
            observed_roster_names=["Rhaast"],
            explicit_set="TFT17",
            explicit_patch="16.15",
        )
