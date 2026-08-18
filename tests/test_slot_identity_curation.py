import json
from pathlib import Path

from PIL import Image

from tft_analyzer.features.slot_identity_curation import (
    CuratedSlotVisualGroup,
    SlotIdentityCurationSettings,
    curate_slot_identity_dataset,
)
from tft_analyzer.features.slot_identity_curation import pipeline
from tft_analyzer.features.slot_identity_dataset import (
    SlotIdentityObservation,
)


def _pattern(path, *, reverse=False):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    image = Image.new(
        "L",
        (64, 64),
    )
    pixels = image.load()
    for y in range(64):
        for x in range(64):
            value = (
                255 - x * 4
                if reverse
                else x * 4
            )
            pixels[x, y] = max(
                0,
                min(
                    255,
                    value,
                ),
            )
    image.convert(
        "RGB"
    ).save(path)


def _obs(
    sample_id,
    *,
    timestamp,
    stage,
    location="bench",
    slot_id="b0",
    tier="trusted",
    crop_uri,
):
    if tier == "trusted":
        tracked = "occupied"
        current = True
        source_id = f"e-{sample_id}"
        label = True
        training = True
        qa = False
    elif tier == "supported":
        tracked = "occupied"
        current = False
        source_id = "older"
        label = True
        training = False
        qa = False
    else:
        tracked = "empty"
        current = False
        source_id = "older"
        label = False
        training = False
        qa = True

    return SlotIdentityObservation(
        sample_id=sample_id,
        match_id="match-1",
        timestamp_s=timestamp,
        evidence_id=f"e-{sample_id}",
        stage=stage,
        location=location,
        slot_id=slot_id,
        board_row=(
            0
            if location == "board"
            else None
        ),
        board_col=(
            0
            if location == "board"
            else None
        ),
        bench_slot_index=(
            0
            if location == "bench"
            else None
        ),
        source_frame_uri=f"frames/{sample_id}.png",
        crop_uri=crop_uri,
        crop_sha256="0" * 64,
        crop_width=64,
        crop_height=64,
        context_box=(0, 0, 64, 64),
        footprint_box=(8, 16, 56, 60),
        raw_occupancy_status="occupied",
        raw_occupancy_confidence=0.90,
        raw_occupancy_score=0.80,
        tracked_occupancy_status=tracked,
        tracked_occupancy_confidence=0.90,
        tracked_foreground_score=0.80,
        tracked_source_evidence_id=source_id,
        tracked_is_current_evidence=current,
        scene_valid=True,
        scene_score=0.9,
        board_usable=(
            True
            if location == "board"
            else None
        ),
        board_strong_snapshot=False,
        occupancy_evidence_tier=tier,
        occupancy_evidence_reason=f"reason-{tier}",
        recommended_for_identity_labeling=label,
        recommended_for_identity_training=training,
        recommended_for_occupancy_review=qa,
        label_status="unlabeled",
        producer_version="slot-identity-dataset-exporter-0.21.1",
    )


def _write_source_dataset(
    match,
    observations,
    *,
    reverse_samples=(),
):
    dataset = (
        match
        / "datasets"
        / "slot-identity-dataset-exporter-0.21.1"
    )
    dataset.mkdir(
        parents=True,
        exist_ok=True,
    )

    reverse_samples = set(
        reverse_samples
    )
    for item in observations:
        _pattern(
            dataset
            / item.crop_uri,
            reverse=(
                item.sample_id
                in reverse_samples
            ),
        )

    manifest = (
        dataset
        / "manifest.jsonl"
    )
    manifest.write_text(
        "".join(
            item.model_dump_json()
            + "\n"
            for item in observations
        ),
        encoding="utf-8",
    )
    (
        dataset
        / "summary.json"
    ).write_text(
        json.dumps(
            {
                "producer_version": (
                    "slot-identity-dataset-exporter-0.21.1"
                ),
                "sample_count": len(
                    observations
                ),
            }
        ),
        encoding="utf-8",
    )
    return dataset


def _load_groups(path):
    return [
        CuratedSlotVisualGroup.model_validate_json(
            line
        )
        for line in Path(path).read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def test_directory_publish_retries_transient_permission_error(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "curation.tmp"
    destination = tmp_path / "curation"
    source.mkdir()
    (source / "summary.json").write_text(
        "{}",
        encoding="utf-8",
    )

    original_replace = Path.replace
    calls = 0

    def flaky_replace(path, target):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PermissionError(
                "transient Windows directory lock"
            )
        return original_replace(
            path,
            target,
        )

    monkeypatch.setattr(
        Path,
        "replace",
        flaky_replace,
    )
    monkeypatch.setattr(
        pipeline.time,
        "sleep",
        lambda _seconds: None,
    )

    pipeline._replace_directory_with_retry(
        source,
        destination,
    )

    assert calls == 3
    assert not source.exists()
    assert (
        destination
        / "summary.json"
    ).is_file()


def test_curation_groups_near_duplicates_and_separates_quality_queues(tmp_path):
    match = (
        tmp_path
        / "match"
    )
    observations = [
        _obs(
            "t1",
            timestamp=10.0,
            stage="2-1",
            tier="trusted",
            crop_uri="images/bench/t1.png",
        ),
        _obs(
            "s1",
            timestamp=20.0,
            stage="2-1",
            tier="supported",
            crop_uri="images/bench/s1.png",
        ),
        _obs(
            "t2",
            timestamp=30.0,
            stage="2-1",
            tier="trusted",
            crop_uri="images/bench/t2.png",
        ),
        _obs(
            "r1",
            timestamp=11.0,
            stage="2-1",
            tier="raw_candidate",
            crop_uri="images/bench/r1.png",
        ),
        _obs(
            "r2",
            timestamp=20.5,
            stage="2-1",
            tier="raw_candidate",
            crop_uri="images/bench/r2.png",
        ),
        _obs(
            "bt",
            timestamp=15.0,
            stage="2-1",
            location="board",
            slot_id="r0c0",
            tier="trusted",
            crop_uri="images/board/bt.png",
        ),
    ]
    dataset = _write_source_dataset(
        match,
        observations,
        reverse_samples={
            "t2",
        },
    )

    summary = curate_slot_identity_dataset(
        match,
        SlotIdentityCurationSettings(
            max_temporal_gap_s=15.0,
            max_dhash_distance=6,
        ),
        source_dataset_dir=dataset,
    )

    groups = _load_groups(
        summary[
            "visual_groups_path"
        ]
    )

    identity = [
        group
        for group in groups
        if group.queue_type
        == "identity_label"
    ]
    qa = [
        group
        for group in groups
        if group.queue_type
        == "occupancy_qa"
    ]

    # t1+s1 are identical, adjacent and same slot/stage -> one group.
    # t2 is visually opposite -> another group.
    # board trusted is a different slot/location -> another group.
    assert len(identity) == 3

    combined = next(
        group
        for group in identity
        if set(
            group.member_sample_ids
        )
        == {
            "t1",
            "s1",
        }
    )
    assert combined.member_count == 2
    assert combined.representative_sample_id == "t1"
    assert combined.representative_tier == "trusted"
    assert (
        combined
        .recommended_for_identity_training_after_label
        is True
    )

    # Raw candidates are curated in a separate QA queue and may deduplicate.
    assert len(qa) == 1
    assert qa[0].member_count == 2
    assert qa[0].recommended_for_occupancy_review is True

    assert summary[
        "source_identity_queue_sample_count"
    ] == 4
    assert summary[
        "source_occupancy_qa_sample_count"
    ] == 2
    assert summary[
        "identity_label_group_count"
    ] == 3
    assert summary[
        "occupancy_qa_group_count"
    ] == 1

    assert summary[
        "cross_tabs"
    ][
        "tier_by_location"
    ] == {
        "raw_candidate": {
            "bench": 2,
        },
        "supported": {
            "bench": 1,
        },
        "trusted": {
            "bench": 2,
            "board": 1,
        },
    }

    assert summary[
        "split_policy"
    ][
        "split_unit"
    ] == "match_id"
    assert summary[
        "split_policy"
    ][
        "random_crop_split_forbidden"
    ] is True
    assert summary[
        "classifier_feature_policy"
    ][
        "acquisition_priors_as_visual_classifier_input"
    ] is False

    assert Path(
        summary[
            "identity_label_queue_path"
        ]
    ).exists()
    assert Path(
        summary[
            "occupancy_qa_queue_path"
        ]
    ).exists()
    assert Path(
        summary[
            "representatives_dir"
        ]
    ).exists()


def test_curation_splits_identical_crops_on_stage_change(tmp_path):
    match = (
        tmp_path
        / "match"
    )
    observations = [
        _obs(
            "a",
            timestamp=10.0,
            stage="2-1",
            tier="trusted",
            crop_uri="images/bench/a.png",
        ),
        _obs(
            "b",
            timestamp=20.0,
            stage="2-2",
            tier="trusted",
            crop_uri="images/bench/b.png",
        ),
    ]
    dataset = _write_source_dataset(
        match,
        observations,
    )

    summary = curate_slot_identity_dataset(
        match,
        SlotIdentityCurationSettings(
            split_on_stage_change=True,
            max_temporal_gap_s=15.0,
            max_dhash_distance=6,
        ),
        source_dataset_dir=dataset,
    )

    assert summary[
        "identity_label_group_count"
    ] == 2


def test_curation_can_group_across_stage_when_explicit(tmp_path):
    match = (
        tmp_path
        / "match"
    )
    observations = [
        _obs(
            "a",
            timestamp=10.0,
            stage="2-1",
            tier="trusted",
            crop_uri="images/bench/a.png",
        ),
        _obs(
            "b",
            timestamp=20.0,
            stage="2-2",
            tier="trusted",
            crop_uri="images/bench/b.png",
        ),
    ]
    dataset = _write_source_dataset(
        match,
        observations,
    )

    summary = curate_slot_identity_dataset(
        match,
        SlotIdentityCurationSettings(
            split_on_stage_change=False,
            max_temporal_gap_s=15.0,
            max_dhash_distance=6,
        ),
        source_dataset_dir=dataset,
    )

    assert summary[
        "identity_label_group_count"
    ] == 1
