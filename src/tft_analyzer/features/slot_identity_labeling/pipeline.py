from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import shutil
import time

from tft_analyzer.features.slot_identity_curation.models import (
    CuratedSlotVisualGroup,
)
from tft_analyzer.game_data import (
    load_champion_cost_catalog,
    load_game_context,
    normalize_champion_name,
)

from .models import (
    IdentityLabelAssignment,
    LabeledSlotVisualGroup,
    SlotIdentityLabelingSettings,
)


def _replace_directory_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int = 8,
    initial_delay_s: float = 0.05,
) -> None:
    """Publish a generated directory despite brief Windows file locks."""
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


def find_latest_slot_identity_curation(
    match_dir: Path | str,
) -> Path:
    datasets_dir = (
        Path(match_dir)
        / "datasets"
    )
    candidates = [
        path
        for path in datasets_dir.glob(
            "slot-identity-curator-*"
        )
        if path.is_dir()
        and (path / "summary.json").is_file()
        and (path / "visual_groups.jsonl").is_file()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No slot-identity curation under {datasets_dir}. "
            "Run `tft-analyzer curate-slot-identity-dataset <match_dir>` first."
        )
    return max(
        candidates,
        key=_version_key,
    )


def find_latest_identity_label_package(
    match_dir: Path | str,
) -> Path:
    labeling_dir = (
        Path(match_dir)
        / "labeling"
    )
    candidates = [
        path
        for path in labeling_dir.glob(
            "slot-identity-label-package-*"
        )
        if path.is_dir()
        and (path / "package.json").is_file()
        and (path / "labels.csv").is_file()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No identity-label package under {labeling_dir}. "
            "Run `tft-analyzer prepare-identity-labeling <match_dir>` first."
        )
    return max(
        candidates,
        key=_version_key,
    )


def _load_json(
    path: Path,
):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def _load_groups(
    path: Path,
) -> list[CuratedSlotVisualGroup]:
    values = []
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                values.append(
                    CuratedSlotVisualGroup.model_validate_json(
                        line
                    )
                )
    return values


def _copy_group_image(
    *,
    curation_dir: Path,
    package_temp_dir: Path,
    group: CuratedSlotVisualGroup,
) -> str:
    src = (
        curation_dir
        / group.representative_crop_uri
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
        Path("images")
        / group.queue_type
        / f"{group.visual_group_id}{suffix}"
    )
    dst = (
        package_temp_dir
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


def _resolve_game_context(
    match_dir: Path,
    curation_summary: dict,
) -> dict[str, object]:
    context = load_game_context(
        match_dir
    )
    if context is not None:
        return context.model_dump(
            mode="json"
        )

    source_dataset_dir = Path(
        curation_summary[
            "source_dataset_dir"
        ]
    )
    source_summary_path = (
        source_dataset_dir
        / "summary.json"
    )
    if source_summary_path.is_file():
        source_summary = _load_json(
            source_summary_path
        )
        game_context = (
            source_summary.get(
                "game_context"
            )
            or {}
        )
        if game_context:
            return dict(
                game_context
            )

    return {}


def _catalog_schema(
    *,
    catalog_path: Path | None,
    set_id: str | None,
) -> dict[str, object]:
    if catalog_path is None:
        return {
            "catalog_available": False,
            "set_id": set_id,
            "champion_labels": [],
        }

    catalog = load_champion_cost_catalog(
        catalog_path
    )
    entries = (
        catalog.entries_for_set(
            set_id
        )
        if set_id
        else ()
    )

    labels = sorted(
        {
            entry.normalized_name
            for entry in entries
            if entry.normalized_name
        }
    )

    return {
        "catalog_available": True,
        "catalog_path": str(
            catalog_path
        ),
        "provider": (
            catalog.snapshot.provider
        ),
        "version": (
            catalog.snapshot.version
        ),
        "locale": (
            catalog.snapshot.locale
        ),
        "source_sha256": (
            catalog.snapshot.source_sha256
        ),
        "set_id": set_id,
        "champion_count": len(
            labels
        ),
        "champion_labels": labels,
    }


def _write_labels_csv(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    fields = [
        "visual_group_id",
        "image_uri",
        "queue_type",
        "match_id",
        "location",
        "slot_id",
        "stage_start",
        "stage_end",
        "start_timestamp_s",
        "end_timestamp_s",
        "member_count",
        "representative_tier",
        "representative_tracked_source",
        "recommended_for_identity_training_after_label",
        "target_type",
        "champion_label",
        "label_status",
        "annotator",
        "notes",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                row
            )


def _write_package_readme(
    path: Path,
    *,
    producer_version: str,
    champion_count: int,
) -> None:
    path.write_text(
        f"""# TFT Identity Label Package

Producer: `{producer_version}`

This package is self-contained. Representative images are copied under
`images/identity_label/` and `images/occupancy_qa/`.

Edit `labels.csv` only in these columns:

```text
target_type
champion_label
label_status
annotator
notes
```

Allowed target types:

```text
champion
no_unit
uncertain
unusable
```

Rules:

```text
champion -> champion_label is required
no_unit / uncertain / unusable -> champion_label must be empty
```

The pinned set catalog currently exposes {champion_count} normalized champion
labels in `label_schema.json`.

For a first pass:

- `identity_label` rows normally become `champion`, `uncertain` or `unusable`;
- `occupancy_qa` rows may become `no_unit`, `champion`, `uncertain` or
  `unusable`.

A `champion` found in the occupancy-QA queue is valid: it means the earlier
occupancy evidence was conservative/wrong. A `no_unit` label found in the
identity queue is retained as a quality conflict and is not silently used as a
negative-training example.

## CVAT bridge

`cvat_image_manifest.csv` maps each flat image filename to `visual_group_id`.
The package can therefore be uploaded to an external image-annotation UI such
as CVAT while keeping this project JSONL/CSV as canonical truth.

0.21.3 does not define or depend on a native CVAT annotation-export format.
After annotation, copy the labels back into `labels.csv` and run:

```text
tft-analyzer import-identity-labels <match_dir>
```

Incremental/partial imports are supported by default.
""",
        encoding="utf-8",
    )


def prepare_identity_label_package(
    match_dir: Path | str,
    settings: SlotIdentityLabelingSettings,
    *,
    curation_dir: Path | str | None = None,
    catalog_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    force: bool = False,
) -> dict[str, object]:
    match_dir = Path(
        match_dir
    )
    curation_dir = (
        Path(
            curation_dir
        )
        if curation_dir
        is not None
        else find_latest_slot_identity_curation(
            match_dir
        )
    )

    curation_summary_path = (
        curation_dir
        / "summary.json"
    )
    groups_path = (
        curation_dir
        / "visual_groups.jsonl"
    )
    curation_summary = _load_json(
        curation_summary_path
    )
    groups = _load_groups(
        groups_path
    )

    game_context = _resolve_game_context(
        match_dir,
        curation_summary,
    )
    set_id = (
        game_context.get(
            "set_id"
        )
        if game_context
        else None
    )

    catalog_path = (
        Path(
            catalog_path
        )
        if catalog_path
        is not None
        else None
    )
    schema = _catalog_schema(
        catalog_path=catalog_path,
        set_id=(
            str(set_id)
            if set_id
            else None
        ),
    )

    output_dir = (
        Path(
            output_dir
        )
        if output_dir
        is not None
        else (
            match_dir
            / "labeling"
            / settings.package_producer_version
        )
    )

    if output_dir.exists():
        if not force:
            raise FileExistsError(
                f"Label package already exists: {output_dir}. "
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

    rows = []
    cvat_rows = []
    queue_counts = Counter()
    tier_counts = Counter()

    for group in groups:
        image_uri = _copy_group_image(
            curation_dir=curation_dir,
            package_temp_dir=temp_dir,
            group=group,
        )
        queue_counts[
            group.queue_type
        ] += 1
        tier_counts[
            group.representative_tier
        ] += 1

        rows.append(
            {
                "visual_group_id": (
                    group.visual_group_id
                ),
                "image_uri": image_uri,
                "queue_type": (
                    group.queue_type
                ),
                "match_id": (
                    group.match_id
                ),
                "location": (
                    group.location
                ),
                "slot_id": (
                    group.slot_id
                ),
                "stage_start": (
                    group.stage_start
                    or ""
                ),
                "stage_end": (
                    group.stage_end
                    or ""
                ),
                "start_timestamp_s": (
                    f"{group.start_timestamp_s:.3f}"
                ),
                "end_timestamp_s": (
                    f"{group.end_timestamp_s:.3f}"
                ),
                "member_count": (
                    group.member_count
                ),
                "representative_tier": (
                    group.representative_tier
                ),
                "representative_tracked_source": (
                    group.representative_tracked_source
                ),
                "recommended_for_identity_training_after_label": str(
                    group.recommended_for_identity_training_after_label
                ).lower(),
                "target_type": "",
                "champion_label": "",
                "label_status": "",
                "annotator": "",
                "notes": "",
            }
        )

        cvat_rows.append(
            {
                "image_filename": (
                    Path(
                        image_uri
                    ).name
                ),
                "visual_group_id": (
                    group.visual_group_id
                ),
                "queue_type": (
                    group.queue_type
                ),
                "location": (
                    group.location
                ),
                "slot_id": (
                    group.slot_id
                ),
            }
        )

    labels_path = (
        temp_dir
        / "labels.csv"
    )
    _write_labels_csv(
        labels_path,
        rows,
    )

    cvat_manifest_path = (
        temp_dir
        / "cvat_image_manifest.csv"
    )
    with cvat_manifest_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "image_filename",
                "visual_group_id",
                "queue_type",
                "location",
                "slot_id",
            ],
        )
        writer.writeheader()
        writer.writerows(
            cvat_rows
        )

    schema_path = (
        temp_dir
        / "label_schema.json"
    )
    schema_payload = {
        "schema_version": 1,
        "target_types": [
            "champion",
            "no_unit",
            "uncertain",
            "unusable",
        ],
        "champion_label_semantics": (
            "normalized TFT set champion name"
        ),
        "game_context": game_context,
        "champion_catalog": schema,
        "canonical_truth": (
            "project importer output; external annotation tools are UI only"
        ),
    }
    schema_path.write_text(
        json.dumps(
            schema_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _write_package_readme(
        temp_dir
        / "README.md",
        producer_version=(
            settings.package_producer_version
        ),
        champion_count=int(
            schema.get(
                "champion_count",
                0,
            )
            or 0
        ),
    )

    package_path_temp = (
        temp_dir
        / "package.json"
    )
    package = {
        "schema_version": 1,
        "producer_version": (
            settings.package_producer_version
        ),
        "match_dir": str(
            match_dir
        ),
        "source_curation_dir": str(
            curation_dir
        ),
        "source_curation_producer_version": (
            curation_summary.get(
                "producer_version"
            )
        ),
        "source_visual_groups_path": str(
            groups_path
        ),
        "visual_group_count": len(
            groups
        ),
        "queue_type_counts": dict(
            sorted(
                queue_counts.items()
            )
        ),
        "representative_tier_counts": dict(
            sorted(
                tier_counts.items()
            )
        ),
        "game_context": (
            game_context
        ),
        "catalog_available": bool(
            schema.get(
                "catalog_available"
            )
        ),
        "catalog_champion_count": int(
            schema.get(
                "champion_count",
                0,
            )
            or 0
        ),
        "output_dir": str(
            output_dir
        ),
        "labels_path": str(
            output_dir
            / "labels.csv"
        ),
        "label_schema_path": str(
            output_dir
            / "label_schema.json"
        ),
        "cvat_image_manifest_path": str(
            output_dir
            / "cvat_image_manifest.csv"
        ),
        "images_dir": str(
            output_dir
            / "images"
        ),
        "package_path": str(
            output_dir
            / "package.json"
        ),
    }
    package_path_temp.write_text(
        json.dumps(
            package,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    output_dir.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    _replace_directory_with_retry(
        temp_dir,
        output_dir,
    )
    return package


def _read_label_assignments(
    path: Path,
) -> tuple[
    dict[str, IdentityLabelAssignment],
    int,
]:
    assignments = {}
    blank_count = 0

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(
            f
        )
        required = {
            "visual_group_id",
            "target_type",
            "champion_label",
        }
        missing = (
            required
            - set(
                reader.fieldnames
                or ()
            )
        )
        if missing:
            raise ValueError(
                "Labels CSV is missing required columns: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        for row_number, row in enumerate(
            reader,
            start=2,
        ):
            group_id = str(
                row.get(
                    "visual_group_id",
                    "",
                )
            ).strip()
            if not group_id:
                raise ValueError(
                    f"Row {row_number}: empty visual_group_id"
                )

            target_type = str(
                row.get(
                    "target_type",
                    "",
                )
            ).strip()
            champion_label = str(
                row.get(
                    "champion_label",
                    "",
                )
            ).strip()

            if not target_type:
                if champion_label:
                    raise ValueError(
                        f"Row {row_number}: champion_label is set "
                        "but target_type is empty"
                    )
                blank_count += 1
                continue

            if group_id in assignments:
                raise ValueError(
                    f"Duplicate label for visual_group_id={group_id}"
                )

            label_status = str(
                row.get(
                    "label_status",
                    "",
                )
            ).strip() or "human_labeled"

            assignments[
                group_id
            ] = IdentityLabelAssignment(
                visual_group_id=group_id,
                target_type=target_type,
                champion_label=(
                    champion_label
                    or None
                ),
                label_status=label_status,
                annotator=(
                    str(
                        row.get(
                            "annotator",
                            "",
                        )
                    ).strip()
                    or None
                ),
                notes=(
                    str(
                        row.get(
                            "notes",
                            "",
                        )
                    ).strip()
                    or None
                ),
            )

    return assignments, blank_count


def _champion_catalog_index(
    *,
    catalog_path: Path | None,
    set_id: str | None,
) -> tuple[
    dict[str, object],
    dict[str, list],
]:
    if catalog_path is None:
        return {}, {}

    catalog = load_champion_cost_catalog(
        catalog_path
    )
    entries = (
        catalog.entries_for_set(
            set_id
        )
        if set_id
        else ()
    )
    by_normalized = defaultdict(
        list
    )
    for entry in entries:
        if entry.normalized_name:
            by_normalized[
                entry.normalized_name
            ].append(
                entry
            )

    metadata = {
        "provider": (
            catalog.snapshot.provider
        ),
        "version": (
            catalog.snapshot.version
        ),
        "locale": (
            catalog.snapshot.locale
        ),
        "source_sha256": (
            catalog.snapshot.source_sha256
        ),
        "set_id": (
            set_id
        ),
        "scoped_champion_count": (
            len(
                entries
            )
        ),
    }
    return (
        metadata,
        dict(
            by_normalized
        ),
    )


def _primary_catalog_candidate(
    candidates: list,
):
    if len(candidates) == 1:
        return candidates[0]

    # Data Dragon may publish a technical TraitClone beside the playable
    # champion with the same set, display name, tier and art. Human labels
    # describe the champion, so resolve that duplicate to the playable entry.
    playable = [
        entry
        for entry in candidates
        if not entry.champion_id.casefold().endswith(
            "_traitclone"
        )
    ]
    if len(playable) == 1:
        return playable[0]
    return None


def _write_labeled_jsonl(
    path: Path,
    values: list[LabeledSlotVisualGroup],
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


def _write_training_manifest(
    path: Path,
    values: list[LabeledSlotVisualGroup],
) -> None:
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
                "match_id",
                "split_key",
                "location",
                "representative_crop_uri",
                "champion_label",
                "champion_id",
                "member_count",
            ]
        )
        for value in values:
            if not (
                value
                .eligible_visual_champion_training_group
            ):
                continue
            writer.writerow(
                [
                    value.visual_group_id,
                    value.match_id,
                    value.split_key,
                    value.location,
                    value.representative_crop_uri,
                    value.champion_label,
                    value.champion_id
                    or "",
                    value.member_count,
                ]
            )


def _write_negative_manifest(
    path: Path,
    values: list[LabeledSlotVisualGroup],
) -> None:
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
                "match_id",
                "split_key",
                "location",
                "representative_crop_uri",
                "member_count",
            ]
        )
        for value in values:
            if not (
                value
                .eligible_occupancy_negative_group
            ):
                continue
            writer.writerow(
                [
                    value.visual_group_id,
                    value.match_id,
                    value.split_key,
                    value.location,
                    value.representative_crop_uri,
                    value.member_count,
                ]
            )


def import_identity_labels(
    match_dir: Path | str,
    settings: SlotIdentityLabelingSettings,
    *,
    labels_path: Path | str | None = None,
    label_package_dir: Path | str | None = None,
    curation_dir: Path | str | None = None,
    catalog_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    require_complete: bool = False,
    require_complete_queue: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    match_dir = Path(
        match_dir
    )

    package_dir = (
        Path(
            label_package_dir
        )
        if label_package_dir
        is not None
        else find_latest_identity_label_package(
            match_dir
        )
    )
    package = _load_json(
        package_dir
        / "package.json"
    )

    labels_path = (
        Path(
            labels_path
        )
        if labels_path
        is not None
        else (
            package_dir
            / "labels.csv"
        )
    )

    curation_dir = (
        Path(
            curation_dir
        )
        if curation_dir
        is not None
        else Path(
            package[
                "source_curation_dir"
            ]
        )
    )
    curation_summary = _load_json(
        curation_dir
        / "summary.json"
    )
    groups_path = (
        curation_dir
        / "visual_groups.jsonl"
    )
    groups = _load_groups(
        groups_path
    )
    groups_by_id = {
        group.visual_group_id: group
        for group in groups
    }

    assignments, blank_row_count = (
        _read_label_assignments(
            labels_path
        )
    )

    unknown_group_ids = sorted(
        set(
            assignments
        )
        - set(
            groups_by_id
        )
    )
    if unknown_group_ids:
        raise ValueError(
            "Labels reference unknown visual_group_id values: "
            + ", ".join(
                unknown_group_ids[
                    :8
                ]
            )
        )

    unlabeled_group_ids = sorted(
        set(
            groups_by_id
        )
        - set(
            assignments
        )
    )
    effective_require_complete = bool(
        require_complete
        or not settings.allow_partial_import
    )
    if (
        effective_require_complete
        and unlabeled_group_ids
    ):
        raise ValueError(
            f"Label import is incomplete: "
            f"{len(unlabeled_group_ids)} visual groups remain unlabeled."
        )

    if require_complete_queue is not None:
        allowed_queues = {
            "identity_label",
            "occupancy_qa",
        }
        if require_complete_queue not in allowed_queues:
            raise ValueError(
                "require_complete_queue must be one of: "
                + ", ".join(sorted(allowed_queues))
            )

        queue_group_ids = {
            group.visual_group_id
            for group in groups
            if group.queue_type
            == require_complete_queue
        }
        queue_unlabeled = sorted(
            queue_group_ids
            - set(assignments)
        )
        if queue_unlabeled:
            raise ValueError(
                f"Label queue {require_complete_queue!r} is incomplete: "
                f"{len(queue_unlabeled)} visual groups remain unlabeled."
            )

    game_context = _resolve_game_context(
        match_dir,
        curation_summary,
    )
    set_id = (
        str(
            game_context.get(
                "set_id"
            )
        )
        if game_context.get(
            "set_id"
        )
        else None
    )

    catalog_path = (
        Path(
            catalog_path
        )
        if catalog_path
        is not None
        else None
    )
    (
        catalog_metadata,
        catalog_by_normalized,
    ) = _champion_catalog_index(
        catalog_path=catalog_path,
        set_id=set_id,
    )

    has_champion_labels = any(
        assignment.target_type
        == "champion"
        for assignment in assignments.values()
    )
    if (
        has_champion_labels
        and settings.require_catalog_for_champion_labels
        and not catalog_by_normalized
    ):
        raise ValueError(
            "Champion labels require a pinned champion catalog for validation. "
            "Pass --game-data-catalog or enable the active catalog."
        )

    labeled = []
    catalog_error_ids = []
    identity_queue_no_unit_conflicts = 0

    for group in sorted(
        groups,
        key=lambda item: (
            item.start_timestamp_s,
            item.location,
            item.slot_id,
            item.visual_group_id,
        ),
    ):
        assignment = assignments.get(
            group.visual_group_id
        )
        if assignment is None:
            continue

        champion_label = None
        champion_normalized = None
        champion_id = None
        catalog_validated = False

        if (
            assignment.target_type
            == "champion"
        ):
            normalized = normalize_champion_name(
                assignment.champion_label
                or ""
            )
            candidates = (
                catalog_by_normalized.get(
                    normalized,
                    []
                )
            )
            if catalog_by_normalized:
                entry = _primary_catalog_candidate(
                    candidates
                )
                if entry is None:
                    catalog_error_ids.append(
                        group.visual_group_id
                    )
                    continue
                champion_label = (
                    entry.normalized_name
                )
                champion_normalized = (
                    entry.normalized_name
                )
                champion_id = (
                    entry.champion_id
                )
                catalog_validated = True
            else:
                champion_label = normalized
                champion_normalized = normalized
        else:
            champion_label = None
            champion_normalized = None

        training_eligible = bool(
            assignment.target_type
            == "champion"
            and group
            .recommended_for_identity_training_after_label
            and (
                catalog_validated
                or not settings
                .require_catalog_for_champion_labels
            )
        )

        negative_eligible = bool(
            assignment.target_type
            == "no_unit"
            and group.queue_type
            == "occupancy_qa"
        )

        if (
            assignment.target_type
            == "no_unit"
            and group.queue_type
            == "identity_label"
        ):
            identity_queue_no_unit_conflicts += 1

        labeled.append(
            LabeledSlotVisualGroup(
                visual_group_id=(
                    group.visual_group_id
                ),
                match_id=(
                    group.match_id
                ),
                queue_type=(
                    group.queue_type
                ),
                location=(
                    group.location
                ),
                slot_id=(
                    group.slot_id
                ),
                stage_start=(
                    group.stage_start
                ),
                stage_end=(
                    group.stage_end
                ),
                start_timestamp_s=(
                    group.start_timestamp_s
                ),
                end_timestamp_s=(
                    group.end_timestamp_s
                ),
                member_count=(
                    group.member_count
                ),
                representative_crop_uri=(
                    group.representative_crop_uri
                ),
                representative_tier=(
                    group.representative_tier
                ),
                representative_tracked_source=(
                    group.representative_tracked_source
                ),
                recommended_for_identity_training_after_label=(
                    group
                    .recommended_for_identity_training_after_label
                ),
                target_type=(
                    assignment.target_type
                ),
                champion_label=(
                    champion_label
                ),
                champion_normalized_name=(
                    champion_normalized
                ),
                champion_id=(
                    champion_id
                ),
                champion_catalog_validated=(
                    catalog_validated
                ),
                label_status=(
                    assignment.label_status
                ),
                annotator=(
                    assignment.annotator
                ),
                notes=(
                    assignment.notes
                ),
                eligible_visual_champion_training_group=(
                    training_eligible
                ),
                eligible_occupancy_negative_group=(
                    negative_eligible
                ),
                split_key=(
                    group.split_key
                ),
                source_curation_producer_version=(
                    curation_summary.get(
                        "producer_version",
                        "",
                    )
                ),
                source_visual_groups_path=str(
                    groups_path
                ),
                producer_version=(
                    settings
                    .import_producer_version
                ),
            )
        )

    if catalog_error_ids:
        raise ValueError(
            "Champion labels failed exact pinned-set catalog validation for "
            f"{len(catalog_error_ids)} visual groups; first: "
            + ", ".join(
                catalog_error_ids[
                    :8
                ]
            )
        )

    output_dir = (
        Path(
            output_dir
        )
        if output_dir
        is not None
        else (
            match_dir
            / "labels"
            / settings.import_producer_version
        )
    )
    if output_dir.exists():
        if not force:
            raise FileExistsError(
                f"Label import directory already exists: {output_dir}. "
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

    labeled_path = (
        temp_dir
        / "labeled_visual_groups.jsonl"
    )
    training_path = (
        temp_dir
        / "visual_champion_training_manifest.csv"
    )
    negatives_path = (
        temp_dir
        / "occupancy_negative_manifest.csv"
    )

    _write_labeled_jsonl(
        labeled_path,
        labeled,
    )
    _write_training_manifest(
        training_path,
        labeled,
    )
    _write_negative_manifest(
        negatives_path,
        labeled,
    )

    target_counts = Counter(
        value.target_type
        for value in labeled
    )
    queue_labeled_counts = Counter(
        value.queue_type
        for value in labeled
    )
    location_labeled_counts = Counter(
        value.location
        for value in labeled
    )

    champion_group_counts = Counter()
    champion_member_sample_counts = Counter()
    champion_training_group_counts = Counter()
    champion_location_counts = defaultdict(
        Counter
    )
    champion_matches = defaultdict(
        set
    )

    for value in labeled:
        if (
            value.target_type
            != "champion"
            or not value.champion_label
        ):
            continue

        champion_group_counts[
            value.champion_label
        ] += 1
        champion_member_sample_counts[
            value.champion_label
        ] += (
            value.member_count
        )
        champion_location_counts[
            value.champion_label
        ][
            value.location
        ] += 1
        champion_matches[
            value.champion_label
        ].add(
            value.match_id
        )

        if (
            value
            .eligible_visual_champion_training_group
        ):
            champion_training_group_counts[
                value.champion_label
            ] += 1

    per_champion = {}
    for champion in sorted(
        champion_group_counts
    ):
        per_champion[
            champion
        ] = {
            "visual_group_count": (
                champion_group_counts[
                    champion
                ]
            ),
            "member_sample_count": (
                champion_member_sample_counts[
                    champion
                ]
            ),
            "training_eligible_group_count": (
                champion_training_group_counts[
                    champion
                ]
            ),
            "match_count": len(
                champion_matches[
                    champion
                ]
            ),
            "locations": dict(
                sorted(
                    champion_location_counts[
                        champion
                    ].items()
                )
            ),
        }

    champion_classes_by_location = {
        location: sorted(
            {
                value.champion_label
                for value in labeled
                if (
                    value.location
                    == location
                    and value.target_type
                    == "champion"
                    and value.champion_label
                )
            }
        )
        for location in (
            "board",
            "bench",
        )
    }

    training_eligible_count = sum(
        value
        .eligible_visual_champion_training_group
        for value in labeled
    )
    occupancy_negative_count = sum(
        value
        .eligible_occupancy_negative_group
        for value in labeled
    )

    summary = {
        "schema_version": 1,
        "producer_version": (
            settings.import_producer_version
        ),
        "match_dir": str(
            match_dir
        ),
        "source_label_package_dir": str(
            package_dir
        ),
        "source_labels_path": str(
            labels_path
        ),
        "source_curation_dir": str(
            curation_dir
        ),
        "source_curation_producer_version": (
            curation_summary.get(
                "producer_version"
            )
        ),
        "source_visual_group_count": len(
            groups
        ),
        "labeled_group_count": len(
            labeled
        ),
        "unlabeled_group_count": (
            len(
                groups
            )
            - len(
                labeled
            )
        ),
        "blank_label_row_count": (
            blank_row_count
        ),
        "require_complete": (
            effective_require_complete
        ),
        "require_complete_queue": (
            require_complete_queue
        ),
        "target_type_counts": dict(
            sorted(
                target_counts.items()
            )
        ),
        "queue_labeled_counts": dict(
            sorted(
                queue_labeled_counts.items()
            )
        ),
        "location_labeled_counts": dict(
            sorted(
                location_labeled_counts.items()
            )
        ),
        "identity_label_queue_total": sum(
            group.queue_type
            == "identity_label"
            for group in groups
        ),
        "occupancy_qa_queue_total": sum(
            group.queue_type
            == "occupancy_qa"
            for group in groups
        ),
        "identity_label_queue_labeled": (
            queue_labeled_counts[
                "identity_label"
            ]
        ),
        "occupancy_qa_queue_labeled": (
            queue_labeled_counts[
                "occupancy_qa"
            ]
        ),
        "identity_label_queue_coverage": (
            queue_labeled_counts[
                "identity_label"
            ]
            / max(
                1,
                sum(
                    group.queue_type
                    == "identity_label"
                    for group in groups
                ),
            )
        ),
        "occupancy_qa_queue_coverage": (
            queue_labeled_counts[
                "occupancy_qa"
            ]
            / max(
                1,
                sum(
                    group.queue_type
                    == "occupancy_qa"
                    for group in groups
                ),
            )
        ),
        "champion_class_count": len(
            champion_group_counts
        ),
        "champion_group_count": sum(
            champion_group_counts.values()
        ),
        "visual_champion_training_eligible_group_count": (
            training_eligible_count
        ),
        "occupancy_negative_eligible_group_count": (
            occupancy_negative_count
        ),
        "identity_queue_no_unit_conflict_count": (
            identity_queue_no_unit_conflicts
        ),
        "champion_classes_by_location": (
            champion_classes_by_location
        ),
        "per_champion": (
            per_champion
        ),
        "game_context": (
            game_context
        ),
        "champion_catalog": (
            catalog_metadata
        ),
        "split_policy": {
            "split_unit": "match_id",
            "current_match_count": len(
                {
                    group.match_id
                    for group in groups
                }
            ),
            "random_crop_split_forbidden": True,
            "random_visual_group_split_across_same_match_forbidden": True,
        },
        "classifier_feature_policy": {
            "pixels_only_for_visual_identity_model": True,
            "acquisition_priors_as_visual_classifier_input": False,
        },
        "output_dir": str(
            output_dir
        ),
        "labeled_visual_groups_path": str(
            output_dir
            / "labeled_visual_groups.jsonl"
        ),
        "visual_champion_training_manifest_path": str(
            output_dir
            / "visual_champion_training_manifest.csv"
        ),
        "occupancy_negative_manifest_path": str(
            output_dir
            / "occupancy_negative_manifest.csv"
        ),
        "summary_path": str(
            output_dir
            / "summary.json"
        ),
    }

    (
        temp_dir
        / "summary.json"
    ).write_text(
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
    _replace_directory_with_retry(
        temp_dir,
        output_dir,
    )

    return summary
