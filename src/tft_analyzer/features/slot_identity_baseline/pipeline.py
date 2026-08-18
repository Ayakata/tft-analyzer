from __future__ import annotations

from collections import Counter, defaultdict
import copy
import csv
import json
from pathlib import Path
import random
import shutil
import time
from typing import Callable

import numpy as np
from PIL import Image


BASELINE_PRODUCER_VERSION = "slot-identity-baseline-0.22.0"

_TIER_WEIGHTS = {
    "primary": 1.0,
    "secondary": 0.8,
    "recovered_candidate": 0.5,
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_baseline_manifest(dataset_dir: Path | str) -> tuple[list[dict], dict]:
    dataset_dir = Path(dataset_dir).resolve()
    summary_path = dataset_dir / "summary.json"
    manifest_path = dataset_dir / "manifest.csv"
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    summary = _load_json(summary_path)
    if summary.get("producer_version") != "slot-identity-multimatch-0.22.0":
        raise ValueError(
            "Unsupported multimatch dataset version: "
            f"{summary.get('producer_version')!r}"
        )
    with manifest_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        image_path = Path(row["image_path"])
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        row["member_count"] = int(row["member_count"])
    return rows, summary


def classification_metrics(
    truth: list[int],
    predictions: list[int],
    topk_predictions: list[list[int]],
    class_names: list[str],
) -> dict:
    if not truth or len(truth) != len(predictions):
        raise ValueError("truth and predictions must be non-empty and aligned")
    if len(topk_predictions) != len(truth):
        raise ValueError("top-k predictions must align with truth")

    class_count = len(class_names)
    confusion = [[0 for _ in range(class_count)] for _ in range(class_count)]
    for target, predicted in zip(truth, predictions, strict=True):
        confusion[target][predicted] += 1

    per_class = {}
    recalls = []
    for index, class_name in enumerate(class_names):
        support = sum(confusion[index])
        correct = confusion[index][index]
        recall = correct / support if support else None
        if recall is not None:
            recalls.append(recall)
        per_class[class_name] = {
            "support": support,
            "correct": correct,
            "recall": recall,
        }

    correct = sum(int(a == b) for a, b in zip(truth, predictions, strict=True))
    topk_correct = sum(
        int(target in candidates)
        for target, candidates in zip(truth, topk_predictions, strict=True)
    )
    return {
        "sample_count": len(truth),
        "accuracy": correct / len(truth),
        "top3_accuracy": topk_correct / len(truth),
        "macro_recall": sum(recalls) / len(recalls),
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def _replace_directory_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int = 8,
    initial_delay_s: float = 0.05,
) -> None:
    delay_s = initial_delay_s
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_s)
            delay_s = min(delay_s * 2.0, 0.5)


def _require_torch():
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, WeightedRandomSampler
        from torchvision import models, transforms
    except ImportError as exc:
        raise RuntimeError(
            "Identity baseline requires PyTorch and Torchvision. Install the "
            "project with `python -m pip install -e \".[ml]\"`."
        ) from exc
    return torch, nn, DataLoader, WeightedRandomSampler, models, transforms


class _ImageRows:
    def __init__(self, rows, *, class_to_index, transform):
        self.rows = rows
        self.class_to_index = class_to_index
        self.transform = transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(row["image_path"]) as source:
            image = source.convert("RGB")
        return (
            self.transform(image),
            self.class_to_index[row["champion_label"]],
            float(_TIER_WEIGHTS[row["training_tier"]]),
            index,
        )


def _evaluate(
    model,
    loader,
    *,
    rows,
    class_names,
    device,
    torch,
) -> tuple[dict, list[dict]]:
    model.eval()
    truth: list[int] = []
    predicted: list[int] = []
    topk_values: list[list[int]] = []
    prediction_rows: list[dict] = []
    topk_size = min(3, len(class_names))
    with torch.inference_mode():
        for images, targets, _tier_weights, row_indexes in loader:
            images = images.to(device, non_blocking=True)
            logits = model(images)
            probabilities = torch.softmax(logits, dim=1)
            confidence, topk = probabilities.topk(topk_size, dim=1)
            batch_predictions = topk[:, 0]
            for offset in range(len(targets)):
                target = int(targets[offset])
                candidates = [int(value) for value in topk[offset].cpu().tolist()]
                prediction = int(batch_predictions[offset].cpu())
                source = rows[int(row_indexes[offset])]
                truth.append(target)
                predicted.append(prediction)
                topk_values.append(candidates)
                prediction_rows.append(
                    {
                        "visual_group_id": source["visual_group_id"],
                        "match_id": source["match_id"],
                        "training_tier": source["training_tier"],
                        "location": source["location"],
                        "true_label": class_names[target],
                        "predicted_label": class_names[prediction],
                        "confidence": float(confidence[offset, 0].cpu()),
                        "top3_labels": "|".join(
                            class_names[value] for value in candidates
                        ),
                        "correct": prediction == target,
                    }
                )
    return (
        classification_metrics(truth, predicted, topk_values, class_names),
        prediction_rows,
    )


def _metrics_by_tier(prediction_rows: list[dict], class_names: list[str]) -> dict:
    class_to_index = {name: index for index, name in enumerate(class_names)}
    values = {}
    for tier in _TIER_WEIGHTS:
        selected = [row for row in prediction_rows if row["training_tier"] == tier]
        if not selected:
            continue
        truth = [class_to_index[row["true_label"]] for row in selected]
        predicted = [class_to_index[row["predicted_label"]] for row in selected]
        topk = [
            [class_to_index[value] for value in row["top3_labels"].split("|")]
            for row in selected
        ]
        values[tier] = classification_metrics(
            truth, predicted, topk, class_names
        )
    return values


def _train_fold(
    *,
    train_rows: list[dict],
    validation_rows: list[dict],
    class_names: list[str],
    fold_dir: Path,
    epochs: int,
    batch_size: int,
    image_size: int,
    learning_rate: float,
    seed: int,
    device_name: str,
    pretrained: bool,
    progress: Callable[[dict], None] | None,
) -> dict:
    (
        torch,
        nn,
        DataLoader,
        WeightedRandomSampler,
        models,
        transforms,
    ) = _require_torch()

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    device = torch.device(
        "cuda" if device_name == "auto" and torch.cuda.is_available() else (
            "cpu" if device_name == "auto" else device_name
        )
    )
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    if device.type == "cuda":
        torch.set_float32_matmul_precision("high")

    class_to_index = {name: index for index, name in enumerate(class_names)}
    normalize = transforms.Normalize(
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225),
    )
    train_transform = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ColorJitter(
                brightness=0.12,
                contrast=0.12,
                saturation=0.08,
                hue=0.02,
            ),
            transforms.ToTensor(),
            normalize,
        ]
    )
    validation_transform = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            normalize,
        ]
    )
    train_dataset = _ImageRows(
        train_rows,
        class_to_index=class_to_index,
        transform=train_transform,
    )
    validation_dataset = _ImageRows(
        validation_rows,
        class_to_index=class_to_index,
        transform=validation_transform,
    )

    class_counts = Counter(row["champion_label"] for row in train_rows)
    sample_weights = [
        1.0 / class_counts[row["champion_label"]] for row in train_rows
    ]
    generator = torch.Generator().manual_seed(seed)
    sampler = WeightedRandomSampler(
        sample_weights,
        num_samples=len(sample_weights),
        replacement=True,
        generator=generator,
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        sampler=sampler,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )

    weights = models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
    model = models.mobilenet_v3_small(weights=weights)
    model.classifier[3] = nn.Linear(
        model.classifier[3].in_features,
        len(class_names),
    )
    model.to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=max(epochs, 1),
    )
    criterion = nn.CrossEntropyLoss(reduction="none", label_smoothing=0.05)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    fold_dir.mkdir(parents=True)
    checkpoint_path = fold_dir / "best.pt"
    history = []
    best_macro_recall = -1.0
    best_epoch = 0
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        seen = 0
        for images, targets, tier_weights, _row_indexes in train_loader:
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            tier_weights = tier_weights.to(
                device=device,
                dtype=torch.float32,
                non_blocking=True,
            )
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=use_amp):
                logits = model(images)
                losses = criterion(logits, targets)
                loss = (losses * tier_weights).sum() / tier_weights.sum()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            batch_count = int(targets.shape[0])
            total_loss += float(loss.detach().cpu()) * batch_count
            seen += batch_count
        scheduler.step()

        validation_metrics, _ = _evaluate(
            model,
            validation_loader,
            rows=validation_rows,
            class_names=class_names,
            device=device,
            torch=torch,
        )
        epoch_result = {
            "epoch": epoch,
            "training_loss": total_loss / max(seen, 1),
            "learning_rate": optimizer.param_groups[0]["lr"],
            "validation_accuracy": validation_metrics["accuracy"],
            "validation_top3_accuracy": validation_metrics["top3_accuracy"],
            "validation_macro_recall": validation_metrics["macro_recall"],
        }
        history.append(epoch_result)
        if progress:
            progress(copy.deepcopy(epoch_result))
        if validation_metrics["macro_recall"] > best_macro_recall:
            best_macro_recall = validation_metrics["macro_recall"]
            best_epoch = epoch
            torch.save(
                {
                    "producer_version": BASELINE_PRODUCER_VERSION,
                    "architecture": "mobilenet_v3_small",
                    "pretrained_imagenet": pretrained,
                    "image_size": image_size,
                    "class_names": class_names,
                    "model_state_dict": model.state_dict(),
                },
                checkpoint_path,
            )

    checkpoint = torch.load(
        checkpoint_path,
        map_location=device,
        weights_only=False,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    metrics, prediction_rows = _evaluate(
        model,
        validation_loader,
        rows=validation_rows,
        class_names=class_names,
        device=device,
        torch=torch,
    )
    metrics["by_training_tier"] = _metrics_by_tier(
        prediction_rows, class_names
    )
    predictions_path = fold_dir / "predictions.csv"
    with predictions_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(prediction_rows[0]))
        writer.writeheader()
        writer.writerows(prediction_rows)
    (fold_dir / "history.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "best_epoch": best_epoch,
        "metrics": metrics,
        "history": history,
        "checkpoint_path": str(checkpoint_path),
        "predictions_path": str(predictions_path),
        "device": str(device),
        "prediction_rows": prediction_rows,
    }


def train_identity_baseline(
    dataset_dir: Path | str,
    *,
    protocol: str = "human_confirmed",
    output_dir: Path | str | None = None,
    epochs: int = 8,
    batch_size: int = 64,
    image_size: int = 128,
    learning_rate: float = 3e-4,
    seed: int = 1729,
    device: str = "auto",
    pretrained: bool = True,
    force: bool = False,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    if epochs < 1 or batch_size < 1 or image_size < 32:
        raise ValueError("Invalid baseline training dimensions")
    rows, dataset_summary = load_baseline_manifest(dataset_dir)
    protocols = dataset_summary.get("protocols") or {}
    if protocol not in protocols:
        raise ValueError(
            f"Unknown protocol {protocol!r}; choose from {sorted(protocols)}"
        )
    protocol_summary = protocols[protocol]
    class_names = list(protocol_summary["classes"])
    tiers = set(protocol_summary["training_tiers"])
    if len(class_names) < 2:
        raise ValueError(f"Protocol {protocol!r} has fewer than two classes")
    selected = [
        row
        for row in rows
        if row["training_tier"] in tiers
        and row["champion_label"] in class_names
    ]

    dataset_dir = Path(dataset_dir).resolve()
    output_dir = Path(
        output_dir
        or dataset_dir / "baselines" / BASELINE_PRODUCER_VERSION
    ).resolve()
    temp_dir = output_dir.with_name(output_dir.name + ".tmp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    if output_dir.exists() and not force:
        raise FileExistsError(f"Output already exists: {output_dir}; pass --force")
    temp_dir.mkdir(parents=True)

    match_ids = list(dataset_summary["match_ids"])
    fold_results = []
    all_predictions = []
    for fold_index, validation_match_id in enumerate(match_ids):
        train_rows = [
            row for row in selected if row["match_id"] != validation_match_id
        ]
        validation_rows = [
            row for row in selected if row["match_id"] == validation_match_id
        ]
        missing_train = set(class_names) - {
            row["champion_label"] for row in train_rows
        }
        missing_validation = set(class_names) - {
            row["champion_label"] for row in validation_rows
        }
        if missing_train or missing_validation:
            raise ValueError(
                f"Fold {validation_match_id} is missing classes: "
                f"train={sorted(missing_train)} validation={sorted(missing_validation)}"
            )
        if progress:
            progress(
                {
                    "event": "fold_start",
                    "fold_index": fold_index + 1,
                    "fold_count": len(match_ids),
                    "validation_match_id": validation_match_id,
                    "training_group_count": len(train_rows),
                    "validation_group_count": len(validation_rows),
                }
            )

        def fold_progress(value):
            if progress:
                progress(
                    {
                        "event": "epoch",
                        "fold_index": fold_index + 1,
                        "fold_count": len(match_ids),
                        "validation_match_id": validation_match_id,
                        **value,
                    }
                )

        fold_dir = temp_dir / f"fold-{validation_match_id}"
        result = _train_fold(
            train_rows=train_rows,
            validation_rows=validation_rows,
            class_names=class_names,
            fold_dir=fold_dir,
            epochs=epochs,
            batch_size=batch_size,
            image_size=image_size,
            learning_rate=learning_rate,
            seed=seed + fold_index,
            device_name=device,
            pretrained=pretrained,
            progress=fold_progress,
        )
        all_predictions.extend(result.pop("prediction_rows"))
        result["checkpoint_path"] = str(
            output_dir / fold_dir.name / "best.pt"
        )
        result["predictions_path"] = str(
            output_dir / fold_dir.name / "predictions.csv"
        )
        result.update(
            {
                "validation_match_id": validation_match_id,
                "training_match_ids": [
                    match_id for match_id in match_ids if match_id != validation_match_id
                ],
                "training_group_count": len(train_rows),
                "validation_group_count": len(validation_rows),
            }
        )
        fold_results.append(result)

    class_to_index = {name: index for index, name in enumerate(class_names)}
    aggregate_metrics = classification_metrics(
        [class_to_index[row["true_label"]] for row in all_predictions],
        [class_to_index[row["predicted_label"]] for row in all_predictions],
        [
            [class_to_index[value] for value in row["top3_labels"].split("|")]
            for row in all_predictions
        ],
        class_names,
    )
    aggregate_metrics["by_training_tier"] = _metrics_by_tier(
        all_predictions, class_names
    )
    summary = {
        "schema_version": 1,
        "producer_version": BASELINE_PRODUCER_VERSION,
        "source_dataset_dir": str(dataset_dir),
        "source_dataset_producer_version": dataset_summary["producer_version"],
        "protocol": protocol,
        "training_tiers": sorted(tiers),
        "class_count": len(class_names),
        "class_names": class_names,
        "match_count": len(match_ids),
        "match_ids": match_ids,
        "cross_validation": "leave_one_match_out",
        "architecture": "mobilenet_v3_small",
        "pretrained_imagenet": pretrained,
        "epochs": epochs,
        "batch_size": batch_size,
        "image_size": image_size,
        "learning_rate": learning_rate,
        "seed": seed,
        "tier_loss_weights": _TIER_WEIGHTS,
        "folds": fold_results,
        "aggregate_metrics": aggregate_metrics,
        "output_dir": str(output_dir),
        "summary_path": str(output_dir / "summary.json"),
    }
    (temp_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    _replace_directory_with_retry(temp_dir, output_dir)
    return summary
