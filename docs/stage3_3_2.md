# Stage 3.3.2 — Bench Geometry Fix

## Goal

Fix bench slot geometry using a real planning-phase frame and make debug
visualization distinguish:

- logical slot footprint
- larger sampling context crop

## What changed

- bench anchors shifted left (`bench_left = [0.230, 0.790]`)
- bench span widened while keeping the right anchor stable
- bench context crop enlarged upward to include more champion body
- bench footprint geometry added for clearer overlay semantics
- board debug overlay now draws:
  - thin context crop
  - stronger footprint box
  - slot/cell anchor point

## Why

A fixed occupancy crop should not be interpreted as a full character bbox.
For planning-phase board/bench perception we need a stable slot geometry first,
then future temporal occupancy calibration can build on top of it.
