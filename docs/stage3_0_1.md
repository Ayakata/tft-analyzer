# Stage 3.0.1 - Player HP stabilization (0.8.1)

The first full-match player-list run proved the geometry is viable but exposed two failure modes:

```text
panel present: 269 / 271
self selected: 146 / 269
HP parsed:     146 / 146
HP accepted:   144 / 146
```

The main issue was not integer parsing itself. Later HP search windows could beat the calibrated primary HP window by raw OCR confidence and produce trajectories such as:

```text
100 -> 6 -> 100
71  -> 1 -> 71
48  -> 10 -> 48
```

0.8.1 stabilizes both perception and temporal tracking.

## Primary HP geometry

`hp_candidate_0` is now authoritative whenever it produces a valid HP with confidence >= 0.60.

Fallback windows are searched only when the primary candidate is not usable. Fallbacks are weighted by positional priors:

```text
candidate 0 = 1.00
candidate 1 = 0.70
candidate 2 = 0.45
candidate 3 = 0.30
candidate 4 = 0.20
```

This directly addresses cases where candidate 0 read `100` with confidence around 0.67 while a later window read an unrelated `6` with a higher OCR confidence.

## Lazy no-name tie-breaker

The own leaderboard row has no opponent nickname. 0.8.1 uses this only when highlight top-1/top-2 is ambiguous.

Normal frames still use highlight only. On ambiguous frames the recognizer OCRs only the top three highlight candidates and interprets the nickname area:

```text
alphabetic text present -> opponent-name evidence
high-confidence numeric-only text -> own-row no-name evidence
empty/weak OCR -> unknown, not no-name
```

The selection method is recorded as:

```text
highlight_no_name
```

This avoids performing eight nickname OCR calls on every frame and prevents missing OCR text from being treated as positive evidence.

## HP temporal rules

Tracker settings:

```yaml
hp_max_jump_without_confirmation: 25
hp_single_digit_min_confidence: 0.90
suspicious_confirmation_count: 2
```

Rules:

- normal HP decreases up to 25 are accepted immediately;
- increases require confirmation because healing is possible but rare;
- decreases larger than 25 require confirmation;
- two-digit -> one-digit changes require confirmation;
- two-digit -> one-digit observations below confidence 0.90 are rejected immediately.

This specifically protects against crop truncation such as:

```text
48 -> 4
71 -> 1
```

while a real late-game transition such as `17 -> 6` can still be accepted after two high-confidence observations.

## Diagnostics

Player perception summary now includes:

```text
primary_candidate_used
fallback_candidate_used
primary_candidate_rate
ambiguous_self_rows
no_name_fallback_selected
max_hp_observation_gap_s
```

Tracker summary adds:

```text
hp_stabilization:
  pending_count
  rejected_count
  confirmed_change_count
  large_jump_reason_count
```

## Re-run

Fixed HUD OCR remains valid. Re-run only player perception:

```powershell
tft-analyzer perceive-players `
  .\data\matches\20260812T164303Z_4c85a55ea6
```

Inspect the new summary first. If the HP trajectory is plausible, run merged tracking:

```powershell
tft-analyzer track-hud `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline `
  --timeline-limit 271
```
