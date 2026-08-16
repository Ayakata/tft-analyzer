from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import shutil

from tft_analyzer.features.slot_identity_labeling.models import (
    LabeledSlotVisualGroup,
)

from .models import (
    SlotIdentityHumanAuditSettings,
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


def find_latest_identity_label_import(
    match_dir: Path | str,
) -> Path:
    labels_dir = (
        Path(match_dir)
        / "labels"
    )
    candidates = [
        path
        for path in labels_dir.glob(
            "slot-identity-label-importer-*"
        )
        if path.is_dir()
        and (
            path
            / "labeled_visual_groups.jsonl"
        ).is_file()
        and (
            path
            / "summary.json"
        ).is_file()
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No imported identity labels under {labels_dir}. "
            "Run `tft-analyzer import-identity-labels <match_dir>` first."
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


def _load_labeled_groups(
    path: Path,
) -> list[LabeledSlotVisualGroup]:
    values = []
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                values.append(
                    LabeledSlotVisualGroup.model_validate_json(
                        line
                    )
                )
    return values


def _cross_tab(
    values: list[LabeledSlotVisualGroup],
    row_value,
    column_value,
) -> dict[str, dict[str, int]]:
    table = defaultdict(Counter)

    for value in values:
        table[
            str(
                row_value(
                    value
                )
            )
        ][
            str(
                column_value(
                    value
                )
            )
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


def _slot_key(
    value: LabeledSlotVisualGroup,
) -> str:
    return (
        f"{value.location}:{value.slot_id}"
    )


def _training_tier(
    value: LabeledSlotVisualGroup,
    settings: SlotIdentityHumanAuditSettings,
) -> str | None:
    if (
        value.target_type
        != "champion"
        or not value.champion_label
        or not value.champion_catalog_validated
    ):
        return None

    tier = (
        value.representative_tier
    )
    if tier in settings.primary_evidence_tiers:
        return "primary"
    if tier in settings.secondary_evidence_tiers:
        return "secondary"
    if tier in settings.recovered_candidate_tiers:
        return "recovered_candidate"
    return None


def _write_champion_manifest(
    path: Path,
    values: list[LabeledSlotVisualGroup],
    *,
    allowed_tiers: set[str],
    settings: SlotIdentityHumanAuditSettings,
) -> int:
    selected = [
        value
        for value in values
        if (
            _training_tier(
                value,
                settings,
            )
            in allowed_tiers
        )
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
        )

        for value in selected:
            writer.writerow(
                [
                    value.visual_group_id,
                    value.match_id,
                    value.split_key,
                    _training_tier(
                        value,
                        settings,
                    ),
                    value.location,
                    value.slot_id,
                    value.representative_tier,
                    value.representative_tracked_source,
                    value.representative_crop_uri,
                    value.champion_label,
                    value.champion_id
                    or "",
                    value.member_count,
                ]
            )

    return len(
        selected
    )


def _write_no_unit_manifest(
    path: Path,
    values: list[LabeledSlotVisualGroup],
) -> int:
    selected = [
        value
        for value in values
        if value.target_type
        == "no_unit"
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
                "match_id",
                "split_key",
                "source_queue",
                "location",
                "slot_id",
                "representative_tier",
                "representative_tracked_source",
                "representative_crop_uri",
                "member_count",
            ]
        )

        for value in selected:
            writer.writerow(
                [
                    value.visual_group_id,
                    value.match_id,
                    value.split_key,
                    value.queue_type,
                    value.location,
                    value.slot_id,
                    value.representative_tier,
                    value.representative_tracked_source,
                    value.representative_crop_uri,
                    value.member_count,
                ]
            )

    return len(
        selected
    )


def _build_hotspots(
    values: list[LabeledSlotVisualGroup],
    settings: SlotIdentityHumanAuditSettings,
) -> list[dict[str, object]]:
    by_slot = defaultdict(
        list
    )
    for value in values:
        by_slot[
            (
                value.location,
                value.slot_id,
            )
        ].append(
            value
        )

    hotspots = []
    for (
        location,
        slot_id,
    ), rows in sorted(
        by_slot.items()
    ):
        labeled_count = len(
            rows
        )
        if (
            labeled_count
            < settings.hotspot_min_labeled_groups
        ):
            continue

        target_counts = Counter(
            row.target_type
            for row in rows
        )
        no_unit_count = target_counts[
            "no_unit"
        ]
        uncertain_count = target_counts[
            "uncertain"
        ]
        champion_count = target_counts[
            "champion"
        ]
        unusable_count = target_counts[
            "unusable"
        ]

        # Only slots with actual human occupancy/identity disagreement belong
        # in the hotspot list.
        if (
            no_unit_count == 0
            and uncertain_count == 0
        ):
            continue

        hotspots.append(
            {
                "location": location,
                "slot_id": slot_id,
                "labeled_group_count": (
                    labeled_count
                ),
                "champion_count": (
                    champion_count
                ),
                "no_unit_count": (
                    no_unit_count
                ),
                "uncertain_count": (
                    uncertain_count
                ),
                "unusable_count": (
                    unusable_count
                ),
                "no_unit_rate": (
                    no_unit_count
                    / labeled_count
                ),
                "non_champion_rate": (
                    (
                        no_unit_count
                        + uncertain_count
                        + unusable_count
                    )
                    / labeled_count
                ),
            }
        )

    hotspots.sort(
        key=lambda item: (
            -int(
                item[
                    "no_unit_count"
                ]
            ),
            -float(
                item[
                    "no_unit_rate"
                ]
            ),
            -int(
                item[
                    "uncertain_count"
                ]
            ),
            str(
                item[
                    "location"
                ]
            ),
            str(
                item[
                    "slot_id"
                ]
            ),
        )
    )
    return hotspots[
        : settings.hotspot_limit
    ]


def audit_identity_labels(
    match_dir: Path | str,
    settings: SlotIdentityHumanAuditSettings,
    *,
    label_import_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    force: bool = False,
) -> dict[str, object]:
    match_dir = Path(
        match_dir
    )
    label_import_dir = (
        Path(
            label_import_dir
        )
        if label_import_dir
        is not None
        else find_latest_identity_label_import(
            match_dir
        )
    )

    source_summary_path = (
        label_import_dir
        / "summary.json"
    )
    source_groups_path = (
        label_import_dir
        / "labeled_visual_groups.jsonl"
    )
    source_summary = _load_json(
        source_summary_path
    )
    values = _load_labeled_groups(
        source_groups_path
    )

    output_dir = (
        Path(
            output_dir
        )
        if output_dir
        is not None
        else (
            match_dir
            / "audits"
            / settings.producer_version
        )
    )

    if output_dir.exists():
        if not force:
            raise FileExistsError(
                f"Audit directory already exists: {output_dir}. "
                "Pass --force to regenerate it."
            )
        shutil.rmtree(
            output_dir
        )

    temp_dir = output_dir.with_name(
        output_dir.name
        + ".tmp"
    )
    if temp_dir.exists():
        shutil.rmtree(
            temp_dir
        )
    temp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    primary_path = (
        temp_dir
        / "visual_champion_primary_manifest.csv"
    )
    secondary_path = (
        temp_dir
        / "visual_champion_secondary_manifest.csv"
    )
    all_human_path = (
        temp_dir
        / "visual_champion_human_confirmed_manifest.csv"
    )
    no_unit_path = (
        temp_dir
        / "occupancy_hard_negative_manifest.csv"
    )

    primary_count = _write_champion_manifest(
        primary_path,
        values,
        allowed_tiers={
            "primary",
        },
        settings=settings,
    )
    secondary_count = _write_champion_manifest(
        secondary_path,
        values,
        allowed_tiers={
            "secondary",
        },
        settings=settings,
    )
    human_confirmed_count = _write_champion_manifest(
        all_human_path,
        values,
        allowed_tiers={
            "primary",
            "secondary",
            "recovered_candidate",
        },
        settings=settings,
    )
    no_unit_count = (
        _write_no_unit_manifest(
            no_unit_path,
            values,
        )
        if settings
        .export_all_human_no_unit_as_occupancy_hard_negative
        else 0
    )

    target_counts = Counter(
        value.target_type
        for value in values
    )

    training_tier_counts = Counter()
    champion_tier_counts = defaultdict(
        Counter
    )
    champion_location_counts = defaultdict(
        Counter
    )
    champion_match_ids = defaultdict(
        set
    )

    for value in values:
        tier = _training_tier(
            value,
            settings,
        )
        if tier:
            training_tier_counts[
                tier
            ] += 1

        if (
            value.target_type
            == "champion"
            and value.champion_label
        ):
            champion_location_counts[
                value.champion_label
            ][
                value.location
            ] += 1
            champion_match_ids[
                value.champion_label
            ].add(
                value.match_id
            )
            if tier:
                champion_tier_counts[
                    value.champion_label
                ][
                    tier
                ] += 1

    per_champion = {}
    for champion in sorted(
        champion_location_counts
    ):
        tier_counts = (
            champion_tier_counts[
                champion
            ]
        )
        locations = (
            champion_location_counts[
                champion
            ]
        )

        all_groups = [
            value
            for value in values
            if (
                value.target_type
                == "champion"
                and value.champion_label
                == champion
            )
        ]

        per_champion[
            champion
        ] = {
            "human_confirmed_group_count": len(
                all_groups
            ),
            "primary_group_count": (
                tier_counts[
                    "primary"
                ]
            ),
            "secondary_group_count": (
                tier_counts[
                    "secondary"
                ]
            ),
            "recovered_candidate_group_count": (
                tier_counts[
                    "recovered_candidate"
                ]
            ),
            "match_count": len(
                champion_match_ids[
                    champion
                ]
            ),
            "locations": dict(
                sorted(
                    locations.items()
                )
            ),
        }

    hotspots = _build_hotspots(
        values,
        settings,
    )

    cross_tabs = {
        "target_by_location": _cross_tab(
            values,
            lambda value: (
                value.target_type
            ),
            lambda value: (
                value.location
            ),
        ),
        "target_by_representative_tier": _cross_tab(
            values,
            lambda value: (
                value.target_type
            ),
            lambda value: (
                value.representative_tier
            ),
        ),
        "target_by_tracker_source": _cross_tab(
            values,
            lambda value: (
                value.target_type
            ),
            lambda value: (
                value.representative_tracked_source
            ),
        ),
        "target_by_slot": _cross_tab(
            values,
            lambda value: (
                value.target_type
            ),
            _slot_key,
        ),
        "champion_by_training_tier": {
            champion: dict(
                sorted(
                    counts.items()
                )
            )
            for champion, counts in sorted(
                champion_tier_counts.items()
            )
        },
        "champion_by_location": {
            champion: dict(
                sorted(
                    counts.items()
                )
            )
            for champion, counts in sorted(
                champion_location_counts.items()
            )
        },
    }

    summary = {
        "schema_version": 1,
        "producer_version": (
            settings.producer_version
        ),
        "match_dir": str(
            match_dir
        ),
        "source_label_import_dir": str(
            label_import_dir
        ),
        "source_importer_version": (
            source_summary.get(
                "producer_version"
            )
        ),
        "source_labeled_group_count": len(
            values
        ),
        "source_unlabeled_group_count": (
            source_summary.get(
                "unlabeled_group_count",
                0,
            )
        ),
        "target_type_counts": dict(
            sorted(
                target_counts.items()
            )
        ),
        "training_policy": {
            "primary": (
                "human champion + catalog validated + representative tier trusted"
            ),
            "secondary": (
                "human champion + catalog validated + representative tier supported"
            ),
            "recovered_candidate": (
                "human champion + catalog validated + representative tier raw_candidate"
            ),
            "uncertain": (
                "excluded from supervised champion training"
            ),
            "unusable": (
                "excluded from supervised champion training"
            ),
            "human_no_unit": (
                "explicit occupancy QA/hard-negative evidence; never champion training"
            ),
        },
        "primary_group_count": (
            primary_count
        ),
        "secondary_group_count": (
            secondary_count
        ),
        "recovered_candidate_group_count": (
            training_tier_counts[
                "recovered_candidate"
            ]
        ),
        "human_confirmed_champion_manifest_group_count": (
            human_confirmed_count
        ),
        "occupancy_hard_negative_group_count": (
            no_unit_count
        ),
        "training_tier_counts": dict(
            sorted(
                training_tier_counts.items()
            )
        ),
        "cross_tabs": (
            cross_tabs
        ),
        "occupancy_false_positive_hotspots": (
            hotspots
        ),
        "per_champion": (
            per_champion
        ),
        "split_policy": {
            "split_unit": "match_id",
            "current_match_count": len(
                {
                    value.match_id
                    for value in values
                }
            ),
            "random_crop_split_forbidden": True,
            "random_visual_group_split_across_same_match_forbidden": True,
        },
        "classifier_feature_policy": {
            "pixels_only_for_visual_identity_model": True,
            "acquisition_priors_as_visual_classifier_input": False,
            "occupancy_evidence_tier_as_visual_classifier_input": False,
            "occupancy_evidence_tier_is_provenance_only": True,
        },
        "settings": {
            "primary_evidence_tiers": list(
                settings.primary_evidence_tiers
            ),
            "secondary_evidence_tiers": list(
                settings.secondary_evidence_tiers
            ),
            "recovered_candidate_tiers": list(
                settings.recovered_candidate_tiers
            ),
            "export_all_human_no_unit_as_occupancy_hard_negative": (
                settings
                .export_all_human_no_unit_as_occupancy_hard_negative
            ),
            "hotspot_min_labeled_groups": (
                settings.hotspot_min_labeled_groups
            ),
            "hotspot_limit": (
                settings.hotspot_limit
            ),
        },
        "output_dir": str(
            output_dir
        ),
        "primary_manifest_path": str(
            output_dir
            / "visual_champion_primary_manifest.csv"
        ),
        "secondary_manifest_path": str(
            output_dir
            / "visual_champion_secondary_manifest.csv"
        ),
        "human_confirmed_manifest_path": str(
            output_dir
            / "visual_champion_human_confirmed_manifest.csv"
        ),
        "occupancy_hard_negative_manifest_path": str(
            output_dir
            / "occupancy_hard_negative_manifest.csv"
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

    (
        temp_dir
        / "README.md"
    ).write_text(
        """# Human identity-label audit

This artifact does not alter human labels or upstream perception.

Policy:

- primary: human-confirmed champion + trusted occupancy provenance
- secondary: human-confirmed champion + supported occupancy provenance
- recovered_candidate: human-confirmed champion + raw-candidate provenance
- no_unit: explicit occupancy QA/hard-negative evidence
- uncertain/unusable: excluded from supervised champion training

The future visual identity model must not consume occupancy tier, tracker
source, acquisition priors or other semantic resolver features as inputs.

Train/validation/test split unit remains match_id.
""",
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
