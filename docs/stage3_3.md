# Stage 3.3 - Board / Bench geometry + occupancy (0.11.0)

## Scope

This stage intentionally solves only where local units may be and whether each
position looks occupied.

```text
Evidence frame
   -> board perspective lattice (4 x 7)
   -> bench lattice (9)
   -> per-position visual features
   -> occupied / empty / uncertain
   -> BOARD and BENCH observations
```

Champion identity, stars, items, and temporal GameState integration are out of
scope until geometry/occupancy passes real-match acceptance.

## Geometry contract

Board geometry is represented by the normalized centre of the first and last
hex in each of four perspective rows. Seven centres are interpolated per row.
This is preferable to a rectangular grid because the rendered board widens
toward the player.

Bench uses a normalized left/right centre line with nine equally-spaced slots.
All coordinates live in `perception.board_bench` in `configs/default.yaml` so
real-frame calibration does not require code changes.

## Occupancy contract

The recognizer persists raw visual features for every position and uses a
three-way state:

- `occupied`
- `empty`
- `uncertain`

Ambiguous positions are never forced into a binary answer. Initial thresholds
are deliberately conservative and must be calibrated from the user's recorded
match.

## Acceptance

Start with a planning-phase frame where the user's board and bench are clearly
visible:

```powershell
tft-analyzer board-debug <frame.png>
```

Inspect `overlay.png` and the 28/9 crops. Geometry acceptance comes before
threshold tuning.

Only after the centres/windows line up with the actual board and bench:

```powershell
tft-analyzer perceive-board .\\data\\matches\\20260812T164303Z_4c85a55ea6
```

Useful metrics are uncertain rate, mean occupied counts, per-cell/slot status
counts, and raw snapshot changes. No downstream tracker should consume these
observations yet.
