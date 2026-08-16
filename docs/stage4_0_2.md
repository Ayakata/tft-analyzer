# Stage 4.0.2 — Bounded Economy Ledger

0.14.1 fixed absolute XP but still represented remaining gold too precisely.

## Reroll interval

For:

```text
observed spend = 19
shop refresh signature = true
reroll cost = 2
```

the evidence supports:

```text
reroll count = [1..9]
reroll spend = [2..18]
unallocated  = [1..17]
```

not `17 exact`.

Exact XP spend is removed from the available budget before calculating the
reroll upper bound.

## Unpriced BUY_UNIT

Champion identity is known from the shop, but champion cost is not yet part of
the trusted game-data contract.

Therefore a recognized buy has:

```text
count exact
spend_min = 0
spend_max = unknown
```

At window level it may account for all remaining observed spend.

Example:

```text
observed spend = 35
BUY_XP x8 = 32 exact
BUY[rhaast] = unpriced

action spend      [32..35]
unallocated spend [0..3]
```

## Ledger notation

```text
19=K[2..18]+U[1..17]
35=K[32..35]+U[0..3],buy?x1
```

`K` is spend attributable to recognized action classes.
`U` is spend still unallocated after all currently supported explanations.
