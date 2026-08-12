# Stage 2.1.3 - Presence confidence cleanup (0.4.3)

## Scope

This is a diagnostics/semantics patch only.

No ROI, OCR preprocessing, parser, stage-localization, or observation-selection
logic is changed.

## Problem in 0.4.2

Presence decisions were conjunctive:

```text
dark_ok AND edge_ok AND bright_ok
```

but the reported score was based on an average of feature ratios. Therefore a
crop could correctly be classified as:

```text
present = false
```

while still reporting:

```text
presence_score = 1.0
```

because strong features compensated numerically for the failed required one.

## 0.4.3 semantics

Each required feature is normalized against its threshold:

```text
criterion_score = clamp(value / threshold, 0, 1)
```

and final presence confidence is:

```text
presence_score = min(required criterion scores)
```

Therefore:

```text
PRESENT => presence_score == 1.0
ABSENT  => presence_score < 1.0
```

under the current hard-threshold gate.

This makes `presence_score` interpretable and prevents contradictory diagnostic
output.

## CLI

`hud-debug` now prints explicitly:

```text
presence=PRESENT(1.000)
```

or:

```text
presence=ABSENT(0.217)
```

instead of showing only a bare numeric value.

## Versioning

The perception producer is now:

```text
hud-rapidocr-0.4.3
```

so outputs are written alongside, rather than over, the 0.4.0/0.4.1/0.4.2
baselines.
