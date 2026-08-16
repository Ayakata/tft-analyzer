# Stage 4.4 — Context-Aware Review Analyzer

Version: 0.18.0

## Goal

Move from descriptive episode landmarks to context-aware post-game review
candidates without pretending that the system can already grade TFT strategy.

The analyzer consumes:

```text
DecisionEpisode
+ EpisodePlayerContext
+ semantic actions
+ episode economy
```

and produces:

```text
Finding(interpretation="review_candidate")
```

## Trust boundary

Every strategic rule must use the 0.17.1 feature-trust contract.

```text
known != usable_for_strategy
```

HUD pressure features may be used when trusted. Board and bench features are
literal only when their boundary trust explicitly permits strategic use.

For example:

```text
board=4/7
semantics=lower_bound
usable_for_strategy=false
```

cannot trigger any "three empty slots" finding.

## Economy boundary

All action-spend reasoning uses:

```text
episode.economy
```

Never:

```text
gold_after - gold_before
```

because sparse boundary changes can contain natural income and hidden
transitions.

## Infeasible episodes

If the economy constraint system is infeasible, the analyzer emits:

```text
context_review_blocked_infeasible
```

as `data_quality` and returns immediately for that episode.

No strategic review candidate is emitted from contradictory evidence.

## Initial rules

### economy_commitment_under_pressure

Trusted HP is at or below the pressure threshold and observed action spend is
at least the economy-commitment threshold.

### large_spend_under_pressure

Same, but spend reaches the larger commitment threshold. This replaces the
generic commitment finding rather than duplicating it.

### low_hp_roll_activity

Trusted HP is under pressure and semantic shop-refresh activity is observed.

### low_hp_level_up

Trusted HP is under pressure and the trusted boundary level increases.

### high_gold_under_pressure

Trusted post-episode HUD still shows substantial gold while HP is critical.

This is a review landmark only. It is deliberately not named "greed".

### near_elimination_activity

Any observed semantic activity at near-elimination HP is promoted as a
high-priority review landmark.

### trusted_board_below_capacity

This rule is allowed to run only when the post-episode board count is explicitly
`usable_for_strategy=true`. It exists both as a useful future signal and as an
executable test of the trust contract.

## Policy

0.18.0 emits:

```text
review_candidate
data_quality (only as a strategic-analysis block)
```

It emits zero:

```text
decision_grade
```

A later stage may add actual strategic grading only after board strength,
champion identities/upgrades, items, traits, streak/lobby state and
patch-specific policy are sufficiently trusted.
