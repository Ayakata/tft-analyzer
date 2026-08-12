# Stage 2.1.1 - Tight HUD OCR (0.4.1)

The 0.4.0 baseline on 20 real evidence frames showed:

- stage parsed: 6/20;
- gold parsed: 15/20;
- level parsed: 18/20;
- XP parsed: 4/20.

The infrastructure was correct, but wide HUD ROIs included decorative frame
edges and generic OCR was especially weak on XP.

## Changes

### Separate context and OCR ROIs

The original ROIs remain for visual diagnostics:

```text
stage_value
level_value
xp_value
gold_value
```

Recognition now uses tighter text-only regions:

```text
stage_text
level_text
xp_text
gold_number
```

This preserves layout debuggability while allowing OCR-specific calibration.

### Preprocessing

Every tight crop may be tried as:

1. `rgb_tight`;
2. `gray_tight`;
3. `binary_tight` - bright TFT glyphs converted to dark text on white.

A successful high-confidence `rgb_tight` parse stops the fallback chain early.

### Metrics

`parse_rate` and `accepted_rate` are now reported separately.

A parsed value may still be rejected when its confidence is below
`min_observation_confidence`.

Example:

```text
level parsed=18/20 (90.0%) accepted=12/20 (60.0%)
```

### Debug output

`hud-debug` saves both:

```text
crops/
  stage_context.png
  stage_ocr.png
  ...
```

and all preprocessing variants.

## Comparison workflow

Run the same first 20 evidence frames:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

0.4.1 writes a separate producer:

```text
hud-rapidocr-0.4.1*.jsonl/json
```

so it can be compared directly with the retained 0.4.0 baseline.

If XP remains weak after tight ROIs, the next step is a specialized numeric HUD
recognizer rather than additional generic-OCR heuristics.
