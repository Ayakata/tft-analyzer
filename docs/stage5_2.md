# Stage 5.2 — Identity Dataset Curation & QA

Version: 0.21.2

## Goal

Estimate how many practically distinct visual examples exist inside the
0.21.1 observation pool and create compact queues for manual champion labeling
and occupancy/hard-negative QA.

This stage does not modify occupancy truth and does not infer champion identity.

## Source

Input is a complete `slot-identity-dataset-exporter-0.21.1` directory:

```text
manifest.jsonl
images/board/
images/bench/
```

## Queue separation

The source quality tiers are mapped into two independent queues:

```text
trusted + supported -> identity_label
raw_candidate       -> occupancy_qa
```

The queues never merge during temporal grouping.

## Temporal near-duplicate grouping

Candidates are grouped only within:

```text
match_id
location
slot_id
queue_type
```

Default compatibility rules:

```text
time gap <= 15 seconds
64-bit dHash Hamming distance <= 6
same stage
```

`--allow-stage-crossing` can disable the stage boundary for diagnostics.

The perceptual hash is intentionally conservative. A visual group means
near-duplicate crop evidence, not "same champion".

## Representative selection

Within one group, representative preference is deterministic:

```text
trusted > supported > raw_candidate
identity-training recommendation
identity-label recommendation
strong board snapshot
current tracker evidence > carry > none
higher raw occupancy confidence
earlier timestamp
```

Representative images are copied into the curation directory so labeling
queues can be used without manually searching the source image tree.

## Cross-tabs

The curation summary reports:

```text
tier_by_location
tier_by_stage
recommendation_by_location
tracked_source_by_location
strong_snapshot_by_tier
```

This is intended to answer whether board and bench provide comparable usable
identity evidence before choosing a visual-model architecture.

## ML split contract

Temporal de-duplication is not enough to make samples independent.

All samples and visual groups from one match must remain in one split:

```text
split_unit = match_id
```

Forbidden:

```text
random crop split
random visual-group split across the same match
```

With multiple recorded matches, train/validation/test must be partitioned by
match.

## Classifier feature contract

The future visual identity model should consume pixels only (plus ordinary
pixel transforms).

Do not feed acquisition priors into the visual classifier.

Acquisition history belongs to a later resolver:

```text
visual identity probabilities
+ temporal evidence
+ acquisition history
+ board/bench constraints
-> identity resolver
```

This prevents the classifier from learning roster history instead of visual
champion appearance.
