# Stage 5.5 — Human Label Audit & Dataset Policy

Version: 0.21.7

## Purpose

Manual annotation established a stronger semantic signal than the upstream
occupancy trust tier.

Therefore:

```text
human label = semantic truth
occupancy tier = provenance / quality metadata
```

The audit never rewrites labels and never modifies perception output.

## Identity tiers

Primary:

```text
target_type = champion
catalog validated
representative_tier = trusted
```

Secondary:

```text
target_type = champion
catalog validated
representative_tier = supported
```

Recovered candidate:

```text
target_type = champion
catalog validated
representative_tier = raw_candidate
```

These tiers allow future training experiments such as:

```text
primary only
primary + secondary
primary + secondary + recovered candidate
```

without pretending that upstream occupancy confidence is champion identity.

## Human no-unit labels

A human `no_unit` annotation means the crop is direct occupancy-error evidence.

All such rows are exported to:

```text
occupancy_hard_negative_manifest.csv
```

This manifest is intended for occupancy QA and possible future occupancy-model
training. It is separate from champion identity training.

## Cross-tabs and hotspots

The audit summarizes:

```text
target x location
target x representative tier
target x tracker source
target x slot
champion x training tier
champion x location
```

For each location/slot it also computes:

```text
labeled_group_count
champion_count
no_unit_count
uncertain_count
unusable_count
no_unit_rate
non_champion_rate
```

The highest occupancy-error slots are surfaced as hotspots.

## Completion policy

Global completeness:

```text
--require-complete
```

still means every curation queue must be labeled.

Queue-level completeness:

```text
--require-complete-queue identity_label
--require-complete-queue occupancy_qa
```

validates only the selected queue.

This matches the workflow where champion identity can be complete while
occupancy QA remains intentionally deferred.

## Split policy

The ML split unit remains:

```text
match_id
```

No crop-level or visual-group-level random split is allowed across one match.

## Visual classifier feature policy

Allowed:

```text
pixels / ordinary image transforms
```

Not classifier inputs:

```text
occupancy tier
tracker source
acquisition priors
semantic resolver state
```

Those signals remain available for downstream identity resolution and QA.
