# Stage 2.0 - Layout and ROI contract

## Goal

Introduce the first perception-facing contract without implementing OCR or
champion recognition yet.

```text
CapturedFrame
    -> LayoutProfile
    -> ROIRegistry
    -> normalized ROI -> PixelROI
    -> crop / overlay / future recognizer
```

## Why normalized coordinates

The initial profile was calibrated on 1920x1080, but ROI coordinates are stored
in `[0, 1]`. The same 16:9 profile therefore resolves to 1600x900 or 2560x1440.

This does **not** mean every TFT layout is already universal. In-game UI scale,
ultrawide modes and future UI changes may require separate profiles. The profile
ID is explicit so new variants can be added without changing recognizers.

## Initial profile

`configs/layouts/tft_16_9_default.yaml`

It contains:

- stage value;
- optional phase banner;
- level;
- XP;
- gold;
- dynamic `players_panel` search area (player HP is not a static ROI);
- whole shop strip;
- five full shop cards;
- five portrait subregions.

## Debug command

```powershell
tft-analyzer roi-debug .\path\to\frame.png --open
```

The command creates:

```text
data/roi_debug/<image>_<profile>/
├── overlay.png
├── roi_manifest.json
└── crops/
    ├── stage_value.png
    ├── gold_value.png
    ├── shop_0_card.png
    └── ...
```

Select only a subset when tuning a profile:

```powershell
tft-analyzer roi-debug frame.png `
  --roi gold_value `
  --roi level_value `
  --roi shop_0_card `
  --open
```

## Acceptance criterion

Run `roi-debug` on several real match frames from different phases. The boxes
must consistently cover the intended UI elements. Small tuning changes belong in
the YAML profile, not in Python code.

The static HUD/shop contract is now considered validated. `player_hp` was removed
from the static profile because the local player row moves vertically with the
right-side ranking list. Stage 2.1 will implement OCR for stage/gold/level/XP;
player HP will later be extracted by `PlayerListRecognizer` from `players_panel`.
