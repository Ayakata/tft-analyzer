# Stage 3.0 - Dynamic player list / self HP (0.8.0)

## Goal

Add the first new perception field after the Evidence -> GameState foundation
was stabilized.

Player HP cannot be a static ROI because the right-side scoreboard is ordered
dynamically. The pipeline is therefore:

```text
players_panel
    |
    v
8 row candidates
    |
    v
self-row localization
    |--- visual highlight heuristic
    |--- optional player-name OCR
    |--- manual row override for calibration/debug only
    |
    v
HP candidate search + constrained OCR
    |
    v
Observation(kind=hp)
```

## Why player perception is a separate observation stream

The stable HUD OCR does not need to be rerun just because player-list
perception changes.

Stage 3.0 writes:

```text
observations/players-rapidocr-0.8.0.jsonl
```

while existing fixed-HUD observations remain in:

```text
observations/hud-rapidocr-0.4.3.jsonl
```

The tracker now merges the latest file from each configured producer stream.

This keeps perception modules independently rebuildable.

## Self-row localization

### Default: visual highlight

Each of the eight player rows receives a normalized warm/gold highlight score.

The recognizer selects a row only when:

```text
best_score >= min_highlight_score
and
best_score - second_best >= min_highlight_margin
```

This deliberately allows "unknown self row" instead of forcing a guess.

### Optional: player-name OCR

A stable player name can be configured or passed at runtime:

```powershell
--player-name "MyName"
```

When the OCR-assisted name match exceeds `min_name_match_score`, it is preferred
over the visual highlight heuristic.

### Manual row

For calibration only:

```powershell
--self-row 3
```

This bypasses row identity and verifies HP search/OCR geometry independently.

It is not suitable for full matches because scoreboard ordering changes.

## HP OCR

Once the self row is selected, the recognizer scans multiple narrow horizontal
candidate windows in the right portion of the row. Each candidate uses the
existing OCR preprocessing variants and a constrained 0..250 integer parser.

Observation confidence combines:

```text
self-row identity confidence
HP OCR confidence
```

using their geometric mean.

## Debug first

Before processing a match, run:

```powershell
tft-analyzer players-debug <frame>
```

Outputs:

```text
data/players_debug/<frame>_<profile>/
├── overlay.png
├── players_panel.png
├── result.json
├── rows/
└── hp_candidates/
```

The overlay shows all 8 candidate rows and the selected row.

If automatic self-row localization fails, run the same frame with the known
row index to test HP geometry separately:

```powershell
tft-analyzer players-debug <frame> --self-row 3
```

Optionally test name-assisted identification:

```powershell
tft-analyzer players-debug <frame> --player-name "MyName"
```

## Offline match perception

```powershell
tft-analyzer perceive-players `
  .\data\matches\<match_id>
```

This writes:

```text
players-rapidocr-0.8.0.jsonl
players-rapidocr-0.8.0_attempts.jsonl
players-rapidocr-0.8.0_summary.json
```

## End-to-end HP propagation

Stage 3.0 extends every existing HUD-derived contract:

```text
ObservationKind.HP
      ↓
TrackedHUDState.hp
      ↓
HP_CHANGED
      ↓
EventValidation(field=hp)
      ↓
GameState.player.hp
```

HP increases are not rejected by the tracker because game mechanics can
legitimately restore player health. Only impossible OCR range is rejected.

## Multi-stream tracking

Default tracker inputs are now:

```yaml
input_observation_globs:
  - hud-rapidocr-*.jsonl
  - players-rapidocr-*.jsonl
```

So after player perception:

```powershell
tft-analyzer track-hud .\data\matches\<match_id> --timeline
```

automatically merges both latest observation streams.

## Acceptance sequence

Do not start with the full match. Use one known frame where the scoreboard and
own HP are clearly visible:

```powershell
tft-analyzer players-debug <frame>
```

Acceptance questions:

1. Are the eight row boxes aligned?
2. Is the self row selected correctly?
3. What are the top two highlight scores and their margin?
4. Does HP OCR find the correct value?
5. Which HP candidate/variant wins?

Only after this calibration should the full match be processed.
