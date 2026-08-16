# Stage 3.3.1 - Perspective geometry calibration (0.11.1)

Real `board-debug` frame:

```text
00000093_00000690.062_5423f282c294.png
```

showed that the lattice centres themselves already align well with the board
and bench.

The geometry issue is the sampling window: 0.11.0 used one constant
`116 x 102` board rectangle for all four rows despite the camera perspective.

That makes the upper row slightly too wide relative to its cell spacing and the
lower rows too narrow for the larger projected champion/cell footprint.

## 0.11.1 board windows

Reference 1920x1080 values:

```text
row 0: width=100  up=68  down=26
row 1: width=112  up=72  down=28
row 2: width=124  up=78  down=30
row 3: width=136  up=84  down=32
```

The board lattice centres are unchanged:

```yaml
board_row_left:
  - [0.330, 0.355]
  - [0.305, 0.455]
  - [0.280, 0.555]
  - [0.255, 0.655]

board_row_right:
  - [0.670, 0.355]
  - [0.695, 0.455]
  - [0.720, 0.555]
  - [0.745, 0.655]
```

## Bench window

Bench centres are also unchanged.

The crop changes from:

```text
width=80  up=58  down=16
```

to:

```text
width=88  up=66  down=14
```

This samples more champion body above the bench anchor while reducing lower HUD
contamination.

## Important

Occupancy thresholds and feature weights are intentionally unchanged.

First accept geometry on the same debug frame, then run the full match and use
those statistics to calibrate occupancy separately.
