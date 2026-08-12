# Stage 2.2 - Temporal fusion / HUD state tracking (0.5.0)

## Goal

Convert independent HUD `Observation` objects into a stable time-indexed state
timeline without yet inventing semantic `GameEvent` objects.

```text
Evidence timeline
      +
HUD Observations
      |
      v
HUDStateTracker
      |
      +--> TrackedHUDState JSONL
      |
      +--> TrackingDecision JSONL
```

## Why an intermediate tracked state exists

Perception describes what one frame appears to contain.

Tracking describes what the system currently believes the game state is, after
considering:

- recent history;
- field freshness;
- impossible regressions;
- suspicious jumps;
- missing observations.

Event extraction is a separate next step.

## Fields

Stage 2.2 tracks:

- `stage`;
- `gold`;
- `level`;
- `xp`.

## Missing observations

A missing observation is not interpreted as a changed value.

Recent accepted values are carried forward for a configurable period:

```yaml
max_age_seconds:
  stage: 30
  gold: 8
  level: 20
  xp: 8
```

Carried confidence decays linearly with age.

After the maximum age the field becomes `stale` and its value is omitted.

## Constraints

### Stage

- regression is rejected;
- ordinary forward progress is accepted;
- very large forward jumps require repeated confirmation.

### Level

- regression is rejected;
- normal increases are accepted;
- unusually large jumps require confirmation.

### XP

- regression with the same XP requirement is rejected;
- a changed requirement allows XP to reset because it likely indicates a
  level transition.

### Gold

Gold is not heavily smoothed because real purchases, income and roll-downs may
change it rapidly. Semantic validation of gold deltas belongs to event
extraction.

## Output

```text
data/matches/<match_id>/tracking/
├── hud-state-tracker-0.5.0.jsonl
├── hud-state-tracker-0.5.0_decisions.jsonl
└── hud-state-tracker-0.5.0_summary.json
```

Each field in a state has status:

```text
observed
carried
stale
unknown
```

and keeps provenance to the source observation/evidence.

## CLI

The latest `hud-rapidocr-*.jsonl` is selected automatically:

```powershell
tft-analyzer track-hud .\data\matches\<match_id> --timeline
```

Or specify a particular baseline:

```powershell
tft-analyzer track-hud .\data\matches\<match_id> `
  --observations .\data\matches\<match_id>\observations\hud-rapidocr-0.4.3.jsonl `
  --timeline
```

Print an existing tracked timeline:

```powershell
tft-analyzer hud-timeline `
  .\data\matches\<match_id>\tracking\hud-state-tracker-0.5.0.jsonl
```

A `~` after a value means it was carried from a recent observation.

## Next

Stage 2.3 will compare consecutive stable states and emit candidate semantic
events such as:

```text
ROUND_CHANGED
LEVEL_CHANGED
GOLD_CHANGED
XP_CHANGED
```

Later, shop observations will allow stronger inference such as BUY / REFRESH /
PURCHASE_XP.
