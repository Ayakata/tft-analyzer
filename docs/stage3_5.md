# Stage 3.5 — Match-local Background + Temporal Occupancy (0.13.0)

Geometry and footprint sampling are fixed and no longer calibrated here.

## Inputs

The tracker consumes the latest versioned footprint attempts artifact produced by:

```powershell
tft-analyzer perceive-board <match_dir>
```

For the accepted calibration match this is:

```text
board-bench-occupancy-0.12.0_attempts.jsonl
```

## Match-local background

A separate background model is fitted for every logical position:

```text
28 board cells + 9 bench slots = 37 prototypes
```

For each position, the low raw-score tail is used as background candidates. The
prototype stores robust feature medians and MAD-derived scales for:

```text
contrast
edge_density
saturation
bright_fraction
center_edge_delta
center_saturation_delta
```

Current footprint measurements are converted to a background-relative
`foreground_score` rather than compared to the same global arena texture.

## Temporal occupancy

`empty`/`occupied` initialization and changes require two repeated observations.
`uncertain` never mutates the stable state.

Bench tracking is always active.

Board tracking additionally has a conservative formation stability gate. A
board frame becomes canonical-usable only when the current frame has:

- enough known occupancy candidates;
- bounded uncertain-cell count;
- bounded foreground motion across cells;
- bounded proposed changes versus the stable board.

Large-motion frames remain evidence but do not rewrite the formation state.

This is intentionally a planning-like stability heuristic, not a semantic
combat-phase classifier.

## Command

```powershell
tft-analyzer track-board <match_dir> --timeline
```

Outputs live under `tracking/`:

```text
board-bench-background-0.13.0.json
board-occupancy-tracker-0.13.0.jsonl
bench-occupancy-tracker-0.13.0.jsonl
board-bench-occupancy-tracker-0.13.0_decisions.jsonl
board-bench-occupancy-tracker-0.13.0_summary.json
```
