# Stage 4.3.1 — Context Feature Trust Semantics

## Purpose

This release does not change perception. It prevents downstream strategic
analysis from treating every present context value as equally trustworthy.

Exact evidence alignment answers:

```text
"Did these HUD/board/bench values come from the same recorded evidence?"
```

Feature trust answers:

```text
"Can this value be interpreted literally for strategy?"
```

Those are intentionally different questions.

## Trust contract

Each boundary exposes trust for:

```text
hp
gold
level
xp_absolute
board_count
board_utilization
bench_count
```

Each feature records:

```text
known
semantics
usable_for_strategy
reason
source
```

Supported semantics:

```text
exact
lower_bound
carried
unusable
unknown
```

## Board semantics

The canonical board tracker is conservative. Without a strong usable snapshot,
an occupied count means that many occupied cells are confirmed; it does not
prove every other cell is empty.

Therefore:

```text
4/7
```

must not be interpreted as:

```text
"the player intentionally fielded only four of seven available units"
```

unless the boundary trust is `exact`.

A strong usable snapshot can certify exact board count/utilization.

Scene-invalid boundaries are `unusable`, regardless of exact evidence-ID
alignment.

## Bench semantics

The current bench context remains descriptive but is not certified exact for
strategic rules. It is therefore not yet `usable_for_strategy`.

## Gold boundary semantics

`gold_after - gold_before` describes two observed states and may include natural
income or hidden transitions between sparse screenshots.

It is never action accounting.

Downstream rules must use:

```text
episode.economy
```

for spend constraints and action-cost reasoning.

## Downstream rule

A context-aware analyzer must check `usable_for_strategy` before making literal
board/bench claims.

This guard is deliberately stronger than `known`.
