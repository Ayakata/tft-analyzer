# Stage 3.4 — Footprint-first occupancy diagnostics (0.12.0)

The 0.11.4 full-match run had correct geometry but unstable occupancy: board uncertain 31.8%, bench uncertain 26.9%, 251/188 raw snapshot changes.

Inspection of `board-bench-occupancy-0.11.0_attempts.jsonl` exposed two problems:

1. raw `OccupancyFeatures` were not actually serialized;
2. occupancy was measured on the tall context crop, while the logical footprint was debug-only.

0.12.0 changes the measurement contract:

```text
board native hex footprint -> masked features -> score
bench slot footprint       -> features        -> score
```

The larger context crop remains available for future unit identity and debug, but it no longer contributes to occupancy.

Feature weights and global thresholds are intentionally unchanged so the next full-match run isolates the effect of correcting the sampling region.

New aggregate artifacts:

```text
board-bench-occupancy-0.12.0_attempts.jsonl
board-bench-occupancy-0.12.0_summary.json
```

They persist raw feature vectors and per-position score/feature quantiles. Temporal/background stabilization comes after measuring these corrected footprint distributions.
