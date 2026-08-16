from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from tft_analyzer.actions.models import InferredAction
from tft_analyzer.core.models.analysis import Finding
from tft_analyzer.core.models.decisions import DecisionEpisode
from tft_analyzer.features.episode_context.models import EpisodePlayerContext

from .analyzer import analyze_context_episodes
from .models import ContextReviewAnalyzerSettings


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version_key(path: Path):
    matches = list(_VERSION_RE.finditer(path.name))
    version = (
        tuple(int(x) for x in matches[-1].groups())
        if matches
        else (0, 0, 0)
    )
    return (*version, path.stat().st_mtime)


def find_latest_context_summary(
    match_dir: Path | str,
) -> Path:
    feature_dir = Path(match_dir) / "features"
    candidates = list(
        feature_dir.glob(
            "episode-context-builder-*_summary.json"
        )
    )
    if not candidates:
        raise FileNotFoundError(
            f"No episode-context-builder summary in {feature_dir}. "
            "Run `tft-analyzer build-episode-context <match_dir>` first."
        )
    return max(candidates, key=_version_key)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path, model):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield model.model_validate_json(line)


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
    candidate = match_dir / subdir / path.name
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(value)


def _write_jsonl(path: Path, values) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        for value in values:
            f.write(
                json.dumps(
                    value.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    tmp.replace(path)


def analyze_match_context(
    match_dir: Path | str,
    settings: ContextReviewAnalyzerSettings,
    *,
    context_summary_path: Path | str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    source_context_summary = (
        Path(context_summary_path)
        if context_summary_path is not None
        else find_latest_context_summary(match_dir)
    )
    context_summary = _load_json(
        source_context_summary
    )

    if not context_summary.get("trust_semantics_version"):
        raise ValueError(
            "Context review requires feature trust semantics. "
            "Run `tft-analyzer build-episode-context <match_dir>` "
            "with episode-context-builder 0.17.1 or newer."
        )

    contexts_path = _resolve(
        match_dir,
        context_summary.get("contexts_path"),
        "features",
    )
    episodes_path = _resolve(
        match_dir,
        context_summary.get("input_episodes_path"),
        "decisions",
    )
    episode_summary_path = _resolve(
        match_dir,
        context_summary.get(
            "input_episode_summary_path"
        ),
        "decisions",
    )
    episode_summary = _load_json(
        episode_summary_path
    )
    actions_path = _resolve(
        match_dir,
        episode_summary.get("input_actions_path"),
        "actions",
    )

    contexts = list(
        _iter_jsonl(
            contexts_path,
            EpisodePlayerContext,
        )
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

    findings, analysis_stats = analyze_context_episodes(
        episodes,
        contexts,
        actions,
        settings,
    )

    out_dir = match_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_version = (
        settings.producer_version
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    findings_path = out_dir / f"{safe_version}.jsonl"
    summary_path = out_dir / (
        f"{safe_version}_summary.json"
    )
    _write_jsonl(findings_path, findings)

    category_counts = Counter(
        item.category
        for item in findings
    )
    code_counts = Counter(
        item.finding_code or "unknown"
        for item in findings
    )
    severity_counts = Counter(
        item.severity
        for item in findings
    )
    interpretation_counts = Counter(
        item.interpretation
        for item in findings
    )

    review_episode_ids = {
        item.decision_id
        for item in findings
        if (
            item.interpretation == "review_candidate"
            and item.decision_id
        )
    }
    data_quality_episode_ids = {
        item.decision_id
        for item in findings
        if (
            item.interpretation == "data_quality"
            and item.decision_id
        )
    }

    game_context = (
        context_summary.get("game_context")
        or {}
    )

    summary = {
        "schema_version": 1,
        "producer_version": settings.producer_version,
        "match_dir": str(match_dir),
        "input_context_summary_path": str(
            source_context_summary
        ),
        "input_context_producer_version": (
            context_summary.get("producer_version")
        ),
        "input_trust_semantics_version": (
            context_summary.get("trust_semantics_version")
        ),
        "input_contexts_path": str(contexts_path),
        "input_episode_summary_path": str(
            episode_summary_path
        ),
        "input_episode_producer_version": (
            episode_summary.get("producer_version")
        ),
        "input_episodes_path": str(episodes_path),
        "input_actions_path": str(actions_path),
        "episode_count": len(episodes),
        "context_count": len(contexts),
        "finding_count": len(findings),
        "review_candidate_episode_count": len(
            review_episode_ids
        ),
        "data_quality_blocked_episode_count": len(
            data_quality_episode_ids
        ),
        "decision_grade_count": sum(
            item.interpretation == "decision_grade"
            for item in findings
        ),
        "finding_code_counts": dict(
            sorted(code_counts.items())
        ),
        "category_counts": dict(
            sorted(category_counts.items())
        ),
        "severity_counts": dict(
            sorted(severity_counts.items())
        ),
        "interpretation_counts": dict(
            sorted(interpretation_counts.items())
        ),
        "strategic_episode_blocked_infeasible_count": (
            analysis_stats[
                "strategic_episode_blocked_infeasible"
            ]
        ),
        "missing_context_episode_count": (
            analysis_stats[
                "missing_context_episode_count"
            ]
        ),
        "board_rule_eligible_episode_count": (
            analysis_stats["board_rule_eligible"]
        ),
        "board_rule_skipped_untrusted_episode_count": (
            analysis_stats[
                "board_rule_skipped_untrusted"
            ]
        ),
        "analysis_policy": (
            "context_aware_review_candidates_no_decision_grade"
        ),
        "trust_policy": (
            "strategy_rules_must_require_feature_trust"
        ),
        "economy_policy": (
            "episode_economy_only_not_boundary_gold_delta"
        ),
        "infeasible_policy": (
            "hard_block_context_strategy_review"
        ),
        "game_context": game_context,
        "settings": {
            "pressure_hp_threshold": (
                settings.pressure_hp_threshold
            ),
            "critical_hp_threshold": (
                settings.critical_hp_threshold
            ),
            "near_elimination_hp_threshold": (
                settings.near_elimination_hp_threshold
            ),
            "economy_commitment_spend_threshold": (
                settings.economy_commitment_spend_threshold
            ),
            "large_spend_under_pressure_threshold": (
                settings.large_spend_under_pressure_threshold
            ),
            "high_gold_under_pressure_threshold": (
                settings.high_gold_under_pressure_threshold
            ),
        },
        "findings_path": str(findings_path),
        "summary_path": str(summary_path),
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
