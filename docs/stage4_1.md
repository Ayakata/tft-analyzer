# Stage 4.1 — Sparse Decision Episodes

## Goal

Convert Stage 4.0 semantic actions into a more useful trajectory unit:

```text
state before
+ bounded observed activity
+ economy constraints
-> state after
```

The episode is **not** a reconstructed click trace.

## Sparse evidence contract

The recorder frequently provides screenshots roughly seconds apart. TFT can
contain several buys, sells, rerolls, XP purchases and board/bench moves within
one second. Therefore Stage 4.1 makes only the claims supported by evidence.

For one source window:

```text
{BUY Rhaast, BUY XP x8}
```

means both actions are compatible with the transition. It does not mean the
buy happened before XP or vice versa.

For consecutive non-overlapping source windows:

```text
{BUY, XP} -> {REROLL}
```

we preserve only window-level partial order.

Contracts expose:

```text
sampling.mode = sparse_snapshots
sampling.ordering_guarantee = window_partial_order
sampling.exact_action_timestamps_known = false
sampling.exact_intra_window_order_known = false
```

No downstream analyzer should silently strengthen these guarantees.

## Grouping

Active action windows are grouped when all conditions hold:

```text
same TFT stage
idle gap <= 15 s
whole episode <= 45 s
no stage-change boundary
```

Both thresholds are configurable.

These settings describe how much observed activity belongs to one planning
burst. They do not synthesize actions in inactive gaps.

## Strategic labels

Stage 4.1 is intentionally conservative.

Safe labels only:

```text
position-only actions -> POSITIONING_CHANGE
XP purchase + observed level increase -> LEVEL_UP
otherwise -> OTHER
```

In particular, multiple rerolls are not yet automatically classified as
`ROLLDOWN`, `SLOW_ROLL` or `STABILIZE`.

Those concepts require strategic context and belong to the analyzer layer.

## Economy

Episode economy aggregates the Stage 4.0 ledger without changing it:

```text
observed spend
required action spend interval
compatible spend interval
unallocated spend interval
infeasible window count
deficit
required unknown / uncertainty-only counts
```

An infeasible Zoe window therefore remains infeasible inside the episode. It is
not repaired or redistributed across neighboring windows.

## Provenance

Each `DecisionEpisode` stores:

```text
window_indices
action_ids
action_groups
evidence_ids per action group
state_before / state_after
economy
sampling
confidence
extractor_version
```

The episode ID is deterministic from match ID, source windows and extractor
version.

## CLI

```powershell
tft-analyzer build-episodes `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline
```

The latest `semantic-action-fusion-*_summary.json` is selected automatically.
An explicit source can be supplied with `--action-summary`.

## Acceptance focus

For the canonical sparse match, validate:

- every Stage 4.0 action is covered exactly once;
- same-stage bursts around 3-5, 3-6, 4-2, 4-6 and 5-2 merge sensibly;
- stage boundaries do not merge;
- compound windows remain unordered groups;
- Zoe infeasibility survives episode aggregation;
- no exact action sequence is claimed anywhere.
