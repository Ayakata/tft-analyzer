# Stage 2.4.1 - Canonical state stabilization (0.7.1)

This patch keeps the semantic behavior of 0.7.0 and fixes three structural
issues discovered during the full-match acceptance run.

## 1. Bounded provenance

0.7.0 accumulated all source event/state IDs in every `GameState`.

0.7.1 uses:

```text
parent_state_id
applied_event_ids
source_state_ids
```

where event/state IDs are only the direct sources for that canonical state.

Full lineage is reconstructed by following `parent_state_id`.

This changes provenance growth from cumulative history copying to bounded
per-state references.

## 2. Event routing by tracked state ID

Events are no longer joined to tracked states by exact floating-point timestamp
equality.

`GameEvent.source_state_ids[-1]` is treated as the tracked state carrying the
new target value.

Therefore reducer routing is stable even if timestamp serialization or
precision changes.

## 3. Field-level confidence and freshness

`GameState.field_meta` now stores, per field:

```text
confidence
last_observed_at_s
age_s
source_observation_id
source_evidence_id
source_tracked_state_id
```

The reducer processes every tracked state.

When a repeated `observed` value equals the current canonical value, it updates
metadata only:

```text
METADATA_REFRESHED
```

No new semantic `GameState` is emitted.

This fixes the 0.7.0 behavior where a low-confidence transition could limit
`GameState.confidence` for minutes even after many strong confirmations of the
same value.

A tracked observation with a *different* value never refreshes canonical
metadata. It still has to pass through primitive event validation.

## 4. Aggregate confidence

`GameState.confidence` remains the minimum confidence among known HUD fields,
but now those field confidences reflect the latest matching observation rather
than only the observation that originally changed the value.

## 5. Latest state view

The persisted canonical timeline remains semantic-only.

The reducer summary additionally contains `latest_state_view`, a non-persisted
snapshot at the final tracked timestamp. It includes metadata confirmations
that happened after the last semantic transition.

## Acceptance

Re-run only the reducer:

```powershell
tft-analyzer reduce-game-state `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline `
  --timeline-limit 200
```

No OCR, tracking, event detection or validation rerun is required.

Expected invariants:

```text
canonical semantic values remain equivalent to 0.7.0
skipped_validation = 2
applied_with_mismatch = 1
metadata_refreshed > 0
max direct provenance remains small
```

Around 913-943 seconds the canonical gold path must remain:

```text
41 -> 52
```

and must not expose 17 or 1.
