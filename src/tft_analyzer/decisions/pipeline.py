from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from tft_analyzer.actions.models import (
    ActionWindowDiagnostic,
    EconomyLedgerWindow,
    InferredAction,
)

from .builder import build_decision_episodes
from .models import DecisionEpisodeSettings


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version_key(path: Path):
    matches = list(_VERSION_RE.finditer(path.name))
    version = (
        tuple(int(x) for x in matches[-1].groups())
        if matches
        else (0, 0, 0)
    )
    return (*version, path.stat().st_mtime)


def find_latest_action_summary(match_dir: Path | str) -> Path:
    action_dir = Path(match_dir) / "actions"
    candidates = list(
        action_dir.glob("semantic-action-fusion-*_summary.json")
    )
    if not candidates:
        raise FileNotFoundError(
            f"No semantic-action-fusion summary in {action_dir}. "
            "Run `tft-analyzer infer-actions <match_dir>` first."
        )
    return max(candidates, key=_version_key)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path, model):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield model.model_validate_json(line)


def _resolve_artifact_path(match_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.exists():
        return path

    # Action summaries often store paths relative to the repository cwd.
    # The filename itself is stable, so fall back to match_dir/actions.
    candidate = match_dir / "actions" / path.name
    if candidate.exists():
        return candidate

    raise FileNotFoundError(value)


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


def build_match_decision_episodes(
    match_dir: Path | str,
    settings: DecisionEpisodeSettings,
    *,
    action_summary_path: Path | str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    summary_path = (
        Path(action_summary_path)
        if action_summary_path is not None
        else find_latest_action_summary(match_dir)
    )
    action_summary = _load_json(summary_path)

    actions_path = _resolve_artifact_path(
        match_dir,
        action_summary["actions_path"],
    )
    windows_path = _resolve_artifact_path(
        match_dir,
        action_summary["windows_path"],
    )
    ledger_path = _resolve_artifact_path(
        match_dir,
        action_summary["ledger_path"],
    )

    actions = list(_iter_jsonl(actions_path, InferredAction))
    windows = list(_iter_jsonl(windows_path, ActionWindowDiagnostic))
    ledgers = list(_iter_jsonl(ledger_path, EconomyLedgerWindow))

    episodes = build_decision_episodes(
        actions=actions,
        windows=windows,
        ledgers=ledgers,
        settings=settings,
    )

    out_dir = match_dir / "decisions"
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_version = (
        settings.producer_version
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    episodes_path = out_dir / f"{safe_version}.jsonl"
    episode_summary_path = out_dir / f"{safe_version}_summary.json"

    _write_jsonl(episodes_path, episodes)

    type_counts = Counter(
        episode.decision_type.value for episode in episodes
    )
    source_window_counts = Counter(
        episode.sampling.source_window_count for episode in episodes
    )
    action_type_counts = Counter(
        action.action_type.value for action in actions
    )

    covered_action_ids = {
        action_id
        for episode in episodes
        for action_id in episode.action_ids
    }
    all_action_ids = {action.action_id for action in actions}

    summary = {
        "schema_version": 1,
        "producer_version": settings.producer_version,
        "match_dir": str(match_dir),
        "input_action_summary_path": str(summary_path),
        "input_action_producer_version": action_summary.get(
            "producer_version"
        ),
        "input_actions_path": str(actions_path),
        "input_windows_path": str(windows_path),
        "input_ledger_path": str(ledger_path),
        "input_action_count": len(actions),
        "input_action_type_counts": dict(action_type_counts),
        "episode_count": len(episodes),
        "decision_type_counts": dict(type_counts),
        "episodes_by_source_window_count": {
            str(key): value
            for key, value in sorted(source_window_counts.items())
        },
        "multi_window_episode_count": sum(
            episode.sampling.source_window_count > 1
            for episode in episodes
        ),
        "compound_action_group_count": sum(
            episode.summary.get("compound_action_group_count", 0)
            for episode in episodes
        ),
        "infeasible_episode_count": sum(
            episode.economy.infeasible_window_count > 0
            for episode in episodes
        ),
        "exact_sequence_reconstructed_count": 0,
        "ordering_policy": "window_partial_order",
        "sampling_mode": "sparse_snapshots",
        "covered_action_count": len(covered_action_ids),
        "uncovered_action_count": len(
            all_action_ids - covered_action_ids
        ),
        "action_coverage_ratio": (
            len(covered_action_ids) / len(all_action_ids)
            if all_action_ids
            else 1.0
        ),
        "settings": {
            "max_idle_gap_seconds": settings.max_idle_gap_seconds,
            "max_episode_duration_seconds": (
                settings.max_episode_duration_seconds
            ),
            "split_on_stage_change": settings.split_on_stage_change,
            "include_unknown_economy_only": (
                settings.include_unknown_economy_only
            ),
        },
        "episodes_path": str(episodes_path),
        "summary_path": str(episode_summary_path),
    }

    tmp = episode_summary_path.with_suffix(
        episode_summary_path.suffix + ".tmp"
    )
    tmp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(episode_summary_path)

    return summary
