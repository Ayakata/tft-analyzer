# Stage 4.2.1 — Finding Semantics Cleanup

## Goal

Do not confuse normal uncertainty from sparse screenshots with broken source or
reconstruction data.

The analyzer now has an explicit semantic lane:

```text
reconstruction_uncertainty
```

between descriptive activity and hard `data_quality` findings.

## Hard data-quality findings

`data_quality` is reserved for contradictions where the reconstructed facts
cannot all be true at the same time.

Current rule:

```text
economy_infeasible
```

Example from the canonical TFT17 match:

```text
observed spend = 1g
trusted Zoe BUY requirement = 2g
constraint deficit = 1g
```

This remains:

```text
interpretation = data_quality
category = data_quality.hard_conflict.economy
severity = major
```

It is an upstream QA/reconstruction problem, not a player mistake.

## Reconstruction uncertainty

Sparse screenshots can legitimately omit many actions between adjacent
observations. Therefore an observed gold loss that cannot be allocated to
named actions is not evidence of bad data by itself.

0.16.0:

```text
required_unexplained_spend
interpretation = data_quality
severity = minor/major
```

0.16.1:

```text
unresolved_economy_spend
interpretation = reconstruction_uncertainty
category = reconstruction_uncertainty.economy
severity = info
```

The numeric interval remains unchanged; only its semantic interpretation is
corrected.

`bounded_economy_uncertainty` is moved to the same interpretation lane.

## Summary contract

The analyzer summary separates:

```text
hard_data_quality_episode_count
reconstruction_uncertainty_episode_count
review_candidate_episode_count
decision_grade_count
```

`data_quality_episode_count` remains as a backward-compatible alias for
`hard_data_quality_episode_count`.

## Policy

0.16.1 still does not grade TFT decisions. It emits:

- descriptive activity landmarks;
- expected reconstruction uncertainty;
- hard data-quality contradictions;
- conservative review candidates.

Strategic judgments remain blocked until richer episode context is available.
