# Stage 4.5 — Match Review Cards

Version: 0.19.0

## Goal

Convert episode-level technical findings into compact post-game review items. Multiple findings from one episode become one card.

## Contract

A card contains:

- card type: `gameplay_review` or `data_quality`;
- review priority: `critical/high/medium/low`;
- trusted before/after state;
- compact activity metrics;
- observed facts;
- reasons the moment is useful to review;
- limitations and source finding/evidence provenance.

`decision_grade` is always null in 0.19.0.

## Priority semantics

Priority ranks review value, not decision quality.

- `critical`: near-elimination activity;
- `high`: at least one major context signal;
- `medium`: multiple pressure signals or large spend under pressure;
- `low`: a single weaker review signal.

A hard reconstruction conflict produces a separate high-priority data-quality card and never a gameplay card.

## Expected canonical-match shape

The accepted 0.18.0 match has 11 findings across four gameplay-review episodes plus one blocked QA episode. 0.19.0 should therefore collapse them to approximately five cards: four gameplay cards and one data-quality card.
