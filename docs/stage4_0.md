# Stage 4.0 — Semantic Action Fusion MVP

The accepted Stage 3.5 trajectory now provides four complementary streams:

```text
HUD:   stage / gold / level / XP
shop:  five champion identities
board: canonical occupied cells
bench: canonical occupied slots
```

Stage 4.0 fuses *changes* across those streams into bounded-window semantic
actions.

## Important timing contract

The recorder currently saves evidence at a sparse, adaptive cadence. Therefore
an interval such as:

```text
264.1s -> 274.1s
```

may contain more than one atomic click.

0.14.0 does not invent precise timestamps or ordering. Each inferred action has:

```text
start_timestamp_s
end_timestamp_s
confidence
quality
params
signals
evidence_ids
```

and may carry `aggregate_window=true`.

## MVP rules

### Refresh shop

Strong support requires:

```text
>= 4 changed shop slots
>= 4 occupied slots before and after
gold decrease >= reroll cost
no stage/round transition
```

A shop refresh coincident with stage change is marked diagnostically as an
automatic round refresh candidate and is **not** emitted as `refresh_shop`.

### Buy unit

Primary evidence:

```text
shop champion -> empty slot
+ board/bench total unit count increases
```

The champion name is taken from the cleared shop slot when available.

A weaker supported rule allows shop-clear + gold spend even if the occupancy
trajectory did not resolve the additional unit.

### Purchase XP

Strong support:

```text
XP increases by configured XP purchase amount
+ gold decreases by configured XP purchase cost
```

The current recorded UI uses 4 gold / 4 XP; both values remain configurable.

### Bench/board transfer

```text
board +N
bench -N
total units unchanged
```

or the inverse, only when the canonical board frame is usable and the arena
scene is valid.

### Sell

Supported evidence:

```text
total canonical units decreases
+ gold increases
+ no stage transition
+ valid arena scene
```

Identity is intentionally left unknown until bench/board identity exists.

### Unknown economy spend

A negative observed gold delta inside the same round that cannot be explained
by an observed reroll/XP/buy signal is retained as:

```text
unknown_econ_action
```

rather than silently discarded.

## Output

```text
actions/
  semantic-action-fusion-0.14.0.jsonl
  semantic-action-fusion-0.14.0_windows.jsonl
  semantic-action-fusion-0.14.0_summary.json
```

The windows artifact is diagnostic ground truth for later validation and
decision-episode extraction.

## Next acceptance

Run on the canonical real match and inspect:

```powershell
tft-analyzer infer-actions `
  .\data\matches\20260812T164303Z_4c85a55ea6 `
  --timeline
```

We should validate:
- rerolls against visible shop/gold behavior;
- buys against shop slot clears and bench growth;
- XP purchases against XP/gold;
- whether sparse windows generate too many compound/unknown actions;
- transfer events only around trustworthy canonical board snapshots.
