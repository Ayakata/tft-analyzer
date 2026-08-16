# Stage 3.2 - Temporal shop state and primitive SHOP_CHANGED (0.10.0)

## Goal

Promote the identity-stabilized shop perception stream into the existing
evidence-first state pipeline without inferring player intent.

```text
shop-rapidocr-0.9.1 Observation
        ↓
TrackedHUDState.shop
        ↓
SHOP_CHANGED
        ↓
EventValidation(field=shop)
        ↓
GameState.shop
```

`TrackedHUDState` remains the common evidence-timeline backbone even though it
now carries fixed HUD, player HP and shop state.

## Canonical shop value

Perception metadata is stripped before tracking:

```json
{
  "slots": ["pyke", null, "ezreal", "ornn", "nami"]
}
```

Only identity-resolved complete observations from `shop-rapidocr-0.9.1` can
enter the tracker.

## Temporal tracking

Default shop TTL:

```yaml
shop: 45.0
```

This is slightly above the observed maximum accepted-snapshot gap of about
40.9 seconds in the calibration match.

Rules:

- first snapshot -> accepted baseline;
- identical snapshot -> refreshed;
- changed snapshot with confidence >= 0.80 -> accepted;
- changed snapshot below 0.80 -> pending until repeated;
- malformed slot vector -> rejected.

No purchase/reroll/round-refresh cause is inferred.

## Primitive event

A semantic shop change emits:

```json
{
  "field": "shop",
  "from": {"slots": ["a", "b", "c", "d", "e"]},
  "to": {"slots": ["a", null, "x", "d", "e"]},
  "changed_slots": [1, 2],
  "slot_change_count": 2,
  "slot_changes": [
    {"index": 1, "from": "b", "to": null},
    {"index": 2, "from": "c", "to": "x"}
  ]
}
```

This is intentionally only a fact about visible shop state.

Later analyzers may combine it with gold/board/bench to infer:

```text
BUY_UNIT
REFRESH_SHOP
automatic shop refresh
```

but those causes do not belong in Stage 3.2.

## Validation

Shop target confidence defaults to 0.80.

The validator also defensively requires exactly five slots, each either null or
a non-empty canonical identity.

Transition-window uncertainty is handled exactly like existing primitive HUD
events.

## Canonical GameState

The reducer initializes `GameState.shop` from the first observed tracked shop
and thereafter changes it only through validated `SHOP_CHANGED`.

`ShopState.locked` remains `null`; lock perception has not been implemented.

## Perception diagnostics correction

The old `resolved_complete_snapshots` label mixed identity completeness with
snapshot acceptance.

When shop perception is rerun, summary now distinguishes:

```text
raw_complete_snapshots
identity_complete_snapshots
accepted_snapshots
```

Compatibility aliases remain available.

This diagnostic correction does not require rerunning shop perception before
Stage 3.2 tracking.

## Acceptance sequence

Existing `shop-rapidocr-0.9.1.jsonl` is sufficient.

```powershell
tft-analyzer track-hud `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline `
  --timeline-limit 271
```

Expected calibration-match shape:

```text
shop observations ≈ 194
shop semantic changes ≈ 57
```

Then:

```powershell
tft-analyzer detect-hud-events `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline `
  --timeline-limit 260

tft-analyzer validate-hud-events `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline `
  --timeline-limit 260

tft-analyzer reduce-game-state `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline `
  --timeline-limit 260
```

The old 152 primitive events plus roughly 57 shop changes imply about 209
events if temporal tracking accepts every identity-stabilized shop transition.
The exact acceptance count is a real-match measurement, not a hard-coded test.
