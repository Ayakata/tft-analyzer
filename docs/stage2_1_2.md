# Stage 2.1.2 - HUD presence gating and dynamic stage localization

## Motivation

Two issues remained after 0.4.1:

1. Early `1-x` stage labels render slightly farther right than later stages.
2. Generic OCR may return plausible digits from visual texture when a HUD field
   is not actually present.

## Stage localization

`stage_text` is no longer the only OCR location. A wider
`stage_search_region` generates several horizontally shifted candidate crops.

Each candidate is preprocessed and OCR'd; only valid `N-N` parses compete, and
the highest-confidence valid candidate becomes the observation.

This avoids state-dependent rules such as "if stage < 2, move right".

## Presence gate

Before OCR, a lightweight non-ML gate measures:

- dark-pixel fraction;
- bright glyph-like fraction;
- edge density.

For stage, only bright/edge structure is required because the top HUD differs
from the bottom economy panel.

The gate is intentionally permissive. It rejects obvious non-HUD texture but
does not identify the value itself.

## Metrics

The summary now distinguishes:

```text
frames -> present -> parsed -> accepted
```

and reports both:

- `parse_rate_when_present`
- `accepted_rate_when_present`

so absent UI is not counted as an OCR failure.

## Debug

`hud-debug` adds:

```text
stage_candidates/
  stage_candidate_0.png
  stage_candidate_0_rgb_tight.png
  ...
```

and records the selected candidate and candidate box in `hud_result.json`.

## Comparison

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

0.4.2 writes `hud-rapidocr-0.4.2*`, preserving earlier baselines.
