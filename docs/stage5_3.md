# Stage 5.3 — Identity Labeling Workflow

Version: 0.21.3

## Goal

Turn curated visual representatives into validated semantic labels without
making an external annotation tool the source of truth.

Workflow:

```text
0.21.2 visual groups
    ↓
prepare labeling package
    ↓
human annotation / optional external UI
    ↓
import and validate
    ↓
canonical labeled_visual_groups.jsonl
    ↓
coverage and class-balance report
```

## Label package

`prepare-identity-labeling` copies every curated representative into a
self-contained package and creates one editable `labels.csv`.

The package keeps the curation queues separate on disk:

```text
images/identity_label/
images/occupancy_qa/
```

It also writes:

```text
label_schema.json
cvat_image_manifest.csv
package.json
README.md
```

`cvat_image_manifest.csv` maps flat image filenames to project
`visual_group_id`. It is a bridge for an external image annotation UI, not a
native CVAT annotation interchange format.

## Label semantics

Supported targets:

```text
champion
no_unit
uncertain
unusable
```

Rules:

```text
target_type=champion
    -> champion_label required

target_type=no_unit|uncertain|unusable
    -> champion_label empty
```

Rows with empty `target_type` remain unlabeled and are ignored during partial
import.

## Champion validation

When champion labels are present, the importer uses the pinned Data Dragon
catalog and the match TFT set.

The annotator may type display-like variants such as:

```text
Rhaast
Rek'Sai
```

The importer normalizes them and requires a unique entry in the exact match set.

Unknown or ambiguous labels are rejected rather than silently added as new
classes.

## Partial annotation

Partial imports are first-class:

```text
allow_partial_import = true
```

This permits repeated annotation sessions without requiring all ~1000+ curated
groups to be labeled at once.

For a final completeness check:

```text
tft-analyzer import-identity-labels <match_dir> --require-complete
```

## Canonical labeled artifact

Every imported label becomes a `LabeledSlotVisualGroup` containing:

```text
visual group / match / queue provenance
location + slot
representative evidence quality
target_type
canonical champion label/id when applicable
catalog validation status
annotator / notes
training eligibility
split_key = match_id
```

External annotation state is not consumed directly downstream.

## Training eligibility

Champion classification training eligibility requires:

```text
target_type = champion
representative recommended_for_identity_training_after_label = true
catalog validation = true
```

This means a supported/carry-only representative can still be labeled and used
for analysis, but is not automatically admitted into the clean training
manifest.

## Occupancy negatives

A human label:

```text
target_type = no_unit
```

is useful for occupancy hard-negative training only when the curated source
queue was:

```text
occupancy_qa
```

A `no_unit` result from the identity queue contradicts stronger upstream
occupancy evidence. It is counted as a QA conflict and excluded from automatic
negative-training export.

## Reports

The import summary includes:

```text
label coverage
target-type counts
queue coverage
location counts
champion class count
training-eligible champion groups
occupancy-negative groups
identity-queue no_unit conflicts
```

Per champion:

```text
visual_group_count
member_sample_count
training_eligible_group_count
match_count
board / bench group counts
```

`match_count` is a key readiness metric. Many visual groups from one recorded
match do not create an independent validation set.

## Split and feature policy

The split unit remains:

```text
match_id
```

Never random-split crops or visual groups from the same match.

The future visual identity classifier consumes pixels, not acquisition-history
priors. Acquisition evidence remains reserved for a later semantic resolver.
