# Stage 2.1 - HUD perception

## Goal

Turn saved visual evidence into the first canonical `Observation` stream.

Fields:

- stage / round;
- gold;
- level;
- XP current / required.

Player HP is intentionally excluded because it requires dynamic localization
inside `players_panel`. Shop champion recognition is a later stage.

## Pipeline

```text
EvidenceRef
    |
    v
captured PNG
    |
    v
ROIRegistry
    |
    +--> stage_value
    +--> gold_value
    +--> level_value
    +--> xp_value
            |
            v
      preprocessing
            |
            v
 RapidOCR recognition-only
            |
            v
 constrained TFT parser
            |
            v
       Observation
```

## Why recognition-only OCR

The text location is already known from Stage 2.0. Running a general text
detector inside a 40-pixel-high HUD ROI adds unnecessary failure modes.

Each field first uses an RGB upscaled crop. If the OCR output cannot be parsed
confidently, a grayscale/autocontrast fallback is tried.

## Commands

Install/update:

```powershell
python -m pip install -e ".[dev]"
```

Single frame:

```powershell
tft-analyzer hud-debug `
  .\data\matches\<match_id>\evidence\frames\<frame>.png
```

Full saved match:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id>
```

Fast smoke test:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

Every fifth saved evidence frame:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --stride 5
```

## Output

```text
data/matches/<match_id>/observations/
├── hud-rapidocr-0.4.0.jsonl
├── hud-rapidocr-0.4.0_attempts.jsonl
└── hud-rapidocr-0.4.0_summary.json
```

`*_attempts.jsonl` is deliberately retained because failed/ambiguous OCR is
training and debugging data, not useless noise.

## Expected observation examples

```json
{
  "kind": "stage",
  "value": {
    "stage": 3,
    "round": 3,
    "raw_text": "3-3",
    "normalized_text": "3-3",
    "ocr_engine": "rapidocr",
    "ocr_variant": "rgb"
  }
}
```

```json
{
  "kind": "xp",
  "value": {
    "current": 12,
    "required": 20
  }
}
```

## Stage 2.1 acceptance criteria

- OCR initializes on Python 3.12 / Windows.
- A known frame reads approximately:
  - stage = 3-3;
  - level = 5;
  - XP = 12/20;
  - gold = 38.
- The full match produces a versioned observation JSONL.
- Every observation keeps its originating `evidence_id`.
- Failed OCR attempts remain inspectable.
