# Stage 4.0.1 — Economy Ledger + Absolute XP

The first real 0.14.0 run proved the cross-stream fusion concept, but exposed
two accounting problems.

## 1. Gold was treated as binary "explained / unexplained"

Example:

```text
gold delta: -5
shop refresh detected
```

0.14.0 emitted a reroll and then considered the window explained.

0.14.1 allocates only what is actually known:

```text
observed spend       5
reroll fixed minimum 2
residual              3
```

The residual is retained as `unknown_econ_action`.

## 2. BUY_UNIT is recognized but not yet priceable

Shop identity knows the champion name, but the current project does not yet
have a trusted champion-cost table in its game-data contract.

Therefore:

```text
BUY[rhaast]
gold delta -5
```

is represented as:

```text
recognized buy count: 1
buy price: unknown
residual upper bound: 5
```

rather than inventing Rhaast's price or declaring 5 gold unexplained exactly.

Future champion-cost data can collapse this upper bound without changing the
action contract.

## 3. Absolute XP progress

Same-level XP delta is insufficient across:

```text
L5 18/20 -> L6 6/36
```

0.14.1 infers the modal `required XP` for every observed level from the HUD
trajectory and constructs a match-relative cumulative XP coordinate:

```text
absolute_xp(level, current)
  = sum(required XP of lower observed levels)
  + current XP
```

When the requirement chain is complete, XP delta remains valid across a level
transition.

This allows:

```text
absolute XP +8
gold -8
same round
```

to become:

```text
PURCHASE_XP x2
```

instead of the previous fallback `x1`.

## Outputs

```text
actions/
  semantic-action-fusion-0.14.1.jsonl
  semantic-action-fusion-0.14.1_windows.jsonl
  semantic-action-fusion-0.14.1_ledger.jsonl
  semantic-action-fusion-0.14.1_summary.json
```

Timeline ledger notation:

```text
5=2+=3
```

means exact residual 3 after 2 fixed gold.

```text
5=0+<=5,buy?x1
```

means one recognized but unpriced buy exists, so 5 is only an upper bound on
the still-unallocated spend.
