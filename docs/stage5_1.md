# Stage 5.1 — Board/Bench Identity Observation Contract + Dataset Export

Current release: 0.21.1

## Goal

Prepare a reproducible champion-identity dataset from the already calibrated
TFT board/bench geometry before introducing a classifier or visual resolver.

This stage is perception infrastructure only.

## Inputs

The exporter joins four existing evidence layers:

```text
evidence frames
board-bench occupancy attempts
tracked board/bench states
0.20.1 acquisition history
```

No new champion identity is inferred.

## Crop geometry

Identity samples use the existing calibrated `context_box`, not a newly tuned
ROI.

For board cells this is the perspective-aware taller crop surrounding the
native hex footprint.

For bench slots this is the taller calibrated context crop surrounding the
logical bench footprint.

The original `footprint_box` is retained in the manifest for occupancy/local
geometry reasoning.

## Default sample gate

A crop is exported by default only when:

```text
raw occupancy status == occupied
raw occupancy confidence >= 0.55
scene_valid == true
```

This is deliberately based on the current-frame raw visual observation. A
canonical tracker state carried from older evidence cannot by itself create an
identity training sample.

`tracked_is_current_evidence` records whether the temporal tracker state for
the slot was refreshed by this exact evidence frame.

## Scene semantics

The arena scene guard is reused from the accepted 0.13.5 tracker.

Scene-invalid frames are excluded by default. They can be exported explicitly
for QA with:

```text
--allow-scene-invalid
```

but are not recommended as normal champion-identity training examples.

## Acquisition prior

The 0.20.1 acquisition layer is attached as an optional historical prior.

Critical rules:

```text
historical only
non-exhaustive
not current ownership
not a label
no future leakage
```

For timestamp T, the exporter selects only the latest roster context whose
DecisionEpisode end timestamp is <= T.

Therefore a BUY reconstructed from an episode ending at 466.5s cannot influence
a crop captured at 456.3s.

Example prior:

```text
rhaast acquired>=3
?zoe x1
```

means that those identities have historical acquisition evidence. It never
means the current slot must be one of them.

## Manifest contract

One `SlotIdentityObservation` per exported crop contains:

```text
sample_id
match_id
timestamp_s
evidence_id
stage

location = board | bench
slot_id
row/col or bench index

source_frame_uri
crop_uri
crop_sha256
crop dimensions
context_box
footprint_box

raw occupancy status/confidence/score

tracked occupancy status/confidence/foreground
tracked source evidence id
tracked_is_current_evidence

scene_valid/score
board usable
strong snapshot
gate reason
HUD level
capacity status

acquisition priors
prior source decision/end/age

identity_search_space_exhaustive = false
current_ownership_established = false

label_status = unlabeled
champion_label = null
```

## Dataset layout

```text
datasets/
  slot-identity-dataset-exporter-0.21.1/
    manifest.jsonl
    labels_template.csv
    summary.json
    README.md
    images/
      board/
      bench/
```

`crop_uri` is relative to the dataset root, so the generated directory can be
moved as one portable unit.

## Label workflow

`labels_template.csv` is intentionally simple and can be filled manually or
converted into a later CVAT/import format.

0.21.0 does not mutate `manifest.jsonl` with guessed identities.

## Non-goals

Not implemented here:

```text
champion classifier
visual identity resolver
temporal identity tracker
current roster reconstruction
board-vs-bench ownership assignment
star level
items
traits
board strength
```

These belong to subsequent Stage 5 releases.


## 0.21.1 quality-tier refinement

The canonical 0.21.0 match export showed that raw occupancy alone is too weak
to define a clean champion-identity training set. High raw scores can still
conflict with temporal occupancy state.

0.21.1 therefore distinguishes the complete observation pool from the clean
training subset.

### trusted

A crop is `trusted` when the current raw observation says `occupied` and:

```text
tracked occupied source == current evidence
```

or, for board cells:

```text
accepted strong board snapshot
AND tracked occupied
```

These samples are recommended for identity labeling and clean identity
training.

### supported

A crop is `supported` when:

```text
raw occupied
tracked occupied
tracked source = older evidence / carry
```

These samples are useful for manual identity labeling but are not enabled for
clean training by default.

### raw_candidate

A crop remains `raw_candidate` when occupancy is not sufficiently supported:

```text
raw occupied vs tracked empty
raw occupied vs tracked unknown
raw occupied with no tracker support
scene invalid
raw empty/uncertain exported explicitly
```

These samples remain in the dataset for occupancy QA and hard-negative mining.

### Label target contract

`labels_template.csv` now exposes:

```text
target_type
champion_label
label_status
```

Supported `target_type` values:

```text
champion
no_unit
uncertain
unusable
```

`no_unit` is intentionally first-class so false-positive occupancy crops can
be labeled rather than discarded.

### Important non-claim

`recommended_for_identity_training=true` means only that occupancy evidence is
clean enough to use the crop in a champion-identity training workflow after
identity labeling.

It does not infer or validate champion identity by itself.
