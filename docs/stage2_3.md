# Stage 2.3 - Primitive HUD Event Detector (0.6.0)

## Goal

Turn canonical tracked HUD state changes into immutable primitive `GameEvent`
objects.

```text
TrackedHUDState
      |
      v
HUDEventDetector
      |
      +--> ROUND_START
      +--> LEVEL_CHANGED
      +--> XP_CHANGED
      +--> GOLD_CHANGED
```

This stage records **what changed**, not **why it changed**.

It does not yet infer:

- `PURCHASE_XP`;
- `REFRESH_SHOP`;
- `BUY_UNIT`;
- income sources;
- combat results.

Those require more observations and/or higher-level inference.

## Why `ROUND_START`, not a new `ROUND_CHANGED`

The core contract already contains `EventType.ROUND_START`.

A detected transition stores both sides:

```json
{
  "event_type": "round_start",
  "payload": {
    "field": "stage",
    "from": {"stage": 3, "round": 7},
    "to": {"stage": 4, "round": 1}
  }
}
```

so a duplicate enum is unnecessary.

## Baselines

The first observed value of each field establishes its baseline and does not
emit an event by default.

A later different observed value emits one event.

Repeated equal observations only refresh the baseline timestamp/provenance.

This is important for timing:

```text
10s gold=50
19s gold=50
29s gold=43
```

The event transition window is `[19s, 29s]`, not `[10s, 29s]`.

## Carried/stale fields

Only `TrackedField.status == observed` may create or refresh event baselines.

`carried` values are state continuity, not new evidence, and never create
events.

## Event time versus transition window

The event timestamp is the first observation of the new value.

The exact change happened somewhere between the last observation of the old
value and the first observation of the new value:

```json
"transition_window": {
  "start_s": 19.0,
  "end_s": 29.0,
  "width_s": 10.0
}
```

A wide timing window is recorded as a timing warning. It does not reduce the
semantic confidence that the value changed.

## Primitive payloads

### Gold

```json
{
  "from": {"gold": 50},
  "to": {"gold": 43},
  "delta": -7
}
```

### Level

```json
{
  "from": {"level": 7},
  "to": {"level": 8},
  "delta": 1
}
```

### XP

```json
{
  "from": {"current": 54, "required": 60},
  "to": {"current": 2, "required": 68},
  "requirement_changed": true,
  "current_delta": null
}
```

### Stage / round

```json
{
  "from": {"stage": 3, "round": 7},
  "to": {"stage": 4, "round": 1},
  "stage_changed": true,
  "round_changed": true
}
```

## Provenance

Every event keeps:

- old/new observation IDs;
- old/new evidence IDs;
- old/new tracked state IDs.

Perception implementation details remain behind those references.

## CLI

Automatic latest tracker:

```powershell
tft-analyzer detect-hud-events `
  .\data\matches\<match_id> `
  --timeline
```

Explicit tracker:

```powershell
tft-analyzer detect-hud-events `
  .\data\matches\<match_id> `
  --states .\data\matches\<match_id>\tracking\hud-state-tracker-0.5.1.jsonl `
  --timeline
```

Print existing events:

```powershell
tft-analyzer hud-events `
  .\data\matches\<match_id>\events\hud-event-detector-0.6.0.jsonl
```

## Expected full-match sanity check

For the validated 271-state match, Stage 2.2 reported semantic changes:

```text
stage = 32
level = 6
xp    = 29
gold  = 73
```

Therefore Stage 2.3 should emit:

```text
ROUND_START   32
LEVEL_CHANGED  6
XP_CHANGED    29
GOLD_CHANGED  73
----------------
TOTAL         140
```

If those counts differ, event extraction or input version selection should be
investigated before moving forward.

## Next

Stage 2.4 can introduce a `GameStateReducer` that consumes primitive events and
builds the first canonical full `GameState` sequence.

Only after that should higher-level action/event inference begin.
