from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from tft_analyzer.core.models.decisions import DecisionEpisode
from tft_analyzer.core.models.tracking import TrackedHUDState
from tft_analyzer.game_data import load_game_context
from tft_analyzer.tracking.board.models import (
    TrackedBenchOccupancyState,
    TrackedBoardOccupancyState,
)

from .builder import build_episode_player_context
from .models import EpisodeContextSettings


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version_key(path: Path):
    matches = list(_VERSION_RE.finditer(path.name))
    version = (
        tuple(int(x) for x in matches[-1].groups())
        if matches
        else (0, 0, 0)
    )
    return (*version, path.stat().st_mtime)


def find_latest_episode_summary(match_dir: Path | str) -> Path:
    decision_dir = Path(match_dir) / "decisions"
    candidates = list(
        decision_dir.glob("decision-episode-builder-*_summary.json")
    )
    if not candidates:
        raise FileNotFoundError(
            f"No decision-episode-builder summary in {decision_dir}. "
            "Run `tft-analyzer build-episodes <match_dir>` first."
        )
    return max(candidates, key=_version_key)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path, model):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield model.model_validate_json(line)


def _resolve_artifact_path(
    match_dir: Path,
    value: str | None,
    subdir: str,
) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_file():
        return path
    candidate = match_dir / subdir / path.name
    if candidate.is_file():
        return candidate
    return None


def _require_path(
    match_dir: Path,
    explicit: Path | str | None,
    action_summary: dict,
    key: str,
) -> Path:
    if explicit is not None:
        path = Path(explicit)
        if path.is_file():
            return path
        candidate = match_dir / "tracking" / path.name
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(path)

    resolved = _resolve_artifact_path(
        match_dir,
        action_summary.get(key),
        "tracking",
    )
    if resolved is None:
        raise FileNotFoundError(
            f"Could not resolve {key!r} from action summary. "
            "Pass an explicit tracking path."
        )
    return resolved


def _write_jsonl(path: Path, values) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for value in values:
            f.write(
                json.dumps(
                    value.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp.replace(path)


def build_match_episode_context(
    match_dir: Path | str,
    settings: EpisodeContextSettings,
    *,
    episode_summary_path: Path | str | None = None,
    hud_states_path: Path | str | None = None,
    board_states_path: Path | str | None = None,
    bench_states_path: Path | str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    source_episode_summary = (
        Path(episode_summary_path)
        if episode_summary_path is not None
        else find_latest_episode_summary(match_dir)
    )
    episode_summary = _load_json(source_episode_summary)

    episodes_path = _resolve_artifact_path(
        match_dir,
        episode_summary.get("episodes_path"),
        "decisions",
    )
    if episodes_path is None:
        raise FileNotFoundError(episode_summary.get("episodes_path"))

    action_summary_value = episode_summary.get("input_action_summary_path")
    action_summary_path = _resolve_artifact_path(
        match_dir,
        action_summary_value,
        "actions",
    )
    action_summary = (
        _load_json(action_summary_path)
        if action_summary_path is not None
        else {}
    )

    hud_states_path = _require_path(
        match_dir,
        hud_states_path,
        action_summary,
        "input_hud_states_path",
    )
    board_states_path = _require_path(
        match_dir,
        board_states_path,
        action_summary,
        "input_board_states_path",
    )
    bench_states_path = _require_path(
        match_dir,
        bench_states_path,
        action_summary,
        "input_bench_states_path",
    )

    episodes = list(_iter_jsonl(episodes_path, DecisionEpisode))
    hud_states = list(_iter_jsonl(hud_states_path, TrackedHUDState))
    board_states = list(
        _iter_jsonl(board_states_path, TrackedBoardOccupancyState)
    )
    bench_states = list(
        _iter_jsonl(bench_states_path, TrackedBenchOccupancyState)
    )

    hud_by_evidence = {
        str(item.evidence_id): item
        for item in hud_states
        if item.evidence_id
    }
    board_by_evidence = {
        str(item.evidence_id): item for item in board_states
    }
    bench_by_evidence = {
        str(item.evidence_id): item for item in bench_states
    }

    contexts = [
        build_episode_player_context(
            episode,
            hud_by_evidence=hud_by_evidence,
            board_by_evidence=board_by_evidence,
            bench_by_evidence=bench_by_evidence,
            settings=settings,
        )
        for episode in episodes
    ]

    out_dir = match_dir / "features"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_version = (
        settings.producer_version
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    contexts_path = out_dir / f"{safe_version}.jsonl"
    summary_path = out_dir / f"{safe_version}_summary.json"
    _write_jsonl(contexts_path, contexts)

    exact_before = sum(item.quality.before_exact_alignment for item in contexts)
    exact_after = sum(item.quality.after_exact_alignment for item in contexts)
    hp_before = sum(item.quality.hp_known_before for item in contexts)
    hp_after = sum(item.quality.hp_known_after for item in contexts)
    hp_both = sum(
        item.quality.hp_known_before and item.quality.hp_known_after
        for item in contexts
    )
    board_both = sum(
        item.quality.board_known_before and item.quality.board_known_after
        for item in contexts
    )
    util_both = sum(
        item.quality.board_utilization_known_before
        and item.quality.board_utilization_known_after
        for item in contexts
    )
    scene_invalid_boundaries = sum(
        value is False
        for item in contexts
        for value in (
            item.quality.scene_valid_before,
            item.quality.scene_valid_after,
        )
    )

    hud_status_counts = Counter()
    for item in contexts:
        for state in (item.before, item.after):
            for name, meta in state.hud_fields.items():
                hud_status_counts[f"{name}:{meta.status}"] += 1

    hp_values = [
        hp
        for item in contexts
        for hp in (item.before.hp, item.after.hp)
        if hp is not None
    ]

    hp_strategy_usable_both = sum(
        item.feature_trust.before.hp.usable_for_strategy
        and item.feature_trust.after.hp.usable_for_strategy
        for item in contexts
    )
    board_exact_both = sum(
        item.feature_trust.before.board_count.semantics == "exact"
        and item.feature_trust.after.board_count.semantics == "exact"
        for item in contexts
    )
    board_strategy_usable_both = sum(
        item.feature_trust.before.board_count.usable_for_strategy
        and item.feature_trust.after.board_count.usable_for_strategy
        for item in contexts
    )
    board_lower_bound_contexts = sum(
        item.feature_trust.before.board_count.semantics
        in {"lower_bound", "carried"}
        or item.feature_trust.after.board_count.semantics
        in {"lower_bound", "carried"}
        for item in contexts
    )
    board_unusable_contexts = sum(
        item.feature_trust.before.board_count.semantics == "unusable"
        or item.feature_trust.after.board_count.semantics == "unusable"
        for item in contexts
    )
    bench_strategy_usable_both = sum(
        item.feature_trust.before.bench_count.usable_for_strategy
        and item.feature_trust.after.bench_count.usable_for_strategy
        for item in contexts
    )

    game_context = load_game_context(match_dir)
    summary = {
        "schema_version": 1,
        "producer_version": settings.producer_version,
        "match_dir": str(match_dir),
        "input_episode_summary_path": str(source_episode_summary),
        "input_episode_producer_version": episode_summary.get("producer_version"),
        "input_episodes_path": str(episodes_path),
        "input_action_summary_path": str(action_summary_path) if action_summary_path else None,
        "input_hud_states_path": str(hud_states_path),
        "input_board_states_path": str(board_states_path),
        "input_bench_states_path": str(bench_states_path),
        "episode_count": len(episodes),
        "context_count": len(contexts),
        "context_coverage_ratio": (len(contexts) / len(episodes) if episodes else 1.0),
        "trust_semantics_version": 1,
        "hp_strategy_usable_both_count": hp_strategy_usable_both,
        "board_exact_both_count": board_exact_both,
        "board_strategy_usable_both_count": board_strategy_usable_both,
        "board_lower_bound_context_count": board_lower_bound_contexts,
        "board_unusable_context_count": board_unusable_contexts,
        "bench_strategy_usable_both_count": bench_strategy_usable_both,
        "boundary_gold_delta_semantics": "observed_state_delta_not_action_accounting",
        "economy_source_for_action_spend": "episode_economy",
        "exact_before_alignment_count": exact_before,
        "exact_after_alignment_count": exact_after,
        "fully_exact_context_count": sum(
            item.quality.before_exact_alignment and item.quality.after_exact_alignment
            for item in contexts
        ),
        "hp_known_before_count": hp_before,
        "hp_known_after_count": hp_after,
        "hp_known_both_count": hp_both,
        "board_known_both_count": board_both,
        "board_utilization_known_both_count": util_both,
        "scene_invalid_boundary_count": scene_invalid_boundaries,
        "economy_infeasible_context_count": sum(
            item.quality.economy_feasible is False for item in contexts
        ),
        "reconstruction_uncertainty_context_count": sum(
            item.quality.reconstruction_uncertainty for item in contexts
        ),
        "hud_field_status_counts": dict(sorted(hud_status_counts.items())),
        "hp_observed_min": min(hp_values) if hp_values else None,
        "hp_observed_max": max(hp_values) if hp_values else None,
        "game_context": (
            game_context.model_dump(mode="json")
            if game_context is not None
            else None
        ),
        "contexts_path": str(contexts_path),
        "summary_path": str(summary_path),
    }

    tmp = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(summary_path)
    return summary
