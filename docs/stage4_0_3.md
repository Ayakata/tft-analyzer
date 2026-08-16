# Stage 4.0.3 — Economy Action Existence Semantics

0.14.2 introduced correct bounded spend intervals, but still converted every
non-zero upper bound into an `UNKNOWN_ECON_ACTION`.

That confuses:

```text
possible additional action
```

with:

```text
required additional action
```

## Contract

For a ledger interval:

```text
U[min..max]
```

the action existence rule is:

```text
min > 0
=> additional spend exists in every compatible explanation
=> emit UNKNOWN_ECON_ACTION

min == 0 and max > 0
=> recognized actions may explain the whole observed spend
=> keep uncertainty in ledger only
=> do not emit UNKNOWN_ECON_ACTION
```

Examples:

```text
10=K[2..10]+U[0..8]
```

No unknown action is emitted.

```text
35=K[32..35]+U[0..3],buy?x1
```

No unknown action is emitted; the unpriced buy can explain the remainder.

```text
19=K[2..18]+U[1..17]
```

`UNKNOWN_ECON_ACTION[1..17g]` is emitted because at least 1 gold necessarily
remains outside the recognized action classes.

The ledger remains unchanged and therefore preserves all uncertainty even when
no separate action exists.
