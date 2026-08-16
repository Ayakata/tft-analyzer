# Stage 3.3.4 — Native Hex Grid Calibration

The board lattice is recalibrated from TFT's own cyan placement overlay instead
of fitting rectangular crops by eye.

At 1920x1080 the calibrated row endpoints are approximately:

```text
r0: (563, 447) -> (1250, 447)
r1: (612, 516) -> (1321, 516)
r2: (534, 593) -> (1273, 593)
r3: (584, 675) -> (1346, 675)
```

The alternating horizontal offset is intentional and reflects the native hex
layout. Row spacing and horizontal span increase toward the camera. The calibration was recovered directly from the native cyan mask; alternating rows are shifted by roughly half a cell.

Debug output separates two concepts:

- `context crop`: rectangular image region used by occupancy features;
- `hex footprint`: logical cell where the champion is standing.

A champion may extend well above its hex footprint; this is not a geometry
error. The footprint is now drawn as a six-point flat-top hex while the context
crop remains a thin rectangle.

Bench geometry and all occupancy thresholds are unchanged from 0.11.3.
