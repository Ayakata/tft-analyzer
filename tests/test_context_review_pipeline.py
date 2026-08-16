import json

import pytest

from tft_analyzer.analyzers.context_review import (
    ContextReviewAnalyzerSettings,
    analyze_match_context,
)


def test_context_review_rejects_context_without_trust_semantics(tmp_path):
    match = tmp_path / "match"
    features = match / "features"
    features.mkdir(parents=True)

    summary = features / "episode-context-builder-0.17.0_summary.json"
    summary.write_text(
        json.dumps(
            {
                "producer_version": "episode-context-builder-0.17.0",
                "contexts_path": "unused.jsonl",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="requires feature trust semantics",
    ):
        analyze_match_context(
            match,
            ContextReviewAnalyzerSettings(),
            context_summary_path=summary,
        )
