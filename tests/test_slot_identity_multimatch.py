import csv
import json

from PIL import Image

from tft_analyzer.features.slot_identity_multimatch import (
    build_multimatch_identity_dataset,
)


def _write_match(tmp_path, match_id, rows):
    match_dir = tmp_path / "data" / "matches" / match_id
    audit_dir = (
        match_dir
        / "audits"
        / "slot-identity-human-label-audit-0.21.7"
    )
    import_dir = (
        match_dir
        / "labels"
        / "slot-identity-label-importer-0.21.3"
    )
    curation_dir = (
        match_dir
        / "datasets"
        / "slot-identity-curator-0.21.2"
    )
    representatives = curation_dir / "representatives" / "identity_label"
    representatives.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    import_dir.mkdir(parents=True)

    for row in rows:
        Image.new("RGB", (20, 30), (20, 40, 60)).save(
            representatives / f"{row['visual_group_id']}.png"
        )

    manifest_fields = [
        "visual_group_id",
        "match_id",
        "split_key",
        "training_tier",
        "location",
        "slot_id",
        "representative_tier",
        "representative_tracked_source",
        "representative_crop_uri",
        "champion_label",
        "champion_id",
        "member_count",
    ]
    with (
        audit_dir / "visual_champion_human_confirmed_manifest.csv"
    ).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manifest_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "match_id": match_id,
                    "split_key": match_id,
                    "location": "bench",
                    "slot_id": "b0",
                    "representative_tier": row["training_tier"],
                    "representative_tracked_source": "current",
                    "representative_crop_uri": (
                        "representatives/identity_label/"
                        f"{row['visual_group_id']}.png"
                    ),
                    "champion_id": "TFT17_" + row["champion_label"],
                    "member_count": 1,
                }
            )

    (audit_dir / "summary.json").write_text(
        json.dumps(
            {
                "source_unlabeled_group_count": 0,
                "source_label_import_dir": str(import_dir),
            }
        ),
        encoding="utf-8",
    )
    (import_dir / "summary.json").write_text(
        json.dumps(
            {
                "source_curation_dir": str(curation_dir),
                "game_context": {
                    "set_id": "TFT17",
                    "patch": "16.16",
                    "data_dragon_version": "16.16.1",
                    "catalog_source_sha256": "a" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    return match_dir


def test_build_multimatch_dataset_preserves_tiers_and_match_folds(tmp_path):
    matches = []
    for index in range(3):
        matches.append(
            _write_match(
                tmp_path,
                f"match-{index}",
                [
                    {
                        "visual_group_id": f"g{index}-a",
                        "training_tier": "primary",
                        "champion_label": "aatrox",
                    },
                    {
                        "visual_group_id": f"g{index}-b",
                        "training_tier": (
                            "secondary" if index < 2 else "recovered_candidate"
                        ),
                        "champion_label": "briar",
                    },
                    {
                        "visual_group_id": f"g{index}-c",
                        "training_tier": "recovered_candidate",
                        "champion_label": f"only{index}",
                    },
                ],
            )
        )

    output_dir = tmp_path / "combined"
    summary = build_multimatch_identity_dataset(
        matches,
        output_dir=output_dir,
    )

    assert summary["visual_group_count"] == 9
    assert summary["tier_counts"] == {
        "primary": 3,
        "recovered_candidate": 4,
        "secondary": 2,
    }
    assert summary["protocols"]["human_confirmed"]["classes"] == [
        "aatrox",
        "briar",
    ]
    assert summary["protocols"]["clean"]["classes"] == ["aatrox"]
    assert len(summary["protocols"]["human_confirmed"]["folds"]) == 3

    with (output_dir / "manifest.csv").open(
        "r", encoding="utf-8", newline=""
    ) as f:
        manifest = list(csv.DictReader(f))
    assert len(manifest) == 9
    assert all(row["split_key"] == row["match_id"] for row in manifest)
    assert all(row["image_path"] for row in manifest)


def test_build_multimatch_rejects_incomplete_audit(tmp_path):
    first = _write_match(
        tmp_path,
        "match-a",
        [
            {
                "visual_group_id": "g1",
                "training_tier": "primary",
                "champion_label": "aatrox",
            }
        ],
    )
    second = _write_match(
        tmp_path,
        "match-b",
        [
            {
                "visual_group_id": "g2",
                "training_tier": "primary",
                "champion_label": "aatrox",
            }
        ],
    )
    audit_summary = (
        second
        / "audits"
        / "slot-identity-human-label-audit-0.21.7"
        / "summary.json"
    )
    payload = json.loads(audit_summary.read_text(encoding="utf-8"))
    payload["source_unlabeled_group_count"] = 1
    audit_summary.write_text(json.dumps(payload), encoding="utf-8")

    try:
        build_multimatch_identity_dataset(
            [first, second],
            output_dir=tmp_path / "combined",
        )
        raise AssertionError("Expected incomplete-audit failure")
    except ValueError as exc:
        assert "incomplete" in str(exc).lower()
