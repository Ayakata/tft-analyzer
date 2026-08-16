from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

from PIL import Image

from tft_analyzer.features.slot_identity_dataset.models import (
    SlotIdentityObservation,
)

from .models import (
    CuratedSlotVisualGroup,
    SlotIdentityCurationSettings,
)


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version_key(path: Path):
    matches = list(
        _VERSION_RE.finditer(path.name)
    )
    version = (
        tuple(
            int(value)
            for value in matches[-1].groups()
        )
        if matches
        else (0, 0, 0)
    )
    return (
        *version,
        path.stat().st_mtime,
    )


def find_latest_slot_identity_dataset(
    match_dir: Path | str,
) -> Path:
    datasets_dir = (
        Path(match_dir)
        / "datasets"
    )
    candidates = [
        path
        for path in datasets_dir.glob(
            "slot-identity-dataset-exporter-*"
        )
        if path.is_dir()
        and (path / "summary.json").is_file()
        and (path / "manifest.jsonl").is_file()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No slot-identity dataset under {datasets_dir}. "
            "Run `tft-analyzer export-slot-identity-dataset <match_dir>` first."
        )
    return max(
        candidates,
        key=_version_key,
    )


def _load_json(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def _load_manifest(
    path: Path,
) -> list[SlotIdentityObservation]:
    values = []
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                values.append(
                    SlotIdentityObservation.model_validate_json(
                        line
                    )
                )
    return values


def _dhash(
    image_path: Path,
    *,
    hash_size: int,
) -> int:
    if hash_size <= 0:
        raise ValueError(
            "dhash_size must be > 0"
        )

    with Image.open(
        image_path
    ) as src:
        image = (
            src
            .convert("L")
            .resize(
                (
                    hash_size + 1,
                    hash_size,
                )
            )
        )
        pixels = image.tobytes()

    value = 0
    for row in range(
        hash_size
    ):
        start = row * (
            hash_size + 1
        )
        for col in range(
            hash_size
        ):
            left = pixels[
                start + col
            ]
            right = pixels[
                start + col + 1
            ]
            value <<= 1
            if left > right:
                value |= 1
    return value


def _hamming(
    left: int,
    right: int,
) -> int:
    return (
        left ^ right
    ).bit_count()


def _queue_type(
    item: SlotIdentityObservation,
    settings: SlotIdentityCurationSettings,
) -> str | None:
    if (
        item.occupancy_evidence_tier
        in settings.identity_tiers
    ):
        return "identity_label"

    if (
        item.occupancy_evidence_tier
        in settings.occupancy_qa_tiers
    ):
        return "occupancy_qa"

    return None


def _tracked_source(
    item: SlotIdentityObservation,
) -> str:
    if item.tracked_is_current_evidence:
        return "current"
    if item.tracked_source_evidence_id:
        return "carry"
    return "none"


def _representative_rank(
    item: SlotIdentityObservation,
) -> tuple:
    tier_rank = {
        "trusted": 3,
        "supported": 2,
        "raw_candidate": 1,
    }.get(
        item.occupancy_evidence_tier,
        0,
    )
    source_rank = {
        "current": 2,
        "carry": 1,
        "none": 0,
    }[
        _tracked_source(
            item
        )
    ]
    return (
        tier_rank,
        int(
            item.recommended_for_identity_training
        ),
        int(
            item.recommended_for_identity_labeling
        ),
        int(
            item.board_strong_snapshot
            is True
        ),
        source_rank,
        item.raw_occupancy_confidence,
        -item.timestamp_s,
        item.sample_id,
    )


def _visual_group_id(
    *,
    match_id: str,
    queue_type: str,
    location: str,
    slot_id: str,
    first_sample_id: str,
    producer_version: str,
) -> str:
    raw = "|".join(
        [
            match_id,
            queue_type,
            location,
            slot_id,
            first_sample_id,
            producer_version,
        ]
    )
    digest = hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]
    return f"visual-{digest}"


def _cross_tab(
    items: list[SlotIdentityObservation],
    row_value,
    col_value,
) -> dict[str, dict[str, int]]:
    table = defaultdict(Counter)
    for item in items:
        table[
            str(row_value(item))
        ][
            str(col_value(item))
        ] += 1

    return {
        row: dict(
            sorted(
                counts.items()
            )
        )
        for row, counts in sorted(
            table.items()
        )
    }


def _recommendation(
    item: SlotIdentityObservation,
) -> str:
    if item.recommended_for_identity_training:
        return "identity_training"
    if item.recommended_for_identity_labeling:
        return "identity_labeling"
    if item.recommended_for_occupancy_review:
        return "occupancy_review"
    return "none"


def _strong_snapshot(
    item: SlotIdentityObservation,
) -> str:
    return (
        "strong"
        if item.board_strong_snapshot
        else "not_strong"
    )


def _write_jsonl(
    path: Path,
    values,
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        for value in values:
            f.write(
                value.model_dump_json()
                + "\n"
            )


def _copy_representative(
    *,
    source_dataset_dir: Path,
    temp_dir: Path,
    group_id: str,
    queue_type: str,
    item: SlotIdentityObservation,
) -> str:
    src = (
        source_dataset_dir
        / item.crop_uri
    )
    if not src.is_file():
        raise FileNotFoundError(
            src
        )

    suffix = (
        src.suffix.lower()
        or ".png"
    )
    relative = (
        Path("representatives")
        / queue_type
        / f"{group_id}{suffix}"
    )
    dst = (
        temp_dir
        / relative
    )
    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        src,
        dst,
    )
    return relative.as_posix()


def _write_queue_csv(
    path: Path,
    groups: list[CuratedSlotVisualGroup],
    *,
    queue_type: str,
) -> None:
    selected = [
        group
        for group in groups
        if group.queue_type
        == queue_type
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.writer(
            f
        )
        writer.writerow(
            [
                "visual_group_id",
                "representative_crop_uri",
                "location",
                "slot_id",
                "stage_start",
                "stage_end",
                "start_timestamp_s",
                "end_timestamp_s",
                "member_count",
                "representative_tier",
                "recommended_for_identity_training_after_label",
                "target_type",
                "champion_label",
                "label_status",
                "notes",
            ]
        )

        for group in selected:
            writer.writerow(
                [
                    group.visual_group_id,
                    group.representative_crop_uri,
                    group.location,
                    group.slot_id,
                    group.stage_start or "",
                    group.stage_end or "",
                    f"{group.start_timestamp_s:.3f}",
                    f"{group.end_timestamp_s:.3f}",
                    group.member_count,
                    group.representative_tier,
                    str(
                        group
                        .recommended_for_identity_training_after_label
                    ).lower(),
                    "",
                    "",
                    "unlabeled",
                    "",
                ]
            )


def _write_readme(
    path: Path,
    *,
    producer_version: str,
) -> None:
    path.write_text(
        f"""# TFT Slot Identity Curation

Producer: `{producer_version}`

This directory contains curation metadata and representative images derived
from a 0.21.1 slot-identity observation dataset.

The curator never changes perception truth and never infers champion identity.

## Visual grouping

Temporal observations are compared only inside:

```text
match_id + location + slot_id + queue_type
```

and optionally split on stage changes.

Two observations are grouped only when both conditions hold:

```text
timestamp gap <= configured max_temporal_gap_s
dHash distance <= configured max_dhash_distance
```

This is near-duplicate curation, not champion tracking. Different visual groups
may still show the same champion.

## Queues

`identity_label_queue.csv` contains representatives from trusted/supported
identity evidence.

`occupancy_qa_queue.csv` contains representatives from raw-candidate occupancy
evidence and is intended for labels such as `no_unit`, `uncertain` or
`unusable`.

## ML split contract

Never random-split individual crops or visual groups from the same recorded
match between train/validation/test.

The split unit is:

```text
match_id
```

Visual grouping reduces temporal duplicates but does not make samples from one
match statistically independent.

Acquisition priors remain metadata for a later resolver and must not be used as
visual-classifier input features.
""",
        encoding="utf-8",
    )


def curate_slot_identity_dataset(
    match_dir: Path | str,
    settings: SlotIdentityCurationSettings,
    *,
    source_dataset_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    force: bool = False,
) -> dict[str, object]:
    match_dir = Path(
        match_dir
    )

    source_dataset_dir = (
        Path(
            source_dataset_dir
        )
        if source_dataset_dir
        is not None
        else find_latest_slot_identity_dataset(
            match_dir
        )
    )
    source_summary_path = (
        source_dataset_dir
        / "summary.json"
    )
    source_manifest_path = (
        source_dataset_dir
        / "manifest.jsonl"
    )

    source_summary = _load_json(
        source_summary_path
    )
    observations = _load_manifest(
        source_manifest_path
    )

    source_producer = str(
        source_summary.get(
            "producer_version",
            "",
        )
    )
    if (
        not source_producer.startswith(
            "slot-identity-dataset-exporter-"
        )
    ):
        raise ValueError(
            "Source is not a slot-identity observation dataset."
        )

    output_dir = (
        Path(output_dir)
        if output_dir is not None
        else (
            match_dir
            / "datasets"
            / settings.producer_version
        )
    )

    if output_dir.exists():
        if not force:
            raise FileExistsError(
                f"Curation directory already exists: {output_dir}. "
                "Pass --force to regenerate it."
            )
        shutil.rmtree(
            output_dir
        )

    temp_dir = output_dir.with_name(
        output_dir.name + ".tmp"
    )
    if temp_dir.exists():
        shutil.rmtree(
            temp_dir
        )
    temp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    hash_by_sample = {}
    hash_hex_width = (
        settings.dhash_size
        * settings.dhash_size
        + 3
    ) // 4

    for item in observations:
        crop_path = (
            source_dataset_dir
            / item.crop_uri
        )
        hash_by_sample[
            item.sample_id
        ] = _dhash(
            crop_path,
            hash_size=settings.dhash_size,
        )

    buckets = defaultdict(
        list
    )
    skipped_tier_count = 0

    for item in observations:
        queue_type = _queue_type(
            item,
            settings,
        )
        if queue_type is None:
            skipped_tier_count += 1
            continue

        buckets[
            (
                item.match_id,
                item.location,
                item.slot_id,
                queue_type,
            )
        ].append(
            item
        )

    groups_members = []

    for key, bucket in sorted(
        buckets.items()
    ):
        ordered = sorted(
            bucket,
            key=lambda item: (
                item.timestamp_s,
                item.sample_id,
            ),
        )
        current = []

        for item in ordered:
            if not current:
                current = [
                    item
                ]
                continue

            representative = max(
                current,
                key=_representative_rank,
            )
            previous = current[
                -1
            ]

            gap = (
                item.timestamp_s
                - previous.timestamp_s
            )
            same_stage = (
                item.stage
                == representative.stage
            )
            distance = _hamming(
                hash_by_sample[
                    item.sample_id
                ],
                hash_by_sample[
                    representative.sample_id
                ],
            )

            compatible = (
                gap
                <= settings.max_temporal_gap_s
                and distance
                <= settings.max_dhash_distance
                and (
                    not settings.split_on_stage_change
                    or same_stage
                )
            )

            if compatible:
                current.append(
                    item
                )
            else:
                groups_members.append(
                    (
                        key,
                        current,
                    )
                )
                current = [
                    item
                ]

        if current:
            groups_members.append(
                (
                    key,
                    current,
                )
            )

    groups = []

    for (
        (
            match_id,
            location,
            slot_id,
            queue_type,
        ),
        members,
    ) in groups_members:
        representative = max(
            members,
            key=_representative_rank,
        )
        group_id = _visual_group_id(
            match_id=match_id,
            queue_type=queue_type,
            location=location,
            slot_id=slot_id,
            first_sample_id=members[0].sample_id,
            producer_version=settings.producer_version,
        )
        representative_uri = _copy_representative(
            source_dataset_dir=source_dataset_dir,
            temp_dir=temp_dir,
            group_id=group_id,
            queue_type=queue_type,
            item=representative,
        )

        tier_counts = Counter(
            item.occupancy_evidence_tier
            for item in members
        )
        stages = tuple(
            dict.fromkeys(
                item.stage
                for item in members
                if item.stage
            )
        )
        start = min(
            item.timestamp_s
            for item in members
        )
        end = max(
            item.timestamp_s
            for item in members
        )

        groups.append(
            CuratedSlotVisualGroup(
                visual_group_id=group_id,
                match_id=match_id,
                queue_type=queue_type,
                location=location,
                slot_id=slot_id,
                start_timestamp_s=start,
                end_timestamp_s=end,
                duration_s=max(
                    0.0,
                    end - start,
                ),
                stage_start=members[0].stage,
                stage_end=members[-1].stage,
                stages=stages,
                member_count=len(
                    members
                ),
                member_sample_ids=tuple(
                    item.sample_id
                    for item in members
                ),
                member_tier_counts=dict(
                    sorted(
                        tier_counts.items()
                    )
                ),
                representative_sample_id=(
                    representative.sample_id
                ),
                representative_timestamp_s=(
                    representative.timestamp_s
                ),
                representative_crop_uri=(
                    representative_uri
                ),
                representative_source_crop_uri=(
                    representative.crop_uri
                ),
                representative_tier=(
                    representative
                    .occupancy_evidence_tier
                ),
                representative_raw_occupancy_confidence=(
                    representative
                    .raw_occupancy_confidence
                ),
                representative_tracked_source=(
                    _tracked_source(
                        representative
                    )
                ),
                representative_dhash_hex=(
                    f"{hash_by_sample[representative.sample_id]:0{hash_hex_width}x}"
                ),
                recommended_for_identity_labeling=(
                    queue_type
                    == "identity_label"
                ),
                recommended_for_identity_training_after_label=(
                    representative
                    .occupancy_evidence_tier
                    == "trusted"
                ),
                recommended_for_occupancy_review=(
                    queue_type
                    == "occupancy_qa"
                ),
                split_key=match_id,
                source_dataset_producer_version=(
                    source_producer
                ),
                source_manifest_path=str(
                    source_manifest_path
                ),
                producer_version=(
                    settings.producer_version
                ),
            )
        )

    groups.sort(
        key=lambda group: (
            group.start_timestamp_s,
            group.location,
            group.slot_id,
            group.queue_type,
        )
    )

    groups_path = (
        temp_dir
        / "visual_groups.jsonl"
    )
    identity_queue_path = (
        temp_dir
        / "identity_label_queue.csv"
    )
    occupancy_queue_path = (
        temp_dir
        / "occupancy_qa_queue.csv"
    )
    summary_path_temp = (
        temp_dir
        / "summary.json"
    )
    readme_path = (
        temp_dir
        / "README.md"
    )

    _write_jsonl(
        groups_path,
        groups,
    )
    _write_queue_csv(
        identity_queue_path,
        groups,
        queue_type="identity_label",
    )
    _write_queue_csv(
        occupancy_queue_path,
        groups,
        queue_type="occupancy_qa",
    )
    _write_readme(
        readme_path,
        producer_version=settings.producer_version,
    )

    identity_groups = [
        group
        for group in groups
        if group.queue_type
        == "identity_label"
    ]
    qa_groups = [
        group
        for group in groups
        if group.queue_type
        == "occupancy_qa"
    ]

    identity_source_count = sum(
        1
        for item in observations
        if _queue_type(
            item,
            settings,
        )
        == "identity_label"
    )
    qa_source_count = sum(
        1
        for item in observations
        if _queue_type(
            item,
            settings,
        )
        == "occupancy_qa"
    )

    group_location_counts = Counter(
        (
            group.queue_type,
            group.location,
        )
        for group in groups
    )

    summary = {
        "schema_version": 1,
        "producer_version": settings.producer_version,
        "match_dir": str(
            match_dir
        ),
        "source_dataset_dir": str(
            source_dataset_dir
        ),
        "source_dataset_producer_version": (
            source_producer
        ),
        "source_summary_path": str(
            source_summary_path
        ),
        "source_manifest_path": str(
            source_manifest_path
        ),
        "source_sample_count": len(
            observations
        ),
        "source_identity_queue_sample_count": (
            identity_source_count
        ),
        "source_occupancy_qa_sample_count": (
            qa_source_count
        ),
        "skipped_tier_sample_count": (
            skipped_tier_count
        ),
        "visual_group_count": len(
            groups
        ),
        "identity_label_group_count": len(
            identity_groups
        ),
        "occupancy_qa_group_count": len(
            qa_groups
        ),
        "identity_temporal_reduction_ratio": (
            (
                1.0
                - len(
                    identity_groups
                )
                / identity_source_count
            )
            if identity_source_count
            else 0.0
        ),
        "occupancy_qa_temporal_reduction_ratio": (
            (
                1.0
                - len(
                    qa_groups
                )
                / qa_source_count
            )
            if qa_source_count
            else 0.0
        ),
        "mean_identity_group_size": (
            (
                identity_source_count
                / len(
                    identity_groups
                )
            )
            if identity_groups
            else 0.0
        ),
        "mean_occupancy_qa_group_size": (
            (
                qa_source_count
                / len(
                    qa_groups
                )
            )
            if qa_groups
            else 0.0
        ),
        "group_counts_by_queue_and_location": {
            queue: {
                location: count
                for (
                    q,
                    location,
                ), count in sorted(
                    group_location_counts.items()
                )
                if q == queue
            }
            for queue in (
                "identity_label",
                "occupancy_qa",
            )
        },
        "cross_tabs": {
            "tier_by_location": _cross_tab(
                observations,
                lambda item: (
                    item
                    .occupancy_evidence_tier
                ),
                lambda item: (
                    item.location
                ),
            ),
            "tier_by_stage": _cross_tab(
                observations,
                lambda item: (
                    item
                    .occupancy_evidence_tier
                ),
                lambda item: (
                    item.stage
                    or "unknown"
                ),
            ),
            "recommendation_by_location": _cross_tab(
                observations,
                _recommendation,
                lambda item: (
                    item.location
                ),
            ),
            "tracked_source_by_location": _cross_tab(
                observations,
                _tracked_source,
                lambda item: (
                    item.location
                ),
            ),
            "strong_snapshot_by_tier": _cross_tab(
                observations,
                _strong_snapshot,
                lambda item: (
                    item
                    .occupancy_evidence_tier
                ),
            ),
        },
        "split_policy": {
            "split_unit": "match_id",
            "random_crop_split_forbidden": True,
            "random_visual_group_split_across_same_match_forbidden": True,
            "reason": (
                "temporal observations from one match are correlated and "
                "must remain in the same ML split"
            ),
        },
        "classifier_feature_policy": {
            "pixels_only_for_visual_identity_model": True,
            "acquisition_priors_as_visual_classifier_input": False,
            "acquisition_priors_reserved_for_later_resolver": True,
        },
        "settings": {
            "max_temporal_gap_s": (
                settings.max_temporal_gap_s
            ),
            "dhash_size": (
                settings.dhash_size
            ),
            "max_dhash_distance": (
                settings.max_dhash_distance
            ),
            "split_on_stage_change": (
                settings.split_on_stage_change
            ),
            "identity_tiers": list(
                settings.identity_tiers
            ),
            "occupancy_qa_tiers": list(
                settings.occupancy_qa_tiers
            ),
        },
        "output_dir": str(
            output_dir
        ),
        "visual_groups_path": str(
            output_dir
            / "visual_groups.jsonl"
        ),
        "identity_label_queue_path": str(
            output_dir
            / "identity_label_queue.csv"
        ),
        "occupancy_qa_queue_path": str(
            output_dir
            / "occupancy_qa_queue.csv"
        ),
        "representatives_dir": str(
            output_dir
            / "representatives"
        ),
        "readme_path": str(
            output_dir
            / "README.md"
        ),
        "summary_path": str(
            output_dir
            / "summary.json"
        ),
    }

    summary_path_temp.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    output_dir.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temp_dir.replace(
        output_dir
    )

    return summary
