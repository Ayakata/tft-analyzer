# Stage 3.3.3 — Bench vertical anchor correction

Two planning-phase overlays at 1920x1080 showed a consistent calibration error:

- bench horizontal span matched the physical nine-slot row;
- the slot footprint was drawn on the lower foliage/decorative edge;
- the actual bench platform is approximately 48 px higher.

The fix changes only:

```yaml
bench_left:  [0.230, 0.745]
bench_right: [0.715, 0.745]
```

At 1920x1080 the common anchor Y becomes:

```text
805 px
```

instead of:

```text
853 px
```

Context and footprint geometry remain:

```text
context:   width=120, up=142, down=12
footprint: width=72,  up=64,  down=16
```

No occupancy thresholds or board geometry are modified.
