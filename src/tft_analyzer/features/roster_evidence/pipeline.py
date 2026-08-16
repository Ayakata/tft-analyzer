from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from tft_analyzer.actions.models import InferredAction
from tft_analyzer.core.enums import ActionType
from tft_analyzer.core.models.decisions import DecisionEpisode

from .builder import build_roster_evidence
from .models import (
    EpisodeRosterEvidence,
    RosterEvidenceSettings,
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


def find_latest_episode_summary(
    match_dir: Path | str,
) -> Path:
    decision_dir = Path(match_dir) / "decisions"
    candidates = list(
        decision_dir.glob(
            "decision-episode-builder-*_summary.json"
        )
    )
    if not candidates:
        raise FileNotFoundError(
            f"No decision-episode-builder summary in "
            f"{decision_dir}. Run "
            "`tft-analyzer build-episodes <match_dir>` first."
        )
    return max(
        candidates,
        key=_version_key,
    )


def _load_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def _iter_jsonl(path: Path, model):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            if line.strip():
                yield model.model_validate_json(
                    line
                )


def _resolve(
    match_dir: Path,
    value: str | None,
    subdir: str,
) -> Path:
    if not value:
        raise FileNotFoundError(
            f"Missing artifact path for {subdir}"
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
    raise FileNotFoundError(value)


def _write_jsonl(path: Path, values) -> None:
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )
    with tmp.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        for value in values:
            f.write(
                json.dumps(
                    value.model_dump(
                        mode="json"
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp.replace(path)


def _snapshot_dict(
    context: EpisodeRosterEvidence | None,
) -> dict[str, object]:
    if context is None:
        return {
            "acquisition_semantics": "confirmed_history_lower_bound",
            "complete_roster_known": False,
            "complete_sell_history_known": False,
            "current_ownership_status": "not_established",
            "confirmed_identity_buy_copy_count": 0,
            "candidate_identity_buy_copy_count": 0,
            "unidentified_confirmed_buy_copy_count": 0,
            "unidentified_candidate_buy_copy_count": 0,
            "identified_sell_unit_count": 0,
            "unidentified_sell_unit_count_lower_bound": 0,
            "unresolved_economy_action_count": 0,
            "unresolved_economy_spend_min_total": 0,
            "unresolved_economy_spend_max_total": 0,
            "confirmed_buy_identity_coverage": 1.0,
            "champions": [],
        }
    return context.after.model_dump(
        mode="json"
    )


def build_match_roster_evidence(
    match_dir: Path | str,
    settings: RosterEvidenceSettings,
    *,
    episode_summary_path: Path | str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)

    source_episode_summary = (
        Path(episode_summary_path)
        if episode_summary_path is not None
        else find_latest_episode_summary(
            match_dir
        )
    )
    episode_summary = _load_json(
        source_episode_summary
    )

    episodes_path = _resolve(
        match_dir,
        episode_summary.get("episodes_path"),
        "decisions",
    )
    actions_path = _resolve(
        match_dir,
        episode_summary.get(
            "input_actions_path"
        ),
        "actions",
    )

    action_summary_path = _resolve(
        match_dir,
        episode_summary.get(
            "input_action_summary_path"
        ),
        "actions",
    )
    action_summary = _load_json(
        action_summary_path
    )

    episodes = list(
        _iter_jsonl(
            episodes_path,
            DecisionEpisode,
        )
    )
    actions = list(
        _iter_jsonl(
            actions_path,
            InferredAction,
        )
    )

    contexts, coverage_stats = build_roster_evidence(
        episodes,
        actions,
        settings,
        source_action_producer_version=(
            episode_summary.get(
                "input_action_producer_version"
            )
            or action_summary.get(
                "producer_version"
            )
        ),
    )

    out_dir = match_dir / "features"
    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_version = (
        settings.producer_version
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    contexts_path = (
        out_dir
        / f"{safe_version}.jsonl"
    )
    summary_path = (
        out_dir
        / f"{safe_version}_summary.json"
    )
    _write_jsonl(
        contexts_path,
        contexts,
    )

    action_type_counts = Counter(
        action.action_type.value
        for action in actions
    )

    buy_actions = [
        action
        for action in actions
        if action.action_type
        == ActionType.BUY_UNIT
    ]
    sell_actions = [
        action
        for action in actions
        if action.action_type
        == ActionType.SELL_UNIT
    ]
    unknown_econ_actions = [
        action
        for action in actions
        if action.action_type
        == ActionType.UNKNOWN_ECON_ACTION
    ]

    final_snapshot = _snapshot_dict(
        contexts[-1]
        if contexts
        else None
    )

    confirmed_acquisition_lower_bounds = {
        item["champion"]: item[
            "confirmed_acquired_copy_lower_bound"
        ]
        for item in final_snapshot[
            "champions"
        ]
        if item[
            "confirmed_acquired_copy_lower_bound"
        ] > 0
    }
    candidate_acquisitions = {
        item["champion"]: item[
            "candidate_acquired_copy_count"
        ]
        for item in final_snapshot[
            "champions"
        ]
        if item[
            "candidate_acquired_copy_count"
        ] > 0
    }

    episode_with_roster_change_count = sum(
        bool(
            context.delta.confirmed_buys
            or context.delta.candidate_buys
            or context.delta.identified_sells
            or context.delta.unidentified_confirmed_buy_copy_count
            or context.delta.unidentified_candidate_buy_copy_count
            or context.delta.unidentified_sell_unit_count_lower_bound
        )
        for context in contexts
    )

    game_data = (
        action_summary.get("game_data")
        or {}
    )

    summary = {
        "schema_version": 1,
        "producer_version": (
            settings.producer_version
        ),
        "match_dir": str(match_dir),
        "input_episode_summary_path": str(
            source_episode_summary
        ),
        "input_episode_producer_version": (
            episode_summary.get(
                "producer_version"
            )
        ),
        "input_episodes_path": str(
            episodes_path
        ),
        "input_action_summary_path": str(
            action_summary_path
        ),
        "input_action_producer_version": (
            action_summary.get(
                "producer_version"
            )
        ),
        "input_actions_path": str(
            actions_path
        ),
        "episode_count": len(episodes),
        "context_count": len(contexts),
        "episode_with_roster_change_count": (
            episode_with_roster_change_count
        ),
        "input_action_count": len(actions),
        "input_action_type_counts": dict(
            sorted(
                action_type_counts.items()
            )
        ),
        **coverage_stats,
        "buy_action_count": len(
            buy_actions
        ),
        "sell_action_count": len(
            sell_actions
        ),
        "unknown_economy_action_count": len(
            unknown_econ_actions
        ),
        "confirmed_identity_buy_copy_count": (
            final_snapshot[
                "confirmed_identity_buy_copy_count"
            ]
        ),
        "candidate_identity_buy_copy_count": (
            final_snapshot[
                "candidate_identity_buy_copy_count"
            ]
        ),
        "unidentified_confirmed_buy_copy_count": (
            final_snapshot[
                "unidentified_confirmed_buy_copy_count"
            ]
        ),
        "unidentified_candidate_buy_copy_count": (
            final_snapshot[
                "unidentified_candidate_buy_copy_count"
            ]
        ),
        "confirmed_buy_identity_coverage": (
            final_snapshot[
                "confirmed_buy_identity_coverage"
            ]
        ),
        "identified_sell_unit_count": (
            final_snapshot[
                "identified_sell_unit_count"
            ]
        ),
        "unidentified_sell_unit_count_lower_bound": (
            final_snapshot[
                "unidentified_sell_unit_count_lower_bound"
            ]
        ),
        "unresolved_economy_spend_min_total": (
            final_snapshot[
                "unresolved_economy_spend_min_total"
            ]
        ),
        "unresolved_economy_spend_max_total": (
            final_snapshot[
                "unresolved_economy_spend_max_total"
            ]
        ),
        "final_confirmed_acquisition_copy_lower_bounds": (
            dict(
                sorted(
                    confirmed_acquisition_lower_bounds.items()
                )
            )
        ),
        "final_candidate_acquisitions": dict(
            sorted(
                candidate_acquisitions.items()
            )
        ),
        "acquisition_semantics": (
            "confirmed_history_lower_bound"
        ),
        "current_ownership_status": (
            "not_established"
        ),
        "complete_roster_known": False,
        "complete_sell_history_known": False,
        "game_context": {
            "set_id": game_data.get(
                "set_id"
            ),
            "patch": game_data.get(
                "patch"
            ),
            "data_dragon_version": (
                game_data.get("version")
            ),
        },
        "settings": {
            "min_confirmed_buy_confidence": (
                settings.min_confirmed_buy_confidence
            ),
            "exclude_cost_conflict_from_confirmed": (
                settings.exclude_cost_conflict_from_confirmed
            ),
            "require_relevant_action_coverage": (
                settings.require_relevant_action_coverage
            ),
        },
        "contexts_path": str(
            contexts_path
        ),
        "summary_path": str(
            summary_path
        ),
    }

    tmp = summary_path.with_suffix(
        summary_path.suffix + ".tmp"
    )
    tmp.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(summary_path)
    return summary
