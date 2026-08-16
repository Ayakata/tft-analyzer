from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from tft_analyzer.storage import (
    find_latest_tracked_hud_file,
    iter_evidence_records,
    iter_tracked_hud_states,
)

from .background import (
    classify_foreground,
    fit_background_models,
    foreground_score,
)
from .models import (
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)
from .tracker import (
    TemporalOccupancyTracker,
)
from .scene_guard import (
    ArenaSceneGuardSettings,
    SCENE_GUARD_VERSION,
    fit_arena_scene_guard,
    save_arena_scene_guard,
)


_VERSION_RE = re.compile(
    r"(\d+)\.(\d+)\.(\d+)"
)
TRACKER_VERSION = (
    "board-bench-occupancy-tracker-0.13.5"
)
BACKGROUND_VERSION = (
    "board-bench-background-0.13.2"
)


@dataclass(
    frozen=True,
    slots=True,
)
class BoardOccupancyTrackerSettings:
    background_quantile: float = 0.22
    background_min_candidates: int = 12
    foreground_empty_below: float = 0.34
    foreground_occupied_above: float = 0.58
    confirmation_count: int = 2

    # Legacy visual stability gate. It remains useful when HUD context is not
    # available and as a weaker gate for under-cap snapshots.
    board_stable_frames_required: int = 1
    board_max_motion_cells: int = 10
    board_max_candidate_changes: int = 8
    board_max_uncertain_cells: int = 12
    board_motion_delta: float = 0.18
    board_min_known_candidates: int = 16

    # 0.13.1: TFT board capacity / planning context.
    use_hud_board_context: bool = True
    planning_min_round_age_s: float = 2.5
    planning_max_round_age_s: float = 32.0
    full_level_snapshot_max_uncertain: int = 14
    full_level_snapshot_min_mean_fg: float = 0.60

    # 0.13.4 match-local arena scene guard. The template is fitted from the
    # match's own static arena anchors and rejects full-screen/non-arena scenes.
    use_arena_scene_guard: bool = True
    scene_guard_descriptor_size: int = 48
    scene_guard_reference_fraction: float = 0.60
    scene_guard_score_threshold: float = 0.12
    scene_guard_anchor_threshold: float = 0.15
    scene_guard_min_anchor_pass: int = 3


@dataclass(
    frozen=True,
    slots=True,
)
class _HUDBoardContext:
    level: int | None = None
    stage: str | None = None
    round_age_s: float | None = None


def _version_key(
    path: Path,
):
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


def find_latest_attempts(
    match_dir: Path | str,
) -> Path:
    observations = (
        Path(match_dir)
        / "observations"
    )
    candidates = list(
        observations.glob(
            "board-bench-occupancy-*_attempts.jsonl"
        )
    )
    if not candidates:
        raise FileNotFoundError(
            "No board-bench occupancy attempts "
            f"found in {observations}; "
            "run perceive-board first."
        )
    return max(
        candidates,
        key=_version_key,
    )


def _load_attempts(
    path: Path,
) -> list[dict]:
    values = []
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            if (
                item.get("sampling_mode")
                == "footprint"
            ):
                values.append(item)
    if not values:
        raise ValueError(
            f"No footprint attempts in {path}"
        )
    return values


def _samples(
    attempts: list[dict],
    key: str,
    position_fn,
):
    result = defaultdict(list)
    for frame in attempts:
        for item in frame.get(key, []):
            result[
                position_fn(item)
            ].append(item)
    return dict(result)


def _write_jsonl(
    path: Path,
    values,
) -> None:
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )
    with tmp.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        for value in values:
            payload = (
                value.model_dump(
                    mode="json"
                )
                if hasattr(
                    value,
                    "model_dump",
                )
                else value
            )
            f.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp.replace(path)


def _score_stats(
    values: list[float],
) -> dict[str, float]:
    if not values:
        return {
            "mean": 0.0,
            "q10": 0.0,
            "q50": 0.0,
            "q90": 0.0,
        }

    ordered = sorted(
        float(v)
        for v in values
    )

    def q(
        p: float,
    ) -> float:
        if len(ordered) == 1:
            return ordered[0]
        x = p * (
            len(ordered) - 1
        )
        lo = int(x)
        hi = min(
            lo + 1,
            len(ordered) - 1,
        )
        frac = x - lo
        return (
            ordered[lo]
            * (1.0 - frac)
            + ordered[hi]
            * frac
        )

    return {
        "mean": (
            sum(ordered)
            / len(ordered)
        ),
        "q10": q(0.10),
        "q50": q(0.50),
        "q90": q(0.90),
    }


def _stage_key(
    value,
) -> str | None:
    if value is None:
        return None

    if isinstance(value, dict):
        stage = value.get("stage")
        round_ = value.get("round")
        if (
            stage is not None
            and round_ is not None
        ):
            return (
                f"{int(stage)}-"
                f"{int(round_)}"
            )

    if isinstance(
        value,
        str,
    ):
        value = value.strip()
        if value:
            return value

    return None


def _level_value(
    value,
) -> int | None:
    """
    Normalize the tracked HUD level contract.

    Canonical HUD semantic value:
        {"level": 8}

    Scalar support is retained only for compatibility with older/tests data.
    """
    if isinstance(value, dict):
        value = value.get("level")

    if isinstance(
        value,
        bool,
    ):
        return None

    if isinstance(
        value,
        (int, float),
    ):
        value = int(value)
        if 1 <= value <= 10:
            return value

    return None


def _load_hud_context(
    match_dir: Path,
    *,
    hud_states_path: Path | str | None,
    enabled: bool,
) -> tuple[
    dict[str, _HUDBoardContext],
    Path | None,
]:
    if not enabled:
        return {}, None

    path: Path | None
    if hud_states_path is not None:
        path = Path(
            hud_states_path
        )
    else:
        try:
            path = (
                find_latest_tracked_hud_file(
                    match_dir
                )
            )
        except FileNotFoundError:
            return {}, None

    states = list(
        iter_tracked_hud_states(path)
    )
    if not states:
        return {}, path

    by_evidence: dict[
        str,
        _HUDBoardContext,
    ] = {}

    current_stage: str | None = None
    current_stage_start: (
        float | None
    ) = None

    for state in states:
        stage = _stage_key(
            state.stage.value
        )
        if stage is not None:
            if stage != current_stage:
                current_stage = stage
                current_stage_start = float(
                    state.timestamp_s
                )

        level = _level_value(
            state.level.value
        )

        age = None
        if (
            current_stage is not None
            and current_stage_start
            is not None
        ):
            age = max(
                0.0,
                float(
                    state.timestamp_s
                )
                - current_stage_start,
            )

        if state.evidence_id:
            by_evidence[
                str(state.evidence_id)
            ] = _HUDBoardContext(
                level=level,
                stage=current_stage,
                round_age_s=age,
            )

    return by_evidence, path


def _capacity_status(
    *,
    occupied_count: int,
    level: int | None,
) -> str:
    if level is None:
        return "unknown"
    if occupied_count > level:
        return "over"
    if occupied_count == level:
        return "at"
    return "under"


def track_match_board_occupancy(
    match_dir: Path | str,
    settings: BoardOccupancyTrackerSettings,
    *,
    attempts_path: Path | str | None = None,
    hud_states_path: Path | str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    attempts_path = (
        Path(attempts_path)
        if attempts_path
        else find_latest_attempts(
            match_dir
        )
    )
    attempts = _load_attempts(
        attempts_path
    )

    board_samples = _samples(
        attempts,
        "board_cells",
        lambda x: (
            f"{int(x['row'])},"
            f"{int(x['col'])}"
        ),
    )
    bench_samples = _samples(
        attempts,
        "bench_slots",
        lambda x: str(
            int(x["slot_index"])
        ),
    )

    board_models = (
        fit_background_models(
            board_samples,
            source_quantile=(
                settings.background_quantile
            ),
            min_candidates=(
                settings.background_min_candidates
            ),
        )
    )
    bench_models = (
        fit_background_models(
            bench_samples,
            source_quantile=(
                settings.background_quantile
            ),
            min_candidates=(
                settings.background_min_candidates
            ),
        )
    )

    (
        hud_context_by_evidence,
        resolved_hud_states_path,
    ) = _load_hud_context(
        match_dir,
        hud_states_path=hud_states_path,
        enabled=(
            settings.use_hud_board_context
        ),
    )

    evidence_records = {}

    scene_guard_model = None
    scene_results = {}
    scene_guard_output = None

    if settings.use_arena_scene_guard:
        evidence_records = {
            str(record.evidence.evidence_id): record
            for record in iter_evidence_records(match_dir)
        }

        evidence_paths = []
        seen_evidence_ids = set()
        for frame in attempts:
            evidence_id = str(frame.get("evidence_id", ""))
            if not evidence_id or evidence_id in seen_evidence_ids:
                continue
            record = evidence_records.get(evidence_id)
            if record is None:
                continue
            path = match_dir / record.evidence.uri
            if not path.exists():
                continue
            seen_evidence_ids.add(evidence_id)
            evidence_paths.append((evidence_id, path))

        if evidence_paths:
            scene_guard_model, scene_results = fit_arena_scene_guard(
                evidence_paths,
                settings=ArenaSceneGuardSettings(
                    descriptor_size=settings.scene_guard_descriptor_size,
                    reference_fraction=settings.scene_guard_reference_fraction,
                    score_threshold=settings.scene_guard_score_threshold,
                    anchor_threshold=settings.scene_guard_anchor_threshold,
                    min_anchor_pass=settings.scene_guard_min_anchor_pass,
                ),
            )

    board_tracker = (
        TemporalOccupancyTracker(
            confirmation_count=(
                settings.confirmation_count
            )
        )
    )
    bench_tracker = (
        TemporalOccupancyTracker(
            confirmation_count=(
                settings.confirmation_count
            )
        )
    )

    board_states = []
    bench_states = []
    decisions = []

    previous_board_fg: dict[
        str,
        float,
    ] = {}
    stable_frame_run = 0

    raw_board_changes = 0
    raw_bench_changes = 0
    previous_board_signature = None
    previous_bench_signature = None

    usable_board_frames = 0
    unstable_board_frames = 0
    warming_board_frames = 0
    board_motion_values = []
    board_change_values = []

    board_candidate_status = Counter()
    bench_candidate_status = Counter()
    board_position_status = defaultdict(
        Counter
    )
    bench_position_status = defaultdict(
        Counter
    )
    board_position_fg = defaultdict(
        list
    )
    bench_position_fg = defaultdict(
        list
    )

    gate_reason_counts = Counter()
    hud_aligned_frames = 0
    hud_level_known_frames = 0
    strong_snapshot_frames = 0
    capacity_over_frames = 0
    inferred_empty_total = 0
    tracked_over_level_frames = 0

    scene_valid_frames = 0
    scene_invalid_frames = 0
    scene_invalid_full_level_candidates = 0
    scene_score_values = []

    bench_scene_blocked_frames = 0
    bench_scene_blocked_positions = 0

    board_positions = [
        f"{r},{c}"
        for r in range(4)
        for c in range(7)
    ]

    for frame in attempts:
        ts = float(
            frame["timestamp_s"]
        )
        evidence_id = str(
            frame["evidence_id"]
        )
        match_id = str(
            frame.get("match_id")
            or match_dir.name
        )

        board_candidates = {}
        board_fg = {}
        board_raw = {}
        board_conf = {}

        for cell in frame.get(
            "board_cells",
            [],
        ):
            pos = (
                f"{int(cell['row'])},"
                f"{int(cell['col'])}"
            )
            model = board_models.get(pos)
            if model is None:
                continue

            fg = foreground_score(
                cell,
                model,
            )
            (
                status,
                conf,
            ) = classify_foreground(
                fg,
                empty_below=(
                    settings.foreground_empty_below
                ),
                occupied_above=(
                    settings.foreground_occupied_above
                ),
            )

            board_candidates[pos] = (
                status
            )
            board_fg[pos] = fg
            board_raw[pos] = float(
                cell.get(
                    "score",
                    0.0,
                )
            )
            board_conf[pos] = conf

        bench_candidates = {}
        bench_fg = {}
        bench_raw = {}
        bench_conf = {}

        for slot in frame.get(
            "bench_slots",
            [],
        ):
            pos = str(
                int(
                    slot[
                        "slot_index"
                    ]
                )
            )
            model = bench_models.get(pos)
            if model is None:
                continue

            fg = foreground_score(
                slot,
                model,
            )
            (
                status,
                conf,
            ) = classify_foreground(
                fg,
                empty_below=(
                    settings.foreground_empty_below
                ),
                occupied_above=(
                    settings.foreground_occupied_above
                ),
            )

            bench_candidates[pos] = (
                status
            )
            bench_fg[pos] = fg
            bench_raw[pos] = float(
                slot.get(
                    "score",
                    0.0,
                )
            )
            bench_conf[pos] = conf

        for (
            pos,
            status,
        ) in board_candidates.items():
            board_candidate_status[
                status
            ] += 1
            board_position_status[
                pos
            ][status] += 1
            board_position_fg[
                pos
            ].append(
                board_fg[pos]
            )

        for (
            pos,
            status,
        ) in bench_candidates.items():
            bench_candidate_status[
                status
            ] += 1
            bench_position_status[
                pos
            ][status] += 1
            bench_position_fg[
                pos
            ].append(
                bench_fg[pos]
            )

        board_sig = tuple(
            board_candidates.get(
                f"{r},{c}",
                "unknown",
            )
            for r in range(4)
            for c in range(7)
        )
        bench_sig = tuple(
            bench_candidates.get(
                str(i),
                "unknown",
            )
            for i in range(9)
        )

        raw_board_changes += int(
            previous_board_signature
            is not None
            and board_sig
            != previous_board_signature
        )
        raw_bench_changes += int(
            previous_bench_signature
            is not None
            and bench_sig
            != previous_bench_signature
        )
        previous_board_signature = (
            board_sig
        )
        previous_bench_signature = (
            bench_sig
        )

        uncertain_count = sum(
            s == "uncertain"
            for s in (
                board_candidates.values()
            )
        )
        known_count = sum(
            s in (
                "empty",
                "occupied",
            )
            for s in (
                board_candidates.values()
            )
        )
        candidate_occupied_count = sum(
            s == "occupied"
            for s in (
                board_candidates.values()
            )
        )

        occupied_fg_values = [
            board_fg[pos]
            for (
                pos,
                status,
            ) in (
                board_candidates.items()
            )
            if status == "occupied"
        ]
        mean_occupied_fg = (
            sum(
                occupied_fg_values
            )
            / len(
                occupied_fg_values
            )
            if occupied_fg_values
            else 0.0
        )

        motion_count = 0
        for (
            pos,
            fg,
        ) in board_fg.items():
            if (
                pos in previous_board_fg
                and abs(
                    fg
                    - previous_board_fg[pos]
                )
                >= settings.board_motion_delta
            ):
                motion_count += 1

        candidate_change_count = 0
        for (
            pos,
            candidate,
        ) in board_candidates.items():
            current = (
                board_tracker
                .snapshot(pos)
                .status
            )
            if (
                current
                in (
                    "empty",
                    "occupied",
                )
                and candidate
                in (
                    "empty",
                    "occupied",
                )
                and current
                != candidate
            ):
                candidate_change_count += 1

        board_motion_values.append(
            motion_count
        )
        board_change_values.append(
            candidate_change_count
        )

        visual_stable = (
            known_count
            >= settings.board_min_known_candidates
            and uncertain_count
            <= settings.board_max_uncertain_cells
            and motion_count
            <= settings.board_max_motion_cells
            and candidate_change_count
            <= settings.board_max_candidate_changes
        )

        hud_context = (
            hud_context_by_evidence.get(
                evidence_id
            )
        )
        hud_level = (
            hud_context.level
            if hud_context
            else None
        )
        hud_stage = (
            hud_context.stage
            if hud_context
            else None
        )
        round_age_s = (
            hud_context.round_age_s
            if hud_context
            else None
        )

        if hud_context is not None:
            hud_aligned_frames += 1
        if hud_level is not None:
            hud_level_known_frames += 1

        capacity_status = (
            _capacity_status(
                occupied_count=(
                    candidate_occupied_count
                ),
                level=hud_level,
            )
        )
        if capacity_status == "over":
            capacity_over_frames += 1

        scene_result = scene_results.get(evidence_id)
        if scene_result is None:
            scene_valid = True
            scene_score = None
            scene_anchor_pass_count = None
        else:
            scene_valid = bool(scene_result.valid)
            scene_score = float(scene_result.score)
            scene_anchor_pass_count = int(
                scene_result.anchor_pass_count
            )
            scene_score_values.append(scene_score)

        if scene_valid:
            scene_valid_frames += 1
        else:
            scene_invalid_frames += 1
            if (
                hud_level is not None
                and candidate_occupied_count == hud_level
            ):
                scene_invalid_full_level_candidates += 1

        planning_window = (
            round_age_s is not None
            and (
                settings.planning_min_round_age_s
                <= round_age_s
                <= settings.planning_max_round_age_s
            )
        )

        strong_snapshot = (
            scene_valid
            and hud_level is not None
            and planning_window
            and candidate_occupied_count
            == hud_level
            and uncertain_count
            <= settings.full_level_snapshot_max_uncertain
            and mean_occupied_fg
            >= settings.full_level_snapshot_min_mean_fg
        )

        hud_gate_active = (
            settings.use_hud_board_context
            and hud_context is not None
            and hud_level is not None
            and round_age_s is not None
        )

        if not scene_valid:
            frame_stable = False
            gate_reason = "scene_invalid"
        elif hud_gate_active:
            if capacity_status == "over":
                frame_stable = False
                gate_reason = (
                    "level_capacity_exceeded"
                )
            elif not planning_window:
                frame_stable = False
                gate_reason = (
                    "outside_planning_window"
                )
            elif strong_snapshot:
                frame_stable = True
                gate_reason = (
                    "full_level_snapshot"
                )
            elif visual_stable:
                frame_stable = True
                gate_reason = (
                    "planning_visual_stable"
                )
            else:
                frame_stable = False
                gate_reason = (
                    "planning_visual_unstable"
                )
        else:
            frame_stable = visual_stable
            gate_reason = (
                "visual_fallback_stable"
                if visual_stable
                else "visual_fallback_unstable"
            )

        if frame_stable:
            stable_frame_run += 1
        else:
            stable_frame_run = 0

        if strong_snapshot:
            board_usable = True
        else:
            board_usable = (
                stable_frame_run
                >= settings.board_stable_frames_required
            )

        stability = (
            "stable"
            if board_usable
            else (
                "unstable"
                if not frame_stable
                else "warming"
            )
        )

        if board_usable:
            usable_board_frames += 1
        elif stability == "unstable":
            unstable_board_frames += 1
        else:
            warming_board_frames += 1

        gate_reason_counts[
            gate_reason
        ] += 1

        inferred_empty_count = 0

        if strong_snapshot:
            strong_snapshot_frames += 1

            # A full-level board is a whole-snapshot invariant. Independent
            # per-cell carry-over would create impossible Frankenstein states
            # (e.g. 11 occupied while HUD level is 8). Replace the canonical
            # snapshot atomically.
            for pos in board_positions:
                candidate = (
                    board_candidates.get(
                        pos,
                        "uncertain",
                    )
                )

                if candidate == "occupied":
                    target = "occupied"
                    reason = (
                        "full_level_snapshot"
                    )
                    conf = board_conf[pos]
                else:
                    target = "empty"
                    if candidate == "empty":
                        reason = (
                            "full_level_snapshot"
                        )
                        conf = board_conf[pos]
                    else:
                        reason = (
                            "level_cap_inferred_empty"
                        )
                        conf = 0.55
                        inferred_empty_count += 1

                d = (
                    board_tracker.force_status(
                        position=pos,
                        status=target,
                        confidence=conf,
                        foreground_score=(
                            board_fg.get(
                                pos,
                                0.0,
                            )
                        ),
                        raw_score=(
                            board_raw.get(
                                pos,
                                0.0,
                            )
                        ),
                        timestamp_s=ts,
                        evidence_id=evidence_id,
                        reason=reason,
                    )
                )
                decisions.append({
                    "timestamp_s": ts,
                    "evidence_id": evidence_id,
                    "domain": "board",
                    **asdict(d),
                })

            inferred_empty_total += (
                inferred_empty_count
            )

        else:
            # For ordinary usable frames we keep temporal confirmation.
            # Empty candidates are processed before additions so capacity can
            # be released before a unit appears in a different cell.
            ordered_positions = sorted(
                board_positions,
                key=lambda pos: {
                    "empty": 0,
                    "uncertain": 1,
                    "occupied": 2,
                }.get(
                    board_candidates.get(
                        pos,
                        "uncertain",
                    ),
                    1,
                ),
            )

            for pos in ordered_positions:
                if pos not in board_candidates:
                    continue

                candidate = (
                    board_candidates[pos]
                )
                allow_change = board_usable
                blocked_reason = (
                    "board_frame_unstable"
                )

                if (
                    board_usable
                    and hud_level is not None
                    and candidate
                    == "occupied"
                    and (
                        board_tracker
                        .snapshot(pos)
                        .status
                        != "occupied"
                    )
                ):
                    current_occupied = sum(
                        board_tracker
                        .snapshot(p)
                        .status
                        == "occupied"
                        for p in board_positions
                    )
                    if (
                        current_occupied
                        >= hud_level
                    ):
                        allow_change = False
                        blocked_reason = (
                            "level_capacity_guard"
                        )

                d = board_tracker.ingest(
                    position=pos,
                    candidate_status=candidate,
                    confidence=(
                        board_conf[pos]
                    ),
                    foreground_score=(
                        board_fg[pos]
                    ),
                    raw_score=(
                        board_raw[pos]
                    ),
                    timestamp_s=ts,
                    evidence_id=evidence_id,
                    allow_change=allow_change,
                    blocked_reason=(
                        blocked_reason
                    ),
                )
                decisions.append({
                    "timestamp_s": ts,
                    "evidence_id": evidence_id,
                    "domain": "board",
                    **asdict(d),
                })

        if not scene_valid and bench_candidates:
            bench_scene_blocked_frames += 1

        for pos in [
            str(i)
            for i in range(9)
        ]:
            if pos not in bench_candidates:
                continue

            if not scene_valid:
                # The bench is not semantically observable on full-screen /
                # non-arena scenes. Keep raw candidate diagnostics, but do not
                # mutate or refresh canonical/pending bench state.
                d = bench_tracker.carry(
                    position=pos,
                    candidate_status=(
                        bench_candidates[pos]
                    ),
                    confidence=(
                        bench_conf[pos]
                    ),
                    reason="scene_invalid",
                )
                bench_scene_blocked_positions += 1
            else:
                d = bench_tracker.ingest(
                    position=pos,
                    candidate_status=(
                        bench_candidates[pos]
                    ),
                    confidence=(
                        bench_conf[pos]
                    ),
                    foreground_score=(
                        bench_fg[pos]
                    ),
                    raw_score=(
                        bench_raw[pos]
                    ),
                    timestamp_s=ts,
                    evidence_id=evidence_id,
                    allow_change=True,
                )

            decisions.append({
                "timestamp_s": ts,
                "evidence_id": evidence_id,
                "domain": "bench",
                **asdict(d),
            })

        board_cells = tuple(
            board_tracker.snapshot(
                f"{r},{c}"
            )
            for r in range(4)
            for c in range(7)
        )
        bench_slots = tuple(
            bench_tracker.snapshot(
                str(i)
            )
            for i in range(9)
        )

        tracked_occupied_count = sum(
            c.status == "occupied"
            for c in board_cells
        )
        if (
            hud_level is not None
            and tracked_occupied_count
            > hud_level
        ):
            tracked_over_level_frames += 1

        board_states.append(
            TrackedBoardOccupancyState(
                match_id=match_id,
                timestamp_s=ts,
                evidence_id=evidence_id,
                usable=board_usable,
                stability=stability,
                gate_reason=gate_reason,
                motion_count=motion_count,
                candidate_change_count=(
                    candidate_change_count
                ),
                uncertain_count=(
                    uncertain_count
                ),
                candidate_occupied_count=(
                    candidate_occupied_count
                ),
                occupied_count=(
                    tracked_occupied_count
                ),
                hud_level=hud_level,
                hud_stage=hud_stage,
                round_age_s=round_age_s,
                capacity_status=(
                    capacity_status
                ),
                strong_snapshot=(
                    strong_snapshot
                ),
                inferred_empty_count=(
                    inferred_empty_count
                ),
                scene_valid=scene_valid,
                scene_score=scene_score,
                scene_anchor_pass_count=(
                    scene_anchor_pass_count
                ),
                cells=board_cells,
                tracker_version=(
                    TRACKER_VERSION
                ),
            )
        )

        bench_states.append(
            TrackedBenchOccupancyState(
                match_id=match_id,
                timestamp_s=ts,
                evidence_id=evidence_id,
                uncertain_count=sum(
                    s == "uncertain"
                    for s in (
                        bench_candidates.values()
                    )
                ),
                occupied_count=sum(
                    s.status == "occupied"
                    for s in bench_slots
                ),
                slots=bench_slots,
                tracker_version=(
                    TRACKER_VERSION
                ),
            )
        )

        previous_board_fg = board_fg

    out_dir = (
        match_dir
        / "tracking"
    )
    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if scene_guard_model is not None:
        scene_guard_output = save_arena_scene_guard(
            scene_guard_model,
            scene_results,
            out_dir / SCENE_GUARD_VERSION,
        )

    background_path = (
        out_dir
        / f"{BACKGROUND_VERSION}.json"
    )
    board_path = (
        out_dir
        / "board-occupancy-tracker-0.13.5.jsonl"
    )
    bench_path = (
        out_dir
        / "bench-occupancy-tracker-0.13.5.jsonl"
    )
    decisions_path = (
        out_dir
        / f"{TRACKER_VERSION}_decisions.jsonl"
    )
    summary_path = (
        out_dir
        / f"{TRACKER_VERSION}_summary.json"
    )

    background_payload = {
        "schema_version": 2,
        "background_version": (
            BACKGROUND_VERSION
        ),
        "source_attempts_path": str(
            attempts_path
        ),
        "hud_states_path": (
            str(
                resolved_hud_states_path
            )
            if resolved_hud_states_path
            is not None
            else None
        ),
        "settings": asdict(settings),
        "board": {
            k: v.model_dump(
                mode="json"
            )
            for (
                k,
                v,
            ) in board_models.items()
        },
        "bench": {
            k: v.model_dump(
                mode="json"
            )
            for (
                k,
                v,
            ) in bench_models.items()
        },
    }
    background_path.write_text(
        json.dumps(
            background_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _write_jsonl(
        board_path,
        board_states,
    )
    _write_jsonl(
        bench_path,
        bench_states,
    )
    _write_jsonl(
        decisions_path,
        decisions,
    )

    action_counts = Counter(
        d["action"]
        for d in decisions
    )
    reason_counts = Counter(
        d["reason"]
        for d in decisions
    )
    domain_actions = {
        domain: Counter(
            d["action"]
            for d in decisions
            if d["domain"] == domain
        )
        for domain in (
            "board",
            "bench",
        )
    }

    accepted_changes = {
        domain: sum(
            d["action"]
            == "accepted"
            and d["previous_status"]
            in (
                "empty",
                "occupied",
            )
            and d["resulting_status"]
            != d["previous_status"]
            for d in decisions
            if d["domain"] == domain
        )
        for domain in (
            "board",
            "bench",
        )
    }

    board_semantic_changes = sum(
        a.usable
        and b.usable
        and tuple(
            c.status
            for c in a.cells
        )
        != tuple(
            c.status
            for c in b.cells
        )
        for (
            a,
            b,
        ) in zip(
            board_states,
            board_states[1:],
        )
    )
    bench_semantic_changes = sum(
        tuple(
            c.status
            for c in a.slots
        )
        != tuple(
            c.status
            for c in b.slots
        )
        for (
            a,
            b,
        ) in zip(
            bench_states,
            bench_states[1:],
        )
    )

    summary = {
        "schema_version": 2,
        "tracker_version": (
            TRACKER_VERSION
        ),
        "background_version": (
            BACKGROUND_VERSION
        ),
        "source_attempts_path": str(
            attempts_path
        ),
        "hud_states_path": (
            str(
                resolved_hud_states_path
            )
            if resolved_hud_states_path
            is not None
            else None
        ),
        "frame_count": len(attempts),
        "background_model_counts": {
            "board": len(
                board_models
            ),
            "bench": len(
                bench_models
            ),
        },
        "raw_candidate_snapshot_changes": {
            "board": raw_board_changes,
            "bench": raw_bench_changes,
        },
        "background_relative_candidate_status_counts": {
            "board": dict(
                board_candidate_status
            ),
            "bench": dict(
                bench_candidate_status
            ),
        },
        "board_position_candidate_status_counts": {
            k: dict(v)
            for (
                k,
                v,
            ) in board_position_status.items()
        },
        "bench_position_candidate_status_counts": {
            k: dict(v)
            for (
                k,
                v,
            ) in bench_position_status.items()
        },
        "board_position_foreground_score_stats": {
            k: _score_stats(v)
            for (
                k,
                v,
            ) in board_position_fg.items()
        },
        "bench_position_foreground_score_stats": {
            k: _score_stats(v)
            for (
                k,
                v,
            ) in bench_position_fg.items()
        },
        "tracked_snapshot_changes": {
            "board": (
                board_semantic_changes
            ),
            "bench": (
                bench_semantic_changes
            ),
        },
        "board_gate": {
            "usable_frames": (
                usable_board_frames
            ),
            "warming_frames": (
                warming_board_frames
            ),
            "unstable_frames": (
                unstable_board_frames
            ),
            "usable_rate": (
                usable_board_frames
                / len(attempts)
                if attempts
                else 0.0
            ),
            "gate_reason_counts": dict(
                gate_reason_counts
            ),
            "hud_aligned_frames": (
                hud_aligned_frames
            ),
            "hud_level_known_frames": (
                hud_level_known_frames
            ),
            "strong_snapshot_frames": (
                strong_snapshot_frames
            ),
            "capacity_over_frames": (
                capacity_over_frames
            ),
            "tracked_over_level_frames": (
                tracked_over_level_frames
            ),
            "inferred_empty_total": (
                inferred_empty_total
            ),
            "scene_valid_frames": (
                scene_valid_frames
            ),
            "scene_invalid_frames": (
                scene_invalid_frames
            ),
            "scene_invalid_full_level_candidates": (
                scene_invalid_full_level_candidates
            ),
            "scene_score_stats": (
                _score_stats(scene_score_values)
            ),
            "motion_count_stats": (
                _score_stats(
                    board_motion_values
                )
            ),
            "candidate_change_count_stats": (
                _score_stats(
                    board_change_values
                )
            ),
        },
        "decision_actions": dict(
            action_counts
        ),
        "decision_reasons": dict(
            reason_counts
        ),
        "domain_decision_actions": {
            k: dict(v)
            for (
                k,
                v,
            ) in domain_actions.items()
        },
        "accepted_semantic_changes": (
            accepted_changes
        ),
        "bench_scene_guard": {
            "blocked_frames": bench_scene_blocked_frames,
            "blocked_positions": bench_scene_blocked_positions,
        },
        "final_board_occupied_count": (
            board_states[-1].occupied_count
            if board_states
            else 0
        ),
        "final_bench_occupied_count": (
            bench_states[-1].occupied_count
            if bench_states
            else 0
        ),
        "background_path": str(
            background_path
        ),
        "board_states_path": str(
            board_path
        ),
        "bench_states_path": str(
            bench_path
        ),
        "decisions_path": str(
            decisions_path
        ),
        "summary_path": str(
            summary_path
        ),
        "scene_guard_version": (
            SCENE_GUARD_VERSION
            if scene_guard_model is not None
            else None
        ),
        "scene_guard_path": (
            scene_guard_output["scene_guard_path"]
            if scene_guard_output is not None
            else None
        ),
    }

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return summary
