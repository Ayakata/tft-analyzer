import csv
import json

from PIL import Image

from tft_analyzer.features.slot_identity_baseline import (
    classification_metrics,
    load_baseline_manifest,
)


def test_classification_metrics_reports_top1_top3_and_macro_recall():
    metrics = classification_metrics(
        truth=[0, 0, 1, 2],
        predictions=[0, 1, 1, 1],
        topk_predictions=[
            [0, 1, 2],
            [1, 0, 2],
            [1, 2, 0],
            [1, 2, 0],
        ],
        class_names=["a", "b", "c"],
    )

    assert metrics["accuracy"] == 0.5
    assert metrics["top3_accuracy"] == 1.0
    assert metrics["macro_recall"] == (0.5 + 1.0 + 0.0) / 3
    assert metrics["per_class"]["c"] == {
        "support": 1,
        "correct": 0,
        "recall": 0.0,
    }


def test_load_baseline_manifest_validates_images_and_types(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    image_path = dataset / "crop.png"
    Image.new("RGB", (12, 18), (10, 20, 30)).save(image_path)
    (dataset / "summary.json").write_text(
        json.dumps(
            {
                "producer_version": "slot-identity-multimatch-0.22.0",
                "protocols": {},
            }
        ),
        encoding="utf-8",
    )
    with (dataset / "manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "visual_group_id",
                "match_id",
                "training_tier",
                "location",
                "champion_label",
                "member_count",
                "image_path",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "visual_group_id": "g1",
                "match_id": "m1",
                "training_tier": "primary",
                "location": "bench",
                "champion_label": "aatrox",
                "member_count": "3",
                "image_path": str(image_path),
            }
        )

    rows, summary = load_baseline_manifest(dataset)

    assert summary["producer_version"] == "slot-identity-multimatch-0.22.0"
    assert rows[0]["member_count"] == 3
