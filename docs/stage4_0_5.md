# Stage 4.0.5 — Explicit Game Context + Set-Scoped Catalog + BUY Validation

## Why explicit context

Data Dragon version and TFT set are different concepts.

```text
set   = TFT17
patch = 16.16
Data Dragon version = 16.16.1
```

A Data Dragon champion catalog may contain records from several TFT sets at
once. Therefore a production analyzer should not treat the full file as one
roster.

## Context precedence

```text
1. CLI --set / --patch
2. <match_dir>/game_context.json
3. configs/default.yaml game.set / game.patch
4. fallback roster inference
```

An explicit CLI set that conflicts with existing match metadata requires:

```text
--force-game-context
```

The persisted `game_context.json` records:

```text
set_id
patch
data_dragon_version
resolution_source
catalog provider / locale / sha256
scoped champion count
auto-inference diagnostics when used
```

## Set-scoped price resolution

Once `set_id=TFT17`, only champion records whose Riot ID belongs to `TFT17_`
participate in cost lookup.

Examples in the canonical catalog:

```text
Lissandra:
  TFT16 = 4
  TFT17 = 1

Rek'Sai:
  TFT16 = 2
  TFT17 = 1

Zoe:
  TFT16 = 3
  TFT17 = 2
```

Under an explicit TFT17 context the prices are no longer ambiguous.

## Fallback auto inference

Auto inference is not the primary path. It scores the observed shop roster over
TFT<N> namespaces and requires at least two names unique to the winning set,
plus confidence/margin thresholds.

If the fallback cannot resolve the set conservatively, inference stops and asks
for `--set`.

## BUY cost validation

After the entire bounded economy ledger is assembled, each fully priced BUY
receives:

```text
cost_consistent
cost_possible
cost_conflict
unpriced
unobserved
```

`cost_conflict` means:

```text
observed window spend < trusted BUY cost
```

The action is retained for QA, but its confidence is reduced to 0.45/ambiguous.

This is intentionally useful for the canonical Zoe example:

```text
TFT17 Zoe cost = 2
observed window gold delta = -1
=> BUY[zoe] cost_conflict
```

while:

```text
TFT17 Rhaast cost = 3
observed window gold delta = -3
=> cost_consistent
```
