from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
import json
from pathlib import Path
import re

from tft_analyzer.storage import (
    find_latest_tracked_hud_file,
    iter_tracked_hud_states,
)
from tft_analyzer.game_data import (
    load_champion_cost_catalog,
    resolve_game_context,
)
from tft_analyzer.tracking.board import (
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)

from .fusion import (
    ActionFusionEngine,
    ActionFusionSettings,
    FusionSnapshot,
)
from .models import EconomyLedgerWindow


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version_key(path: Path) -> tuple[int, int, int, float]:
    matches = list(_VERSION_RE.finditer(path.name))
    version = (
        tuple(int(x) for x in matches[-1].groups())
        if matches
        else (0, 0, 0)
    )
    return (*version, path.stat().st_mtime)


def _find_latest(
    match_dir: Path,
    pattern: str,
    *,
    exclude: tuple[str, ...] = ("_summary", "_decisions"),
) -> Path:
    tracking = match_dir / "tracking"
    candidates = [
        p
        for p in tracking.glob(pattern)
        if not any(token in p.name for token in exclude)
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No files matching {pattern!r} in {tracking}"
        )
    return max(candidates, key=_version_key)


def find_latest_board_states(match_dir: Path | str) -> Path:
    return _find_latest(
        Path(match_dir),
        "board-occupancy-tracker-*.jsonl",
    )


def find_latest_bench_states(match_dir: Path | str) -> Path:
    return _find_latest(
        Path(match_dir),
        "bench-occupancy-tracker-*.jsonl",
    )


def _iter_board(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield TrackedBoardOccupancyState.model_validate_json(line)


def _iter_bench(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield TrackedBenchOccupancyState.model_validate_json(line)


def _stage_value(field) -> str | None:
    value = field.value
    if not isinstance(value, dict):
        return None
    stage = value.get("stage")
    round_ = value.get("round")
    if stage is None or round_ is None:
        return None
    return f"{int(stage)}-{int(round_)}"


def _int_field(field, key: str) -> int | None:
    value = field.value
    if not isinstance(value, dict):
        return None
    raw = value.get(key)
    if raw is None:
        return None
    return int(raw)


def _xp(field) -> tuple[int | None, int | None]:
    value = field.value
    if not isinstance(value, dict):
        return None, None
    current = value.get("current")
    required = value.get("required")
    return (
        int(current) if current is not None else None,
        int(required) if required is not None else None,
    )


def _shop(field) -> tuple[str | None, ...]:
    value = field.value
    if not isinstance(value, dict):
        return ()
    slots = value.get("slots")
    if not isinstance(slots, (list, tuple)):
        return ()
    return tuple(
        str(item) if item is not None else None
        for item in slots
    )


def _occupied_positions(items) -> frozenset[str]:
    return frozenset(
        item.position
        for item in items
        if item.status == "occupied"
    )


def _build_snapshot(hud, board, bench) -> FusionSnapshot:
    xp_current, xp_required = _xp(hud.xp)

    return FusionSnapshot(
        match_id=hud.match_id,
        timestamp_s=float(board.timestamp_s),
        evidence_id=str(board.evidence_id),
        stage=_stage_value(hud.stage),
        stage_status=hud.stage.status,
        gold=_int_field(hud.gold, "gold"),
        gold_status=hud.gold.status,
        level=_int_field(hud.level, "level"),
        level_status=hud.level.status,
        xp_current=xp_current,
        xp_required=xp_required,
        xp_status=hud.xp.status,
        xp_absolute=None,
        shop_slots=_shop(hud.shop),
        shop_status=hud.shop.status,
        board_count=int(board.occupied_count),
        board_cells=_occupied_positions(board.cells),
        board_usable=bool(board.usable),
        scene_valid=bool(board.scene_valid),
        bench_count=int(bench.occupied_count),
        bench_slots=_occupied_positions(bench.slots),
    )


def _build_xp_requirement_map(
    snapshots: list[FusionSnapshot],
) -> dict[int, int]:
    """
    Infer the match-local XP requirement for each observed level.

    HUD's `required` value is interpreted as XP needed to advance from that
    level to the next. Use the mode per level so occasional OCR noise does not
    redefine the progression.
    """
    votes: dict[int, Counter] = defaultdict(Counter)

    for snapshot in snapshots:
        if (
            snapshot.level is None
            or snapshot.xp_required is None
            or snapshot.xp_required <= 0
        ):
            continue
        votes[int(snapshot.level)][int(snapshot.xp_required)] += 1

    result: dict[int, int] = {}
    for level, counts in votes.items():
        required, _ = counts.most_common(1)[0]
        result[level] = int(required)

    return result


def _absolute_xp(
    snapshot: FusionSnapshot,
    requirement_map: dict[int, int],
    *,
    base_level: int,
) -> int | None:
    if snapshot.level is None or snapshot.xp_current is None:
        return None
    level = int(snapshot.level)

    if level < base_level:
        return None

    total = int(snapshot.xp_current)
    for current_level in range(base_level, level):
        required = requirement_map.get(current_level)
        if required is None:
            return None
        total += int(required)

    return total


def _enrich_absolute_xp(
    snapshots: list[FusionSnapshot],
) -> tuple[list[FusionSnapshot], dict[int, int], int | None]:
    levels = [
        int(snapshot.level)
        for snapshot in snapshots
        if snapshot.level is not None
    ]
    if not levels:
        return snapshots, {}, None

    requirement_map = _build_xp_requirement_map(snapshots)
    base_level = min(levels)

    enriched = [
        replace(
            snapshot,
            xp_absolute=_absolute_xp(
                snapshot,
                requirement_map,
                base_level=base_level,
            ),
        )
        for snapshot in snapshots
    ]
    return enriched, requirement_map, base_level


def _write_jsonl(path: Path, values) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for value in values:
            payload = (
                value.model_dump(mode="json")
                if hasattr(value, "model_dump")
                else value
            )
            f.write(
                json.dumps(payload, ensure_ascii=False)
                + "\n"
            )
    tmp.replace(path)


def infer_match_actions(
    match_dir: Path | str,
    settings: ActionFusionSettings,
    *,
    hud_states_path: Path | str | None = None,
    board_states_path: Path | str | None = None,
    bench_states_path: Path | str | None = None,
    champion_catalog_path: Path | str | None = None,
    explicit_set: str | None = None,
    explicit_patch: str | None = None,
    config_set: str | None = None,
    config_patch: str | None = None,
    allow_auto_set: bool = True,
    force_game_context: bool = False,
) -> dict[str, object]:
    match_dir = Path(match_dir)

    hud_states_path = (
        Path(hud_states_path)
        if hud_states_path is not None
        else find_latest_tracked_hud_file(match_dir)
    )
    board_states_path = (
        Path(board_states_path)
        if board_states_path is not None
        else find_latest_board_states(match_dir)
    )
    bench_states_path = (
        Path(bench_states_path)
        if bench_states_path is not None
        else find_latest_bench_states(match_dir)
    )

    hud_by_evidence = {
        str(state.evidence_id): state
        for state in iter_tracked_hud_states(hud_states_path)
        if state.evidence_id
    }
    board_by_evidence = {
        str(state.evidence_id): state
        for state in _iter_board(board_states_path)
    }
    bench_by_evidence = {
        str(state.evidence_id): state
        for state in _iter_bench(bench_states_path)
    }

    common_ids = (
        set(hud_by_evidence)
        & set(board_by_evidence)
        & set(bench_by_evidence)
    )

    snapshots = [
        _build_snapshot(
            hud_by_evidence[evidence_id],
            board_by_evidence[evidence_id],
            bench_by_evidence[evidence_id],
        )
        for evidence_id in common_ids
    ]
    snapshots.sort(key=lambda x: x.timestamp_s)

    if len(snapshots) < 2:
        raise ValueError(
            "Need at least two evidence-aligned HUD/board/bench snapshots"
        )

    snapshots, xp_requirement_map, xp_base_level = _enrich_absolute_xp(
        snapshots
    )

    champion_catalog = (
        load_champion_cost_catalog(
            champion_catalog_path
        )
        if champion_catalog_path is not None
        else None
    )

    observed_roster_names = sorted(
        {
            champion
            for snapshot in snapshots
            for champion in snapshot.shop_slots
            if champion
        }
    )

    game_context = None
    if champion_catalog is not None:
        game_context = resolve_game_context(
            match_dir=match_dir,
            catalog=champion_catalog,
            observed_roster_names=observed_roster_names,
            explicit_set=explicit_set,
            explicit_patch=explicit_patch,
            config_set=config_set,
            config_patch=config_patch,
            allow_auto_inference=allow_auto_set,
            force_context=force_game_context,
        )

    engine = ActionFusionEngine(
        settings,
        champion_cost_catalog=champion_catalog,
        set_id=(
            game_context.set_id
            if game_context is not None
            else None
        ),
    )

    actions = []
    windows = []
    ledgers: list[EconomyLedgerWindow] = []

    for index, (prev, curr) in enumerate(
        zip(snapshots, snapshots[1:])
    ):
        result = engine.infer_pair(
            prev,
            curr,
            window_index=index,
        )
        actions.extend(result.actions)
        if result.diagnostic is not None:
            windows.append(result.diagnostic)
        if result.ledger is not None:
            ledgers.append(result.ledger)

    out_dir = match_dir / "actions"
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_version = (
        settings.producer_version
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    actions_path = out_dir / f"{safe_version}.jsonl"
    windows_path = out_dir / f"{safe_version}_windows.jsonl"
    ledger_path = out_dir / f"{safe_version}_ledger.jsonl"
    summary_path = out_dir / f"{safe_version}_summary.json"

    _write_jsonl(actions_path, actions)
    _write_jsonl(windows_path, windows)
    _write_jsonl(ledger_path, ledgers)

    type_counts = Counter(
        action.action_type.value
        for action in actions
    )
    quality_counts = Counter(
        action.quality.value
        for action in actions
    )
    window_action_counts = Counter(
        len(window.action_ids)
        for window in windows
    )
    ledger_status_counts = Counter(
        ledger.status
        for ledger in ledgers
    )

    compound_windows = sum(
        len(window.action_ids) > 1
        for window in windows
    )
    automatic_shop_refresh_candidates = sum(
        "automatic_round_shop_refresh_candidate"
        in window.notes
        for window in windows
    )
    long_windows = sum(
        "long_window" in window.notes
        for window in windows
    )

    observed_spend_total = sum(
        ledger.observed_spend or 0
        for ledger in ledgers
    )
    required_action_spend_min_total = sum(
        ledger.required_action_spend_min
        for ledger in ledgers
    )
    required_action_spend_max_known_total = sum(
        ledger.required_action_spend_max or 0
        for ledger in ledgers
    )
    required_action_spend_open_max_window_count = sum(
        ledger.required_action_spend_max is None and bool(ledger.components)
        for ledger in ledgers
    )
    action_spend_min_total = required_action_spend_min_total
    action_spend_max_total = required_action_spend_max_known_total
    compatible_action_spend_min_total = sum(
        ledger.compatible_action_spend_min or 0
        for ledger in ledgers
    )
    compatible_action_spend_max_total = sum(
        ledger.compatible_action_spend_max or 0
        for ledger in ledgers
    )
    unallocated_min_total = sum(
        ledger.unallocated_spend_min or 0
        for ledger in ledgers
    )
    unallocated_max_total = sum(
        ledger.unallocated_spend_max or 0
        for ledger in ledgers
    )
    unallocated_windows = sum(
        (ledger.unallocated_spend_max or 0) > 0
        for ledger in ledgers
    )
    required_unknown_windows = sum(
        (ledger.unallocated_spend_min or 0) > 0
        for ledger in ledgers
    )
    uncertainty_only_windows = sum(
        (ledger.unallocated_spend_min or 0) == 0
        and (ledger.unallocated_spend_max or 0) > 0
        for ledger in ledgers
    )
    feasible_spend_windows = sum(
        ledger.observed_spend is not None and ledger.feasible is True
        for ledger in ledgers
    )
    infeasible_spend_windows = sum(
        ledger.feasible is False
        for ledger in ledgers
    )
    spend_deficit_min_total = sum(
        ledger.spend_deficit_min or 0
        for ledger in ledgers
        if ledger.feasible is False
    )
    spend_deficit_max_known_total = sum(
        ledger.spend_deficit_max or 0
        for ledger in ledgers
        if ledger.feasible is False
    )
    spend_deficit_open_max_window_count = sum(
        ledger.feasible is False and ledger.spend_deficit_max is None
        for ledger in ledgers
    )

    bounded_unallocated_windows = sum(
        ledger.status == "unallocated_bounded"
        for ledger in ledgers
    )
    exact_unallocated_windows = sum(
        ledger.status == "unallocated_exact"
        for ledger in ledgers
    )
    buy_components = [
        component
        for ledger in ledgers
        for component in ledger.components
        if component.kind == "buy_unit"
    ]
    buy_champion_count = sum(
        component.count_min
        for component in buy_components
    )
    priced_buy_champion_count = sum(
        sum(
            cost is not None
            for cost in component.unit_costs
        )
        for component in buy_components
    )
    unresolved_buy_champion_count = sum(
        len(component.unresolved_champions)
        for component in buy_components
    )
    fully_priced_buy_window_count = sum(
        any(
            component.kind == "buy_unit"
            and component.exact_spend
            for component in ledger.components
        )
        for ledger in ledgers
    )
    unpriced_buy_window_count = sum(
        any(
            component.kind == "buy_unit"
            and not component.exact_spend
            for component in ledger.components
        )
        for ledger in ledgers
    )
    priced_buy_spend_total = sum(
        component.spend_min
        for component in buy_components
    )

    buy_actions = [
        action
        for action in actions
        if action.action_type.value == "buy_unit"
    ]
    buy_cost_validation_counts = Counter(
        str(
            action.params.get(
                "cost_validation",
                "unknown",
            )
        )
        for action in buy_actions
    )

    xp_absolute_count = sum(
        snapshot.xp_absolute is not None
        for snapshot in snapshots
    )

    summary = {
        "schema_version": 6,
        "producer_version": settings.producer_version,
        "match_dir": str(match_dir),
        "input_hud_states_path": str(hud_states_path),
        "input_board_states_path": str(board_states_path),
        "input_bench_states_path": str(bench_states_path),
        "hud_state_count": len(hud_by_evidence),
        "board_state_count": len(board_by_evidence),
        "bench_state_count": len(bench_by_evidence),
        "aligned_snapshot_count": len(snapshots),
        "window_count": len(windows),
        "action_count": len(actions),
        "action_type_counts": dict(type_counts),
        "quality_counts": dict(quality_counts),
        "windows_by_action_count": {
            str(k): v
            for k, v in sorted(window_action_counts.items())
        },
        "compound_window_count": compound_windows,
        "automatic_shop_refresh_candidate_count": (
            automatic_shop_refresh_candidates
        ),
        "long_window_count": long_windows,
        "xp_progress": {
            "base_level": xp_base_level,
            "absolute_snapshot_count": xp_absolute_count,
            "requirement_map": {
                str(level): required
                for level, required in sorted(xp_requirement_map.items())
            },
        },
        "economy_ledger": {
            "status_counts": dict(ledger_status_counts),
            "observed_spend_total": observed_spend_total,
            "required_action_spend_min_total": required_action_spend_min_total,
            "required_action_spend_max_known_total": required_action_spend_max_known_total,
            "required_action_spend_open_max_window_count": required_action_spend_open_max_window_count,
            "compatible_action_spend_min_total": compatible_action_spend_min_total,
            "compatible_action_spend_max_total": compatible_action_spend_max_total,
            "action_spend_min_total": action_spend_min_total,
            "action_spend_max_total": action_spend_max_total,
            "feasible_spend_window_count": feasible_spend_windows,
            "infeasible_spend_window_count": infeasible_spend_windows,
            "spend_deficit_min_total": spend_deficit_min_total,
            "spend_deficit_max_known_total": spend_deficit_max_known_total,
            "spend_deficit_open_max_window_count": spend_deficit_open_max_window_count,
            "unallocated_spend_min_total": unallocated_min_total,
            "unallocated_spend_max_total": unallocated_max_total,
            "unallocated_window_count": unallocated_windows,
            "required_unknown_window_count": required_unknown_windows,
            "uncertainty_only_window_count": uncertainty_only_windows,
            "bounded_unallocated_window_count": bounded_unallocated_windows,
            "exact_unallocated_window_count": exact_unallocated_windows,
            "unpriced_buy_window_count": unpriced_buy_window_count,
        },
        "game_data": {
            "enabled": champion_catalog is not None,
            "catalog_path": (
                str(champion_catalog_path)
                if champion_catalog_path is not None
                else None
            ),
            "provider": (
                champion_catalog.snapshot.provider
                if champion_catalog is not None
                else None
            ),
            "version": (
                champion_catalog.snapshot.version
                if champion_catalog is not None
                else None
            ),
            "locale": (
                champion_catalog.snapshot.locale
                if champion_catalog is not None
                else None
            ),
            "source_sha256": (
                champion_catalog.snapshot.source_sha256
                if champion_catalog is not None
                else None
            ),
            "catalog_champion_count": (
                len(champion_catalog.snapshot.champions)
                if champion_catalog is not None
                else 0
            ),
            "buy_champion_count": buy_champion_count,
            "priced_buy_champion_count": (
                priced_buy_champion_count
            ),
            "unresolved_buy_champion_count": (
                unresolved_buy_champion_count
            ),
            "fully_priced_buy_window_count": (
                fully_priced_buy_window_count
            ),
            "unpriced_buy_window_count": (
                unpriced_buy_window_count
            ),
            "priced_buy_spend_total": (
                priced_buy_spend_total
            ),
            "buy_cost_validation_counts": dict(
                buy_cost_validation_counts
            ),
            "set_id": (
                game_context.set_id
                if game_context is not None
                else None
            ),
            "patch": (
                game_context.patch
                if game_context is not None
                else None
            ),
            "context_resolution_source": (
                game_context.resolution_source
                if game_context is not None
                else None
            ),
            "scoped_champion_count": (
                game_context.scoped_champion_count
                if game_context is not None
                else 0
            ),
            "game_context_path": (
                str(match_dir / "game_context.json")
                if game_context is not None
                else None
            ),
        },
        "actions_path": str(actions_path),
        "windows_path": str(windows_path),
        "ledger_path": str(ledger_path),
        "summary_path": str(summary_path),
    }

    tmp = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(summary_path)

    return summary
