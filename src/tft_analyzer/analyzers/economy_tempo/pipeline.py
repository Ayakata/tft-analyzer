from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from tft_analyzer.actions.models import InferredAction
from tft_analyzer.core.models.analysis import Finding
from tft_analyzer.core.models.decisions import DecisionEpisode

from .analyzer import analyze_episodes
from .models import EconomyTempoAnalyzerSettings


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


def _resolve_artifact_path(match_dir: Path, value: str, subdir: str) -> Path:
    path = Path(value)
    if path.exists():
        return path
    candidate = match_dir / subdir / path.name
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


def analyze_match_episodes(
    match_dir: Path | str,
    settings: EconomyTempoAnalyzerSettings,
    *,
    episode_summary_path: Path | str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    source_summary_path = (
        Path(episode_summary_path)
        if episode_summary_path is not None
        else find_latest_episode_summary(match_dir)
    )
    episode_summary = _load_json(source_summary_path)

    episodes_path = _resolve_artifact_path(
        match_dir,
        episode_summary["episodes_path"],
        "decisions",
    )
    actions_path = _resolve_artifact_path(
        match_dir,
        episode_summary["input_actions_path"],
        "actions",
    )

    episodes = list(_iter_jsonl(episodes_path, DecisionEpisode))
    actions = list(_iter_jsonl(actions_path, InferredAction))
    findings = analyze_episodes(episodes, actions, settings)

    out_dir = match_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_version = (
        settings.producer_version
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    findings_path = out_dir / f"{safe_version}.jsonl"
    summary_path = out_dir / f"{safe_version}_summary.json"
    _write_jsonl(findings_path, findings)

    category_counts = Counter(item.category for item in findings)
    code_counts = Counter(item.finding_code or "unknown" for item in findings)
    severity_counts = Counter(item.severity for item in findings)
    interpretation_counts = Counter(item.interpretation for item in findings)

    episodes_with_findings = {
        item.decision_id for item in findings if item.decision_id
    }
    hard_data_quality_episode_ids = {
        item.decision_id
        for item in findings
        if item.interpretation == "data_quality" and item.decision_id
    }
    reconstruction_uncertainty_episode_ids = {
        item.decision_id
        for item in findings
        if (
            item.interpretation == "reconstruction_uncertainty"
            and item.decision_id
        )
    }
    review_episode_ids = {
        item.decision_id
        for item in findings
        if item.interpretation == "review_candidate" and item.decision_id
    }

    # Pull set/patch provenance when available. This remains contextual only;
    # the 0.16.0 rules themselves are not meta-aware.
    action_summary_value = episode_summary.get(
        "input_action_summary_path"
    )
    action_summary_path = (
        Path(action_summary_value)
        if action_summary_value
        else None
    )
    if (
        action_summary_path is not None
        and not action_summary_path.exists()
        and action_summary_path.name
    ):
        candidate = match_dir / "actions" / action_summary_path.name
        if candidate.exists():
            action_summary_path = candidate
    action_summary = (
        _load_json(action_summary_path)
        if (
            action_summary_path is not None
            and action_summary_path.is_file()
        )
        else {}
    )
    game_data = action_summary.get("game_data", {})

    summary = {
        "schema_version": 2,
        "producer_version": settings.producer_version,
        "match_dir": str(match_dir),
        "input_episode_summary_path": str(source_summary_path),
        "input_episode_producer_version": episode_summary.get(
            "producer_version"
        ),
        "input_episodes_path": str(episodes_path),
        "input_actions_path": str(actions_path),
        "episode_count": len(episodes),
        "finding_count": len(findings),
        "episodes_with_findings_count": len(episodes_with_findings),
        "category_counts": dict(category_counts),
        "finding_code_counts": dict(code_counts),
        "severity_counts": dict(severity_counts),
        "interpretation_counts": dict(interpretation_counts),
        # 0.16.1: `data_quality` now means a hard contradiction only.
        "hard_data_quality_episode_count": len(
            hard_data_quality_episode_ids
        ),
        "reconstruction_uncertainty_episode_count": len(
            reconstruction_uncertainty_episode_ids
        ),
        # Backward-compatible field. Its meaning is intentionally narrowed to
        # hard data-quality contradictions in 0.16.1.
        "data_quality_episode_count": len(
            hard_data_quality_episode_ids
        ),
        "review_candidate_episode_count": len(review_episode_ids),
        "decision_grade_count": sum(
            item.interpretation == "decision_grade"
            for item in findings
        ),
        "analysis_policy": (
            "descriptive_reconstruction_uncertainty_review_no_meta_grade"
        ),
        "ordering_policy": episode_summary.get(
            "ordering_policy",
            "window_partial_order",
        ),
        "exact_sequence_reconstructed_count": 0,
        "game_context": {
            "set_id": game_data.get("set_id"),
            "patch": game_data.get("patch"),
            "data_dragon_version": game_data.get("version"),
        },
        "settings": {
            "large_spend_threshold": settings.large_spend_threshold,
            "low_gold_after_threshold": settings.low_gold_after_threshold,
            "roll_burst_max_count_threshold": (
                settings.roll_burst_max_count_threshold
            ),
            "emit_unresolved_economy_spend": (
                settings.emit_unresolved_economy_spend
            ),
            "emit_uncertainty_only": settings.emit_uncertainty_only,
            "emit_large_spend": settings.emit_large_spend,
            "emit_low_gold_review_candidate": (
                settings.emit_low_gold_review_candidate
            ),
            "emit_roll_activity": settings.emit_roll_activity,
            "emit_xp_investment": settings.emit_xp_investment,
            "emit_positioning_only": settings.emit_positioning_only,
        },
        "findings_path": str(findings_path),
        "summary_path": str(summary_path),
    }

    tmp = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(summary_path)
    return summary
