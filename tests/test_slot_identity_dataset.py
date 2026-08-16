import hashlib
import json

import pytest
from pathlib import Path

from PIL import Image

from tft_analyzer.features.roster_evidence.models import (
    EpisodeRosterEvidence,
    RosterChampionEvidence,
    RosterEpisodeDelta,
    RosterEvidenceSnapshot,
)
from tft_analyzer.features.slot_identity_dataset import (
    SlotIdentityDatasetSettings,
    SlotIdentityObservation,
    export_slot_identity_dataset,
)
from tft_analyzer.features.slot_identity_dataset.pipeline import (
    _occupancy_evidence_quality,
)
from tft_analyzer.tracking.board.models import (
    OccupancyPositionState,
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)


def _write_jsonl(path, values):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        for value in values:
            if hasattr(value, "model_dump_json"):
                line = value.model_dump_json()
            else:
                line = json.dumps(value)
            f.write(line + "\n")


def _evidence(
    match,
    evidence_id,
    timestamp_s,
    sequence,
    *,
    color,
):
    frames = match / "evidence" / "frames"
    frames.mkdir(
        parents=True,
        exist_ok=True,
    )
    frame = frames / f"{sequence:08d}.png"
    Image.new(
        "RGB",
        (200, 120),
        color,
    ).save(frame)

    digest = hashlib.sha256(
        frame.read_bytes()
    ).hexdigest()
    record = {
        "sequence": sequence,
        "reason": "test",
        "scene_change_score": 0.1,
        "wall_time_iso": None,
        "width": 200,
        "height": 120,
        "evidence": {
            "evidence_id": evidence_id,
            "match_id": "m",
            "timestamp_s": timestamp_s,
            "kind": "frame",
            "uri": frame.relative_to(match).as_posix(),
            "sha256": digest,
            "source": "screen",
        },
    }
    index = match / "evidence" / "evidence_index.jsonl"
    index.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    with index.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(record)
            + "\n"
        )


def _board_state(
    evidence_id,
    timestamp_s,
    *,
    scene_valid=True,
    strong=False,
    source_evidence_id=None,
):
    cells = []
    for row in range(4):
        for col in range(7):
            pos = f"{row},{col}"
            occupied = pos == "0,0"
            cells.append(
                OccupancyPositionState(
                    position=pos,
                    status=(
                        "occupied"
                        if occupied
                        else "empty"
                    ),
                    confidence=0.9,
                    foreground_score=(
                        0.9
                        if occupied
                        else 0.1
                    ),
                    raw_score=(
                        0.8
                        if occupied
                        else 0.2
                    ),
                    source_timestamp_s=(
                        timestamp_s
                        if occupied
                        else timestamp_s
                    ),
                    source_evidence_id=(
                        source_evidence_id
                        if occupied
                        else evidence_id
                    ),
                )
            )

    return TrackedBoardOccupancyState(
        match_id="m",
        timestamp_s=timestamp_s,
        evidence_id=evidence_id,
        usable=scene_valid,
        stability=(
            "stable"
            if scene_valid
            else "unstable"
        ),
        gate_reason=(
            "full_level_snapshot"
            if strong
            else (
                "planning_visual_stable"
                if scene_valid
                else "scene_invalid"
            )
        ),
        motion_count=0,
        candidate_change_count=0,
        uncertain_count=0,
        candidate_occupied_count=1,
        occupied_count=1,
        hud_level=2,
        hud_stage="2-1",
        round_age_s=10.0,
        capacity_status="under",
        strong_snapshot=strong,
        scene_valid=scene_valid,
        scene_score=(
            0.8
            if scene_valid
            else 0.01
        ),
        cells=tuple(cells),
        tracker_version="board-bench-occupancy-tracker-0.13.5",
    )


def _bench_state(
    evidence_id,
    timestamp_s,
):
    slots = []
    for index in range(9):
        occupied = index == 0
        slots.append(
            OccupancyPositionState(
                position=str(index),
                status=(
                    "occupied"
                    if occupied
                    else "empty"
                ),
                confidence=0.88,
                foreground_score=(
                    0.82
                    if occupied
                    else 0.1
                ),
                raw_score=(
                    0.75
                    if occupied
                    else 0.2
                ),
                source_timestamp_s=timestamp_s,
                source_evidence_id=evidence_id,
            )
        )

    return TrackedBenchOccupancyState(
        match_id="m",
        timestamp_s=timestamp_s,
        evidence_id=evidence_id,
        uncertain_count=0,
        occupied_count=1,
        slots=tuple(slots),
        tracker_version="board-bench-occupancy-tracker-0.13.5",
    )


def _attempt(
    evidence_id,
    timestamp_s,
    sequence,
):
    return {
        "sequence": sequence,
        "timestamp_s": timestamp_s,
        "evidence_id": evidence_id,
        "board_present": True,
        "bench_present": True,
        "board_cells": [
            {
                "row": 0,
                "col": 0,
                "status": "occupied",
                "score": 0.82,
                "confidence": 0.91,
                "context_box": [10, 10, 70, 90],
                "footprint_box": [20, 40, 60, 80],
            },
            {
                "row": 0,
                "col": 1,
                "status": "empty",
                "score": 0.10,
                "confidence": 0.95,
                "context_box": [70, 10, 120, 90],
                "footprint_box": [80, 40, 110, 80],
            },
        ],
        "bench_slots": [
            {
                "slot_index": 0,
                "status": "occupied",
                "score": 0.79,
                "confidence": 0.89,
                "context_box": [120, 10, 190, 100],
                "footprint_box": [135, 55, 175, 95],
            }
        ],
    }


def _roster_context(
    decision_id,
    end_timestamp_s,
    *,
    champions,
):
    snapshot = RosterEvidenceSnapshot(
        champions=tuple(
            RosterChampionEvidence(
                champion=name,
                confirmed_acquired_copy_lower_bound=count,
            )
            for name, count in champions.items()
        ),
        confirmed_identity_buy_copy_count=sum(
            champions.values()
        ),
    )
    return EpisodeRosterEvidence(
        roster_context_id=f"r-{decision_id}",
        match_id="m",
        decision_id=decision_id,
        stage_start="2-1",
        stage_end="2-1",
        start_timestamp_s=max(
            0.0,
            end_timestamp_s - 10.0,
        ),
        end_timestamp_s=end_timestamp_s,
        before=RosterEvidenceSnapshot(),
        delta=RosterEpisodeDelta(
            confirmed_buys=champions,
        ),
        after=snapshot,
        source_episode_producer_version="decision-episode-builder-0.15.0",
        source_action_producer_version="semantic-action-fusion-0.14.6",
        producer_version="roster-evidence-builder-0.20.1",
    )


def test_export_uses_scene_valid_occupied_crops_and_causal_priors(tmp_path):
    match = tmp_path / "match"

    _evidence(
        match,
        "e-valid",
        20.0,
        0,
        color=(10, 20, 30),
    )
    _evidence(
        match,
        "e-invalid",
        40.0,
        1,
        color=(40, 50, 60),
    )

    attempts_path = (
        match
        / "observations"
        / "board-bench-occupancy-0.12.0_attempts.jsonl"
    )
    _write_jsonl(
        attempts_path,
        [
            _attempt(
                "e-valid",
                20.0,
                0,
            ),
            _attempt(
                "e-invalid",
                40.0,
                1,
            ),
        ],
    )

    board_path = (
        match
        / "tracking"
        / "board-occupancy-tracker-0.13.5.jsonl"
    )
    bench_path = (
        match
        / "tracking"
        / "bench-occupancy-tracker-0.13.5.jsonl"
    )
    _write_jsonl(
        board_path,
        [
            _board_state(
                "e-valid",
                20.0,
                source_evidence_id="older-evidence",
            ),
            _board_state(
                "e-invalid",
                40.0,
                scene_valid=False,
            ),
        ],
    )
    _write_jsonl(
        bench_path,
        [
            _bench_state(
                "e-valid",
                20.0,
            ),
            _bench_state(
                "e-invalid",
                40.0,
            ),
        ],
    )

    tracker_summary_path = (
        match
        / "tracking"
        / "board-bench-occupancy-tracker-0.13.5_summary.json"
    )
    tracker_summary_path.write_text(
        json.dumps(
            {
                "tracker_version": "board-bench-occupancy-tracker-0.13.5",
                "source_attempts_path": str(attempts_path),
                "board_states_path": str(board_path),
                "bench_states_path": str(bench_path),
            }
        ),
        encoding="utf-8",
    )

    roster_contexts = [
        _roster_context(
            "d1",
            10.0,
            champions={
                "rhaast": 2,
            },
        ),
        _roster_context(
            "d2",
            30.0,
            champions={
                "rhaast": 2,
                "briar": 1,
            },
        ),
    ]
    roster_contexts_path = (
        match
        / "features"
        / "roster-evidence-builder-0.20.1.jsonl"
    )
    _write_jsonl(
        roster_contexts_path,
        roster_contexts,
    )
    roster_summary_path = (
        match
        / "features"
        / "roster-evidence-builder-0.20.1_summary.json"
    )
    roster_summary_path.write_text(
        json.dumps(
            {
                "producer_version": "roster-evidence-builder-0.20.1",
                "contexts_path": str(roster_contexts_path),
                "current_ownership_status": "not_established",
                "game_context": {
                    "set_id": "TFT17",
                    "patch": "16.16",
                    "data_dragon_version": "16.16.1",
                },
            }
        ),
        encoding="utf-8",
    )

    summary = export_slot_identity_dataset(
        match,
        SlotIdentityDatasetSettings(),
        board_tracker_summary_path=tracker_summary_path,
        roster_summary_path=roster_summary_path,
    )

    assert summary["sample_count"] == 2
    assert summary["board_sample_count"] == 1
    assert summary["bench_sample_count"] == 1
    assert summary["scene_invalid_attempt_count"] == 1
    assert summary["occupancy_evidence_tier_counts"] == {
        "supported": 1,
        "trusted": 1,
    }
    assert summary["identity_training_recommended_sample_count"] == 1
    assert summary["identity_labeling_recommended_sample_count"] == 2
    assert summary["occupancy_review_recommended_sample_count"] == 0
    assert summary["identity_search_space_exhaustive"] is False
    assert summary["current_ownership_assumed"] is False

    manifest = [
        SlotIdentityObservation.model_validate_json(line)
        for line in Path(summary["manifest_path"]).read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert len(manifest) == 2
    assert {
        item.location
        for item in manifest
    } == {
        "board",
        "bench",
    }

    # t=20 may only use the episode completed at t=10; Briar acquired at
    # episode end t=30 must not leak backward into the crop prior.
    for item in manifest:
        priors = {
            prior.champion:
            prior.confirmed_acquired_copy_lower_bound
            for prior in item.acquisition_priors
        }
        assert priors == {
            "rhaast": 2,
        }
        assert (
            item.acquisition_prior_source_decision_id
            == "d1"
        )
        assert item.current_ownership_established is False
        assert item.identity_search_space_exhaustive is False
        assert item.champion_label is None
        assert item.label_status == "unlabeled"

        crop = (
            Path(summary["dataset_dir"])
            / item.crop_uri
        )
        assert crop.exists()

    board = next(
        item
        for item in manifest
        if item.location == "board"
    )
    assert board.crop_width == 60
    assert board.crop_height == 80
    assert board.tracked_is_current_evidence is False
    assert board.occupancy_evidence_tier == "supported"
    assert board.recommended_for_identity_labeling is True
    assert board.recommended_for_identity_training is False
    assert board.recommended_for_occupancy_review is False

    bench = next(
        item
        for item in manifest
        if item.location == "bench"
    )
    assert bench.crop_width == 70
    assert bench.crop_height == 90
    assert bench.tracked_is_current_evidence is True
    assert bench.occupancy_evidence_tier == "trusted"
    assert bench.recommended_for_identity_labeling is True
    assert bench.recommended_for_identity_training is True
    assert bench.recommended_for_occupancy_review is False

    labels = Path(
        summary["labels_template_path"]
    ).read_text(
        encoding="utf-8"
    )
    assert "target_type" in labels
    assert "champion_label" in labels
    assert "occupancy_evidence_tier" in labels
    assert "recommended_for_identity_training" in labels
    assert "unlabeled" in labels


def test_export_can_include_empty_and_scene_invalid_when_explicit(tmp_path):
    match = tmp_path / "match"
    _evidence(
        match,
        "e1",
        20.0,
        0,
        color=(20, 30, 40),
    )

    attempts_path = (
        match
        / "observations"
        / "board-bench-occupancy-0.12.0_attempts.jsonl"
    )
    _write_jsonl(
        attempts_path,
        [
            _attempt(
                "e1",
                20.0,
                0,
            )
        ],
    )

    board_path = (
        match
        / "tracking"
        / "board-occupancy-tracker-0.13.5.jsonl"
    )
    bench_path = (
        match
        / "tracking"
        / "bench-occupancy-tracker-0.13.5.jsonl"
    )
    _write_jsonl(
        board_path,
        [
            _board_state(
                "e1",
                20.0,
                scene_valid=False,
            )
        ],
    )
    _write_jsonl(
        bench_path,
        [
            _bench_state(
                "e1",
                20.0,
            )
        ],
    )

    tracker_summary = (
        match
        / "tracking"
        / "board-bench-occupancy-tracker-0.13.5_summary.json"
    )
    tracker_summary.write_text(
        json.dumps(
            {
                "source_attempts_path": str(attempts_path),
                "board_states_path": str(board_path),
                "bench_states_path": str(bench_path),
            }
        ),
        encoding="utf-8",
    )

    roster_path = (
        match
        / "features"
        / "roster-evidence-builder-0.20.1.jsonl"
    )
    _write_jsonl(
        roster_path,
        [],
    )
    roster_summary = (
        match
        / "features"
        / "roster-evidence-builder-0.20.1_summary.json"
    )
    roster_summary.write_text(
        json.dumps(
            {
                "producer_version": "roster-evidence-builder-0.20.1",
                "contexts_path": str(roster_path),
                "current_ownership_status": "not_established",
            }
        ),
        encoding="utf-8",
    )

    settings = SlotIdentityDatasetSettings(
        selected_occupancy_statuses=(
            "occupied",
            "empty",
        ),
        require_scene_valid=False,
    )
    summary = export_slot_identity_dataset(
        match,
        settings,
        board_tracker_summary_path=tracker_summary,
        roster_summary_path=roster_summary,
    )

    # board r0c0 occupied + r0c1 empty + bench b0 occupied
    assert summary["sample_count"] == 3
    assert summary["raw_occupancy_status_counts"] == {
        "empty": 1,
        "occupied": 2,
    }
    assert summary["occupancy_evidence_tier_counts"] == {
        "raw_candidate": 3,
    }
    assert summary["identity_training_recommended_sample_count"] == 0
    assert summary["identity_labeling_recommended_sample_count"] == 0
    assert summary["occupancy_review_recommended_sample_count"] == 3



def test_occupancy_quality_tiers_distinguish_current_carry_and_conflict():
    trusted = _occupancy_evidence_quality(
        location="bench",
        raw_status="occupied",
        tracked_status="occupied",
        tracked_is_current_evidence=True,
        scene_valid=True,
        board_strong_snapshot=False,
    )
    assert trusted == (
        "trusted",
        "raw_and_tracked_occupied_current_evidence",
        True,
        True,
        False,
    )

    supported = _occupancy_evidence_quality(
        location="bench",
        raw_status="occupied",
        tracked_status="occupied",
        tracked_is_current_evidence=False,
        scene_valid=True,
        board_strong_snapshot=False,
    )
    assert supported == (
        "supported",
        "raw_occupied_with_tracked_occupied_carry",
        True,
        False,
        False,
    )

    conflict = _occupancy_evidence_quality(
        location="board",
        raw_status="occupied",
        tracked_status="empty",
        tracked_is_current_evidence=False,
        scene_valid=True,
        board_strong_snapshot=False,
    )
    assert conflict[0] == "raw_candidate"
    assert conflict[1] == "raw_occupied_conflicts_tracked_empty_carry"
    assert conflict[2:] == (
        False,
        False,
        True,
    )

    strong = _occupancy_evidence_quality(
        location="board",
        raw_status="occupied",
        tracked_status="occupied",
        tracked_is_current_evidence=False,
        scene_valid=True,
        board_strong_snapshot=True,
    )
    assert strong[0] == "trusted"
    assert strong[1] == "strong_board_snapshot_tracked_occupied"
    assert strong[3] is True


def test_label_contract_supports_no_unit_and_rejects_invalid_combinations():
    base = dict(
        sample_id="s1",
        match_id="m",
        timestamp_s=1.0,
        evidence_id="e1",
        location="board",
        slot_id="r0c0",
        board_row=0,
        board_col=0,
        source_frame_uri="frame.png",
        crop_uri="images/board/crop.png",
        crop_sha256="0" * 64,
        crop_width=40,
        crop_height=60,
        context_box=(0, 0, 40, 60),
        footprint_box=(5, 20, 35, 55),
        raw_occupancy_status="occupied",
        raw_occupancy_confidence=0.8,
        raw_occupancy_score=0.7,
        occupancy_evidence_tier="raw_candidate",
        occupancy_evidence_reason="raw_occupied_without_tracked_support",
        recommended_for_occupancy_review=True,
        producer_version="slot-identity-dataset-exporter-0.21.1",
    )

    no_unit = SlotIdentityObservation(
        **base,
        label_status="human_labeled",
        target_type="no_unit",
        champion_label=None,
    )
    assert no_unit.target_type == "no_unit"

    champion = SlotIdentityObservation(
        **base,
        label_status="human_labeled",
        target_type="champion",
        champion_label="rhaast",
    )
    assert champion.champion_label == "rhaast"

    with pytest.raises(
        ValueError,
        match="requires champion_label",
    ):
        SlotIdentityObservation(
            **base,
            label_status="human_labeled",
            target_type="champion",
            champion_label=None,
        )

    with pytest.raises(
        ValueError,
        match="cannot carry champion_label",
    ):
        SlotIdentityObservation(
            **base,
            label_status="human_labeled",
            target_type="no_unit",
            champion_label="rhaast",
        )
