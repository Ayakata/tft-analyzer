# TFT Analyzer

Trajectory-first Teamfight Tactics recorder, post-game analyzer and future ML/RL research platform.

## Status

- Stage 0: domain/contracts - complete
- Stage 1: recorder/replay - complete
- Stage 1.1: HWND/WGC capture - complete
- Stage 2.0: normalized layout + ROI debug - implemented
- Stage 2.1: HUD OCR observations - next

## Install / update

```powershell
python -m pip install -e ".[dev]"
pytest
```

## Capture

```powershell
tft-analyzer windows --process-regex "League"
tft-analyzer record --handle <HWND> --backend wgc --no-fallback
```

## ROI debug

Choose any real evidence frame:

```powershell
tft-analyzer roi-debug `
  .\data\matches\<match_id>\evidence\frames\<frame>.png `
  --open
```

Default profile:

```text
configs/layouts/tft_16_9_default.yaml
```

Output:

```text
data/roi_debug/<image>_<profile>/
├── overlay.png
├── roi_manifest.json
└── crops/
```

The initial profile is calibrated on a real 1920x1080 match capture but stores
normalized coordinates, so it can scale across 16:9 resolutions. Different UI
scale/aspect-ratio layouts can be introduced as separate profiles later.

See `docs/stage2_0.md`.
