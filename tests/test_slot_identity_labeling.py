import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from tft_analyzer.features.slot_identity_curation import (
    CuratedSlotVisualGroup,
)
from tft_analyzer.features.slot_identity_labeling import (
    SlotIdentityLabelingSettings,
    import_identity_labels,
    prepare_identity_label_package,
)


def _group(
    group_id,
    *,
    queue_type,
    tier,
    location,
    crop_uri,
    train_after_label,
    t=10.0,
):
    return CuratedSlotVisualGroup(
        visual_group_id=group_id,
        match_id="match-1",
        queue_type=queue_type,
        location=location,
        slot_id=(
            "b0"
            if location == "bench"
            else "r0c0"
        ),
        start_timestamp_s=t,
        end_timestamp_s=t,
        duration_s=0.0,
        stage_start="2-1",
        stage_end="2-1",
        stages=("2-1",),
        member_count=2,
        member_sample_ids=(
            f"{group_id}-1",
            f"{group_id}-2",
        ),
        member_tier_counts={
            tier: 2,
        },
        representative_sample_id=f"{group_id}-1",
        representative_timestamp_s=t,
        representative_crop_uri=crop_uri,
        representative_source_crop_uri=(
            f"source/{group_id}.png"
        ),
        representative_tier=tier,
        representative_raw_occupancy_confidence=0.9,
        representative_tracked_source=(
            "current"
            if tier == "trusted"
            else "carry"
        ),
        representative_dhash_hex="0" * 16,
        recommended_for_identity_labeling=(
            queue_type == "identity_label"
        ),
        recommended_for_identity_training_after_label=(
            train_after_label
        ),
        recommended_for_occupancy_review=(
            queue_type == "occupancy_qa"
        ),
        split_key="match-1",
        source_dataset_producer_version=(
            "slot-identity-dataset-exporter-0.21.1"
        ),
        source_manifest_path="manifest.jsonl",
        producer_version="slot-identity-curator-0.21.2",
    )


def _write_curation(match):
    curation = (
        match
        / "datasets"
        / "slot-identity-curator-0.21.2"
    )
    curation.mkdir(
        parents=True,
        exist_ok=True,
    )

    groups = [
        _group(
            "g1",
            queue_type="identity_label",
            tier="trusted",
            location="bench",
            crop_uri=(
                "representatives/identity_label/g1.png"
            ),
            train_after_label=True,
            t=10.0,
        ),
        _group(
            "g2",
            queue_type="identity_label",
            tier="supported",
            location="board",
            crop_uri=(
                "representatives/identity_label/g2.png"
            ),
            train_after_label=False,
            t=20.0,
        ),
        _group(
            "g3",
            queue_type="occupancy_qa",
            tier="raw_candidate",
            location="board",
            crop_uri=(
                "representatives/occupancy_qa/g3.png"
            ),
            train_after_label=False,
            t=30.0,
        ),
    ]

    for group in groups:
        path = (
            curation
            / group.representative_crop_uri
        )
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Image.new(
            "RGB",
            (48, 64),
            (
                30 + int(group.start_timestamp_s),
                50,
                70,
            ),
        ).save(path)

    (
        curation
        / "visual_groups.jsonl"
    ).write_text(
        "".join(
            group.model_dump_json()
            + "\n"
            for group in groups
        ),
        encoding="utf-8",
    )

    source_dataset = (
        match
        / "datasets"
        / "slot-identity-dataset-exporter-0.21.1"
    )
    source_dataset.mkdir(
        parents=True,
        exist_ok=True,
    )
    (
        source_dataset
        / "summary.json"
    ).write_text(
        json.dumps(
            {
                "producer_version": (
                    "slot-identity-dataset-exporter-0.21.1"
                ),
                "game_context": {
                    "set_id": "TFT17",
                    "patch": "16.16",
                    "data_dragon_version": "16.16.1",
                },
            }
        ),
        encoding="utf-8",
    )

    (
        curation
        / "summary.json"
    ).write_text(
        json.dumps(
            {
                "producer_version": (
                    "slot-identity-curator-0.21.2"
                ),
                "source_dataset_dir": str(
                    source_dataset
                ),
                "visual_group_count": 3,
            }
        ),
        encoding="utf-8",
    )

    return curation


def _write_catalog(tmp_path):
    catalog = (
        tmp_path
        / "catalog.json"
    )
    catalog.write_text(
        json.dumps(
            {
                "provider": "riot_ddragon",
                "version": "16.16.1",
                "locale": "en_US",
                "source_url": "https://example.invalid/tft.json",
                "source_sha256": "a" * 64,
                "fetched_at_utc": "2026-08-15T00:00:00+00:00",
                "source_field_for_cost": "tier",
                "champions": [
                    {
                        "champion_id": "TFT17_Rhaast",
                        "name": "Rhaast",
                        "normalized_name": "rhaast",
                        "tier": 4,
                    },
                    {
                        "champion_id": "TFT17_Lissandra",
                        "name": "Lissandra",
                        "normalized_name": "lissandra",
                        "tier": 2,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return catalog


def _edit_labels(path, assignments):
    rows = []
    with Path(path).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as f:
        rows = list(
            csv.DictReader(f)
        )

    for row in rows:
        values = assignments.get(
            row["visual_group_id"]
        )
        if values is None:
            continue
        row.update(
            values
        )

    with Path(path).open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=rows[0].keys(),
        )
        writer.writeheader()
        writer.writerows(
            rows
        )


def test_prepare_package_copies_groups_and_pinned_set_schema(tmp_path):
    match = tmp_path / "match"
    curation = _write_curation(
        match
    )
    catalog = _write_catalog(
        tmp_path
    )

    package = prepare_identity_label_package(
        match,
        SlotIdentityLabelingSettings(),
        curation_dir=curation,
        catalog_path=catalog,
    )

    assert package[
        "visual_group_count"
    ] == 3
    assert package[
        "queue_type_counts"
    ] == {
        "identity_label": 2,
        "occupancy_qa": 1,
    }
    assert package[
        "catalog_available"
    ] is True
    assert package[
        "catalog_champion_count"
    ] == 2

    schema = json.loads(
        Path(
            package[
                "label_schema_path"
            ]
        ).read_text(
            encoding="utf-8"
        )
    )
    assert schema[
        "champion_catalog"
    ][
        "set_id"
    ] == "TFT17"
    assert schema[
        "champion_catalog"
    ][
        "champion_labels"
    ] == [
        "lissandra",
        "rhaast",
    ]

    with Path(
        package[
            "labels_path"
        ]
    ).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as f:
        rows = list(
            csv.DictReader(f)
        )

    assert len(rows) == 3
    assert all(
        row[
            "target_type"
        ] == ""
        for row in rows
    )
    assert all(
        (
            Path(
                package[
                    "output_dir"
                ]
            )
            / row[
                "image_uri"
            ]
        ).is_file()
        for row in rows
    )


def test_import_partial_labels_validates_catalog_and_writes_manifests(tmp_path):
    match = tmp_path / "match"
    curation = _write_curation(
        match
    )
    catalog = _write_catalog(
        tmp_path
    )

    package = prepare_identity_label_package(
        match,
        SlotIdentityLabelingSettings(),
        curation_dir=curation,
        catalog_path=catalog,
    )

    _edit_labels(
        package[
            "labels_path"
        ],
        {
            "g1": {
                "target_type": "champion",
                "champion_label": "Rhaast",
                "label_status": "human_labeled",
                "annotator": "tester",
            },
            "g2": {
                "target_type": "uncertain",
                "champion_label": "",
                "label_status": "human_labeled",
            },
            "g3": {
                "target_type": "no_unit",
                "champion_label": "",
                "label_status": "human_labeled",
            },
        },
    )

    summary = import_identity_labels(
        match,
        SlotIdentityLabelingSettings(),
        label_package_dir=Path(
            package[
                "output_dir"
            ]
        ),
        catalog_path=catalog,
    )

    assert summary[
        "labeled_group_count"
    ] == 3
    assert summary[
        "unlabeled_group_count"
    ] == 0
    assert summary[
        "target_type_counts"
    ] == {
        "champion": 1,
        "no_unit": 1,
        "uncertain": 1,
    }
    assert summary[
        "champion_class_count"
    ] == 1
    assert summary[
        "visual_champion_training_eligible_group_count"
    ] == 1
    assert summary[
        "occupancy_negative_eligible_group_count"
    ] == 1
    assert summary[
        "identity_queue_no_unit_conflict_count"
    ] == 0

    rhaast = summary[
        "per_champion"
    ][
        "rhaast"
    ]
    assert rhaast[
        "visual_group_count"
    ] == 1
    assert rhaast[
        "training_eligible_group_count"
    ] == 1
    assert rhaast[
        "match_count"
    ] == 1
    assert rhaast[
        "locations"
    ] == {
        "bench": 1,
    }

    labeled_path = Path(
        summary[
            "labeled_visual_groups_path"
        ]
    )
    values = [
        json.loads(line)
        for line in labeled_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    champion = next(
        value
        for value in values
        if value[
            "target_type"
        ] == "champion"
    )
    assert champion[
        "champion_label"
    ] == "rhaast"
    assert champion[
        "champion_id"
    ] == "TFT17_Rhaast"
    assert champion[
        "champion_catalog_validated"
    ] is True

    train_csv = Path(
        summary[
            "visual_champion_training_manifest_path"
        ]
    ).read_text(
        encoding="utf-8"
    )
    assert "rhaast" in train_csv

    negative_csv = Path(
        summary[
            "occupancy_negative_manifest_path"
        ]
    ).read_text(
        encoding="utf-8"
    )
    assert "g3" in negative_csv


def test_unknown_champion_label_is_rejected_by_pinned_set_catalog(tmp_path):
    match = tmp_path / "match"
    curation = _write_curation(
        match
    )
    catalog = _write_catalog(
        tmp_path
    )

    package = prepare_identity_label_package(
        match,
        SlotIdentityLabelingSettings(),
        curation_dir=curation,
        catalog_path=catalog,
    )

    _edit_labels(
        package[
            "labels_path"
        ],
        {
            "g1": {
                "target_type": "champion",
                "champion_label": "Batman",
            },
        },
    )

    with pytest.raises(
        ValueError,
        match="catalog validation",
    ):
        import_identity_labels(
            match,
            SlotIdentityLabelingSettings(),
            label_package_dir=Path(
                package[
                    "output_dir"
                ]
            ),
            catalog_path=catalog,
        )


def test_no_unit_in_identity_queue_is_conflict_not_auto_negative(tmp_path):
    match = tmp_path / "match"
    curation = _write_curation(
        match
    )
    catalog = _write_catalog(
        tmp_path
    )

    package = prepare_identity_label_package(
        match,
        SlotIdentityLabelingSettings(),
        curation_dir=curation,
        catalog_path=catalog,
    )

    _edit_labels(
        package[
            "labels_path"
        ],
        {
            "g1": {
                "target_type": "no_unit",
                "champion_label": "",
            },
        },
    )

    summary = import_identity_labels(
        match,
        SlotIdentityLabelingSettings(),
        label_package_dir=Path(
            package[
                "output_dir"
            ]
        ),
        catalog_path=catalog,
    )

    assert summary[
        "identity_queue_no_unit_conflict_count"
    ] == 1
    assert summary[
        "occupancy_negative_eligible_group_count"
    ] == 0


def test_require_complete_rejects_blank_queue_rows(tmp_path):
    match = tmp_path / "match"
    curation = _write_curation(
        match
    )
    catalog = _write_catalog(
        tmp_path
    )

    package = prepare_identity_label_package(
        match,
        SlotIdentityLabelingSettings(),
        curation_dir=curation,
        catalog_path=catalog,
    )

    _edit_labels(
        package[
            "labels_path"
        ],
        {
            "g1": {
                "target_type": "champion",
                "champion_label": "Rhaast",
            },
        },
    )

    with pytest.raises(
        ValueError,
        match="incomplete",
    ):
        import_identity_labels(
            match,
            SlotIdentityLabelingSettings(),
            label_package_dir=Path(
                package[
                    "output_dir"
                ]
            ),
            catalog_path=catalog,
            require_complete=True,
        )



def test_require_complete_queue_accepts_finished_identity_without_occupancy_qa(
    tmp_path,
):
    match = tmp_path / "match"
    curation = _write_curation(
        match
    )
    catalog = _write_catalog(
        tmp_path
    )

    package = prepare_identity_label_package(
        match,
        SlotIdentityLabelingSettings(),
        curation_dir=curation,
        catalog_path=catalog,
    )

    _edit_labels(
        package[
            "labels_path"
        ],
        {
            "g1": {
                "target_type": "champion",
                "champion_label": "Rhaast",
            },
            "g2": {
                "target_type": "uncertain",
                "champion_label": "",
            },
            # g3 is occupancy_qa and intentionally remains unlabeled.
        },
    )

    summary = import_identity_labels(
        match,
        SlotIdentityLabelingSettings(),
        label_package_dir=Path(
            package[
                "output_dir"
            ]
        ),
        catalog_path=catalog,
        require_complete_queue="identity_label",
    )

    assert summary[
        "require_complete_queue"
    ] == "identity_label"
    assert summary[
        "identity_label_queue_labeled"
    ] == 2
    assert summary[
        "identity_label_queue_total"
    ] == 2
    assert summary[
        "occupancy_qa_queue_labeled"
    ] == 0
    assert summary[
        "occupancy_qa_queue_total"
    ] == 1


def test_require_complete_queue_rejects_unfinished_selected_queue(tmp_path):
    match = tmp_path / "match"
    curation = _write_curation(
        match
    )
    catalog = _write_catalog(
        tmp_path
    )

    package = prepare_identity_label_package(
        match,
        SlotIdentityLabelingSettings(),
        curation_dir=curation,
        catalog_path=catalog,
    )

    _edit_labels(
        package[
            "labels_path"
        ],
        {
            "g1": {
                "target_type": "champion",
                "champion_label": "Rhaast",
            },
            "g2": {
                "target_type": "uncertain",
                "champion_label": "",
            },
        },
    )

    with pytest.raises(
        ValueError,
        match="occupancy_qa.*incomplete",
    ):
        import_identity_labels(
            match,
            SlotIdentityLabelingSettings(),
            label_package_dir=Path(
                package[
                    "output_dir"
                ]
            ),
            catalog_path=catalog,
            require_complete_queue="occupancy_qa",
        )
