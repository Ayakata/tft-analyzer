import json
from pathlib import Path

from tft_analyzer.features.slot_identity_audit import (
    SlotIdentityHumanAuditSettings,
    audit_identity_labels,
)
from tft_analyzer.features.slot_identity_labeling import (
    LabeledSlotVisualGroup,
)


def _labeled(
    group_id,
    *,
    target_type,
    tier,
    location,
    slot_id,
    champion=None,
    tracked_source="current",
):
    return LabeledSlotVisualGroup(
        visual_group_id=group_id,
        match_id="match-1",
        queue_type=(
            "occupancy_qa"
            if tier == "raw_candidate"
            else "identity_label"
        ),
        location=location,
        slot_id=slot_id,
        stage_start="2-1",
        stage_end="2-1",
        start_timestamp_s=10.0,
        end_timestamp_s=10.0,
        member_count=1,
        representative_crop_uri=f"representatives/{group_id}.png",
        representative_tier=tier,
        representative_tracked_source=tracked_source,
        recommended_for_identity_training_after_label=(
            tier == "trusted"
        ),
        target_type=target_type,
        champion_label=champion,
        champion_normalized_name=champion,
        champion_id=(
            f"TFT17_{champion}"
            if champion
            else None
        ),
        champion_catalog_validated=bool(
            champion
        ),
        label_status="human_labeled",
        eligible_visual_champion_training_group=bool(
            champion
            and tier == "trusted"
        ),
        eligible_occupancy_negative_group=False,
        split_key="match-1",
        source_curation_producer_version=(
            "slot-identity-curator-0.21.2"
        ),
        source_visual_groups_path="visual_groups.jsonl",
        producer_version="slot-identity-label-importer-0.21.3",
    )


def _write_import(match):
    imported = (
        match
        / "labels"
        / "slot-identity-label-importer-0.21.3"
    )
    imported.mkdir(
        parents=True,
        exist_ok=True,
    )

    values = [
        _labeled(
            "p1",
            target_type="champion",
            tier="trusted",
            location="bench",
            slot_id="b0",
            champion="rhaast",
        ),
        _labeled(
            "s1",
            target_type="champion",
            tier="supported",
            location="board",
            slot_id="r0c0",
            champion="rhaast",
            tracked_source="carry",
        ),
        _labeled(
            "r1",
            target_type="champion",
            tier="raw_candidate",
            location="board",
            slot_id="r1c1",
            champion="reksai",
            tracked_source="carry",
        ),
        _labeled(
            "n1",
            target_type="no_unit",
            tier="trusted",
            location="board",
            slot_id="r2c0",
        ),
        _labeled(
            "n2",
            target_type="no_unit",
            tier="trusted",
            location="board",
            slot_id="r2c0",
        ),
        _labeled(
            "u1",
            target_type="uncertain",
            tier="supported",
            location="board",
            slot_id="r0c4",
            tracked_source="carry",
        ),
    ]

    (
        imported
        / "labeled_visual_groups.jsonl"
    ).write_text(
        "".join(
            value.model_dump_json()
            + "\n"
            for value in values
        ),
        encoding="utf-8",
    )
    (
        imported
        / "summary.json"
    ).write_text(
        json.dumps(
            {
                "producer_version": (
                    "slot-identity-label-importer-0.21.3"
                ),
                "labeled_group_count": 6,
                "unlabeled_group_count": 10,
            }
        ),
        encoding="utf-8",
    )
    return imported


def test_human_label_audit_separates_identity_policy_and_hotspots(tmp_path):
    match = tmp_path / "match"
    imported = _write_import(
        match
    )

    summary = audit_identity_labels(
        match,
        SlotIdentityHumanAuditSettings(),
        label_import_dir=imported,
    )

    assert summary[
        "primary_group_count"
    ] == 1
    assert summary[
        "secondary_group_count"
    ] == 1
    assert summary[
        "recovered_candidate_group_count"
    ] == 1
    assert summary[
        "human_confirmed_champion_manifest_group_count"
    ] == 3
    assert summary[
        "occupancy_hard_negative_group_count"
    ] == 2

    assert summary[
        "target_type_counts"
    ] == {
        "champion": 3,
        "no_unit": 2,
        "uncertain": 1,
    }

    target_tier = summary[
        "cross_tabs"
    ][
        "target_by_representative_tier"
    ]
    assert target_tier[
        "champion"
    ] == {
        "raw_candidate": 1,
        "supported": 1,
        "trusted": 1,
    }
    assert target_tier[
        "no_unit"
    ] == {
        "trusted": 2,
    }

    rhaast = summary[
        "per_champion"
    ][
        "rhaast"
    ]
    assert rhaast[
        "human_confirmed_group_count"
    ] == 2
    assert rhaast[
        "primary_group_count"
    ] == 1
    assert rhaast[
        "secondary_group_count"
    ] == 1

    hotspot = summary[
        "occupancy_false_positive_hotspots"
    ][0]
    assert hotspot[
        "location"
    ] == "board"
    assert hotspot[
        "slot_id"
    ] == "r2c0"
    assert hotspot[
        "no_unit_count"
    ] == 2
    assert hotspot[
        "no_unit_rate"
    ] == 1.0

    for key in (
        "primary_manifest_path",
        "secondary_manifest_path",
        "human_confirmed_manifest_path",
        "occupancy_hard_negative_manifest_path",
    ):
        assert Path(
            summary[
                key
            ]
        ).is_file()
