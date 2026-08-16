# Stage 3.5.5 — Scene-aware bench tracking

0.13.4 successfully rejected non-arena board scenes, including the two
`Choose your God wisely` false full-cap snapshots.

The same full-screen scenes were still ingested by the independent bench
tracker. As a result, visually absent bench slots were interpreted as empty and
canonical bench state collapsed toward `0/9`.

0.13.5 applies the already accepted arena scene validity signal to bench
tracking.

## Contract

For `scene_valid == true`:

```text
raw bench candidate -> temporal bench tracker
```

For `scene_valid == false`:

```text
raw bench candidate -> diagnostics only
                    -> canonical bench strict carry
```

Strict carry means:

- status unchanged;
- confidence/provenance unchanged;
- pending transition unchanged;
- no refresh timestamp.

This differs deliberately from `allow_change=False`, because a same-status
candidate on an invalid scene must not refresh provenance either.

## Acceptance

No perception rerun is required:

```powershell
tft-analyzer track-board `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline
```

Expected:

- board behavior identical to 0.13.4;
- `tracked_over_cap=0`;
- `full_cap=7`;
- special scenes remain `scene-bad`;
- bench no longer collapses during those scenes;
- final bench should preserve the last valid arena observation instead of
  becoming zero solely because the match ends on non-arena frames.
