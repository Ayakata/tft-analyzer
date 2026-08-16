# Stage 5.0 — Evidence-Aware Player Acquisition History

Current release: 0.20.1

## Goal

Extract champion acquisition facts already present in semantic shop/action
evidence without pretending sparse screenshots establish the player's current
roster.

## Core distinction

The layer proves historical acquisition lower bounds:

```text
rhaast acquired>=4
reksai acquired>=3
```

It does not prove current ownership:

```text
current_ownership_status = not_established
```

This distinction is fundamental. Sparse capture can miss sales and other
within-window actions.

## Source contract

Inputs:

```text
semantic actions
DecisionEpisodes
game context
```

Relevant actions:

```text
BUY_UNIT
SELL_UNIT
UNKNOWN_ECON_ACTION
```

All relevant actions must be covered by DecisionEpisodes by default.

## Confirmed acquisition evidence

A BUY identity is promoted into confirmed acquisition history when:

```text
action confidence >= configured threshold
AND
BUY cost validation is not a hard conflict
```

Default confidence threshold:

```text
0.68
```

The count is expressed in base-copy equivalents. Three observed purchases of
the same champion remain three acquired copies even if the game later combines
them into one 2-star unit.

Per-champion field:

```text
confirmed_acquired_copy_lower_bound
```

Global semantic:

```text
acquisition_semantics = confirmed_history_lower_bound
```

## Candidate acquisition evidence

Readable identity from a cost-conflicted or insufficiently supported BUY stays
candidate evidence.

Example:

```text
?zoe x1
```

It does not increase the confirmed acquisition lower bound.

## SELL evidence

SELL events are preserved because they matter for future reconstruction, but
0.20.1 deliberately does not derive current ownership from them.

Reasons:

```text
sparse screenshots may miss other sales
current SELL identity coverage is incomplete
sold-unit star level is unknown
```

Therefore:

```text
complete_sell_history_known = false
current_ownership_status = not_established
```

A sale does not decrement historical acquisition evidence: selling a Rhaast
does not undo the fact that Rhaast was previously acquired.

The old `surviving_copy_lower_bound` concept from 0.20.0 is removed from the
0.20.1 public schema.

## UNKNOWN_ECON

Required unresolved spend is retained as:

```text
unresolved_economy_action_count
unresolved_economy_spend_min/max
```

It may hide BUY/ROLL/XP/other actions but is never converted into invented
champion acquisitions.

## Output

One `EpisodeRosterEvidence` per DecisionEpisode:

```text
before
delta
after
```

Cumulative champion facts include:

```text
confirmed_acquired_copy_lower_bound
candidate_acquired_copy_count
identified_sell_unit_count
current_ownership_status = not_established
```

Snapshot-level semantics include:

```text
acquisition_semantics = confirmed_history_lower_bound
complete_roster_known = false
complete_sell_history_known = false
current_ownership_status = not_established
```

## Non-goals

0.20.1 does not infer:

```text
current complete roster
board champion identity
bench champion identity
board-vs-bench assignment
star level
traits
items
combat strength
```

Current presence/ownership becomes a separate evidence problem for the next
Stage 5 layer.
