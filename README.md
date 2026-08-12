# TFT Analyzer

Trajectory-first Teamfight Tactics recorder, post-game analyzer and future ML/RL research platform.

## Status

- Stage 0: domain/contracts - complete
- Stage 1: recorder/replay - complete
- Stage 1.1: HWND/WGC capture - complete
- Stage 2.0: normalized layout / ROI contract - complete
- Stage 2.1: HUD perception - implemented\n- Stage 2.1.1: tight HUD OCR + accepted metrics - complete
- Stage 2.1.2: HUD presence + dynamic stage localization - complete
- Stage 2.1.3: presence confidence semantics cleanup - implemented

Current version: **0.4.3**

## Install/update on Windows

```powershell
python -m pip install -e ".[dev]"
pytest
```

## Recorder

```powershell
tft-analyzer windows --process-regex "League"
tft-analyzer record --handle <HWND> --backend wgc --no-fallback
```

## ROI debug

```powershell
tft-analyzer roi-debug <frame.png> --open
```

## HUD OCR debug

```powershell
tft-analyzer hud-debug <frame.png>
```

## Process a saved match

Smoke test:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

Full saved evidence:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id>
```

See `docs/stage2_1.md`.


## 0.4.1 baseline comparison

Re-run the same first 20 saved evidence frames:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

The console now reports both `parsed` and `accepted`.


## 0.4.2

Run the same 20-frame baseline:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

The summary now reports `present`, `parsed`, and `accepted` separately.


## 0.4.3

Presence diagnostics are now semantically consistent:

```text
PRESENT => score 1.0
ABSENT  => score < 1.0
```

No OCR/ROI behavior changed.
