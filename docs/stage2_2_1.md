# Stage 2.2.1 - Tracker stabilization (0.5.1)

This patch stabilizes temporal tracking after the full 271-frame match run.

## Canonical tracked values

Tracking now strips perception/debug metadata before equality checks and storage:

```text
stage -> {stage, round}
gold  -> {gold}
level -> {level}
xp    -> {current, required}
```

OCR fields such as `raw_text`, `ocr_variant`, `ocr_candidate` and
`presence_score` remain in the source `Observation` and are reachable through
provenance, but they no longer affect state equality.

## Freshness defaults

```yaml
max_age_seconds:
  stage: 45.0
  gold: 15.0
  level: 45.0
  xp: 15.0
```

The 15-second gold/XP TTL covers the normal ~10-second evidence cadence without
keeping genuinely missing HUD data alive indefinitely.

## Summary diagnostics

The tracking summary now includes per-field:

- decision actions;
- decision reasons;
- semantic value change counts;
- observed/carried/stale/unknown state counts.

After validation, Stage 2.2 is ready to close and Stage 2.3 can consume only
canonical tracked-state differences.
