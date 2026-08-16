from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from tft_analyzer.core.models.analysis import Finding
from tft_analyzer.features.episode_context.models import EpisodePlayerContext

from .builder import build_match_review_cards
from .models import MatchReviewReportSettings
from .render import render_review_markdown

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version_key(path: Path):
    matches = list(_VERSION_RE.finditer(path.name))
    version = (
        tuple(int(x) for x in matches[-1].groups())
        if matches
        else (0, 0, 0)
    )
    return (*version, path.stat().st_mtime)


def find_latest_context_review_summary(match_dir: Path | str) -> Path:
    analysis_dir = Path(match_dir) / "analysis"
    candidates = list(
        analysis_dir.glob("context-review-analyzer-*_summary.json")
    )
    if not candidates:
        raise FileNotFoundError(
            f"No context-review-analyzer summary in {analysis_dir}. "
            "Run `tft-analyzer analyze-context <match_dir>` first."
        )
    return max(candidates, key=_version_key)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path, model):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield model.model_validate_json(line)


def _resolve(match_dir: Path, value: str | None, subdir: str) -> Path:
    if not value:
        raise FileNotFoundError(f"Missing artifact path for {subdir}")
    path = Path(value)
    if path.is_file():
        return path
    candidate = match_dir / subdir / path.name
    if candidate.is_file():
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


def build_match_review_report(
    match_dir: Path | str,
    settings: MatchReviewReportSettings,
    *,
    context_review_summary_path: Path | str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    source_review_summary = (
        Path(context_review_summary_path)
        if context_review_summary_path is not None
        else find_latest_context_review_summary(match_dir)
    )
    review_summary = _load(source_review_summary)

    if review_summary.get("decision_grade_count", 0) != 0:
        raise ValueError(
            "0.19.0 review cards expect a no-grade context-review input."
        )

    findings_path = _resolve(
        match_dir,
        review_summary.get("findings_path"),
        "analysis",
    )
    context_summary_path = _resolve(
        match_dir,
        review_summary.get("input_context_summary_path"),
        "features",
    )
    context_summary = _load(context_summary_path)
    if not context_summary.get("trust_semantics_version"):
        raise ValueError(
            "Review report requires episode context with feature trust semantics."
        )
    contexts_path = _resolve(
        match_dir,
        context_summary.get("contexts_path"),
        "features",
    )

    findings = list(_iter_jsonl(findings_path, Finding))
    contexts = list(_iter_jsonl(contexts_path, EpisodePlayerContext))
    cards = build_match_review_cards(findings, contexts, settings)

    out_dir = match_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_version = (
        settings.producer_version
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    cards_path = out_dir / f"{safe_version}.jsonl"
    summary_path = out_dir / f"{safe_version}_summary.json"
    markdown_path = out_dir / f"{safe_version}.md"
    _write_jsonl(cards_path, cards)

    game_context = (
        review_summary.get("game_context")
        or context_summary.get("game_context")
        or {}
    )
    markdown_path.write_text(
        render_review_markdown(
            cards,
            match_id=contexts[0].match_id if contexts else match_dir.name,
            game_context=game_context,
            producer_version=settings.producer_version,
        ),
        encoding="utf-8",
    )

    priority_counts = Counter(card.priority for card in cards)
    type_counts = Counter(card.card_type for card in cards)
    gameplay_cards = [
        card for card in cards if card.card_type == "gameplay_review"
    ]
    qa_cards = [card for card in cards if card.card_type == "data_quality"]

    summary = {
        "schema_version": 1,
        "producer_version": settings.producer_version,
        "match_dir": str(match_dir),
        "input_context_review_summary_path": str(source_review_summary),
        "input_context_review_producer_version": review_summary.get("producer_version"),
        "input_findings_path": str(findings_path),
        "input_context_summary_path": str(context_summary_path),
        "input_context_producer_version": context_summary.get("producer_version"),
        "input_trust_semantics_version": context_summary.get("trust_semantics_version"),
        "input_finding_count": len(findings),
        "context_count": len(contexts),
        "card_count": len(cards),
        "gameplay_review_card_count": len(gameplay_cards),
        "data_quality_card_count": len(qa_cards),
        "priority_counts": dict(sorted(priority_counts.items())),
        "card_type_counts": dict(sorted(type_counts.items())),
        "decision_grade_count": 0,
        "report_policy": "aggregate_episode_findings_into_review_cards_no_decision_grade",
        "priority_policy": "review_importance_not_decision_quality",
        "data_quality_policy": "separate_cards_not_gameplay_review",
        "game_context": game_context,
        "settings": {
            "include_data_quality_cards": settings.include_data_quality_cards,
        },
        "cards_path": str(cards_path),
        "markdown_path": str(markdown_path),
        "summary_path": str(summary_path),
    }
    tmp = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(summary_path)
    return summary
