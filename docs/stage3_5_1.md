# Stage 3.5.1 — HUD-aware canonical board snapshots

The 0.13.0 decisions showed that the known 1642.609 planning frame already had
eight background-relative `occupied` candidates. The canonical state remained
at five because the frame was blocked by the visual stability gate.

A second failure mode was independent per-cell carry-over: stale occupied cells
from older frames could coexist with newly accepted occupied cells, producing
impossible canonical counts of 10–11 while HUD level was 8.

0.13.1 does not loosen foreground thresholds.

## Canonical invariants

When tracked HUD context is available:

- canonical occupied count may not exceed `level`;
- candidate snapshots over `level` cannot mutate canonical board;
- updates are restricted to an early-round planning window;
- a snapshot with exactly `level` occupied candidates can replace the entire
  28-cell canonical board atomically.

Default planning window:

```text
2.5s <= time_since_stage_change <= 32.0s
```

Default full-level snapshot requirements:

```text
candidate occupied == HUD level
uncertain <= 14
mean occupied foreground >= 0.60
```

When the cap is exactly full, non-occupied cells are canonicalized to empty for
that snapshot. Cells that were raw `uncertain` are recorded with
`level_cap_inferred_empty`; raw perception itself remains unchanged.

If no HUD tracker file exists, the 0.13.0 visual gate remains as a fallback.

## Acceptance

No perception rerun is required:

```powershell
tft-analyzer track-board `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline
```

Expected known-frame behavior:

```text
1642.6 stable full-cap L8 candidate=8 canonical=8
```

and `tracked_over_cap` must remain zero.
