from __future__ import annotations

from bisect import bisect_right
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

from PIL import Image

from tft_analyzer.features.roster_evidence.models import (
    EpisodeRosterEvidence,
)
from tft_analyzer.storage import iter_evidence_records
from tft_analyzer.tracking.board.models import (
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)

from .models import (
    AcquisitionIdentityPrior,
    SlotIdentityDatasetSettings,
    SlotIdentityObservation,
)


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version_key(path: Path):
    matches = list(
        _VERSION_RE.finditer(path.name)
    )
    version = (
        tuple(
            int(x)
            for x in matches[-1].groups()
        )
        if matches
        else (0, 0, 0)
    )
    return (
        *version,
        path.stat().st_mtime,
    )


def _find_latest(
    directory: Path,
    pattern: str,
) -> Path:
    candidates = list(
        directory.glob(pattern)
    )
    if not candidates:
        raise FileNotFoundError(
            f"No files matching {pattern!r} in {directory}"
        )
    return max(
        candidates,
        key=_version_key,
    )


def find_latest_board_tracker_summary(
    match_dir: Path | str,
) -> Path:
    return _find_latest(
        Path(match_dir) / "tracking",
        "board-bench-occupancy-tracker-*_summary.json",
    )


def find_latest_roster_summary(
    match_dir: Path | str,
) -> Path:
    return _find_latest(
        Path(match_dir) / "features",
        "roster-evidence-builder-*_summary.json",
    )


def _load_json(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def _read_jsonl(
    path: Path,
    model=None,
):
    values = []
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if not line.strip():
                continue
            if model is None:
                values.append(
                    json.loads(line)
                )
            else:
                values.append(
                    model.model_validate_json(
                        line
                    )
                )
    return values


def _resolve(
    match_dir: Path,
    value: str | None,
    subdir: str,
) -> Path:
    if not value:
        raise FileNotFoundError(
            f"Missing source artifact path for {subdir}"
        )
    path = Path(value)
    if path.is_file():
        return path
    candidate = (
        match_dir
        / subdir
        / path.name
    )
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        value
    )


def _sample_id(
    evidence_id: str,
    location: str,
    slot_id: str,
    producer_version: str,
) -> str:
    raw = (
        f"{evidence_id}|{location}|"
        f"{slot_id}|{producer_version}"
    )
    digest = hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]
    return f"slotid-{digest}"


def _sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(
                1024 * 1024
            )
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _tracked_positions(
    state,
) -> dict[str, object]:
    if state is None:
        return {}
    values = (
        state.cells
        if isinstance(
            state,
            TrackedBoardOccupancyState,
        )
        else state.slots
    )
    return {
        item.position: item
        for item in values
    }


class _AcquisitionPriorIndex:
    def __init__(
        self,
        contexts: list[EpisodeRosterEvidence],
    ) -> None:
        ordered = sorted(
            contexts,
            key=lambda item: (
                item.end_timestamp_s,
                item.decision_id,
            ),
        )
        self._contexts = ordered
        self._ends = [
            item.end_timestamp_s
            for item in ordered
        ]

    def at(
        self,
        timestamp_s: float,
    ) -> tuple[
        tuple[AcquisitionIdentityPrior, ...],
        str | None,
        float | None,
        float | None,
    ]:
        # Deliberately causal: a roster snapshot may become a prior only after
        # its sparse DecisionEpisode has ended. This avoids leaking future BUY
        # evidence into crops from inside the same episode.
        index = bisect_right(
            self._ends,
            timestamp_s + 1e-9,
        ) - 1
        if index < 0:
            return (), None, None, None

        context = self._contexts[
            index
        ]
        values = []
        for champion in context.after.champions:
            confirmed = (
                champion
                .confirmed_acquired_copy_lower_bound
            )
            candidate = (
                champion
                .candidate_acquired_copy_count
            )
            if (
                confirmed <= 0
                and candidate <= 0
            ):
                continue
            values.append(
                AcquisitionIdentityPrior(
                    champion=champion.champion,
                    confirmed_acquired_copy_lower_bound=confirmed,
                    candidate_acquired_copy_count=candidate,
                )
            )

        return (
            tuple(values),
            context.decision_id,
            context.end_timestamp_s,
            max(
                0.0,
                timestamp_s
                - context.end_timestamp_s,
            ),
        )


def _eligible(
    raw_item: dict,
    settings: SlotIdentityDatasetSettings,
) -> tuple[bool, str]:
    status = str(
        raw_item.get(
            "status",
            "unknown",
        )
    )
    if (
        status
        not in settings.selected_occupancy_statuses
    ):
        return False, f"status:{status}"

    confidence = float(
        raw_item.get(
            "confidence",
            0.0,
        )
        or 0.0
    )
    if (
        confidence
        < settings.min_raw_occupancy_confidence
    ):
        return False, "low_occupancy_confidence"

    box = raw_item.get(
        "context_box"
    )
    footprint = raw_item.get(
        "footprint_box"
    )
    if (
        not isinstance(box, (list, tuple))
        or len(box) != 4
        or not isinstance(
            footprint,
            (list, tuple),
        )
        or len(footprint) != 4
    ):
        return False, "missing_geometry"

    return True, "eligible"


def _occupancy_evidence_quality(
    *,
    location: str,
    raw_status: str,
    tracked_status: str | None,
    tracked_is_current_evidence: bool,
    scene_valid: bool | None,
    board_strong_snapshot: bool,
) -> tuple[str, str, bool, bool, bool]:
    """
    Return:
      tier,
      reason,
      recommended_for_identity_labeling,
      recommended_for_identity_training,
      recommended_for_occupancy_review

    Important: this classifies confidence in *slot occupancy as an identity
    crop*, not champion identity itself.
    """
    if scene_valid is not True:
        return (
            "raw_candidate",
            "scene_not_valid",
            False,
            False,
            True,
        )

    if raw_status != "occupied":
        return (
            "raw_candidate",
            f"raw_status_{raw_status}",
            False,
            False,
            True,
        )

    if tracked_status == "occupied":
        if tracked_is_current_evidence:
            return (
                "trusted",
                "raw_and_tracked_occupied_current_evidence",
                True,
                True,
                False,
            )

        if (
            location == "board"
            and board_strong_snapshot
        ):
            return (
                "trusted",
                "strong_board_snapshot_tracked_occupied",
                True,
                True,
                False,
            )

        return (
            "supported",
            "raw_occupied_with_tracked_occupied_carry",
            True,
            False,
            False,
        )

    if tracked_status == "empty":
        return (
            "raw_candidate",
            (
                "raw_occupied_conflicts_tracked_empty_current"
                if tracked_is_current_evidence
                else "raw_occupied_conflicts_tracked_empty_carry"
            ),
            False,
            False,
            True,
        )

    if tracked_status == "unknown":
        return (
            "raw_candidate",
            (
                "raw_occupied_tracked_unknown_current"
                if tracked_is_current_evidence
                else "raw_occupied_tracked_unknown"
            ),
            False,
            False,
            True,
        )

    return (
        "raw_candidate",
        "raw_occupied_without_tracked_support",
        False,
        False,
        True,
    )


def _crop_name(
    *,
    sequence: int,
    timestamp_s: float,
    location: str,
    slot_id: str,
) -> str:
    safe_slot = (
        slot_id
        .replace(",", "_")
        .replace("/", "_")
    )
    return (
        f"{sequence:08d}_"
        f"{timestamp_s:010.3f}_"
        f"{location}_{safe_slot}.png"
    )


def _write_manifest(
    path: Path,
    values: list[SlotIdentityObservation],
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


def _write_label_template(
    path: Path,
    values: list[SlotIdentityObservation],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "sample_id",
                "crop_uri",
                "evidence_id",
                "timestamp_s",
                "stage",
                "location",
                "slot_id",
                "raw_occupancy_status",
                "raw_occupancy_confidence",
                "tracked_occupancy_status",
                "tracked_source",
                "occupancy_evidence_tier",
                "occupancy_evidence_reason",
                "recommended_for_identity_labeling",
                "recommended_for_identity_training",
                "recommended_for_occupancy_review",
                "target_type",
                "champion_label",
                "label_status",
                "notes",
            ]
        )
        for value in values:
            tracked_source = (
                "current"
                if value.tracked_is_current_evidence
                else (
                    "carry"
                    if value.tracked_source_evidence_id
                    else "none"
                )
            )
            writer.writerow(
                [
                    value.sample_id,
                    value.crop_uri,
                    value.evidence_id,
                    f"{value.timestamp_s:.3f}",
                    value.stage or "",
                    value.location,
                    value.slot_id,
                    value.raw_occupancy_status,
                    f"{value.raw_occupancy_confidence:.6f}",
                    value.tracked_occupancy_status or "",
                    tracked_source,
                    value.occupancy_evidence_tier,
                    value.occupancy_evidence_reason,
                    str(
                        value.recommended_for_identity_labeling
                    ).lower(),
                    str(
                        value.recommended_for_identity_training
                    ).lower(),
                    str(
                        value.recommended_for_occupancy_review
                    ).lower(),
                    "",
                    "",
                    "unlabeled",
                    "",
                ]
            )


def _write_dataset_readme(
    path: Path,
    *,
    producer_version: str,
) -> None:
    path.write_text(
        f"""# TFT Slot Identity Observation Dataset

Producer: `{producer_version}`

`manifest.jsonl` contains the complete selected observation pool. 0.21.1
classifies confidence in *slot occupancy as a champion-identity crop* without
inferring champion identity.

Occupancy evidence tiers:

- `trusted`: raw current-frame occupancy is supported by current tracked
  occupied state, or by an accepted strong board snapshot with tracked
  occupancy. Recommended for identity labeling and clean identity training.
- `supported`: raw occupied crop agrees with tracked occupied state, but the
  tracker support is carried from older evidence. Recommended for manual
  identity labeling, not clean training by default.
- `raw_candidate`: raw occupancy lacks temporal support, contradicts tracked
  empty/unknown state, comes from a non-occupied opt-in status, or is
  scene-invalid. Retained for occupancy QA/hard-negative review.

Label contract:

- `target_type=champion` + `champion_label=<name>`
- `target_type=no_unit` for false-positive occupancy / hard negatives
- `target_type=uncertain` when a human cannot decide
- `target_type=unusable` for effects/occlusion/bad crops

Important semantics:

- crops are observations, not champion labels;
- `acquisition_priors` are historical and non-exhaustive;
- priors never establish current ownership;
- a champion absent from acquisition priors remains a valid identity;
- tracker carry is metadata/support, not current-frame visual truth;
- `recommended_for_identity_training=true` is a clean occupancy gate only;
  it does not mean the champion identity is already known;
- all exported rows remain unlabeled until an explicit labeling workflow fills
  `target_type` / `champion_label`.

0.21.1 does not infer champion identity, star level, items or traits.
""",
        encoding="utf-8",
    )


def export_slot_identity_dataset(
    match_dir: Path | str,
    settings: SlotIdentityDatasetSettings,
    *,
    board_tracker_summary_path: Path | str | None = None,
    roster_summary_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    force: bool = False,
) -> dict[str, object]:
    match_dir = Path(
        match_dir
    )

    tracker_summary_path = (
        Path(
            board_tracker_summary_path
        )
        if board_tracker_summary_path
        is not None
        else find_latest_board_tracker_summary(
            match_dir
        )
    )
    tracker_summary = _load_json(
        tracker_summary_path
    )

    attempts_path = _resolve(
        match_dir,
        tracker_summary.get(
            "source_attempts_path"
        ),
        "observations",
    )
    board_states_path = _resolve(
        match_dir,
        tracker_summary.get(
            "board_states_path"
        ),
        "tracking",
    )
    bench_states_path = _resolve(
        match_dir,
        tracker_summary.get(
            "bench_states_path"
        ),
        "tracking",
    )

    source_roster_summary_path = (
        Path(roster_summary_path)
        if roster_summary_path
        is not None
        else find_latest_roster_summary(
            match_dir
        )
    )
    roster_summary = _load_json(
        source_roster_summary_path
    )

    if (
        roster_summary.get(
            "current_ownership_status"
        )
        != "not_established"
    ):
        raise ValueError(
            "0.21.1 expects acquisition-history priors, "
            "not a claimed complete current roster."
        )

    roster_contexts_path = _resolve(
        match_dir,
        roster_summary.get(
            "contexts_path"
        ),
        "features",
    )

    attempts = _read_jsonl(
        attempts_path
    )
    board_states = _read_jsonl(
        board_states_path,
        TrackedBoardOccupancyState,
    )
    bench_states = _read_jsonl(
        bench_states_path,
        TrackedBenchOccupancyState,
    )
    roster_contexts = _read_jsonl(
        roster_contexts_path,
        EpisodeRosterEvidence,
    )

    board_by_evidence = {
        item.evidence_id: item
        for item in board_states
    }
    bench_by_evidence = {
        item.evidence_id: item
        for item in bench_states
    }
    evidence_by_id = {
        record.evidence.evidence_id: record
        for record in iter_evidence_records(
            match_dir
        )
    }
    prior_index = _AcquisitionPriorIndex(
        roster_contexts
    )

    dataset_dir = (
        Path(output_dir)
        if output_dir is not None
        else (
            match_dir
            / "datasets"
            / settings.producer_version
        )
    )
    if dataset_dir.exists():
        if not force:
            raise FileExistsError(
                f"Dataset directory already exists: {dataset_dir}. "
                "Pass --force to regenerate it."
            )
        shutil.rmtree(
            dataset_dir
        )

    temp_dir = dataset_dir.with_name(
        dataset_dir.name + ".tmp"
    )
    if temp_dir.exists():
        shutil.rmtree(
            temp_dir
        )

    board_images_dir = (
        temp_dir
        / "images"
        / "board"
    )
    bench_images_dir = (
        temp_dir
        / "images"
        / "bench"
    )
    board_images_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    bench_images_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    observations = []
    skipped = Counter()
    exported_by_location = Counter()
    exported_by_stage = Counter()
    exported_raw_status = Counter()
    evidence_tier_counts = Counter()
    evidence_reason_counts = Counter()
    identity_labeling_recommended_count = 0
    identity_training_recommended_count = 0
    occupancy_review_recommended_count = 0
    tracked_current_count = 0
    strong_snapshot_sample_count = 0
    sample_with_prior_count = 0
    sample_with_confirmed_prior_count = 0
    sample_with_candidate_prior_count = 0

    unique_confirmed_prior_champions = set()
    unique_candidate_prior_champions = set()

    scene_valid_attempt_count = 0
    scene_invalid_attempt_count = 0
    missing_scene_attempt_count = 0

    for attempt in attempts:
        evidence_id = str(
            attempt.get(
                "evidence_id",
                "",
            )
        )
        if not evidence_id:
            skipped[
                "missing_evidence_id"
            ] += 1
            continue

        record = evidence_by_id.get(
            evidence_id
        )
        if record is None:
            skipped[
                "missing_evidence_record"
            ] += 1
            continue

        source_path = (
            match_dir
            / record.evidence.uri
        )
        if not source_path.exists():
            skipped[
                "missing_source_frame"
            ] += 1
            continue

        board_state = (
            board_by_evidence.get(
                evidence_id
            )
        )
        bench_state = (
            bench_by_evidence.get(
                evidence_id
            )
        )

        scene_valid = (
            board_state.scene_valid
            if board_state is not None
            else None
        )
        if scene_valid is True:
            scene_valid_attempt_count += 1
        elif scene_valid is False:
            scene_invalid_attempt_count += 1
        else:
            missing_scene_attempt_count += 1

        if (
            settings.require_scene_valid
            and scene_valid is not True
        ):
            skipped[
                "scene_not_valid"
            ] += (
                len(
                    attempt.get(
                        "board_cells",
                        [],
                    )
                )
                + len(
                    attempt.get(
                        "bench_slots",
                        [],
                    )
                )
            )
            continue

        timestamp_s = float(
            attempt.get(
                "timestamp_s",
                record.evidence.timestamp_s,
            )
        )
        sequence = int(
            attempt.get(
                "sequence",
                record.sequence,
            )
        )

        (
            acquisition_priors,
            prior_decision_id,
            prior_end_timestamp_s,
            prior_age_s,
        ) = prior_index.at(
            timestamp_s
        )

        if acquisition_priors:
            sample_prior_available = True
        else:
            sample_prior_available = False

        board_positions = (
            _tracked_positions(
                board_state
            )
        )
        bench_positions = (
            _tracked_positions(
                bench_state
            )
        )

        candidates = []

        if settings.export_board:
            for raw in attempt.get(
                "board_cells",
                [],
            ):
                ok, reason = _eligible(
                    raw,
                    settings,
                )
                if not ok:
                    skipped[
                        f"board_{reason}"
                    ] += 1
                    continue

                row = int(
                    raw["row"]
                )
                col = int(
                    raw["col"]
                )
                position = f"{row},{col}"
                tracked = (
                    board_positions.get(
                        position
                    )
                )
                candidates.append(
                    (
                        "board",
                        f"r{row}c{col}",
                        row,
                        col,
                        None,
                        raw,
                        tracked,
                    )
                )

        if settings.export_bench:
            for raw in attempt.get(
                "bench_slots",
                [],
            ):
                ok, reason = _eligible(
                    raw,
                    settings,
                )
                if not ok:
                    skipped[
                        f"bench_{reason}"
                    ] += 1
                    continue

                index = int(
                    raw["slot_index"]
                )
                position = str(
                    index
                )
                tracked = (
                    bench_positions.get(
                        position
                    )
                )
                candidates.append(
                    (
                        "bench",
                        f"b{index}",
                        None,
                        None,
                        index,
                        raw,
                        tracked,
                    )
                )

        if not candidates:
            continue

        with Image.open(
            source_path
        ) as src:
            image = src.convert(
                "RGB"
            )

            for (
                location,
                slot_id,
                board_row,
                board_col,
                bench_slot_index,
                raw,
                tracked,
            ) in candidates:
                box = tuple(
                    int(x)
                    for x in raw[
                        "context_box"
                    ]
                )
                footprint_box = tuple(
                    int(x)
                    for x in raw[
                        "footprint_box"
                    ]
                )
                crop = image.crop(
                    box
                )

                relative_dir = (
                    Path("images")
                    / location
                )
                filename = _crop_name(
                    sequence=sequence,
                    timestamp_s=timestamp_s,
                    location=location,
                    slot_id=slot_id,
                )
                crop_path = (
                    temp_dir
                    / relative_dir
                    / filename
                )
                crop.save(
                    crop_path,
                    format="PNG",
                )

                crop_sha = _sha256_file(
                    crop_path
                )
                crop_uri = (
                    relative_dir
                    / filename
                ).as_posix()

                tracked_source_evidence_id = (
                    tracked.source_evidence_id
                    if tracked is not None
                    else None
                )
                tracked_is_current = (
                    tracked_source_evidence_id
                    == evidence_id
                    if tracked_source_evidence_id
                    is not None
                    else False
                )

                if tracked_is_current:
                    tracked_current_count += 1

                if (
                    location == "board"
                    and board_state is not None
                    and board_state.strong_snapshot
                ):
                    strong_snapshot_sample_count += 1

                if sample_prior_available:
                    sample_with_prior_count += 1

                if any(
                    prior.confirmed_acquired_copy_lower_bound
                    > 0
                    for prior in acquisition_priors
                ):
                    sample_with_confirmed_prior_count += 1
                    unique_confirmed_prior_champions.update(
                        prior.champion
                        for prior in acquisition_priors
                        if (
                            prior.confirmed_acquired_copy_lower_bound
                            > 0
                        )
                    )

                if any(
                    prior.candidate_acquired_copy_count
                    > 0
                    for prior in acquisition_priors
                ):
                    sample_with_candidate_prior_count += 1
                    unique_candidate_prior_champions.update(
                        prior.champion
                        for prior in acquisition_priors
                        if (
                            prior.candidate_acquired_copy_count
                            > 0
                        )
                    )

                raw_status = str(
                    raw.get(
                        "status",
                        "unknown",
                    )
                )
                raw_confidence = float(
                    raw.get(
                        "confidence",
                        0.0,
                    )
                    or 0.0
                )
                raw_score = float(
                    raw.get(
                        "score",
                        0.0,
                    )
                    or 0.0
                )
                tracked_status = (
                    tracked.status
                    if tracked is not None
                    else None
                )
                (
                    occupancy_evidence_tier,
                    occupancy_evidence_reason,
                    recommended_for_identity_labeling,
                    recommended_for_identity_training,
                    recommended_for_occupancy_review,
                ) = _occupancy_evidence_quality(
                    location=location,
                    raw_status=raw_status,
                    tracked_status=tracked_status,
                    tracked_is_current_evidence=tracked_is_current,
                    scene_valid=scene_valid,
                    board_strong_snapshot=bool(
                        location == "board"
                        and board_state is not None
                        and board_state.strong_snapshot
                    ),
                )

                observation = SlotIdentityObservation(
                    sample_id=_sample_id(
                        evidence_id,
                        location,
                        slot_id,
                        settings.producer_version,
                    ),
                    match_id=record.evidence.match_id,
                    timestamp_s=timestamp_s,
                    evidence_id=evidence_id,
                    stage=(
                        board_state.hud_stage
                        if board_state is not None
                        else None
                    ),
                    location=location,
                    slot_id=slot_id,
                    board_row=board_row,
                    board_col=board_col,
                    bench_slot_index=bench_slot_index,
                    source_frame_uri=(
                        record.evidence.uri
                    ),
                    crop_uri=crop_uri,
                    crop_sha256=crop_sha,
                    crop_width=crop.width,
                    crop_height=crop.height,
                    context_box=box,
                    footprint_box=footprint_box,
                    raw_occupancy_status=raw_status,
                    raw_occupancy_confidence=raw_confidence,
                    raw_occupancy_score=raw_score,
                    tracked_occupancy_status=tracked_status,
                    tracked_occupancy_confidence=(
                        tracked.confidence
                        if tracked is not None
                        else None
                    ),
                    tracked_foreground_score=(
                        tracked.foreground_score
                        if tracked is not None
                        else None
                    ),
                    tracked_source_evidence_id=(
                        tracked_source_evidence_id
                    ),
                    tracked_is_current_evidence=(
                        tracked_is_current
                    ),
                    scene_valid=scene_valid,
                    scene_score=(
                        board_state.scene_score
                        if board_state is not None
                        else None
                    ),
                    board_usable=(
                        board_state.usable
                        if board_state is not None
                        else None
                    ),
                    board_strong_snapshot=(
                        board_state.strong_snapshot
                        if board_state is not None
                        else None
                    ),
                    board_gate_reason=(
                        board_state.gate_reason
                        if board_state is not None
                        else None
                    ),
                    hud_level=(
                        board_state.hud_level
                        if board_state is not None
                        else None
                    ),
                    board_capacity_status=(
                        board_state.capacity_status
                        if board_state is not None
                        else None
                    ),
                    occupancy_evidence_tier=(
                        occupancy_evidence_tier
                    ),
                    occupancy_evidence_reason=(
                        occupancy_evidence_reason
                    ),
                    recommended_for_identity_labeling=(
                        recommended_for_identity_labeling
                    ),
                    recommended_for_identity_training=(
                        recommended_for_identity_training
                    ),
                    recommended_for_occupancy_review=(
                        recommended_for_occupancy_review
                    ),
                    acquisition_priors=(
                        acquisition_priors
                    ),
                    acquisition_prior_source_decision_id=(
                        prior_decision_id
                    ),
                    acquisition_prior_source_end_timestamp_s=(
                        prior_end_timestamp_s
                    ),
                    acquisition_prior_age_s=(
                        prior_age_s
                    ),
                    label_status="unlabeled",
                    target_type=None,
                    champion_label=None,
                    source_board_tracker_version=(
                        board_state.tracker_version
                        if board_state is not None
                        else None
                    ),
                    source_bench_tracker_version=(
                        bench_state.tracker_version
                        if bench_state is not None
                        else None
                    ),
                    source_roster_producer_version=(
                        roster_summary.get(
                            "producer_version"
                        )
                    ),
                    producer_version=(
                        settings.producer_version
                    ),
                )
                observations.append(
                    observation
                )
                exported_by_location[
                    location
                ] += 1
                exported_by_stage[
                    observation.stage
                    or "unknown"
                ] += 1
                exported_raw_status[
                    observation.raw_occupancy_status
                ] += 1
                evidence_tier_counts[
                    observation.occupancy_evidence_tier
                ] += 1
                evidence_reason_counts[
                    observation.occupancy_evidence_reason
                ] += 1
                if observation.recommended_for_identity_labeling:
                    identity_labeling_recommended_count += 1
                if observation.recommended_for_identity_training:
                    identity_training_recommended_count += 1
                if observation.recommended_for_occupancy_review:
                    occupancy_review_recommended_count += 1

    manifest_path = (
        temp_dir
        / "manifest.jsonl"
    )
    labels_path = (
        temp_dir
        / "labels_template.csv"
    )
    summary_path_temp = (
        temp_dir
        / "summary.json"
    )
    readme_path = (
        temp_dir
        / "README.md"
    )

    _write_manifest(
        manifest_path,
        observations,
    )
    _write_label_template(
        labels_path,
        observations,
    )
    _write_dataset_readme(
        readme_path,
        producer_version=(
            settings.producer_version
        ),
    )

    game_context = (
        roster_summary.get(
            "game_context"
        )
        or {}
    )

    summary = {
        "schema_version": 2,
        "producer_version": settings.producer_version,
        "match_dir": str(match_dir),
        "dataset_semantics": (
            "unlabeled_slot_identity_observations"
        ),
        "identity_search_space_exhaustive": False,
        "current_ownership_assumed": False,
        "acquisition_prior_semantics": (
            "historical_non_exhaustive_not_current_ownership"
        ),
        "input_board_tracker_summary_path": str(
            tracker_summary_path
        ),
        "input_attempts_path": str(
            attempts_path
        ),
        "input_board_states_path": str(
            board_states_path
        ),
        "input_bench_states_path": str(
            bench_states_path
        ),
        "input_roster_summary_path": str(
            source_roster_summary_path
        ),
        "input_roster_contexts_path": str(
            roster_contexts_path
        ),
        "source_attempt_count": len(
            attempts
        ),
        "source_board_state_count": len(
            board_states
        ),
        "source_bench_state_count": len(
            bench_states
        ),
        "scene_valid_attempt_count": (
            scene_valid_attempt_count
        ),
        "scene_invalid_attempt_count": (
            scene_invalid_attempt_count
        ),
        "scene_unknown_attempt_count": (
            missing_scene_attempt_count
        ),
        "sample_count": len(
            observations
        ),
        "board_sample_count": (
            exported_by_location[
                "board"
            ]
        ),
        "bench_sample_count": (
            exported_by_location[
                "bench"
            ]
        ),
        "sample_stage_counts": dict(
            sorted(
                exported_by_stage.items()
            )
        ),
        "raw_occupancy_status_counts": dict(
            sorted(
                exported_raw_status.items()
            )
        ),
        "occupancy_evidence_tier_counts": dict(
            sorted(
                evidence_tier_counts.items()
            )
        ),
        "occupancy_evidence_reason_counts": dict(
            sorted(
                evidence_reason_counts.items()
            )
        ),
        "identity_labeling_recommended_sample_count": (
            identity_labeling_recommended_count
        ),
        "identity_training_recommended_sample_count": (
            identity_training_recommended_count
        ),
        "occupancy_review_recommended_sample_count": (
            occupancy_review_recommended_count
        ),
        "tracked_current_evidence_sample_count": (
            tracked_current_count
        ),
        "board_strong_snapshot_sample_count": (
            strong_snapshot_sample_count
        ),
        "sample_with_acquisition_prior_count": (
            sample_with_prior_count
        ),
        "sample_with_confirmed_acquisition_prior_count": (
            sample_with_confirmed_prior_count
        ),
        "sample_with_candidate_acquisition_prior_count": (
            sample_with_candidate_prior_count
        ),
        "unique_confirmed_acquisition_prior_champions": sorted(
            unique_confirmed_prior_champions
        ),
        "unique_candidate_acquisition_prior_champions": sorted(
            unique_candidate_prior_champions
        ),
        "skipped_counts": dict(
            sorted(
                skipped.items()
            )
        ),
        "label_status_counts": {
            "unlabeled": len(
                observations
            )
        },
        "game_context": game_context,
        "settings": {
            "export_board": settings.export_board,
            "export_bench": settings.export_bench,
            "selected_occupancy_statuses": list(
                settings.selected_occupancy_statuses
            ),
            "min_raw_occupancy_confidence": (
                settings.min_raw_occupancy_confidence
            ),
            "require_scene_valid": (
                settings.require_scene_valid
            ),
            "image_format": settings.image_format,
        },
        "dataset_dir": str(
            dataset_dir
        ),
        "manifest_path": str(
            dataset_dir
            / "manifest.jsonl"
        ),
        "labels_template_path": str(
            dataset_dir
            / "labels_template.csv"
        ),
        "images_dir": str(
            dataset_dir
            / "images"
        ),
        "readme_path": str(
            dataset_dir
            / "README.md"
        ),
        "summary_path": str(
            dataset_dir
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

    dataset_dir.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temp_dir.replace(
        dataset_dir
    )

    return summary
