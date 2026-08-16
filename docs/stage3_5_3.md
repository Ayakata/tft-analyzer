# Stage 3.5.3 — Board formation QA export

0.13.2 fixed the semantic board pipeline:

- HUD level is resolved;
- canonical occupied count never exceeds level;
- the known 1642.609 L8 frame becomes an atomic 8/8 board snapshot.

The remaining acceptance question is **phase purity**: are all `full-cap`
snapshots actual planning formations, or can combat occasionally satisfy
`candidate_occupied_count == level`?

0.13.3 adds no tracking changes. It only exports evidence selected from tracked
board states.

## Command

```powershell
tft-analyzer board-qa `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --kind full-cap `
  --kind plan-ok `
  --open
```

The latest `board-occupancy-tracker-*.jsonl` is auto-discovered.

## Output

```text
tracking/board-formation-qa-0.13.3/
  full-cap/*.png
  plan-ok/*.png
  manifest.json
  index.html
```

The HTML gallery is local and references the exported PNG files.

Each frame is labelled with:

```text
timestamp
stage
level
round age
candidate occupied count
canonical occupied count
uncertain count
gate reason
canonical four-row occupancy string
```

The QA exporter uses the immutable evidence index to locate the original frame.
