# Stage 1 - Recorder

## Implemented

- Windows visible-window enumeration.
- Client-area bounds rather than decorated window bounds.
- MSS capture.
- Whole-frame visual-change detector.
- Match session lifecycle.
- Append-only PNG evidence store.
- SHA-256 indexed JSONL evidence records.
- Periodic and change-triggered keyframes.
- Automatic session close when the target window disappears.
- HTML replay.

## Commands

```powershell
tft-analyzer windows
tft-analyzer windows --title-regex "League of Legends"

tft-analyzer record
# or:
tft-analyzer record --handle 123456

tft-analyzer replay data/matches/<match_id> --open
```

`Ctrl+C` stops a recording cleanly.

## Output

```text
data/matches/<match_id>/
├── manifest.json
├── replay.html
└── evidence/
    ├── evidence_index.jsonl
    └── frames/
```

## Known limitation

The full-frame scene detector is temporary. TFT combat animation can create a lot
of change. Stage 2 should add ROI-aware sampling for HUD/shop/economy/board so
strategically relevant changes are captured precisely while animation is ignored.
