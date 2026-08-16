from __future__ import annotations

from pathlib import Path

from .models import CuratedSlotVisualGroup


def _iter(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                yield CuratedSlotVisualGroup.model_validate_json(
                    line
                )


def format_slot_identity_curation_timeline(
    groups_path: Path | str,
    *,
    limit: int | None = 80,
    queue_type: str | None = None,
) -> str:
    values = list(
        _iter(
            groups_path
        )
    )

    if queue_type:
        values = [
            value
            for value in values
            if value.queue_type
            == queue_type
        ]

    if limit is not None:
        values = values[:limit]

    lines = [
        " # start-end(s) stage loc slot queue      members rep-tier src     train-after-label representative",
        "-" * 132,
    ]

    for index, group in enumerate(
        values,
        1,
    ):
        location = (
            "BRD"
            if group.location
            == "board"
            else "BNH"
        )
        queue = (
            "identity"
            if group.queue_type
            == "identity_label"
            else "occQA"
        )
        train = (
            "yes"
            if group
            .recommended_for_identity_training_after_label
            else "no"
        )

        lines.append(
            f"{index:2d} "
            f"{group.start_timestamp_s:7.1f}-"
            f"{group.end_timestamp_s:7.1f} "
            f"{(group.stage_start or '?'):>5} "
            f"{location:>3} "
            f"{group.slot_id:<5} "
            f"{queue:<9} "
            f"{group.member_count:7d} "
            f"{group.representative_tier:<9} "
            f"{group.representative_tracked_source:<7} "
            f"{train:<17} "
            f"{Path(group.representative_crop_uri).name}"
        )

    lines.extend(
        [
            "",
            "visual groups are near-duplicate curation units, not champion tracks or identity labels.",
            "identity queue = trusted/supported occupancy evidence; occQA = raw-candidate occupancy/hard-negative review.",
            "train-after-label=yes only means the representative occupancy evidence is trusted; champion identity is still unlabeled.",
            "ML split unit is match_id; never random-split crops/groups from the same match across train/val/test.",
        ]
    )
    return "\n".join(
        lines
    )
