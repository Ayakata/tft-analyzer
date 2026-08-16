from __future__ import annotations

from pathlib import Path

from .models import SlotIdentityObservation


def _iter(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                yield SlotIdentityObservation.model_validate_json(
                    line
                )


def _prior_text(
    item: SlotIdentityObservation,
) -> str:
    if not item.acquisition_priors:
        return "-"
    values = []
    for prior in item.acquisition_priors:
        if (
            prior.confirmed_acquired_copy_lower_bound
            > 0
        ):
            values.append(
                f"{prior.champion}>="
                f"{prior.confirmed_acquired_copy_lower_bound}"
            )
        elif (
            prior.candidate_acquired_copy_count
            > 0
        ):
            values.append(
                f"?{prior.champion}x"
                f"{prior.candidate_acquired_copy_count}"
            )
    return ",".join(values) or "-"


def _location_code(location: str) -> str:
    return (
        "BRD"
        if location == "board"
        else "BNH"
        if location == "bench"
        else location[:3].upper()
    )


def _tier_code(item: SlotIdentityObservation) -> str:
    return {
        "trusted": "T",
        "supported": "S",
        "raw_candidate": "R",
    }.get(
        item.occupancy_evidence_tier,
        "?",
    )


def _recommendation_code(
    item: SlotIdentityObservation,
) -> str:
    if item.recommended_for_identity_training:
        return "train"
    if item.recommended_for_identity_labeling:
        return "label"
    if item.recommended_for_occupancy_review:
        return "occQA"
    return "-"


def format_slot_identity_dataset_timeline(
    manifest_path: Path | str,
    *,
    limit: int | None = 80,
) -> str:
    values = list(
        _iter(
            manifest_path
        )
    )
    if limit is not None:
        values = values[:limit]

    lines = [
        " #  time(s) stage loc slot  raw/conf tracked src   tier use   strong acquisition priors                    crop",
        "-" * 158,
    ]

    for index, item in enumerate(
        values,
        1,
    ):
        tracked = (
            item.tracked_occupancy_status
            or "?"
        )
        source = (
            "now"
            if item.tracked_is_current_evidence
            else (
                "carry"
                if item.tracked_source_evidence_id
                else "-"
            )
        )
        strong = (
            "Y"
            if item.board_strong_snapshot
            else "N"
        )
        priors = _prior_text(item)

        lines.append(
            f"{index:2d} "
            f"{item.timestamp_s:8.1f} "
            f"{(item.stage or '?'):>5} "
            f"{_location_code(item.location):>3} "
            f"{item.slot_id:<5} "
            f"{item.raw_occupancy_status[:3]:>3}/"
            f"{item.raw_occupancy_confidence:.2f} "
            f"{tracked[:3]:>7} "
            f"{source:<5} "
            f"{_tier_code(item):^4} "
            f"{_recommendation_code(item):<5} "
            f"{strong:^6} "
            f"{priors:<38.38} "
            f"{Path(item.crop_uri).name}"
        )

    lines.extend(
        [
            "",
            "tier: T=trusted occupancy evidence, S=supported by tracked carry, R=raw candidate/occupancy QA.",
            "use: train=clean identity-training candidate, label=manual identity labeling, occQA=occupancy/hard-negative review.",
            "BRD=board, BNH=bench. src=now means tracker refreshed from this exact frame; carry means older tracker evidence.",
            "acquisition priors remain historical/non-exhaustive and never establish champion identity or current ownership.",
            "all rows remain unlabeled until target_type/champion_label are explicitly filled.",
        ]
    )
    return "\n".join(lines)
