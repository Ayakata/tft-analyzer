# Stage 2.4 - Event validation + canonical GameState reducer (0.7.0)

## Purpose

Stage 2.3 deliberately emitted immutable primitive facts without explaining or
correcting them.

Stage 2.4 adds two derived layers:

```text
Primitive GameEvent
        |
        v
HUDEventValidator
        |
        +--> trusted
        +--> timing_uncertain
        +--> suspicious
        |
        v
HUDGameStateReducer
        |
        v
canonical GameState
```

Neither layer mutates the primitive event file.

## Side-specific confidence

A primitive event uses a conservative confidence derived from both sides of the
transition. That is useful for the event itself, but insufficient for state
reconstruction.

Example:

```text
gold 1 -> 52
```

may have:

```text
old value confidence = 0.59
new value confidence = 0.99
```

The transition is suspicious because the old side is weak, but the new target
is still strong enough to repair canonical state.

Validator resolves old/new confidence through `GameEvent.source_state_ids`.

## EventValidation

Each validation stores:

```text
quality
reasons
from_confidence
to_confidence
transition_window_s
apply_to_state
```

`apply_to_state` is intentionally separate from `quality`.

Possible case:

```text
quality = suspicious
reason = low_previous_confidence
apply_to_state = true
```

This means "the transition story is questionable, but the newly observed
target is trustworthy."

## Quality rules

### Suspicious

A primitive event is suspicious when:

- previous source confidence is below the field threshold;
- target source confidence is below the field threshold;
- target semantics are invalid.

### Timing uncertain

An otherwise trustworthy event is timing-uncertain when:

- transition window exceeds the configured threshold;
- stage transition is non-adjacent, such as `1-2 -> 1-4`.

A timing-uncertain event is still normally applied to canonical state.

## Reducer bootstrap

Primitive events intentionally do not emit initial values. Therefore the
reducer initializes each HUD field from its first `observed` tracked value.

After initialization, only validated primitive events change the field.

```text
TrackedHUDState -> initial field bootstrap only
Validated events -> all subsequent changes
```

This keeps the event layer honest without losing initial values.

## Recovery after skipped noise

Suppose validation produces:

```text
41 -> 17   suspicious, target weak, skip
17 -> 1    suspicious, target weak, skip
1  -> 52   suspicious old side, target strong, apply
```

Canonical state remains:

```text
41
41
52
```

The last reducer decision is:

```text
applied_with_mismatch
reason=trusted_target_recovery_from_source_mismatch
```

Nothing is silently rewritten in primitive evidence.

## GameState

`PlayerState` now includes:

```text
xp_required
```

so canonical state can preserve TFT XP semantics:

```text
level=8
xp=2
xp_required=68
```

`GameState` also preserves source tracked-state IDs in addition to source event
IDs.

## CLI

Validate primitive events:

```powershell
tft-analyzer validate-hud-events `
  .\data\matches\<match_id> `
  --timeline
```

Build canonical state:

```powershell
tft-analyzer reduce-game-state `
  .\data\matches\<match_id> `
  --timeline
```

Outputs:

```text
validation/
├── hud-event-validator-0.7.0.jsonl
└── hud-event-validator-0.7.0_summary.json

states/
├── hud-game-state-reducer-0.7.0.jsonl
├── hud-game-state-reducer-0.7.0_decisions.jsonl
└── hud-game-state-reducer-0.7.0_summary.json
```

## Acceptance focus on the current full match

The most informative section is around the previously observed low-confidence
gold sequence near 913-943 seconds.

Expected qualitative behavior:

```text
41 -> 17  => suspicious / skip
17 -> 1   => suspicious / skip
1 -> 52   => likely suspicious because old side is weak,
             but apply if target side is strong
```

The reducer should therefore avoid exposing `17` and `1` as canonical gold,
while recovering to a later high-confidence value.

The exact validation counts are intentionally not hard-coded: Stage 2.4 is the
first layer where source-side confidence, timing, and completeness flags can
overlap.
