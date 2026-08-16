# Stage 4.2 — Economy & Tempo Findings (0.16.0)

## Goal

Stage 4.2 is the first layer that consumes `DecisionEpisode` objects and emits
post-game `Finding` objects.

The first analyzer is intentionally meta-independent. Its job is to surface
facts and review landmarks without inventing optimal TFT play from sparse
screenshots.

## Contract

```text
Semantic Actions
      ↓
DecisionEpisode (sparse / partially ordered)
      ↓
EconomyTempoAnalyzer
      ↓
Finding[]
```

A finding carries:

```text
finding_code
category
interpretation = descriptive | data_quality | review_candidate | decision_grade
severity
confidence
decision_id
stage / time range
metrics
evidence_ids
producer_version
limitations
```

0.16.0 intentionally emits **zero** `decision_grade` findings.

## Current rules

### Data quality

`economy_infeasible`
: Required action cost exceeds observed spend. This is an upstream reconstruction
  contradiction and must not be treated as player error.

`required_unexplained_spend`
: At least `U.min > 0` gold cannot be assigned to recognized actions. Severity
  becomes major at the configurable threshold (default 10g).

### Descriptive tempo/economy

`level_up`
: Boundary level increased without roll activity.

`level_and_roll`
: Boundary level increased and the episode also contains refresh activity.

`xp_investment_without_level`
: XP purchase is observed, but boundary level does not increase.

`roll_activity` / `roll_burst_candidate`
: Bounded refresh activity. "Burst candidate" uses only observed action count and
  count bounds; it is not a `ROLLDOWN` or `SLOW_ROLL` classification.

`large_spend`
: Observed spend crosses a descriptive threshold (default 20g).

`positioning_only`
: All actions in the episode are board/bench movement actions.

### Review candidate

`large_spend_low_gold_review`
: Large spend ends below a configurable observed-gold threshold. This is only a
  review landmark. It is explicitly not called a mistake until HP, board strength,
  streak, lobby and meta context exist.

## Sparse evidence policy

The analyzer consumes episode partial ordering as-is. It does not infer exact
click timestamps or reorder actions inside a source window.

## CLI

```powershell
tft-analyzer analyze-episodes `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline
```

Outputs:

```text
<match>/analysis/economy-tempo-analyzer-0.16.0.jsonl
<match>/analysis/economy-tempo-analyzer-0.16.0_summary.json
```


## 0.16.1 semantic correction

The original 0.16.0 `required_unexplained_spend` finding was too strong when
classified as `data_quality`. Sparse capture makes missing semantic actions
expected. See `docs/stage4_2_1.md` for the corrected
`reconstruction_uncertainty` contract.
